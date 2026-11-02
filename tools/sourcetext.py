"""Load cached source text for a URL (live snapshot, else the archive copy)."""
from __future__ import annotations

import json
import os

from textnorm import sha1

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "sources", "cache")
INDEX = os.path.join(ROOT, "sources", "index.json")


def load_index() -> dict:
    if os.path.exists(INDEX):
        return json.load(open(INDEX, encoding="utf-8"))
    return {}


_cache: dict = {}


def text_for(url: str, which: str = "live"):
    """which = 'live' or 'archive'. Returns str or None."""
    key = (url, which)
    if key in _cache:
        return _cache[key]
    name = sha1(url) + (".txt" if which == "live" else ".archive.txt")
    p = os.path.join(CACHE, name)
    t = open(p, encoding="utf-8", errors="replace").read() if os.path.exists(p) else None
    _cache[key] = t
    return t


def usable_texts(url: str, idx: dict) -> list:
    """[(which, text)] to search, live first. Live text counts only if the fetch was ok."""
    rec = idx.get(url) or {}
    out = []
    if rec.get("state") == "ok":
        t = text_for(url, "live")
        if t:
            out.append(("live", t))
    if rec.get("archive_state") == "ok":
        t = text_for(url, "archive")
        if t:
            out.append(("archive", t))
    return out
