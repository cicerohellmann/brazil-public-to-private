#!/usr/bin/env python3
"""Ask the Wayback Machine (Save Page Now) to save a public copy of sources.

Cicero approved this as ONE bundled final step, after every source is final.
Default is a dry run that only lists what would be sent. Nothing is sent
without --go.

Only the public source URLs go to archive.org. A URL is submitted when it has
no archive copy newer than --max-age-days (default 365) and its page is not
dead. Polite rate: one request every 5-10 seconds, long back-off on HTTP 429.
Results go into sources/index.json: archive_url, archive_timestamp, saved_at.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INDEX = os.path.join(ROOT, "sources", "index.json")
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")


def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def save_index(idx):
    tmp = INDEX + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(dict(sorted(idx.items())), f, ensure_ascii=False, indent=1)
    os.replace(tmp, INDEX)


def needs_copy(rec, cutoff):
    if rec.get("state") == "dead":
        return False
    ts = rec.get("archive_timestamp")
    if not ts:
        return True
    try:
        t = datetime.strptime(ts[:14], "%Y%m%d%H%M%S").replace(tzinfo=timezone.utc)
    except ValueError:
        return True
    return t < cutoff


def submit(url):
    """Returns (archive_url or None, http_status)."""
    req = urllib.request.Request("https://web.archive.org/save/" + url, headers={"User-Agent": UA})
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            loc = r.headers.get("Content-Location") or ""
            final = r.geturl()
            status = r.status
    except urllib.error.HTTPError as e:
        return None, e.code
    m = re.search(r"/web/(\d{14})", loc or final)
    if m:
        path = loc if loc.startswith("/web/") else urllib.parse.urlsplit(final).path
        return "https://web.archive.org" + path, status
    return None, status


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--go", action="store_true", help="really submit (default: dry run)")
    ap.add_argument("--max-age-days", type=int, default=365)
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()
    idx = json.load(open(INDEX, encoding="utf-8"))
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.max_age_days)
    todo = [u for u, r in sorted(idx.items()) if needs_copy(r, cutoff)]
    if args.limit:
        todo = todo[: args.limit]
    print(f"{len(idx)} sources; {len(todo)} need a new archive copy "
          f"(none newer than {args.max_age_days} days, page not dead)")
    if not args.go:
        for u in todo[:20]:
            print("  would submit:", u)
        if len(todo) > 20:
            print(f"  ... and {len(todo) - 20} more")
        print("dry run: nothing sent. Add --go to submit.")
        return
    backoff = 0
    done = 0
    for u in todo:
        while True:
            arch, status = submit(u)
            if status == 429:
                backoff += 1
                if backoff > 5:
                    save_index(idx)
                    sys.exit(f"archive.org keeps saying 429; stopped after {done}. Re-run later to resume.")
                wait = 60 * 2 ** (backoff - 1)
                print(f"  429, waiting {wait}s", flush=True)
                time.sleep(wait)
                continue
            backoff = 0
            break
        rec = idx[u]
        rec["saved_at"] = now_utc()
        rec["save_status"] = status
        if arch:
            rec["archive_url"] = arch
            rec["archive_timestamp"] = re.search(r"/web/(\d{14})", arch).group(1)
        done += 1
        if done % 10 == 0:
            save_index(idx)
            print(f"  {done}/{len(todo)}", flush=True)
        time.sleep(random.uniform(5, 10))
    save_index(idx)
    print(f"submitted {done}")


if __name__ == "__main__":
    main()
