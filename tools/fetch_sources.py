#!/usr/bin/env python3
"""Snapshot every source URL into sources/cache/<sha1(url)>.txt.

* Web pages: headless Chromium through Playwright, rendered body text.
* PDFs and other files: downloaded with the same browser context, PDFs turned
  into text with `pdftotext -layout` (form feeds between pages are kept, so a
  quote can be located by page).
* Wayback Machine: read-only availability lookup only. No save requests.
  For dead or blocked pages that have an archive copy, the copy is also
  fetched into sources/cache/<sha1(url)>.archive.txt.
* Resumable: URLs fetched in the last 30 days are skipped unless --refresh.
  Rows with state "error" (timeouts, crashes) are retried on every run.

sources/index.json is written every 20 results, so a crash keeps progress.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import io
import json
import os
import random
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textnorm import sha1, sha256  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "sources")
CACHE = os.path.join(SRC, "cache")
INDEX = os.path.join(SRC, "index.json")
CLAIMS_URLS = os.path.join(ROOT, "claims", "source_urls.json")

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
TIMEOUT_MS = 45_000
HOST_GAP_S = 2.5
WAYBACK_GAP_S = 3.0
FILE_EXT = re.compile(r"\.(pdf|xlsx?|csv|docx?|odt|ods|zip|txt|json|xml)(?:$|[?#])", re.I)
BLOCK_PATTERNS = re.compile(
    r"just a moment|checking your browser|attention required|verify you are (?:a )?human|"
    r"are you a robot|captcha|access denied|request blocked|unusual traffic|enable javascript and cookies|"
    r"ddos protection|cf-browser-verification|bot detection|pardon our interruption",
    re.I)


def now_utc() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def load_index() -> dict:
    if os.path.exists(INDEX):
        return json.load(open(INDEX, encoding="utf-8"))
    return {}


def save_index(idx: dict) -> None:
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(idx.items())), f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDEX)


def host_of(url: str) -> str:
    return urllib.parse.urlsplit(url).netloc.lower()


def pdf_to_text(data: bytes) -> str:
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "f.pdf")
        open(p, "wb").write(data)
        out = os.path.join(td, "f.txt")
        r = subprocess.run(["pdftotext", "-layout", "-enc", "UTF-8", p, out],
                           capture_output=True, timeout=180)
        if r.returncode != 0 or not os.path.exists(out):
            raise RuntimeError("pdftotext failed: " + r.stderr.decode("utf-8", "replace")[:200])
        return open(out, encoding="utf-8", errors="replace").read()


def file_to_text(data: bytes, ctype: str, url: str):
    """Return (kind, text) for a downloaded file."""
    ct = (ctype or "").lower()
    low = url.lower().split("?")[0]
    if data[:5] == b"%PDF-" or "pdf" in ct:
        return "pdf", pdf_to_text(data)
    if "spreadsheetml" in ct or low.endswith(".xlsx"):
        try:
            import openpyxl
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
            parts = []
            for ws in wb.worksheets:
                parts.append(f"## sheet {ws.title}")
                for row in ws.iter_rows(values_only=True):
                    parts.append("\t".join("" if v is None else str(v) for v in row))
                parts.append("\f")
            return "xlsx", "\n".join(parts)
        except Exception as e:  # noqa: BLE001
            raise RuntimeError(f"xlsx read failed: {e}")
    if any(k in ct for k in ("text/", "json", "xml", "csv")) or low.endswith((".csv", ".txt", ".json", ".xml")):
        for enc in ("utf-8", "latin-1"):
            try:
                return "text", data.decode(enc)
            except UnicodeDecodeError:
                continue
    raise RuntimeError(f"unsupported file type: {ct or 'unknown'}")


def classify(rec: dict) -> str:
    st = rec.get("http_status")
    n = rec.get("n_chars") or 0
    err = rec.get("error") or ""
    if "unsupported file type" in err:
        return "unsupported"     # fetched fine, but no text extractor (zip, doc)
    if err.startswith("blocked") or st in (401, 403, 429, 451):
        return "blocked"
    if st and (st in (404, 410) or st >= 500):
        return "dead"
    if st and 400 <= st < 500:
        return "dead"
    if re.search(r"ERR_NAME_NOT_RESOLVED|ERR_CONNECTION_REFUSED|ERR_ADDRESS_UNREACHABLE|"
                 r"ERR_CERT|ERR_SSL|ERR_CONNECTION_RESET|ERR_EMPTY_RESPONSE|ENOTFOUND|getaddrinfo", err):
        return "dead"
    if err:
        return "error"
    if n < 80:
        return "dead"           # empty page
    return "ok"


class HostGate:
    """Polite spacing: one request at a time per host, HOST_GAP_S apart."""

    def __init__(self):
        self.locks = defaultdict(asyncio.Lock)
        self.last = defaultdict(float)

    async def __aenter_host__(self, host):
        await self.locks[host].acquire()
        wait = self.last[host] + HOST_GAP_S - time.monotonic()
        if wait > 0:
            await asyncio.sleep(wait + random.random() * 0.5)

    def release(self, host):
        self.last[host] = time.monotonic()
        self.locks[host].release()


async def fetch_one(ctx, url: str) -> dict:
    rec = {"url": url, "final_url": None, "http_status": None, "content_type": None,
           "kind": None, "fetched_at": now_utc(), "text_sha256": None, "n_chars": 0, "error": None}
    text = None

    async def via_request():
        nonlocal text
        resp = await ctx.request.get(url, timeout=TIMEOUT_MS, max_redirects=10)
        rec["http_status"] = resp.status
        rec["final_url"] = resp.url
        rec["content_type"] = resp.headers.get("content-type")
        body = await resp.body()
        if resp.status >= 400:
            return
        ct = (rec["content_type"] or "").lower()
        if "html" in ct and body[:5] != b"%PDF-":
            return "html"     # a page after all: let the browser render it
        kind, t = file_to_text(body, ct, resp.url)
        rec["kind"] = kind
        rec["raw_sha256"] = hashlib.sha256(body).hexdigest()
        text = t

    try:
        if FILE_EXT.search(url):
            r = await via_request()
            if r != "html":
                return finish(rec, text)
        page = await ctx.new_page()
        try:
            try:
                resp = await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                if "Download is starting" in msg or "ERR_ABORTED" in msg:
                    await page.close()
                    page = None
                    await via_request()
                    return finish(rec, text)
                raise
            if resp is not None:
                rec["http_status"] = resp.status
                rec["content_type"] = resp.headers.get("content-type")
            ct = (rec["content_type"] or "").lower()
            if ct and "html" not in ct and "xml" not in ct and "text/plain" not in ct:
                await page.close()
                page = None
                await via_request()
                return finish(rec, text)
            try:
                await page.wait_for_load_state("networkidle", timeout=8000)
            except Exception:  # noqa: BLE001
                pass
            rec["final_url"] = page.url
            title = ""
            try:
                title = await page.title()
            except Exception:  # noqa: BLE001
                pass
            body = await page.evaluate("() => document.body ? document.body.innerText : ''")
            rec["kind"] = "html"
            text = (title + "\n\n" + (body or "")).strip()
            if len(text) < 3000 and BLOCK_PATTERNS.search(text[:3000]):
                rec["error"] = "blocked: bot wall or captcha page"
        finally:
            if page is not None:
                await page.close()
    except Exception as e:  # noqa: BLE001
        rec["error"] = (type(e).__name__ + ": " + str(e).splitlines()[0])[:300]
    return finish(rec, text)


def finish(rec: dict, text) -> dict:
    if text is not None:
        text = text.replace("\r\n", "\n")
        rec["n_chars"] = len(text)
        rec["text_sha256"] = sha256(text)
        with open(os.path.join(CACHE, sha1(rec["url"]) + ".txt"), "w", encoding="utf-8") as f:
            f.write(text)
    rec["state"] = classify(rec)
    return rec


def wayback_lookup(url: str) -> dict:
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    req = urllib.request.Request(api, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        data = json.loads(r.read().decode("utf-8"))
    snap = (data.get("archived_snapshots") or {}).get("closest") or {}
    if snap.get("available") and snap.get("url"):
        return {"archive_url": snap["url"].replace("http://web.archive.org", "https://web.archive.org"),
                "archive_timestamp": snap.get("timestamp"), "archive_status": snap.get("status")}
    return {"archive_url": None, "archive_timestamp": None, "archive_status": None}


async def wayback_worker(urls, idx, refresh, lock_save):
    loop = asyncio.get_running_loop()
    gap = WAYBACK_GAP_S
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)
    done = 0
    for u in urls:
        rec = idx.get(u) or {}
        chk = rec.get("archive_checked_at")
        if chk and not refresh and datetime.strptime(chk, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) > cutoff:
            continue
        for attempt in range(4):
            try:
                res = await loop.run_in_executor(None, wayback_lookup, u)
                break
            except Exception as e:  # noqa: BLE001
                res = {"archive_error": str(e)[:200]}
                # archive.org rate-limits hard: back off long on 429 and slow down for good
                if "429" in str(e):
                    gap = min(gap * 1.5, 15.0)
                await asyncio.sleep((60 if "429" in str(e) else 5) * (attempt + 1))
        async with lock_save:
            rec = idx.setdefault(u, {"url": u})
            rec.update(res)
            if "archive_error" not in res:
                rec.pop("archive_error", None)
                rec["archive_checked_at"] = now_utc()
            done += 1
        await asyncio.sleep(gap)
        if done % 50 == 0:
            async with lock_save:
                save_index(idx)
            print(f"  wayback {done} looked up", flush=True)
    return done


async def launch_browser(pw):
    """Launch headless Chromium. If this Playwright's own build is missing,
    fall back to the newest headless shell already in the Playwright cache."""
    try:
        return await pw.chromium.launch(headless=True)
    except Exception as e:  # noqa: BLE001
        if "Executable doesn't exist" not in str(e):
            raise
    import glob as _glob
    cands = sorted(_glob.glob(os.path.expanduser(
        "~/Library/Caches/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell")))
    cands += sorted(_glob.glob(os.path.expanduser(
        "~/.cache/ms-playwright/chromium_headless_shell-*/chrome-headless-shell-*/chrome-headless-shell")))
    if not cands:
        raise RuntimeError("no Chromium found; run: python3 -m playwright install chromium")
    return await pw.chromium.launch(headless=True, executable_path=cands[-1])


async def main_async(args):
    os.makedirs(CACHE, exist_ok=True)
    urls = json.load(open(CLAIMS_URLS, encoding="utf-8"))["urls"]
    if args.only:
        urls = [u for u in urls if re.search(args.only, u)]
    idx = load_index()
    if not args.only:
        # forget URLs that are no longer in the data (and their snapshots)
        for u in [u for u in idx if u not in set(urls)]:
            for ext in (".txt", ".archive.txt"):
                p = os.path.join(CACHE, sha1(u) + ext)
                if os.path.exists(p):
                    os.remove(p)
            del idx[u]
    cutoff = datetime.now(timezone.utc) - timedelta(days=30)

    def due(u):
        r = idx.get(u)
        if not r or not r.get("fetched_at") or args.refresh:
            return True
        if r.get("state") == "error":
            return True
        t = datetime.strptime(r["fetched_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
        return t < cutoff

    todo = [] if args.wayback_only else [u for u in urls if due(u)]
    if args.limit:
        todo = todo[: args.limit]
    # interleave hosts so the workers do not queue on one site
    by_host = defaultdict(list)
    for u in todo:
        by_host[host_of(u)].append(u)
    order = []
    while any(by_host.values()):
        for h in list(by_host):
            if by_host[h]:
                order.append(by_host[h].pop(0))
    print(f"{len(urls)} urls, {len(order)} to fetch", flush=True)

    from playwright.async_api import async_playwright
    lock_save = asyncio.Lock()
    gate = HostGate()
    queue: asyncio.Queue = asyncio.Queue()
    for u in order:
        queue.put_nowait(u)
    counter = {"n": 0}

    async with async_playwright() as pw:
        browser = await launch_browser(pw)
        ctx = await browser.new_context(user_agent=UA, locale="pt-BR", viewport={"width": 1366, "height": 900},
                                        accept_downloads=False, ignore_https_errors=True,   # many .gov.br sites send broken cert chains

                                        extra_http_headers={"Accept-Language": "pt-BR,pt;q=0.9,en;q=0.8"})

        async def worker():
            nonlocal ctx
            while True:
                try:
                    u = queue.get_nowait()
                except asyncio.QueueEmpty:
                    return
                h = host_of(u)
                await gate.__aenter_host__(h)
                try:
                    rec = await asyncio.wait_for(fetch_one(ctx, u), timeout=TIMEOUT_MS / 1000 * 3)
                except Exception as e:  # noqa: BLE001
                    rec = finish({"url": u, "final_url": None, "http_status": None, "content_type": None,
                                  "kind": None, "fetched_at": now_utc(), "text_sha256": None, "n_chars": 0,
                                  "error": (type(e).__name__ + ": " + str(e))[:300] or "timeout"}, None)
                finally:
                    gate.release(h)
                async with lock_save:
                    old = idx.get(u, {})
                    for k in ("archive_url", "archive_timestamp", "archive_status", "archive_checked_at"):
                        if k in old:
                            rec.setdefault(k, old[k])
                    if old.get("text_sha256") and rec.get("text_sha256") and old["text_sha256"] != rec["text_sha256"]:
                        rec["changed_since"] = old.get("fetched_at")
                    idx[u] = rec
                    counter["n"] += 1
                    if counter["n"] % 20 == 0:
                        save_index(idx)
                        print(f"  {counter['n']}/{len(order)}", flush=True)

        tasks = [asyncio.create_task(worker()) for _ in range(args.concurrency)]
        wb_task = None
        if not args.no_wayback:
            wb_task = asyncio.create_task(wayback_worker(urls if not args.limit else order, idx, args.refresh, lock_save))
        await asyncio.gather(*tasks)
        async with lock_save:
            save_index(idx)
        if wb_task:
            await wb_task
            async with lock_save:
                save_index(idx)

        # archive copies for dead or blocked pages
        if not args.no_wayback:
            need = [u for u in urls if idx.get(u, {}).get("state") in ("dead", "blocked", "error")
                    and idx[u].get("archive_url")
                    and (args.refresh or not idx[u].get("archive_fetched_at"))]
            print(f"archive copies to fetch: {len(need)}", flush=True)
            for u in need:
                a = idx[u]["archive_url"]
                m = re.match(r"(https?://web\.archive\.org/web/\d+)(/.*)", a)
                raw = (m.group(1) + "id_" + m.group(2)) if m else a
                r = await fetch_one(ctx, raw)
                rec = idx[u]
                rec["archive_fetched_at"] = r["fetched_at"]
                rec["archive_http_status"] = r["http_status"]
                rec["archive_state"] = r["state"]
                rec["archive_n_chars"] = r["n_chars"]
                rec["archive_text_sha256"] = r["text_sha256"]
                src = os.path.join(CACHE, sha1(raw) + ".txt")
                if os.path.exists(src):
                    os.replace(src, os.path.join(CACHE, sha1(u) + ".archive.txt"))
                await asyncio.sleep(1.5)
            save_index(idx)
        await browser.close()

    states = defaultdict(int)
    for u in urls:
        states[idx.get(u, {}).get("state", "missing")] += 1
    print("states:", dict(states))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--refresh", action="store_true", help="re-fetch everything")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", help="regex: only URLs matching this")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--no-wayback", action="store_true")
    ap.add_argument("--wayback-only", action="store_true", help="only the archive lookups and copies")
    args = ap.parse_args()
    asyncio.run(main_async(args))


if __name__ == "__main__":
    main()
