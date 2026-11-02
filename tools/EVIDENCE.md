# Evidence format (for agents)

Evidence ties one claim to one exact quote on one source. `tools/verify.py` reads it and
computes the mark. **Never write a mark by hand**; write evidence and re-run the tests.

## Where

- `evidence/<group>.json`, one file per group: `g1` … `g10`, `people-e1` … `people-e6`,
  `series`, `terms`. The group of a claim is its `group` field in `claims/claims.json`.
- `evidence/auto-candidates.json` is written by `tools/auto_match.py`. Do not edit it; it is
  overwritten on every run. Copy a good candidate into the group file instead (see below).

## Record

A file is a JSON list of records:

```json
{
  "claim_id": "e4-19/fig/2",
  "source_url": "https://example.org/page",
  "quote": "exact words copied from the source, containing the number",
  "page": 14,
  "locator": "section 'Resultados', table 3, row Vale",
  "recorded_by": "w1234 / agent or person name",
  "recorded_at": "2026-11-01T22:00:00Z",
  "supports": true,
  "note": "optional free text"
}
```

| Field | Rule |
|---|---|
| `claim_id` | An id from `claims/claims.json`. Ids are stable; see `claims/id-map.json`. |
| `source_url` | Must be in `sources/index.json` (i.e. fetched). New URL: add it to the data, run `extract_claims.py` and `fetch_sources.py`. |
| `quote` | Copied **exactly** from the saved text (`sources/cache/<sha1(url)>.txt`). One sentence is best, under about 300 chars. |
| `page` | PDFs: 1-based page. The test finds the real page and flags `page-mismatch` if yours differs. |
| `locator` | Free text to help a human find it (heading, table, paragraph). |
| `recorded_by` | Who. Anything except `auto`. `auto` records never count as verified. |
| `recorded_at` | UTC, ISO 8601. |
| `supports` | `true` if the quote backs the claim. `false` if the source contradicts it (the claim then fails). |
| `note` | Optional. |

## What makes a record pass

1. The quote is found in the saved source text, comparing with whitespace collapsed, case
   ignored, curly quotes and dashes made plain, end-of-line hyphenation joined, and accents
   ignored. If that fails, a letters-and-digits-only compare is tried (flag `loose-match`).
2. If the live page is dead or blocked, the archive copy (`*.archive.txt`) is searched
   instead (flag `archive-only`).
3. For numeric claims (the claim has `numbers`), the quote must contain one of the claim's
   numbers. Years are ignored unless the claim has only years. Numbers compare by value:
   `3,338` / `3.338` / `3338`, `3,3 bilhões` = `US$ 3.3 billion` = `3.3bn`, Portuguese or
   English separators, within 0.5 percent or the claim's own rounding (max 2 percent).
   A percent in the claim needs a percent in the quote.

## Marks

- **verified**: at least one non-auto record with `supports: true` passes, and none with
  `supports: false` passes.
- **auto-match**: no human record; an auto candidate passes.
- **failing**: a human record exists but none passes, or a `supports: false` record passes,
  or every source of the claim is dead with no archive copy.
- **unchecked**: no evidence.

Flags: `stale` (snapshot older than 365 days: re-fetch), `disputed` (passing records carry
different numbers, or one supports and one contradicts), `blocked` (all sources bot-walled),
`no_source`, `regression` (was verified on the last run).

## How to add evidence

1. Find unchecked or failing claims: `claims/claims.csv` or the table on `verification.html`.
2. Open the saved text for the source: `sources/cache/$(python3 -c 'import hashlib,sys;print(hashlib.sha1(sys.argv[1].encode()).hexdigest())' URL).txt`.
3. Copy the sentence. For an auto-match, check the candidate in `evidence/auto-candidates.json`;
   if it is right, copy that record into the group file and change `recorded_by`.
4. Append the record to `evidence/<group>.json`.
5. Run `tools/run_all.sh --no-fetch` (or just `python3 tools/verify.py`). Commit the evidence
   file together with `claims/marks.json`, `claims/claims.csv`, `claims/last-run.json` and
   `verification.html`.

`verify.py` exits 1 when a claim that was verified on the last run is no longer verified.
Fix it (new source, new quote) before committing. The alarm repeats on every run (the claim is
stored as `regressed` in `claims/last-run.json`) until the claim is verified again. If losing the
mark is intended (the claim was removed or rightly downgraded), run
`python3 tools/verify.py --accept-regressions` once and say why in the commit message.
