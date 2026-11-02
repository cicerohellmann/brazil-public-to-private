#!/usr/bin/env python3
"""Build explorer.html: one interactive time chart for incomes, the income gap, state money and poverty.

Run: python3 build_explorer.py   (reads data/*.json through timeline_data.py and build_chapters.py; never hand-edit explorer.html)
All data is embedded as JSON; the page has no external scripts. State lives in the URL hash:
  explorer.html#from=2000&to=2014&base=2002&s=min-wage-real,household-income-per-capita&y=2006[&mode=real][&embed=1]
A hash with no '=' is a preset, president or term id that exists on the page (lula-1, p-lula, t-lula-2003, ...).
"""
import json
import os
import re

import build_chapters as bc
import timeline_data as td

ROOT = td.ROOT
OUT = os.path.join(ROOT, "explorer.html")
S = bc.S
MAXY = 2026
OK = ("verified", "corrected")

# (id, group, picker name, short name for line labels, unit key, decimals, prefix, suffix, which way is better, scale, nominal)
SERIES = [
    ("household-income-per-capita", "rich", "Household income per person", "Household income", "brl-month", 0, "R$ ", " a month", "up = people got more", 1, False),
    ("min-wage-real", "rich", "Real minimum wage", "Minimum wage", "brl-month", 0, "R$ ", " a month", "up = the lowest wage buys more", 1, False),
    ("min-wage-in-cestas", "rich", "Minimum wage in food baskets", "Wage in baskets", "baskets", 2, "", " baskets", "up = the wage buys more food", 1, False),
    ("gdp-per-capita-worldbank", "rich", "GDP per person (the economy, not pay)", "GDP per person", "usd-year", 0, "US$ ", " a year", "up = bigger economy per person", 1, False),
    ("income-gini-pnad-ipea-1995-2025", "gap", "Income gap in surveys (Gini)", "Survey Gini", "gini", 1, "", "", "down = more equal", 1, False),
    ("top1-income-share-wid-2001-2024", "gap", "Top 1% share of income", "Top 1% income", "pct-income", 1, "", "%", "up = the top got more", 1, False),
    ("top10-income-share-wid-2001-2024", "gap", "Top 10% share of income", "Top 10% income", "pct-income", 1, "", "%", "up = the top got more", 1, False),
    ("dist-wid-bottom50-share", "gap", "Bottom 50% share of income", "Bottom 50% income", "pct-income", 1, "", "%", "up = the poorer half got more", 1, False),
    ("dist-wid-middle40-share", "gap", "Middle 40% share of income", "Middle 40% income", "pct-income", 1, "", "%", "up = the middle got more", 1, False),
    ("labour-share-pwt-1950-2023", "gap", "Workers' share of GDP", "Workers' share", "pct-labour", 1, "", "% of GDP", "up = workers got more", 100, False),
    ("top1-wealth-share-wid-1920-2024", "gap", "Top 1% share of wealth", "Top 1% wealth", "pct-wealth", 1, "", "%", "up = the top owns more", 1, False),
    ("dist-interest-pct-gdp", "state", "Interest paid on public debt", "Interest on debt", "pct-gdp", 1, "", "% of GDP", "money paid to holders of public debt", 1, False),
    ("dist-bolsa-familia-pct-gdp", "state", "Bolsa Família benefits", "Bolsa Família", "pct-gdp", 2, "", "% of GDP", "money paid to poor families", 1, False),
    ("dist-bndes-implicit-subsidy-brl-bn", "state", "BNDES loan subsidy (not inflation-adjusted)", "BNDES subsidy", "brl-bn", 1, "R$ ", " bn", "cost of cheap Treasury loans to BNDES; nominal R$", 1, True),
    ("dlsp-pct-gdp", "state", "Public debt (net)", "Public debt", "pct-debt", 1, "", "% of GDP", "", 1, False),
    ("public-investment-public-sector-pct-gdp", "state", "Public investment", "Public investment", "pct-gdp", 2, "", "% of GDP", "roads, energy, schools built by the state", 1, False),
    ("prices-overall-ipca", "cost", "Prices overall (IPCA)", "Prices overall", "price-index", 0, "", "", "a rising line = prices rose", 1, False),
    ("inflation-ipca", "cost", "Inflation per year (IPCA)", "Inflation per year", "pct-year", 1, "", "% a year", "down = prices rose more slowly", 1, False),
    ("cesta-basica-sp-nominal", "cost", "Food basket price (São Paulo)", "Food basket price", "brl-nominal", 0, "R$ ", " a month", "price of the DIEESE food basket; nominal R$", 1, True),
    ("dist-extreme-poverty-rate", "pov", "Extreme poverty (under US$ 3 a day)", "Extreme poverty", "pct-people", 1, "", "% of people", "down = fewer very poor", 1, False),
    ("dist-poverty-rate", "pov", "Poverty (under US$ 8.30 a day)", "Poverty", "pct-people", 1, "", "% of people", "down = fewer poor", 1, False),
]
GROUPS = [("rich", "Did people get richer?"), ("gap", "Did the gap shrink?"), ("state", "Where did the state's money go?"), ("pov", "Poverty"), ("cost", "Cost of living")]
UNITS = {
    "brl-month": "R$ a month, inflation removed", "baskets": "Food baskets a month (São Paulo)", "usd-year": "US$ a year, 2015 prices",
    "gini": "Gini, 0 to 100 (up = more unequal)", "pct-income": "% of national income", "pct-labour": "Workers' share, % of GDP",
    "pct-wealth": "% of all personal wealth", "pct-gdp": "% of GDP each year", "brl-bn": "R$ bn a year, not inflation-adjusted",
    "pct-debt": "Public debt, % of GDP", "pct-people": "% of people",
    "price-index": "Price level, Dec 1994 = 100", "pct-year": "Inflation, % a year (Dec to Dec)", "brl-nominal": "R$ a month, not inflation-adjusted",
}
DEFAULT = dict(frm=1990, to=MAXY, base=2002, s=["household-income-per-capita", "min-wage-real", "income-gini-pnad-ipea-1995-2025", "dist-interest-pct-gdp"])
PRESETS = [("lula-1", "Lula 2003–2010", 2000, 2013, 2002, 2010), ("lula-3", "Lula 2023–now", 2019, MAXY, 2022, 2025),
           ("cardoso", "Cardoso", 1992, 2005, 1994, 2002), ("all", "All", None, MAXY, None, 2025)]
# Topic buttons: one per question; each switches the chart to that topic's lines.
TOPICS = [
    ("topic-rich", "Richer or poorer?", ["household-income-per-capita", "min-wage-real", "min-wage-in-cestas"]),
    ("topic-gap", "The gap", ["income-gini-pnad-ipea-1995-2025", "top10-income-share-wid-2001-2024", "dist-wid-bottom50-share", "dist-wid-middle40-share"]),
    ("topic-state", "State money", ["dist-interest-pct-gdp", "dist-bolsa-familia-pct-gdp", "dist-bndes-implicit-subsidy-brl-bn"]),
    ("topic-pov", "Poverty", ["dist-extreme-poverty-rate", "dist-poverty-rate"]),
    ("topic-cost", "Cost of living", ["prices-overall-ipca", "cesta-basica-sp-nominal", "min-wage-real", "min-wage-in-cestas"]),
]


def esc(s):
    return bc.esc(s)


BAND = {"Getúlio Vargas": "Vargas", "Fernando Collor": "Collor", "Itamar Franco": "Itamar", "Dilma Rousseff": "Dilma",
        "Michel Temer": "Temer", "Jair Bolsonaro": "Bolsonaro", "José Sarney": "Sarney", "João Figueiredo": "Figueiredo",
        "Ernesto Geisel": "Geisel", "João Goulart": "Goulart", "Jânio Quadros": "Jânio", "Washington Luís": "W. Luís",
        "Epitácio Pessoa": "Epitácio", "Artur Bernardes": "Bernardes", "Café Filho": "Café Filho", "José Linhares": "Linhares",
        "Ranieri Mazzilli": "Mazzilli", "Carlos Luz": "Luz", "Nereu Ramos": "N. Ramos"}


def roman(n):
    return ["", "I", "II", "III", "IV", "V"][n] if n < 6 else str(n)


RATE_ONLY = {"inflation-ipca"}   # a % per year: "change since" makes no sense, so it only shows in Real values mode
PRICE_BASE_YEAR = 1994           # price level = 100 at the end of this year


def prices_overall():
    """Price level from compounding the yearly IPCA % (Dec to Dec): Dec 1994 = 100. Inherits the source's status and link."""
    src = S["inflation-ipca"]
    lvl, pts = 100.0, {}
    for y in sorted(src["_pts"]):
        if y > PRICE_BASE_YEAR:
            lvl *= 1 + src["_pts"][y] / 100
            pts[y] = lvl
    return dict(_pts=pts, status=src.get("status"), unit="index, Dec 1994 = 100", source_title=src.get("source_title"),
                source_url=src.get("source_url"))


def series_json():
    out = []
    S_ = dict(S)
    S_["prices-overall-ipca"] = prices_overall()
    for sid, grp, name, short, ukey, dec, pre, suf, better, scale, nominal in SERIES:
        s = S_[sid]
        if sid == "prices-overall-ipca":
            pts, dropped = dict(s["_pts"]), []
        else:
            pts, dropped = bc.w_pts(sid, scale)
        pts = [[y, round(pts[y], dec + 2)] for y in sorted(pts)]
        note = []
        if nominal:
            note.append("Nominal reais: part of the rise is inflation.")
        if sid == "prices-overall-ipca":
            note.append("Computed from yearly IPCA: each year's rate (December to December) compounded from Dec 1994 = 100.")
        if sid in RATE_ONLY:
            note.append("Shown in Real values only.")
        if dropped:
            note.append(f"Last value repeated in the source for {dropped[0]}–{dropped[-1]}; treated as no new data.")
        out.append(dict(id=sid, g=grp, name=name, short=short, u=ukey, dec=dec, pre=pre, suf=suf, better=better,
                        rate=sid in RATE_ONLY, ok=s.get("status") in OK, status=s.get("status") or "unverified", nominal=nominal,
                        unit=s.get("unit") or "", src_t=s.get("source_title") or "source", src_u=s.get("source_url") or "",
                        note=" ".join(note), pts=pts))
    return out


def terms_json(min_year):
    """Bands: every term that overlaps the data years. Label = short name, with I/II/... for repeat terms."""
    out = []
    by_slug = {}
    for slug, P in bc.PERSONS.items():
        for i, t in enumerate(P["terms"]):
            by_slug[t["id"]] = (slug, P, i)
    for t in bc.TERMS:
        if t["_end"].year < min_year or t["id"] not in by_slug:
            continue
        slug, P, i = by_slug[t["id"]]
        n = len(P["terms"])
        rn = " " + roman(i + 1) if n > 1 else ""
        name = P["name"] + rn
        short = ("Junta" if P["name"].startswith("Military junta") else BAND.get(P["name"], P["name"])) + rn
        sy, ey = td.term_ref_years(t)
        ab = short[0] + (str(i + 1) if n > 1 else "")
        out.append(dict(id=t["id"], name=name, band=short, ab=ab, person=P["name"], slug=slug, years=bc.term_years(t),
                        s=round(td.frac(t["_start"]), 3), e=round(td.frac(t["_end"]), 3), base=sy, end=ey if ey is not None else 2025,
                        href=f"chapters/{slug}.html#term-{bc.tshort(t)}"))
    return out


def deals_json(min_year):
    out = {}
    for c in bc.CASES:
        st, places = bc.DEAL[c["id"]]
        if st not in ("deal", "ongoing"):
            continue
        for _place, y, note in places:
            if y is None or not (min_year <= y <= MAXY):
                continue
            out.setdefault(str(y), []).append([note or c["title"], f"index.html#{c['id']}", st == "ongoing"])
    return out


def disasters_json(min_year):
    out = {}
    for d in bc.DIS:
        y = d["_y"]
        if y is None or not (min_year <= y <= MAXY):
            continue
        href = f"disasters.html#{d['id']}" if d["id"] in bc.DIS_PAGE_IDS else ""
        out.setdefault(str(y), []).append([d.get("name") or d["id"], href, bc.deaths_txt(d)])
    return out


def check_links(terms, deals, dis):
    ids = {}

    def has(path, frag):
        if path not in ids:
            ids[path] = set(re.findall(r'\bid="([^"]+)"', open(os.path.join(ROOT, path), encoding="utf-8").read()))
        return frag in ids[path]
    bad = []
    for t in terms:
        p, f = t["href"].split("#")
        if not os.path.exists(os.path.join(ROOT, p)) or not has(p, f):
            bad.append(t["href"])
    for rows in list(deals.values()) + list(dis.values()):
        for r in rows:
            if r[1]:
                p, f = r[1].split("#")
                if not has(p, f):
                    bad.append(r[1])
    assert not bad, f"explorer links that do not resolve: {bad[:10]}"
    return sum(len(v) for v in deals.values()) + sum(1 for v in dis.values() for r in v if r[1]) + len(terms)


def build():
    ser = series_json()
    min_year = min(s["pts"][0][0] for s in ser)
    terms = terms_json(min_year)
    deals = deals_json(min_year)
    dis = disasters_json(min_year)
    nlinks = check_links(terms, deals, dis)
    go = {}
    for pid, label, f, t, b, y in PRESETS:
        go[pid] = dict(label=label, frm=f, to=t, base=b, y=y)
    known = {x["id"] for x in ser}
    for tid, label, ids in TOPICS:
        missing = [i for i in ids if i not in known]
        assert not missing, (tid, missing)
        go[tid] = dict(label=label, frm=1995, to=MAXY, base=2002, y=2025, s=ids)
    persons = {}
    for t in terms:
        persons.setdefault(t["slug"], []).append(t)
        go[t["id"]] = dict(label=f'{t["name"]}, {t["years"]}', frm=max(min_year, int(t["s"]) - 3), to=min(MAXY, int(t["e"]) + 3), base=t["base"], y=t["end"])
    for slug, ts in persons.items():
        go["p-" + slug] = dict(label=ts[0]["person"], frm=max(min_year, int(ts[0]["s"]) - 3), to=min(MAXY, int(ts[-1]["e"]) + 3), base=ts[0]["base"], y=ts[-1]["end"])
    data = dict(series=ser, groups=[dict(k=k, title=t) for k, t in GROUPS], units=UNITS, terms=terms, deals=deals, dis=dis, go=go,
                minY=min_year, maxY=MAXY, dflt=dict(frm=DEFAULT["frm"], to=DEFAULT["to"], base=DEFAULT["base"], s=DEFAULT["s"]))
    js_data = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    preset_html = "".join(f'<a class="pbtn" id="{p[0]}" href="#{p[0]}">{esc(p[1])}</a>' for p in PRESETS)
    topic_html = "".join(f'<a class="pbtn topic" id="{t[0]}" href="#{t[0]}">{esc(t[1])}</a>' for t in TOPICS)
    jump = []
    for slug, ts in reversed(list(persons.items())):
        jump.append(f'<li><a id="p-{slug}" href="#p-{slug}"><strong>{esc(ts[0]["person"])}</strong></a>: '
                    + " · ".join(f'<a id="{t["id"]}" href="#{t["id"]}">{esc(t["years"])}</a>' for t in ts) + "</li>")
    src_rows = []
    for s in ser:
        pill = f'<span class="pill s-{esc(s["status"])}">{esc(s["status"])}</span>'
        link = f'<a href="{esc(s["src_u"])}">{esc(s["src_t"])}</a>' if s["src_u"].startswith("http") else esc(s["src_t"])
        src_rows.append(f'<li><strong>{esc(s["name"])}</strong> {pill} <span class="muted small">{esc(s["unit"])}; {s["pts"][0][0]}–{s["pts"][-1][0]}.</span>'
                        f'{(" " + esc(s["note"])) if s["note"] else ""}<br><span class="small">Source: {link}</span></li>')
    html_ = TEMPLATE.replace("/*BASECSS*/", bc.base_css()).replace("@@PRESETS@@", preset_html).replace("@@TOPICS@@", topic_html).replace("@@JUMP@@", "".join(jump)) \
        .replace("@@SOURCES@@", "".join(src_rows)).replace("@@NSER@@", str(len(ser))).replace("@@DATA@@", js_data)
    for bad in ("/" + "Users/", "file" + "://", "@" + "gmail"):   # split so this file passes the publish scan too
        assert bad not in html_, bad
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(html_)
    print(f"wrote explorer.html ({len(html_):,} bytes, {len(ser)} series, {len(terms)} terms, {nlinks} links checked)")


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Data explorer: who got richer</title>
<style>/*BASECSS*/
html{scroll-behavior:smooth}
section:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
:root{--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--s6:#008300;--s7:#6250d6;--s8:#e34948;
--bandA:rgba(120,110,90,.07);--bandB:rgba(120,110,90,0);--stripA:#e9e5da;--stripB:#f5f2ea;--stripT:#3a3f47;--cur:#1d2127}
@media (prefers-color-scheme:dark){:root{--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--s6:#008300;--s7:#9085e9;--s8:#e66767;
--bandA:rgba(200,210,225,.06);--bandB:rgba(0,0,0,0);--stripA:#2b313a;--stripB:#22272e;--stripT:#d5dae0;--cur:#e6e8eb}}
main{max-width:1240px}
h1{font-size:1.8rem}
.lead{font-size:1.1rem;margin:.3em 0 .6em}
.toc{columns:1}.toc li{display:inline;margin-right:14px}.toc{padding-left:0;list-style:none;margin:0}
#explore{padding:14px}
.bar{display:flex;flex-wrap:wrap;gap:8px 14px;align-items:center;margin:0 0 10px}
.bar .grp{display:flex;flex-wrap:wrap;gap:6px;align-items:center}
.lbl{font-size:.85rem;color:var(--muted);font-weight:600}
.pbtn,.mbtn{display:inline-block;padding:6px 12px;border:2px solid var(--acc);border-radius:99px;background:var(--card);color:var(--acc);font:600 .9rem/1.2 inherit;text-decoration:none;cursor:pointer}
.pbtn.on,.mbtn.on{background:var(--acc);color:var(--card)}
.bar .topics{padding-bottom:6px;border-bottom:1px solid var(--line);width:100%}.pbtn.topic{font-size:.95rem}
select{font:inherit;font-size:.9rem;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--card);color:var(--fg)}
.picker{display:grid;grid-template-columns:repeat(auto-fit,minmax(250px,1fr));gap:8px 14px;margin:0 0 10px}
.picker details{border:1px solid var(--line);border-radius:8px;padding:6px 10px;background:var(--bg)}
.picker summary{cursor:pointer;font-weight:700;padding:2px 0}
.picker summary .n{font-weight:400;color:var(--muted);font-size:.85rem}
.chips{display:flex;flex-wrap:wrap;gap:6px;margin:6px 0 2px}
.chip{display:inline-flex;align-items:center;gap:6px;padding:5px 10px;border:1px solid var(--line);border-radius:99px;background:var(--card);color:var(--fg);font:inherit;font-size:.86rem;line-height:1.25;cursor:pointer;text-align:left}
.chip[aria-pressed=true]{border-color:var(--fg);font-weight:600}
.chip:disabled{opacity:.45;cursor:not-allowed}
.key{display:inline-block;width:20px;height:0;border-top:3px solid var(--muted);flex:0 0 auto}
.key.off{border-top:2px solid var(--line)}.key.u{border-top-style:dashed}
.tag{font-size:.68rem;font-weight:600;padding:1px 6px;border-radius:99px;background:var(--sub);color:var(--su);white-space:nowrap}
.tag.nom{background:var(--scb);color:var(--sc)}
.legend{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.85rem;margin:2px 0 6px;color:var(--fg)}
.legend span.it{display:inline-flex;align-items:center;gap:6px}
.flow{display:flex;flex-direction:column}.hint .below{display:none}@media (min-width:700px){.hint .below{display:inline}.hint .above{display:none}}
@media (min-width:700px){.flow .legend{order:1}.flow .stage{order:2}.flow .picker{order:3;margin:14px 0 0}}
.stage{display:grid;grid-template-columns:minmax(0,1fr) 340px;gap:16px;align-items:start}
@media (max-width:900px){.stage{grid-template-columns:minmax(0,1fr)}}
#chartbox{position:relative;min-width:0;outline:none;border-radius:6px}
#chartbox:focus-visible{box-shadow:0 0 0 3px #ffb454}
#chart{display:block;width:100%;touch-action:pan-y;user-select:none;-webkit-user-select:none}
#chart text{font:11px system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;fill:var(--muted)}
#chart .bt{fill:var(--stripT);font-weight:600;font-size:11.5px;pointer-events:none}
#chart .strip{cursor:pointer}#chart .strip:hover rect{stroke:var(--acc);stroke-width:1.5}
#chart .grid{stroke:var(--grid);stroke-width:1}
#chart .zero{stroke:var(--muted);stroke-width:1.2}
#chart .basel{stroke:var(--muted);stroke-width:1;stroke-dasharray:2 3}
#chart .ln{fill:none;stroke-width:2.2;stroke-linejoin:round;stroke-linecap:round}
#chart .ln.u{stroke-dasharray:6 4}
#chart .lab{fill:var(--fg);font-size:12px;font-weight:600}
#chart .pt{fill:var(--fg);font-size:12px;font-weight:700}
#chart .ptitle{fill:var(--fg);font-weight:700;font-size:12px}
#chart .curl{stroke:var(--cur);stroke-width:1.5}
#chart .curm{stroke:var(--card);stroke-width:2}
#chart .cury{fill:var(--cur)}#chart .curyt{fill:var(--card);font-weight:700;font-size:12px}
.hint{font-size:.82rem;color:var(--muted);margin:4px 0 0}
#panel{border:1px solid var(--line);border-radius:8px;background:var(--bg);padding:10px 12px;min-height:200px}
#panel h3{margin:0 0 .2em;font-size:1.5rem}
#panel h4{margin:.9em 0 .3em;font-size:.95rem}
#panel .pres{margin:0 0 .5em}
#panel ul{list-style:none;padding:0;margin:0}
#panel .vals li{display:grid;grid-template-columns:22px minmax(0,1fr);gap:0 6px;padding:6px 0;border-top:1px solid var(--line)}
#panel .vals .key{margin-top:.6em}
#panel .v{font-weight:700;font-size:1.05rem}
#panel .nm{font-size:.86rem}
#panel .sm{font-size:.78rem;color:var(--muted)}
#panel .list li{margin:.25em 0;font-size:.88rem;line-height:1.35}
#panel .none{color:var(--muted);font-size:.88rem;margin:.2em 0}
.notes{margin:.6em 0 0;padding-left:1.2em;font-size:.9rem}
.notes li{margin:.2em 0}
#jump ul{columns:2;column-gap:28px;padding-left:1.1em}#jump li{break-inside:avoid;margin:.25em 0}
#sources ul{padding-left:1.1em}#sources li{margin:.5em 0}
.tbl{overflow-x:auto;max-width:100%}
.tbl table{border-collapse:collapse;font-size:.85rem;font-variant-numeric:tabular-nums}
.tbl th,.tbl td{border-bottom:1px solid var(--line);padding:3px 8px;text-align:right;white-space:nowrap}
.tbl th:first-child,.tbl td:first-child{text-align:left}
.full{font-size:.85rem;font-weight:600}
body.embed main{padding:6px}body.embed .page-only{display:none}body.embed #explore{margin:0;border:0;padding:4px}
body:not(.embed) .embed-only{display:none}
@media (max-width:640px){h1{font-size:1.45rem}#explore{padding:10px}.picker{grid-template-columns:minmax(0,1fr)}#jump ul{columns:1}#panel h3{font-size:1.3rem}}
</style></head>
<body><main id="top">
<div class="page-only">
<p class="sub"><a href="index.html">Main page</a> · <a href="timeline.html">Timeline</a> · <a href="chapters/index.html">President chapters</a> · <a href="disasters.html">Disasters</a></p>
<h1 id="title">Who got richer, who got poorer: one chart</h1>
<p class="lead"><strong>Incomes, the gap, state money, poverty and the cost of living on one time line.</strong> Pick a Topic, or single lines. Drag, tap or press ← → to move through the years. Click a president's name to zoom in.</p>
<nav id="contents" aria-label="Contents"><h2 id="contents-h" class="small">Contents</h2><ul class="toc"><li><a href="#explore">The chart</a></li><li><a href="#how">How to read it</a></li><li><a href="#jump">Jump to a president</a></li><li><a href="#numbers">The numbers</a></li><li><a href="#sources">Sources</a></li></ul></nav>
</div>
<section id="explore" aria-label="The chart"><h2 id="explore-h" class="page-only">The chart</h2>
<div class="bar">
<div class="grp topics" aria-label="Topics"><span class="lbl">Topic:</span>@@TOPICS@@</div>
<div class="grp" aria-label="Presets"><span class="lbl">Years:</span>@@PRESETS@@</div>
<div class="grp"><span class="lbl">Lines as:</span><button type="button" class="mbtn" id="m-index" data-mode="index">Change since …</button><button type="button" class="mbtn" id="m-real" data-mode="real">Real values</button></div>
<div class="grp"><label class="lbl" for="base">Compare with</label><select id="base"></select><label class="lbl" for="from">From</label><select id="from"></select><label class="lbl" for="to">to</label><select id="to"></select></div>
<a class="full embed-only" id="fulllink" href="explorer.html" target="_top">Open the full page ↗</a>
</div>
<p class="small muted" id="costnote">Wages and incomes here already have inflation removed; 'Prices overall' shows how much prices themselves rose.</p>
<div class="flow"><div class="picker" id="picker"></div>
<div class="legend" id="legend" aria-label="Lines on the chart"></div>
<div class="stage">
<div><div id="chartbox" tabindex="0" aria-label="Chart. Left and right arrow keys move the year."><svg id="chart" role="img" aria-labelledby="chart-desc"><desc id="chart-desc">Time chart of the selected series with presidents as bands along the top.</desc></svg></div>
<p class="hint" id="hint">Tip: click a name in the top band to zoom to that term. Use the Topic buttons above, or pick single lines in the boxes <span class="below">below</span><span class="above">above</span>.</p></div>
<aside id="panel" aria-live="polite"></aside>
</div></div>
</section>
<div class="page-only">
<section id="how"><h2 id="how-h">How to read it</h2>
<ul class="notes">
<li><strong>Change since a year:</strong> every line starts at 0% in the year you pick under "Compare with". Up = it grew since then.</li>
<li><strong>Real values:</strong> one small chart per unit, so % and R$ never share an axis.</li>
<li><strong>Dashed line = not verified yet.</strong> It has a source, but no second check.</li>
<li><strong>A break in a line = no data that year</strong> (the household survey skipped 2000 and 2010).</li>
<li>Bands along the top = who was president. Deals and disasters for the year are in the box next to the chart.</li>
<li>A deal or disaster in the same year as a line moving is order in time, not proof of cause.</li>
</ul></section>
<section id="jump"><h2 id="jump-h">Jump to a president</h2><p class="small muted">Each link zooms the chart to that president or term and compares with the year before they took office.</p><ul>@@JUMP@@</ul></section>
<section id="numbers"><h2 id="numbers-h">The numbers behind the chart</h2><p class="small muted">The lines that are on, for the years in view. Real values.</p><div class="tbl" id="tbl"></div></section>
<section id="sources"><h2 id="sources-h">Sources for all @@NSER@@ lines</h2><ul>@@SOURCES@@</ul>
<p class="small muted">Built from the data files by build_explorer.py.</p></section>
</div>
</main>
<script type="application/json" id="data">@@DATA@@</script>
<script>
(function(){
"use strict";
var D=JSON.parse(document.getElementById("data").textContent);
var SER={},ORDER=[];
D.series.forEach(function(s){s.map={};s.pts.forEach(function(p){s.map[p[0]]=p[1];});s.first=s.pts[0][0];s.last=s.pts[s.pts.length-1][0];SER[s.id]=s;ORDER.push(s.id);});
var MAXSEL=8;
var st={frm:D.dflt.frm,to:D.dflt.to,base:D.dflt.base,slots:[null,null,null,null,null,null,null,null],y:2025,mode:"index",embed:false};
var dragging=false,hashTimer=null,lastW=0;
function esc(s){return String(s).replace(/[&<>"']/g,function(c){return{"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c];});}
function sel(){return st.slots.filter(function(x){return x;});}
function slotOf(id){return st.slots.indexOf(id);}
function col(id){return "var(--s"+(slotOf(id)+1)+")";}
function clamp(v,a,b){return Math.max(a,Math.min(b,v));}
function num(v,d){return v.toLocaleString("en-US",{minimumFractionDigits:d,maximumFractionDigits:d});}
function fmtv(s,v){return s.pre+num(v,s.dec)+s.suf;}
function setSel(ids){st.slots=[null,null,null,null,null,null,null,null];ids.filter(function(i){return SER[i];}).slice(0,MAXSEL).forEach(function(i,k){if(st.slots.indexOf(i)<0)st.slots[k]=i;});}
function toggle(id){var k=slotOf(id);if(k>=0){st.slots[k]=null;}else{var f=st.slots.indexOf(null);if(f<0)return;st.slots[f]=id;}render();}
/* base value: the base year, else the nearest year within 2, else the first year in view */
function baseOf(s){
  if(s.rate)return null;
  var b=st.base;
  if(s.map[b]!=null)return{y:b,v:s.map[b],why:""};
  var best=null;for(var d=1;d<=2;d++){if(s.map[b-d]!=null){best=b-d;break;}if(s.map[b+d]!=null){best=b+d;break;}}
  if(best!=null)return{y:best,v:s.map[best],why:"nearest year to "+b};
  for(var y=Math.max(st.frm,s.first);y<=Math.min(st.to,s.last);y++){if(s.map[y]!=null)return{y:y,v:s.map[y],why:"first year in data"};}
  return null;
}
function idx(s,v,bi){return v/bi.v*100;}
function pct(i){var p=i-100;return (p>=0.5?"+":p<=-0.5?"−":"")+num(Math.abs(p),0)+"%";}
/* ---------- hash state */
function applyGo(id){
  var g=D.go[id];if(!g)return false;
  var to=g.to,frm=g.frm,base=g.base;
  if(g.s)setSel(g.s);
  if(id==="all"){var ids=sel().length?sel():ORDER;frm=Math.min.apply(null,ids.map(function(i){return SER[i].first;}));base=st.base;}
  st.frm=frm;st.to=to;st.base=base;st.y=clamp(g.y||to,frm,to);return true;
}
function parseHash(){
  var h=decodeURIComponent(location.hash.slice(1)||"");
  if(!h){setSel(D.dflt.s);return false;}
  if(h.indexOf("=")<0){if(!sel().length)setSel(D.dflt.s);return applyGo(h);}
  var p={};h.split("&").forEach(function(kv){var i=kv.indexOf("=");if(i>0)p[kv.slice(0,i)]=kv.slice(i+1);});
  st.embed=p.embed==="1";
  setSel(p.s!=null?p.s.split(",").filter(Boolean):D.dflt.s);
  if(p.go)applyGo(p.go);
  function iv(k,d){var v=parseInt(p[k],10);return isNaN(v)?d:v;}
  st.frm=clamp(iv("from",st.frm),D.minY,D.maxY-2);st.to=clamp(iv("to",st.to),st.frm+2,D.maxY);
  st.base=clamp(iv("base",st.base),D.minY,D.maxY);st.y=clamp(iv("y",st.y),st.frm,st.to);
  st.mode=p.mode==="real"?"real":"index";
  return false;
}
function stateStr(embed){
  var a=["from="+st.frm,"to="+st.to,"base="+st.base,"s="+sel().join(","),"y="+st.y];
  if(st.mode==="real")a.push("mode=real");if(embed)a.push("embed=1");return a.join("&");
}
function writeHash(){
  clearTimeout(hashTimer);
  hashTimer=setTimeout(function(){try{history.replaceState(null,"","#"+stateStr(st.embed));}catch(e){}
    var fl=document.getElementById("fulllink");if(fl)fl.href="explorer.html#"+stateStr(false);},150);
}
/* ---------- controls */
function opts(el,a,b,v){var h="";for(var y=a;y<=b;y++)h+='<option value="'+y+'"'+(y===v?" selected":"")+">"+y+"</option>";el.innerHTML=h;}
function renderControls(){
  opts(document.getElementById("base"),D.minY,2025,st.base);
  opts(document.getElementById("from"),D.minY,D.maxY-2,st.frm);
  opts(document.getElementById("to"),st.frm+2,D.maxY,st.to);
  var mi=document.getElementById("m-index");mi.textContent="Change since "+st.base;
  mi.classList.toggle("on",st.mode==="index");document.getElementById("m-real").classList.toggle("on",st.mode==="real");
  mi.setAttribute("aria-pressed",st.mode==="index");document.getElementById("m-real").setAttribute("aria-pressed",st.mode==="real");
  Array.prototype.forEach.call(document.querySelectorAll(".pbtn"),function(a){var g=D.go[a.id];
    var on=g&&g.to===st.to&&(!g.s||g.s.join()===sel().join())&&(a.id==="all"?st.frm===Math.min.apply(null,(sel().length?sel():ORDER).map(function(i){return SER[i].first;})):(g.frm===st.frm&&g.base===st.base));
    a.classList.toggle("on",!!on);});
}
var openGroups=null;
function renderPicker(){
  var box=document.getElementById("picker");
  if(openGroups===null){openGroups={};var wide=window.innerWidth>=700&&!st.embed;D.groups.forEach(function(g){openGroups[g.k]=wide;});}
  var full=sel().length>=MAXSEL,h="";
  D.groups.forEach(function(g){
    var ids=ORDER.filter(function(i){return SER[i].g===g.k;}),non=ids.filter(function(i){return slotOf(i)>=0;}).length;
    h+='<details data-g="'+g.k+'"'+(openGroups[g.k]?" open":"")+'><summary>'+esc(g.title)+' <span class="n">('+non+' on)</span></summary><div class="chips">';
    ids.forEach(function(i){var s=SER[i],on=slotOf(i)>=0;
      h+='<button type="button" class="chip" data-id="'+i+'" aria-pressed="'+on+'"'+(!on&&full?' disabled title="8 lines at most. Turn one off first."':'')+'>'
       +'<span class="key'+(on?"":" off")+(s.ok?"":" u")+'"'+(on?' style="border-top-color:'+col(i)+'"':'')+'></span>'+esc(s.name)
       +(s.ok?"":' <span class="tag">unverified</span>')+(s.nominal?' <span class="tag nom">nominal</span>':'')+(s.rate?' <span class="tag">real values only</span>':'')+'</button>';});
    h+='</div></details>';});
  box.innerHTML=h;
  var lg="";sel().forEach(function(i){var s=SER[i];lg+='<span class="it"><span class="key'+(s.ok?"":" u")+'" style="border-top-color:'+col(i)+'"></span>'+esc(s.short)+(s.ok?"":' <span class="tag">unverified</span>')+'</span>';});
  document.getElementById("legend").innerHTML=sel().length?lg:'<span class="muted">No line on. Pick one above.</span>';
}
/* ---------- chart */
var G={};
function nice(lo,hi,n){
  if(hi-lo<1e-9){hi=lo+1;lo=lo-1;}
  var raw=(hi-lo)/n,mag=Math.pow(10,Math.floor(Math.log10(raw))),r=raw/mag,step=(r<1.5?1:r<3?2:r<7?5:10)*mag;
  var a=Math.floor(lo/step)*step,b=Math.ceil(hi/step)*step,t=[];for(var v=a;v<=b+step/2;v+=step)t.push(+v.toFixed(10));return{lo:a,hi:b,ticks:t,step:step};
}
function tw(s,size){return s.length*(size||11.5)*0.56;}
function panels(){
  var ids=sel();
  if(st.mode==="index")return[{title:"",ids:ids}];
  var ps=[],by={};ids.forEach(function(i){var u=SER[i].u;if(!by[u]){by[u]={title:D.units[u],ids:[],u:u};ps.push(by[u]);}by[u].ids.push(i);});
  return ps.length?ps:[{title:"",ids:[]}];
}
function renderChart(){
  var box=document.getElementById("chartbox"),svg=document.getElementById("chart");
  var W=Math.max(280,Math.floor(box.clientWidth));lastW=W;
  var narrow=W<600,ids=sel(),ps=panels();
  var labelsOn=!narrow&&ps.every(function(p){return p.ids.length<=4;})&&ids.length>0;
  var m={l:narrow?44:54,r:labelsOn?Math.min(180,30+Math.max.apply(null,ids.map(function(i){return tw(SER[i].short,13);}))):(narrow?10:16),t:30,b:28};
  var pw=W-m.l-m.r;
  var ph=st.mode==="index"?(narrow?280:400):(narrow?118:150);
  var ptop=st.mode==="index"?0:20,gap=st.mode==="index"?0:16;
  var H=m.t+ps.length*(ph+ptop)+(ps.length-1)*gap+m.b;
  var x0=st.frm-0.5,x1=st.to+0.5;
  function X(y){return m.l+(y-x0)/(x1-x0)*pw;}
  G={X:X,m:m,W:W,H:H,pw:pw,ps:[],x0:x0,x1:x1};
  var o=[];
  /* term bands */
  var plotTop=m.t,plotBot=H-m.b;
  D.terms.forEach(function(t,k){
    if(t.e<=x0||t.s>=x1)return;
    var a=X(Math.max(t.s,x0)),b=X(Math.min(t.e,x1)),w=b-a;if(w<=0)return;
    o.push('<rect x="'+a.toFixed(1)+'" y="'+plotTop+'" width="'+w.toFixed(1)+'" height="'+(plotBot-plotTop)+'" fill="var(--band'+(k%2?"B":"A")+')"/>');
    o.push('<g class="strip" data-term="'+t.id+'" role="button" tabindex="-1"><title>'+esc(t.person+", "+t.years+" (click to zoom)")+'</title><rect x="'+(a+0.5).toFixed(1)+'" y="4" width="'+Math.max(0,w-1).toFixed(1)+'" height="22" rx="4" fill="var(--strip'+(k%2?"B":"A")+')"/>');
    var lab=t.band;if(tw(lab)>w-8){lab=t.ab;if(tw(lab)>w-6)lab="";}
    if(lab)o.push('<text class="bt" x="'+((a+b)/2).toFixed(1)+'" y="19" text-anchor="middle">'+esc(lab)+'</text>');
    o.push('</g>');
  });
  /* x axis */
  var ppy=pw/(x1-x0),step=[1,2,5,10,20,50].filter(function(s){return s*ppy>=(narrow?42:48);})[0]||50;
  for(var y=Math.ceil(st.frm/step)*step;y<=st.to;y+=step){var xx=X(y);
    o.push('<line class="grid" x1="'+xx.toFixed(1)+'" x2="'+xx.toFixed(1)+'" y1="'+plotTop+'" y2="'+plotBot+'" opacity=".55"/>');
    o.push('<text x="'+xx.toFixed(1)+'" y="'+(H-m.b+17)+'" text-anchor="middle">'+y+'</text>');}
  /* panels */
  var top=m.t;
  ps.forEach(function(p,pi){
    var pt=top+ptop,pb=pt+ph;
    var vals=[],lines=[];
    p.ids.forEach(function(i){var s=SER[i],bi=st.mode==="index"?baseOf(s):null;
      if(st.mode==="index"&&!bi){lines.push({id:i,pts:[],bi:null});return;}
      var pts=[];s.pts.forEach(function(q){if(q[0]>=st.frm&&q[0]<=st.to){var v=st.mode==="index"?idx(s,q[1],bi):q[1];pts.push([q[0],v]);vals.push(v);}});
      lines.push({id:i,pts:pts,bi:bi});});
    if(st.mode==="index")vals.push(100);
    var lo=Math.min.apply(null,vals.length?vals:[0]),hi=Math.max.apply(null,vals.length?vals:[1]);
    var pad=(hi-lo)*0.06||1,nn=nice(st.mode==="real"&&lo>=0?Math.max(0,lo-pad):lo-pad,hi+pad,narrow?4:5);
    function Y(v){return pb-(v-nn.lo)/(nn.hi-nn.lo)*ph;}
    G.ps.push({ids:p.ids,Y:Y,lines:lines,top:pt,bot:pb});
    if(p.title)o.push('<text class="ptitle" x="'+m.l+'" y="'+(top+13)+'">'+esc(p.title)+'</text>');
    nn.ticks.forEach(function(v){var yy=Y(v);if(yy<pt-1||yy>pb+1)return;
      var isZero=st.mode==="index"&&Math.abs(v-100)<1e-6;
      o.push('<line class="'+(isZero?"zero":"grid")+'" x1="'+m.l+'" x2="'+(m.l+pw)+'" y1="'+yy.toFixed(1)+'" y2="'+yy.toFixed(1)+'"/>');
      var tl=st.mode==="index"?(isZero?String(st.base):pct(v)):(function(){var s=SER[p.ids[0]];var d=nn.step<1?(nn.step<0.1?2:1):0;return (s.pre==="R$ "||s.pre==="US$ "?s.pre:"")+num(v,d)+(s.suf.charAt(0)==="%"?"%":"");})();
      o.push('<text x="'+(m.l-6)+'" y="'+(yy+4).toFixed(1)+'" text-anchor="end"'+(isZero?' class="pt" style="font-size:11px"':'')+'>'+esc(tl)+'</text>');});
    if(st.mode==="index"&&st.base>=st.frm&&st.base<=st.to){var bx=X(st.base);o.push('<line class="basel" x1="'+bx.toFixed(1)+'" x2="'+bx.toFixed(1)+'" y1="'+pt+'" y2="'+pb+'"/>');}
    /* lines */
    var ends=[];
    lines.forEach(function(L){var s=SER[L.id],c=col(L.id),d="",run=[];
      function flush(){if(run.length===1){o.push('<circle cx="'+X(run[0][0]).toFixed(1)+'" cy="'+Y(run[0][1]).toFixed(1)+'" r="3" fill="'+c+'"/>');}
        else if(run.length>1){d=run.map(function(q,j){return (j?"L":"M")+X(q[0]).toFixed(1)+" "+Y(q[1]).toFixed(1);}).join("");
          o.push('<path class="ln'+(s.ok?"":" u")+'" d="'+d+'" stroke="'+c+'"/>');}run=[];}
      L.pts.forEach(function(q,j){if(j&&q[0]!==L.pts[j-1][0]+1)flush();run.push(q);});flush();
      if(L.pts.length)ends.push({id:L.id,y:Y(L.pts[L.pts.length-1][1]),x:X(L.pts[L.pts.length-1][0])});});
    if(labelsOn&&ends.length){
      ends.sort(function(a,b){return a.y-b.y;});
      for(var k=1;k<ends.length;k++)if(ends[k].y-ends[k-1].y<15)ends[k].y=ends[k-1].y+15;
      var over=ends[ends.length-1].y-(pb+4);if(over>0)ends.forEach(function(e){e.y-=over;});
      var lx=m.l+pw+8;
      ends.forEach(function(e){o.push('<line x1="'+lx+'" x2="'+(lx+12)+'" y1="'+e.y.toFixed(1)+'" y2="'+e.y.toFixed(1)+'" stroke="'+col(e.id)+'" stroke-width="3"'+(SER[e.id].ok?'':' stroke-dasharray="4 3"')+'/>');
        o.push('<text class="lab" x="'+(lx+16)+'" y="'+(e.y+4).toFixed(1)+'">'+esc(SER[e.id].short)+'</text>');});
    }
    if(!p.ids.length)o.push('<text x="'+(m.l+pw/2)+'" y="'+((pt+pb)/2)+'" text-anchor="middle" class="pt">Pick a line above</text>');
    top=pb+gap;
  });
  o.push('<g id="cur"></g><rect id="hit" x="'+m.l+'" y="'+m.t+'" width="'+pw+'" height="'+(plotBot-m.t)+'" fill="transparent"/>');
  svg.setAttribute("viewBox","0 0 "+W+" "+H);svg.setAttribute("width",W);svg.setAttribute("height",H);
  svg.innerHTML='<desc id="chart-desc">Time chart, '+st.frm+" to "+st.to+'. Presidents as bands along the top.</desc>'+o.join("");
  renderCursor();
}
function renderCursor(){
  var g=document.getElementById("cur");if(!g||!G.X)return;
  var x=G.X(st.y),o=['<line class="curl" x1="'+x.toFixed(1)+'" x2="'+x.toFixed(1)+'" y1="'+G.m.t+'" y2="'+(G.H-G.m.b)+'"/>'];
  G.ps.forEach(function(p){p.lines.forEach(function(L){var s=SER[L.id];if(!L.pts)return;
    var q=L.pts.filter(function(q){return q[0]===st.y;})[0];
    if(q)o.push('<circle class="curm" cx="'+x.toFixed(1)+'" cy="'+p.Y(q[1]).toFixed(1)+'" r="5" fill="'+col(L.id)+'"/>');});});
  var yt=String(st.y),w=tw(yt,12)+12,bx=clamp(x-w/2,0,G.W-w);
  o.push('<rect class="cury" x="'+bx.toFixed(1)+'" y="'+(G.H-G.m.b+3)+'" width="'+w.toFixed(1)+'" height="19" rx="9"/><text class="curyt" x="'+(bx+w/2).toFixed(1)+'" y="'+(G.H-G.m.b+17)+'" text-anchor="middle">'+yt+'</text>');
  g.innerHTML=o.join("");
}
/* ---------- year panel */
function renderPanel(){
  var y=st.y,h='<h3 id="year-h">'+y+'</h3>';
  var ts=D.terms.filter(function(t){return t.s<y+1&&t.e>y;});
  h+='<p class="pres">'+(ts.length?"President: "+ts.map(function(t){return '<a href="'+esc(t.href)+'"'+(st.embed?' target="_top"':'')+'>'+esc(t.person)+'</a> <span class="muted small">('+esc(t.years)+')</span>';}).join(" → "):'<span class="muted">No term in the data.</span>')+'</p>';
  var ids=sel();
  if(ids.length){h+='<ul class="vals">';
    ids.forEach(function(i){var s=SER[i],v=s.map[y],line;
      if(v!=null){line='<span class="v">'+esc(fmtv(s,v))+'</span>';
        var bi=baseOf(s);if(bi&&bi.y!==y)line+=' <span class="sm">'+esc(pct(idx(s,v,bi))+" since "+bi.y+(bi.why?" ("+bi.why+")":""))+'</span>';}
      if(v!=null&&st.mode==="index"&&s.rate)line+=' <span class="sm">(use Real values for this line)</span>';
      if(v==null)line='<span class="sm">'+(y<s.first?"no data before "+s.first:y>s.last?"no data after "+s.last:"no data for "+y+" (gap in the source)")+'</span>';
      h+='<li><span class="key'+(s.ok?"":" u")+'" style="border-top-color:'+col(i)+'"></span><span>'+line+'<br><span class="nm">'+esc(s.name)+'</span>'
        +(s.ok?"":' <span class="tag">unverified</span>')+(s.nominal?' <span class="tag nom">nominal</span>':'')
        +'<br><span class="sm">'+(s.better?esc(s.better)+" · ":"")+(s.src_u?'<a href="'+esc(s.src_u)+'" target="_blank" rel="noopener">source</a>':esc(s.src_t))+'</span></span></li>';});
    h+='</ul>';}
  var dl=D.deals[y]||[],ds=D.dis[y]||[],tgt=st.embed?' target="_top"':'';
  h+='<h4 id="year-deals-h">Deals started in '+y+' ('+dl.length+')</h4>';
  h+=dl.length?'<ul class="list">'+dl.map(function(d){return '<li><a href="'+esc(d[1])+'"'+tgt+'>'+esc(d[0])+'</a>'+(d[2]?' <span class="sm">ongoing process</span>':'')+'</li>';}).join("")+'</ul>':'<p class="none">None in the case files.</p>';
  h+='<h4 id="year-dis-h">Disasters in '+y+' ('+ds.length+')</h4>';
  h+=ds.length?'<ul class="list">'+ds.map(function(d){return '<li>'+(d[1]?'<a href="'+esc(d[1])+'"'+tgt+'>'+esc(d[0])+'</a>':esc(d[0]))+' <span class="sm">'+esc(d[2])+'</span></li>';}).join("")+'</ul>':'<p class="none">None in the disaster files.</p>';
  document.getElementById("panel").innerHTML=h;
}
function renderTable(){
  var el=document.getElementById("tbl");if(!el||st.embed)return;
  var ids=sel();if(!ids.length){el.innerHTML='<p class="muted">No line on.</p>';return;}
  var h='<table><thead><tr><th>Year</th>'+ids.map(function(i){return '<th>'+esc(SER[i].short)+'</th>';}).join("")+'</tr></thead><tbody>';
  for(var y=st.to;y>=st.frm;y--){var row=ids.map(function(i){var v=SER[i].map[y];return '<td>'+(v==null?"–":esc(fmtv(SER[i],v)))+'</td>';});
    if(row.join("").replace(/<td>–<\/td>/g,"")==="")continue;h+='<tr><td>'+y+'</td>'+row.join("")+'</tr>';}
  el.innerHTML=h+'</tbody></table>';
}
function postHeight(){if(st.embed&&window.parent!==window){try{var mn=document.querySelector("main");window.parent.postMessage({explorerHeight:Math.ceil(mn.getBoundingClientRect().bottom+window.scrollY)+8},"*");}catch(e){}}}
function render(){renderControls();renderPicker();renderChart();renderPanel();renderTable();writeHash();postHeight();}
function setYear(y){y=clamp(Math.round(y),st.frm,st.to);if(y===st.y)return;st.y=y;renderCursor();renderPanel();writeHash();postHeight();}
function zoomTerm(id){if(applyGo(id))render();}
/* ---------- events */
document.getElementById("picker").addEventListener("click",function(e){var b=e.target.closest(".chip");if(b&&!b.disabled)toggle(b.getAttribute("data-id"));});
document.getElementById("picker").addEventListener("toggle",function(e){var d=e.target;if(d.tagName==="DETAILS"&&openGroups){openGroups[d.getAttribute("data-g")]=d.open;postHeight();}},true);
Array.prototype.forEach.call(document.querySelectorAll(".mbtn"),function(b){b.addEventListener("click",function(){st.mode=b.getAttribute("data-mode");render();});});
document.getElementById("base").addEventListener("change",function(e){st.base=+e.target.value;render();});
document.getElementById("from").addEventListener("change",function(e){st.frm=+e.target.value;if(st.to<st.frm+2)st.to=Math.min(D.maxY,st.frm+2);st.y=clamp(st.y,st.frm,st.to);render();});
document.getElementById("to").addEventListener("change",function(e){st.to=+e.target.value;st.y=clamp(st.y,st.frm,st.to);render();});
var svg=document.getElementById("chart");
function yearAt(e){var r=svg.getBoundingClientRect(),x=(e.clientX-r.left)*(G.W/r.width);return G.x0+(x-G.m.l)/G.pw*(G.x1-G.x0);}
svg.addEventListener("click",function(e){var s=e.target.closest(".strip");if(s){zoomTerm(s.getAttribute("data-term"));}});
svg.addEventListener("pointerdown",function(e){if(e.target.closest(".strip"))return;dragging=true;try{svg.setPointerCapture(e.pointerId);}catch(_){}setYear(yearAt(e));});
svg.addEventListener("pointermove",function(e){if(e.pointerType==="mouse"&&!e.target.closest(".strip")||dragging)setYear(yearAt(e));});
function stop(){dragging=false;}
svg.addEventListener("pointerup",stop);svg.addEventListener("pointercancel",stop);
function onKey(e){
  var t=e.target,tag=(t&&t.tagName)||"";if(tag==="INPUT"||tag==="SELECT"||tag==="TEXTAREA")return;
  if(t!==document.body&&t!==document.documentElement&&t.id!=="chartbox"&&!(t.closest&&t.closest("#chartbox")))return;
  var d={ArrowLeft:-1,ArrowRight:1}[e.key];
  if(d){e.preventDefault();setYear(st.y+d*(e.shiftKey?5:1));}
  else if(e.key==="Home"&&t.id==="chartbox"){e.preventDefault();setYear(st.frm);}
  else if(e.key==="End"&&t.id==="chartbox"){e.preventDefault();setYear(st.to);}
}
document.addEventListener("keydown",onKey);
window.addEventListener("hashchange",function(){var go=parseHash();render();if(go&&!st.embed){var ex=document.getElementById("explore");if(ex)ex.scrollIntoView();}});
if(window.ResizeObserver){new ResizeObserver(function(){var w=Math.floor(document.getElementById("chartbox").clientWidth);if(Math.abs(w-lastW)>2){renderChart();postHeight();}}).observe(document.getElementById("chartbox"));}
else window.addEventListener("resize",function(){renderChart();});
/* ---------- start */
var go0=parseHash();
if(st.embed)document.body.classList.add("embed");
render();
if(go0&&!st.embed){var ex0=document.getElementById("explore");if(ex0)setTimeout(function(){ex0.scrollIntoView();},0);}
})();
</script>
</body></html>
"""

if __name__ == "__main__":
    build()
