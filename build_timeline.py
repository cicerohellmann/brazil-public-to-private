#!/usr/bin/env python3
"""Build timeline.html: Brazil's terms of power on one year axis, crossed with public patrimony,
purchasing power, concentration of wealth and political power, plus the decision-makers of every term.

Run: python3 build_timeline.py   (reads data/*.json through timeline_data.py)
"""
import collections
import html
import json
import os
import re
import sys

import timeline_data as td

ROOT = td.ROOT
OUT = os.path.join(ROOT, "timeline.html")
D = td.load_all()
TERMS, PEOPLE, CASES, DIS, S = D["terms"], D["people"], D["cases"], D["disasters"], D["series"]
TID = {t["id"]: t for t in TERMS}
CASE = {c["id"]: c for c in CASES}
CP, CT, TP = D["case_people"], D["case_term"], D["term_people"]
FC = [dict(fc, _file=f) for f, ex in D["extra"].items() for fc in ex["foreign_counterparts"]]


def esc(s):
    return html.escape("" if s is None else str(s))


def url_ok(u):
    return isinstance(u, str) and u.startswith(("http://", "https://"))


def src(u, text="source", title=None):
    if url_ok(u):
        t = f' title="{esc(title)}"' if title else ""
        return f'<a href="{esc(u)}" rel="noopener"{t}>{esc(text)}</a>'
    return '<span class="muted">no link</span>'


def pill(st, note=None):
    st = st if st in ("verified", "unverified") else "unverified"
    t = f' title="{esc(note)}"' if note else ""
    return f'<span class="pill s-{st}"{t}>{st}</span>'


def fmt(v):
    a = abs(v)
    if a >= 100:
        return f"{v:,.0f}"
    if a >= 10:
        return f"{v:.1f}"
    if a >= 1:
        return f"{v:.2f}"
    return f"{v:.3f}"


def case_a(cid, text=None):
    if cid in CASE:
        return f'<a href="index.html#{esc(cid)}">{esc(text if text is not None else CASE[cid]["title"])}</a>'
    return esc(cid)


REGIME = {
    "monarchy": ("rg-mon", "Monarchy"),
    "oligarchic republic": ("rg-olig", "Oligarchic republic"),
    "Vargas dictatorship": ("rg-vd", "Vargas dictatorship"),
    "democracy": ("rg-dem", "Democracy"),
    "military dictatorship": ("rg-mil", "Military dictatorship"),
    "new republic": ("rg-new", "New Republic (indirect election)"),
}
for t in TERMS:
    assert t["regime"] in REGIME, t["regime"]


def regime_pill(r):
    k, lab = REGIME[r]
    return f'<span class="rpill {k}">{esc(lab)}</span>'


def years_txt(t):
    e = "today" if t["_open"] else str(t["_end"].year)
    return f'{t["_start"].year}–{e}'


def short_ruler(r):
    r = r.split("(")[0].strip()
    rep = {"Provisional Triune Regency": "Regency (prov.)", "Permanent Triune Regency": "Triune Regency",
           "Luiz Inácio Lula da Silva": "Lula", "Fernando Henrique Cardoso": "Cardoso",
           "Humberto de Alencar Castelo Branco": "Castelo Branco", "Artur da Costa e Silva": "Costa e Silva",
           "Emílio Garrastazu Médici": "Médici", "Eurico Gaspar Dutra": "Dutra", "Juscelino Kubitschek": "Kubitschek"}
    return rep.get(r, r)


# =============================================================== chart geometry
Y0, Y1 = 1822, 2026
L, R, PX = 50, 14, 5.4
W = round(L + (Y1 - Y0 + 1) * PX + R)


def X(y):
    return L + (y - Y0) * PX


def XM(y):  # middle of a year slot
    return L + (y - Y0 + 0.5) * PX


DICT = []  # dictatorship spans (fractional years) for shading
for t in TERMS:
    if "dictatorship" in t["regime"]:
        a, b = td.frac(t["_start"]), td.frac(t["_end"])
        if DICT and abs(DICT[-1][1] - a) < 0.05:
            DICT[-1][1] = b
        else:
            DICT.append([a, b])


def frame(h, grid=True):
    out = []
    for a, b in DICT:
        out.append(f'<rect class="shade" x="{X(a):.1f}" y="0" width="{(b - a) * PX:.1f}" height="{h}"/>')
    if grid:
        for y in range(1830, Y1 + 1, 10):
            out.append(f'<line class="grid{" g50" if y % 50 == 0 else ""}" x1="{X(y):.1f}" x2="{X(y):.1f}" y1="0" y2="{h}"/>')
    return "".join(out)


def svg_open(h, label):
    return (f'<svg class="trk" viewBox="0 0 {W} {h}" width="{W}" height="{h}" role="img" aria-label="{esc(label)}">')


def svg_close(h):
    return f'<line class="xh" x1="-20" x2="-20" y1="0" y2="{h}"/></svg>'


# =============================================================== series tracks
READ = {}   # series id -> {year: display string}
DRAWN = []  # series ids drawn


def is_dashed(s):
    return s["status"] != "verified" or "imputed" in s["label"].lower() or "modelled" in s["label"].lower()


def track(tid, title, unit, specs, ymin, ymax, h=86, ticks=None, note=None):
    """specs: list of dicts {id, short, mode: line|points|bars, scale, cls}"""
    pad_t, pad_b = 8, 8
    ih = h - pad_t - pad_b

    def Y(v):
        return pad_t + ih * (1 - (v - ymin) / (ymax - ymin))
    body = [frame(h)]
    ticks = ticks or [ymin, (ymin + ymax) / 2, ymax]
    for tv in ticks:
        body.append(f'<line class="yt" x1="{L - 4}" x2="{W - R}" y1="{Y(tv):.1f}" y2="{Y(tv):.1f}"/>'
                    f'<text class="yl" x="{L - 6}" y="{Y(tv) + 3:.1f}">{esc(fmt(tv) if tv != int(tv) or abs(tv) < 10 else f"{int(tv):,}")}</text>')
    legend = []
    for i, sp in enumerate(specs):
        s = S[sp["id"]]
        DRAWN.append(sp["id"])
        cls = sp.get("cls", f"c{i + 1}")
        scale = sp.get("scale", 1)
        dashed = is_dashed(s)
        pts = sorted(s["_pts"].items())
        out = [y for y, val in pts if Y0 <= y <= Y1 and not (ymin <= val * scale <= ymax)]
        assert not out, f"{sp['id']} outside y-range {ymin}-{ymax} in {out[:5]}"
        READ[sp["id"]] = {y: fmt(v) for y, v in pts}
        mode = sp.get("mode", "line")
        hollow = dashed
        g = [f'<g class="{cls}{" dash" if dashed else ""}">']
        if mode == "bars":
            bw = PX - 1.2
            for y, v in pts:
                if Y0 <= y <= Y1:
                    g.append(f'<rect class="bar" x="{X(y) + 0.6:.1f}" y="{Y(v * scale):.1f}" width="{bw:.1f}" height="{Y(ymin) - Y(v * scale):.1f}"><title>{y}: {esc(fmt(v))} {esc(s["unit"])}</title></rect>')
        else:
            runs, cur = [], []
            for y, v in pts:
                if not (Y0 <= y <= Y1):
                    continue
                if mode == "line" and cur and y == cur[-1][0] + 1:
                    cur.append((y, v))
                else:
                    if cur:
                        runs.append(cur)
                    cur = [(y, v)]
            if cur:
                runs.append(cur)
            for run in runs:
                if mode == "line" and len(run) > 1:
                    d = " ".join(f"{XM(y):.1f},{Y(v * scale):.1f}" for y, v in run)
                    g.append(f'<polyline class="ln" points="{d}"/>')
                else:
                    for y, v in run:
                        g.append(f'<circle class="pt{" hol" if hollow else ""}" cx="{XM(y):.1f}" cy="{Y(v * scale):.1f}" r="3.2"><title>{y}: {esc(fmt(v))} {esc(s["unit"])}</title></circle>')
        g.append("</g>")
        body.append("".join(g))
        sw_line = ('<line x1="1" y1="6" x2="21" y2="6"/>' if mode == "line" else
                   '<rect x="6" y="1" width="10" height="10"/>' if mode == "bars" else
                   f'<circle cx="11" cy="6" r="4" class="{"hol" if hollow else ""}"/>')
        sw = f'<svg class="sw {cls}{" dash" if dashed else ""}" viewBox="0 0 22 12" width="22" height="12" aria-hidden="true">{sw_line}</svg>'
        yrs = f'{min(s["_pts"])}–{max(s["_pts"])}' if len(s["_pts"]) > 1 else f'{min(s["_pts"])}'
        flag = ""
        if dashed:
            flag = ' <span class="flag">imputed</span>' if "imputed" in s["label"].lower() else (
                ' <span class="flag">modelled</span>' if "modelled" in s["label"].lower() else "")
        sc = f' <span class="muted">(drawn ×{scale:g})</span>' if scale != 1 else ""
        legend.append(
            f'<li>{sw} <span title="{esc(s["label"])}">{esc(sp["short"])}</span> <span class="muted">{yrs}</span>{sc} '
            f'{pill(s["status"])}{flag} {src(s["source_url"], "source", s["source_title"])} '
            f'<span class="rvw">→ <b class="rv" data-s="{esc(sp["id"])}" data-u="{esc(s["unit"])}">–</b></span></li>')
    nt = f'<p class="cnote">{note}</p>' if note else ""
    return (f'<div class="cap" id="{tid}"><span class="ct">{esc(title)}</span> <span class="cu">{esc(unit)}</span>'
            f'<ul class="lg">{"".join(legend)}</ul>{nt}</div>'
            + svg_open(h, title) + "".join(body) + svg_close(h))


# =============================================================== terms band
def terms_band():
    h = 128
    out = [svg_open(h, "Terms of power, coloured by regime")]
    for y in range(1830, Y1 + 1, 10):
        out.append(f'<line class="grid{" g50" if y % 50 == 0 else ""}" x1="{X(y):.1f}" x2="{X(y):.1f}" y1="14" y2="{h}"/>')
        if y % 20 == 0:
            out.append(f'<text class="xl" x="{X(y):.1f}" y="10">{y}</text>')
    for t in TERMS:
        a, b = td.frac(t["_start"]), td.frac(t["_end"])
        x, w = X(a), max((b - a) * PX, 1.2)
        k = REGIME[t["regime"]][0]
        lab = short_ruler(t["ruler"])
        txt = ""
        if w >= 9:
            txt = (f'<text class="tl {k}" transform="translate({x + w / 2 + 3.5:.1f},122) rotate(-90)">{esc(lab[:22])}</text>')
        out.append(f'<a href="#{t["_sid"]}"><rect class="term {k}" x="{x:.1f}" y="16" width="{w:.1f}" height="110">'
                   f'<title>{esc(t["ruler"])}, {years_txt(t)} ({esc(t["regime"])})</title></rect>{txt}</a>')
    out.append(svg_close(h))
    return "".join(out)


# =============================================================== case ticks
def tick_rows(items, y0, y1, xf, wdt, h, cls, href, label):
    by = collections.defaultdict(list)
    for it in items:
        by[it["_y"]].append(it)
    out = []
    step = 6
    for y, its in sorted(by.items()):
        if not (y0 <= y <= y1):
            continue
        for i, it in enumerate(sorted(its, key=lambda c: c["id"])):
            yy = h - 4 - (i + 1) * step
            out.append(f'<a href="{href(it)}"><rect class="{cls}" x="{xf(y) + 0.4:.1f}" y="{yy + 1}" width="{wdt:.1f}" height="{step - 1.5}">'
                       f'<title>{esc(label(it))}</title></rect></a>')
    return "".join(out), max((len(v) for k, v in by.items() if y0 <= k <= y1), default=0)


def cases_svg():
    body, mx = tick_rows(CASES, Y0, Y1, X, PX - 0.8, 0, "tk", lambda c: f'index.html#{c["id"]}',
                         lambda c: f'{c["_y"]} · {c["id"]}: {c["title"]}')
    h = mx * 6 + 10
    body, _ = tick_rows(CASES, Y0, Y1, X, PX - 0.8, h, "tk", lambda c: f'index.html#{c["id"]}',
                        lambda c: f'{c["_y"]} · {c["id"]}: {c["title"]}')
    return svg_open(h, "Transfer cases by start year") + frame(h) + body + svg_close(h), h


def dis_svg():
    items = [d for d in DIS if d["_y"]]
    body, mx = tick_rows(items, Y0, Y1, X, PX - 0.8, 0, "dk", lambda d: f'disasters.html#{d["id"]}',
                         lambda d: f'{d.get("date")} · {d.get("name")}')
    h = mx * 6 + 8
    body, _ = tick_rows(items, Y0, Y1, X, PX - 0.8, h, "dk", lambda d: f'disasters.html#{d["id"]}',
                        lambda d: f'{d.get("date")} · {d.get("name")}')
    return svg_open(h, "Disasters by year") + frame(h) + body + svg_close(h), h


def colony_svg():
    c0, c1, cpx, cl = 1500, 1822, 2.6, 30
    wc = round(cl + (c1 - c0 + 1) * cpx + 14)
    items = [c for c in CASES if c["_y"] < 1822]

    def xc(y):
        return cl + (y - c0) * cpx
    body, mx = tick_rows(items, c0, c1, xc, cpx + 1.4, 0, "tk", lambda c: "", lambda c: "")
    h = max(mx, 3) * 6 + 24
    body, _ = tick_rows(items, c0, c1, xc, cpx + 1.4, h - 14, "tk", lambda c: f'index.html#{c["id"]}',
                        lambda c: f'{c["_y"]} · {c["id"]}: {c["title"]}')
    ax = "".join(f'<line class="grid g50" x1="{xc(y):.1f}" x2="{xc(y):.1f}" y1="0" y2="{h - 14}"/>'
                 f'<text class="xl" x="{xc(y):.1f}" y="{h - 3}">{y}</text>' for y in range(1500, 1830, 50))
    ax += f'<line class="indep" x1="{xc(1822):.1f}" x2="{xc(1822):.1f}" y1="0" y2="{h - 14}"/>'
    return (f'<svg class="colony" viewBox="0 0 {wc} {h}" width="{wc}" height="{h}" role="img" aria-label="Colony-era cases 1500-1822">'
            f'{ax}{body}</svg>'), len(items)


def axis_svg():
    h = 18
    out = [f'<svg class="trk" viewBox="0 0 {W} {h}" width="{W}" height="{h}" aria-hidden="true">']
    for y in range(1830, Y1 + 1, 10):
        if y % 20 == 0:
            out.append(f'<text class="xl" x="{X(y):.1f}" y="13">{y}</text>')
    out.append(svg_close(h))
    return "".join(out)


# =============================================================== panels
PANELS = [
    ("tl-patrimony", "3. Public patrimony", [
        track("tr-invest", "Public investment", "% of GDP", [
            dict(id="public-investment-public-sector-pct-gdp", short="Whole public sector (government + federal SOEs)"),
            dict(id="public-investment-soe-pct-gdp", short="Federal state-owned companies (SOEs)")], 0, 12,
            ticks=[0, 4, 8, 12], note="A flow of investment, not a stock of assets. SOE investment also falls after privatizations, because sold firms leave the count (method note)."),
        track("tr-priv", "Privatization result per year (sale receipts + debt transferred)", "US$ bn, nominal", [
            dict(id="privatization-result-annual-usd-bn-1991-2002", short="Federal + state programmes", mode="bars")], 0, 40, h=70,
            ticks=[0, 20, 40], note="Totals: US$ 105.3 bn for 1990–2002 (federal + state); federal PND US$ 63.7 bn for 1990–2015. No yearly figures after 2002 in the data."),
        track("tr-soe", "Number of federal state-owned companies: four counting bases, never joined", "companies", [
            dict(id="federal-soe-count-dest-1980-2011", short="DEST series", mode="points"),
            dict(id="federal-soe-count-ipea-1995", short="SEST, cited by Ipea", mode="points"),
            dict(id="federal-soe-count", short="Sest registry (EEF)", mode="points"),
            dict(id="federal-soe-count-sest-active-2021-2022", short="Active under Sest (incl. subsidiaries)", mode="points")], 0, 250, h=70,
            ticks=[0, 125, 250]),
        track("tr-debt", "Public debt: two series that are not comparable", "% of GDP", [
            dict(id="hist-federal-internal-debt-pct-gdp", short="Federal internal debt, gross (historical)"),
            dict(id="dlsp-pct-gdp", short="Public sector net debt (DLSP)")], 0, 70, ticks=[0, 35, 70]),
    ]),
    ("tl-purchasing", "4. Purchasing power", [
        track("tr-wage", "Real minimum wage and household income per person", "R$ per month (wage at Sep 2026 prices; household income at 2025 prices)", [
            dict(id="min-wage-real", short="Real monthly minimum wage"),
            dict(id="household-income-per-capita", short="Mean household income per person (PNAD)")], 0, 2400, ticks=[0, 800, 1600, 2400]),
        track("tr-gdppc", "GDP per person, long run (Maddison)", "2011 US$, PPP", [
            dict(id="gdp-per-capita-maddison", short="Real GDP per person")], 0, 16000, ticks=[0, 8000, 16000],
            note="The World Bank series (constant 2015 US$) uses another base and is not drawn on this axis."),
    ]),
    ("tl-concentration", "5. Concentration of income and wealth", [
        track("tr-gini", "Income inequality (Gini): three survey series, not joined", "Gini, 0–100", [
            dict(id="income-gini-pnad-ipea-1995-2025", short="IPEA, harmonised PNAD"),
            dict(id="income-gini-pnad-old-1976-2014", short="Old PNAD (0–1 scale)", scale=100),
            dict(id="income-gini-worldbank-1981-2024", short="World Bank")], 45, 65, ticks=[45, 55, 65],
            note="Surveys miss top incomes, so these Ginis are lower than tax-based estimates."),
        track("tr-top", "Share of the top 1% and top 10%", "% of national income or of personal wealth", [
            dict(id="top1-income-share-wid-2001-2024", short="Top 1%, income"),
            dict(id="top10-income-share-wid-2001-2024", short="Top 10%, income"),
            dict(id="top1-income-share-wid-modelled-1920-1970", short="Top 1%, income, modelled", cls="c1", mode="points"),
            dict(id="top10-income-share-wid-modelled-1920-1970", short="Top 10%, income, modelled", cls="c2", mode="points"),
            dict(id="top10-wealth-share-wid-1920-2024", short="Top 10%, wealth (imputed)", cls="c3")], 0, 85, h=100,
            ticks=[0, 40, 80], note="Wealth shares are imputed. The drop between 1970 and 1980 is a change of method, not a real fall, so the line is broken there."),
        track("tr-land", "Inequality of farmland among farms", "Gini, 0–1", [
            dict(id="land-gini-establishments-1975-2017", short="Land Gini (agricultural censuses)", mode="points")], 0.80, 0.90, h=60,
            ticks=[0.8, 0.85, 0.9]),
        track("tr-labour", "Labour share of GDP", "share of GDP, 0–1", [
            dict(id="labour-share-pwt-1950-2023", short="Labour share (Penn World Table)")], 0.40, 0.65, h=70, ticks=[0.4, 0.5, 0.6]),
    ]),
    ("tl-political", "6. Political power", [
        track("tr-vdem", "Electoral democracy (V-Dem)", "index, 0 (low) to 1 (high)", [
            dict(id="vdem-electoral-democracy", short="V-Dem electoral democracy index")], 0, 1, ticks=[0, 0.5, 1],
            note="Expert-coded; the uncertainty bands are not drawn."),
        track("tr-voters", "Who could choose: registered voters", "% of total population", [
            dict(id="electorate-pct-population-ibge", short="IBGE, census years", mode="points"),
            dict(id="electorate-pct-population-derived", short="Derived and secondary", mode="points")], 0, 80, h=70, ticks=[0, 40, 80]),
        track("tr-corp", "Company money in campaigns", "% of candidate receipts", [
            dict(id="campaign-donations-corporate-share", short="Companies' direct share", mode="points"),
            dict(id="campaign-donations-corporate-share-2002-heuristic", short="2002, heuristic", mode="points")], 0, 70, h=60,
            ticks=[0, 35, 70], note="A lower bound: money passed through parties and other candidates is not traced. Company donations were banned after 2015."),
    ]),
]

cases_s, _ = cases_svg()
dis_s, _ = dis_svg()
colony_s, n_colony = colony_svg()

panel_html = [
    f'<div class="ph" id="tl-terms"><span class="pt">1. Terms of power</span> <span class="muted small">Colour = regime. Click a term to open its scorecard.</span></div>'
    + axis_svg() + terms_band(),
    f'<div class="ph" id="tl-cases"><span class="pt">2. Transfer cases and disasters</span> <span class="muted small">'
    f'Each dark tick is one case, by start year (links to the main page). The light row below is disasters (links to the disasters page).</span></div>'
    + cases_s + '<div class="cap"><span class="cu">Disasters by year</span></div>' + dis_s,
]
for pid, title, tracks in PANELS:
    panel_html.append(f'<div class="ph" id="{pid}"><span class="pt">{esc(title)}</span></div>' + "".join(tracks))
panel_html.append(axis_svg())

legend_regimes = " ".join(f'<span class="rpill {k}">{esc(lab)}</span>' for k, lab in REGIME.values())

# =============================================================== indicators per term
IND = [
    ("Real minimum wage", ["min-wage-real"]),
    ("Income Gini", ["income-gini-pnad-ipea-1995-2025", "income-gini-pnad-old-1976-2014", "income-gini-worldbank-1981-2024"]),
    ("SOE investment", ["public-investment-soe-pct-gdp"]),
    ("Public debt", ["dlsp-pct-gdp", "hist-federal-internal-debt-pct-gdp"]),
    ("Electoral democracy (V-Dem)", ["vdem-electoral-democracy"]),
]


def near(pts, y, order):
    for d in order:
        if y + d in pts:
            return y + d
    return None


def ind_change(t, sids):
    sy, ey = td.term_ref_years(t)
    for sid in sids:
        pts = S[sid]["_pts"]
        a = near(pts, sy, (0, 1, -1, 2, -2))
        if t["_open"]:
            later = [y for y in pts if y > (a or 9999)]
            b = max(later) if later else None
        else:
            b = near(pts, ey, (0, -1, 1, -2, 2))
        if a is not None and b is not None and b > a:
            return sid, a, b
        if a is not None and b is not None and b == a:
            return sid, a, None
    return None


def ind_rows(t):
    rows = []
    for name, sids in IND:
        r = ind_change(t, sids)
        if not r:
            rows.append(f'<tr><td>{esc(name)}</td><td colspan="3" class="muted">no data</td></tr>')
            continue
        sid, a, b = r
        s = S[sid]
        lab = f'{esc(name)}<br><span class="muted small">{esc(s["unit"])} · {src(s["source_url"], "source", s["label"])}'
        lab += (f' · {pill(s["status"])}' if s["status"] != "verified" else "") + "</span>"
        va = s["_pts"][a]
        if b is None:
            rows.append(f'<tr><td>{lab}</td><td>{fmt(va)} <span class="muted">({a})</span></td><td class="muted">term too short</td><td></td></tr>')
            continue
        vb = s["_pts"][b]
        dv = vb - va
        arrow = "▲" if dv > 0 else ("▼" if dv < 0 else "=")
        to_date = " to date" if t["_open"] else ""
        rows.append(f'<tr><td>{lab}</td><td>{fmt(va)} <span class="muted">({a})</span></td>'
                    f'<td>{fmt(vb)} <span class="muted">({b}{to_date})</span></td><td class="nw">{arrow} {("+" if dv > 0 else "")}{fmt(dv)}</td></tr>')
    return ("<div class=\"tw\"><table class=\"ind\"><thead><tr><th>Indicator</th><th>Start</th><th>End</th><th>Change</th></tr></thead><tbody>"
            + "".join(rows) + "</tbody></table></div>")


def voters_txt(t):
    sy, ey = td.term_ref_years(t)
    ey = ey or 2026
    best = None
    for sid in ("electorate-pct-population-ibge", "electorate-pct-population-derived"):
        for y, v in S[sid]["_pts"].items():
            if sy - 2 <= y <= ey + 2:
                dist = 0 if sy <= y <= ey else min(abs(y - sy), abs(y - ey))
                if best is None or dist < best[0]:
                    best = (dist, sid, y, v)
    if not best:
        return '<span class="muted">no data on registered voters for these years</span>'
    _, sid, y, v = best
    s = S[sid]
    return f'Registered voters: <strong>{fmt(v)}% of the population</strong> ({y}) {pill(s["status"])} {src(s["source_url"], "source", s["label"])}'


def vdem_txt(t):
    r = ind_change(t, ["vdem-electoral-democracy"])
    if not r:
        return '<span class="muted">no data</span>'
    sid, a, b = r
    p = S[sid]["_pts"]
    if b is None:
        return f'V-Dem electoral democracy <strong>{fmt(p[a])}</strong> ({a}), on a 0–1 scale'
    return f'V-Dem electoral democracy <strong>{fmt(p[a])}</strong> ({a}) to <strong>{fmt(p[b])}</strong> ({b}), on a 0–1 scale'


# =============================================================== people cards
SHOWN = set()


def person_card(pid, place):
    p = PEOPLE[pid]
    aid = td.person_anchor(pid, place)
    main = ""
    if pid not in SHOWN:
        SHOWN.add(pid)
        main = f'<span id="{esc(pid)}"></span>'
    posts = []
    for x in p["posts"]:
        st, en = x.get("start"), x.get("end")
        dates = f'{esc(st) if st not in (None, "") else "?"} to {esc(en) if en not in (None, "") else "?"}'
        if st in (None, "") and en in (None, ""):
            dates = "dates not given"
        ap = f' · appointed by: {esc(x.get("appointed_by"))}' if x.get("appointed_by") else ""
        posts.append(f'<li>{pill(x.get("status"))} <strong>{esc(x.get("post"))}</strong> <span class="muted">({dates})</span>{ap}</li>')
    parts = [f'<h5>Posts</h5><ul class="pl">{"".join(posts) or "<li class=muted>none recorded</li>"}</ul>']
    ba = []
    for fld, lab in (("before", "Before"), ("after", "After")):
        if p[fld]:
            ba.append(f'<p><strong>{lab}:</strong> {" · ".join(esc(v) for v in p[fld])}</p>')
    if ba:
        parts.append("".join(ba))
    if p["foreign_ties"]:
        parts.append('<h5>Foreign and private ties</h5><ul class="pl">' + "".join(
            f'<li>{pill(x.get("status"))} <strong>{esc(x.get("counterpart"))}</strong> <span class="muted">({esc(x.get("kind"))})</span>: {esc(x.get("detail"))} {src(x.get("source_url"))}</li>'
            for x in p["foreign_ties"]) + "</ul>")
    if p["case_links"]:
        cl = []
        for x in sorted(p["case_links"], key=lambda x: (CASE.get(x["case_id"], {}).get("_y", 0), x["case_id"])):
            b = td.BASIS_TEXT.get(x.get("basis"), x.get("basis"))
            cls = "acted" if x.get("basis") == "documented-act" else "inoff"
            cl.append(f'<li>{pill(x.get("status"))} <span class="basis {cls}">{esc(b)}</span> {case_a(x["case_id"], x["case_id"] + ": " + CASE[x["case_id"]]["title"] if x["case_id"] in CASE else None)}'
                      f'<br><span class="small">{esc(x.get("role"))}. {esc(x.get("detail"))} {src(x.get("source_url"))}</span></li>')
        parts.append(f'<h5>Cases</h5><ul class="pl">{"".join(cl)}</ul>')
    if p["controversies"]:
        parts.append('<h5>Investigations and their outcome</h5><ul class="pl">' + "".join(
            f'<li>{pill(x.get("status"))} {esc(x.get("what"))}<br><strong>Outcome:</strong> {esc(x.get("outcome"))} {src(x.get("source_url"))}</li>'
            for x in p["controversies"]) + "</ul>")
    srcs = [s for s in p["sources"] if url_ok(s.get("url"))]
    if srcs:
        parts.append('<p class="small muted">Sources: ' + " · ".join(src(s["url"], s.get("title") or s["url"]) for s in srcs) + "</p>")
    # posts overlapping this place, for the summary line
    if place != td.COLONY:
        t = TID[place]
        ov = [x for x in p["posts"] if (sp := td.post_span(x)) and sp[0] <= t["_end"] and sp[1] >= t["_start"]]
    else:
        ov = []
    head = ", ".join(esc(x["post"]) for x in (ov or p["posts"])[:2])
    n_ver = sum(1 for x in p["posts"] if x.get("status") == "verified")
    tag = ' <span class="flag">linked through a case only</span>' if pid in D["added_by_case"] else ""
    flags = []
    if any(x.get("basis") == "documented-act" for x in p["case_links"]):
        flags.append('<span class="basis acted">acted in a case</span>')
    if p["controversies"]:
        flags.append(f'<span class="flag">{len(p["controversies"])} investigation{"s" if len(p["controversies"]) > 1 else ""}</span>')
    return (f'<details class="person" id="{esc(aid)}">{main}<summary>{pill(p["_status"], str(n_ver) + " of " + str(len(p["posts"])) + " posts verified")} '
            f'<strong>{esc(p["name"])}</strong> <span class="muted">· {head}</span> {" ".join(flags)}{tag}</summary>'
            f'<div class="pbody">{"".join(parts)}</div></details>')


def term_cases(place):
    cs = sorted([c for c in CASES if CT[c["id"]] == place], key=lambda c: (c["_y"], c["id"]))
    if not cs:
        return '<p class="muted">No transfer case in the data starts in this term.</p>', cs
    items = []
    for c in cs:
        ppl = CP.get(c["id"], [])
        if ppl:
            who = "; ".join(
                f'<a href="#{td.person_anchor(pid, place) if pid in TP.get(place, []) else td.person_anchor(pid, D["first_place"][pid])}">{esc(PEOPLE[pid]["name"])}</a> '
                f'<span class="basis {"acted" if l["basis"] == "documented-act" else "inoff"}">{esc(td.BASIS_TEXT[l["basis"]])}</span>'
                for pid, l in ppl)
        else:
            who = '<span class="muted">no person linked in the data</span>'
        items.append(f'<li><span class="muted">{c["_y"]}</span> {case_a(c["id"], c["id"] + ": " + c["title"])}<br><span class="small">{who}</span></li>')
    return f'<ul class="cl">{"".join(items)}</ul>', cs


def term_foreign(cs):
    ids = {c["id"] for c in cs}
    fx = [f for f in FC if f["case_id"] in ids]
    if not fx:
        return '<p class="muted">No foreign counterpart recorded for these cases.</p>'
    return '<ul class="pl">' + "".join(
        f'<li>{pill(f.get("status"))} <strong>{esc(f["counterpart"])}</strong> <span class="muted">({esc(f["country"])}, {esc(f["kind"])})</span> '
        f'in {case_a(f["case_id"], f["case_id"])}: {esc(f["detail"])} {src(f.get("source_url"))}</li>' for f in fx) + "</ul>"


# =============================================================== deals ledger
DEAL = td.deal_places(TERMS, CASES, CT)
DIS_BY_ID = {d["id"]: d for d in DIS}
DMATCH = td.match_disasters(CASES, DIS)
with open(os.path.join(ROOT, "disasters.html"), encoding="utf-8") as _fh:
    DIS_PAGE_IDS = set(__import__("re").findall(r'\bid="([^"]+)"', _fh.read()))
FOLLOW = collections.defaultdict(list)   # case id -> [(disaster, later?, note)]
for _did, (_cid, _how, _det) in DMATCH.items():
    if not _cid:
        continue
    _d = DIS_BY_ID[_did]
    _later = _d["_y"] is not None and _d["_y"] >= CASE[_cid]["_y"]
    _note = None
    if _did in td.DIS_AFTER_OVERRIDES:
        _later, _note = True, td.DIS_AFTER_OVERRIDES[_did]
    FOLLOW[_cid].append((_d, _later, _note))
for _v in FOLLOW.values():
    _v.sort(key=lambda x: (x[0]["_y"] or 0, x[0]["id"]))
SAME_OF = collections.defaultdict(list)
for _x, _e in td.SAME_DEAL.items():
    SAME_OF[_e].append(_x)

print("Deals ledger: disaster links")
for _did, (_cid, _how, _det) in DMATCH.items():
    print(f"  {_how:9s} {_did} -> {_cid or '-'}  ({_det})")
_unm = [k for k, v in DMATCH.items() if not v[0]]
print(f"  matched {len(DMATCH) - len(_unm)} of {len(DMATCH)}; not linked: {', '.join(_unm)}")
print("  left out as not deals: " + "; ".join(f"{k} ({v})" for k, v in td.NOT_DEALS.items()))

MONEY = ("BRL", "USD", "R$", "US$", "GBP", "réis", "reis", "cruz", "contos", "pounds", "Cr$")


def fig_pill(st, note=None):
    st = st if st in ("verified", "unverified", "corrected", "disputed") else "unverified"
    t = f' title="{esc(note)}"' if note else ""
    return f'<span class="pill s-{st}"{t}>{st}</span>'


def key_figure(c):
    figs = c.get("figures") or []
    money = [f for f in figs if any(m in str(f.get("currency") or "") for m in MONEY) and not isinstance(f.get("value"), str)]
    pick = next((f for f in money if f.get("kind") != "other"), None) or (money[0] if money else None) or (figs[0] if figs else None)
    if not pick:
        return '<span class="muted">no figure</span>'
    v = pick.get("value")
    cur = pick.get("currency") or ""
    vs = (f"{v:,}" if isinstance(v, (int, float)) else esc(v)) + (f" {esc(cur)}" if cur and cur not in ("n/a", "other") else "")
    return f'{esc(pick.get("label"))}: <strong>{vs}</strong> {fig_pill(pick.get("status"), pick.get("note"))}'


def first_sentence(s, n=170):
    s = (s or "").strip()
    if not s:
        return '<span class="muted">not stated</span>'
    m = __import__("re").match(r"(.+?[.;])(\s|$)", s)
    cut = m.group(1) if m else s
    if len(cut) > n:
        cut = cut[:n].rsplit(" ", 1)[0] + "…"
    return f'<span title="{esc(s)}">{esc(cut)}</span>'


def deaths_txt(d):
    n = td.deaths_count(d.get("deaths"))
    if n is None:
        return '<span class="muted">no count</span>'
    return "none recorded" if n == 0 else f"{n:,} dead"


def dis_a(d):
    name = esc(d.get("name"))
    return f'<a href="disasters.html#{esc(d["id"])}">{name}</a>' if d["id"] in DIS_PAGE_IDS else name


def followed_html(cid):
    items = FOLLOW.get(cid, [])
    if not items:
        return '<span class="muted">none linked</span>'
    later = [x for x in items if x[1]]
    before = [x for x in items if not x[1]]
    out = []
    if later:
        out.append('<ul class="fl">' + "".join(
            f'<li>{dis_a(d)} <span class="muted">({d["_y"]}; {deaths_txt(d)})</span>'
            + (f' <span class="small muted">{esc(note)}</span>' if note else "") + "</li>" for d, _l, note in later) + "</ul>")
    if before:
        out.append('<p class="small muted">Linked in the data, dated before the deal (not counted): '
                   + "; ".join(f'{dis_a(d)} ({d["_y"]})' for d, _l, _n in before) + "</p>")
    return "".join(out) or '<span class="muted">none linked</span>'


def decided_html(cid):
    ppl = CP.get(cid, [])
    if not ppl:
        return '<span class="muted">no person linked</span>'
    parts = []
    for pid, l in ppl:
        tgt = td.person_link_target(pid, cid, D)
        nm = esc(PEOPLE[pid]["name"])
        a = f'<a href="#{esc(tgt)}">{nm}</a>' if tgt else nm
        parts.append(f'{a} <span class="basis {"acted" if l["basis"] == "documented-act" else "inoff"}">{esc(td.BASIS_TEXT[l["basis"]])}</span>')
    return "; ".join(parts)


TERM_DEALS = collections.defaultdict(list)    # place -> [(year, case, note)]
TERM_ONGOING = collections.defaultdict(list)  # place -> [case]
for c in CASES:
    status, places = DEAL[c["id"]]
    if status == "deal":
        for place, y, note in places:
            TERM_DEALS[place].append((y, c, note))
    elif status == "ongoing":
        TERM_ONGOING[places[0][0]].append(c)
for _p in TERM_DEALS:
    TERM_DEALS[_p].sort(key=lambda x: (x[0], x[1]["id"]))


def term_totals(place):
    rows = TERM_DEALS.get(place, [])
    seen = {}
    for _y, c, _n in rows:
        for d, later, _note in FOLLOW.get(c["id"], []):
            if later:
                seen[d["id"]] = d
    counts = [td.deaths_count(d.get("deaths")) for d in seen.values()]
    deaths = sum(n for n in counts if n)
    nocount = sum(1 for n in counts if n is None)
    return len(rows), len(seen), deaths, nocount


def totals_bar(place):
    n, nd, deaths, nocount = term_totals(place)
    nc = f", {nocount} with no death count" if nocount else ""
    return (f'<p class="tot"><span class="muted small">Counts, not a score:</span> <b>{n}</b> deal{"s" if n != 1 else ""} signed · '
            f'<b>{nd}</b> later disaster{"s" if nd != 1 else ""} linked · <b>{deaths:,}</b> deaths recorded{nc}</p>')


def ledger_table(place):
    rows = TERM_DEALS.get(place, [])
    if not rows:
        return '<p class="muted small">No signed deal in the data for this term.</p>'
    trs = []
    for y, c, note in rows:
        same = f' <span class="small muted">(same deal: {", ".join(case_a(x, x) for x in SAME_OF[c["id"]])})</span>' if SAME_OF.get(c["id"]) else ""
        nt = f'<br><span class="small muted">{esc(note)}</span>' if note else ""
        trs.append(f'<tr><td class="nw">{y}</td><td>{case_a(c["id"], c["id"] + ": " + c["title"])}{same}{nt}</td>'
                   f'<td>{first_sentence(c.get("who_got"))}</td><td>{first_sentence(c.get("who_paid"))}</td>'
                   f'<td>{key_figure(c)}</td><td class="small">{decided_html(c["id"])}</td><td class="small">{followed_html(c["id"])}</td></tr>')
    return ('<div class="tw"><table class="ledger"><thead><tr><th>Year</th><th>Deal</th><th>Who got</th><th>Who paid</th>'
            '<th>Key figure</th><th>Decided by</th><th>Followed by</th></tr></thead><tbody>' + "".join(trs) + "</tbody></table></div>")


def ongoing_line(place):
    cs = TERM_ONGOING.get(place, [])
    if not cs:
        return ""
    return ('<p class="small"><strong>Ongoing under this term</strong> <span class="muted">(long processes with no single signing act, not counted as deals)</span>: '
            + "; ".join(f'{case_a(c["id"], c["id"] + ": " + c["title"])} <span class="muted">({esc(c["year"])})</span>' for c in cs) + "</p>")


def term_ledger(place):
    """Ledger rows for one term, used inside the term's details block (no ids, to avoid duplicates)."""
    return f'<h4>Deals signed</h4>{totals_bar(place)}{ledger_table(place)}{ongoing_line(place)}'


term_secs = []
n_term_people = 0
for t in TERMS:
    pids = TP.get(t["id"], [])
    n_term_people += len(pids)
    ctext, cs = term_cases(t["id"])
    people_html = "".join(person_card(pid, t["id"]) for pid in pids) or '<p class="muted">No decision-makers mapped for this term in the people files.</p>'
    interim = ' <span class="flag">interim</span>' if t.get("interim") else ""
    srcs = " · ".join(src(s["url"], s["title"]) for s in t.get("sources") or [] if url_ok(s.get("url")))
    sc = (
        '<div class="tw"><table class="score"><tbody>'
        f'<tr><th scope="row">1. Who ruled, and how</th><td>{esc(t["ruler"])}, {esc(t["title"])}. {esc(t["how_came_to_power"])} <strong>Left:</strong> {esc(t["how_left"])}.</td></tr>'
        f'<tr><th scope="row">2. Who could choose them</th><td>{voters_txt(t)}</td></tr>'
        f'<tr><th scope="row">3. Who backed them</th><td>{esc(t["party_or_base"])} <span class="muted">Seats in Congress: no data.</span></td></tr>'
        f'<tr><th scope="row">4. What checked them</th><td>{vdem_txt(t)}</td></tr>'
        f'<tr><th scope="row">5. What they handed over</th><td><strong>{len(cs)}</strong> case{"s" if len(cs) != 1 else ""} started in this term (list below)</td></tr>'
        f'<tr><th scope="row">6. Who gained or lost</th><td>See the indicator change below.</td></tr>'
        '</tbody></table></div>')
    note = f'<p class="small muted">{esc(t["notes"])}</p>' if t.get("notes") else ""
    term_secs.append(
        f'<section id="{t["_sid"]}" class="term-sec"><details class="term-d"><summary><h3 id="{t["_sid"]}-h">{esc(t["ruler"])} <span class="muted small">{years_txt(t)}</span></h3> {regime_pill(t["regime"])}{interim} <span class="small muted">{len(pids)} decision-maker{"s" if len(pids) != 1 else ""}, {len(cs)} case{"s" if len(cs) != 1 else ""}</span></summary>'
        f'<p><span class="small muted">{esc(t["start"])} to {esc(t["end"] or "today")}</span></p>'
        f'{sc}{note}'
        f'<h4>Indicator change, start to end of term</h4>{ind_rows(t)}'
        f'<h4>Decision-makers ({len(pids)})</h4>{people_html}'
        f'{term_ledger(t["id"])}'
        f'<h4>Cases that started in this term</h4>{ctext}'
        f'<h4>Foreign counterparts in these cases</h4>{term_foreign(cs)}'
        f'<p class="small muted">Term sources: {srcs or "none"}</p></details></section>')

# colony block
col_ctext, col_cs = term_cases(td.COLONY)
col_groups = []
for label, pids in D["colony_groups"]:
    col_groups.append(f'<h4>{esc(label)}</h4>' + "".join(
        person_card(pid, td.COLONY) if td.person_anchor(pid, td.COLONY) not in "".join(col_groups)
        else f'<p class="small">{esc(PEOPLE[pid]["name"])}: see <a href="#{td.person_anchor(pid, td.COLONY)}">above</a>.</p>'
        for pid in pids))
n_col_people = len({pid for _l, pids in D["colony_groups"] for pid in pids})
colony_sec = (
    f'<section id="term-colony" class="term-sec"><details class="term-d"><summary><h3 id="term-colony-h">Before independence: Portuguese crown, 1500–1822</h3> <span class="small muted">{n_col_people} decision-makers, {len(col_cs)} cases</span></summary>'
    f'<p class="muted">terms.json starts in 1822, so the crown years have no scorecard or indicators. The people files still map decision-makers for them.</p>'
    f'{"".join(col_groups)}{term_ledger(td.COLONY)}<h4>Cases that started before independence</h4>{col_ctext}'
    f'<h4>Foreign counterparts in these cases</h4>{term_foreign(col_cs)}</details></section>')

# =============================================================== both sides
MOVE_KEYS = ("employer", "board", "consultant", "investor", "client", "co-founder", "lawyer/adviser")


def is_move(kind):
    k = (kind or "").lower()
    return any(m in k for m in MOVE_KEYS)


def gov_posts(p):
    return "; ".join(f'{esc(x["post"])} <span class="muted">({esc(x.get("start") or "?")}–{esc(x.get("end") or "?")})</span>' for x in p["posts"][:3])


both_v, both_u = [], []
for pid, p in PEOPLE.items():
    for x in p["foreign_ties"]:
        row = (f'<tr><td><a href="#{td.person_anchor(pid, D["first_place"][pid])}">{esc(p["name"])}</a></td><td class="small">{gov_posts(p)}</td>'
               f'<td><strong>{esc(x["counterpart"])}</strong><br><span class="muted small">{esc(x["kind"])}</span></td>'
               f'<td class="small">{esc(x["detail"])}</td><td>{pill(x["status"])} {src(x.get("source_url"))}</td></tr>')
        if x["status"] == "verified" and is_move(x["kind"]):
            both_v.append((p["name"], row))
        elif x["status"] != "verified":
            both_u.append((p["name"], row))
both_v.sort()
n_both_people = len({n for n, _ in both_v})

# =============================================================== foreign by country
ALIAS = {"US": "United States", "USA": "United States", "multiple": "Multiple", "multilateral": "Multilateral"}


def countries(s):
    out = []
    for part in s.split("/"):
        p = ALIAS.get(part.strip(), part.strip())
        if p and p not in out:
            out.append(p)
    return out


by_country = collections.defaultdict(list)
for f in FC:
    for ctry in countries(f["country"]):
        by_country[ctry].append(f)
cty_ids = {}
for_secs = []
for ctry, fs in sorted(by_country.items(), key=lambda kv: (-len(kv[1]), kv[0])):
    cid = "fc-" + "".join(ch if ch.isalnum() else "-" for ch in ctry.lower()).strip("-")
    while "--" in cid:
        cid = cid.replace("--", "-")
    cty_ids[ctry] = cid
    fs = sorted(fs, key=lambda f: CASE.get(f["case_id"], {}).get("_y", 0))
    rows = "".join(
        f'<tr><td class="nw">{CASE[f["case_id"]]["_y"] if f["case_id"] in CASE else ""}</td><td>{case_a(f["case_id"], f["case_id"] + ": " + CASE[f["case_id"]]["title"] if f["case_id"] in CASE else None)}</td>'
        f'<td><strong>{esc(f["counterpart"])}</strong><br><span class="muted small">{esc(f["kind"])}{" · listed as " + esc(f["country"]) if f["country"] != ctry else ""}</span></td>'
        f'<td class="small">{esc(f["detail"])}</td><td>{pill(f.get("status"))} {src(f.get("source_url"))}</td></tr>' for f in fs)
    for_secs.append(f'<h3 id="{cid}">{esc(ctry)} <span class="muted small">({len(fs)})</span></h3>'
                    f'<div class="tw"><table class="wide"><thead><tr><th>Year</th><th>Case</th><th>Counterpart</th><th>Detail</th><th>Status</th></tr></thead><tbody>{rows}</tbody></table></div>')

# =============================================================== answer numbers
def v(sid, y):
    return S[sid]["_pts"].get(y)


top_cty = ", ".join(f"<strong>{esc(c)}</strong> ({len(by_country[c])})" for c in sorted(by_country, key=lambda c: (-len(by_country[c]), c))[:3])
reg_cases = collections.Counter(TID[p]["regime"] if p != td.COLONY else "colony" for p in CT.values())
n_cases = len(CASES)
n_after_1990 = sum(1 for c in CASES if c["_y"] >= 1990)
priv = S["privatization-result-annual-usd-bn-1991-2002"]["_pts"]
priv_peak = max(priv.items(), key=lambda kv: kv[1])
top1 = [S["top1-income-share-wid-2001-2024"]["_pts"][y] for y in range(2003, 2015) if y in S["top1-income-share-wid-2001-2024"]["_pts"]]
soe_peak = max(S["public-investment-soe-pct-gdp"]["_pts"].items(), key=lambda kv: kv[1])
vd_mil = [v("vdem-electoral-democracy", y) for y in range(1965, 1985)]
cnt_9599 = sum(1 for c in CASES if 1995 <= c["_y"] <= 1999)
cnt_1621 = sum(1 for c in CASES if 2016 <= c["_y"] <= 2021)

answer = f'''<section id="answer"><h2 id="answer-h">What the timeline shows</h2>
<p class="lead"><strong>Transfers cluster in a few periods, and each period has a different mix</strong> of democracy, wages and inequality. These are patterns in time, <strong>not proof of motive</strong>.</p>
<ol class="ans">
<li><strong>Military rule, 1964–1985:</strong> democracy scores at their lowest (V-Dem {fmt(min(vd_mil))}–{fmt(max(vd_mil))}), state-company investment at its peak ({fmt(soe_peak[1])}% of GDP in {soe_peak[0]}), and the real minimum wage falling from R$ {fmt(v("min-wage-real", 1964))} (1964) to R$ {fmt(v("min-wage-real", 1984))} (1984).</li>
<li><strong>The 1990s sales:</strong> {cnt_9599} cases start in 1995–1999 and yearly privatization money peaks at US$ {fmt(priv_peak[1])} bn in {priv_peak[0]}, under high democracy scores (V-Dem {fmt(v("vdem-electoral-democracy", 1998))} in 1998). The real minimum wage was R$ {fmt(v("min-wage-real", 1995))} (1995) and R$ {fmt(v("min-wage-real", 1999))} (1999), the Gini stayed near {fmt(v("income-gini-pnad-ipea-1995-2025", 1998))}, and net public debt rose from {fmt(v("dlsp-pct-gdp", 1994))}% (1994) to {fmt(v("dlsp-pct-gdp", 2002))}% of GDP (2002).</li>
<li><strong>2003–2014:</strong> the survey Gini fell from {fmt(v("income-gini-pnad-ipea-1995-2025", 2003))} to {fmt(v("income-gini-pnad-ipea-1995-2025", 2014))} and the minimum wage rose to R$ {fmt(v("min-wage-real", 2014))}, while the top 1% kept {fmt(min(top1))}–{fmt(max(top1))}% of national income.</li>
<li><strong>2016–2021:</strong> {cnt_1621} cases start, V-Dem drops from {fmt(v("vdem-electoral-democracy", 2015))} (2015) to {fmt(v("vdem-electoral-democracy", 2020))} (2020), and net debt rises to {fmt(v("dlsp-pct-gdp", 2020))}% of GDP (2020).</li>
</ol>
<div class="callout warn"><strong>Correlation, not proof.</strong> Lines moving together in the same years do not show that one caused the other, or why anyone acted. Old eras also have thinner records: {n_after_1990} of {n_cases} cases start in 1990 or later.</div>
</section>'''

# =============================================================== deals section (top)
def term_block(place, title, href, hid):
    return (f'<h4 id="{hid}"><a href="#{href}">{title}</a></h4>{totals_bar(place)}{ledger_table(place)}{ongoing_line(place)}')


ERAS_D = [("deals-colony", "Before independence: Portuguese crown, 1500–1822", None, [td.COLONY])]
for t in TERMS:
    if ERAS_D[-1][2] != t["regime"] or ERAS_D[-1][0] == "deals-colony":
        ERAS_D.append((f'deals-{REGIME[t["regime"]][0][3:]}-{t["_start"].year}', None, t["regime"], []))
    ERAS_D[-1][3].append(t["id"])
era_html = []
deal_toc = []
for eid, etitle, reg, places in ERAS_D:
    if etitle is None:
        last = TID[places[-1]]
        etitle = f'{REGIME[reg][1]}, {TID[places[0]]["_start"].year}–{"today" if last["_open"] else last["_end"].year}'
    n_era = sum(len(TERM_DEALS.get(p, [])) for p in places)
    blocks, empty = [], []
    for p in places:
        if not TERM_DEALS.get(p) and not TERM_ONGOING.get(p):
            empty.append(p)
            continue
        if p == td.COLONY:
            blocks.append(term_block(p, "Portuguese crown, 1500–1822", "term-colony", "deals-in-colony"))
        else:
            t = TID[p]
            blocks.append(term_block(p, f'{esc(t["ruler"])} <span class="muted small">{years_txt(t)}</span>', t["_sid"], "deals-in-" + t["id"][2:]))
    if empty:
        blocks.append('<p class="small muted">No signed deal in the data: ' + ", ".join(
            f'<a href="#{TID[p]["_sid"]}">{esc(short_ruler(TID[p]["ruler"]))} {TID[p]["_start"].year}</a>' for p in empty) + ".</p>")
    era_html.append(f'<h3 id="{eid}">{esc(etitle)} <span class="muted small">({n_era} deal{"s" if n_era != 1 else ""})</span></h3>{"".join(blocks)}')
    deal_toc.append(f'<a href="#{eid}">{esc(etitle)}</a>')

_per_term = [len(TERM_DEALS.get(t["id"], [])) for t in TERMS]
_rank = sorted(((term_totals(t["id"])[2], t) for t in TERMS), key=lambda x: -x[0])[:3]
print(f"  deals per term: min {min(_per_term)}, max {max(_per_term)}, terms with zero {sum(1 for n in _per_term if n == 0)} of {len(TERMS)}; colony {len(TERM_DEALS.get(td.COLONY, []))}")
print("  most later deaths: " + "; ".join(f'{t["id"]} {n}' for n, t in _rank))
n_deal_rows = sum(len(v) for v in TERM_DEALS.values())
n_deal_cases = sum(1 for v in DEAL.values() if v[0] == "deal")
n_ongoing = sum(1 for v in DEAL.values() if v[0] == "ongoing")
n_linked = sum(1 for v in DMATCH.values() if v[0])
left_out = "; ".join(f'{case_a(k, k)}: {esc(v)}' for k, v in td.NOT_DEALS.items())
same_txt = "; ".join(f'{case_a(x, x)} is listed under {case_a(e, e)}' for x, e in td.SAME_DEAL.items())
unl = "; ".join(f'{dis_a(DIS_BY_ID[k])}: {esc(v[2]) if v[1] == "override" else "no case matched the text"}' for k, v in DMATCH.items() if not v[0])

# =============================================================== deals per term + later deaths (chart band)
def deals_band():
    """Bar per term: height = deals signed in that term (TERM_DEALS). Under it, one circle per term for the
    deaths in disasters later tied to those deals (term_totals); a hollow ring when the only tied disasters
    have no death count."""
    mx = max(_per_term) or 1
    hb, hd = 74, 44
    h = hb + hd
    out = [svg_open(h, "Deals signed per term, and deaths in disasters later tied to those deals"), frame(h)]
    out.append(f'<line class="base" x1="{L}" x2="{W - R}" y1="{hb - 2}" y2="{hb - 2}"/>')
    mxd = max(term_totals(t["id"])[2] for t in TERMS) or 1
    for t in TERMS:
        a, b_ = td.frac(t["_start"]), td.frac(t["_end"])
        x, w = X(a), max((b_ - a) * PX, 1.2)
        n, nd, deaths, nocount = term_totals(t["id"])
        tip = f'{t["ruler"]}, {years_txt(t)}: {n} deal{"s" if n != 1 else ""} signed'
        if n:
            bh = 4 + (hb - 22) * n / mx
            out.append(f'<a href="#deals-in-{t["id"][2:]}"><rect class="db" x="{x + .3:.1f}" y="{hb - 2 - bh:.1f}" width="{max(w - .6, 1):.1f}" height="{bh:.1f}"><title>{esc(tip)}</title></rect></a>')
            if n >= max(3, mx * .3):
                out.append(f'<text class="dbl" x="{x + w / 2:.1f}" y="{hb - 6 - bh:.1f}">{n}</text>')
        if nd:
            cx, cy = x + w / 2, hb + hd / 2
            dtip = f'{t["ruler"]}: {nd} later disaster{"s" if nd != 1 else ""} tied to deals of this term, {deaths:,} deaths recorded' + (f', {nocount} with no death count' if nocount else '')
            r = 3.5 + 14 * (deaths / mxd) ** .5 if deaths else 4
            out.append(f'<a href="#deals-in-{t["id"][2:]}"><circle class="ld{"" if deaths else " nc"}" cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}"><title>{esc(dtip)}</title></circle></a>')
            if deaths:
                out.append(f'<text class="ldl" x="{cx + r + 3:.1f}" y="{cy + 4:.1f}">{deaths:,}</text>')
    out.append(svg_close(h))
    return "".join(out)


_mx_deals = max(len(TERM_DEALS.get(t["id"], [])) for t in TERMS)
_top_deals = [t for t in TERMS if len(TERM_DEALS.get(t["id"], [])) == _mx_deals]
_top_txt = " and ".join(f'{esc(short_ruler(t["ruler"]))} {t["_start"].year}' for t in _top_deals)
_dead_terms = [t for t in TERMS if term_totals(t["id"])[1]]
FIG_DEALS = (f'<figure id="fig-deals-per-term" class="tlf"><div class="ph" id="tl-deals"><span class="pt">1b. Deals per term: most in {_top_txt} ({_mx_deals} each)</span> '
             f'<span class="muted small">'
             f'Bar height = deals signed in the term (long terms have room for more). Circle = deaths in disasters later tied to those deals '
             f'({len(_dead_terms)} terms); a hollow ring means no death count; each count keeps its own status on the disasters page. Click to open the term in the deals list. '
             f'Source: data/g1–g10, placed by the <a href="#deals-rules">deal rules</a>.</span></div>'
             + deals_band() + '</figure>')
panel_html.insert(1, FIG_DEALS)

deals = f'''<section id="deals"><h2 id="deals-h">What deals did each president sign, and what followed?</h2>
<p class="lead">Each row is a signed deal. 'Followed by' shows disasters later tied to that deal. A link is not proof of cause; read the chain.</p>
<p class="small muted">{n_deal_cases} deals over {n_deal_rows} rows (a deal with signing acts in two terms is listed under each, with that year). {n_ongoing} long processes are listed as "ongoing under" their start term. {n_linked} disasters are tied to a deal from their "linked transfer" text. Who got and who paid show the first sentence of the case; hover for the full text. Deaths are added up only where the data gives a number.</p>
<p class="small"><span class="basis acted">acted</span> = a source names the person acting in the case. <span class="basis inoff">in office at the time</span> = held the post; no source names them acting. Each figure keeps its status pill.</p>
<div class="callout"><strong>Jump to an era:</strong> {" · ".join(deal_toc)}</div>
{"".join(era_html)}
<details class="notes" id="deals-rules"><summary>How deals were placed, and what was left out</summary>
<ul class="small">
<li><strong>Term:</strong> the term in office on the signing date when the case text gives a full date in its start year and several terms held office that year; otherwise the term the case sits under below. Later signing acts in another term come from the case's own text.</li>
<li><strong>Not deals (left out):</strong> {left_out}.</li>
<li><strong>Listed once:</strong> {same_txt}.</li>
<li><strong>Disaster links:</strong> each disaster's "linked transfer" text was matched to case titles by word overlap, year and exact date, with a short hand-checked list for the rest. Disasters dated before their deal are shown but not counted.</li>
<li><strong>Disasters with a linked-transfer text but no deal here:</strong> {unl}.</li>
</ul></details>
</section>'''

# =============================================================== data for JS
term_js = [[round(td.frac(t["_start"]), 3), round(td.frac(t["_end"]), 3), t["ruler"], REGIME[t["regime"]][1], t["_sid"]] for t in TERMS]
case_js = collections.defaultdict(int)
for c in CASES:
    case_js[c["_y"]] += 1
dis_js = collections.defaultdict(int)
for d in DIS:
    if d["_y"]:
        dis_js[d["_y"]] += 1
TLD = {"L": L, "PX": PX, "y0": Y0, "y1": Y1, "series": READ, "terms": term_js, "cases": case_js, "dis": dis_js}
tl_json = json.dumps(TLD, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
# year panel data, only for the charts page: deals signed per year (deal rules above) and disasters per year
_yd = collections.defaultdict(dict)
for c in CASES:
    _st, _places = DEAL[c["id"]]
    if _st == "deal":
        for _pl, _y, _n in _places:
            _yd[_y][c["id"]] = c["title"]
_yx = collections.defaultdict(list)
for d in sorted(DIS, key=lambda d: d.get("date") or ""):
    if d["_y"]:
        _yx[d["_y"]].append([d["id"], d.get("name"), html.unescape(re.sub(r"<[^>]+>", "", deaths_txt(d)))])
TLD_CH = dict(TLD, charts=1, base="timeline.html", ydeals={y: [[k, v] for k, v in sorted(m.items())] for y, m in _yd.items()}, ydis=_yx)
tl_json_ch = json.dumps(TLD_CH, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

JS = r"""
(function(){
var D=JSON.parse(document.getElementById('tl-data').textContent);
var box=document.getElementById('tl-box'), rng=document.getElementById('tl-year');
var ref=box.querySelector('svg.trk'), cur=null;
function setYear(y){
  y=Math.max(D.y0,Math.min(D.y1,y|0)); if(y===cur) return; cur=y; rng.value=y;
  var x=D.L+(y-D.y0+0.5)*D.PX;
  box.querySelectorAll('line.xh').forEach(function(l){l.setAttribute('x1',x);l.setAttribute('x2',x);});
  document.getElementById('tl-y').textContent=y;
  var te=document.getElementById('tl-t'); te.textContent='';
  D.terms.filter(function(t){return t[0]<y+1&&t[1]>y;}).forEach(function(t,i){
    if(i) te.appendChild(document.createTextNode(', '));
    var a=document.createElement('a'); a.href=(D.base||'')+'#'+t[4]; a.textContent=t[2]; te.appendChild(a);
    te.appendChild(document.createTextNode(' ('+t[3]+')'));
  });
  var n=D.cases[y]||0, m=D.dis[y]||0;
  document.getElementById('tl-c').textContent=n+' case'+(n===1?'':'s')+' start · '+m+' disaster'+(m===1?'':'s');
  box.querySelectorAll('.rv').forEach(function(s){
    var v=(D.series[s.getAttribute('data-s')]||{})[y];
    s.textContent=(v===undefined)?'no data':v; s.classList.toggle('nd',v===undefined);
  });
  if(D.charts){panel(y);clearTimeout(ht);ht=setTimeout(function(){history.replaceState(null,'','#y'+y);},250);}
}
var ht=null;
function h(s){return String(s==null?'':s).replace(/[&<>"]/g,function(c){return{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];});}
function panel(y){
  var p=document.getElementById('tl-yp'); if(!p) return;
  var ts=D.terms.filter(function(t){return t[0]<y+1&&t[1]>y;});
  var dl=D.ydeals[y]||[], ds=D.ydis[y]||[];
  var o='<h3 id="tl-yp-h">'+y+'</h3><div class="ypc"><p><b>In power:</b> '+(ts.length?ts.map(function(t){return '<a href="'+D.base+'#'+h(t[4])+'">'+h(t[2])+'</a> <span class="muted small">('+h(t[3])+')</span>';}).join(', '):'<span class="muted">Portuguese crown (before 1822) or no term in the data</span>')+'</p></div>';
  o+='<div class="ypc"><p><b>Deals signed ('+dl.length+'):</b></p>'+(dl.length?'<ul>'+dl.map(function(c){return '<li><a href="index.html#'+h(c[0])+'">'+h(c[1])+'</a></li>';}).join('')+'</ul>':'<p class="muted small">None in the data this year.</p>')+'</div>';
  o+='<div class="ypc"><p><b>Disasters ('+ds.length+'):</b></p>'+(ds.length?'<ul>'+ds.map(function(d){return '<li><a href="disasters.html#'+h(d[0])+'">'+h(d[1])+'</a> <span class="muted small">'+h(d[2])+'</span></li>';}).join('')+'</ul>':'<p class="muted small">None in the data this year.</p>')+'</div>';
  p.innerHTML=o;
}
function fromHash(){var m=/^#y(\d{4})$/.exec(location.hash); return m?+m[1]:null;}
function yearAt(e){var r=ref.getBoundingClientRect(); var x=(e.clientX-r.left)*ref.viewBox.baseVal.width/r.width; return Math.floor((x-D.L)/D.PX)+D.y0;}
box.addEventListener('pointermove',function(e){if(e.pointerType==='mouse'&&e.target.closest('svg.trk')) setYear(yearAt(e));});
box.addEventListener('click',function(e){if(e.target.closest('a')||!e.target.closest('svg.trk')) return; setYear(yearAt(e));});
rng.addEventListener('input',function(){setYear(+rng.value);});
var y0=D.charts?fromHash():null; setYear(y0||1998);
if(D.charts) window.addEventListener('hashchange',function(){var y=fromHash(); if(y) setYear(y);});
})();
(function(){
function fit(){document.querySelectorAll('.tl-box,.colony-box').forEach(function(b){if(b.scrollWidth>b.clientWidth)b.scrollLeft=b.scrollWidth;});}
fit();window.addEventListener('load',fit);
function reveal(){
  var id=decodeURIComponent(location.hash.slice(1)); if(!id)return;
  var el=document.getElementById(id); if(!el)return;
  for(var n=el;n;n=n.parentElement){if(n.tagName==='DETAILS')n.open=true;}
  el.scrollIntoView();
}
window.addEventListener('hashchange',reveal);reveal();
function all(o){document.querySelectorAll('details.term-d').forEach(function(d){d.open=o;});}
var to=document.getElementById('terms-open'), tc=document.getElementById('terms-close');
if(to) to.addEventListener('click',function(){all(true);});
if(tc) tc.addEventListener('click',function(){all(false);});
})();
"""

# =============================================================== text sections
n_people = len(PEOPLE)
n_links = sum(len(p["case_links"]) for p in PEOPLE.values())
n_act = sum(1 for p in PEOPLE.values() for l in p["case_links"] if l["basis"] == "documented-act")
n_inoff = n_links - n_act
n_empty_terms = sum(1 for t in TERMS if not TP.get(t["id"]))
n_cong_null = sum(1 for t in TERMS if t.get("congress_share") is None)
n_unv_posts = sum(1 for p in PEOPLE.values() for x in p["posts"] if x.get("status") != "verified")
n_posts = sum(len(p["posts"]) for p in PEOPLE.values())
n_unv_links = sum(1 for p in PEOPLE.values() for x in p["case_links"] if x.get("status") != "verified")
not_drawn = [sid for sid in S if sid not in DRAWN]
dups = sorted(pid for pid, p in PEOPLE.items() if len(p["_files"]) > 1)

term_toc = []
cur_reg = None
for t in TERMS:
    if t["regime"] != cur_reg:
        if cur_reg is not None:
            term_toc.append("</p>")
        cur_reg = t["regime"]
        term_toc.append(f'<p class="ttoc">{regime_pill(t["regime"])} ')
    term_toc.append(f'<a href="#{t["_sid"]}">{esc(short_ruler(t["ruler"]))} {t["_start"].year}</a> ')
term_toc.append("</p>")

method_kinds = ", ".join(sorted({x["kind"] for p in PEOPLE.values() for x in p["foreign_ties"] if is_move(x["kind"])}))
e5_gaps = D["extra"].get("people-e5", {}).get("gaps", [])
e4_note = D["extra"].get("people-e4", {}).get("notes", "")
e3_note = D["extra"].get("people-e3", {}).get("verification_note", "")

soe_years = sorted(y for sid in ("federal-soe-count-dest-1980-2011", "federal-soe-count-ipea-1995", "federal-soe-count", "federal-soe-count-sest-active-2021-2022") for y in S[sid]["_pts"])
lab_flat = sorted(y for y, val in S["labour-share-pwt-1950-2023"]["_pts"].items() if abs(val - S["labour-share-pwt-1950-2023"]["_pts"][1950]) < 1e-9)

series_notes = []
for pid, title, _ in PANELS:
    pass
for sid in DRAWN:
    s = S[sid]
    series_notes.append(f'<li>{pill(s["status"])} <strong>{esc(s["label"])}</strong> <span class="muted">({esc(s["unit"])})</span> '
                        f'{src(s["source_url"], s["source_title"])}<br><span class="small">{esc(s["method_notes"])}</span></li>')
nd_notes = "".join(f'<li>{pill(S[sid]["status"])} {esc(S[sid]["label"])} <span class="muted">({esc(S[sid]["unit"])}, {len(S[sid]["_pts"])} points)</span> {src(S[sid]["source_url"])}</li>' for sid in not_drawn)

CSS = r"""
:root{--bg:#fbfaf7;--fg:#1d2127;--card:#fff;--line:#d9d6cd;--muted:#5d6572;--acc:#0b5d8f;
--c1:#1f5f99;--c2:#c0620e;--c3:#2f7d4f;--c4:#7a4aa8;--tk:#37474f;--dk:#a7a29a;--shade:rgba(160,60,40,.07);--grid:#e6e3db;--xh:#d0021b;
--rg-mon:#857596;--rg-olig:#a8813a;--rg-vd:#b0503a;--rg-mil:#8a2c2c;--rg-dem:#2c6a98;--rg-new:#4b7fa3;--rgt:#fff;
--sv:#1e6b34;--svb:#d9f0df;--su:#7a5a00;--sub:#fff0c2;--sc:#0b5d8f;--scb:#dcecf7;--sd:#9a2a1a;--sdb:#fadcd5}
@media (prefers-color-scheme:dark){:root{--bg:#14171b;--fg:#e6e8eb;--card:#1c2026;--line:#363c45;--muted:#a1a9b5;--acc:#7cc0ee;
--c1:#6cb0e6;--c2:#f0a35e;--c3:#7fcf9b;--c4:#c4a0e8;--tk:#cfd8dc;--dk:#6b6760;--shade:rgba(240,120,100,.09);--grid:#2a3038;--xh:#ff6b6b;
--rg-mon:#a593b8;--rg-olig:#c9a35a;--rg-vd:#d77a62;--rg-mil:#c25b5b;--rg-dem:#5d9fd0;--rg-new:#8ab9da;--rgt:#10141a;
--sv:#8fd9a2;--svb:#1d3a25;--su:#f3d57a;--sub:#4a3b0c;--sc:#7cc0ee;--scb:#16304a;--sd:#f4ab9b;--sdb:#4a2018}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;overflow-wrap:anywhere}
main{max-width:1240px;margin:0 auto;padding:16px}
h1{font-size:1.7rem;line-height:1.2;margin:.4em 0 .2em}
h2{font-size:1.35rem;margin:0 0 .5em;border-bottom:2px solid var(--line);padding-bottom:.25em}
h3{font-size:1.12rem;margin:1.2em 0 .4em}
h4{font-size:1rem;margin:1.1em 0 .3em}
h5{font-size:.85rem;margin:.8em 0 .2em;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}
section,nav{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0}
section section{margin:14px 0;background:var(--bg)}
section:target,tr:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
section:target,tr:target,figure:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
details:target,h3:target,.cap:target,.ph:target{outline:3px solid #ffb454;outline-offset:4px;border-radius:6px}
a{color:var(--acc)}
.lead{font-size:1.08rem}.muted{color:var(--muted)}.small{font-size:.85rem}.sub{color:var(--muted);margin:0}
ul,ol{padding-left:1.3em}
.toc{columns:2;column-gap:28px}.toc>li{break-inside:avoid}
.callout{border-left:5px solid #ffb454;background:var(--bg);padding:10px 14px;border-radius:6px;margin:12px 0}
.callout.warn{border-left-color:var(--rg-mil)}
.pill{display:inline-block;font-size:.68rem;line-height:1;padding:2px 6px;border-radius:99px;vertical-align:middle;font-weight:600;white-space:nowrap}
.pill.s-verified{background:var(--svb);color:var(--sv)}.pill.s-unverified{background:var(--sub);color:var(--su)}
.pill.s-corrected{background:var(--scb);color:var(--sc)}.pill.s-disputed{background:var(--sdb);color:var(--sd)}
table.ledger td{vertical-align:top}table.ledger td.nw{white-space:nowrap}ul.fl{margin:0;padding-left:1em}.tot{margin:.2em 0 .4em}
.flag{display:inline-block;font-size:.68rem;padding:1px 6px;border-radius:99px;border:1px dashed var(--muted);color:var(--muted);white-space:nowrap}
.rpill{display:inline-block;font-size:.72rem;padding:2px 8px;border-radius:99px;color:var(--rgt);font-weight:600;white-space:nowrap}
.rpill.rg-mon{background:var(--rg-mon)}.rpill.rg-olig{background:var(--rg-olig)}.rpill.rg-vd{background:var(--rg-vd)}
.rpill.rg-mil{background:var(--rg-mil)}.rpill.rg-dem{background:var(--rg-dem)}.rpill.rg-new{background:var(--rg-new)}
.basis{display:inline-block;font-size:.7rem;padding:1px 6px;border-radius:4px;white-space:nowrap;font-weight:600}
.basis.acted{background:var(--c2);color:var(--card)}.basis.inoff{border:1px solid var(--muted);color:var(--muted)}
/* timeline */
.tl-bar{position:sticky;top:0;z-index:5;background:var(--card);border:1px solid var(--line);border-radius:8px;padding:6px 10px;margin:8px 0;display:flex;flex-wrap:wrap;gap:4px 14px;align-items:center;font-size:.9rem}
.tl-bar input{flex:1 1 220px;min-width:160px}
.tl-bar #tl-y{font-size:1.2rem;font-variant-numeric:tabular-nums}
.tl-box{overflow-x:auto;overflow-y:hidden;border:1px solid var(--line);border-radius:8px;background:var(--card);-webkit-overflow-scrolling:touch;padding-bottom:6px}
.tl-inner{width:max-content}
.tl-box svg{display:block}
.ph{position:sticky;left:0;width:min(100%,calc(100vw - 60px));max-width:1180px;padding:10px 10px 2px;border-top:2px solid var(--line);margin-top:4px}
.ph .pt{font-weight:700;font-size:1.02rem}
.cap{position:sticky;left:0;width:min(100%,calc(100vw - 60px));max-width:1180px;padding:6px 10px 0;font-size:.85rem}
.cap .ct{font-weight:600}.cap .cu{color:var(--muted)}
.cap .cnote{margin:.1em 0 0;color:var(--muted);font-size:.8rem}
ul.lg{list-style:none;margin:2px 0 0;padding:0;display:flex;flex-wrap:wrap;gap:2px 16px}
ul.lg li{white-space:normal}
.rvw{white-space:nowrap}.rv{font-variant-numeric:tabular-nums}.rv.nd{font-weight:400;color:var(--muted)}
svg .grid{stroke:var(--grid);stroke-width:1}svg .grid.g50{stroke:var(--line)}
svg .shade{fill:var(--shade)}
svg .yt{stroke:var(--grid);stroke-dasharray:2 3}
svg .yl{fill:var(--muted);font-size:10px;text-anchor:end}
svg .xl{fill:var(--muted);font-size:10px;text-anchor:middle}
svg .xh{stroke:var(--xh);stroke-width:1.5;pointer-events:none}
svg .ln{fill:none;stroke-width:2;stroke-linejoin:round}
svg .c1{stroke:var(--c1);fill:var(--c1)}svg .c2{stroke:var(--c2);fill:var(--c2)}svg .c3{stroke:var(--c3);fill:var(--c3)}svg .c4{stroke:var(--c4);fill:var(--c4)}
svg g .ln{fill:none}
svg .dash .ln,svg.sw.dash line{stroke-dasharray:5 3}
svg .pt{stroke-width:1.5}svg .pt.hol,svg.sw circle.hol{fill:var(--card)}
svg .bar{stroke:none}
svg.sw{vertical-align:middle}svg.sw line{stroke-width:2.5}svg.sw circle{stroke-width:1.5}
svg .term{stroke:var(--card);stroke-width:.5}
svg .term.rg-mon{fill:var(--rg-mon)}svg .term.rg-olig{fill:var(--rg-olig)}svg .term.rg-vd{fill:var(--rg-vd)}
svg .term.rg-mil{fill:var(--rg-mil)}svg .term.rg-dem{fill:var(--rg-dem)}svg .term.rg-new{fill:var(--rg-new)}
svg a:hover .term,svg a:focus .term{opacity:.75}
svg .tl{fill:var(--rgt);font-size:10px;pointer-events:none}
svg .tk{fill:var(--tk)}svg .dk{fill:var(--dk)}
svg a:hover .tk,svg a:hover .dk{fill:var(--xh)}
svg .indep{stroke:var(--xh);stroke-dasharray:3 2}
figure.tlf{margin:0}svg .base{stroke:var(--line)}svg .db{fill:var(--tk);opacity:.8}svg a:hover .db{fill:var(--xh);opacity:1}
svg .dbl{fill:var(--fg);font-size:10px;text-anchor:middle;font-weight:600}
svg .ld{fill:var(--dk);stroke:var(--fg);stroke-width:.8;fill-opacity:.85}svg .ld.nc{fill:var(--card);stroke:var(--dk);stroke-width:1.5}
svg .ldl{fill:var(--fg);font-size:10px}svg a:hover .ld{stroke:var(--xh);stroke-width:2}
.colony-box{overflow-x:auto;border:1px solid var(--line);border-radius:8px;padding:6px;margin:8px 0;background:var(--card)}
/* tables and people */
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin:8px 0;-webkit-overflow-scrolling:touch}
table{border-collapse:collapse;width:100%;font-size:.9rem}
table.wide{min-width:820px}
th,td{padding:6px 9px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
thead th{background:var(--bg);font-size:.78rem;text-transform:uppercase;letter-spacing:.03em}
table.score th{width:200px;font-size:.85rem;background:transparent}
table.ind td:first-child{min-width:180px}
td.nw{white-space:nowrap}
details.person{border:1px solid var(--line);border-radius:8px;margin:6px 0;background:var(--card)}
details.person summary{cursor:pointer;padding:6px 10px}
details.person .pbody{padding:0 12px 10px}
ul.pl{margin:.2em 0;padding-left:1.1em}ul.pl li{margin:.3em 0}
ul.cl li{margin:.4em 0}
.ttoc{margin:.3em 0;line-height:1.9}.ttoc a{margin-right:6px;white-space:nowrap}
ol.ans li{margin:.4em 0}
details.notes summary{cursor:pointer;color:var(--acc);font-weight:600}
details.notes li{margin:.5em 0}
details.term-d>summary{cursor:pointer;list-style-position:inside}
details.term-d>summary h3{display:inline;margin:0}
@media (max-width:600px){.tl-bar{flex-wrap:nowrap;gap:6px;padding:3px 8px;margin:4px 0;font-size:.75rem;white-space:nowrap;overflow:hidden;min-height:0;height:40px;box-sizing:border-box}
.tl-bar #tl-y{font-size:.95rem}.tl-bar #tl-t{overflow:hidden;text-overflow:ellipsis;flex:0 1 auto;min-width:0}.tl-bar #tl-c{display:none}.tl-bar input{flex:1 1 80px;min-width:60px}}
@media (max-width:640px){main{padding:8px}section,nav{padding:12px}.toc{columns:1}table.score th{width:auto}}
"""

colony_cases_n = n_colony

TL_TOC = ('<li><a href="#tl-colony">Colony cases 1500–1822</a></li><li><a href="#tl-terms">Terms of power</a></li>'
          '<li><a href="#fig-deals-per-term">Chart: deals per term and later deaths</a></li>'
          '<li><a href="#tl-cases">Cases and disasters</a></li><li><a href="#tl-patrimony">Public patrimony</a></li><li><a href="#tl-purchasing">Purchasing power</a></li>'
          '<li><a href="#tl-concentration">Concentration</a></li><li><a href="#tl-political">Political power</a></li><li><a href="#tl-notes">Notes on every series</a></li>')

def timeline_section(charts):
    """The timeline section. timeline.html uses it as is; timeline-charts.html (charts=True) adds an intro,
    a how-to-read line and a year panel, and folds the colony strip into a details box."""
    colony_html = (f'<h3 id="tl-colony">Before independence: {colony_cases_n} transfer cases, 1500–1822</h3>\n'
                   f'<div class="colony-box">{colony_s}</div>')
    intro = year_panel = ""
    if charts:
        colony_html = (f'<details class="notes" id="tl-colony-d"><summary>Before independence: {colony_cases_n} transfer cases, 1500–1822 (open the strip)</summary>'
                       f'<h3 id="tl-colony">Colony cases by start year</h3><div class="colony-box">{colony_s}</div></details>')
        intro = ('<p class="lead">Every term of power, every deal and disaster, and the data on public patrimony, wages and wealth, on one year axis from 1822 to today.</p>'
                 '<p class="howto"><strong>How to read it:</strong> each row shares the same years. Pick a year (hover, tap or drag the slider); the red line marks it in every chart, '
                 'and the panel below lists who was in power, the deals signed and the disasters that year. The link in the address bar opens on that year.</p>')
        year_panel = '<aside class="yp" id="tl-yp" aria-live="polite"></aside>'
    return f'''<section id="timeline"><h2 id="timeline-h">The timeline, 1822–2026</h2>
{intro}<p class="lead"><strong>Hover, tap or drag the slider</strong> to pick a year. The bar shows who was in power, and every series shows its value for that year.</p>
<p class="small">{legend_regimes} <span class="muted">· Shaded years = dictatorship. <strong>Dashed line or hollow dot</strong> = unverified, modelled or imputed. Lines join only back-to-back years; a gap means no data.</span></p>
{colony_html}
<div class="tl-bar" aria-live="polite"><b id="tl-y">1998</b> <span id="tl-t"></span> <span id="tl-c" class="muted small"></span>
<input id="tl-year" type="range" min="{Y0}" max="{Y1}" value="1998" aria-label="Pick a year"></div>
<div class="tl-box" id="tl-box"><div class="tl-inner">
{"".join(panel_html)}
</div></div>
{year_panel}<p class="muted small">On a phone, swipe sideways inside the box. Units, sources and status sit above each chart.</p>
<details class="notes" id="tl-notes"><summary>Notes on every series drawn ({len(DRAWN)}), with the method notes as the researchers wrote them</summary>
<ul>{"".join(series_notes)}</ul>
<p><strong>In the data but not drawn ({len(not_drawn)}):</strong></p><ul class="small">{nd_notes}</ul></details>
</section>'''

page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brazil timeline: patrimony, purchasing power, concentration and who decided</title>
<style>{CSS}</style></head>
<body><main id="top">
<p class="sub"><a href="index.html">← Main page: the transfer cases</a> · <a href="disasters.html">Disasters</a> · <a href="chapters/index.html">President chapters</a> · <a href="timeline-charts.html">Timeline charts, full width</a></p>
<h1 id="title">Brazil 1822–2026: who ruled, what was handed over, and what happened to wages and wealth</h1>
<p class="sub">One shared year axis for every term of power, every transfer case, and the data on public patrimony, purchasing power, concentration and democracy. Built from the data files by build_timeline.py.</p>
{answer}
{deals}
<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ol class="toc">
<li><a href="#answer">What the timeline shows</a></li>
<li><a href="#deals">What deals did each president sign, and what followed?</a></li>
<li><a href="#timeline">The timeline</a> (also <a href="timeline-charts.html">on its own, full-width page</a>)<ul>{TL_TOC}</ul></li>
<li><a href="#terms">Every term: scorecard and decision-makers</a></li>
<li><a href="#both-sides">People on both sides</a></li>
<li><a href="#foreign">Foreign counterparts by country</a></li>
<li><a href="#method">How political power is scored</a></li>
<li><a href="#gaps">What data is missing</a></li>
</ol></nav>

{timeline_section(False)}

<section id="terms"><h2 id="terms-h">Every term: scorecard and decision-makers</h2>
<p class="lead"><strong>{len(TERMS)} terms</strong>, oldest first, each with the six-question scorecard, the indicator change, the people who could decide, and the cases that started.</p>
<p>Decision-makers come from the six people files: <strong>{n_people} people</strong>. Each post, tie, case link and investigation keeps its own pill. <strong>Unverified entries stay visible</strong>, marked yellow. Click a name to open the record.</p>
<p class="small"><span class="basis acted">acted</span> = an opened source names the person acting in the case. <span class="basis inoff">in office at the time</span> = the person held the post when the case started; no source names them acting.</p>
<p class="small"><button type="button" id="terms-open">Open all</button> <button type="button" id="terms-close">Close all</button> <span class="muted">Each term is closed until you open it.</span></p>
<div class="callout"><strong>Jump to a term:</strong>{"".join(term_toc)}<p class="ttoc"><a href="#term-colony">Before 1822: Portuguese crown</a></p></div>
{colony_sec}
{"".join(term_secs)}
</section>

<section id="both-sides"><h2 id="both-sides-h">Who sat on both sides: government, then buyers, foreign firms or lenders</h2>
<p class="lead"><strong>{n_both_people} people</strong> have a <strong>verified</strong> tie that shows a move between public office and a private or foreign employer, board, client or investor.</p>
<p>Only ties with status <strong>verified</strong> are in the main table. The tie kind is shown as the researchers wrote it. A tie is not an accusation.</p>
<div class="tw"><table class="wide"><thead><tr><th>Person</th><th>Public posts</th><th>Tie</th><th>Detail</th><th>Status</th></tr></thead><tbody>{"".join(r for _, r in both_v)}</tbody></table></div>
<h3 id="both-sides-unverified">Unverified ties, listed separately ({len(both_u)})</h3>
<p class="muted">These are not confirmed on an opened page. They are shown so nothing is hidden.</p>
<div class="tw"><table class="wide"><thead><tr><th>Person</th><th>Public posts</th><th>Tie</th><th>Detail</th><th>Status</th></tr></thead><tbody>{"".join(r for _, r in both_u)}</tbody></table></div>
<p class="small muted">Dealings with foreign governments and lenders while in office (IMF talks, treaties, loans) are not counted as moves. They are in each person's record and under <a href="#foreign">foreign counterparts</a>. Career text in each person's "Before" and "After" lines was not classified.</p>
</section>

<section id="foreign"><h2 id="foreign-h">Foreign counterparts, by country</h2>
<p class="lead"><strong>{len(FC)} foreign counterparts</strong> in the cases, from {len(by_country)} countries or groups. Most often: {top_cty}.</p>
<p class="small muted">Joint entries (for example "Spain/Portugal") are listed under each country. "US" and "USA" are grouped with "United States".</p>
<p class="ttoc">{" ".join(f'<a href="#{cty_ids[c]}">{esc(c)} ({len(by_country[c])})</a>' for c in sorted(by_country, key=lambda c: (-len(by_country[c]), c)))}</p>
{"".join(for_secs)}
</section>

<section id="method"><h2 id="method-h">How political power is scored in every term</h2>
<p class="lead"><strong>Every term gets the same six questions.</strong> The answers sit next to the money and inequality data, so patterns can be seen across 200 years.</p>
<div class="tw"><table><thead><tr><th>Question</th><th>What answers it here</th></tr></thead><tbody>
<tr><td><strong>1. Who ruled, and how did they get there?</strong></td><td>terms.json: ruler, title, how they came to power, how they left.</td></tr>
<tr><td><strong>2. Who could choose them?</strong></td><td>Registered voters as % of population, nearest year to the term (IBGE census years, or derived values marked unverified).</td></tr>
<tr><td><strong>3. Who backed them?</strong></td><td>Party or base from terms.json. Seats in Congress are missing for every term. Company campaign money (2002–2014) is on the timeline.</td></tr>
<tr><td><strong>4. What checked them?</strong></td><td>V-Dem electoral democracy index at the start and end of the term.</td></tr>
<tr><td><strong>5. What did they hand over?</strong></td><td>The cases that started in the term, with the decision-makers linked to each.</td></tr>
<tr><td><strong>6. Who gained and who lost?</strong></td><td>Change in real minimum wage, Gini, SOE investment, public debt and V-Dem from start to end of the term.</td></tr>
</tbody></table></div>
<div class="callout warn"><strong>Pattern, not proof.</strong> The scorecard shows what happened in the same years. It does not show why anyone acted, or that a decision caused a change in wages or inequality. An investigation is never shown as a fact: its outcome is printed exactly as in the data.</div>
<h3 id="method-rules">Rules used to build the page</h3>
<ol>
<li><strong>Case to term:</strong> a case belongs to the term in office in its start year. If several terms share that year, the term whose decision-makers are linked to the case wins (an "acted" link counts 2, "in office" counts 1). On a tie, the term in office on 1 July wins.</li>
<li><strong>People to term:</strong> the people files group people by term. Where one group covers several terms (Vargas 1930–1945, Floriano and Prudente), a person goes to each term their posts overlap. {len(D["added_by_case"])} people in no group are placed by the cases they are linked to. A person shows in every term they belong to; {len(dups)} people were in two era files and their records are merged.</li>
<li><strong>Indicator change:</strong> the start is the last full year before taking office (or the start year, if the term began after March). The end is the last year in office. If that year has no value, the nearest year within 2 years is used, and the years are printed. Start and end always come from the <strong>same series</strong>. Otherwise: "no data". The current term runs "to date".</li>
<li><strong>Gini and debt:</strong> the harmonised IPEA Gini is used first, then the old PNAD (0–1 scale), then the World Bank. Debt uses DLSP net debt, or before 1970 the gross federal internal debt. They are never mixed within one term.</li>
<li><strong>Both sides:</strong> verified ties whose kind is one of: {esc(method_kinds)}.</li>
<li><strong>Charts:</strong> series with different units have their own scale. Series the method notes say not to splice are drawn as separate marks: the four SOE counts, the two debt series, the three Gini series, the observed and modelled top shares, and Maddison against the World Bank (not drawn). Lines join only back-to-back years.</li>
</ol>
</section>

<section id="gaps"><h2 id="gaps-h">What data is missing</h2>
<p class="lead"><strong>Most links between people and cases are "in office" only</strong>: {n_inoff} of {n_links} links. Only {n_act} name the person acting.</p>
<ul>
<li><strong>Seats in Congress:</strong> congress_share is empty in {n_cong_null} of {len(TERMS)} terms.</li>
<li><strong>{n_empty_terms} terms have no decision-makers mapped</strong>, mostly regencies, juntas and short interim terms.</li>
<li><strong>Unverified entries:</strong> {n_unv_posts} of {n_posts} posts and {n_unv_links} of {n_links} case links.</li>
<li><strong>State-company counts:</strong> only {len(soe_years)} years in four different counting bases ({", ".join(map(str, soe_years))}). Before 2000 there are just 1980, 1990 and 1995.</li>
<li><strong>Privatization money:</strong> yearly figures cover 1991–2002 only. After 2002 there is just one federal total for 1990–2015.</li>
<li><strong>Purchasing power:</strong> household income starts in 1995; the minimum wage starts in 1941; Maddison GDP per person ends in 2022.</li>
<li><strong>Concentration:</strong> top income shares are observed only from 2001; earlier values are modelled decade points. Wealth shares are imputed for all years, with a method break between 1970 and 1980. Land Gini has {len(S["land-gini-establishments-1975-2017"]["_pts"])} census points.</li>
<li><strong>Labour share:</strong> the Penn World Table value is the same ({S["labour-share-pwt-1950-2023"]["_pts"][1950]}) in every year from {lab_flat[0]} to {lab_flat[-1]} in the file. The method note does not explain this, so treat that stretch with care.</li>
<li><strong>Campaign money:</strong> only 2002–2014 elections, candidate accounts only, and company donations were banned after 2015.</li>
<li><strong>Voters:</strong> no sourced share of voters before 1933 except one 1894 figure.</li>
<li><strong>Colony:</strong> terms.json starts in 1822, so the crown years have no scorecard or indicator change.</li>
</ul>
<h3 id="gaps-researchers">Gaps the researchers reported</h3>
<ul class="small">
{"".join(f"<li>{esc(g)}</li>" for g in e5_gaps)}
<li>{esc(e4_note)}</li>
<li>{esc(e3_note)}</li>
</ul>
</section>
<p class="muted small">Generated by build_timeline.py from data/terms.json, data/people-e1…e6.json, data/series-*.json, data/g1–g7 (cases) and g8–g10 (disasters).</p>
</main>
<script type="application/json" id="tl-data">{tl_json}</script>
<script>{JS}</script>
</body></html>
'''

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(page)

# =============================================================== timeline-charts.html: the same section on its own page
CSS_CH = """
main{max-width:1400px}
.howto{font-size:.95rem}
@media (min-width:1000px){.tl-inner{width:auto}.tl-box svg.trk{width:100%;height:auto}.ph,.cap{width:auto;max-width:none}}
@media (min-width:601px){.tl-bar #tl-y{font-size:2.2rem;line-height:1}}
.yp{position:sticky;bottom:0;z-index:6;background:var(--card);border:2px solid var(--line);border-radius:8px;padding:6px 14px;margin:8px 0;max-height:28vh;overflow:auto;font-size:.88rem;box-shadow:0 -4px 14px rgba(0,0,0,.12)}
.yp h3{margin:0;font-size:1.5rem;font-variant-numeric:tabular-nums}.yp p{margin:.2em 0}.yp ul{margin:.1em 0 .3em;padding-left:1.1em}
@media (min-width:900px){.yp{display:grid;grid-template-columns:5rem minmax(0,1fr) minmax(0,1.4fr) minmax(0,1.2fr);gap:0 20px;align-items:start}}
@media (max-width:600px){.yp{position:static;max-height:none}}
"""
CH_TOC = ('<li><a href="#timeline">The timeline</a><ul><li><a href="#tl-yp">The year you picked</a></li>'
          + TL_TOC.replace('href="#tl-colony"', 'href="#tl-colony-d"') + '</ul></li>')
page_ch = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brazil 1822–2026 on one year axis: timeline charts</title>
<style>{CSS}{CSS_CH}</style></head>
<body><main id="top">
<p class="sub"><a href="timeline.html">← Full timeline page (terms, people, deals)</a> · <a href="index.html">Main page</a> · <a href="disasters.html">Disasters</a></p>
<h1 id="title">Brazil 1822–2026 on one year axis</h1>
<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ol class="toc">{CH_TOC}</ol></nav>
{timeline_section(True)}
<p class="muted small">Generated by build_timeline.py from the same code as the timeline section of timeline.html.</p>
</main>
<script type="application/json" id="tl-data">{tl_json_ch}</script>
<script>{JS}</script>
</body></html>
'''
_ids_ch = set(re.findall(r'\bid="([^"]+)"', page_ch))
page_ch = re.sub(r'href="#([^"]+)"', lambda m: m.group(0) if m.group(1) in _ids_ch else f'href="timeline.html#{m.group(1)}"', page_ch)
with open(os.path.join(ROOT, "timeline-charts.html"), "w", encoding="utf-8") as fh:
    fh.write(page_ch)
print(f"wrote timeline-charts.html ({len(page_ch):,} bytes)")
print(f"wrote {OUT} ({len(page):,} bytes)")
print(f"terms {len(TERMS)}, people {n_people} (appearances {n_term_people}), series drawn {len(DRAWN)} of {len(S)}, "
      f"cases {n_cases}, both-sides verified people {n_both_people} rows {len(both_v)} unverified {len(both_u)}, countries {len(by_country)}")
