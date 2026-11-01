#!/usr/bin/env python3
"""Build index.html (the main page) from data/g1..g7 (cases) and data/g8..g10 (disasters).

Run:  python3 build.py
All facts come from the data files. The prose in this script only explains the
profile, the scoring and how to read the page.
"""
import collections
import html
import json
import os
import re
import sys
from html.parser import HTMLParser

import timeline_data

TD = timeline_data.load_all()

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")
OUT = os.path.join(ROOT, "index.html")

# Explicit file lists (a glob like g1* would also catch g10).
CASE_FILES = [
    ("g1-colony", "era-1"),
    ("g2-republic", "era-2"),
    ("g3-dictatorship", "era-3"),
    ("g4-privatization", "era-4"),
    ("g5-2003-2016", "era-5"),
    ("g6-2016-2026", "era-6"),
    ("g7-cross-cutting", "era-x"),
]
DIS_FILES = ["g8-dis-mining", "g9-dis-oil", "g10-dis-hydro-land"]

ERAS = [
    ("era-1", "1500–1889: Colony and Empire", "Colony"),
    ("era-2", "1889–1964: The Republic", "Republic"),
    ("era-3", "1964–1985: Military dictatorship", "Dictatorship"),
    ("era-4", "1985–2002: Privatization", "1985–2002"),
    ("era-5", "2003–2016: Lula and Dilma", "2003–2016"),
    ("era-6", "2016–2026: Temer, Bolsonaro, Lula 3", "2016–2026"),
    ("era-x", "Cross-cutting: taxes, land grabbing, bailouts", "Cross-cutting"),
]
ERA_NAME = {e[0]: e[1] for e in ERAS}
ERA_SHORT = {e[0]: e[2] for e in ERAS}

# Signs: key -> (old stable id, mechanism group, label, definition, test)
SIGNS = collections.OrderedDict([
    ("land-grant", ("sign-lg", "gA", "Land or resource grant",
        "Public land, forest, subsoil or water rights go to a private holder.",
        "Does a title, lease or concession cover land or a natural resource? How many hectares, for how long, at what fee?")),
    ("exclusive-privilege", ("sign-mo", "gA", "Exclusive privilege",
        "One holder gets the sole right to trade, run or extract in a sector or place.",
        "Is there a monopoly or exclusivity clause? For how many years? Who is barred?")),
    ("below-value-price", ("sign-up", "gA", "Below-value or no-contest price",
        "The price is far under other estimates, or the contest was skipped, thin or built on a seller-friendly method.",
        "Compare the price with the seller's own base case and outside valuations. Was there one bidder, or a renewal with no auction?")),
    ("public-money-private-control", ("sign-pf", "gB", "Public money, private control",
        "State banks, funds or pension funds supply capital or credit while private owners keep control and upside.",
        "Who put in the cash? Who votes the shares? Who is paid first?")),
    ("paid-in-paper-or-cheap-credit", ("sign-pn", "gB", "Paid in paper or cheap credit",
        "The buyer pays with discounted securities, long instalments or loans from a public bank.",
        "What share of the price is cash on day one? Who lends the rest?")),
    ("guaranteed-return", ("sign-gr", "gB", "Guaranteed return",
        "The state promises the investor a minimum return or payment whatever happens.",
        "Is there an interest guarantee, a revenue floor or a minimum-payment clause?")),
    ("subsidy-or-tax-break", ("sign-si", "gB", "Subsidy or tax break",
        "Tax waivers, cheap power or subsidised credit lower the private cost.",
        "Is there an exemption, a special tariff or a below-market loan? What does it cost per year and what did it buy?")),
    ("law-rewritten-for-deal", ("sign-lr", "gC", "Law rewritten for the deal",
        "A law, decree or provisional measure changes the rules for, or just before, the deal.",
        "Did a rule change come shortly before the sale or grant? Who asked for it?")),
    ("rights-legalised-after-fact", ("sign-rl", "gC", "Rights legalised after the fact",
        "Past occupation or clearing is made legal by an amnesty or regularisation.",
        "Does a cut-off date turn earlier illegal occupation into title? Has the date moved?")),
    ("regulator-absent-or-late", ("sign-ra", "gC", "Regulator absent, late or sidelined",
        "No independent regulator on the day, or oversight arrives later or is overruled.",
        "Who regulates this market on the day of sale? Was that body created later?")),
    ("conflict-of-interest-or-kickbacks", ("sign-cv", "gC", "Conflict of interest or alleged kickbacks",
        "The valuer or lender had ties to bidders, or prosecutors, courts or plea deals allege bribes. Allegations are not findings.",
        "Who valued the asset and who else do they work for? Are there investigations or plea deals?")),
    ("bailout", ("sign-bo", "gD", "Bailout",
        "The state absorbs losses or debts when the private venture fails.",
        "If it fails, who pays? Is a public bank the main creditor?")),
    ("cleanup-before-sale", ("sign-cl", "gD", "Cleanup before sale",
        "The state takes the debts or liabilities first, then sells the cleaned-up asset.",
        "Were debts moved to the Treasury or the Union before the auction?")),
])

MECHS = [
    ("mech-assets", "gA", "1. Hand over the asset",
     "Public land, rights or markets pass to a private holder, often on thin terms."),
    ("mech-money", "gB", "2. Public money behind private control",
     "The public side carries cost and risk; the private side keeps control and upside."),
    ("mech-rules", "gC", "3. Rules bent to fit",
     "The legal frame, the overseer or the valuer is shaped in favour of the deal."),
    ("mech-losses", "gD", "4. Losses go public",
     "Debts and failures are absorbed by the state, before or after the sale."),
]

# The same deal told twice: once in an era, once in the cross-cutting group.
OVERLAPS = [
    ("x-10", "e4-13"), ("x-13", "e4-17"), ("x-13", "e4-30"), ("x-20", "e5-13"),
    ("x-06", "e3-11"), ("x-01", "e3-07"), ("x-23", "e5-14"), ("x-22", "e5-10"),
    ("x-19", "e6-28"),
]

WEALTH_KINDS = [
    ("price-gap", "Price gap"),
    ("subsidy", "Subsidy"),
    ("bailout", "Bailout"),
    ("debt-absorbed", "Debt absorbed"),
    ("public-finance-to-buyer", "Public finance to buyer"),
    ("guaranteed-return", "Guaranteed return"),
    ("land-area", "Land area"),
]
KIND_LABEL = dict(WEALTH_KINDS)
STATUSES = ["verified", "corrected", "disputed", "unverified"]

# Stage-1 fact-check tallies, as reported by the fact-checkers (approximate).
STAGE1 = [
    # group, era/page, checked, confirmed, corrected, unconfirmable
    ("Colony and Empire", "era-1", 95, 55, 14, 26),
    ("Republic 1889–1964", "era-2", 115, 62, 19, 28),
    ("Dictatorship 1964–1985", "era-3", 105, 62, 15, 28),
    ("Privatization 1985–2002", "era-4", 153, 86, 32, 35),
    ("2003–2016", "era-5", 157, 76, 28, 51),
    ("2016–2026", "era-6", 146, 72, 33, 37),
    ("Disasters: mining", "dis", 95, 40, 17, 30),
    ("Disasters: oil, chemical, energy", "dis", 90, 38, 30, 22),
    ("Disasters: hydro, land, agro", "dis", 170, 76, 45, 36),
]
# New research entries written by the gap-filling notes (11-20).
ADDED = [
    ("Colony and Empire", 8), ("Republic", 10), ("Dictatorship", 14),
    ("1990s federal", 11), ("State privatizations", 21), ("2003–2016", 11),
    ("2016–2026", 13), ("Taxes and royalties", 8), ("Public land grabbing", 9),
    ("Debt and bailouts", 9), ("Disasters: mining", 14), ("Disasters: oil", 13),
    ("Disasters: hydro and land", 13),
]
OLD_CASES = 116          # cases on the page before the double-check
OLD_DISASTERS = 60       # rows on disasters.html before the double-check

E = html.escape


def esc(s):
    return E("" if s is None else str(s))


def url_ok(u):
    return isinstance(u, str) and u.startswith(("http://", "https://"))


def load(name):
    with open(os.path.join(DATA, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


# ---------------------------------------------------------------- load data
cases = []
for fname, era in CASE_FILES:
    for c in load(fname):
        c = dict(c)
        c["_group"] = fname
        e = era
        if fname == "g4-privatization" and isinstance(c["start_year"], int) and c["start_year"] > 2002:
            e = "era-6" if c["start_year"] >= 2016 else "era-5"
            c["_moved"] = True
        c["_era"] = e
        c["_score"] = len(c.get("signs") or [])
        figs = c.get("figures") or []
        good = sum(1 for f in figs if f.get("status") in ("verified", "corrected"))
        c["_ev"] = (good / len(figs)) if figs else 0.0
        c["_good"] = good
        cases.append(c)
BYID = {c["id"]: c for c in cases}
assert len(BYID) == len(cases), "duplicate case ids"
for s in (s for c in cases for s in c["signs"]):
    assert s in SIGNS, s
N_CASES = len(cases)

SEEALSO = collections.defaultdict(list)
for a, b in OVERLAPS:
    assert a in BYID and b in BYID, (a, b)
    SEEALSO[a].append(b)
    SEEALSO[b].append(a)

disasters = []
for fname in DIS_FILES:
    for d in load(fname):
        d = dict(d)
        d["_group"] = fname
        disasters.append(d)

ERA_ORDER = {e[0]: i for i, e in enumerate(ERAS)}
cases_by_era = collections.defaultdict(list)
for c in cases:
    cases_by_era[c["_era"]].append(c)
for k in cases_by_era:
    cases_by_era[k].sort(key=lambda c: (c["start_year"], c["id"]))

all_figs = [(c, f) for c in cases for f in c["figures"]]
fig_status = collections.Counter(f["status"] for _, f in all_figs)
dis_figs = [f for d in disasters for f in d["figures"]]
dis_status = collections.Counter(f.get("status") for f in dis_figs)
sign_count = collections.Counter(s for c in cases for s in c["signs"])
sign_era = collections.defaultdict(collections.Counter)
for c in cases:
    for s in c["signs"]:
        sign_era[s][c["_era"]] += 1

# ---------------------------------------------------------------- helpers


def pill(status, note=""):
    st = status if status in STATUSES else "unverified"
    t = f' title="{esc(note)}"' if note else ""
    return f'<span class="pill s-{st}"{t}>{esc(st)}</span>'


def chip(sign):
    sid, g, label, defn, _ = SIGNS[sign]
    return f'<a class="chip {g}" href="#{sid}" title="{esc(defn)}">{esc(label)}</a>'


def case_link(cid, text=None):
    c = BYID[cid]
    return f'<a href="#{cid}">{esc(text if text is not None else c["title"])}</a>'


def source_link(u, text="source"):
    if url_ok(u):
        return f'<a href="{esc(u)}" rel="noopener">{esc(text)}</a>'
    return '<span class="muted">no link</span>'


def fmt_value(f):
    v = f.get("value")
    cur = f.get("currency") or ""
    s = esc(v)
    if cur and cur not in ("n/a", "other") and not isinstance(v, str):
        s += f' <span class="muted">{esc(cur)}</span>'
    elif cur and cur not in ("n/a", "other", "") and isinstance(v, str):
        s += f' <span class="muted small">({esc(cur)})</span>'
    return s


def mini_status(figs):
    cnt = collections.Counter(f.get("status") for f in figs)
    if not figs:
        return '<span class="muted small">no figures</span>'
    parts = []
    for st in STATUSES:
        if cnt[st]:
            parts.append(f'<span class="pill s-{st}" title="{cnt[st]} {st}">{cnt[st]} {st[:5]}.</span>')
    return " ".join(parts)


def stack_bar(cnt, total):
    if not total:
        return ""
    segs = "".join(
        f'<i class="seg s-{st}" style="width:{100*cnt[st]/total:.2f}%" title="{cnt[st]} {st}"></i>'
        for st in STATUSES if cnt[st])
    return f'<span class="stk">{segs}</span>'


def year_of(v):
    if isinstance(v, int):
        return v
    m = re.search(r"(1[5-9]\d\d|20\d\d)", str(v or ""))
    return int(m.group(1)) if m else None


def num(s):
    return float(s.replace(",", ""))


UNIT = {"billion": 1e9, "bn": 1e9, "bi": 1e9, "million": 1e6, "mn": 1e6, "mi": 1e6, "thousand": 1e3}


def money_amount(c, f):
    """Return (currency, amount) for clean, single magnitudes; else None."""
    cur = (f.get("currency") or "").strip()
    lc = cur.lower()
    v = f.get("value")
    if any(k in lc for k in ("cruz", "cr$", "réis", "reis", "percent", "per kwh", "gdp", "unclear")):
        return None
    res = None
    if isinstance(v, (int, float)):
        if lc == "brl million":
            res = ("BRL", float(v) * 1e6)
        elif lc == "usd million":
            res = ("USD", float(v) * 1e6)
    else:
        s = str(v)
        if "%" in s or "cruz" in s.lower() or "Cr$" in s:
            return None
        if lc in ("brl million", "usd million"):
            m = re.match(r"\s*(?:about |more than |over |at least |up to )?(\d[\d,]*(?:\.\d+)?)\s*$", s)
            if m:
                res = (lc[:3].upper(), num(m.group(1)) * 1e6)
        else:
            m = re.search(r"(R\$|US\$)\s?(\d[\d,]*(?:\.\d+)?)\s*(billion|bn|bi|million|mn|mi|thousand)\b", s)
            if m and is_range(s, m):
                return None
            if m:
                res = ("BRL" if m.group(1) == "R$" else "USD", num(m.group(2)) * UNIT[m.group(3)])
            elif lc in ("brl", "usd"):
                m = re.match(r"\s*(?:about |more than |over |at least |up to )?(\d[\d,]*(?:\.\d+)?)\s*(billion|bn|bi|million|mn|mi)\b", s)
                if m:
                    res = (lc.upper(), num(m.group(1)) * UNIT[m.group(2)])
    if not res:
        return None
    if res[0] == "BRL":
        y = year_of(f.get("value_year")) or c["start_year"]
        if y < 1994:          # the real exists only from July 1994
            return None
    return res


RANGE = re.compile(r"\d[\d,.]*\s*(?:-|–|to)\s*(?:R\$|US\$)?\s?\d")


def is_range(s, m):
    """True if the matched number is part of a range like '80,000-90,000'."""
    return bool(RANGE.search(s[:m.end()]))


def land_ha(f):
    v = f.get("value")
    cur = (f.get("currency") or "").lower()
    if isinstance(v, (int, float)):
        return float(v) if cur == "ha" else None
    s = str(v)
    if "%" in s or "acre" in s:
        return None
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(million\s*)?(ha|hectares)\b", s)
    if m and is_range(s, m):
        return None
    if m:
        return num(m.group(1)) * (1e6 if m.group(2) else 1)
    m = re.search(r"(\d[\d,]*(?:\.\d+)?)\s*(million\s*)?(km2|km²)", s)
    if m:
        return num(m.group(1)) * (1e6 if m.group(2) else 1) * 100
    return None


def human(x, cur):
    pre = {"BRL": "R$ ", "USD": "US$ "}.get(cur, "")
    if cur == "ha":
        if x >= 1e6:
            return f"{x/1e6:,.2f} million ha"
        return f"{x:,.0f} ha"
    if x >= 1e9:
        return f"{pre}{x/1e9:,.2f} bn"
    if x >= 1e6:
        return f"{pre}{x/1e6:,.1f} mn"
    return f"{pre}{x:,.0f}"


def bar_chart(items, cur, cap=None):
    """items: list of (amount, label_html, value_html, row_id). Bars compare within this chart only."""
    items = sorted(items, key=lambda t: -t[0])
    extra = 0
    if cap and len(items) > cap:
        extra = len(items) - cap
        items = items[:cap]
    mx = max(t[0] for t in items) if items else 1
    rows = []
    for amt, lab, val, rid in items:
        w = max(0.6, 100 * amt / mx)
        rows.append(
            f'<div class="brow"><span class="bl">{lab}</span>'
            f'<span class="bt"><i style="width:{w:.2f}%"></i></span>'
            f'<span class="bv"><a href="#{rid}">{esc(human(amt, cur))}</a></span></div>')
    more = f'<p class="muted small">{extra} smaller figures are in the table only.</p>' if extra else ""
    return '<div class="chart">' + "".join(rows) + "</div>" + more


# ---------------------------------------------------------------- flagship selection


def overlap_rep(c):
    """For an overlapping deal, the entry kept in the flagship table."""
    group = [c["id"]] + SEEALSO.get(c["id"], [])
    best = sorted((BYID[i] for i in group),
                  key=lambda x: (-x["_score"], x["id"].startswith("x-"), -x["_ev"]))[0]
    return best["id"]


def rank_key(c):
    return (-c["_score"], -c["_ev"], c["start_year"], c["id"])


eligible = [c for c in cases if c["_score"] > 0 and overlap_rep(c) == c["id"]]
flag_ids = set(c["id"] for c in eligible if c["_score"] >= 4)
for era, *_ in ERAS:
    for c in sorted((c for c in eligible if c["_era"] == era), key=rank_key)[:2]:
        flag_ids.add(c["id"])
flagship = sorted((BYID[i] for i in flag_ids), key=rank_key)
assert 14 <= len(flagship) <= 18, len(flagship)

zero_sign = [c for c in cases if c["_score"] == 0]

# ---------------------------------------------------------------- sections
parts = []


def H(s):
    parts.append(s)


# ---- double-check
s1 = {k: sum(r[i] for r in STAGE1) for k, i in (("checked", 2), ("confirmed", 3), ("corrected", 4), ("unconf", 5))}
s1w = {k: sum(r[i] for r in STAGE1 if r[1] != "dis") for k, i in (("checked", 2), ("confirmed", 3), ("corrected", 4), ("unconf", 5))}
added_total = sum(n for _, n in ADDED)
n_good = fig_status["verified"] + fig_status["corrected"]

era_status_rows = []
for era, name, short in ERAS:
    cnt = collections.Counter(f["status"] for c in cases_by_era[era] for f in c["figures"])
    tot = sum(cnt.values())
    era_status_rows.append(
        f'<div class="brow"><span class="bl"><a href="#{era}">{esc(short)}</a> <span class="muted small">({tot})</span></span>'
        f'{stack_bar(cnt, tot)}<span class="bv small">{cnt["verified"]+cnt["corrected"]} of {tot} confirmed or fixed</span></div>')
dtot = sum(dis_status.values())
era_status_rows.append(
    f'<div class="brow"><span class="bl"><a href="disasters.html">Disasters</a> <span class="muted small">({dtot})</span></span>'
    f'{stack_bar(dis_status, dtot)}<span class="bv small">{dis_status["verified"]+dis_status["corrected"]} of {dtot} confirmed or fixed</span></div>')

stage_rows = "".join(
    f'<tr><td>{esc(g)}</td><td class="num">{a}</td><td class="num">{b}</td><td class="num">{cc}</td><td class="num">{d}</td></tr>'
    for g, _, a, b, cc, d in STAGE1)

# ---- answers on the timeline page (ids kept from the earlier hand-written sections)
_tp = TD["term_people"]
_n_terms = len(TD["terms"])
_n_people = len(TD["people"])
_n_links = sum(len(p["case_links"]) for p in TD["people"].values())
_n_act = sum(1 for p in TD["people"].values() for l in p["case_links"] if l["basis"] == "documented-act")
H(f'''<section id="decision-makers"><h2 id="decision-makers-h">Who was president, and who were the appointed people who could decide these transfers?</h2>
<p class="lead"><strong>Done: every term from 1822 to today now lists its ruler and decision-makers</strong>, on the <a href="timeline.html#terms">timeline page</a>.</p>
<p>The data maps <strong>{_n_people} people</strong> across {_n_terms} terms and the colony years. Each case below now has a <strong>"Decided by"</strong> line with the people linked to it.</p>
<h3 id="dm-who">Who counts as a decision-maker</h3>
<p>The ruler, the money ministers, the ministers over the assets, the heads of the state banks and of the companies being sold, regulators and sale councils, and the negotiators with foreign powers.</p>
<h3 id="dm-what">What each record shows</h3>
<p>Posts with dates and who appointed them, work before and after, foreign ties, the role in each case, and investigations with their outcome exactly as recorded. <strong>Every entry has its own status pill</strong>; unverified ones stay visible and marked.</p>
<h3 id="dm-how">Where to see it</h3>
<ul>
<li><a href="timeline.html#terms">Every term</a>: scorecard, decision-makers and the cases that started.</li>
<li><a href="timeline.html#both-sides">People on both sides</a>: government, then buyers, foreign firms or lenders.</li>
<li><a href="timeline.html#foreign">Foreign counterparts by country</a>.</li>
</ul>
<div class="callout warn"><strong>Most links are "in office at the time".</strong> Only {_n_act} of {_n_links} person-to-case links name the person acting in the case. The rest say who held the post when it started.</div>
</section>''')
H(f'''<section id="political-power"><h2 id="political-power-h">How can we analyse political power in every term?</h2>
<p class="lead"><strong>Done: each of the {_n_terms} terms has the same six-question scorecard</strong>, set next to the money and inequality data. See <a href="timeline.html#method">how it is scored</a>.</p>
<ol>
<li>Who ruled, and how did they get there?</li>
<li>Who could choose them? (registered voters as % of the population)</li>
<li>Who backed them?</li>
<li>What checked them? (V-Dem democracy index)</li>
<li>What did they hand over? (the cases that started in the term)</li>
<li>Who gained and who lost? (change in minimum wage, Gini, state-company investment, public debt, V-Dem)</li>
</ol>
<div class="callout"><strong>Patterns, not proof of motive.</strong> Seats in Congress are missing for every term; see the <a href="timeline.html#gaps">data gaps</a>.</div>
</section>''')
H(f'''<section id="timeline-in-progress"><h2 id="timeline-in-progress-h">Can we see it on a timeline, crossed with purchasing power and wealth concentration?</h2>
<p class="lead"><strong>Done: the <a href="timeline.html#timeline">timeline</a> stacks every term, case and data series on one year axis</strong>, 1822–2026, with the colony cases above it.</p>
<ul>
<li><strong>Public patrimony:</strong> public and state-company investment, privatization money by year, state-company counts, public debt.</li>
<li><strong>Purchasing power:</strong> real minimum wage, household income, GDP per person.</li>
<li><strong>Concentration:</strong> Gini, top 1% and top 10% shares, land Gini, labour share.</li>
<li><strong>Political power:</strong> democracy index, voters, company campaign money.</li>
</ul>
<p>Hover or tap a year to read every value and who was in power.</p>
</section>''')

H(f'''<section id="double-check"><span id="recheck-in-progress"></span><span id="in-progress"></span>
<h2 id="double-check-h">What did the double-check find?</h2>
<p class="lead">Fact-checkers re-opened the sources for <strong>about {s1["checked"]:,} figures</strong>. About <strong>{s1["confirmed"]:,} held up</strong>, <strong>{s1["corrected"]} needed a correction</strong>, now applied, and about {s1["unconf"]} could not be confirmed.</p>
<p>The research also grew. Gap-filling notes added {added_total} new entries or additions to existing ones. This page now has <strong>{N_CASES} entries</strong> (it had {OLD_CASES}), and the <a href="disasters.html">disasters page</a> has {len(disasters)} (it had {OLD_DISASTERS}).</p>
<div class="callout"><strong>Still open:</strong> {fig_status["unverified"]} of {len(all_figs)} figures on this page are <strong>unverified</strong> and {fig_status["disputed"]} are <strong>disputed</strong>. Each figure keeps its own pill, so you can see which is which. Hover a pill to read why.</div>
<h3 id="dc-status">Where each figure stands now</h3>
<p class="muted small">Counted from the data files. Green = verified, blue = corrected, red = disputed, yellow = unverified.</p>
<div class="chart">{"".join(era_status_rows)}</div>
<p class="legend">{pill("verified")} confirmed on an opened page · {pill("corrected")} was wrong, now fixed · {pill("disputed")} sources disagree, range shown · {pill("unverified")} only a snippet, or not re-checked</p>
<h3 id="dc-corrections">The biggest corrections</h3>
<ul class="tight">
<li><strong>Vale 1997:</strong> the price of R$&nbsp;3.338&nbsp;bn is about US$&nbsp;3.0&nbsp;bn, not US$&nbsp;3.3&nbsp;bn. See <a href="#e4-19">Vale</a>.</li>
<li><strong>Eletropaulo:</strong> it sold <strong>at</strong> the minimum price, not above it, and the AES default was in 2003. See <a href="#e4-23">Eletropaulo</a>.</li>
<li><strong>PROER:</strong> the per-bank amounts were wrong. They now follow the CPI Proer report. See <a href="#e4-13">PROER</a> and <a href="#x-10">its cross-cutting entry</a>.</li>
<li><strong>Grampo do BNDES:</strong> the tapes came out in Nov 1998, and the TCU puts BNDES help to Telemar at R$&nbsp;686.8&nbsp;mn. See <a href="#e4-26">the case</a>.</li>
<li><strong>EBX and JBS:</strong> R$&nbsp;10.4&nbsp;bn for EBX was approved, not paid out. The R$&nbsp;5.08&nbsp;bn JBS figure is a TCU audit estimate, and a later TCU ruling found no debit. See <a href="#e5-08">EBX</a> and <a href="#e5-07">JBS</a>.</li>
<li><strong>Eletrobras:</strong> R$&nbsp;46&nbsp;bn is only one part of a TCU minister's undervaluation argument. His full gap is about R$&nbsp;63&nbsp;bn (R$&nbsp;130.4&nbsp;bn against R$&nbsp;67&nbsp;bn). See <a href="#e6-17">Eletrobras</a>.</li>
<li><strong>Correios:</strong> the Treasury rejected a R$&nbsp;20&nbsp;bn loan and authorized R$&nbsp;12&nbsp;bn on 18 Dec 2025. No R$&nbsp;10&nbsp;bn figure exists. See <a href="#e6-20">Correios</a>.</li>
<li><strong>Volkswagen ranch:</strong> the investigation rests on at least 42 victims and 11 witnesses. The "1,000 victims" estimate is not in the cited pages. See <a href="#e3-15">the case</a>.</li>
<li><strong>Colony:</strong> Loronha's 400–500% profit figure is in a source after all (one secondary source), and the first Banco do Brasil's capital is now 1,200,000$000. See <a href="#e1-01">Loronha</a> and <a href="#e1-13">Banco do Brasil</a>.</li>
</ul>
<h3 id="dc-added">What was added</h3>
<ul class="tight">
<li>A new group, <a href="#era-x">cross-cutting</a>, with {len(cases_by_era["era-x"])} entries on tax breaks, land grabbing and bailouts.</li>
<li>State privatizations (electricity, water, banks), PND totals and BNDES loans to buyers in <a href="#era-4">1985–2002</a>.</li>
<li>Bank rescues, the nuclear deal, Itaipu and Proálcool in <a href="#era-3">the dictatorship</a>. Airports, roads, refinery sales and the orçamento secreto in <a href="#era-6">2016–2026</a>.</li>
<li>A <a href="#wealth-moved">table of every amount</a> moved ({sum(1 for _, f in all_figs if f["kind"] in KIND_LABEL)} figures), each with its status pill.</li>
</ul>
<details class="more"><summary>Fact-check tallies by group</summary>
<p class="muted small">These are the fact-checkers' own approximate counts. The status counts in the chart above come from the data files.</p>
<div class="tw"><table class="narrow"><thead><tr><th>Group</th><th>Checked</th><th>Confirmed</th><th>Corrected</th><th>Not confirmable</th></tr></thead><tbody>{stage_rows}</tbody></table></div>
</details>
<div class="callout warn"><strong>"Verified" is not used the same way everywhere.</strong> For the 2003–2016 group and the mining disasters, figures from the gap-filling notes are marked verified because the researcher read the page, though nobody re-checked them. The other groups mark such figures unverified. The cross-cutting group had no separate fact-check; its statuses come from the notes' own flags.</div>
</section>''')

# ---- answer
top3 = flagship[:3]
top_signs = sign_count.most_common(5)
H(f'''<section id="answer"><h2 id="answer-h">The short answer</h2>
<p class="lead">Brazil moved public land, resources, money and markets into private hands <strong>in every era</strong>. The record has <strong>{N_CASES} entries</strong> from {min(c["start_year"] for c in cases)} to {max(c["start_year"] for c in cases)}.</p>
<ul>
<li>The profile has <strong>13 signs in 4 mechanisms</strong>. The most common: {", ".join(f"{esc(SIGNS[s][2].lower())} ({n})" for s, n in top_signs)}.</li>
<li>Highest scores: {", ".join(f"<strong>{case_link(c['id'])}</strong> ({c['_score']} of 13)" for c in top3)}. See <a href="#flagship">all scores</a>.</li>
<li>The pattern shifts over time: <strong>monopolies</strong> in the colony, <strong>public money behind private control</strong> from 1985, <strong>rewritten laws</strong> since 2016. See <a href="#by-era">signs by era</a>.</li>
<li>{n_good} of {len(all_figs)} figures are verified or corrected. Amounts are <strong>never added up</strong> across currencies or eras.</li>
</ul></section>''')

# ---- contents
era_toc = "".join(f'<li><a href="#{e}">{esc(n)}</a></li>' for e, n, _ in ERAS)
H(f'''<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ol class="toc">
<li><a href="timeline.html">Timeline page: terms, decision-makers, wages and wealth</a><ul><li><a href="#timeline-in-progress">The timeline</a></li><li><a href="#political-power">Political power in every term</a></li><li><a href="#decision-makers">Who could decide</a></li></ul></li>
<li><a href="#double-check">What did the double-check find?</a><ul><li><a href="#dc-status">Status now</a></li><li><a href="#dc-corrections">Biggest corrections</a></li><li><a href="#dc-added">What was added</a></li></ul></li>
<li><a href="#answer">The short answer</a></li>
<li><a href="#profile">The profile</a><ul><li><a href="#mech-assets">1. Hand over the asset</a></li><li><a href="#mech-money">2. Public money behind private control</a></li><li><a href="#mech-rules">3. Rules bent to fit</a></li><li><a href="#mech-losses">4. Losses go public</a></li><li><a href="#by-era">Signs by era</a></li><li><a href="#counter-signs">Entries with no sign</a></li><li><a href="#scoring">How the score works</a></li><li><a href="#flagship">Flagship cases scored</a></li></ul></li>
<li><a href="#wealth-moved">How much moved</a><ul><li><a href="#land-chart">Land</a></li><li><a href="#money-charts">Money by currency and era</a></li><li><a href="#transfers-table">Every figure</a></li></ul></li>
<li><a href="#history">History by era</a><ul>{era_toc}</ul></li>
<li><a href="#disasters-link">Transfers linked to later disasters</a></li>
<li><a href="#gaps">What could not be verified</a></li></ol></nav>''')

# ---- profile
mech_html = []
for mid, g, title, sub in MECHS:
    cards = []
    for key, (sid, sg, label, defn, test) in SIGNS.items():
        if sg != g:
            continue
        with_sign = [c for c in cases if key in c["signs"] and overlap_rep(c) == c["id"]]
        exs = []
        for era, *_ in ERAS:
            cand = sorted((c for c in with_sign if c["_era"] == era), key=rank_key)
            if cand:
                exs.append(cand[0])
        exs = sorted(sorted(exs, key=rank_key)[:6], key=lambda c: c["start_year"])
        ex_html = " ".join(
            f'<a class="ex" href="#{c["id"]}" title="{esc(c["title"])}">{esc(c["id"])} <span class="muted">({c["start_year"]})</span></a>'
            for c in exs)
        dist = " · ".join(f'{esc(ERA_SHORT[e])} {sign_era[key][e]}' for e, *_ in ERAS if sign_era[key][e])
        cards.append(
            f'<article class="sign {g}" id="{sid}"><h4 id="{sid}-h">{esc(label)}</h4><p>{esc(defn)}</p>'
            f'<p class="spot"><strong>Spot it:</strong> {esc(test)}</p>'
            f'<p class="exs"><strong>Cases:</strong> {ex_html}</p>'
            f'<p class="muted small">Tagged in <strong>{sign_count[key]} of {N_CASES}</strong> entries. By era: {dist}.</p></article>')
    mech_html.append(f'<h3 id="{mid}">{esc(title)}</h3><p class="muted">{esc(sub)}</p><div class="signs">{"".join(cards)}</div>')

# heat table: signs x eras
mx_cell = max(sign_era[s][e] for s in SIGNS for e, *_ in ERAS)
heat_rows = []
for key, (sid, g, label, *_r) in SIGNS.items():
    cells = []
    for e, *_ in ERAS:
        n = sign_era[key][e]
        a = 0 if not n else 0.15 + 0.85 * n / mx_cell
        cells.append(f'<td class="heat" style="--a:{a:.2f}">{n or ""}</td>')
    heat_rows.append(f'<tr><th scope="row"><a class="chip {g}" href="#{sid}">{esc(label)}</a></th>{"".join(cells)}<td class="num"><b>{sign_count[key]}</b></td></tr>')
era_heads = "".join(f'<th><a href="#{e}">{esc(s)}</a><br><span class="muted small">{len(cases_by_era[e])}</span></th>' for e, _, s in ERAS)

zero_list = ", ".join(case_link(c["id"]) for c in sorted(zero_sign, key=lambda c: c["start_year"]))

fl_rows = []
for c in flagship:
    w = 100 * c["_score"] / 13
    chips = " ".join(chip(s) for s in c["signs"])
    nf = len(c["figures"])
    ev = f'{stack_bar(collections.Counter(f["status"] for f in c["figures"]), nf)}<span class="small">{c["_good"]} of {nf}</span>' if nf else '<span class="muted small">none</span>'
    also = ""
    if SEEALSO.get(c["id"]):
        also = '<br><span class="muted small">Also: ' + ", ".join(f'<a href="#{i}">{i}</a>' for i in SEEALSO[c["id"]]) + "</span>"
    fl_rows.append(
        f'<tr id="fl-{c["id"]}"><td><a href="#{c["id"]}">{esc(c["title"])}</a>{also}</td><td class="nw">{esc(c["year"])}</td>'
        f'<td class="nw"><a href="#{c["_era"]}">{esc(ERA_SHORT[c["_era"]])}</a></td>'
        f'<td class="sc"><span class="bar"><i style="width:{w:.1f}%"></i></span><b>{c["_score"]}</b> / 13</td>'
        f'<td>{chips}</td><td class="ev">{ev}</td></tr>')

H(f'''<section id="profile"><h2 id="profile-h">What a public-to-private transfer looks like: the profile</h2>
<p class="lead">A transfer is a deal where <strong>public wealth or power ends up in private hands</strong>: land, a monopoly, a company, cheap money or a debt the public takes over.</p>
<p>Across 500 years the same <strong>13 signs</strong> keep showing up. They fall into <strong>4 mechanisms</strong>: hand over the asset, put public money behind private control, bend the rules, and let the losses go public.</p>
<p>A deal does not need every sign. The more signs it shows, the closer it is to the pattern. Each card below has a one-line test you can run on a new deal.</p>
{"".join(mech_html)}
<h3 id="by-era">Which signs show up in which era</h3>
<p>Each number counts the entries in that era tagged with the sign. Darker means more. Eras differ in size, so compare <strong>shapes</strong>, not totals.</p>
<div class="tw"><table class="heatmap"><thead><tr><th>Sign</th>{era_heads}<th>All</th></tr></thead><tbody>{"".join(heat_rows)}</tbody></table></div>
<p class="muted small">The colony leans on exclusive privileges. From 1985 to 2016, public money behind private control is the most common sign. From 2016, rewritten laws lead. Bailouts appear in every era from the Republic on.</p>
<h3 id="counter-signs">Entries with no sign tagged</h3>
<p>{len(zero_sign)} entries have <strong>no sign</strong>. Some are state counter-moves or reversals, some are weak fits, and some have thin sources. They are listed, not scored:</p>
<p class="small">{zero_list}</p>
<h3 id="scoring">How the score works</h3>
<ol class="steps">
<li>Each sign tagged on an entry is worth <strong>1 point</strong>. The maximum is 13.</li>
<li>The signs were tagged by the researchers who built the data files, from the notes. <strong>The fact-check did not test the signs</strong>, only the figures.</li>
<li>So the table also shows <strong>evidence</strong>: how many of the entry's figures are verified or corrected.</li>
<li>The score counts signs in the record. It does <strong>not</strong> measure the size of the transfer, who is at fault, or whether the deal was a mistake.</li>
<li>A missing sign means "not found in the sources", not "absent". Old cases have thin records and score lower for that reason.</li>
<li>The old ½-point rule is gone. The data no longer grades each sign, so every sign counts the same.</li>
</ol>
<h3 id="flagship">Flagship cases scored ({len(flagship)})</h3>
<p>Every deal with <strong>4 or more signs</strong>, plus the top two of each era. A deal told twice (in an era and in the cross-cutting group) appears once.</p>
<div class="tw"><table class="wide"><thead><tr><th>Case</th><th>Years</th><th>Era</th><th>Score</th><th>Signs found</th><th>Evidence</th></tr></thead><tbody>{"".join(fl_rows)}</tbody></table></div>
<p class="muted small">Chip colour shows the mechanism. Evidence = figures verified or corrected, out of all figures for that entry.</p>
</section>''')

# ---- wealth moved
wrows = []
land_items = []
money_groups = collections.defaultdict(list)
kind_era = collections.defaultdict(collections.Counter)
n_w = 0
for era, *_ in ERAS:
    for c in cases_by_era[era]:
        k = 0
        for f in c["figures"]:
            if f["kind"] not in KIND_LABEL:
                continue
            k += 1
            n_w += 1
            rid = f'w-{c["id"]}-{k}'
            kind_era[f["kind"]][era] += 1
            lab = f'<a href="#{c["id"]}">{esc(c["id"])}</a> {esc(f["label"])} <span class="muted small">({esc(f.get("value_year") or "year n/a")})</span> {pill(f["status"], f.get("note"))}'
            if f["kind"] == "land-area":
                ha = land_ha(f)
                if ha:
                    land_items.append((ha, lab, "", rid))
            else:
                m = money_amount(c, f)
                if m:
                    money_groups[(m[0], era)].append((m[1], lab, "", rid))
            wrows.append(
                f'<tr id="{rid}"><td class="nw"><a href="#{c["id"]}">{esc(c["id"])}</a></td>'
                f'<td>{esc(c["title"])}</td><td class="nw">{esc(KIND_LABEL[f["kind"]])}</td>'
                f'<td>{esc(f["label"])}</td><td>{fmt_value(f)}</td><td class="nw">{esc(f.get("value_year") or "")}</td>'
                f'<td>{pill(f["status"], f.get("note"))}</td><td class="src">{esc(f.get("estimator") or "")}<br>{source_link(f.get("source_url"))}</td></tr>')

kind_rows = []
mxk = max(kind_era[k][e] for k in KIND_LABEL for e, *_ in ERAS)
for k, lab in WEALTH_KINDS:
    cells = "".join(
        f'<td class="heat" style="--a:{(0 if not kind_era[k][e] else 0.15 + 0.85*kind_era[k][e]/mxk):.2f}">{kind_era[k][e] or ""}</td>'
        for e, *_ in ERAS)
    kind_rows.append(f'<tr><th scope="row">{esc(lab)}</th>{cells}<td class="num"><b>{sum(kind_era[k].values())}</b></td></tr>')

money_html = []
for cur, cname in (("BRL", "Reais (R$), 1994 onward"), ("USD", "US dollars")):
    for era, name, short in ERAS:
        items = money_groups.get((cur, era))
        if not items:
            continue
        money_html.append(f'<h4 id="money-{cur.lower()}-{era}">{esc(cname)}: {esc(name)} <span class="muted small">({len(items)} figures)</span></h4>'
                          + bar_chart(items, cur, cap=12))
n_money = sum(len(v) for v in money_groups.values())
n_money_kinds = sum(1 for _, f in all_figs if f["kind"] in KIND_LABEL and f["kind"] != "land-area")
n_land_kinds = sum(1 for _, f in all_figs if f["kind"] == "land-area")

H(f'''<section id="wealth-moved"><h2 id="wealth-moved-h">How much moved: every numbered transfer</h2>
<p class="lead"><strong>{n_w} figures</strong> put a number on a transfer: a price gap, a subsidy, a bailout, a debt taken over, public money lent to a buyer, a guaranteed return, or land handed over.</p>
<div class="callout"><strong>Nothing is added up.</strong> The figures span five centuries and many currencies (réis, pounds, cruzeiros, reais, dollars). Bars compare figures <strong>inside one chart only</strong>. Each value is in the money of the year shown, not converted to one year.</div>
<h3 id="kinds-by-era">What kind of transfer, in which era</h3>
<p>Number of figures of each kind. Darker means more.</p>
<div class="tw"><table class="heatmap"><thead><tr><th>Kind</th>{era_heads}<th>All</th></tr></thead><tbody>{"".join(kind_rows)}</tbody></table></div>
<h3 id="land-chart">Land and territory (hectares)</h3>
<p>{len(land_items)} of {n_land_kinds} land figures state a clean area in hectares or km² (km² shown as hectares, ×100). The rest (leagues, acres, counts, ranges) are in the table.</p>
<p class="callout">Some of the biggest bars are <strong>not land handed over</strong>: they are the size of a region or programme, a target, or a claimed (often fraudulent) registry title. Read each label.</p>
{bar_chart(land_items, "ha", cap=30)}
<h3 id="money-charts">Money, by currency and era</h3>
<p>{n_money} of {n_money_kinds} money figures state one clean amount in reais or dollars. Each bar is <strong>one figure</strong>, taken as the first amount in its text. Pre-1994 currencies, percentages and ranges stay in the table only.</p>
{"".join(money_html)}
<h3 id="transfers-table">Every figure, with its status</h3>
<p>Values are shown exactly as the sources give them. Hover a pill for the fact-check note.</p>
<div class="tw tall"><table class="wide"><thead><tr><th>Entry</th><th>Case</th><th>Kind</th><th>What</th><th>Value</th><th>Year</th><th>Status</th><th>Estimator and source</th></tr></thead><tbody>{"".join(wrows)}</tbody></table></div>
</section>''')

# ---- history
FIELDS = [("government", "Government"), ("what", "What happened"), ("who_got", "Who got it"),
          ("terms", "Terms"), ("mechanism", "Mechanism"), ("who_paid", "Who paid"),
          ("after", "What came after"), ("counter_view", "Counter-view")]
INTRO = {
    "era-1": "The Crown leased monopolies, granted land and guaranteed returns to private contractors.",
    "era-2": "Foreign concessions, land strips, railway guarantees and coffee rescues, then state counter-moves from the 1940s.",
    "era-3": "Fiscal incentives, Amazon land, subsidised power and the state takeover of private debt.",
    "era-4": "The National Privatization Programme, state-bank rescues and the big federal and state sales.",
    "era-5": "BNDES lending to 'national champions', big dams, oil rounds and land regularisation.",
    "era-6": "Petrobras and Eletrobras sales, new concessions, land laws and tax regimes.",
    "era-x": "Long-running channels that cut across eras: tax waivers, land grabbing and bank rescues.",
}
hist = []
for era, name, short in ERAS:
    rows = []
    for c in cases_by_era[era]:
        dl = []
        for k, lab in FIELDS:
            v = c.get(k)
            if v:
                dl.append(f"<dt>{lab}</dt><dd>{esc(v)}</dd>")
        if c.get("figures"):
            fl = "".join(
                f'<li>{pill(f["status"], f.get("note"))} <strong>{esc(f["label"])}:</strong> {fmt_value(f)}'
                f' <span class="muted small">({esc(f.get("value_year") or "year n/a")}; {esc(f.get("estimator") or "")})</span> {source_link(f.get("source_url"))}'
                + (f'<br><span class="muted small">{esc(f["note"])}</span>' if f.get("note") else "") + "</li>"
                for f in c["figures"])
            dl.append(f'<dt>Figures</dt><dd><ul class="figs">{fl}</ul></dd>')
        srcs = [s for s in (c.get("sources") or []) if isinstance(s, dict)]
        if srcs:
            sl = "".join(f'<li>{source_link(s.get("url"), s.get("title") or s.get("url") or "source")}</li>' for s in srcs)
            dl.append(f'<dt>Sources</dt><dd><ul class="srcs">{sl}</ul></dd>')
        if SEEALSO.get(c["id"]):
            dl.append("<dt>See also</dt><dd>" + ", ".join(case_link(i, f'{i}: {BYID[i]["title"]}') for i in SEEALSO[c["id"]]) + "</dd>")
        _ppl = TD["case_people"].get(c["id"], [])
        if _ppl:
            dl.append("<dt>Decided by</dt><dd><ul class=\"figs\">" + "".join(
                f'<li>{pill(_l.get("status"))} <a href="timeline.html#{timeline_data.person_link_target(_pid, c["id"], TD)}">{esc(TD["people"][_pid]["name"])}</a>'
                f' <span class="muted small">({esc(timeline_data.BASIS_TEXT.get(_l["basis"], _l["basis"]))}; {esc(_l.get("role") or "")})</span></li>'
                for _pid, _l in _ppl) + "</ul></dd>")
        else:
            dl.append('<dt>Decided by</dt><dd class="muted">No person linked in the data yet.</dd>')
        if c.get("_moved"):
            dl.append('<dt>Note</dt><dd>From the 1990s privatization research, placed here by its start year.</dd>')
        chips = " ".join(chip(s) for s in c["signs"]) or '<span class="muted small">none tagged</span>'
        rows.append(
            f'<tr id="{c["id"]}"><td class="nw">{esc(c["year"])}<br><span class="muted small">{esc(c["id"])}</span></td>'
            f'<td><details class="case"><summary>{esc(c["title"])}</summary>'
            f'<p class="sum">{esc(c.get("summary") or "")}</p><dl>{"".join(dl)}</dl></details></td>'
            f'<td>{chips}</td><td>{mini_status(c["figures"])}</td></tr>')
    hist.append(
        f'<h3 id="{era}">{esc(name)} <span class="muted small">({len(cases_by_era[era])} entries)</span></h3>'
        f'<p class="muted">{esc(INTRO[era])}</p>'
        f'<div class="tw"><table class="hist"><thead><tr><th>Years</th><th>Case (click to open)</th><th>Signs</th><th>Figures</th></tr></thead>'
        f'<tbody>{"".join(rows)}</tbody></table></div>')

H(f'''<section id="history"><h2 id="history-h">History by era</h2>
<p class="lead">All {N_CASES} entries, oldest first within each era. <strong>Click a case</strong> to see who got what, on what terms, who paid, what came after, the counter-view and every figure.</p>
<p class="muted small">Entries keep their era from the research batch they came from. A few concessions that began just before an era's start (Mate Laranjeira 1882, Santos docks 1888) stay with the era they shaped.</p>
{"".join(hist)}
</section>''')

# ---- disasters link
dis_html_path = os.path.join(ROOT, "disasters.html")
dis_ids = set()
if os.path.exists(dis_html_path):
    with open(dis_html_path, encoding="utf-8") as fh:
        dis_ids = set(re.findall(r'id="([^"]+)"', fh.read()))


def dis_target(did):
    if did in dis_ids:
        return did, True
    m = re.match(r"d-([a-z]+).*-(\d{4})$", did)
    if m:
        cand = [i for i in dis_ids if i.startswith("d-" + m.group(1)) and i.endswith(m.group(2))]
        if len(cand) == 1:
            return cand[0], True
    return "list", False


def dis_cases(d):
    t = (d.get("linked_transfer") or "") + " " + (d.get("name") or "")
    out = []
    if "Vale privatization" in t:
        out.append("e4-19")
    if "RLAM" in t:
        out.append("e6-16")
    if "Eletrobras" in t and ("privatized" in t or "privatization" in t):
        out.append("e6-17")
    if "Santo Antonio" in t or "Jirau" in t:
        out.append("e5-06")
    if d["id"] == "d-belo-monte-2010":
        out.append("e5-15")
    if d["id"] == "d-tucurui-dam-1984":
        out.append("e3-14")
    return [i for i in out if i in BYID]


linked = sorted((d for d in disasters if d.get("linked_transfer")), key=lambda d: str(d.get("date")), reverse=True)
own = collections.Counter(d.get("ownership") for d in disasters)
drows = []
mapping_log = []
missing_targets = 0
for d in linked:
    tgt, ok = dis_target(d["id"])
    missing_targets += (not ok)
    cs = dis_cases(d)
    mapping_log.append((d["id"], tgt, cs))
    cl = ", ".join(case_link(i, f"{i}: {BYID[i]['title']}") for i in cs) or '<span class="muted small">no case on this page</span>'
    note = "" if ok else ' <span class="muted small">(not yet on the disasters page)</span>'
    drows.append(
        f'<tr id="dl-{esc(d["id"])}"><td><a href="disasters.html#{esc(tgt)}">{esc(d["name"])}</a>{note}</td>'
        f'<td class="nw">{esc(d.get("date"))}</td><td class="nw">{esc(d.get("ownership"))}</td>'
        f'<td>{esc(d.get("linked_transfer"))}</td><td>{cl}</td></tr>')
own_txt = ", ".join(f"{esc(k)} {v}" for k, v in own.most_common())
H(f'''<section id="disasters-link"><h2 id="disasters-link-h">Which transfers the data ties to later disasters</h2>
<p class="lead"><strong>{len(linked)} of {len(disasters)}</strong> disasters on the <a href="disasters.html">disasters page</a> name a transfer in their ownership history.</p>
<div class="callout"><strong>A link is not a cause.</strong> It means the operator got the asset through a sale or concession before the disaster. Several rows say outright there is no causal link (the old Eletrobras dams, for example).</div>
<p class="muted small">Operators of all {len(disasters)} disasters, by ownership: {own_txt}.</p>
<div class="tw"><table class="wide"><thead><tr><th>Disaster</th><th>Date</th><th>Ownership</th><th>Transfer named in the data</th><th>Case on this page</th></tr></thead><tbody>{"".join(drows)}</tbody></table></div>
</section>''')

# ---- gaps
no_fig = [c for c in cases if not c["figures"]]
no_url = sum(1 for _, f in all_figs if not url_ok(f.get("source_url")))
gap_rows = []
for era, name, short in ERAS:
    cnt = collections.Counter(f["status"] for c in cases_by_era[era] for f in c["figures"])
    gap_rows.append(f'<tr><td><a href="#{era}">{esc(short)}</a></td><td class="num">{cnt["unverified"]}</td><td class="num">{cnt["disputed"]}</td><td class="num">{sum(cnt.values())}</td></tr>')
H(f'''<section id="gaps"><h2 id="gaps-h">What could not be verified</h2>
<p class="lead"><strong>{fig_status["unverified"]} figures</strong> are still unverified and <strong>{fig_status["disputed"]}</strong> are disputed. Many sources were blocked (403 errors), were scanned PDFs, or showed only a search snippet.</p>
<div class="tw"><table class="narrow"><thead><tr><th>Era</th><th>Unverified</th><th>Disputed</th><th>All figures</th></tr></thead><tbody>{"".join(gap_rows)}</tbody></table></div>
<h3 id="gaps-open">Biggest open questions</h3>
<ul class="tight">
<li><strong>Colony:</strong> the total cost of railway guarantees to 1889, the Amazon steamship subsidy actually paid, tobacco and tithe contractor profits, and who bought the Jesuit estates.</li>
<li><strong>Republic:</strong> coffee-burning totals, the Norte do Paraná land company's prices, Santos docks profits, and the Amforp buy-out figures (no usable source link).</li>
<li><strong>Dictatorship:</strong> the total private debt the Central Bank took over in 1979–85, the Albras subsidy, Proálcool's total cost, and the 1983–85 bank-rescue costs.</li>
<li><strong>1985–2002:</strong> one total of BNDES loans to privatization buyers, several state-sale prices, the seguro-apagão total, and the Banestado CC5 mechanism.</li>
<li><strong>2003–2016:</strong> local-content waivers per oil round, leniency-deal terms, the TCU cost of the PSI, and losses on Sete Brasil.</li>
<li><strong>2016–2026:</strong> hectares titled under the land laws, the Correios sale value, airport minimum bids, and tax waivers (Refis, Carf, Perse).</li>
<li><strong>Cross-cutting:</strong> primary law texts were blocked; the CFEM audit and Kandir counter-arguments are thin; the Cuiabá registry fraud was not found and was dropped.</li>
</ul>
<h3 id="gaps-judgement">Choices made when building the data</h3>
<ul class="tight">
<li>Signs on each entry are the data builders' judgement from the notes. They were not fact-checked.</li>
<li>{len(no_fig)} entries have no figures ({", ".join(case_link(c["id"], c["id"]) for c in no_fig)}). {no_url} figures have no source link.</li>
<li>Some deals appear twice, once in an era and once in the cross-cutting group. "See also" links join them.</li>
<li>Weak fits for "public to private" (Cubatão, Serra Pelada, Itaipu, the nuclear deal, Calha Norte) are kept and say so in their text.</li>
</ul>
</section>''')

# ---------------------------------------------------------------- page
CSS = r"""
:root{--bg:#fbfaf7;--fg:#1d2127;--card:#fff;--line:#d9d6cd;--muted:#5d6572;--acc:#0b5d8f;--bar:#2d7fb0;--barl:#bcd8ea;--heat:45,127,176;
--gA:#8a4f00;--gAb:#fbe9cf;--gB:#0b5d8f;--gBb:#dcecf7;--gC:#6b2f8f;--gCb:#eddff6;--gD:#a02525;--gDb:#f8dcdc;
--sv:#1e6b34;--svb:#d9f0df;--sc:#0b5d8f;--scb:#dcecf7;--sd:#9a2a1a;--sdb:#fadcd5;--su:#7a5a00;--sub:#fff0c2}
@media (prefers-color-scheme:dark){:root{--bg:#14171b;--fg:#e6e8eb;--card:#1c2026;--line:#363c45;--muted:#a1a9b5;--acc:#7cc0ee;--bar:#5aa6d6;--barl:#2f4b5f;--heat:90,166,214;
--gA:#f0b765;--gAb:#3d2c10;--gB:#7cc0ee;--gBb:#16304a;--gC:#d1a4ec;--gCb:#31203f;--gD:#f09a9a;--gDb:#40201f;
--sv:#8fd9a2;--svb:#1d3a25;--sc:#7cc0ee;--scb:#16304a;--sd:#f4ab9b;--sdb:#4a2018;--su:#f3d57a;--sub:#4a3b0c}}
*{box-sizing:border-box}
html{scroll-behavior:smooth}
body{margin:0;background:var(--bg);color:var(--fg);font:16px/1.55 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif}
main{max-width:1100px;margin:0 auto;padding:16px}
h1{font-size:1.7rem;line-height:1.2;margin:.4em 0 .2em}
h2{font-size:1.35rem;margin:0 0 .5em;border-bottom:2px solid var(--line);padding-bottom:.25em}
h3{font-size:1.1rem;margin:1.6em 0 .4em}
h4{font-size:1rem;margin:1.2em 0 .2em}
section,nav{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin:18px 0}
section:target,tr:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
tr:target td{background:var(--gAb)}
h3:target,h4:target,article:target{outline:3px solid #ffb454;outline-offset:4px;border-radius:6px}
a{color:var(--acc)}
.lead{font-size:1.08rem}
.muted{color:var(--muted)}.small{font-size:.85rem}
.sub{color:var(--muted);margin:0}
ul,ol{padding-left:1.3em}
ul.tight li{margin:.25em 0}
.toc{columns:2;column-gap:28px}.toc>li{break-inside:avoid}
.pill{display:inline-block;font-size:.68rem;line-height:1;padding:2px 6px;border-radius:99px;vertical-align:middle;font-weight:600;white-space:nowrap;cursor:help}
.pill.s-verified{background:var(--svb);color:var(--sv)}.pill.s-corrected{background:var(--scb);color:var(--sc)}
.pill.s-disputed{background:var(--sdb);color:var(--sd)}.pill.s-unverified{background:var(--sub);color:var(--su)}
.legend{font-size:.85rem;color:var(--muted)}
.callout{border-left:5px solid #ffb454;background:var(--bg);padding:10px 14px;border-radius:6px;margin:12px 0}
.callout.warn{border-left-color:var(--gD)}
.tw{overflow-x:auto;border:1px solid var(--line);border-radius:8px;margin:10px 0;-webkit-overflow-scrolling:touch}
.tw.tall{max-height:80vh;overflow-y:auto}
table{border-collapse:collapse;width:100%;font-size:.9rem}
table.hist{min-width:820px}table.wide{min-width:900px}table.narrow{min-width:420px}table.heatmap{min-width:720px}
th,td{padding:7px 9px;border-bottom:1px solid var(--line);vertical-align:top;text-align:left}
th{background:var(--bg);position:sticky;top:0;font-size:.8rem;text-transform:uppercase;letter-spacing:.03em;z-index:1}
tbody th{position:static;text-transform:none;letter-spacing:0;font-size:.85rem;background:transparent}
td.nw{white-space:nowrap}td.num{text-align:right;font-variant-numeric:tabular-nums}
td.src{font-size:.8rem;word-break:break-word;min-width:140px}
td.heat{text-align:center;font-variant-numeric:tabular-nums;background:rgba(var(--heat),var(--a));font-weight:600}
.chip{display:inline-block;font-size:.72rem;padding:1px 7px;border-radius:99px;margin:1px 2px 1px 0;border:1px solid currentColor;white-space:nowrap;text-decoration:none}
.chip.gA{color:var(--gA);background:var(--gAb)}.chip.gB{color:var(--gB);background:var(--gBb)}.chip.gC{color:var(--gC);background:var(--gCb)}.chip.gD{color:var(--gD);background:var(--gDb)}
.signs{display:grid;grid-template-columns:repeat(auto-fill,minmax(300px,1fr));gap:12px}
.sign{border:1px solid var(--line);border-left:6px solid;border-radius:8px;padding:8px 12px;background:var(--bg)}
.sign.gA{border-left-color:var(--gA)}.sign.gB{border-left-color:var(--gB)}.sign.gC{border-left-color:var(--gC)}.sign.gD{border-left-color:var(--gD)}
.sign h4{margin:.2em 0}.sign p{margin:.35em 0}
.ex{display:inline-block;margin:0 8px 2px 0;white-space:nowrap}
td.sc{min-width:150px;white-space:nowrap}td.ev{min-width:130px}
.bar{display:inline-block;width:80px;height:10px;background:var(--barl);border-radius:5px;vertical-align:middle;margin-right:6px;overflow:hidden}
.bar i{display:block;height:100%;background:var(--bar)}
.stk{display:inline-flex;width:100%;min-width:80px;height:12px;border-radius:6px;overflow:hidden;background:var(--barl);vertical-align:middle}
td .stk{width:90px;margin-right:6px}
.stk .seg{display:block;height:100%}
.seg.s-verified{background:#3a9d5a}.seg.s-corrected{background:#2d7fb0}.seg.s-disputed{background:#c8553d}.seg.s-unverified{background:#e0b43a}
.chart{margin:8px 0}
.brow{display:grid;grid-template-columns:minmax(140px,44%) 1fr minmax(90px,auto);gap:8px;align-items:center;padding:3px 0;font-size:.85rem;border-bottom:1px dotted var(--line)}
.bl{min-width:0;word-break:break-word}
.bt{position:relative;display:block;height:14px;border-left:1px solid var(--line)}
.bt i{position:absolute;left:0;top:0;height:100%;background:var(--bar);border-radius:0 4px 4px 0}
.bv{font-variant-numeric:tabular-nums;white-space:nowrap}
details.case summary{cursor:pointer;font-weight:600}
details.case .sum{margin:.5em 0}
details.case dl{margin:0;display:grid;grid-template-columns:130px 1fr;gap:4px 12px}
details.case dt{color:var(--muted);font-size:.85rem}
details.case dd{margin:0;word-break:break-word}
ul.figs,ul.srcs{margin:0;padding-left:1.1em}ul.figs li{margin:.3em 0}ul.srcs li{font-size:.85rem;word-break:break-word}
details.more summary{cursor:pointer;color:var(--acc)}
.steps li{margin:.3em 0}
nav ol{margin:.3em 0}
@media (max-width:640px){.brow{grid-template-columns:1fr;gap:2px}.toc{columns:1}main{padding:8px}section,nav{padding:12px}details.case dl{grid-template-columns:1fr}}
"""

page = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Brazil: public wealth moving into private hands</title>
<style>{CSS}</style></head>
<body><main id="top">
<h1 id="title">Brazil: when public wealth and power moved into private hands</h1>
<p class="sub">A profile of what marks such a deal, and the record from 1500 to 2026. Built from the data files by build.py. Disasters are on a <a href="disasters.html">separate page</a>.</p>
{"".join(parts)}
<p class="muted small">Generated by build.py from data/g1–g7 (cases) and data/g8–g10 (disasters). Every figure carries its source and fact-check status.</p>
</main></body></html>
'''

with open(OUT, "w", encoding="utf-8") as fh:
    fh.write(page)

# ---------------------------------------------------------------- self-checks


class P(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids = collections.Counter()
        self.hrefs = []
        self.tr_ids = set()
        self.ext = []
        self.stack = []
        self.errors = []
        self.headings_without_id = []
        self.sections_without_id = 0

    VOID = {"meta", "br", "img", "hr", "input", "link", "wbr"}

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids[a["id"]] += 1
            if tag == "tr":
                self.tr_ids.add(a["id"])
        if tag in ("h2", "h3") and "id" not in a:
            self.headings_without_id.append(tag)
        if tag == "section" and "id" not in a:
            self.sections_without_id += 1
        if "href" in a:
            self.hrefs.append(a["href"])
        if tag in ("script", "link", "img", "iframe") and (a.get("src") or a.get("href")):
            self.ext.append(tag)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        if not self.stack or self.stack[-1] != tag:
            self.errors.append((tag, self.stack[-3:]))
            if tag in self.stack:
                while self.stack and self.stack.pop() != tag:
                    pass
        else:
            self.stack.pop()


p = P()
p.feed(page)
dups = [i for i, n in p.ids.items() if n > 1]
bad_href = [h for h in p.hrefs if h.startswith("#") and h[1:] not in p.ids]
missing_rows = [c["id"] for c in cases if c["id"] not in p.tr_ids]
wealth_expected = sum(1 for _, f in all_figs if f["kind"] in KIND_LABEL)
wealth_rows = sum(1 for i in p.tr_ids if i.startswith("w-"))
problems = []
if dups:
    problems.append(f"duplicate ids: {dups[:10]}")
if bad_href:
    problems.append(f"unresolved #hrefs: {sorted(set(bad_href))[:10]}")
if missing_rows:
    problems.append(f"case rows missing: {missing_rows[:10]}")
if wealth_rows != wealth_expected:
    problems.append(f"wealth rows {wealth_rows} != {wealth_expected}")
if p.ext:
    problems.append(f"external resources: {p.ext}")
if p.errors or p.stack:
    problems.append(f"tag nesting: {p.errors[:5]} open={p.stack[:5]}")
if p.headings_without_id or p.sections_without_id:
    problems.append(f"h2/h3 or section without id: {p.headings_without_id[:5]} {p.sections_without_id}")
for need in ("html{scroll-behavior:smooth}", "section:target,tr:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}"):
    if need not in page:
        problems.append("css missing " + need)

print(f"wrote {OUT} ({len(page):,} bytes)")
print(f"cases {N_CASES}, figures {len(all_figs)} {dict(fig_status)}; disasters {len(disasters)} figures {dict(dis_status)}")
print(f"wealth rows {wealth_rows}; land bars {len(land_items)}; money bars {n_money}")
print("flagship:", ", ".join(f'{c["id"]}({c["_score"]})' for c in flagship))
print(f"zero-sign entries {len(zero_sign)}; disaster links {len(linked)}, targets missing on disasters.html {missing_targets}")
if "-v" in sys.argv:
    for row in mapping_log:
        print("  dis", row)
    for (cur, era), items in sorted(money_groups.items()):
        for amt, lab, _, rid in sorted(items, key=lambda t: -t[0]):
            f = None
            print(f"  money {cur} {era} {human(amt, cur):>18}  {rid}")
    for amt, lab, _, rid in sorted(land_items, key=lambda t: -t[0]):
        print(f"  land {human(amt, 'ha'):>22}  {rid}")
if problems:
    print("PROBLEMS:")
    for x in problems:
        print("  -", x)
    sys.exit(1)
print("checks OK")
