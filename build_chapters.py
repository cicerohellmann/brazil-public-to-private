#!/usr/bin/env python3
"""Build chapters/<slug>.html (one page per ruler of the republic, all terms grouped) and chapters/index.html.

Run: python3 build_chapters.py   (reads data/*.json through timeline_data.py; CSS is taken from build_timeline.py)
Optional per-person files: data/power-<slug>.json (power section), data/<slug>-deals.json (deal roles; Lula only so far).
"""
import ast
import collections
import html
import json
import math
import os
import re
import unicodedata

import timeline_data as td

ROOT = td.ROOT
OUT = os.path.join(ROOT, "chapters")
D = td.load_all()
TERMS, PEOPLE, CASES, DIS, S = D["terms"], D["people"], D["cases"], D["disasters"], D["series"]
CASE = {c["id"]: c for c in CASES}
DIS_BY_ID = {d["id"]: d for d in DIS}
FC = [dict(fc, _file=f) for f, ex in D["extra"].items() for fc in ex["foreign_counterparts"]]
DEAL = td.deal_places(TERMS, CASES, D["case_term"])
DMATCH = td.match_disasters(CASES, DIS)
with open(os.path.join(ROOT, "disasters.html"), encoding="utf-8") as _fh:
    DIS_PAGE_IDS = set(re.findall(r'\bid="([^"]+)"', _fh.read()))
FOLLOW = collections.defaultdict(list)
for _did, (_cid, _how, _det) in DMATCH.items():
    if not _cid:
        continue
    _d = DIS_BY_ID[_did]
    _later = _d["_y"] is not None and _d["_y"] >= CASE[_cid]["_y"]
    if _did in td.DIS_AFTER_OVERRIDES:
        _later = True
    if _later:
        FOLLOW[_cid].append(_d)


def esc(s):
    return html.escape("" if s is None else str(s))


def fold(s):
    return "".join(c for c in unicodedata.normalize("NFKD", s) if not unicodedata.combining(c))


def slugify(s):
    return re.sub(r"[^a-z0-9]+", "-", fold(s).lower()).strip("-")


def url_ok(u):
    return isinstance(u, str) and u.startswith(("http://", "https://"))


def src(u, text="source"):
    return f'<a href="{esc(u)}" rel="noopener">{esc(text)}</a>' if url_ok(u) else '<span class="muted">no link</span>'


def pill(st):
    st = st if st in ("verified", "unverified", "corrected", "disputed") else "unverified"
    return f'<span class="pill s-{st}">{esc(st)}</span>'


def money_pill(st):
    if st in ("verified", "unverified", "corrected", "disputed"):
        return pill(st)
    return f'<span class="pill s-unverified">{esc(st or "unverified")}</span>'


def first_sentence(s, n=200):
    s = (s or "").strip()
    if not s:
        return '<span class="muted">not stated</span>'
    m = re.match(r"(.+?[.;])(\s|$)", s)
    cut = m.group(1) if m else s
    if len(cut) > n:
        cut = cut[:n].rsplit(" ", 1)[0] + "…"
    return f'<span title="{esc(s)}">{esc(cut)}</span>'


def case_a(cid, text=None):
    return f'<a href="../index.html#{esc(cid)}">{esc(text if text is not None else CASE[cid]["title"])}</a>' if cid in CASE else esc(cid)


def dis_a(d):
    n = esc(d.get("name"))
    return f'<a href="../disasters.html#{esc(d["id"])}">{n}</a>' if d["id"] in DIS_PAGE_IDS else n


def deaths_txt(d):
    n = td.deaths_count(d.get("deaths"))
    if n is None:
        return "no count"
    return "none recorded" if n == 0 else f"{n:,} dead"


def key_figure(c):
    figs = c.get("figures") or []
    cur_ok = ("BRL", "USD", "R$", "US$", "GBP")
    money = [f for f in figs if any(m in str(f.get("currency") or "") for m in cur_ok) and not isinstance(f.get("value"), str)]
    pick = next((f for f in money if f.get("kind") != "other"), None) or (money[0] if money else None) or (figs[0] if figs else None)
    if not pick:
        return '<span class="muted">no figure</span>'
    v = pick.get("value")
    cur = pick.get("currency") or ""
    vs = (f"{v:,}" if isinstance(v, (int, float)) else esc(v)) + (f" {esc(cur)}" if cur and cur not in ("n/a", "other") else "")
    return f'{esc(pick.get("label"))}: <strong>{vs}</strong> {pill(pick.get("status"))}'


# ------------------------------------------------------------------ who is a chapter
def ruler_name(t):
    return t["ruler"].split("(")[0].strip()


def short_name(t):
    n = ruler_name(t)
    rep = {"Luiz Inácio Lula da Silva": "Lula", "Fernando Henrique Cardoso": "Cardoso",
           "Humberto de Alencar Castelo Branco": "Castelo Branco", "Artur da Costa e Silva": "Costa e Silva",
           "Emílio Garrastazu Médici": "Médici", "Eurico Gaspar Dutra": "Dutra", "Juscelino Kubitschek": "Kubitschek"}
    return rep.get(n, n)


PERSONS = collections.OrderedDict()   # slug -> {name, terms}
for t in TERMS:
    if t["_start"].year < 1889:
        continue
    short = short_name(t)
    if short.startswith("Military junta"):
        short = t["ruler"].split("(")[0].strip()
    slug = slugify(short)
    p = PERSONS.setdefault(slug, {"slug": slug, "name": short, "full": ruler_name(t), "terms": []})
    p["terms"].append(t)


def tshort(t):
    return t["id"][2:].rsplit("-", 1)[-1] if re.search(r"-\d{4}$", t["id"]) else t["id"][2:]


def term_years(t):
    return f'{t["_start"].year}–{"today" if t["_open"] else t["_end"].year}'


# ------------------------------------------------------------------ numbers
METRICS = [
    ("Real minimum wage", ["min-wage-real"], "R$ of Sep 2026 per month"),
    ("Income Gini", ["income-gini-pnad-ipea-1995-2025", "income-gini-pnad-old-1976-2014", "income-gini-worldbank-1981-2024"], "Gini index"),
    ("Net public debt", ["dlsp-pct-gdp", "gg-net-debt-pct-gdp-imf"], "% of GDP"),
    ("Public investment", ["public-investment-public-sector-pct-gdp"], "% of GDP"),
    ("Top 1% income share", ["top1-income-share-wid-2001-2024", "top1-income-share-wid-modelled-1920-1970"], "% of national income"),
    ("Federal state companies", ["federal-soe-count", "federal-soe-count-dest-1980-2011"], "companies"),
]


def fmt(v):
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.1f}"
    return f"{v:.2f}"


def near(pts, y, tol=2):
    if y in pts:
        return y
    c = [k for k in pts if abs(k - y) <= tol]
    return min(c, key=lambda k: (abs(k - y), k)) if c else None


def spark(pts, a, b, sy, ey):
    """Series curve with the term shaded; dots and value labels at the inherited (a) and handed-over (b) points."""
    ys = sorted(pts)
    lo, hi = min(pts.values()), max(pts.values())
    y0, y1 = ys[0], ys[-1]
    w, h, px, pt, pb = 260, 64, 4, 16, 6
    X = lambda y: px + (y - y0) / max(1, y1 - y0) * (w - 2 * px)
    Y = lambda v: pt + (1 - (v - lo) / ((hi - lo) or 1)) * (h - pt - pb)
    line = " ".join(f"{X(y):.1f},{Y(pts[y]):.1f}" for y in ys)
    sx0, sx1 = X(max(sy, y0)), X(min(ey, y1))
    lab = ""
    for yy, anc, dx in ((a, "end", -5), (b, "start", 5)):
        if yy in pts:
            x, yv = X(yy), Y(pts[yy])
            if anc == "end" and x < 40:
                anc, dx = "start", 5
            if anc == "start" and x > w - 40:
                anc, dx = "end", -5
            lab += (f'<circle class="sp-d" cx="{x:.1f}" cy="{yv:.1f}" r="2.8"/>'
                    f'<text class="sp-v" x="{x + dx:.1f}" y="{max(11, yv - 5):.1f}" text-anchor="{anc}">{fmt(pts[yy])}</text>')
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Series {y0} to {y1}, term {sy} to {ey} shaded">'
            f'<rect class="sp-t" x="{sx0:.1f}" y="0" width="{max(2, sx1 - sx0):.1f}" height="{h}"/>'
            f'<polyline class="sp-l" points="{line}"/>{lab}'
            f'<text class="sp-a" x="{px}" y="{h - 1}">{y0}</text><text class="sp-a" x="{w - px}" y="{h - 1}" text-anchor="end">{y1}</text></svg>')


def term_numbers(t):
    sy, ey = td.term_ref_years(t)
    ey_eff = ey if ey is not None else td.TODAY.year
    rows, found = [], 0
    for label, ids, unit in METRICS:
        done = False
        for sid in ids:
            if sid not in S:
                continue
            pts = S[sid]["_pts"]
            a, b = near(pts, sy), near(pts, ey_eff)
            if a is None or b is None or a == b:
                continue
            va, vb = pts[a], pts[b]
            ch = vb - va
            pct = f' ({ch / va * 100:+.0f}%)' if va and "%" not in unit and "Gini" not in unit else ""
            rows.append(f'<tr><th scope="row">{esc(label)}<br><span class="small muted">{esc(unit)}</span></th>'
                        f'<td class="nw">{fmt(va)}<br><span class="small muted">{a}</span></td>'
                        f'<td class="nw">{fmt(vb)}<br><span class="small muted">{b}</span></td>'
                        f'<td class="nw">{ch:+.2f}{pct}</td><td>{spark(pts, a, b, sy, ey_eff)}</td>'
                        f'<td class="small">{src(S[sid].get("source_url"), S[sid].get("source_title") or "source")}</td></tr>')
            found += 1
            done = True
            break
        if not done:
            rows.append(f'<tr><th scope="row">{esc(label)}</th><td colspan="5" class="muted">no data for {sy} and {ey_eff} in the series</td></tr>')
    note = f'<p class="small muted">Start = {sy} (last full year before taking office, or the start year if it began after March). End = {ey if ey else "latest year in the data, " + str(ey_eff)}.</p>'
    tab = ('<div class="tw"><table class="num"><thead><tr><th>Series</th><th>Inherited</th><th>Handed over</th><th>Change</th><th>Curve (term shaded)</th><th>Source</th></tr></thead><tbody>'
           + "".join(rows) + "</tbody></table></div>")
    return tab + note, found


# ------------------------------------------------------------------ who got richer, who got poorer
# (sid, label, unit text, value format, colour class). Money series are indexed to 100 at the base year.
RICH = [
    ("household-income-per-capita", "Household income per person", "R$ of 2025 a month, survey", lambda v: f"R$ {v:,.0f}", "k0"),
    ("min-wage-real", "Real minimum wage", "R$ of Sep 2026 a month", lambda v: f"R$ {v:,.0f}", "k1"),
    ("min-wage-in-cestas", "Minimum wage in food baskets", "São Paulo baskets a month", lambda v: f"{v:.2f}", "k2"),
    ("gdp-per-capita-worldbank", "GDP per person (reference)", "constant 2015 US$ a year", lambda v: f"US$ {v:,.0f}", "kn"),
    ("labour-income-pnadc", "Average work income", "R$ a month, survey", lambda v: f"R$ {v:,.0f}", "kn"),
]
# (sid, label, unit text, scale, direction note). Shares and Gini change in points.
GAP = [
    ("income-gini-pnad-ipea-1995-2025", "Income gap in surveys (Gini)", "0 to 100; up = more unequal", 1, "gini"),
    ("top1-income-share-wid-2001-2024", "Top 1% share of income (tax data)", "% of national income; up = top got more", 1, "top"),
    ("top10-income-share-wid-2001-2024", "Top 10% share of income (tax data)", "% of national income; up = top got more", 1, "top"),
    ("labour-share-pwt-1950-2023", "Workers' share of GDP", "% of GDP; up = workers got more", 100, "lab"),
    ("dist-wid-bottom50-share", "Bottom 50% share of income (WID)", "% of national income; up = bottom half got more", 1, "bot"),
    ("dist-wid-middle40-share", "Middle 40% share of income (WID)", "% of national income; up = middle got more", 1, "bot"),
    ("dist-poverty-rate", "Poverty rate", "% of people below US$ 8.30 a day (2021 PPP); down = fewer poor", 1, "pov"),
    ("dist-extreme-poverty-rate", "Extreme poverty rate", "% of people below US$ 3.00 a day (2021 PPP); down = fewer poor", 1, "pov"),
    ("top1-wealth-share-wid-1920-2024", "Top 1% share of wealth", "% of personal wealth; up = top got more", 1, "top"),
    ("top10-wealth-share-wid-1920-2024", "Top 10% share of wealth", "% of personal wealth; up = top got more", 1, "top"),
]
W_OK = ("verified", "corrected")
W_GATE = "household-income-per-capita"
W_TRIM = {"labour-share-pwt-1950-2023"}   # its last years repeat one value (carried forward); treated as no new data


def w_ok(sid):
    return S.get(sid, {}).get("status") in W_OK


def w_pts(sid, scale=1):
    """Points of a series; trailing repeats of the same value (carried forward) are dropped. Returns (pts, dropped_years)."""
    if sid not in S:
        return {}, []
    pts = {y: v * scale for y, v in S[sid]["_pts"].items()}
    ys = sorted(pts)
    drop = []
    while sid in W_TRIM and len(ys) > 2 and pts[ys[-1]] == pts[ys[-2]]:
        drop.append(ys.pop())
        del pts[drop[-1]]
    return pts, sorted(drop)


def w_end(pts, y, open_):
    if open_:
        c = [k for k in pts if k <= td.TODAY.year]
        return max(c) if c else None
    return near(pts, y, tol=1)


def w_span(t):
    sy, ey = td.term_ref_years(t)
    return dict(t=t, sy=sy, ey=ey if ey is not None else td.TODAY.year, open=t["_open"], s=td.frac(t["_start"]), e=td.frac(t["_end"]))


def w_ends(pts, sp):
    a = near(pts, sp["sy"], tol=1)
    b = w_end(pts, sp["ey"], sp["open"])
    return (a, b) if a is not None and b is not None and b > a else (None, None)


def w_has(t):
    pts, _ = w_pts(W_GATE)
    return w_ends(pts, w_span(t))[0] is not None


def w_yr(pts, want, got):
    if got == want:
        return str(got)
    if min(pts) < want < max(pts) and want not in pts:
        return f"{got} (no survey in {want})"
    return f"{got} (nearest year in the data)"


def w_window(spans):
    lo = min(sp["sy"] for sp in spans) - 4
    hi = max(sp["ey"] for sp in spans) + 4
    return max(lo, 1994), min(hi, td.TODAY.year - 1)


def w_runs(pts, x0, x1):
    """Consecutive-year runs inside the window; a missing year breaks the line (never interpolated)."""
    runs, cur = [], []
    for y in range(x0, x1 + 1):
        if y in pts:
            cur.append(y)
        elif cur:
            runs.append(cur)
            cur = []
    if cur:
        runs.append(cur)
    return runs


def w_nice(lo, hi, n=5):
    rng = (hi - lo) or abs(hi) or 1
    for st in (0.1, 0.2, 0.25, 0.5, 1, 2, 2.5, 5, 10, 20, 25, 50, 100, 200, 250, 500):
        if rng / st <= n:
            break
    a = math.floor(lo / st) * st
    b = math.ceil(hi / st) * st
    return a, b, st


def w_terms_marks(x0, x1, X, top):
    """Vertical lines at term changes and short names of the terms inside the window."""
    o = []
    for t in TERMS:
        s, e = td.frac(t["_start"]), td.frac(t["_end"])
        if e <= x0 or s >= x1 + 1:
            continue
        cs, ce = max(s, x0), min(e, x1 + 1)
        if s > x0:
            o.append(f'<line class="w-tb" x1="{X(s):.1f}" y1="{top - 12}" x2="{X(s):.1f}" y2="{top + 1000}"/>')
        if X(ce) - X(cs) >= 46:
            o.append(f'<text class="ch-t ch-m w-tn" x="{(X(cs) + X(ce)) / 2:.1f}" y="{top - 3}" text-anchor="middle">{esc(short_name(t))}</text>')
    return "".join(o)


def w_frame(x0, x1, W, H, padl, padr, top, bot):
    unit = (W - padl - padr) / (x1 - x0 + 1)
    X = lambda y: padl + (y - x0) * unit
    return unit, X


def w_xlabels(x0, x1, X, unit, ybase):
    step = 1 if unit >= 40 else 2 if unit >= 20 else 5
    out = []
    for y in range(x0, x1 + 1):
        if (y - x0) % step == 0 or y == x1 and step == 1:
            out.append(f'<text class="ch-t ch-m" x="{X(y + .5):.1f}" y="{ybase}" text-anchor="middle">{"’" + str(y)[2:] if unit < 40 and y != x0 else y}</text>')
    return "".join(out)


def richer_svg(spans, x0, x1, base_label):
    """Indexed lines (100 = each series' start point of the first span). Coloured inside each span's start..end, faded elsewhere."""
    W, H, padl, padr, top, bot = 480, 236, 34, 44, 26, 22
    unit, X = w_frame(x0, x1, W, H, padl, padr, top, bot)
    lines = []
    for sid, label, _u, _f, cls in RICH:
        pts, _ = w_pts(sid)
        if not pts:
            continue
        a, _b = w_ends(pts, spans[0])
        if a is None:
            continue
        idx = {y: v / pts[a] * 100 for y, v in pts.items() if x0 <= y <= x1}
        if len(idx) < 2:
            continue
        lines.append((sid, label, cls if w_ok(sid) else "kunv", idx, pts, w_ok(sid)))
    if not lines:
        return "", []
    vals = [v for *_r, idx, _p, _ok in lines for v in idx.values()]
    lo, hi, st = w_nice(min(vals + [100]), max(vals + [100]))
    ph = H - top - bot
    Y = lambda v: top + ph - (v - lo) / ((hi - lo) or 1) * ph
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Indexed income lines, {x0} to {x1}">']
    for sp in spans:
        o.append(f'<rect class="sp-t" x="{X(max(sp["s"], x0)):.1f}" y="{top}" width="{max(2, X(min(sp["e"], x1 + 1)) - X(max(sp["s"], x0))):.1f}" height="{ph}"/>')
    g = lo
    while g <= hi + 1e-9:
        o.append(f'<line class="{"w-100" if abs(g - 100) < 1e-9 else "ch-grid"}" x1="{padl}" y1="{Y(g):.1f}" x2="{W - padr}" y2="{Y(g):.1f}"/>'
                 f'<text class="ch-t ch-m" x="{padl - 4}" y="{Y(g) + 4:.1f}" text-anchor="end">{g:g}</text>')
        g += st
    o.append(w_terms_marks(x0, x1, X, top).replace('y2="' + str(top + 1000) + '"', f'y2="{top + ph}"'))
    o.append(f'<line class="ch-ax" x1="{padl}" y1="{top + ph}" x2="{W - padr}" y2="{top + ph}"/>')
    o.append(w_xlabels(x0, x1, X, unit, H - 5))
    labs = []
    for sid, label, cls, idx, pts, ok in lines:
        dash = "" if ok else " u"
        ref = " ref" if sid == "gdp-per-capita-worldbank" else ""
        for run in w_runs(idx, x0, x1):
            if len(run) > 1:
                o.append(f'<polyline class="w-l w-ctx{dash}{ref}" points="' + " ".join(f"{X(y + .5):.1f},{Y(idx[y]):.1f}" for y in run) + '"/>')
        for sp in spans:
            a, b = w_ends(pts, sp)
            if a is None:
                continue
            for run in w_runs({y: v for y, v in idx.items() if a <= y <= b}, a, b):
                if len(run) > 1:
                    o.append(f'<polyline class="w-l {cls}{dash}{ref}" points="' + " ".join(f"{X(y + .5):.1f},{Y(idx[y]):.1f}" for y in run) + '"/>')
            if ok and b in idx:
                o.append(f'<circle class="w-d {cls}" cx="{X(b + .5):.1f}" cy="{Y(idx[b]):.1f}" r="3"><title>{esc(label)} {b}: {idx[b]:.0f}</title></circle>')
                if len(spans) == 1:
                    labs.append([Y(idx[b]), X(b + .5), f"{idx[b] - 100:+.0f}%", cls])
    labs.sort()
    for i in range(1, len(labs)):
        labs[i][0] = max(labs[i][0], labs[i - 1][0] + 13)
    for yv, xv, txt, cls in labs:
        anc, dx = "start", 6
        o.append(f'<text class="ch-t ch-v w-vl {cls}" x="{xv + dx:.1f}" y="{yv + 4:.1f}" text-anchor="{anc}">{txt}</text>')
    o.append("</svg>")
    keys = "".join(f'<span class="ch-key"><span class="w-sw {cls}{"" if ok else " u"}{" ref" if sid == "gdp-per-capita-worldbank" else ""}"></span>{esc(label)}{"" if ok else " " + pill("unverified")}</span>'
                   for sid, label, cls, _i, _p, ok in lines)
    gaps = sorted({y for _s, _l, _c, idx, pts, _o in lines if pts is not None for y in range(max(x0, min(pts)), min(x1, max(pts)) + 1) if y not in pts})
    note = f'<p class="small muted">{esc(base_label)} Shaded = in office; faded lines = the years around it, for context.' + (f' Gaps in a line = no survey that year ({", ".join(map(str, gaps))}); nothing is filled in.' if gaps else "") + '</p>'
    return f'<div class="ch-fit">{"".join(o)}</div><p class="small w-keys">{keys}</p>' + note, lines


def gap_panel(sid, label, unit_txt, scale, spans, x0, x1):
    pts, drop = w_pts(sid, scale)
    win = {y: v for y, v in pts.items() if x0 <= y <= x1}
    if len(win) < 2:
        return "", None
    ok = w_ok(sid)
    W, H, padl, padr, top, bot = 300, 112, 30, 8, 20, 18
    unit, X = w_frame(x0, x1, W, H, padl, padr, top, bot)
    lo, hi = min(win.values()), max(win.values())
    padv = (hi - lo) * .15 or 1
    lo, hi = lo - padv, hi + padv
    ph = H - top - bot
    Y = lambda v: top + ph - (v - lo) / (hi - lo) * ph
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="{esc(label)}, {x0} to {x1}">']
    for sp in spans:
        o.append(f'<rect class="sp-t" x="{X(max(sp["s"], x0)):.1f}" y="{top}" width="{max(2, X(min(sp["e"], x1 + 1)) - X(max(sp["s"], x0))):.1f}" height="{ph}"/>')
    o.append(f'<line class="ch-ax" x1="{padl}" y1="{top + ph}" x2="{W - padr}" y2="{top + ph}"/>')
    for v in (lo + padv, hi - padv):
        o.append(f'<text class="ch-t ch-m" x="{padl - 3}" y="{Y(v) + 4:.1f}" text-anchor="end">{v:.0f}</text>')
    o.append(f'<text class="ch-t ch-m" x="{X(x0 + .5):.1f}" y="{H - 4}" text-anchor="middle">{x0}</text><text class="ch-t ch-m" x="{X(x1 + .5):.1f}" y="{H - 4}" text-anchor="middle">{x1}</text>')
    cls = "k3" if ok else "kunv"
    u = "" if ok else " u"
    for run in w_runs(win, x0, x1):
        if len(run) > 1:
            o.append(f'<polyline class="w-l w-ctx{u}" points="' + " ".join(f"{X(y + .5):.1f},{Y(win[y]):.1f}" for y in run) + '"/>')
        else:
            o.append(f'<circle class="w-d w-ctxd" cx="{X(run[0] + .5):.1f}" cy="{Y(win[run[0]]):.1f}" r="2"/>')
    res = []
    for sp in spans:
        a, b = w_ends(pts, sp)
        if a is None:
            continue
        for run in w_runs({y: v for y, v in win.items() if a <= y <= b}, a, b):
            if len(run) > 1:
                o.append(f'<polyline class="w-l {cls}{u}" points="' + " ".join(f"{X(y + .5):.1f},{Y(win[y]):.1f}" for y in run) + '"/>')
        for yy in (a, b):
            if yy in win:
                o.append(f'<circle class="w-d {cls}" cx="{X(yy + .5):.1f}" cy="{Y(win[yy]):.1f}" r="2.8"/>')
        if len(spans) == 1:
            for yy, anc, dx in ((a, "end", -5), (b, "start", 5)):
                x = X(yy + .5)
                if anc == "end" and x < padl + 30:
                    anc, dx = "start", 5
                if anc == "start" and x > W - padr - 30:
                    anc, dx = "end", -5
                o.append(f'<text class="ch-t ch-v" x="{x + dx:.1f}" y="{max(12, Y(win[yy]) - 5):.1f}" text-anchor="{anc}">{win[yy]:.1f}</text>')
        res.append((sp, a, b, pts[a], pts[b]))
    o.append("</svg>")
    if len(spans) == 1 and not res:
        head = f"no data in this term (series ends {max(pts)})"
    elif len(spans) == 1 and res:
        _sp, a, b, va, vb = res[0]
        head = f'{va:.1f} → {vb:.1f} ({vb - va:+.1f} points, {a}–{b})'
    else:
        head = ", ".join(f'{term_years(sp["t"])}: {vb - va:+.1f}' for sp, a, b, va, vb in res) + " points" if res else ""
    drop = [y for y in drop if x0 <= y <= x1]
    dnote = f'<br><span class="small muted">Same value repeated for {", ".join(map(str, drop))}; treated as no new data.</span>' if drop else ""
    return (f'<div class="w-p{"" if ok else " u"}"><p class="w-pt"><strong>{esc(label)}</strong>{"" if ok else " " + pill("unverified")}<br>'
            f'<span class="small muted">{esc(unit_txt)}</span><br><span class="small">{esc(head)}</span>{dnote}</p>{"".join(o)}</div>'), (res, ok, drop)


def w_word(d, eps):
    return "rose" if d > eps else "fell" if d < -eps else "stayed about the same"


def gap_sentence(gini, top1, inc_up):
    """Plain sentence from the survey Gini change and the tax-data top 1% change (both points). Built per term from data."""
    if gini is None:
        return ""
    dg = gini[1] - gini[0]
    g = f'The income gap in surveys (Gini) {w_word(dg, .5)}, {gini[0]:.1f} → {gini[1]:.1f}.'
    if top1 is None:
        return g + " Tax data on the top 1% starts in 2001."
    dt = top1[1] - top1[0]
    t1 = f' In tax data, the top 1% share of income {w_word(dt, .3)}, {top1[0]:.1f}% → {top1[1]:.1f}%.'
    gs, ts = (dg < -.5) - (dg > .5), (dt < -.3) - (dt > .3)   # +1 = fell, -1 = rose, 0 = flat
    if gs == 1 and ts <= 0:
        why = " Surveys miss top incomes; tax data catches them. So " + ("the poor gained, and " if inc_up else "") + "the top 1% kept or grew its share."
    elif gs == -1 and ts >= 0:
        why = " Surveys miss top incomes; tax data catches them. Here the survey gap grew while the top 1% share did not."
    elif gs == ts == 0:
        why = " Neither source shows a clear change."
    elif gs == ts:
        why = f' Both sources show the gap {"falling" if gs == 1 else "growing"}.'
    else:
        why = ""
    return g + t1 + why


def w_change(sid, va, vb, kind):
    if kind == "money":
        return f"{(vb / va - 1) * 100:+.0f}%"
    d = vb - va
    word = {"gini": ("more unequal", "more equal"), "top": ("top got more", "top got less"), "lab": ("workers got more", "workers got less"), "bot": ("got more", "got less"), "pov": ("more poor", "fewer poor")}[kind]
    eps = .5 if kind == "gini" else .3
    return f'{d:+.1f} points ' + (f'({word[0] if d > 0 else word[1]})' if abs(d) > eps else "(about the same)")


def headline_rows(sp):
    rows, facts = [], {}
    for sid, label, unit_txt, f, _c in RICH:
        if not w_ok(sid):
            continue
        pts, _ = w_pts(sid)
        a, b = w_ends(pts, sp)
        if a is None:
            continue
        facts[sid] = (pts[a], pts[b], a, b)
        rows.append(f'<tr><th scope="row">{esc(label)}<br><span class="small muted">{esc(unit_txt)}</span></th>'
                    f'<td><span class="nw">{f(pts[a])}</span><br><span class="small muted">{esc(w_yr(pts, sp["sy"], a))}</span></td>'
                    f'<td><span class="nw">{f(pts[b])}</span><br><span class="small muted">{esc(w_yr(pts, sp["ey"], b) if not sp["open"] else str(b) + " (latest)")}</span></td>'
                    f'<td class="w-ch">{w_change(sid, pts[a], pts[b], "money")}</td></tr>')
    for sid, label, unit_txt, scale, kind in GAP:
        if not w_ok(sid):
            continue
        pts, drop = w_pts(sid, scale)
        a, b = w_ends(pts, sp)
        if a is None:
            continue
        facts[sid] = (pts[a], pts[b], a, b)
        pct = "%" if kind != "gini" else ""
        rows.append(f'<tr><th scope="row">{esc(label)}<br><span class="small muted">{esc(unit_txt)}</span></th>'
                    f'<td>{pts[a]:.1f}{pct}<br><span class="small muted">{esc(w_yr(pts, sp["sy"], a))}</span></td>'
                    f'<td>{pts[b]:.1f}{pct}<br><span class="small muted">{esc(w_yr(pts, sp["ey"], b) if not sp["open"] else str(b) + (" (no new data after)" if drop else " (latest)"))}</span></td>'
                    f'<td class="w-ch">{w_change(sid, pts[a], pts[b], kind)}</td></tr>')
    return rows, facts


def w_main(facts):
    bits = []
    for sid, name in (("household-income-per-capita", "household income per person"), ("min-wage-real", "the real minimum wage")):
        if sid in facts:
            va, vb, a, b = facts[sid]
            p = (vb / va - 1) * 100
            bits.append(f'{name} {"rose" if p >= 1 else "fell" if p <= -1 else "stayed about the same"}' + (f" {abs(p):.0f}%" if abs(p) >= 1 else "") + f" ({a}–{b})")
    s = ("Richer or poorer: " + " and ".join(bits) + ".") if bits else ""
    return s


STATE_MONEY = [("dist-interest-pct-gdp", "Interest paid on public debt", "k3"), ("dist-bolsa-familia-pct-gdp", "Bolsa Família benefits", "k1")]


def state_money_html(spans, x0, x1):
    """'Where the state's money went' from data/series-distribution.json (optional file). Both lines are % of GDP, so no
    nominal money shares an axis with anything. Unverified lines are dotted. Returns (body, sources) or ""."""
    try:
        have = [(sid, lab, cls) for sid, lab, cls in STATE_MONEY if sid in S and len([y for y in S[sid]["_pts"] if x0 <= y <= x1]) >= 2]
        if not have:
            return ""
        W, H, padl, padr, top, bot = 480, 200, 34, 12, 26, 22
        unit, X = w_frame(x0, x1, W, H, padl, padr, top, bot)
        vals = [v for sid, _l, _c in have for y, v in S[sid]["_pts"].items() if x0 <= y <= x1]
        lo, hi, st = w_nice(0, max(vals))
        ph = H - top - bot
        Y = lambda v: top + ph - (v - lo) / ((hi - lo) or 1) * ph
        o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Interest paid and Bolsa Família, % of GDP, {x0} to {x1}">']
        for sp in spans:
            o.append(f'<rect class="sp-t" x="{X(max(sp["s"], x0)):.1f}" y="{top}" width="{max(2, X(min(sp["e"], x1 + 1)) - X(max(sp["s"], x0))):.1f}" height="{ph}"/>')
        g = lo
        while g <= hi + 1e-9:
            o.append(f'<line class="ch-grid" x1="{padl}" y1="{Y(g):.1f}" x2="{W - padr}" y2="{Y(g):.1f}"/><text class="ch-t ch-m" x="{padl - 4}" y="{Y(g) + 4:.1f}" text-anchor="end">{g:g}%</text>')
            g += st
        o.append(w_terms_marks(x0, x1, X, top).replace('y2="' + str(top + 1000) + '"', f'y2="{top + ph}"'))
        o.append(f'<line class="ch-ax" x1="{padl}" y1="{top + ph}" x2="{W - padr}" y2="{top + ph}"/>' + w_xlabels(x0, x1, X, unit, H - 5))
        keys, srcs = [], []
        for sid, lab, cls in have:
            ok = w_ok(sid)
            pts = {y: v for y, v in S[sid]["_pts"].items() if x0 <= y <= x1}
            for run in w_runs(pts, x0, x1):
                if len(run) > 1:
                    o.append(f'<polyline class="w-l {cls}{"" if ok else " u"}" points="' + " ".join(f"{X(y + .5):.1f},{Y(pts[y]):.1f}" for y in run) + '"/>')
            for y, v in pts.items():
                o.append(f'<circle class="w-d {cls}" cx="{X(y + .5):.1f}" cy="{Y(v):.1f}" r="2.2"><title>{esc(lab)} {y}: {v:.2f}% of GDP</title></circle>')
            keys.append(f'<span class="ch-key"><span class="w-sw {cls}{"" if ok else " u"}"></span>{esc(lab)} ({min(pts)}–{max(pts)}){"" if ok else " " + pill(S[sid]["status"])}</span>')
            srcs.append(src(S[sid].get("source_url"), S[sid].get("source_title") or "source"))
        o.append("</svg>")
        note = ('<p class="small muted">Both are shares of GDP, so they need no inflation adjustment. Interest is the nominal interest bill of the whole public sector. '
                'Bolsa Família annual totals start in 2013 in this file; the December-only monthly figures for 2004–2012 are not annual, so they are not drawn. '
                'Dotted = not verified yet; no sentence on this page rests on these lines.</p>')
        miss = [lab for sid, lab, _c in STATE_MONEY if sid in S and (sid, lab, _c) not in have]
        title = " and ".join(lab for _s, lab, _c in have)
        return (f'<div class="ch-fit">{"".join(o)}</div><p class="small w-keys">{"".join(keys)}</p>'
                + (f'<p class="small"><strong>{esc(", ".join(miss))}: no annual figure in these years; annual totals start in 2013.</strong></p>' if miss else "")
                + note), " · ".join(dict.fromkeys(srcs)), title
    except Exception as e:  # optional data written by another helper: never break the build
        print("warning: state-money figure skipped:", e)
        return ""


def w_sources(ids):
    return " · ".join(dict.fromkeys(src(S[i].get("source_url"), S[i].get("source_title") or "source") for i in ids if i in S))


def wealth_block(t, tp):
    """Per-term block: main point, headline table, richer chart, gap chart (and state money if the optional file exists)."""
    if not w_has(t):
        return "", False
    sp = w_span(t)
    x0, x1 = w_window([sp])
    tyrs = term_years(t)
    rows, facts = headline_rows(sp)
    inc = facts.get("household-income-per-capita")
    g = facts.get("income-gini-pnad-ipea-1995-2025")
    t1 = facts.get("top1-income-share-wid-2001-2024")
    gs = gap_sentence(g, t1, bool(inc and inc[1] > inc[0]))
    so_far = ""
    if sp["open"]:
        ends = sorted({f[3] for f in facts.values()})
        so_far = f' <span class="flag">so far (data ends {ends[0]}{"–" + str(ends[-1]) if ends[-1] != ends[0] else ""})</span>'
    start_note = f"Start = {sp['sy']}, the last full year before taking office." + (" End = the latest year in the data." if sp["open"] else f" End = {sp['ey']}, the last year in office.")
    tab = ('<div class="tw"><table class="w-tab"><thead><tr><th>What</th><th>Start</th><th>End</th><th>Change</th></tr></thead><tbody>'
           + "".join(rows) + '</tbody></table></div>' + f'<p class="small muted">{start_note} Only verified series are in this table.</p>')
    rs, lines = richer_svg([sp], x0, x1, f"100 = each line's value in {sp['sy']} (or the nearest survey year).")
    best = [(l[1], (facts[l[0]][1] / facts[l[0]][0] - 1) * 100) for l in lines if l[0] in facts and l[0] != "gdp-per-capita-worldbank"]
    rtitle = (" and ".join(f"{n if i == 0 else n[0].lower() + n[1:]} {p:+.0f}%" for i, (n, p) in enumerate(best[:2])) + f", {tyrs}" + (" so far" if sp["open"] else "") + " (inflation removed)") if best else f"Real incomes in {tyrs}"
    f_r = fig(f"{tp}-f-richer", rtitle, rs, w_sources([r[0] for r in RICH]) + ". Real money (inflation removed). GDP per person is a reference line, not people's income.",
              "no real income series covers this term.")
    panels, srcs = [], []
    for sid, label, unit_txt, scale, _k in GAP:
        ph, _r = gap_panel(sid, label, unit_txt, scale, [sp], x0, x1)
        if ph:
            panels.append(ph)
            srcs.append(sid)
    gtitle = f"The income gap in {tyrs}"
    if g:
        gtitle = f"Survey gap {w_word(g[1] - g[0], .5)} (Gini {g[0]:.1f} → {g[1]:.1f})"
        if t1:
            gtitle += f"; top 1% share in tax data {w_word(t1[1] - t1[0], .3)} ({t1[0]:.1f}% → {t1[1]:.1f}%)"
    f_g = fig(f"{tp}-f-gap", gtitle, (f'<div class="w-grid">{"".join(panels)}</div>' if panels else ""),
              w_sources(srcs) + ". Each panel says which way is better. Shaded = in office. Dashed grey panels are not verified; no sentence here rests on them.",
              "no inequality series covers this term.")
    sm = state_money_html([sp], x0, x1)
    f_s = fig(f"{tp}-f-state-money", f"Where the state's money went, {tyrs}: {sm[2][0].lower() + sm[2][1:]}, % of GDP (not verified yet)", sm[0], sm[1] + ".", "") if sm else ""
    main = w_main(facts)
    html_ = (f'<h3 id="{tp}-wealth">Who got richer, who got poorer, {tyrs}{so_far}</h3>'
             f'<p class="big"><strong>{esc(main)}</strong> {esc(gs)}</p>{tab}{f_r}{f_g}{f_s}')
    return html_, True


def summary_wealth(terms):
    sps = [w_span(t) for t in terms if w_has(t)]
    if not sps:
        return ""
    x0, x1 = w_window(sps)
    rs, lines = richer_svg(sps, x0, x1, f"100 = each line's value in {sps[0]['sy']} (or the nearest survey year).")
    per = []
    for sp in sps:
        _rows, facts = headline_rows(sp)
        f = facts.get("household-income-per-capita")
        m = facts.get("min-wage-real")
        g = facts.get("income-gini-pnad-ipea-1995-2025")
        t1 = facts.get("top1-income-share-wid-2001-2024")
        bits = []
        if f:
            bits.append(f"household income per person {(f[1] / f[0] - 1) * 100:+.0f}%")
        if m:
            bits.append(f"real minimum wage {(m[1] / m[0] - 1) * 100:+.0f}%")
        if g:
            bits.append(f"survey Gini {g[0]:.1f} → {g[1]:.1f}")
        if t1:
            bits.append(f"top 1% share {t1[0]:.1f}% → {t1[1]:.1f}%")
        per.append(f'<li><a href="#term-{tshort(sp["t"])}-wealth"><strong>{term_years(sp["t"])}{" (so far)" if sp["open"] else ""}</strong></a>: {esc(", ".join(bits))}.</li>')
    f_r = fig("summary-f-richer", f"Real incomes across {len(sps)} term{'s' if len(sps) != 1 else ''}, one line per measure", rs,
              w_sources([r[0] for r in RICH]) + ". Real money (inflation removed).", "")
    panels, srcs = [], []
    for sid, label, unit_txt, scale, _k in GAP:
        ph, _r = gap_panel(sid, label, unit_txt, scale, sps, x0, x1)
        if ph:
            panels.append(ph)
            srcs.append(sid)
    f_g = fig("summary-f-gap", "The income gap: surveys and tax data side by side", (f'<div class="w-grid">{"".join(panels)}</div>' if panels else ""),
              w_sources(srcs) + ". Each panel says which way is better. Shaded = in office. Dashed grey panels are not verified.", "")
    return (f'<h3 id="summary-wealth">Who got richer, who got poorer</h3><p class="big">Per term, start to end, inflation removed:</p>'
            f'<ul class="big">{"".join(per)}</ul>{f_r}{f_g}<p class="small muted">Each term has its own table in its section. Surveys miss top incomes; tax data catches them, so the two gap measures can move apart.</p>')


# ------------------------------------------------------------------ power json
def num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def seatbar(label, v, tot):
    pct = max(0, min(100, v / tot * 100))
    return (f'<div class="seat"><span class="small">{esc(label)}: <strong>{v:g}</strong> of {tot} ({pct:.0f}%)</span>'
            f'<div class="bar"><span style="width:{pct:.1f}%"></span></div></div>')


def gen(v, depth=0):
    """Render any JSON value; links from url keys, pills from status keys."""
    if v is None or v == "":
        return '<span class="muted">not stated</span>'
    if isinstance(v, bool) or num(v):
        return esc(v)
    if isinstance(v, str):
        if url_ok(v):
            return src(v)
        return esc(v)
    if isinstance(v, list):
        if not v:
            return '<span class="muted">none</span>'
        return "<ul class=\"pl\">" + "".join(f"<li>{gen(x, depth + 1)}</li>" for x in v) + "</ul>"
    if isinstance(v, dict):
        bits = []
        for k, x in v.items():
            kl = k.lower()
            if kl == "status":
                continue
            if kl in ("url", "source_url", "source"):
                if isinstance(x, str) and url_ok(x):
                    bits.append(f'<span class="small">{src(x)}</span>')
                    continue
            if kl == "sources" and isinstance(x, list):
                bits.append('<span class="small">' + " · ".join(src(s.get("url"), s.get("title") or "source") if isinstance(s, dict) else src(s) for s in x) + "</span>")
                continue
            lab = k.replace("_", " ")
            if isinstance(x, (dict, list)) and x:
                bits.append(f'<div class="kv"><strong>{esc(lab)}</strong>{gen(x, depth + 1)}</div>')
            else:
                bits.append(f'<div class="kv"><strong>{esc(lab)}:</strong> {gen(x, depth + 1)}</div>')
        st = v.get("status")
        return "".join(bits) + (" " + pill(st) if st else "")
    return esc(v)


def seat_bars(d):
    out = []

    def walk(x, path):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(v, path + [k])
        elif isinstance(x, list):
            for i, v in enumerate(x):
                walk(v, path)
        elif num(x):
            p = " ".join(path).lower()
            if any(w in p for w in ("coalition", "base")) and not any(w in p for w in ("share_pct", "percent")):
                if any(w in p for w in ("chamber", "deputies", "deputados", "camara", "câmara", "house")) and 0 <= x <= 513:
                    out.append(seatbar(" / ".join(path), x, 513))
                elif any(w in p for w in ("senate", "senado", "senators")) and 0 <= x <= 81:
                    out.append(seatbar(" / ".join(path), x, 81))
    walk(d, [])
    return "".join(out)


def load_power(slug):
    f = os.path.join(td.DATA, f"power-{slug}.json")
    if not os.path.exists(f):
        return None
    try:
        return json.load(open(f, encoding="utf-8"))
    except Exception:
        return None


def power_for_term(pw, t):
    """Pick the entry for this term out of a power file; tolerant of several shapes."""
    if pw is None:
        return None, None
    ent = pw.get("terms", pw) if isinstance(pw, dict) else pw
    tid = t["id"]
    alt = {tid, tid[2:], tshort(t), str(t["_start"].year), t["_sid"]}
    if isinstance(ent, dict):
        for k, v in ent.items():
            if k in alt:
                return v, pw
    elif isinstance(ent, list):
        for v in ent:
            if isinstance(v, dict):
                for key in ("term", "term_id", "id", "start_year", "start", "from"):
                    if (key == "from" or key.startswith("start")) and str(v.get(key, ""))[:4] == str(t["_start"].year) or str(v.get(key, "")) in alt:
                        return v, pw
    return None, pw


def power_html(pw, t):
    if pw is None:
        return '<div class="callout"><strong>Being researched.</strong> The power data for this person is not in the repository yet. Rebuilding the chapters picks it up once <code>data/power-' + esc(PSLUG) + '.json</code> exists.</div>', False
    ent, _ = power_for_term(pw, t)
    if ent is None:
        return '<p class="muted">The power file has no entry for this term yet.</p>', False
    bars = seat_bars(ent)
    body = ""
    if isinstance(ent, dict):
        skip = {"term", "term_id", "id"}
        for k, v in ent.items():
            if k in skip:
                continue
            body += f'<h5>{esc(k.replace("_", " "))}</h5>{gen(v)}'
    else:
        body = gen(ent)
    return (f'<div class="bars">{bars}</div>' if bars else "") + body, True


# ------------------------------------------------------------------ chapter pieces
ROLE_ORDER = ["started", "continued", "reversed", "imposed", "relief-or-public-side", "context-only"]
ROLE_TEXT = {
    "started": "Started under this president",
    "continued": "Continued from earlier terms",
    "reversed": "Reversed or undone",
    "imposed": "Imposed on the president",
    "relief-or-public-side": "Relief or public side",
    "context-only": "Context only (not a deal of this term)",
}
ROLE_CLS = {r: f"r{i}" for i, r in enumerate(ROLE_ORDER)}


def role_bar(counts):
    tot = sum(counts.values()) or 1
    segs = "".join(f'<span class="seg {ROLE_CLS[r]}" style="width:{counts[r] / tot * 100:.1f}%" title="{esc(r)}: {counts[r]}"></span>'
                   for r in ROLE_ORDER if counts.get(r))
    leg = " ".join(f'<span class="lg"><i class="sw {ROLE_CLS[r]}"></i>{esc(r)} <b>{counts[r]}</b></span>' for r in ROLE_ORDER if counts.get(r))
    return f'<div class="rolebar" role="img" aria-label="Deals by role">{segs}</div><p class="small legend">{leg}</p>'


def deal_row_classified(c, rid=None):
    ds = " ".join(f'<a href="../disasters.html#{esc(x)}">{esc(DIS_BY_ID[x]["name"])}</a>' if x in DIS_PAGE_IDS and x in DIS_BY_ID else "" for x in c.get("disasters") or [])
    money = f'{esc(c.get("money") or "no figure")} {money_pill(c.get("money_status"))}'
    ida = f' id="{esc(rid)}"' if rid else ""
    return (f'<tr{ida}><td class="nw">{esc(c.get("year"))}</td><td>{case_a(c["id"], c["id"] + ": " + c["title"])}</td>'
            f'<td>{first_sentence(c.get("who_got"))}</td><td>{first_sentence(c.get("who_paid"))}</td>'
            f'<td>{money}</td><td class="small">{esc(c.get("reason"))}</td></tr>')


def role_tables(cases, tid_prefix, tp):
    by = collections.defaultdict(list)
    for c in cases:
        by[c["role"]].append(c)
    out = [role_bar({r: len(by[r]) for r in ROLE_ORDER if by.get(r)})]
    for r in ROLE_ORDER:
        rows = by.get(r)
        if not rows:
            continue
        if r == "started":
            rows = sorted(rows, key=lambda c: -(c.get("money_brl_bn") or 0))
        else:
            rows = sorted(rows, key=lambda c: (str(c.get("year")), c["id"]))
        tbl = ('<div class="tw"><table class="ledger"><thead><tr><th>Year</th><th>Deal</th><th>Who got</th><th>Who paid</th><th>Money</th><th>Reason</th></tr></thead><tbody>'
               + "".join(deal_row_classified(c, f"{tp}-d-{c['id']}") for c in rows) + "</tbody></table></div>")
        sid = f"{tid_prefix}-{r}"
        if r == "context-only":
            out.append(f'<details id="{sid}" class="role"><summary><h4 id="{sid}-h">{esc(ROLE_TEXT[r])} ({len(rows)})</h4></summary>{tbl}</details>')
        else:
            out.append(f'<div id="{sid}" class="role"><h4 id="{sid}-h">{esc(ROLE_TEXT[r])} ({len(rows)})</h4>{tbl}</div>')
    return "".join(out)


def ledger_cases(tid):
    """Ledger deals and ongoing processes for a term id, from timeline_data."""
    deals, ongoing = [], []
    for c in CASES:
        status, places = DEAL[c["id"]]
        if status == "deal":
            for place, y, note in places:
                if place == tid:
                    deals.append((y, c, note))
        elif status == "ongoing" and places[0][0] == tid:
            ongoing.append(c)
    deals.sort(key=lambda x: (x[0], x[1]["id"]))
    return deals, ongoing


def ledger_html(tid, tp):
    deals, ongoing = ledger_cases(tid)
    seen = set()

    def rid(c):
        if c["id"] in seen:
            return ""
        seen.add(c["id"])
        return f' id="{esc(tp)}-d-{esc(c["id"])}"'
    out = ['<div class="callout"><strong>Roles are not classified yet</strong> for this president (started, continued, reversed, and so on). This is the plain ledger of deals signed in the term.</div>']
    if deals:
        out.append('<div class="tw"><table class="ledger"><thead><tr><th>Year</th><th>Deal</th><th>Who got</th><th>Who paid</th><th>Key figure</th></tr></thead><tbody>'
                   + "".join(f'<tr{rid(c)}><td class="nw">{y}</td><td>{case_a(c["id"], c["id"] + ": " + c["title"])}'
                             + (f'<br><span class="small muted">{esc(n)}</span>' if n else "") + f'</td><td>{first_sentence(c.get("who_got"))}</td>'
                             f'<td>{first_sentence(c.get("who_paid"))}</td><td>{key_figure(c)}</td></tr>' for y, c, n in deals)
                   + "</tbody></table></div>")
    else:
        out.append('<p class="muted">No signed deal in the data for this term.</p>')
    if ongoing:
        out.append('<p class="small"><strong>Ongoing under this term</strong> <span class="muted">(long processes, no single signing act)</span>: '
                   + "; ".join(case_a(c["id"], c["id"] + ": " + c["title"]) for c in ongoing) + "</p>")
    return "".join(out), len(deals), [c for _y, c, _n in deals] + ongoing


def followed_rows(case_ids):
    seen = collections.OrderedDict()
    for cid in case_ids:
        for d in FOLLOW.get(cid, []):
            seen.setdefault(d["id"], (d, []))[1].append(cid)
    return seen


def followed_table(seen):
    if not seen:
        return '<p class="muted">No disaster is linked to these deals in the data.</p>'
    rows = sorted(seen.values(), key=lambda x: (x[0]["_y"] or 0, x[0]["id"]))
    trs = "".join(
        f'<tr><td class="nw">{d["_y"]}</td><td>{dis_a(d)}<br><span class="small muted">after {", ".join(case_a(c, c) for c in cs)}</span></td>'
        f'<td class="nw">{esc(deaths_txt(d))}</td><td class="small">{esc(d.get("operator"))}</td><td class="small">{first_sentence(d.get("legal_outcome"), 160)}</td></tr>'
        for d, cs in rows)
    return ('<div class="tw"><table class="ledger"><thead><tr><th>Year</th><th>Disaster</th><th>Deaths</th><th>Operator</th><th>Legal outcome</th></tr></thead><tbody>'
            + trs + '</tbody></table></div><p class="callout">A link is not proof of cause; read the chain.</p>')


def term_people_html(t):
    pids = D["term_people"].get(t["id"], [])
    if not pids:
        return '<p class="muted">No decision-makers mapped for this term in the people files.</p>', 0
    out = []
    for pid in pids:
        p = PEOPLE[pid]
        anchor = td.person_anchor(pid, t["id"])
        posts = "; ".join(esc(x.get("post")) for x in p["posts"][:2])
        links = [l for l in p["case_links"]]
        ls = "".join(f'<li>{case_a(l["case_id"], l["case_id"])} <span class="basis {"acted" if l["basis"] == "documented-act" else "inoff"}">{esc(td.BASIS_TEXT.get(l["basis"], l["basis"]))}</span> {esc(l.get("role"))} {src(l.get("source_url"))}</li>'
                     for l in links[:8])
        more = f'<li class="muted small">and {len(links) - 8} more links in the people record</li>' if len(links) > 8 else ""
        ties = "".join(f'<li>{esc(x.get("counterpart"))} <span class="muted">({esc(x.get("kind"))})</span></li>' for x in p["foreign_ties"][:4])
        out.append(f'<details class="person"><summary><a href="../timeline.html#{esc(anchor)}">{esc(p["name"])}</a> {pill(p["_status"])}<br><span class="small muted">{posts}</span></summary>'
                   f'<div class="pbody">' + (f'<ul class="pl">{ls}{more}</ul>' if ls else '<p class="muted small">No case links.</p>')
                   + (f'<h5>Foreign ties</h5><ul class="pl">{ties}</ul>' if ties else "") + '</div></details>')
    return "".join(out), len(pids)


def foreign_html(case_ids, name):
    ids = set(case_ids)
    fx = [f for f in FC if f["case_id"] in ids]
    ties = []
    for p in PEOPLE.values():
        if fold(p["name"]).lower() == fold(name).lower() or fold(p["name"]).lower() in fold(name).lower() and len(p["name"]) > 8:
            for x in p["foreign_ties"]:
                ties.append((p, x))
    if not fx and not ties:
        return '<p class="muted">No foreign counterpart is recorded for these cases or for the person.</p>', 0
    out = []
    if fx:
        out.append('<h3 id="foreign-cases">In their deals</h3><ul class="pl">' + "".join(
            f'<li>{pill(f.get("status"))} <strong>{esc(f["counterpart"])}</strong> <span class="muted">({esc(f["country"])}, {esc(f["kind"])})</span> in {case_a(f["case_id"], f["case_id"])}: {esc(f["detail"])} {src(f.get("source_url"))}</li>' for f in fx) + "</ul>")
    if ties:
        out.append('<h3 id="foreign-person">Ties of the person</h3><ul class="pl">' + "".join(
            f'<li><strong>{esc(x.get("counterpart"))}</strong> <span class="muted">({esc(x.get("country"))}, {esc(x.get("kind"))})</span>: {esc(x.get("detail"))} {src(x.get("source_url"))}</li>' for p, x in ties[:12]) + "</ul>")
    return "".join(out), len(fx) + len(ties)


# ------------------------------------------------------------------ charts (inline SVG / CSS, generated from data)
def fig(fid, title, body, source, empty):
    """One chart: takeaway title, body, source line. Empty body -> a short 'no data yet' note."""
    if not body:
        body = f'<p class="nodata">No data yet: {esc(empty)}</p>'
    return (f'<figure id="{esc(fid)}" class="chart"><figcaption>{esc(title)}</figcaption>{body}'
            f'<p class="fsrc small muted">Source: {source}</p></figure>')


YR = re.compile(r"\b(1[5-9]\d\d|20\d\d)\b")
MONTHS = {m: i for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}


def span(t):
    """Years drawn on chart axes: start year to the last year in office (the year before, if it ended in January-March)."""
    ey = td.term_ref_years(t)[1]
    ey = td.TODAY.year if ey is None else ey
    return t["_start"].year, max(t["_start"].year, ey)


def deal_year(c, t):
    """First 4-digit year of the deal's 'year' text that falls inside the term; else the first year clamped to the term."""
    ys = [int(y) for y in YR.findall(str(c.get("year") or ""))]
    lo, hi = span(t)
    for y in ys:
        if lo <= y <= hi:
            return y
    return min(max(ys[0], lo), hi) if ys else lo


def trunc(s, n):
    s = s or ""
    return s if len(s) <= n else s[:n - 1].rstrip() + "…"


def role_k(role):
    return f"k{ROLE_ORDER.index(role)}" if role in ROLE_ORDER else "kn"


STRIP_RULE = "one dot per deal at the first year of its date that falls in the term (ranges that start earlier sit at the term start)."
SIZE_RULE = {True: " Dot area follows the money figure in R$ bn; hollow dots have no figure.", False: " All dots are one size: money is not converted to R$ bn for this president."}


def strip_svg(segs):
    """segs: [(lo, hi, label, items)]; item = dict(y, title, role, m, href). Broken axis: one segment per term."""
    if not any(s[3] for s in segs):
        return ""
    allm = [i["m"] for s in segs for i in s[3] if i.get("m")]
    mx = max(allm) if allm else 1
    R = lambda m: 4 + 9 * math.sqrt(m / mx) if m else 5
    W, gap, pad = 640, 22, 10
    spans = [s[1] - s[0] + 1 for s in segs]
    unit = (W - 2 * pad - gap * (len(segs) - 1)) / sum(spans)
    x0, lay, segl, maxh = pad, [], [], 0
    for (lo, hi, lab, items), sp in zip(segs, spans):
        by = collections.defaultdict(list)
        for it in items:
            by[it["y"]].append(it)
        for y, lst in by.items():
            lst.sort(key=lambda i: -(i.get("m") or 0))
            h = 0
            for it in lst:
                r = R(it.get("m"))
                lay.append((x0 + (y - lo + .5) * unit, h + r, r, it))
                h += 2 * r + 3
            maxh = max(maxh, h)
        segl.append((x0, sp * unit, lo, hi, lab))
        x0 += sp * unit + gap
    top = 20
    ax = top + maxh + 4
    H = ax + 22
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H:.0f}" role="img" aria-label="Deals by year">']
    for sx, sw, lo, hi, lab in segl:
        o.append(f'<line class="ch-ax" x1="{sx:.1f}" y1="{ax:.1f}" x2="{sx + sw:.1f}" y2="{ax:.1f}"/>')
        if len(segl) > 1:
            o.append(f'<text class="ch-t ch-b" x="{sx + 2:.1f}" y="13">{esc(lab)}</text>')
        step = 1 if unit >= 34 else 2 if unit >= 17 else 5
        for y in range(lo, hi + 1):
            if (y - lo) % step == 0 or y == hi and unit >= 20:
                x = sx + (y - lo + .5) * unit
                o.append(f'<line class="ch-ax" x1="{x:.1f}" y1="{ax:.1f}" x2="{x:.1f}" y2="{ax + 4:.1f}"/><text class="ch-t ch-m" x="{x:.1f}" y="{ax + 16:.1f}" text-anchor="middle">{y}</text>')
    for x, cy, r, it in lay:
        cls = role_k(it.get("role")) + ("" if it.get("m") or it.get("role") is None else " u")
        tip = f'{it["y"]}: {it["title"]}' + (f' (R$ {it["m"]:g} bn)' if it.get("m") else "") + (f', {it["role"]}' if it.get("role") else "")
        o.append(f'<a href="{esc(it["href"])}"><title>{esc(tip)}</title><circle class="ch-dot {cls}" cx="{x:.1f}" cy="{ax - 3 - cy:.1f}" r="{r:.1f}"/></a>')
    o.append("</svg>")
    keys = collections.Counter(it.get("role") for s in segs for it in s[3])
    key = " ".join(f'<span class="ch-key"><i class="ch-sw {role_k(r)}"></i>{esc(r or "signed (role not classified)")} <b>{n}</b></span>'
                   for r, n in sorted(keys.items(), key=lambda kv: ROLE_ORDER.index(kv[0]) if kv[0] in ROLE_ORDER else 99))
    return f'<div class="ch-box"><div class="ch-in">{"".join(o)}</div></div><p class="small ch-keys">{key}</p>'


# money kind: keyword rules on the money text, first match wins
MONEY_KIND = [
    ("loan volume", r"\bloan|bndes|disburs|financ|credit|treasury transfer"),
    ("revenue given up", r"forg[ao]|forgone|waiver|exempt|tax break|not collected"),
    ("price or payment", r"\bpaid|bought|bonus|price|outorga|purchase|\bfor \d"),
]


def money_kind(txt):
    t = (txt or "").lower()
    for k, rx in MONEY_KIND:
        if re.search(rx, t):
            return k
    return "other figure"


def money_html(cs, href):
    have = sorted([c for c in cs if c.get("money_brl_bn")], key=lambda c: -c["money_brl_bn"])
    none = [c for c in cs if not c.get("money_brl_bn")]
    if not have:
        return ""
    mx = have[0]["money_brl_bn"]
    rows = []
    for c in have:
        v = c["money_brl_bn"]
        ok = c.get("money_status") in ("verified", "corrected")
        w = max(1.5, v / mx * 100)
        vs = f"{v:,.1f}" if v >= 1 else f"{v:,.3g}"
        rows.append(f'<div class="mrow"><div class="mlab"><a href="{esc(href(c))}">{esc(trunc(c["title"], 70))}</a></div>'
                    f'<div class="mtr"><span class="mbar{"" if ok else " unv"}" style="width:{w:.1f}%"></span>'
                    f'<span class="mval">R$ {vs} bn · {esc(money_kind(c.get("money")))}{"" if ok else " · " + esc(c.get("money_status") or "unverified")}</span></div></div>')
    kinds = collections.Counter(money_kind(c.get("money")) for c in have)
    note = ""
    if len(kinds) > 1:
        note = (f'<p class="callout small"><strong>Not all comparable.</strong> These bars mix {", ".join(f"{k} ({n})" for k, n in kinds.items())}. '
                'A loan volume is money lent (it can be repaid); a price is money paid; revenue given up is tax or debt not collected.</p>')
    miss = ('<p class="small muted">No money figure: ' + "; ".join(f'<a href="{esc(href(c))}">{esc(trunc(c["title"], 50))}</a>' for c in none) + "</p>") if none else ""
    rules = ('<details class="small"><summary>How the kind label is chosen</summary><ul class="pl">'
             + "".join(f'<li><strong>{esc(k)}</strong>: money text matches <code>{esc(rx)}</code></li>' for k, rx in MONEY_KIND)
             + '<li>otherwise: <strong>other figure</strong></li></ul></details>')
    return f'<div class="mbars">{"".join(rows)}</div>{note}{miss}{rules}'


# receiver type: keyword rules on the first sentence of who_got, first match wins
WHO_RULES = [
    ("foreign", r"foreign|multinational|transnational|international|modec|paraguay|bolivia|argentin|venezuel|shell|total\b|cnpc|cnooc|chevron|exxon|alcoa|japanese|portug|chinese|british|american|french|german|spanish|big tech|petrogal|\bus\b|\buk\b"),
    ("banks and funds", r"\bbank|banco|financ|fgc|creditor|bondholder|\bfip\b|\bfund"),
    ("landholders", r"\bland|occupant|farmer|rancher|agribusiness|planter|grile|estate owner|latifund"),
    ("contractors", r"consorti|contractor|construct|odebrecht|camargo|andrade|\boas\b|engineering|shipyard|builder"),
    ("state or public body", r"state-controlled|state compan|state-owned|public compan|municipal|eletro|petrobras \(state"),
    ("domestic private", r"group|grupo|firm|compan|famil|private|shareholder|investor|owner|controller|industr|merchant|\bs\.a\.|ltda"),
]
WHO_K = {k: f"g{i}" for i, (k, _rx) in enumerate(WHO_RULES)}
WHO_K["other or not stated"] = "g6"


def who_type(txt):
    s = (txt or "").strip()
    m = re.match(r"(.+?[.;])(\s|$)", s)
    s = (m.group(1) if m else s).lower()
    for k, rx in WHO_RULES:
        if re.search(rx, s):
            return k
    return "other or not stated"


def who_html(cs, href):
    if not cs:
        return ""
    by = collections.OrderedDict((k, []) for k in list(WHO_K))
    for c in cs:
        by[who_type(c.get("who_got"))].append(c)
    tot = len(cs)
    segs = "".join(f'<span class="wseg {WHO_K[k]}" style="width:{len(v) / tot * 100:.2f}%" title="{esc(k)}: {len(v)}"></span>' for k, v in by.items() if v)
    lst = "".join(f'<li><span class="ch-key"><i class="ch-sw {WHO_K[k]}"></i><strong>{esc(k)}</strong> <b>{len(v)}</b></span>: '
                  + "; ".join(f'<a href="{esc(href(c))}" title="{esc(c.get("who_got"))}">{esc(trunc(first_sent(c.get("who_got")), 60))}</a>' for c in v) + "</li>"
                  for k, v in by.items() if v)
    rules = ('<details class="small"><summary>The keyword rules (first match wins, on the first sentence of "who got")</summary><ol class="pl">'
             + "".join(f'<li><strong>{esc(k)}</strong>: <code>{esc(rx)}</code></li>' for k, rx in WHO_RULES)
             + '<li>otherwise: <strong>other or not stated</strong></li></ol></details>')
    return f'<div class="wbar" role="img" aria-label="Deals by receiver type">{segs}</div><ul class="pl wlist">{lst}</ul>{rules}'


def first_sent(s):
    s = (s or "").strip()
    m = re.match(r"(.+?[.;])(\s|$)", s)
    return m.group(1).rstrip(".;") if m else s


def chain_html(cs, fol, href, t):
    """deal box -> its later disaster boxes (year, deaths)."""
    if not fol:
        return ""
    per = collections.OrderedDict()
    for d, cids in sorted(fol.values(), key=lambda x: (x[0]["_y"] or 0, x[0]["id"])):
        for cid in cids:
            per.setdefault(cid, []).append(d)
    known = {c["id"]: c for c in cs}
    rows = []
    for cid, ds in per.items():
        c = known.get(cid) or CASE.get(cid, {"id": cid, "title": cid})
        dy = deal_year(c, t)
        dbox = []
        for d in ds:
            n = td.deaths_count(d.get("deaths"))
            dt = "no death count" if n is None else ("no deaths recorded" if n == 0 else f"{n:,} dead")
            inner = f'<span class="cy">{d["_y"]}</span> {esc(trunc(d.get("name"), 70))}<br><strong class="cd">{esc(dt)}</strong>'
            dbox.append(f'<a class="cbox dis" href="../disasters.html#{esc(d["id"])}">{inner}</a>' if d["id"] in DIS_PAGE_IDS else f'<span class="cbox dis">{inner}</span>')
        rows.append(f'<div class="crow"><a class="cbox deal" href="{esc(href(c))}"><span class="cy">{dy}</span> {esc(trunc(c["title"], 70))}</a>'
                    f'<span class="carr" aria-hidden="true"></span><div class="cdis">{"".join(dbox)}</div></div>')
    return f'<div class="chain">{"".join(rows)}</div>'



def coalition_nums(x):
    xs = x if isinstance(x, list) else [x] if isinstance(x, dict) else []
    return [(e["value"], e.get("note") or e.get("source_title") or "", e) for e in xs if isinstance(e, dict) and num(e.get("value"))]


def dotgrid(total, rows, vals):
    """total seats as a column-major dot grid; vals = sorted coalition numbers (low solid, band to high lighter)."""
    cols = math.ceil(total / rows)
    s, r = 11, 4.2
    W, H = cols * s + 4, rows * s + 24
    lo = vals[0] if vals else 0
    hi = vals[-1] if vals else 0
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="{total} seats">']
    for i in range(total):
        cx, cy = 2 + (i // rows) * s + s / 2, (i % rows) * s + s / 2
        cls = "gov" if i < lo else "gov2" if i < hi else "rest"
        o.append(f'<circle class="ch-seat {cls}" cx="{cx:.1f}" cy="{cy:.1f}" r="{r}"/>')
    half = total / 2
    xh = 2 + (half / rows) * s
    o.append(f'<line class="ch-half" x1="{xh:.1f}" y1="-2" x2="{xh:.1f}" y2="{rows * s + 3}"/>'
             f'<text class="ch-t ch-m ch-big" x="{xh:.1f}" y="{rows * s + 17}" text-anchor="middle">half ({total // 2 + 1} = majority)</text></svg>')
    return "".join(o)


def defeat_marks(ent, t):
    ds = ent.get("defeats") if isinstance(ent, dict) else None
    if not ds:
        return ""
    lo, hi = span(t)
    pts, nodate = [], []
    for d in ds:
        v = d.get("value") if isinstance(d, dict) else d
        if not isinstance(v, str):
            continue
        ys = [int(y) for y in YR.findall(v) if lo <= int(y) <= hi]
        if not ys and re.search(r"year one|first year", v, re.I):
            ys = [lo]
        (pts if ys else nodate).append((ys[0] if ys else None, v))
    W, pad = 360, 22
    X = lambda y: pad + (y - lo + .5) / (hi - lo + 1) * (W - 2 * pad)
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} 46" role="img" aria-label="Big defeats by year"><line class="ch-ax" x1="{pad}" y1="30" x2="{W - pad}" y2="30"/>']
    for y in range(lo, hi + 1, 1 if hi - lo < 8 else 2):
        o.append(f'<text class="ch-t ch-m" x="{X(y):.1f}" y="44" text-anchor="middle">{y}</text>')
    cnt = collections.Counter()
    for y, v in pts:
        k = cnt[y]
        cnt[y] += 1
        x, yy = X(y) + (k - 0) * 12 - 0, 20
        o.append(f'<g><title>{esc(v)}</title><path class="ch-def" d="M{x - 5:.1f},{yy - 5} l10,10 m0,-10 l-10,10"/></g>')
    o.append("</svg>")
    lst = "".join(f'<li><span class="ch-defk">✕</span> {esc(v)}</li>' for _y, v in pts + nodate)
    return f'<p class="small ch-sub"><strong>Big defeats</strong> (✕ at the year in the text)</p><div class="ch-fit sm">{"".join(o)}</div><ul class="pl small">{lst}</ul>'


def congress_html(ent, t, tp):
    if not isinstance(ent, dict):
        return "", []
    cg = ent.get("congress") or {}
    out = []
    srcs = []
    for key, total, rows, nm in (("camara", 513, 9, "Chamber of Deputies"), ("senado", 81, 9, "Senate")):
        h = cg.get(key) or {}
        vals = coalition_nums(h.get("coalition_seats"))
        if not vals:
            out.append(f'<div class="cg"><p class="small"><strong>{nm}</strong> ({total} seats): <span class="nodata">no data yet, no sourced coalition seat count.</span></p></div>')
            continue
        ns = sorted(v for v, _n, _e in vals)
        lab = f'{ns[0]}' + (f'–{ns[-1]}' if ns[-1] != ns[0] else "")
        pct = f'{ns[0] / total * 100:.0f}' + (f'–{ns[-1] / total * 100:.0f}' if ns[-1] != ns[0] else "")
        notes = "; ".join(f'{v}: {esc(trunc(n, 80).rstrip("."))}' for v, n, _e in vals)
        srcs += [src(e.get("source_url"), e.get("source_title") or "source") for _v, _n, e in vals]
        out.append(f'<div class="cg"><p class="small"><strong>{nm}</strong>: government coalition <strong>{lab} of {total}</strong> ({pct}%). '
                   f'<span class="muted">{notes}</span></p><div class="ch-box"><div class="ch-in cgin">{dotgrid(total, rows, ns)}</div></div></div>')
    dm = defeat_marks(ent, t)
    body = "".join(out) + dm
    return body, srcs


def appr_points(ent):
    pts = []
    for a in (ent.get("approval") or []) if isinstance(ent, dict) else []:
        v = a.get("value") if isinstance(a, dict) else None
        if not isinstance(v, str) or (isinstance(a, dict) and a.get("status") == "unverified"):
            continue
        m = re.search(r"(\d{1,2})% ótimo/bom", v) or re.search(r"(\d{1,2})%", v)
        y = YR.search(v)
        if not m or not y:
            continue
        mo = re.search(r"\b(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.? (?:\d{4})", v, re.I)
        month = MONTHS[mo.group(1).lower()] if mo else (12 if re.match(r"\s*end", v, re.I) else 1 if re.match(r"\s*start", v, re.I) else 6)
        pts.append(dict(t=int(y.group(1)) + (month - .5) / 12, pct=int(m.group(1)), ob="ótimo/bom" in v, lab=v, a=a))
    return sorted(pts, key=lambda p: p["t"])


def approval_svg(segs):
    """segs: [(lo, hi, label, points)]; broken axis, line joins points only inside one term."""
    if not any(s[3] for s in segs):
        return ""
    W, gap, padl, padr = 480, 18, 46, 10
    spans = [s[1] - s[0] + 1 for s in segs]
    unit = (W - padl - padr - gap * (len(segs) - 1)) / sum(spans)
    top, ph = 22 if len(segs) > 1 else 10, 120
    Y = lambda p: top + ph - p / 100 * ph
    H = top + ph + 22
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="Approval points">']
    for g in (0, 50, 100):
        o.append(f'<line class="ch-grid" x1="{padl}" y1="{Y(g):.1f}" x2="{W - padr}" y2="{Y(g):.1f}"/><text class="ch-t ch-m" x="{padl - 4}" y="{Y(g) + 4:.1f}" text-anchor="end">{g}%</text>')
    x0 = padl
    star = False
    for (lo, hi, lab, pts), sp in zip(segs, spans):
        X = lambda tt, x0=x0, lo=lo: x0 + (tt - lo) * unit
        o.append(f'<line class="ch-ax" x1="{x0:.1f}" y1="{top + ph:.1f}" x2="{x0 + sp * unit:.1f}" y2="{top + ph:.1f}"/>')
        if len(segs) > 1:
            o.append(f'<text class="ch-t ch-b" x="{x0 + 2:.1f}" y="13">{esc(lab)}</text>')
        step = 1 if unit >= 44 else 2 if unit >= 22 else 5
        for y in range(lo, hi + 1, step):
            o.append(f'<text class="ch-t ch-m" x="{X(y + .5):.1f}" y="{top + ph + 16:.1f}" text-anchor="middle">{y}</text>')
        if len(pts) > 1:
            o.append('<polyline class="ch-line" points="' + " ".join(f"{X(p['t']):.1f},{Y(p['pct']):.1f}" for p in pts) + '"/>')
        for p in pts:
            star = star or not p["ob"]
            o.append(f'<g><title>{esc(p["lab"])}</title><circle class="ch-ap" cx="{X(p["t"]):.1f}" cy="{Y(p["pct"]):.1f}" r="4"/>'
                     f'<text class="ch-t ch-v" x="{X(p["t"]):.1f}" y="{Y(p["pct"]) - 8:.1f}" text-anchor="middle">{p["pct"]}%{"" if p["ob"] else "*"}</text></g>')
        x0 += sp * unit + gap
    o.append("</svg>")
    note = '<p class="small muted">Points are Datafolha "ótimo/bom" (good or great) where the text gives it. * = the text gives "approve" instead; not the same measure. Only verified points are drawn.</p>'
    return f'<div class="ch-fit">{"".join(o)}</div>' + note


def courts_html(ent):
    if not isinstance(ent, dict) or not isinstance(ent.get("courts"), dict):
        return "", "", 0, 0
    ap = [a for a in ent["courts"].get("appointed") or [] if isinstance(a, dict) and a.get("name")]
    if not ap:
        return "", "", 0, 0
    seated = [a for a in ap if not re.search(r"never seated|rejected", str(a.get("note") or ""), re.I)]
    out = [a for a in ap if a not in seated]
    chips = [f'<span class="seatc on" title="{esc(a.get("value"))}"><b>{esc(a["name"])}</b><span class="small">{esc(a.get("year"))}</span></span>' for a in seated]
    chips += ['<span class="seatc"><span class="small muted">other</span></span>'] * max(0, 11 - len(seated))
    chips += [f'<span class="seatc off" title="{esc(a.get("note"))}"><b>{esc(a["name"])}</b><span class="small">{esc(a.get("year"))}, {esc(a.get("note") or "not seated")}</span></span>' for a in out]
    s = src(ap[0].get("source_url"), ap[0].get("source_title") or "source")
    return f'<div class="seats11">{"".join(chips)}</div>', s, len(seated), len(out)


def people_svg(t, ids, href_of):
    pids = D["term_people"].get(t["id"], [])
    ids = list(dict.fromkeys(ids))
    links = []
    for pid in pids:
        for l in PEOPLE[pid]["case_links"]:
            if l["case_id"] in ids:
                links.append((pid, l["case_id"], l["basis"], l.get("role") or ""))
    if not links:
        return "", 0, 0
    ps = list(dict.fromkeys(p for p, *_ in links))
    cs = [c for c in ids if any(c == x for _p, x, *_ in links)]
    pi = {p: i for i, p in enumerate(ps)}
    cs.sort(key=lambda c: sum(pi[p] for p, x, *_ in links if x == c) / sum(1 for _p, x, *_ in links if x == c))
    ci = {c: i for i, c in enumerate(cs)}
    ps.sort(key=lambda p: sum(ci[x] for q, x, *_ in links if q == p) / sum(1 for q, *_ in links if q == p))
    rh = 22
    n = max(len(ps), len(cs))
    H = n * rh + 10
    W, xl, xr = 700, 200, 470
    py = {p: 5 + (i + .5) * (n * rh / len(ps)) for i, p in enumerate(ps)}
    cy = {c: 5 + (i + .5) * (n * rh / len(cs)) for i, c in enumerate(cs)}
    o = [f'<svg class="ch-svg" viewBox="0 0 {W} {H}" role="img" aria-label="People and the deals they decided">']
    for p, c, b, role in links:
        o.append(f'<path class="ch-pl {"acted" if b == "documented-act" else "inoff"}" d="M{xl + 6},{py[p]:.1f} C{(xl + xr) / 2},{py[p]:.1f} {(xl + xr) / 2},{cy[c]:.1f} {xr - 6},{cy[c]:.1f}"><title>{esc(PEOPLE[p]["name"])}: {esc(role)} ({esc(td.BASIS_TEXT.get(b, b))})</title></path>')
    for p in ps:
        o.append(f'<a href="../timeline.html#{esc(td.person_anchor(p, t["id"]))}"><text class="ch-t ch-n" x="{xl}" y="{py[p] + 4:.1f}" text-anchor="end">{esc(trunc(PEOPLE[p]["name"], 28))}</text></a>')
    for c in cs:
        ti = CASE[c]["title"] if c in CASE else c
        o.append(f'<a href="{esc(href_of(c))}"><text class="ch-t ch-n" x="{xr}" y="{cy[c] + 4:.1f}">{esc(c)} {esc(trunc(ti, 30))}</text></a>')
    o.append("</svg>")
    return f'<div class="ch-box"><div class="ch-in ppl">{"".join(o)}</div></div>', len(ps), len(cs)


# ------------------------------------------------------------------ CSS
def base_css():
    tree = ast.parse(open(os.path.join(ROOT, "build_timeline.py"), encoding="utf-8").read())
    for n in tree.body:
        if isinstance(n, ast.Assign) and getattr(n.targets[0], "id", "") == "CSS":
            return ast.literal_eval(n.value)
    raise SystemExit("CSS not found in build_timeline.py")


EXTRA_CSS = r"""
main{max-width:1000px}
section{padding:22px 20px;margin:34px 0}
h1{font-size:2.1rem}h2{font-size:1.7rem;margin-bottom:.7em}h3{font-size:1.35rem;margin:1.8em 0 .6em}h4{font-size:1.1rem;margin:1.6em 0 .4em}
.termnav{position:sticky;top:0;z-index:6;display:flex;gap:8px;overflow-x:auto;background:var(--bg);padding:8px 2px;border-bottom:1px solid var(--line);margin:0}
.termnav a{flex:0 0 auto;padding:8px 14px;border:2px solid var(--acc);border-radius:99px;text-decoration:none;font-weight:600;background:var(--card)}
.termnav a:target,.termnav a:hover{background:var(--acc);color:var(--card)}
.subnav{display:flex;flex-wrap:wrap;gap:6px 14px;margin:.4em 0 1.2em}.subnav a{font-weight:600}
.big{font-size:1.15rem;line-height:1.7}ul.facts li{margin:.7em 0}
.rolebar{display:flex;height:18px;border-radius:9px;overflow:hidden;border:1px solid var(--line);margin:.5em 0}
.seg{display:block;height:100%}.r0{background:var(--k0)}.r1{background:var(--k1)}.r2{background:var(--k2)}.r3{background:var(--k3)}.r4{background:var(--k4)}.r5{background:var(--k5)}
.legend .lg{margin-right:12px;white-space:nowrap}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
.bar{height:12px;background:var(--grid);border-radius:6px;overflow:hidden;margin:2px 0 8px}.bar span{display:block;height:100%;background:var(--c1)}
.spark{display:block;max-width:none}.sp-t{fill:var(--shade);stroke:none}.sp-l{fill:none;stroke:var(--c1);stroke-width:1.8}.sp-d{fill:var(--fg)}.sp-v{fill:var(--fg);font-size:11px;font-weight:700}.sp-a{fill:var(--muted);font-size:9px}
html[data-x]{}.sp-t{fill:rgba(255,180,84,.35)}
table.num td,table.num th{white-space:nowrap}table.num th[scope=row]{white-space:normal;min-width:130px}
.kv{margin:.25em 0}.term-block{border-left:6px solid var(--acc)}
.cmp td,.cmp th{text-align:left}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.cards a{display:block;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);text-decoration:none}
/* chart palette: one set of variables, light and dark */
:root{--k0:#1f5f99;--k1:#2f7d4f;--k2:#c0620e;--k3:#9b2d2d;--k4:#7a4aa8;--k5:#a7a29a;--kn:#4f5b66;--kgov:#1f5f99;--kgov2:#9cc0e0;--krest:#d4d0c6;--kunv:#8d8a84;--kdef:#c4001a;
--g0:#1f5f99;--g1:#7a4aa8;--g2:#c0620e;--g3:#2f7d4f;--g4:#a8813a;--g5:#2c8a8a;--g6:#a7a29a}
@media (prefers-color-scheme:dark){:root{--k0:#6cb0e6;--k1:#7fcf9b;--k2:#f0a35e;--k3:#e07a7a;--k4:#c4a0e8;--k5:#6b6760;--kn:#b8c2cc;--kgov:#6cb0e6;--kgov2:#2f6fa8;--krest:#3a4049;--kunv:#8f8b84;--kdef:#ff6b6b;
--g0:#6cb0e6;--g1:#c4a0e8;--g2:#f0a35e;--g3:#7fcf9b;--g4:#d6b26a;--g5:#6fd0d0;--g6:#6b6760}}
section:target,tr:target,figure:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
figure.chart{margin:16px 0;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);max-width:100%;min-width:0}
figure.chart figcaption{font-weight:700;margin:0 0 .5em;line-height:1.35}
.fsrc{margin:.5em 0 0}.nodata{color:var(--muted);font-style:italic;margin:.3em 0}
.ch-box{overflow-x:auto;-webkit-overflow-scrolling:touch;max-width:100%}.ch-in{min-width:520px}.ch-in.cgin{min-width:0;max-width:640px}.ch-in.ppl{min-width:600px}
.ch-svg{display:block;width:100%;height:auto}.ch-fit{max-width:640px}.ch-fit.sm{max-width:480px}.ch-big{font-size:19px}
tr,figure,section,h3,h4{scroll-margin-top:64px}
.ch-t{fill:var(--fg);font:11px system-ui,-apple-system,sans-serif}.ch-m{fill:var(--muted)}.ch-b{font-weight:700}.ch-v{font-weight:700;font-size:12px}.ch-n{font-size:12px;fill:var(--acc)}
.ch-ax{stroke:var(--muted);stroke-width:1}.ch-grid{stroke:var(--grid);stroke-width:1}
.ch-dot{stroke-width:1.5;fill-opacity:.85}.ch-dot.u{fill-opacity:.12}a:hover .ch-dot,a:focus .ch-dot{stroke:var(--fg);stroke-width:2.5}
.ch-dot.k0,.ch-sw.k0{fill:var(--k0);stroke:var(--k0);background:var(--k0)}.ch-dot.k1,.ch-sw.k1{fill:var(--k1);stroke:var(--k1);background:var(--k1)}
.ch-dot.k2,.ch-sw.k2{fill:var(--k2);stroke:var(--k2);background:var(--k2)}.ch-dot.k3,.ch-sw.k3{fill:var(--k3);stroke:var(--k3);background:var(--k3)}
.ch-dot.k4,.ch-sw.k4{fill:var(--k4);stroke:var(--k4);background:var(--k4)}.ch-dot.k5,.ch-sw.k5{fill:var(--k5);stroke:var(--k5);background:var(--k5)}
.ch-dot.kn,.ch-sw.kn{fill:var(--kn);stroke:var(--kn);background:var(--kn)}
.ch-key{margin-right:12px;white-space:nowrap}.ch-sw{display:inline-block;width:11px;height:11px;border-radius:50%;margin-right:4px;vertical-align:-1px}
.mbars{display:grid;gap:8px}.mrow{display:grid;grid-template-columns:minmax(0,38%) minmax(0,1fr);gap:4px 12px;align-items:center}
.mlab{font-size:.9rem;line-height:1.3}.mtr{display:flex;align-items:center;gap:6px;min-width:0}
.mbar{display:block;height:16px;flex:0 0 auto;max-width:62%;background:var(--k0);border-radius:2px}
.mbar.unv{background:repeating-linear-gradient(135deg,var(--kunv) 0 3px,transparent 3px 6px);border:1px solid var(--kunv)}
.mval{font-size:.82rem;white-space:normal;font-variant-numeric:tabular-nums}
.wbar{display:flex;height:22px;border-radius:4px;overflow:hidden;border:1px solid var(--line);margin:.3em 0 .6em}.wseg{display:block;height:100%}
.g0{background:var(--g0)}.g1{background:var(--g1)}.g2{background:var(--g2)}.g3{background:var(--g3)}.g4{background:var(--g4)}.g5{background:var(--g5)}.g6{background:var(--g6)}
.wlist li{margin:.35em 0;font-size:.9rem}
.chain{display:grid;gap:10px}.crow{display:grid;grid-template-columns:minmax(0,1fr) 28px minmax(0,1.3fr);align-items:center}
.cbox{display:block;padding:6px 10px;border-radius:6px;border:1px solid var(--line);background:var(--card);text-decoration:none;font-size:.88rem;line-height:1.35}
.cbox.deal{border-left:5px solid var(--k0)}.cbox.dis{border-left:5px solid var(--kdef);margin:3px 0}
.cy{font-weight:700;color:var(--fg)}.cd{color:var(--kdef)}
.carr{height:2px;background:var(--muted);position:relative}.carr::after{content:"";position:absolute;right:-1px;top:-4px;border:5px solid transparent;border-left:7px solid var(--muted);border-right:0}
.ch-seat.gov{fill:var(--kgov)}.ch-seat.gov2{fill:var(--kgov2)}.ch-seat.rest{fill:var(--krest)}
.ch-half{stroke:var(--fg);stroke-width:1.5;stroke-dasharray:4 3}.ch-def{stroke:var(--kdef);stroke-width:2.5;fill:none}.ch-defk{color:var(--kdef);font-weight:700}
.cg{margin:.4em 0 .8em}.ch-sub{margin:.6em 0 .2em}
.ch-line{fill:none;stroke:var(--k0);stroke-width:2}.ch-ap{fill:var(--k0);stroke:var(--card);stroke-width:1.5}
.seats11{display:grid;grid-template-columns:repeat(auto-fill,minmax(104px,1fr));gap:6px}
.seatc{display:flex;flex-direction:column;justify-content:center;min-height:52px;padding:5px 8px;border-radius:26px;border:2px solid var(--krest);text-align:center;font-size:.82rem;line-height:1.2}
.seatc.on{background:var(--kgov);border-color:var(--kgov);color:var(--card)}.seatc.off{border-style:dashed;border-color:var(--kgov)}
.ch-pl{fill:none;stroke-width:1.6;opacity:.8}.ch-pl.acted{stroke:var(--k2)}.ch-pl.inoff{stroke:var(--muted);stroke-dasharray:5 4}
@media (max-width:640px){.mrow{grid-template-columns:1fr}.crow{grid-template-columns:1fr}.carr{width:2px;height:16px;margin:2px 0 2px 18px}.carr::after{right:-4px;top:auto;bottom:-2px;border:5px solid transparent;border-top:7px solid var(--muted);border-bottom:0}figure.chart{padding:8px}.ch-fit .ch-t{font-size:15px}.ch-fit .ch-v{font-size:16px}}
code{font-size:.85em}
.w-l{fill:none;stroke-width:2.4;stroke-linejoin:round}.w-l.k0{stroke:var(--k0)}.w-l.k1{stroke:var(--k1)}.w-l.k2{stroke:var(--k2)}.w-l.k3{stroke:var(--k3)}.w-l.kn{stroke:var(--kn)}.w-l.kunv{stroke:var(--kunv)}
.w-l.w-ctx{stroke:var(--muted);stroke-width:1.3;opacity:.45}.w-l.ref{stroke-dasharray:6 4;stroke-width:1.8}.w-l.u{stroke-dasharray:2 3;stroke-width:1.6}
.w-d{stroke:var(--card);stroke-width:1}.w-d.k0{fill:var(--k0)}.w-d.k1{fill:var(--k1)}.w-d.k2{fill:var(--k2)}.w-d.k3{fill:var(--k3)}.w-d.kn{fill:var(--kn)}.w-d.kunv{fill:var(--kunv)}.w-d.w-ctxd{fill:var(--muted);opacity:.5}
.w-vl.k0{fill:var(--k0)}.w-vl.k1{fill:var(--k1)}.w-vl.k2{fill:var(--k2)}.w-vl.kn{fill:var(--kn)}
.w-100{stroke:var(--muted);stroke-width:1.2}.w-tb{stroke:var(--muted);stroke-width:1;stroke-dasharray:3 3;opacity:.7}.w-tn{font-size:10px}
.w-sw{display:inline-block;width:18px;height:0;border-top:3px solid var(--kn);margin-right:5px;vertical-align:4px}.w-sw.k0{border-color:var(--k0)}.w-sw.k1{border-color:var(--k1)}.w-sw.k2{border-color:var(--k2)}.w-sw.ref{border-top-style:dashed}.w-sw.u{border-top:3px dotted var(--kunv)}
.w-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:10px}.w-keys .ch-key{white-space:normal;display:inline-block}.w-p{border:1px solid var(--line);border-radius:6px;padding:6px 8px;background:var(--card);min-width:0}
.w-p.u{border-style:dashed;background:repeating-linear-gradient(135deg,transparent 0 6px,rgba(141,138,132,.08) 6px 9px)}.w-pt{margin:0 0 4px;line-height:1.3}
table.w-tab td,table.w-tab th{text-align:left;vertical-align:top}table.w-tab td{white-space:normal;min-width:64px}table.w-tab th[scope=row]{min-width:110px}.w-ch{font-weight:700}
@media (max-width:640px){h1{font-size:1.6rem}h2{font-size:1.4rem}section{padding:14px 12px;margin:24px 0}table.num td,table.num th{white-space:normal}}
"""
CSS = base_css() + EXTRA_CSS


def page(title, body):
    return (f'<!doctype html>\n<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{esc(title)}</title><style>{CSS}</style></head>\n<body><main id="top">{body}</main></body></html>\n')


# ------------------------------------------------------------------ chapter
def build_chapter(P):
    global PSLUG
    slug, name, terms = P["slug"], P["name"], P["terms"]
    PSLUG = slug
    classified = None
    cf = os.path.join(td.DATA, f"{slug}-deals.json")
    if os.path.exists(cf):
        classified = json.load(open(cf, encoding="utf-8"))["cases"]
    pw = load_power(slug)
    pw_real = False
    gaps = []
    all_case_ids = []
    all_dis = collections.OrderedDict()
    tblocks, overview = [], []
    strip_segs, appr_segs = [], []
    totals = {"deals": 0, "people": 0, "deaths": 0}
    for t in terms:
        k = tshort(t)
        tp = f"term-{k}"
        # deals
        if classified is not None:
            cs = [c for c in classified if t["id"] in c["terms"]]
            n_by = collections.Counter(c["role"] for c in cs)
            deals_html = role_tables(cs, f"{tp}-deals", tp) if cs else '<p class="muted">No classified deal for this term.</p>'
            started = [c for c in cs if c["role"] == "started"]
            ids = [c["id"] for c in cs if c["role"] != "context-only"]
            n_deals, n_main = len(cs), len(started)
            rows_here = {c["id"] for c in cs}
            strip_cs = [(deal_year(c, t), c, c["role"], c.get("money_brl_bn")) for c in cs if c["role"] != "context-only"]
            money_cs = started
            who_cs = [c for c in cs if c["role"] not in ("context-only", "relief-or-public-side")]
            src_deals = f'roles and money from <code>data/{esc(slug)}-deals.json</code>'
        else:
            deals_html, n_deals, lc = ledger_html(t["id"], tp)
            ids = [c["id"] for c in lc]
            n_by, n_main = None, n_deals
            dl, _ong = ledger_cases(t["id"])
            rows_here = {c["id"] for _y, c, _n in dl}
            strip_cs = list({c["id"]: ((y if isinstance(y, int) and span(t)[0] <= y <= span(t)[1] else deal_year(c, t)), c, None, None)
                             for y, c, _n in reversed(dl)}.values())
            money_cs = None
            who_cs = lc
            src_deals = "the case ledger (data/g*.json), deals signed in the term"
        href = (lambda c, tp=tp, rh=rows_here: f"#{tp}-d-{c['id']}" if c["id"] in rh else f"../index.html#{c['id']}")
        hid = (lambda cid, href=href: href({"id": cid}))
        tyrs = term_years(t)
        items = [dict(y=y, title=c["title"], role=r, m=m, href=href(c), cid=c["id"]) for y, c, r, m in sorted(strip_cs, key=lambda x: (x[0], x[1]["id"]))]
        strip_segs.append((*span(t), tyrs, items))
        nrole = collections.Counter(i["role"] for i in items)
        f_strip = fig(f"{tp}-f-strip", f"{len(items)} deals in {tyrs}, placed by year" + (": " + ", ".join(f"{n} {r}" for r, n in nrole.items()) if classified is not None else ""),
                      strip_svg([(*span(t), tyrs, items)]), f"{src_deals}. Rule: {STRIP_RULE}{SIZE_RULE[classified is not None]} Click a dot for its row.", "no dated deal for this term.")
        if money_cs is None:
            f_money = fig(f"{tp}-f-money", f"Money moved by the deals of {tyrs}", "", "case ledger.",
                          "roles are not classified for this president, so money is not converted to R$ bn and the started deals are not marked.")
        else:
            mh = [c for c in money_cs if c.get("money_brl_bn")]
            big = max(mh, key=lambda c: c["money_brl_bn"]) if mh else None
            f_money = fig(f"{tp}-f-money", (f"{len(mh)} of {len(money_cs)} deals started in {tyrs} have a figure in R$ bn; the largest is {trunc(big['title'], 60)}, R$ {big['money_brl_bn']:,.1f} bn"
                                            if big else f"Money moved by the deals started in {tyrs}"),
                          money_html(money_cs, href), f"{src_deals} (<code>money_brl_bn</code>, nominal). Grey hatched bars are not verified (unverified, disputed or only in the case text); corrected figures count as checked and are drawn at face value.",
                          "no deal started in this term has a money figure in R$ bn.")
        wc = collections.Counter(who_type(c.get("who_got")) for c in who_cs)
        wtop = wc.most_common(1)[0] if wc else None
        f_who = fig(f"{tp}-f-who", (f"Largest receiver group in {tyrs}: {wtop[0]}, {wtop[1]} of {len(who_cs)} deals" if wtop else f"Who got the deals of {tyrs}"),
                    who_html(who_cs, href), f'"who got" text of each deal ({src_deals}), sorted by the keyword rules shown.' + (" Relief and context-only deals are left out." if classified is not None else ""),
                    "no deal for this term.")
        all_case_ids += [i for i in ids if i not in all_case_ids]
        fol = followed_rows(ids)
        for did, v in fol.items():
            all_dis.setdefault(did, v)
        deaths = sum(n for n in (td.deaths_count(d.get("deaths")) for d, _ in fol.values()) if n)
        ph, n_people = term_people_html(t)
        nh, nfound = term_numbers(t)
        pwh, real = power_html(pw, t)
        pw_real = pw_real or real
        pdeaths = deaths
        f_chain = fig(f"{tp}-f-chain", (f"{len(fol)} later disasters are linked to deals of {tyrs}, with {pdeaths:,} deaths recorded" if fol else f"Deals of {tyrs} followed by disasters"),
                      chain_html(cs if classified is not None else lc, fol, href, t),
                      "disaster files matched to the cases by text plus hand overrides (timeline_data.py). This shows order in time, not proof of cause.",
                      "no disaster is linked to these deals.")
        ent, _ = power_for_term(pw, t)
        cgh, cgs = congress_html(ent, t, tp)
        cam = coalition_nums(((ent or {}).get("congress") or {}).get("camara", {}).get("coalition_seats")) if isinstance(ent, dict) else []
        if cam:
            ns = sorted(v for v, _n, _e in cam)
            ctitle = f"Government coalition in {tyrs}: {ns[0]}" + (f"–{ns[-1]}" if ns[-1] != ns[0] else "") + f" of 513 deputies; majority is 257"
        else:
            ctitle = f"Congress strength in {tyrs}"
        f_cong = fig(f"{tp}-f-congress", ctitle, cgh if cam or (ent and ent.get("defeats")) else "",
                     (" · ".join(dict.fromkeys(cgs)) or f"<code>data/power-{esc(slug)}.json</code>") + ". Full blue = the lower count, faded blue = up to the higher count (different counting methods or dates); grey = the rest.",
                     f"no sourced coalition seat count for this term (data/power-{slug}.json).")
        aps = appr_points(ent)
        appr_segs.append((*span(t), tyrs, aps))
        f_appr = fig(f"{tp}-f-approval", ("Approval in " + tyrs + ": " + ", ".join(f'{p["pct"]}% ({int(p["t"])})' for p in aps)) if aps else f"Approval in {tyrs}",
                     approval_svg([(*span(t), tyrs, aps)]),
                     " · ".join(dict.fromkeys(src(p["a"].get("source_url"), p["a"].get("source_title") or "source") for p in aps)) or f"<code>data/power-{esc(slug)}.json</code>",
                     "no verified approval figure for this term.")
        cth, cts, nseat, nout = courts_html(ent)
        f_court = fig(f"{tp}-f-courts", (f"{name} named {nseat} of the 11 STF ministers in {tyrs}" + (f"; {nout} more nominee not seated" if nout else "")) if cth else f"Supreme Court seats named in {tyrs}",
                      cth, (cts or f"<code>data/power-{esc(slug)}.json</code>") + ". 11 seats; filled = named in this term and seated; the other seats are not broken down. A dashed box after the 11 = nominee never seated.",
                      "no list of court appointments for this term.")
        pph, nps, ncs = people_svg(t, ids, hid)
        f_ppl = fig(f"{tp}-f-people", (f"{nps} decision-makers are linked to {ncs} deals of {tyrs}" if pph else f"People and deals in {tyrs}"),
                    pph, "case links in the people files (data/people-e*.json). Solid line = acted (documented act); dashed = in office at the time. Click a name or a deal.",
                    "no person in the people files is linked to these deals.")
        sy, ey = td.term_ref_years(t)
        pws = ""
        ptxt = ""
        mini = f'<p class="small muted">{esc(t["notes"])}</p>' if t.get("notes") else ""
        if nfound == 0:
            gaps.append(f"{term_years(t)}: none of the main series has data at both ends of the term.")
        if n_people == 0:
            gaps.append(f"{term_years(t)}: no decision-makers mapped in the people files.")
        sources = " · ".join(src(s["url"], s["title"]) for s in t.get("sources") or [] if url_ok(s.get("url")))
        wh, w_ok_t = wealth_block(t, tp)
        tblocks.append(f'''<section id="{tp}" class="term-block"><h2 id="{tp}-h">{esc(name)}, {term_years(t)}{' <span class="flag">interim</span>' if t.get("interim") else ""}</h2>
<p class="big"><strong>{esc(t["title"])}.</strong> {esc(t["how_came_to_power"])} <strong>Left:</strong> {esc(t["how_left"])}.</p>{mini}
<p class="subnav">{f'<a href="#{tp}-wealth">Richer or poorer</a>' if w_ok_t else ""}<a href="#{tp}-deals">Deals</a><a href="#{tp}-followed">What followed</a><a href="#{tp}-power">Power</a><a href="#{tp}-people">People</a><a href="#{tp}-numbers">Numbers</a><a href="#top">Top</a></p>{wh}
<h3 id="{tp}-deals">Deals, {term_years(t)}</h3>{f_strip}{f_money}{f_who}{deals_html}
<h3 id="{tp}-followed">What followed, {term_years(t)}</h3>{f_chain}{followed_table(fol)}
<h3 id="{tp}-power">Who could help or block, {term_years(t)}</h3>{f_cong}{f_appr}{f_court}{pwh}
<h3 id="{tp}-people">The people who decided, {term_years(t)} ({n_people})</h3>{f_ppl}{ph}
<h3 id="{tp}-numbers">Inherited and handed over, {term_years(t)}</h3>{nh}<p class="callout">This is the situation they worked in, not a score.</p>
<p class="small muted">Term sources: {sources or "none"}</p></section>''')
        overview.append(dict(t=t, tp=tp, wealth=w_ok_t, n_deals=n_deals, n_main=n_main, n_by=n_by, n_dis=len(fol), deaths=deaths, n_people=n_people, real=real))
        totals["deals"] += n_deals
        totals["people"] += n_people
    total_deaths = sum(n for n in (td.deaths_count(d.get("deaths")) for d, _ in all_dis.values()) if n)

    # ---- summary
    yrs = ", ".join(f"{term_years(t)}" for t in terms)
    ent = "; ".join(f'{term_years(t)}: {esc(t["how_came_to_power"])} Left: {esc(t["how_left"])}.' for t in terms)
    bullets = []
    if classified is not None:
        cnt = collections.Counter(c["role"] for c in classified)
        bullets.append(f'{len(classified)} deals tied to these terms: {cnt["started"]} started, {cnt["continued"]} continued, {cnt["reversed"]} reversed, {cnt["imposed"]} imposed.')
        top = sorted([c for c in classified if c["role"] == "started" and c.get("money_brl_bn")], key=lambda c: -c["money_brl_bn"])[:1]
        if top:
            c = top[0]
            bullets.append(f'Largest money figure among the deals they started: {esc(c["title"])}, {esc(c.get("money"))} ({esc(c.get("money_status"))}).')
    else:
        bullets.append(f'{totals["deals"]} deals signed in these terms in the ledger. Roles (started, continued, reversed) are not classified yet.')
    bullets.append(f'{len(all_dis)} later disasters are linked to these deals, with {total_deaths:,} deaths recorded. A link is not proof of cause.')
    bullets.append(f'{len(set(p for t in terms for p in D["term_people"].get(t["id"], [])))} decision-makers are mapped to these terms in the people files.')
    mw = S["min-wage-real"]["_pts"]
    sy0 = td.term_ref_years(terms[0])[0]
    eyl = td.term_ref_years(terms[-1])[1] or td.TODAY.year
    a, b = near(mw, sy0), near(mw, eyl)
    if a and b and a != b:
        bullets.append(f'Real minimum wage went from R$ {mw[a]:,.0f} ({a}) to R$ {mw[b]:,.0f} ({b}), in R$ of Sep 2026 per month. This is the situation, not a score.')
    pw_sum = []
    if isinstance(pw, dict):
        for t in terms:
            e, _ = power_for_term(pw, t)
            s = e.get("summary") if isinstance(e, dict) else None
            if s:
                pw_sum.append(f'<li><strong>{term_years(t)}:</strong> {gen(s)}</li>')
    seen_c, all_segs = set(), []
    for lo, hi, lab, its in strip_segs:
        keep = [i for i in its if i["cid"] not in seen_c]
        seen_c.update(i["cid"] for i in keep)
        all_segs.append((lo, hi, lab, keep))
    nall = sum(len(x[3]) for x in all_segs)
    f_all = fig("summary-strip", f"{nall} deals across {yrs}, one dot each at its year" + (", coloured by role" if classified is not None else ""),
                strip_svg(all_segs), ("roles and money from <code>data/" + esc(slug) + "-deals.json</code>" if classified is not None else "the case ledger") + f". Rule: {STRIP_RULE}{SIZE_RULE[classified is not None]} The axis skips the years out of office. Click a dot for its row.",
                "no dated deal in the data for these terms.")
    f_all_ap = ""
    if any(x[3] for x in appr_segs) and len(appr_segs) > 1:
        aps_all = [p for x in appr_segs for p in x[3]]
        f_all_ap = fig("summary-approval", "Approval across terms: " + ", ".join(f'{p["pct"]}% ({int(p["t"])})' for p in aps_all), approval_svg(appr_segs),
                       " · ".join(dict.fromkeys(src(p["a"].get("source_url"), p["a"].get("source_title") or "source") for p in aps_all)) + ". Lines join points only inside one term.", "")
    sw_html = summary_wealth(terms)
    summary = f'''<section id="summary"><h2 id="summary-h">{esc(name)} in one screen</h2>
{f_all}
<p class="lead big"><strong>{esc(P["full"])}</strong> held office in {len(terms)} term{"s" if len(terms) != 1 else ""}: {yrs}.</p>
{sw_html}<h3 id="summary-how">How they came and left</h3><p>{ent}</p>
<h3 id="summary-facts">The biggest facts</h3><ul class="facts big">{"".join(f"<li>{b}</li>" for b in bullets)}</ul>
{('<h3 id="summary-power">Power, per term</h3><ul>' + "".join(pw_sum) + '</ul>') if pw_sum else ''}{f_all_ap}
<p class="small muted">Plain facts from the sections below. No verdict.</p></section>'''

    # ---- overview (side by side)
    heads = "".join(f'<th><a href="#{o["tp"]}">{term_years(o["t"])}</a></th>' for o in overview)

    def row(label, f):
        return f'<tr><th scope="row">{label}</th>' + "".join(f"<td>{f(o)}</td>" for o in overview) + "</tr>"
    roles_rows = ""
    if classified is not None:
        for r in ROLE_ORDER:
            roles_rows += row(esc(r), lambda o, r=r: str(o["n_by"].get(r, 0)))
    ov_tab = ('<div class="tw"><table class="cmp"><thead><tr><th></th>' + heads + "</thead><tbody>"
              + row("Deals", lambda o: str(o["n_deals"])) + roles_rows
              + row("Disasters linked", lambda o: str(o["n_dis"])) + row("Deaths recorded", lambda o: f'{o["deaths"]:,}')
              + row("Decision-makers", lambda o: str(o["n_people"]))
              + row("Power data", lambda o: "in file" if o["real"] else "being researched") + "</tbody></table></div>")

    def jump(sub):
        return '<p class="subnav">' + "".join(f'<a href="#{o["tp"]}-{sub}">{term_years(o["t"])}</a>' for o in overview) + "</p>"
    ov = f'''<section id="overview"><h2 id="overview-h">All terms side by side</h2>
<p class="big">Counts only, not a score. Each term has its own block below.</p>{ov_tab}
{('<h3 id="wealth">Who got richer, who got poorer</h3><p>Real incomes and the income gap, per term.</p><p class="subnav">' + "".join(f'<a href="#{o["tp"]}-wealth">{term_years(o["t"])}</a>' for o in overview if o["wealth"]) + "</p>") if any(o["wealth"] for o in overview) else ""}
<h3 id="deals">Deals made under {esc(name)}</h3><p>Jump to the deals of a term.</p>{jump("deals")}{role_bar(collections.Counter(c["role"] for c in classified)) if classified is not None else '<p class="small muted">Roles are not classified yet for this president.</p>'}
<h3 id="followed-by">What followed</h3><p>{len(all_dis)} disasters linked to these deals. A link is not proof of cause; read the chain.</p>{jump("followed")}
<h3 id="power">Who could help or block {esc(name)}</h3><p>{"Power data is in the file." if pw_real else '<strong>Being researched.</strong>'}</p>{jump("power")}
<h3 id="people">The people who decided</h3><p>Decision-makers per term.</p>{jump("people")}
<h3 id="numbers">What they inherited and handed over</h3><p>Start and end values of the main series. This is the situation they worked in, not a score.</p>{jump("numbers")}
</section>'''

    # ---- foreign, gaps
    fh, nf = foreign_html(all_case_ids, P["full"])
    foreign = f'<section id="foreign"><h2 id="foreign-h">Foreign counterparts tied to these terms</h2>{fh}</section>'
    if classified is None:
        gaps.append("Deal roles (started, continued, reversed, imposed) are not classified yet.")
    else:
        weak = [c for c in classified if c.get("money_status") in ("unverified", "disputed", "in-text (not in figures)")]
        gaps.append(f"{len(weak)} of {len(classified)} classified deals have a money figure that is unverified, disputed or only in the case text.")
        nomoney = [c for c in classified if not c.get("money_brl_bn")]
        gaps.append(f"{len(nomoney)} classified deals have no money figure in billions of reais.")
    if pw is None:
        gaps.append("Power data (seats, house presidents, STF, central bank, approval) is still being researched.")
    uns = [PEOPLE[p]["name"] for t in terms for p in D["term_people"].get(t["id"], []) if PEOPLE[p]["_status"] == "unverified"]
    if uns:
        gaps.append(f"{len(set(uns))} mapped decision-makers have no verified post record.")
    nc = [d["name"] for d, _ in all_dis.values() if td.deaths_count(d.get("deaths")) is None]
    if nc:
        gaps.append(f"{len(nc)} linked disasters have no death count.")
    if nf == 0:
        gaps.append("No foreign counterpart is recorded.")
    gaps.append("Disaster links come from text matching plus hand overrides; they show order in time, not cause.")
    gaps_html = f'<section id="gaps"><h2 id="gaps-h">What is missing or unverified</h2><ul class="big">{"".join(f"<li>{esc(g)}</li>" for g in gaps)}</ul></section>'

    toc = ('<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ol class="toc"><li><a href="#summary">Summary</a></li>' + ('<li><a href="#summary-wealth">Who got richer, who got poorer</a></li>' if sw_html else '') + '<li><a href="#overview">All terms side by side</a></li>'
           + "".join(f'<li><a href="#{o["tp"]}">{term_years(o["t"])}</a></li>' for o in overview)
           + '<li><a href="#foreign">Foreign counterparts</a></li><li><a href="#gaps">Gaps</a></li></ol></nav>')
    tabs = '<nav class="termnav" id="termnav" aria-label="Jump between terms"><a href="#summary">Summary</a>' + "".join(
        f'<a href="#{o["tp"]}">{term_years(o["t"])}</a>' for o in overview) + '<a href="#foreign">Foreign</a><a href="#gaps">Gaps</a></nav>'
    head = (f'<p class="sub"><a href="index.html">← All chapters</a> · <a href="../timeline.html">Timeline</a> · <a href="../index.html">Transfer cases</a> · <a href="../disasters.html">Disasters</a></p>'
            f'<h1 id="title">{esc(name)}: everything in one place</h1>')
    body = head + tabs + summary + toc + ov + "".join(tblocks) + foreign + gaps_html
    return page(f"{name}: president chapter", body), pw_real, len(terms)


def build_index():
    rows = []
    for P in PERSONS.values():
        ts = P["terms"]
        rows.append(f'<tr id="c-{P["slug"]}"><td class="nw">{ts[0]["_start"].year}–{"today" if ts[-1]["_open"] else ts[-1]["_end"].year}</td>'
                    f'<td><a href="{P["slug"]}.html">{esc(P["name"])}</a></td><td class="small">{", ".join(term_years(t) for t in ts)}</td>'
                    f'<td class="small">{esc(ts[0]["regime"])}</td></tr>')
    body = (f'<p class="sub"><a href="../timeline.html">← Timeline</a> · <a href="../timeline-charts.html">Timeline chart, 1822–2026</a> · <a href="../index.html">Transfer cases</a></p><h1 id="title">President chapters</h1>'
            f'<p class="lead">One page per ruler of the republic, with every term, deal, disaster link, person and number in one place. Time order.</p>'
            f'<nav id="contents"><h2 id="contents-h">Contents</h2><ol class="toc"><li><a href="#all">All chapters</a></li></ol></nav>'
            f'<section id="all"><h2 id="all-h">All {len(PERSONS)} chapters</h2><div class="tw"><table><thead><tr><th>Years</th><th>Chapter</th><th>Terms</th><th>Regime</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div></section>")
    return page("President chapters", body)


if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for P in PERSONS.values():
        h, real, n = build_chapter(P)
        with open(os.path.join(OUT, P["slug"] + ".html"), "w", encoding="utf-8") as fh:
            fh.write(h)
    with open(os.path.join(OUT, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(build_index())
    print(f"{len(PERSONS)} chapters written to chapters/")
