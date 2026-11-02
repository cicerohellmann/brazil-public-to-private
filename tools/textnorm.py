"""Shared text and number normalization for the source checks.

Used by extract_claims.py, auto_match.py and verify.py so all three read
numbers and quotes the same way.
"""
from __future__ import annotations

import hashlib
import re
import unicodedata

# ---------------------------------------------------------------- text

_QUOTES = {
    "‘": "'", "’": "'", "‚": "'", "‛": "'", "′": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"', "″": '"',
    "«": '"', "»": '"', "`": "'", "´": "'",
}
_DASHES = "‐‑‒–—―−﹘﹣－"


def fold(s: str) -> str:
    """Lower case, accents removed (accent-insensitive compare)."""
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower()


def norm_text(s: str) -> str:
    """Normalize for quote matching: whitespace, case, quotes, hyphenation, accents."""
    if not s:
        return ""
    s = s.replace("­", "")              # soft hyphen
    s = s.replace("\f", " ")
    s = re.sub(r"(\w)-[ \t]*\r?\n[ \t]*(\w)", r"\1\2", s)   # end-of-line hyphenation
    for k, v in _QUOTES.items():
        s = s.replace(k, v)
    for d in _DASHES:
        s = s.replace(d, "-")
    s = s.replace(" ", " ").replace(" ", " ").replace(" ", " ")
    s = fold(s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def loose_text(s: str) -> str:
    """Letters and digits only. Fallback when punctuation or spacing differs."""
    return re.sub(r"[^0-9a-z]+", "", norm_text(s))


def sha1(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def sha256(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


def url_key(url: str) -> str:
    return sha1(url)


# ---------------------------------------------------------------- numbers

_SCALES = [
    (r"trilh(?:ao|oes|ão|ões)|trillions?|tri\b|tn\b", 1e12),
    (r"bilh(?:ao|oes|ão|ões)|billions?|bi\b|bn\b|bln\b", 1e9),
    (r"milh(?:ao|oes|ão|ões)|millions?|mi\b|mn\b|mln\b", 1e6),
    (r"mil\b|thousands?", 1e3),
]
_NUM = r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)(?![\w])"
_NUM_RE = re.compile(
    r"(?<![\w.,])(\d{1,3}(?:[.,]\d{3})+(?:[.,]\d+)?|\d+(?:[.,]\d+)?)"
    r"(?:\s*(" + "|".join(p for p, _ in _SCALES) + r")"      # 3,3 bilhões / 3.3 billion / 3bi
    r"|(mn|bn|m|k|b)(?!\w)"                                    # glued: 5.5m / 3bn / 200k
    r"|(?:st|nd|rd|th|º|ª)(?!\w)"                              # ordinals: 7th
    r")?(?!\w)", re.I)
_GLUED = {"m": 1e6, "mn": 1e6, "bn": 1e9, "b": 1e9, "k": 1e3}
_SCALE_RES = [(re.compile(p, re.I), m) for p, m in _SCALES]

YEAR_MIN, YEAR_MAX = 1450, 2100


def _readings(tok: str) -> list:
    """All plausible values of a number written with . or , separators."""
    has_dot, has_com = "." in tok, "," in tok
    if has_dot and has_com:
        dec = "." if tok.rfind(".") > tok.rfind(",") else ","
        th = "," if dec == "." else "."
        return [float(tok.replace(th, "").replace(dec, "."))]
    sep = "." if has_dot else ("," if has_com else None)
    if sep is None:
        return [float(tok)]
    parts = tok.split(sep)
    if len(parts) > 2:
        return [float("".join(parts))]          # 1.234.567 or 1,234,567
    head, tail = parts
    if len(tail) == 3 and tail == "000":
        return [float(head + tail)]             # 100.000 is a hundred thousand
    if len(tail) == 3 and head != "0":
        return [float(head + tail), float(head + "." + tail)]   # 3,338 or 3.338
    return [float(head + "." + tail)]           # 3,3 / 3.3


def _precision(tok: str) -> float:
    """Half a unit of the last written digit, for rounding tolerance."""
    m = re.search(r"[.,](\d{1,2})$", tok)
    if m:
        return 0.5 * 10 ** (-len(m.group(1)))
    return 0.5


def parse_numbers(text: str) -> list:
    """Return number tokens: dicts with raw, start, end, values, mantissas, scale, year, tol."""
    out = []
    if not text:
        return out
    for m in _NUM_RE.finditer(text):
        tok, sc, glued = m.group(1), m.group(2), m.group(3)
        try:
            vals = _readings(tok)
        except ValueError:
            continue
        mult = 1.0
        if glued:
            mult = _GLUED[glued.lower()]
            sc = glued
        elif sc:
            for rx, mm in _SCALE_RES:
                if rx.fullmatch(sc.strip()) or rx.match(sc.strip()):
                    mult = mm
                    break
        is_year = (not sc and re.fullmatch(r"\d{4}", tok) is not None
                   and YEAR_MIN <= int(tok) <= YEAR_MAX)
        out.append({
            "raw": m.group(0).strip(),
            "start": m.start(),
            "end": m.end(),
            "mantissas": vals,
            "values": [v * mult for v in vals],
            "scale": mult,
            "year": is_year,
            "tol": _precision(tok),          # in mantissa units
            "pct": bool(re.match(r"\s?(?:%|por ?cento|percent|pct\b|p\.p\.)", text[m.end():m.end() + 12], re.I)),
        })
    return out


def claim_tokens(value: str) -> list:
    """The numbers a claim is about: its non-year tokens, or all tokens if it only has years."""
    toks = parse_numbers(value or "")
    non_year = [t for t in toks if not t["year"]]
    return non_year or toks


def number_in(claim_toks: list, text: str):
    """First token of text that matches one of the claim tokens, else None."""
    qtoks = parse_numbers(text)
    for ct in claim_toks:
        for qt in qtoks:
            if values_match(ct, qt, strict_scale=False):
                return qt
    return None


def primary_value(tokens: list):
    """First non-year token (the number the claim is about); else first token."""
    for t in tokens:
        if not t["year"]:
            return t
    return tokens[0] if tokens else None


def is_weak(tok: dict) -> bool:
    """Numbers that occur everywhere: years and small integers without a scale."""
    if tok["year"]:
        return True
    if tok["scale"] == 1.0 and max(abs(v) for v in tok["values"]) < 100:
        return True
    return False


def values_match(claim_tok: dict, src_tok: dict, strict_scale: bool = True) -> bool:
    """True if any reading of the claim token equals any reading of the source token.

    Tolerance: 0.5 percent, widened to the claim's own rounding (half its last
    digit) but never more than 2 percent. If strict_scale is False, a scaled
    claim (3.3 billion) also matches an unscaled source mantissa (3,3) when the
    scale is written apart from the number.
    """
    if claim_tok.get("pct") and not src_tok.get("pct"):
        return False
    for cm in claim_tok["mantissas"]:
        cv = cm * claim_tok["scale"]
        half = claim_tok["tol"] * claim_tok["scale"]
        tol = max(abs(cv) * 0.005, min(half, abs(cv) * 0.02))
        for sv in src_tok["values"]:
            if abs(cv - sv) <= tol + 1e-9:
                return True
        if not strict_scale and src_tok["scale"] == 1.0 and claim_tok["scale"] != 1.0:
            for sm in src_tok["mantissas"]:
                if abs(cm - sm) <= max(abs(cm) * 0.005, min(claim_tok["tol"], abs(cm) * 0.02)) + 1e-9:
                    return True
    return False


def best_value(tok: dict) -> float:
    return tok["values"][0]


# ---------------------------------------------------------------- keywords

_STOP = set("""
a an and are as at be by for from has have in into is it its of on or that the this to was were with
not per than then there their they which who will would after before about over under also more less
o os as um uma uns umas e de da do das dos em no na nos nas por para com que se sua seu suas seus ao aos
foi sao ser mais menos entre como pelo pela pelos pelas sobre ate apos ano anos year years total value
million billion milhoes bilhoes milhao bilhao mil thousand percent cento
""".split())


def keywords(text: str, minlen: int = 4) -> list:
    words = re.findall(r"[a-z][a-z\-]+", fold(text or ""))
    seen, out = set(), []
    for w in words:
        w = w.strip("-")
        if len(w) < minlen or w in _STOP or w in seen:
            continue
        seen.add(w)
        out.append(w)
    return out


def stem(w: str) -> str:
    return w[:6] if len(w) > 6 else w


def sentence_around(text: str, start: int, end: int, maxlen: int = 300) -> str:
    """The sentence holding text[start:end], cut to about maxlen chars."""
    lo = max(0, start - 400)
    hi = min(len(text), end + 400)
    left = text[lo:start]
    right = text[end:hi]
    lm = None
    for m in re.finditer(r"(?:[.!?;]\s|\n\s*\n|\f)", left):
        lm = m
    s0 = lo + (lm.end() if lm else 0)
    rm = re.search(r"(?:[.!?;](?=\s)|\n\s*\n|\f)", right)
    s1 = end + (rm.end() if rm else len(right))
    snippet = text[s0:s1]
    if len(snippet) > maxlen:
        # centre the window on the match
        mid = (start + end) // 2 - s0
        a = max(0, mid - maxlen // 2)
        b = min(len(snippet), a + maxlen)
        a = max(0, b - maxlen)
        snippet = snippet[a:b]
        # trim to word edges
        if a > 0:
            snippet = snippet.split(" ", 1)[-1]
        if b < s1 - s0:
            snippet = snippet.rsplit(" ", 1)[0]
    return re.sub(r"[ \t]+", " ", snippet.replace("\f", " ")).strip()


def page_of(text: str, pos: int) -> int:
    """1-based page number from form feeds (pdftotext keeps \\f between pages)."""
    return text.count("\f", 0, pos) + 1


def find_quote(text: str, quote: str):
    """Locate a quote in source text. Returns (found, how, page or None)."""
    if not text or not quote:
        return False, None, None
    nq = norm_text(quote)
    if not nq:
        return False, None, None
    pages = text.split("\f") if "\f" in text else None
    if pages and len(pages) > 1:
        for i, p in enumerate(pages):
            if nq in norm_text(p):
                return True, "exact", i + 1
    nt = norm_text(text)
    if nq in nt:
        return True, "exact", None
    lq = loose_text(quote)
    if len(lq) >= 12:
        if pages and len(pages) > 1:
            for i, p in enumerate(pages):
                if lq in loose_text(p):
                    return True, "loose", i + 1
        if lq in loose_text(text):
            return True, "loose", None
    return False, None, None
