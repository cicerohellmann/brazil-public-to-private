#!/usr/bin/env python3
"""Find candidate quotes for numeric claims in the cached source text.

For each claim with numbers and a fetched source, look for the number in
the source (3,338 / 3.338 / 3338 / "3,3 bilhões" / "US$ 3.3 billion" all
compare by value) and for the claim's key words near it. The best hit per
claim is written to evidence/auto-candidates.json with recorded_by "auto".

These records can only ever give the mark "auto-match", never "verified".
"""
from __future__ import annotations

import bisect
import json
import os
import sys
from collections import Counter
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from textnorm import (claim_tokens, fold, number_in, is_weak, keywords, page_of, parse_numbers, primary_value,  # noqa: E402
                      sentence_around, stem, values_match)
from sourcetext import load_index, usable_texts  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WINDOW = 250


def main():
    claims = json.load(open(os.path.join(ROOT, "claims", "claims.json"), encoding="utf-8"))["claims"]
    idx = load_index()
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    tok_cache: dict = {}
    out = []
    stats = Counter()

    for c in claims:
        if not c.get("numbers") or not c.get("source_urls"):
            continue
        stats["numeric"] += 1
        ctoks = claim_tokens(c["value"])
        if not ctoks:
            continue
        prim = primary_value(ctoks)
        # key words: from the figure label and value; the case title counts as a weaker hint
        head, _, _ = c["claim_text"].partition(": ")
        label_kw = [stem(w) for w in keywords(c["claim_text"][len(head) + 2:])]
        title_kw = [stem(w) for w in keywords(head)]
        best = None
        any_text = False
        for url in c["source_urls"]:
            for which, text in usable_texts(url, idx):
                any_text = True
                key = (url, which)
                if key not in tok_cache:
                    tok_cache[key] = (parse_numbers(text), fold(text))
                stoks, ftext = tok_cache[key]
                starts = [t["start"] for t in stoks]
                for ct in ctoks:
                    weak_c = is_weak(ct)
                    for st in stoks:
                        strict = values_match(ct, st, strict_scale=True)
                        if not strict and not values_match(ct, st, strict_scale=False):
                            continue
                        lo, hi = max(0, st["start"] - WINDOW), min(len(text), st["end"] + WINDOW)
                        win = ftext[lo:hi]
                        kw = [w for w in label_kw if w in win]
                        tkw = [w for w in title_kw if w in win and w not in kw]
                        weak = weak_c or not strict or is_weak(st)
                        need = 2 if weak else 1
                        if not label_kw:
                            need = 1 if weak else 0
                        hits = len(kw) + 0.5 * len(tkw)
                        if hits < need:
                            continue
                        near = stoks[bisect.bisect_left(starts, lo):bisect.bisect_right(starts, hi)]
                        others = sum(1 for o in ctoks if o is not ct and any(values_match(o, s2) for s2 in near))
                        score = (3 if not weak else 1) + hits + others + (1 if ct is prim else 0) + \
                            (0.5 if which == "live" else 0)
                        if best is not None and score <= best["score"]:
                            continue
                        quote = sentence_around(text, st["start"], st["end"], 300)
                        if not number_in([ct], quote):
                            continue                     # the quote must hold the number
                        if weak:
                            # weak numbers need two label key words inside the quote itself
                            fq = fold(quote)
                            if sum(1 for w in label_kw if w in fq) < 2:
                                continue
                        if True:
                            best = {
                                "score": score, "url": url, "which": which, "quote": quote,
                                "page": page_of(text, st["start"]) if "\f" in text else None,
                                "pos": st["start"], "raw": st["raw"], "claim_raw": ct["raw"],
                                "kw": kw + tkw,
                            }
        if any_text:
            stats["with_text"] += 1
        if best:
            stats["matched"] += 1
            out.append({
                "claim_id": c["id"],
                "source_url": best["url"],
                "quote": best["quote"],
                "page": best["page"],
                "locator": f"char {best['pos']} of the {best['which']} snapshot; source number '{best['raw']}'",
                "recorded_by": "auto",
                "recorded_at": now,
                "supports": True,
                "note": f"auto: claim number '{best['claim_raw']}' matched; key words near it: "
                        f"{', '.join(best['kw']) or 'none'}; score {best['score']:.1f}",
            })

    os.makedirs(os.path.join(ROOT, "evidence"), exist_ok=True)
    with open(os.path.join(ROOT, "evidence", "auto-candidates.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"numeric claims: {stats['numeric']}  with source text: {stats['with_text']}  "
          f"auto candidates: {stats['matched']}")


if __name__ == "__main__":
    main()
