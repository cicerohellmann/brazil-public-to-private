#!/usr/bin/env python3
"""Build claims/claims.json: one claim per checkable item in data/.

Ids are derived from record ids plus an index, then pinned through
claims/id-map.json so a reorder or insert never silently re-points an id:

* every claim has a fingerprint built from identity fields (not the value),
  so a corrected value keeps its id;
* a fingerprint seen before keeps its old id, wherever it now sits;
* an id whose old item is gone is retired and never handed to a different item
  (except a small in-place edit of the label, which keeps the id and is logged);
* new items get the next free index.

Changes of this run go to claims/id-changes.json.
"""
from __future__ import annotations

import difflib
import glob
import json
import os
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textnorm import parse_numbers, sha1  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "claims")

URL_RE = re.compile(r"https?://[^\s<>\"\]]+")


def urls_in(*vals) -> list:
    out = []
    for v in vals:
        if v is None:
            continue
        if isinstance(v, dict):
            v = v.get("url") or v.get("source_url")
        if isinstance(v, list):
            for u in urls_in(*v):
                if u not in out:
                    out.append(u)
            continue
        if not isinstance(v, str):
            continue
        v = v.strip()
        found = [v] if re.fullmatch(r"https?://\S+", v) else URL_RE.findall(v)
        for u in found:
            u = u.rstrip(".,;")
            # drop a closing bracket that belongs to the prose, keep wiki-style (…) ones
            while u.endswith(")") and u.count(")") > u.count("("):
                u = u[:-1]
            if u not in out:
                out.append(u)
    return out


def short(s, n=220) -> str:
    s = re.sub(r"\s+", " ", str(s or "")).strip()
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def group_of(fname: str) -> str:
    stem = os.path.basename(fname)[:-5]
    if stem.startswith("series-"):
        return "series"
    if stem == "terms":
        return "terms"
    if stem.startswith("people-"):
        return stem.split("-", 1)[1] and stem         # people-e1
    return stem.split("-", 1)[0]                     # g1 .. g10


class Item:
    __slots__ = ("base", "n", "fp", "ident", "claim")

    def __init__(self, base, n, fp, ident, claim):
        self.base, self.n, self.fp, self.ident, self.claim = base, n, fp, ident, claim


def collect():
    items: list = []
    no_id: list = []
    all_urls: dict = {}          # url -> set of places

    def note_urls(urls, where):
        for u in urls:
            all_urls.setdefault(u, set()).add(where)

    def add(base, n, kind, group, rec_id, fname, path, text, value, numbers, urls,
            legacy, ident_fields, occ, extra_flags=()):
        fp = sha1("|".join([kind, rec_id, os.path.basename(fname)] + [str(x) for x in ident_fields] + [str(occ)]))
        flags = list(extra_flags)
        if not urls:
            flags.append("no_source")
        claim = {
            "id": None,
            "kind": kind,
            "group": group,
            "record_id": rec_id,
            "claim_text": text,
            "value": value,
            "numbers": numbers,
            "source_urls": urls,
            "legacy_status": legacy,
            "file": "data/" + os.path.basename(fname),
            "json_path": path,
            "flags": flags,
        }
        items.append(Item(base, n, fp, " ".join(str(x) for x in ident_fields), claim))
        note_urls(urls, base)

    def nums(value):
        toks = parse_numbers(value or "")
        return [round(t["values"][0], 6) for t in toks]

    # ---- cases and disasters (g1..g10)
    for fname in sorted(glob.glob(os.path.join(DATA, "g*.json")), key=lambda f: int(re.match(r"g(\d+)", os.path.basename(f)).group(1))):
        group = group_of(fname)
        for i, rec in enumerate(json.load(open(fname, encoding="utf-8"))):
            rid = rec.get("id")
            if not rid:
                rid = f"{os.path.basename(fname)[:-5]}#{i}"
                no_id.append({"file": "data/" + os.path.basename(fname), "json_path": f"$[{i}]", "used_id": rid})
            title = rec.get("title") or rec.get("name") or rid
            note_urls(urls_in(rec.get("sources")), rid)
            seen = Counter()
            for j, fg in enumerate(rec.get("figures") or []):
                label = fg.get("label") or ""
                seen[label] += 1
                value = str(fg.get("value") if fg.get("value") is not None else "")
                text = short(f"{title}: {label}: {value}", 300)
                add(f"{rid}/fig", j, "fig", group, rid, fname, f"$[{i}].figures[{j}]", text, value,
                    nums(value), urls_in(fg.get("source_url")), fg.get("status"),
                    [label], seen[label])

    # ---- people
    pfiles = sorted(glob.glob(os.path.join(DATA, "people-*.json")))
    count_pid = Counter()
    for fname in pfiles:
        for p in json.load(open(fname, encoding="utf-8")).get("people", []):
            count_pid[p.get("id")] += 1
    cp_files = defaultdict(set)
    for fname in pfiles:
        for c in json.load(open(fname, encoding="utf-8")).get("foreign_counterparts", []):
            cp_files[c.get("case_id")].add(os.path.basename(fname))

    for fname in pfiles:
        group = group_of(fname)
        era = os.path.basename(fname)[len("people-"):-5]           # e1
        d = json.load(open(fname, encoding="utf-8"))
        for i, p in enumerate(d.get("people", [])):
            pid = p.get("id")
            if not pid:
                pid = f"{os.path.basename(fname)[:-5]}#{i}"
                no_id.append({"file": "data/" + os.path.basename(fname), "json_path": f"$.people[{i}]", "used_id": pid})
            key = pid if count_pid[pid] <= 1 else f"{pid}@{era}"
            name = p.get("name") or pid
            purls = urls_in(p.get("sources"), p.get("verified_sources"))
            note_urls(purls, key)
            seen = Counter()
            for j, x in enumerate(p.get("posts") or []):
                ident = [x.get("post"), x.get("start")]
                seen[tuple(map(str, ident))] += 1
                appointed = f", appointed by {x.get('appointed_by')}" if x.get("appointed_by") else ""
                text = short(f"{name} held the post {x.get('post')} from {x.get('start')} to {x.get('end')}{appointed}.", 300)
                urls = urls_in(x.get("source_url"), x.get("sources")) or purls
                add(f"{key}/post", j, "post", group, pid, fname, f"$.people[{i}].posts[{j}]", text,
                    str(x.get("post") or ""), [], urls, x.get("status"), ident, seen[tuple(map(str, ident))],
                    [] if (x.get("source_url") or x.get("sources")) else ["person_sources"])
            seen = Counter()
            for j, x in enumerate(p.get("foreign_ties") or []):
                ident = [x.get("counterpart"), x.get("kind")]
                seen[tuple(map(str, ident))] += 1
                text = short(f"{name}: {x.get('kind')} tie with {x.get('counterpart')}. {x.get('detail') or ''}", 300)
                add(f"{key}/tie", j, "tie", group, pid, fname, f"$.people[{i}].foreign_ties[{j}]", text,
                    str(x.get("detail") or x.get("counterpart") or ""), [],
                    urls_in(x.get("source_url"), x.get("sources")), x.get("status"), ident, seen[tuple(map(str, ident))])
            seen = Counter()
            for j, x in enumerate(p.get("case_links") or []):
                ident = [x.get("case_id"), x.get("role")]
                seen[tuple(map(str, ident))] += 1
                text = short(f"{name} {x.get('role')} (case {x.get('case_id')}).", 300)
                add(f"{key}/link", j, "link", group, pid, fname, f"$.people[{i}].case_links[{j}]", text,
                    str(x.get("role") or ""), [], urls_in(x.get("source_url"), x.get("sources")),
                    x.get("status"), ident, seen[tuple(map(str, ident))])
            seen = Counter()
            for j, x in enumerate(p.get("controversies") or []):
                ident = [x.get("what")]
                seen[tuple(map(str, ident))] += 1
                text = short(f"{name}: {x.get('what')} Outcome: {x.get('outcome')}", 300)
                add(f"{key}/controversy", j, "controversy", group, pid, fname,
                    f"$.people[{i}].controversies[{j}]", text, str(x.get("outcome") or ""), [],
                    urls_in(x.get("source_url"), x.get("sources")), x.get("status"), ident,
                    seen[tuple(map(str, ident))])
        # foreign counterparts, keyed by case id
        per_case = Counter()
        seen = Counter()
        for i, c in enumerate(d.get("foreign_counterparts", [])):
            cid = c.get("case_id") or f"{os.path.basename(fname)[:-5]}#cp{i}"
            ckey = cid if len(cp_files[cid]) <= 1 else f"{cid}@{era}"
            n = per_case[ckey]
            per_case[ckey] += 1
            ident = [c.get("counterpart"), c.get("kind")]
            seen[(ckey,) + tuple(map(str, ident))] += 1
            text = short(f"Case {cid}: foreign counterpart {c.get('counterpart')} ({c.get('country')}, {c.get('kind')}). {c.get('detail') or ''}", 300)
            add(f"{ckey}/counterpart", n, "counterpart", group, cid, fname, f"$.foreign_counterparts[{i}]",
                text, str(c.get("detail") or c.get("counterpart") or ""), [],
                urls_in(c.get("source_url"), c.get("sources")), c.get("status"), ident,
                seen[(ckey,) + tuple(map(str, ident))])
        for t in d.get("terms", []):
            pass  # era term lists name decision makers only; no source to check

    # ---- series
    for fname in sorted(glob.glob(os.path.join(DATA, "series-*.json"))):
        for i, s in enumerate(json.load(open(fname, encoding="utf-8")).get("series", [])):
            sid = s.get("id")
            if not sid:
                sid = f"{os.path.basename(fname)[:-5]}#{i}"
                no_id.append({"file": "data/" + os.path.basename(fname), "json_path": f"$.series[{i}]", "used_id": sid})
            pts = s.get("points") or []
            span = f"{pts[0][0]} to {pts[-1][0]}" if pts and isinstance(pts[0], list) else ""
            text = short(f"Series: {s.get('label')} ({s.get('unit')}), {len(pts)} points {span}.", 300)
            add("series", None, "series", "series", sid, fname, f"$.series[{i}]", text,
                f"{len(pts)} points", [], urls_in(s.get("source_url"), s.get("sources")),
                s.get("status"), [sid], 1)
            items[-1].base = f"series/{sid}"

    # ---- terms of office
    fname = os.path.join(DATA, "terms.json")
    if os.path.exists(fname):
        for i, t in enumerate(json.load(open(fname, encoding="utf-8")).get("terms", [])):
            tid = t.get("id")
            if not tid:
                tid = f"terms#{i}"
                no_id.append({"file": "data/terms.json", "json_path": f"$.terms[{i}]", "used_id": tid})
            text = short(f"{t.get('ruler')} was {t.get('title')} from {t.get('start')} to {t.get('end')}"
                         f" ({t.get('how_came_to_power') or ''}).", 300)
            add("term", None, "term", "terms", tid, fname, f"$.terms[{i}]", text,
                f"{t.get('start')} to {t.get('end')}", [], urls_in(t.get("sources"), t.get("source_url")),
                None, [tid], 1)
            items[-1].base = f"term/{tid}"
    return items, no_id, all_urls


def assign_ids(items: list, old_map: dict):
    """Give every item a stable id. Returns (new_map, changes)."""
    fp_to_old = {v["fp"]: k for k, v in old_map.items()}
    current_fps = {it.fp for it in items}
    used = set()
    changes = []
    assigned = {}

    def derived(it):
        return it.base if it.n is None else f"{it.base}/{it.n}"

    # 1. fingerprints seen before keep their id
    for it in items:
        oid = fp_to_old.get(it.fp)
        if oid and oid not in used:
            assigned[id(it)] = oid
            used.add(oid)
            if oid != derived(it):
                changes.append({"id": oid, "change": "kept-after-move", "now_at": it.claim["json_path"],
                                "file": it.claim["file"]})

    # highest index ever used per base, so new items never take a retired id
    max_n = defaultdict(lambda: -1)
    for k in list(old_map.keys()):
        m = re.match(r"(.*)/(\d+)$", k)
        if m:
            max_n[m.group(1)] = max(max_n[m.group(1)], int(m.group(2)))
    for it in items:
        if it.n is not None:
            max_n[it.base] = max(max_n[it.base], it.n)

    # 2. everyone else
    for it in items:
        if id(it) in assigned:
            continue
        d = derived(it)
        old = old_map.get(d)
        if d not in used and old is None:
            nid = d
            if old_map:
                changes.append({"id": nid, "change": "new"})
        elif d not in used and old["fp"] not in current_fps and \
                difflib.SequenceMatcher(None, old.get("ident", ""), it.ident).ratio() >= 0.6:
            nid = d
            changes.append({"id": nid, "change": "edited-in-place", "was": old.get("ident"), "now": it.ident})
        else:
            if it.n is None:
                k = 2
                while f"{it.base}~{k}" in used or f"{it.base}~{k}" in old_map:
                    k += 1
                nid = f"{it.base}~{k}"
            else:
                max_n[it.base] += 1
                nid = f"{it.base}/{max_n[it.base]}"
            changes.append({"id": nid, "change": "new-index", "derived_was_taken": d})
        assigned[id(it)] = nid
        used.add(nid)

    new_map = {}
    for it in items:
        cid = assigned[id(it)]
        it.claim["id"] = cid
        new_map[cid] = {"fp": it.fp, "ident": it.ident[:200], "status": "active",
                        "file": it.claim["file"], "json_path": it.claim["json_path"]}
    for k, v in old_map.items():
        if k not in new_map:
            v = dict(v)
            if v.get("status") != "retired":
                changes.append({"id": k, "change": "retired"})
            v["status"] = "retired"
            new_map[k] = v
    return new_map, changes


def main():
    os.makedirs(OUT, exist_ok=True)
    items, no_id, all_urls = collect()
    map_path = os.path.join(OUT, "id-map.json")
    old_map = json.load(open(map_path, encoding="utf-8")) if os.path.exists(map_path) else {}
    new_map, changes = assign_ids(items, old_map)
    claims = [it.claim for it in items]
    ids = [c["id"] for c in claims]
    dup = [k for k, v in Counter(ids).items() if v > 1]
    if dup:
        sys.exit(f"duplicate claim ids: {dup[:10]}")

    # non-URL source fields, for the notes
    bad_src = []
    for c in claims:
        if "no_source" in c["flags"]:
            bad_src.append(c["id"])

    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    kinds = Counter(c["kind"] for c in claims)
    doc = {
        "generated_at": now,
        "counts": dict(kinds),
        "n_claims": len(claims),
        "records_without_id": no_id,
        "claims_without_source_url": bad_src,
        "claims": claims,
    }
    json.dump(doc, open(os.path.join(OUT, "claims.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(dict(sorted(new_map.items())), open(map_path, "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    json.dump({"generated_at": now, "changes": changes},
              open(os.path.join(OUT, "id-changes.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    urls = sorted(all_urls)
    json.dump({"generated_at": now, "n": len(urls), "urls": urls},
              open(os.path.join(OUT, "source_urls.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=0)
    print(f"claims: {len(claims)}  " + "  ".join(f"{k}={v}" for k, v in sorted(kinds.items())))
    print(f"unique urls: {len(urls)}  records without id: {len(no_id)}  claims without source url: {len(bad_src)}")
    print(f"id changes this run: {len(changes)}")


if __name__ == "__main__":
    main()
