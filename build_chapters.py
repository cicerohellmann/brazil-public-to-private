#!/usr/bin/env python3
"""Build chapters/<slug>.html (one page per ruler of the republic, all terms grouped) and chapters/index.html.

Run: python3 build_chapters.py   (reads data/*.json through timeline_data.py; CSS is taken from build_timeline.py)
Optional per-person files: data/power-<slug>.json (power section), data/<slug>-deals.json (deal roles; Lula only so far).
"""
import ast
import collections
import html
import json
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
    ys = sorted(pts)
    lo, hi = min(pts.values()), max(pts.values())
    y0, y1 = ys[0], ys[-1]
    w, h = 120, 28
    X = lambda y: 2 + (y - y0) / max(1, y1 - y0) * (w - 4)
    Y = lambda v: h - 3 - (v - lo) / ((hi - lo) or 1) * (h - 6)
    line = " ".join(f"{X(y):.1f},{Y(pts[y]):.1f}" for y in ys)
    sx0, sx1 = X(max(a, y0)), X(min(b, y1))
    return (f'<svg class="spark" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="Series {y0} to {y1}, term {sy} to {ey} shaded">'
            f'<rect class="sp-t" x="{sx0:.1f}" y="0" width="{max(2, sx1 - sx0):.1f}" height="{h}"/>'
            f'<polyline class="sp-l" points="{line}"/></svg>')


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
                        f'<td class="nw">{ch:+.2f}{pct}</td><td>{spark(pts, sy, ey_eff, sy, ey_eff)}</td>'
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


def deal_row_classified(c):
    ds = " ".join(f'<a href="../disasters.html#{esc(x)}">{esc(DIS_BY_ID[x]["name"])}</a>' if x in DIS_PAGE_IDS and x in DIS_BY_ID else "" for x in c.get("disasters") or [])
    money = f'{esc(c.get("money") or "no figure")} {money_pill(c.get("money_status"))}'
    return (f'<tr><td class="nw">{esc(c.get("year"))}</td><td>{case_a(c["id"], c["id"] + ": " + c["title"])}</td>'
            f'<td>{first_sentence(c.get("who_got"))}</td><td>{first_sentence(c.get("who_paid"))}</td>'
            f'<td>{money}</td><td class="small">{esc(c.get("reason"))}</td></tr>')


def role_tables(cases, tid_prefix):
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
               + "".join(deal_row_classified(c) for c in rows) + "</tbody></table></div>")
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


def ledger_html(tid):
    deals, ongoing = ledger_cases(tid)
    out = ['<div class="callout"><strong>Roles are not classified yet</strong> for this president (started, continued, reversed, and so on). This is the plain ledger of deals signed in the term.</div>']
    if deals:
        out.append('<div class="tw"><table class="ledger"><thead><tr><th>Year</th><th>Deal</th><th>Who got</th><th>Who paid</th><th>Key figure</th></tr></thead><tbody>'
                   + "".join(f'<tr><td class="nw">{y}</td><td>{case_a(c["id"], c["id"] + ": " + c["title"])}'
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
.seg{display:block;height:100%}.r0{background:var(--c1)}.r1{background:var(--c3)}.r2{background:var(--c2)}.r3{background:var(--rg-mil)}.r4{background:var(--c4)}.r5{background:var(--dk)}
.legend .lg{margin-right:12px;white-space:nowrap}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px}
.bar{height:12px;background:var(--grid);border-radius:6px;overflow:hidden;margin:2px 0 8px}.bar span{display:block;height:100%;background:var(--c1)}
.spark{display:block}.sp-t{fill:var(--shade);stroke:none}.sp-l{fill:none;stroke:var(--c1);stroke-width:1.5}
html[data-x]{}.sp-t{fill:rgba(255,180,84,.35)}
table.num td,table.num th{white-space:nowrap}table.num th[scope=row]{white-space:normal;min-width:130px}
.kv{margin:.25em 0}.term-block{border-left:6px solid var(--acc)}
.cmp td,.cmp th{text-align:left}
.cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:12px}.cards a{display:block;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--bg);text-decoration:none}
code{font-size:.85em}
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
    totals = {"deals": 0, "people": 0, "deaths": 0}
    for t in terms:
        k = tshort(t)
        tp = f"term-{k}"
        # deals
        if classified is not None:
            cs = [c for c in classified if t["id"] in c["terms"]]
            n_by = collections.Counter(c["role"] for c in cs)
            deals_html = role_tables(cs, f"{tp}-deals") if cs else '<p class="muted">No classified deal for this term.</p>'
            started = [c for c in cs if c["role"] == "started"]
            ids = [c["id"] for c in cs if c["role"] != "context-only"]
            n_deals, n_main = len(cs), len(started)
        else:
            deals_html, n_deals, lc = ledger_html(t["id"])
            ids = [c["id"] for c in lc]
            n_by, n_main = None, n_deals
        all_case_ids += [i for i in ids if i not in all_case_ids]
        fol = followed_rows(ids)
        for did, v in fol.items():
            all_dis.setdefault(did, v)
        deaths = sum(n for n in (td.deaths_count(d.get("deaths")) for d, _ in fol.values()) if n)
        ph, n_people = term_people_html(t)
        nh, nfound = term_numbers(t)
        pwh, real = power_html(pw, t)
        pw_real = pw_real or real
        sy, ey = td.term_ref_years(t)
        pws = ""
        ptxt = ""
        mini = f'<p class="small muted">{esc(t["notes"])}</p>' if t.get("notes") else ""
        if nfound == 0:
            gaps.append(f"{term_years(t)}: none of the main series has data at both ends of the term.")
        if n_people == 0:
            gaps.append(f"{term_years(t)}: no decision-makers mapped in the people files.")
        sources = " · ".join(src(s["url"], s["title"]) for s in t.get("sources") or [] if url_ok(s.get("url")))
        tblocks.append(f'''<section id="{tp}" class="term-block"><h2 id="{tp}-h">{esc(name)}, {term_years(t)}{' <span class="flag">interim</span>' if t.get("interim") else ""}</h2>
<p class="big"><strong>{esc(t["title"])}.</strong> {esc(t["how_came_to_power"])} <strong>Left:</strong> {esc(t["how_left"])}.</p>{mini}
<p class="subnav"><a href="#{tp}-deals">Deals</a><a href="#{tp}-followed">What followed</a><a href="#{tp}-power">Power</a><a href="#{tp}-people">People</a><a href="#{tp}-numbers">Numbers</a><a href="#top">Top</a></p>
<h3 id="{tp}-deals">Deals, {term_years(t)}</h3>{deals_html}
<h3 id="{tp}-followed">What followed, {term_years(t)}</h3>{followed_table(fol)}
<h3 id="{tp}-power">Who could help or block, {term_years(t)}</h3>{pwh}
<h3 id="{tp}-people">The people who decided, {term_years(t)} ({n_people})</h3>{ph}
<h3 id="{tp}-numbers">Inherited and handed over, {term_years(t)}</h3>{nh}<p class="callout">This is the situation they worked in, not a score.</p>
<p class="small muted">Term sources: {sources or "none"}</p></section>''')
        overview.append(dict(t=t, tp=tp, n_deals=n_deals, n_main=n_main, n_by=n_by, n_dis=len(fol), deaths=deaths, n_people=n_people, real=real))
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
    summary = f'''<section id="summary"><h2 id="summary-h">{esc(name)} in one screen</h2>
<p class="lead big"><strong>{esc(P["full"])}</strong> held office in {len(terms)} term{"s" if len(terms) != 1 else ""}: {yrs}.</p>
<h3 id="summary-how">How they came and left</h3><p>{ent}</p>
<h3 id="summary-facts">The biggest facts</h3><ul class="facts big">{"".join(f"<li>{b}</li>" for b in bullets)}</ul>
{('<h3 id="summary-power">Power, per term</h3><ul>' + "".join(pw_sum) + '</ul>') if pw_sum else ''}
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

    toc = ('<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ol class="toc"><li><a href="#summary">Summary</a></li><li><a href="#overview">All terms side by side</a></li>'
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
    body = (f'<p class="sub"><a href="../timeline.html">← Timeline</a> · <a href="../index.html">Transfer cases</a></p><h1 id="title">President chapters</h1>'
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
