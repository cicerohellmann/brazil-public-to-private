#!/usr/bin/env python3
"""The test runner: compute a mark for every claim.

Marks (computed here, never typed by hand):
  verified    a researcher's evidence record (supports=true) passes: its quote is on
              the saved source and, for numeric claims, the claim's number is in the quote
  auto-match  only an auto candidate (recorded_by "auto") passes
  failing     a researcher's evidence exists but does not pass, or a source
              contradicts the claim, or every source is dead with no archive copy
  unchecked   no evidence

Flags: stale (snapshot older than 365 days), disputed (passing records carry
different numbers, or a source contradicts), blocked (bot wall), no_source,
archive-only, loose-match, page-mismatch, regression.

Outputs: claims/marks.json, claims/claims.csv, claims/last-run.json, verification.html.
Exit code 1 if a claim that was verified on the last run is no longer verified.
"""
from __future__ import annotations

import csv
import glob
import html
import json
import os
import re
import sys
from collections import Counter, OrderedDict, defaultdict
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textnorm import claim_tokens, find_quote, number_in  # noqa: E402
from sourcetext import load_index, usable_texts  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.join(ROOT, "tools")
MARKS = ("verified", "auto-match", "failing", "unchecked")
PILL = {"verified": "pass", "auto-match": "auto", "failing": "fail", "unchecked": "none"}
STALE_DAYS = 365


def parse_ts(s):
    try:
        return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def load_evidence():
    recs = []
    for p in sorted(glob.glob(os.path.join(ROOT, "evidence", "*.json"))):
        name = os.path.relpath(p, ROOT)
        try:
            data = json.load(open(p, encoding="utf-8"))
        except Exception as e:  # noqa: BLE001
            sys.exit(f"bad evidence file {name}: {e}")
        if isinstance(data, dict):
            data = data.get("evidence", [])
        auto_file = os.path.basename(p) == "auto-candidates.json"
        for i, r in enumerate(data):
            r = dict(r)
            r["_ref"] = f"{name}#{i}"
            r["_auto"] = auto_file or (r.get("recorded_by") or "").strip().lower() == "auto"
            recs.append(r)
    return recs


def check_record(rec, claim, idx):
    """Return dict(pass, reason, page, how, which, src_value)."""
    url = (rec.get("source_url") or "").strip()
    quote = rec.get("quote") or ""
    res = {"pass": False, "reason": None, "page": None, "how": None, "which": None, "src_value": None}
    if not url or not quote.strip():
        res["reason"] = "evidence has no source_url or no quote"
        return res
    if url not in idx:
        res["reason"] = "source not fetched yet (run fetch_sources.py)"
        return res
    texts = usable_texts(url, idx)
    if not texts:
        st = idx[url].get("state")
        res["reason"] = f"source {st or 'not fetched'}, no usable snapshot or archive copy"
        return res
    for which, text in texts:
        found, how, page = find_quote(text, quote)
        if found:
            res.update(how=how, page=page, which=which)
            break
    else:
        res["reason"] = "quote not found on the saved source"
        return res
    ctoks = claim_tokens(claim.get("value")) if claim.get("numbers") else []
    if ctoks:
        hit = number_in(ctoks, quote)
        if not hit:
            res["reason"] = "the claim's number is not in the quote"
            return res
        res["src_value"] = hit["values"][0]
    res["pass"] = True
    return res


def slug(cid):
    return "c-" + re.sub(r"[^a-z0-9]+", "-", cid.lower()).strip("-")


ACCEPT = "--accept-regressions" in sys.argv


def main():
    claims_doc = json.load(open(os.path.join(ROOT, "claims", "claims.json"), encoding="utf-8"))
    claims = claims_doc["claims"]
    idx = load_index()
    evidence = load_evidence()
    by_claim = defaultdict(list)
    known = {c["id"] for c in claims}
    orphans = []
    for r in evidence:
        if r.get("claim_id") in known:
            by_claim[r["claim_id"]].append(r)
        else:
            orphans.append(r["_ref"])
    now = datetime.now(timezone.utc)
    now_s = now.strftime("%Y-%m-%dT%H:%M:%SZ")

    last_path = os.path.join(ROOT, "claims", "last-run.json")
    last = json.load(open(last_path, encoding="utf-8")) if os.path.exists(last_path) else {}
    last_marks = last.get("marks", {})

    marks = OrderedDict()
    rows = []
    for c in claims:
        cid = c["id"]
        flags = [f for f in c.get("flags", []) if f == "no_source"]
        recs = by_claim.get(cid, [])
        human = [r for r in recs if not r["_auto"]]
        auto = [r for r in recs if r["_auto"]]
        checked = [(r, check_record(r, c, idx)) for r in recs]
        res_of = {r["_ref"]: x for r, x in checked}
        h_pass = [r for r in human if r.get("supports", True) is not False and res_of[r["_ref"]]["pass"]]
        h_contra = [r for r in human if r.get("supports", True) is False and res_of[r["_ref"]]["pass"]]
        a_pass = [r for r in auto if res_of[r["_ref"]]["pass"]]
        reason = None
        deciding = None
        if h_pass and not h_contra:
            mark, deciding = "verified", h_pass[0]
        elif human:
            mark = "failing"
            if h_contra:
                deciding = h_contra[0]
                reason = "a recorded source contradicts the claim"
            else:
                deciding = human[0]
                reason = res_of[deciding["_ref"]]["reason"]
        elif a_pass:
            mark, deciding = "auto-match", a_pass[0]
        else:
            mark = "unchecked"
            if auto:
                flags.append("auto-candidate-fails")

        # dead sources
        srcs = c.get("source_urls") or []
        states = [(idx.get(u) or {}) for u in srcs]
        if srcs and all(s.get("state") in ("dead",) and not s.get("archive_url") for s in states) \
                and mark != "verified":
            mark = "failing"
            reason = reason or "every source is dead and has no archive copy"
        if srcs and all(s.get("state") == "blocked" for s in states):
            flags.append("blocked")
        if h_pass and h_contra:
            flags.append("disputed")
        vals = [res_of[r["_ref"]]["src_value"] for r in h_pass if res_of[r["_ref"]]["src_value"] is not None]
        if len(vals) >= 2 and (max(vals) - min(vals)) > 0.005 * max(abs(v) for v in vals):
            flags.append("disputed")
        if deciding is not None:
            x = res_of[deciding["_ref"]]
            if x.get("which") == "archive":
                flags.append("archive-only")
            if x.get("how") == "loose":
                flags.append("loose-match")
            if deciding.get("page") and x.get("page") and str(deciding.get("page")) != str(x.get("page")):
                flags.append("page-mismatch")
        ev_url = deciding.get("source_url") if deciding else (srcs[0] if srcs else "")
        src_rec = idx.get(ev_url) or {}
        fa = parse_ts(src_rec.get("fetched_at") or "")
        if fa and now - fa > timedelta(days=STALE_DAYS):
            flags.append("stale")
        if last_marks.get(cid) in ("verified", "regressed") and mark != "verified" and not ACCEPT:
            flags.append("regression")
        flags = sorted(set(flags))
        marks[cid] = {"mark": mark, "flags": flags, "evidence_ref": deciding["_ref"] if deciding else None}
        if reason:
            marks[cid]["reason"] = reason
        rows.append({
            "c": c, "mark": mark, "flags": flags, "reason": reason,
            "quote": (deciding or {}).get("quote") or "",
            "page": (res_of[deciding["_ref"]]["page"] if deciding else None) or (deciding or {}).get("page"),
            "by": (deciding or {}).get("recorded_by") or "",
            "url": ev_url or "",
            "archive": src_rec.get("archive_url") or "",
            "fetched": src_rec.get("fetched_at") or "",
            "hash": src_rec.get("text_sha256") or "",
            "state": src_rec.get("state") or ("" if not ev_url else "not fetched"),
        })

    regressions = [cid for cid, m in marks.items() if "regression" in m["flags"]]

    # ---- outputs
    cdir = os.path.join(ROOT, "claims")
    json.dump({"generated_at": now_s, "marks": marks}, open(os.path.join(cdir, "marks.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=0)
    with open(os.path.join(cdir, "claims.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["claim_id", "group", "kind", "claim", "value", "mark", "flags", "reason", "quote", "page",
                    "recorded_by", "source_url", "source_state", "archive_url", "fetched_at", "text_sha256",
                    "legacy_status", "data_file", "json_path"])
        for r in rows:
            c = r["c"]
            w.writerow([c["id"], c["group"], c["kind"], c["claim_text"], c["value"], r["mark"], " ".join(r["flags"]),
                        r["reason"] or "", r["quote"], r["page"] or "", r["by"], r["url"], r["state"], r["archive"],
                        r["fetched"], r["hash"], c.get("legacy_status") or "", c["file"], c["json_path"]])
    # a regressed claim stays "regressed" in last-run.json, so the alarm repeats on
    # every run until the claim is verified again or --accept-regressions is given
    json.dump({"run_at": now_s, "marks": {k: ("regressed" if "regression" in v["flags"] else v["mark"])
                                          for k, v in marks.items()}},
              open(last_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)

    write_html(rows, marks, idx, evidence, orphans, regressions, now_s, claims_doc)

    tot = Counter(m["mark"] for m in marks.values())
    print("marks: " + "  ".join(f"{k}={tot.get(k, 0)}" for k in MARKS))
    fl = Counter(f for m in marks.values() for f in m["flags"])
    print("flags: " + "  ".join(f"{k}={v}" for k, v in sorted(fl.items())))
    if orphans:
        print(f"evidence records with unknown claim_id: {len(orphans)} (first: {orphans[0]})")
    if regressions:
        print(f"REGRESSION: {len(regressions)} claims were verified and no longer are: {regressions[:10]}")
        sys.exit(1)


# ------------------------------------------------------------------ html

GROUP_LABEL = {
    "g1": "Cases 1500-1889", "g2": "Cases 1889-1964", "g3": "Cases 1964-1985", "g4": "Cases 1985-2002",
    "g5": "Cases 2003-2016", "g6": "Cases 2016-2026", "g7": "Cross-cutting cases", "g8": "Disasters: mining",
    "g9": "Disasters: oil", "g10": "Disasters: dams and land", "people-e1": "People 1500-1889",
    "people-e2": "People 1889-1964", "people-e3": "People 1964-1985", "people-e4": "People 1985-2002",
    "people-e5": "People 2003-2016", "people-e6": "People 2016-2026", "series": "Data series",
    "terms": "Terms of office",
}

EXTRA_CSS = """
.bar{display:flex;height:16px;border-radius:6px;overflow:hidden;background:var(--line);min-width:120px}
.bar span{display:block;height:100%}
.b-pass{background:var(--ok)}.b-auto{background:var(--ask)}.b-fail{background:var(--bad)}.b-none{background:var(--wait);opacity:.45}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.totals{display:flex;flex-wrap:wrap;gap:10px;margin:8px 0 14px}
.totals div{border:1px solid var(--line);border-radius:10px;padding:8px 14px;min-width:110px}
.totals b{display:block;font-size:24px}
.small{font-size:14px;color:var(--muted)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin:8px 0 12px}
.filters select,.filters input{font:inherit;font-size:15px;padding:4px 8px;border-radius:8px;border:1px solid var(--line);background:var(--bg);color:var(--fg)}
#claims-table td{font-size:14px}
#claims-table td.q{max-width:340px}
#claims-table .cid{font-family:ui-monospace,Menlo,monospace;font-size:12px;color:var(--muted);word-break:break-all}
.flag{display:inline-block;font-size:11px;padding:0 6px;border-radius:6px;border:1px solid var(--line);margin:2px 2px 0 0;color:var(--muted)}
a{color:var(--ask)}
blockquote{margin:0;padding-left:8px;border-left:3px solid var(--line)}
@media (max-width:700px){
 #claims-table thead{display:none}
 #claims-table tr{display:block;border-top:1px solid var(--line);padding:6px 0}
 #claims-table td{display:block;border:0;padding:2px 0;max-width:none}
 #claims-table td.q{max-width:none}
}
"""

JS = """
(function(){
 var g=document.getElementById('f-group'),m=document.getElementById('f-mark'),q=document.getElementById('f-text'),
     n=document.getElementById('f-count'),rows=document.querySelectorAll('#claims-table tbody tr');
 function run(){var gv=g.value,mv=m.value,tv=q.value.toLowerCase(),k=0;
  for(var i=0;i<rows.length;i++){var r=rows[i];
   var ok=(!gv||r.dataset.group===gv)&&(!mv||r.dataset.mark===mv)&&(!tv||r.textContent.toLowerCase().indexOf(tv)>=0);
   r.hidden=!ok;if(ok)k++;}
  n.textContent=k+' shown';}
 var t;g.onchange=run;m.onchange=run;q.oninput=function(){clearTimeout(t);t=setTimeout(run,200);};
 function reveal(){var h=location.hash.slice(1);if(!h)return;var el=document.getElementById(h);
  if(el&&el.tagName==='TR'&&el.hidden){g.value='';m.value='';q.value='';run();el.scrollIntoView();}}
 window.addEventListener('hashchange',reveal);run();reveal();
})();
"""


def e(s):
    return html.escape(str(s if s is not None else ""), quote=True)


def write_html(rows, marks, idx, evidence, orphans, regressions, now_s, claims_doc):
    css = open(os.path.join(TOOLS, "verification_style.css"), encoding="utf-8").read()
    intro = open(os.path.join(TOOLS, "verification_intro.html"), encoding="utf-8").read()
    tot = Counter(r["mark"] for r in rows)
    n = len(rows)
    groups = []
    for r in rows:
        if r["c"]["group"] not in groups:
            groups.append(r["c"]["group"])
    per_group = {g: Counter() for g in groups}
    for r in rows:
        per_group[r["c"]["group"]][r["mark"]] += 1
    flags = Counter(f for r in rows for f in r["flags"])
    urls = set()
    for r in rows:
        urls.update(r["c"].get("source_urls") or [])
    st = Counter((idx.get(u) or {}).get("state", "not fetched") for u in urls)
    pdfs = sum(1 for u in urls if (idx.get(u) or {}).get("kind") == "pdf")
    archived = sum(1 for u in urls if (idx.get(u) or {}).get("archive_url"))
    human_ev = sum(1 for x in evidence if not x["_auto"])
    auto_ev = sum(1 for x in evidence if x["_auto"])
    date = now_s[:10]

    out = []
    a = out.append
    a('<!doctype html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
      '<meta name="viewport" content="width=device-width, initial-scale=1">\n<title>Source checks</title>\n<style>\n')
    a(css + EXTRA_CSS)
    a('</style>\n</head>\n<body>\n<main>\n<h1>Source checks</h1>\n'
      '<p class="sub">How every number in the study is tied to a source anyone can check. Newest on top.</p>\n')
    a('<nav><strong>Contents</strong>\n<ol>\n'
      '<li><a href="#test-run">What did the latest test run find?</a>'
      '<ul><li><a href="#by-group">Marks by group</a></li><li><a href="#sources-state">The source pages</a></li></ul></li>\n'
      '<li><a href="#plan">How do we make every source traceable, like unit tests?</a>\n'
      '<ul><li><a href="#problem">The problem today</a></li><li><a href="#how-it-works">How the system works</a></li>'
      '<li><a href="#statuses">The four marks</a></li><li><a href="#steps">Steps</a></li>'
      '<li><a href="#decision-archive">Decision: public archive copies</a></li></ul></li>\n'
      '<li><a href="#failing">Which claims are failing?</a></li>\n'
      '<li><a href="#download">Download the claim list</a></li>\n'
      '<li><a href="#claims">Every claim</a></li>\n</ol>\n</nav>\n')

    # ---- test run
    a('<section id="test-run">\n<h2 id="test-run-h">What did the latest test run find?</h2>\n')
    a(f'<p class="lead"><strong>{tot.get("verified", 0)} of {n} claims are verified.</strong> '
      f'The script found the number on the source page for {tot.get("auto-match", 0)} more, '
      f'but no one has confirmed those yet. Run on {e(date)}.</p>\n')
    a('<div class="totals">')
    for m in MARKS:
        a(f'<div><b>{tot.get(m, 0)}</b><span class="pill {PILL[m]}">{m}</span></div>')
    a('</div>\n')
    if tot.get("verified", 0) == 0:
        a('<div class="callout action"><strong>Why zero verified:</strong> "verified" now needs an exact quote '
          'written down by a researcher. None are written yet. The old "verified" labels in the data are kept '
          'only as history and do not count.</div>\n')
    if regressions:
        a(f'<div class="callout action"><strong>Alarm:</strong> {len(regressions)} claims were verified on the '
          'last run and are not any more. They are in the failing list.</div>\n')
    a(f'<p class="small">Evidence on file: {human_ev} researcher quotes, {auto_ev} automatic candidates. '
      + (f'{len(orphans)} evidence records point to unknown claims. ' if orphans else '')
      + 'Flags: ' + (", ".join(f"{k} {v}" for k, v in sorted(flags.items())) or "none") + '.</p>\n')

    a('<h3 id="by-group">Marks by group</h3>\n<div class="scroll"><table>\n'
      '<tr><th>Group</th><th class="num">Claims</th><th>Marks</th><th class="num">Verified</th>'
      '<th class="num">Auto</th><th class="num">Failing</th><th class="num">Unchecked</th></tr>\n')
    for g in groups:
        c = per_group[g]
        k = sum(c.values()) or 1
        bar = "".join(
            f'<span class="b-{PILL[m]}" style="width:{100.0 * c.get(m, 0) / k:.2f}%" title="{m}: {c.get(m, 0)}"></span>'
            for m in MARKS if c.get(m, 0))
        a(f'<tr><td>{e(GROUP_LABEL.get(g, g))} <span class="small">{e(g)}</span></td><td class="num">{sum(c.values())}</td>'
          f'<td><div class="bar">{bar}</div></td>'
          + "".join(f'<td class="num">{c.get(m, 0)}</td>' for m in MARKS) + '</tr>\n')
    a('</table></div>\n')
    a('<h3 id="sources-state">The source pages</h3>\n')
    a(f'<p>{len(urls)} different source pages are linked from the claims. '
      f'<strong>{st.get("ok", 0)}</strong> opened fine ({pdfs} of them PDFs or files), '
      f'<strong>{st.get("dead", 0)}</strong> are dead or empty, <strong>{st.get("blocked", 0)}</strong> block robots, '
      f'{st.get("error", 0)} timed out or failed, {st.get("not fetched", 0)} are not fetched yet. '
      f'{archived} have an older copy in the Internet Archive.</p>\n')
    a('<p class="small">A page that blocks robots is not counted as dead: it is probably still there for a person. '
      'Those claims get the flag "blocked".</p>\n</section>\n')

    # ---- intro prose (kept from the hand-written page)
    a(intro)

    # ---- failing
    fails = [r for r in rows if r["mark"] == "failing"]
    a('<section id="failing">\n<h2 id="failing-h">Which claims are failing?</h2>\n')
    a(f'<p class="lead"><strong>{len(fails)} claims are failing.</strong> Each needs a researcher to find a working '
      'source and record a new quote.</p>\n')
    if fails:
        a('<div class="scroll"><table>\n<tr><th>Claim</th><th>Why</th><th>Source</th></tr>\n')
        for r in fails[:1500]:
            c = r["c"]
            a(f'<tr><td><a href="#{slug(c["id"])}">{e(c["claim_text"][:140])}</a><br><span class="small">{e(c["id"])}</span></td>'
              f'<td>{e(r["reason"] or "")}</td>'
              f'<td>{link(r["url"], "page")}{(" · " + link(r["archive"], "archive")) if r["archive"] else ""}</td></tr>\n')
        a('</table></div>\n')
        if len(fails) > 1500:
            a(f'<p class="small">Showing the first 1500. The full list is in the claims table and the CSV file.</p>\n')
    a('</section>\n')

    # ---- download
    ev_files = sorted(os.path.relpath(p, ROOT) for p in glob.glob(os.path.join(ROOT, "evidence", "*.json")))
    a('<section id="download">\n<h2 id="download-h">Download the claim list</h2>\n')
    a('<p class="lead"><strong>Everything on this page is in plain files</strong> you can open in a spreadsheet.</p>\n<ul>\n')
    a('<li><a href="claims/claims.csv">claims/claims.csv</a>: every claim with its mark, quote, source, archive copy and date checked.</li>\n')
    a('<li><a href="claims/claims.json">claims/claims.json</a>: the claim list with the data file and place of each claim.</li>\n')
    a('<li><a href="claims/marks.json">claims/marks.json</a>: the mark of every claim, as the script computed it.</li>\n')
    a('<li><a href="sources/index.json">sources/index.json</a>: every source page, when it was read, and its fingerprint (hash).</li>\n')
    for p in ev_files:
        a(f'<li><a href="{e(p)}">{e(p)}</a>: evidence records.</li>\n')
    a('</ul>\n</section>\n')

    # ---- claims table
    a('<section id="claims">\n<h2 id="claims-h">Every claim</h2>\n')
    a(f'<p class="lead"><strong>{n} claims.</strong> Pick a group or a mark to filter. Each row has its own link.</p>\n')
    a('<div class="filters"><label>Group <select id="f-group"><option value="">all</option>')
    for g in groups:
        a(f'<option value="{e(g)}">{e(GROUP_LABEL.get(g, g))}</option>')
    a('</select></label> <label>Mark <select id="f-mark"><option value="">all</option>')
    for m in MARKS:
        a(f'<option value="{m}">{m}</option>')
    a('</select></label> <label>Search <input id="f-text" type="search" size="14"></label> '
      '<span id="f-count" class="small"></span></div>\n')
    a('<div class="scroll"><table id="claims-table">\n<thead><tr><th>Claim</th><th>Mark</th><th>Source</th>'
      '<th>Quote</th><th>Checked</th></tr></thead>\n<tbody>\n')
    seen = set()
    for r in rows:
        c = r["c"]
        sid = slug(c["id"])
        while sid in seen:
            sid += "-x"
        seen.add(sid)
        fl = "".join(f'<span class="flag">{e(f)}</span>' for f in r["flags"])
        src = link(r["url"], "page") if r["url"] else '<span class="small">no source link</span>'
        if r["archive"]:
            src += " · " + link(r["archive"], "archive")
        if r["state"] and r["state"] != "ok":
            src += f'<br><span class="small">{e(r["state"])}</span>'
        q = ""
        if r["quote"]:
            q = f'<blockquote>{e(r["quote"])}</blockquote>'
            if r["page"]:
                q += f'<span class="small">page {e(r["page"])}</span> '
            q += f'<span class="small">by {e(r["by"])}</span>'
        elif r["reason"]:
            q = f'<span class="small">{e(r["reason"])}</span>'
        chk = e(r["fetched"][:10]) if r["fetched"] else ""
        if r["hash"]:
            chk += f'<br><span class="small" title="sha256 of the saved text">#{e(r["hash"][:10])}</span>'
        a(f'<tr id="{sid}" data-group="{e(c["group"])}" data-mark="{r["mark"]}">'
          f'<td>{e(c["claim_text"])}<div class="cid">{e(c["id"])}</div></td>'
          f'<td><span class="pill {PILL[r["mark"]]}">{r["mark"]}</span>{fl}</td>'
          f'<td>{src}</td><td class="q">{q}</td><td>{chk}</td></tr>\n')
    a('</tbody></table></div>\n</section>\n')
    a('</main>\n<script>' + JS + '</script>\n</body>\n</html>\n')
    tmp = os.path.join(ROOT, "verification.html.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("".join(out))
    os.replace(tmp, os.path.join(ROOT, "verification.html"))


def link(url, label):
    if not url:
        return ""
    return f'<a href="{e(url)}" rel="noopener noreferrer">{e(label)}</a>'


if __name__ == "__main__":
    main()
