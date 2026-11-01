#!/usr/bin/env python3
"""Builds disasters.html from data/g8-dis-mining.json, g9-dis-oil.json, g10-dis-hydro-land.json."""
import json, os, html, collections as C
D = os.path.dirname(os.path.abspath(__file__))
FILES = ['g8-dis-mining', 'g9-dis-oil', 'g10-dis-hydro-land']
L = []
for f in FILES:
    L += json.load(open(os.path.join(D, 'data', f + '.json'), encoding='utf-8'))
L.sort(key=lambda x: x['date'], reverse=True)
e = lambda s: html.escape(str(s if s is not None else ''), quote=True)

OWN = [('state-owned', 'State-owned', 's'), ('privatized', 'Privatized (company sold to private owners)', 'p'),
       ('private-concession', 'Private concession', 'c'), ('private-company', 'Private company', 'b'),
       ('private-landholders', 'Private landholders', 'l'), ('unknown', 'Unknown or mixed', 'u')]
OWNL = {k: (n, c) for k, n, c in OWN}
TYP = [('mining', 'Mining'), ('oil-chemical-nuclear-energy', 'Oil, chemical, nuclear and energy'),
       ('hydro-infrastructure', 'Hydro and infrastructure'), ('land-agro', 'Land and agribusiness')]
TYPL = dict(TYP)
oc = C.Counter(x['ownership'] for x in L); tc = C.Counter(x['type'] for x in L)
N = len(L)
st = C.Counter(f['status'] for x in L for f in x['figures'])
NF = sum(st.values())
linked = [x for x in L if x['linked_transfer']]

def pill(s, note=''):
    return f'<span class="pill {e(s)}" title="{e(note)}">{e(s)}</span>'

def bars(pairs, maxv, cls):
    o = ''
    for lab, v, c in pairs:
        o += f'<div class="bar"><span class="bl">{e(lab)}</span><span class="bt"><i class="own-{c}" style="width:{100*v/maxv:.1f}%"></i></span><b class="bn">{v}</b></div>\n'
    return o

def ownpill(x):
    n, c = OWNL.get(x['ownership'], (x['ownership'], 'u'))
    y = x['privatized_or_conceded_year']
    return f'<span class="own own-{c}">{e(n)}</span>' + (f' <span class="tag">year {y}</span>' if y else '')

def srcs(x):
    items = ''.join(f'<li><a href="{e(s["url"])}" rel="noopener">{e(s["title"])}</a></li>' for s in x['sources'] if str(s.get('url', '')).startswith('http'))
    return f'<details class="src"><summary>{len(x["sources"])} sources</summary><ul>{items}</ul></details>'

def figs(x):
    r = ''
    for f in x['figures']:
        u = f.get('source_url')
        link = f' <a href="{e(u)}" rel="noopener">source</a>' if u and str(u).startswith('http') else ' <span class="tag">no link</span>'
        r += f'<tr><td>{e(f["label"])}</td><td>{e(f["value"])}</td><td>{pill(f["status"], f.get("note", ""))}{link}</td></tr>'
    return f'<div class="tw2"><table class="ft"><thead><tr><th>Figure</th><th>Value</th><th>Status</th></tr></thead><tbody>{r}</tbody></table></div>'

rows = ''
for x in L:
    rows += (f'<tr id="{e(x["id"])}" data-t="{e(x["type"])}"><td class="nw">{e(x["date"])}</td>'
             f'<td><b>{e(x["name"])}</b><br><span class="tag">{e(TYPL.get(x["type"], x["type"]))}</span>'
             f'<details><summary>Summary and figures</summary><p>{e(x["summary"])}</p>{figs(x)}</details></td>'
             f'<td>{e(x["place"])}</td><td>{e(x["operator"])}<br>{ownpill(x)}</td><td>{e(x["deaths"])}</td>'
             f'<td>{e(x["affected"])}</td><td>{e(x["damage"])}</td><td>{e(x["legal_outcome"])}</td><td>{srcs(x)}</td></tr>\n')

filt = f'<button data-f="all" aria-pressed="true">All ({N})</button>' + ''.join(
    f'<button data-f="{k}" aria-pressed="false">{e(n)} ({tc[k]})</button>' for k, n in TYP)

lrows = ''
for x in sorted(linked, key=lambda x: x['date'], reverse=True):
    y = x['privatized_or_conceded_year']
    ev = x['date'][:4]
    gap = f'{int(ev) - y} years' if y else 'not stated'
    lrows += (f'<tr><td class="nw">{e(x["date"])}</td><td><a href="#{e(x["id"])}">{e(x["name"])}</a></td>'
              f'<td>{ownpill(x)}</td><td>{e(x["linked_transfer"])}</td><td class="nw">{gap}</td></tr>\n')
lk_own = C.Counter(x['ownership'] for x in linked)

# patterns (all computed from the data)
matrix = ''
for k, n, c in OWN:
    matrix += f'<tr><td>{e(n)}</td>' + ''.join(f'<td>{sum(1 for x in L if x["ownership"]==k and x["type"]==t)}</td>' for t, _ in TYP) + f'<td><b>{oc[k]}</b></td></tr>'
dec = C.Counter()
for x in L:
    dec[x['date'][:3] + '0s'] += 1
decbars = bars([(k, dec[k], 't') for k in sorted(dec, reverse=True)], max(dec.values()), 't')
stt = {t: C.Counter(f['status'] for x in L if x['type'] == t for f in x['figures']) for t, _ in TYP}
strows = ''.join(f'<tr><td>{e(n)}</td>' + ''.join(f'<td>{stt[t][s]}</td>' for s in ['verified', 'corrected', 'disputed', 'unverified']) + '</tr>' for t, n in TYP)
gaps_y = [int(x['date'][:4]) - x['privatized_or_conceded_year'] for x in L if x['privatized_or_conceded_year']]
nodeath = sum(1 for x in L if x['deaths'].lower().startswith(('none', 'no ')))
nolink = sum(1 for x in L for f in x['figures'] if not f.get('source_url'))
nolegal = sum(1 for x in L if x['legal_outcome'].lower().startswith(('no fine', 'no charge', 'no case', 'none', 'no ')))
vc = sum(1 for x in L if x['ownership'] == 'unknown')

# ---------------------------------------------------------------- charts (figures)
import math, re, sys, unicodedata
import timeline_data as td

def fold(s):
    return ''.join(ch for ch in unicodedata.normalize('NFKD', str(s).lower()) if not unicodedata.combining(ch))

def death_n(x):
    """(count, exact). Shared rule first (timeline_data.deaths_count); if that gives none, a lower bound from
    text that starts 'At least N', 'Disputed: N' or 'Official: N' (exact=False). (None, False) = no count."""
    n = td.deaths_count(x['deaths'])
    if n is not None:
        return n, True
    m = re.match(r'\s*(?:at least|disputed:|official:)\s*(\d[\d,]*)', x['deaths'], re.I)
    if m:
        return int(m.group(1).replace(',', '')), False
    return None, False

DN = {x['id']: death_n(x) for x in L}

def death_status(x):
    """Status of the case's own deaths figure (first figure whose label is about deaths), or None if it has none."""
    for f in x['figures']:
        if re.search(r'death|dead|killed|fatalit|mortos|toll', f['label'], re.I):
            return f['status']
    return None

DOK = {x['id']: death_status(x) in ('verified', 'corrected') for x in L}
YR = {x['id']: int(x['date'][:4]) for x in L}

def fig(fid, title, body, source):
    return (f'<figure class="ch" id="{fid}"><figcaption><span class="tk">{title}</span></figcaption>'
            f'{body}<p class="src">{source}</p></figure>')

own_leg = ''.join(f'<li><i class="sw own-{c}"></i>{e(n.split(" (")[0])}</li>' for k, n, c in OWN)

# --- 1. deaths and disasters over time: lanes by type, dot size by deaths, colour by ownership
def dot_r(n):
    return 3 if not n else 3 + 1.45 * math.sqrt(n)

def time_svg():
    W, LFT, R, LH = 960, 150, 20, 84
    y0 = min(YR.values()) // 10 * 10
    y1 = 2026
    def X(y):
        return LFT + (y - y0) / (y1 - y0) * (W - LFT - R)
    rad = dot_r
    H = 30 + LH * len(TYP) + 10
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="fig-dis-time-t">']
    for yy in range(y0, y1 + 1, 10):
        out.append(f'<line class="grid" x1="{X(yy):.1f}" x2="{X(yy):.1f}" y1="18" y2="{H - 8}"/><text class="ax" x="{X(yy):.1f}" y="13">{yy}</text>')
    labels = []
    for i, (tk, tn) in enumerate(TYP):
        cy = 30 + LH * i + LH / 2
        out.append(f'<line class="axl" x1="{LFT}" x2="{W - R}" y1="{cy:.1f}" y2="{cy:.1f}"/>'
                   f'<text class="rl" x="{LFT - 10}" y="{cy - 2:.1f}">{e(tn.split(",")[0].replace(" and", ""))}</text>'
                   f'<text class="rr2" x="{LFT - 10}" y="{cy + 13:.1f}">{tc[tk]} cases</text>')
        xs = sorted((x for x in L if x['type'] == tk), key=lambda x: -(DN[x['id']][0] or 0))
        for x in xs:
            n, exact = DN[x['id']]
            c = OWNL.get(x['ownership'], ('', 'u'))[1]
            cls = f'dd own-{c}' + ('' if n is not None else ' nc') + ('' if exact or n is None else ' lb') + ('' if n is None or DOK[x['id']] else ' pale')
            dtxt = 'no death count' if n is None else (f'{n:,} deaths' if exact else f'at least {n:,} deaths')
            r = rad(n)
            out.append(f'<a href="#{e(x["id"])}"><circle class="{cls}" cx="{X(YR[x["id"]] + .5):.1f}" cy="{cy:.1f}" r="{r:.1f}">'
                       f'<title>{e(x["date"])} · {e(x["name"])} · {dtxt} · {e(OWNL.get(x["ownership"], (x["ownership"],))[0])}</title></circle></a>')
            if n and n >= 80:
                labels.append((X(YR[x['id']] + .5), cy, r, x, n, exact))
    boxes = []  # placed label boxes; try above, below, then further up/down until free
    for lx, cy, r, x, n, exact in sorted(labels, key=lambda t: -t[4]):
        nm = x['name'].split(':')[0].split(' (')[0]
        nm = nm if len(nm) <= 16 else nm[:15].rstrip() + '…'
        txt = f'{nm} {"" if exact else "≥"}{n}'
        w = 6.6 * len(txt)
        x0 = min(max(lx - w / 2, LFT), W - R - w)
        for ty in (cy - r - 5, cy + r + 14, cy + r + 28, cy - r - 19):
            bx = (x0, ty - 11, x0 + w, ty + 3)
            if not any(bx[0] < o[2] and o[0] < bx[2] and bx[1] < o[3] and o[1] < bx[3] for o in boxes):
                break
        boxes.append(bx)
        out.append(f'<text class="dl" x="{x0:.1f}" y="{ty:.1f}">{e(txt)}</text>')
    out.append('</svg>')
    return ''.join(out)

dead_known = [DN[x['id']][0] for x in L if DN[x['id']][0] is not None]
n_nocount = sum(1 for x in L if DN[x['id']][0] is None)
dec_dead = C.Counter()
for x in L:
    if DN[x['id']][0]:
        dec_dead[x['date'][:3] + '0s'] += DN[x['id']][0]
TOPD = max(L, key=lambda x: DN[x['id']][0] or 0)
since2000 = sum(1 for x in L if YR[x['id']] >= 2000)
size_leg = ''.join(f'<li><svg viewBox="0 0 {2 * dot_r(n) + 4:.0f} {2 * dot_r(n) + 4:.0f}" width="{2 * dot_r(n) + 4:.0f}" height="{2 * dot_r(n) + 4:.0f}" aria-hidden="true"><circle class="dd own-u" cx="{dot_r(n) + 2:.1f}" cy="{dot_r(n) + 2:.1f}" r="{dot_r(n):.1f}"/></svg>{n} death{"s" if n > 1 else ""}</li>' for n in (1, 20, 100, 250))
FIG_TIME = fig('fig-dis-time',
    f'<span id="fig-dis-time-t">{since2000} of the {N} disasters happened in 2000 or later; the highest death count is {e(TOPD["name"].split(":")[0])} ({"" if DN[TOPD["id"]][1] else "at least "}{DN[TOPD["id"]][0]:,})</span>',
    f'<ul class="lg">{own_leg}<li><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><circle class="dd own-u nc" cx="10" cy="10" r="6"/></svg>no death count</li></ul>'
    f'<p class="hint">Swipe sideways for all years; the chart opens at the most recent.</p><div class="sx" data-end>{time_svg()}</div><ul class="lg">{size_leg}<li>dashed ring = lower bound ("at least")</li><li><svg viewBox="0 0 20 20" width="16" height="16" aria-hidden="true"><circle class="dd own-u pale" cx="10" cy="10" r="7"/></svg>pale = the deaths figure is unverified, disputed or not checked</li></ul>',
    f'One dot per disaster at its year, in a row for its type. Size = deaths where the data gives a number; {n_nocount} have no count and are drawn as small hollow rings, not as zero. '
    'Where the deaths text starts "At least", "Disputed:" or "Official:", the lowest number is drawn with a dashed ring. Colour = ownership at the time; pale = the deaths figure is unverified, disputed or not checked. Tap a dot to open its row. Source: data/g8–g10, fields "date", "deaths", "type", "ownership".')

# --- 2. ownership: count and deaths side by side (HTML bars)
own_dead = C.Counter()
own_nc = C.Counter()
for x in L:
    n = DN[x['id']][0]
    if n is None:
        own_nc[x['ownership']] += 1
    else:
        own_dead[x['ownership']] += n
mo, md = max(oc.values()), max(own_dead.values()) or 1
orows = ''
for k, n, c in OWN:
    orows += (f'<div class="orow"><span class="ol">{e(n.split(" (")[0])}</span>'
              f'<span class="ob"><i class="own-{c}" style="width:{100 * oc[k] / mo:.1f}%"></i><b>{oc[k]}</b></span>'
              f'<span class="ob"><i class="own-{c}" style="width:{100 * own_dead[k] / md:.1f}%"></i><b>{own_dead[k]:,}</b>'
              f'{f" <small>+{own_nc[k]} no count</small>" if own_nc[k] else ""}</span></div>')
top_own = max(OWN, key=lambda o: oc[o[0]])
top_dead = max(OWN, key=lambda o: own_dead[o[0]])
FIG_OWN = fig('fig-ownership',
    f'{e(top_own[1].split(" (")[0])} operators had the most disasters ({oc[top_own[0]]}); {e(top_dead[1].split(" (")[0].lower())} ones the most recorded deaths ({own_dead[top_dead[0]]:,})',
    f'<div class="orow oh"><span class="ol"></span><span>Disasters</span><span>Deaths recorded</span></div>{orows}',
    'Deaths are added only where the data gives a number (lower bounds counted at their lowest value); the "no count" note says how many are left out. Ownership is the operator\'s at the time of the event. Counts describe this sample, not all disasters in Brazil. Source: data/g8–g10.')

# --- 3. map: tile grid of the 27 states
STATES = [  # abbr, name, col, row
    ('RR', 'Roraima', 1, 0), ('AP', 'Amapá', 3, 0),
    ('AM', 'Amazonas', 1, 1), ('PA', 'Pará', 2, 1), ('MA', 'Maranhão', 3, 1), ('CE', 'Ceará', 4, 1), ('RN', 'Rio Grande do Norte', 5, 1),
    ('AC', 'Acre', 0, 2), ('RO', 'Rondônia', 1, 2), ('MT', 'Mato Grosso', 2, 2), ('TO', 'Tocantins', 3, 2), ('PI', 'Piauí', 4, 2), ('PB', 'Paraíba', 5, 2),
    ('GO', 'Goiás', 3, 3), ('DF', 'Distrito Federal', 4, 3), ('BA', 'Bahia', 5, 3), ('PE', 'Pernambuco', 6, 3),
    ('MS', 'Mato Grosso do Sul', 2, 4), ('SP', 'São Paulo', 3, 4), ('MG', 'Minas Gerais', 4, 4), ('ES', 'Espírito Santo', 5, 4), ('AL', 'Alagoas', 6, 4),
    ('PR', 'Paraná', 3, 5), ('RJ', 'Rio de Janeiro', 4, 5), ('SE', 'Sergipe', 6, 5),
    ('SC', 'Santa Catarina', 3, 6), ('RS', 'Rio Grande do Sul', 3, 7),
]
SNAME = {a: n for a, n, _, _ in STATES}
_srx = sorted(((fold(n), a) for a, n, _, _ in STATES), key=lambda t: -len(t[0]))

# Places whose text does not name the state the usual way (checked by hand against the place field).
PLACE_STATES = {'d-belo-monte-blackout-2018': [],  # "13 states ... (Acre, Roraima, Rondônia spared)": not placed
                'd-ouro-preto-nova-lima-evacuations-2019': ['MG']}  # Nova Lima, Ouro Preto, Barão de Cocais are in Minas Gerais

def states_of(place):
    """States named in the place text, on whole words, longest names first (Mato Grosso do Sul before
    Mato Grosso, Paraná and Paraíba before Pará). A name used as a river ("Rio Paraíba do Sul", "Paraná river")
    or inside a town name ("Jaci-Paraná") is skipped. Two-letter codes in brackets, "(MA)", also count."""
    found = [(m.start(), m.group(1)) for m in re.finditer(r'\(([A-Z]{2})\)', place) if m.group(1) in SNAME]
    t = fold(place)
    for nm, a in _srx:
        for m in re.finditer(r'(?<![a-z-])' + re.escape(nm) + r'(?![a-z-])', t):
            if t[max(0, m.start() - 4):m.start()] == 'rio ' or t[m.end():m.end() + 6] == ' river':
                continue
            found.append((m.start(), a))
            t = t[:m.start()] + '#' * (m.end() - m.start()) + t[m.end():]
    return [a for _, a in sorted(found)]

BY_STATE = C.defaultdict(list)
UNPLACED = []
MULTI = []
for x in L:
    ss = PLACE_STATES[x['id']] if x['id'] in PLACE_STATES else list(dict.fromkeys(states_of(x['place'])))
    if not ss:
        UNPLACED.append(x)
    else:
        if len(ss) > 1:
            MULTI.append(x)
        for a in ss:
            BY_STATE[a].append(x)
ms = max(len(v) for v in BY_STATE.values())

def tile(a, n, cc, r):
    xs = BY_STATE.get(a, [])
    lvl = 0 if not xs else 1 + min(3, int(3 * (len(xs) - 1) / max(ms - 1, 1)))
    dead = sum(DN[x['id']][0] or 0 for x in xs)
    tip = f'{n}: {len(xs)} disaster{"s" if len(xs) != 1 else ""}' + (f', {dead:,} deaths recorded' if dead else '') + (': ' + '; '.join(x['name'].split(':')[0] for x in sorted(xs, key=lambda x: x['date'])) if xs else '')
    inner = f'<b>{a}</b><span>{len(xs) or ""}</span>'
    href = f' href="#st-{a.lower()}"' if xs else ''
    tag = 'a' if xs else 'span'
    return f'<{tag} class="tile l{lvl}"{href} style="grid-column:{cc + 1};grid-row:{r + 1}" title="{e(tip)}">{inner}</{tag}>'

tiles = ''.join(tile(a, n, cc, r) for a, n, cc, r in STATES)
st_list = ''.join(
    f'<li id="st-{a.lower()}"><b>{a}</b> {e(SNAME[a])} ({len(BY_STATE[a])}): '
    + ', '.join(f'<a href="#{e(x["id"])}">{e(x["name"].split(":")[0])}</a> <small>{x["date"][:4]}</small>' for x in sorted(BY_STATE[a], key=lambda x: x['date']))
    + '</li>' for a in sorted(BY_STATE, key=lambda a: (-len(BY_STATE[a]), a)))
top_st = sorted(BY_STATE, key=lambda a: -len(BY_STATE[a]))[:3]
FIG_MAP = fig('fig-dis-map',
    f'{e(SNAME[top_st[0]])} has the most disasters in the data ({len(BY_STATE[top_st[0]])}), then {e(SNAME[top_st[1]])} ({len(BY_STATE[top_st[1]])}) and {e(SNAME[top_st[2]])} ({len(BY_STATE[top_st[2]])})',
    f'<div class="mapwrap"><div class="tiles" role="img" aria-label="Tile map of the 27 states with disaster counts">{tiles}</div>'
    f'<div class="mapside"><p class="lg2"><span><i class="tile-sw l1"></i>1</span><span><i class="tile-sw l2"></i>more</span><span><i class="tile-sw l4"></i>most ({ms})</span><span><i class="tile-sw l0"></i>none</span></p>'
    f'<p class="small"><b>Not on a state: {len(UNPLACED)}</b> (nationwide, along a coast, or no single state named): '
    + ', '.join(f'<a href="#{e(x["id"])}">{e(x["name"].split(":")[0])}</a>' for x in UNPLACED) + '.</p>'
    f'<p class="small"><b>In more than one state: {len(MULTI)}</b>, counted in each.</p></div></div>'
    f'<details class="more"><summary>Disasters by state</summary><ul class="stl">{st_list}</ul></details>',
    'One square per state in rough geographic position, not to scale or shape. A state is counted when its name appears in the "place" text. Source: data/g8–g10, field "place".')

# --- 4. deal → disaster chain for the disasters tied to a case (shared matching rules)
CASES = td.load_cases()
CASE = {c['id']: c for c in CASES}
DM = td.match_disasters(CASES, L)
chain = []
for did, (cid, how, det) in DM.items():
    if cid:
        x = next(v for v in L if v['id'] == did)
        chain.append((x, CASE[cid]))
chain.sort(key=lambda t: (t[1]['_y'], t[0]['date']))

def chain_svg():
    W, LFT, R, RH = 960, 330, 30, 38
    y0 = min(min(c['_y'] for _, c in chain), min(YR[x['id']] for x, _ in chain)) // 10 * 10
    y1 = 2026
    def X(y):
        return LFT + (y - y0) / (y1 - y0) * (W - LFT - R)
    H = 26 + RH * len(chain) + 6
    out = [f'<svg viewBox="0 0 {W} {H}" role="img" aria-labelledby="fig-dis-chain-t">']
    for yy in range(y0, y1 + 1, 10):
        out.append(f'<line class="grid" x1="{X(yy):.1f}" x2="{X(yy):.1f}" y1="18" y2="{H - 4}"/><text class="ax" x="{X(yy):.1f}" y="13">{yy}</text>')
    for i, (x, c) in enumerate(chain):
        cy = 26 + RH * i + RH / 2
        dy, cyr = YR[x['id']] + .5, c['_y'] + .5
        n, exact = DN[x['id']]
        oc_ = OWNL.get(x['ownership'], ('', 'u'))[1]
        nm = x['name'].split(':')[0]
        nm = nm if len(nm) <= 40 else nm[:39] + '…'
        ct = c['title'] if len(c['title']) <= 44 else c['title'][:43] + '…'
        gap = YR[x['id']] - c['_y']
        ovr = x['id'] in td.DIS_AFTER_OVERRIDES
        out.append(f'<a href="#{e(x["id"])}"><text class="rl" x="{LFT - 12}" y="{cy - 3:.1f}">{e(nm)}</text></a>'
                   f'<a href="index.html#{e(c["id"])}"><text class="rr2" x="{LFT - 12}" y="{cy + 11:.1f}">after {e(c["id"])}: {e(ct)}</text></a>'
                   f'<line class="chl{" neg" if gap < 0 and not ovr else ""}" x1="{X(cyr):.1f}" x2="{X(dy):.1f}" y1="{cy:.1f}" y2="{cy:.1f}"/>'
                   f'<a href="index.html#{e(c["id"])}"><rect class="deal" x="{X(cyr) - 5:.1f}" y="{cy - 5:.1f}" width="10" height="10"><title>{c["_y"]} deal: {e(c["title"])}</title></rect></a>'
                   f'<a href="#{e(x["id"])}"><circle class="dd own-{oc_}{"" if n is not None else " nc"}{"" if n is None or DOK[x["id"]] else " pale"}" cx="{X(dy):.1f}" cy="{cy:.1f}" r="7"><title>{e(x["date"])} · {e(x["name"])} · {"no death count" if n is None else ("" if exact else "at least ") + f"{n:,} deaths"}</title></circle></a>'
                   + (f'<text class="gl" x="{max(X(dy), X(cyr)) + 11:.1f}" y="{cy + 4:.1f}">' if max(X(dy), X(cyr)) < W - 70 else f'<text class="gl" text-anchor="end" x="{min(X(dy), X(cyr)) - 11:.1f}" y="{cy + 4:.1f}">') + (f'{gap} yrs, deaths counted later*' if ovr else f'{"+" if gap >= 0 else ""}{gap} yrs') + '</text>')
    out.append('</svg>')
    return ''.join(out)

chain_gaps = [0 if x['id'] in td.DIS_AFTER_OVERRIDES else YR[x['id']] - c['_y'] for x, c in chain]
chain_ovr = ' '.join(f'*{e(x["name"].split(":")[0])}: {e(td.DIS_AFTER_OVERRIDES[x["id"]])}.' for x, _ in chain if x['id'] in td.DIS_AFTER_OVERRIDES)
FIG_CHAIN = fig('fig-dis-chain',
    f'<span id="fig-dis-chain-t">{len(chain)} disasters are tied to a deal on the main page: {sum(g >= 0 for g in chain_gaps)} count as in or after the deal year, {sum(g < 0 for g in chain_gaps)} came before it</span>',
    f'<ul class="lg"><li><svg viewBox="0 0 14 14" width="12" height="12" aria-hidden="true"><rect class="deal" x="2" y="2" width="10" height="10"/></svg>deal (start year, links to the main page)</li><li>circle = disaster, coloured by ownership</li><li>dotted line = disaster came before the deal year</li></ul>'
    f'<p class="hint">Swipe sideways to see the years.</p><div class="sx chain">{chain_svg()}</div>',
    f'A tie means the "linked transfer" text names that deal; it does not show cause. The matching rules are shared with the <a href="timeline.html#deals-rules">timeline page</a>; {len(linked) - len(chain)} other disasters name a transfer that is not a case on the main page. {chain_ovr} Dot shade: pale = the deaths figure is unverified, disputed or not checked. Source: data/g8–g10 field "linked_transfer", data/g1–g7.')

if '-v' in sys.argv:
    print('unplaced:', [x['id'] for x in UNPLACED])
    print('multi:', [(x['id'], states_of(x['place'])) for x in MULTI])
    for x in L:
        print('  ', states_of(x['place']), '|', x['place'][:70])
    print('lower bounds:', [(k, v) for k, v in DN.items() if v[0] is not None and not v[1]])

CHART_CSS = """
section:target,tr:target,figure:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
:root{--ink:#1d1d21;--unv:#a3a8b0}
@media (prefers-color-scheme:dark){:root{--ink:#ececef;--unv:#6b717a}}
figure.ch{margin:16px 0;padding:12px;border:1px solid var(--line);border-radius:8px;background:var(--card);min-width:0}
figure.ch figcaption .tk{font-weight:700;font-size:1.05rem;display:block;margin-bottom:6px}
figure.ch .src{font-size:.8rem;color:var(--mut);margin:.5em 0 0}
.sx{overflow-x:auto;-webkit-overflow-scrolling:touch;margin:4px 0}
.sx svg{display:block;width:100%;height:auto;min-width:760px}
.sx.chain svg{min-width:860px}
.hint{display:none;font-size:.8rem;color:var(--mut);margin:2px 0}@media(max-width:780px){.hint{display:block}}
svg .grid{stroke:var(--line);stroke-width:1;stroke-dasharray:2 3}svg .axl{stroke:var(--line);stroke-width:1}
svg .ax{fill:var(--mut);font-size:12px;text-anchor:middle}
svg .rl{fill:var(--ink);font-size:13px;text-anchor:end}svg .rr2{fill:var(--mut);font-size:11px;text-anchor:end}
svg .dl{fill:var(--ink);font-size:11.5px;font-weight:600;paint-order:stroke;stroke:var(--card);stroke-width:3px}
svg .gl{fill:var(--mut);font-size:11px}
svg .dd{stroke:var(--card);stroke-width:1;fill-opacity:.85}
svg .dd.own-s{fill:var(--s)}svg .dd.own-p{fill:var(--p)}svg .dd.own-c{fill:var(--c)}svg .dd.own-b{fill:var(--b)}svg .dd.own-l{fill:var(--l)}svg .dd.own-u{fill:var(--u)}
svg .dd.nc{fill:var(--card);fill-opacity:1;stroke-width:1.6}
svg .dd.nc.own-s{stroke:var(--s)}svg .dd.nc.own-p{stroke:var(--p)}svg .dd.nc.own-c{stroke:var(--c)}svg .dd.nc.own-b{stroke:var(--b)}svg .dd.nc.own-l{stroke:var(--l)}svg .dd.nc.own-u{stroke:var(--u)}
svg .dd.pale{fill-opacity:.3}
svg .dd.lb{stroke:var(--ink);stroke-dasharray:3 2;stroke-width:1.4}
svg a:hover .dd,svg a:focus .dd{stroke:var(--ink);stroke-width:2.2}
svg .deal{fill:var(--ink)}svg .chl{stroke:var(--mut);stroke-width:2}svg .chl.neg{stroke-dasharray:2 3}
svg a text{text-decoration:none}svg a:hover text{text-decoration:underline}
ul.lg{list-style:none;margin:4px 0;padding:0;display:flex;flex-wrap:wrap;gap:2px 14px;font-size:.85rem;align-items:center}
ul.lg li{display:flex;align-items:center;gap:5px}
.lg2{display:flex;flex-wrap:wrap;gap:4px 14px;font-size:.85rem;margin:4px 0}.lg2 span{display:inline-flex;align-items:center;gap:5px}
i.sw{display:inline-block;width:12px;height:12px;border-radius:3px;flex:none}
.orow{display:grid;grid-template-columns:minmax(110px,26%) 1fr 1fr;gap:10px;align-items:center;padding:4px 0;border-bottom:1px dotted var(--line);font-size:.88rem}
.orow.oh{font-size:.78rem;text-transform:uppercase;letter-spacing:.03em;color:var(--mut)}
.ob{display:flex;align-items:center;gap:6px;min-width:0;flex-wrap:wrap}.ob i{display:block;height:16px;border-radius:0 4px 4px 0;min-width:2px}
.ob b{font-variant-numeric:tabular-nums}.ob small{color:var(--mut);font-size:.72rem}
.mapwrap{display:flex;flex-wrap:wrap;gap:16px;align-items:flex-start}
.tiles{display:grid;grid-template-columns:repeat(7,minmax(0,52px));grid-auto-rows:minmax(44px,auto);gap:4px;flex:0 1 380px;max-width:100%}
.tile{display:flex;flex-direction:column;align-items:center;justify-content:center;border-radius:5px;font-size:.78rem;line-height:1.1;text-decoration:none;color:var(--fg);border:1px solid var(--line)}
.tile b{font-size:.8rem}.tile span{font-size:.95rem;font-weight:700}
.tile.l0,.tile-sw.l0{background:var(--card);color:var(--mut)}
.tile.l1,.tile-sw.l1{background:color-mix(in srgb,var(--acc) 22%,var(--card))}
.tile.l2,.tile-sw.l2{background:color-mix(in srgb,var(--acc) 45%,var(--card))}
.tile.l3,.tile-sw.l3{background:color-mix(in srgb,var(--acc) 70%,var(--card))}
.tile.l4,.tile-sw.l4{background:var(--acc);color:#fff}
@media (prefers-color-scheme:dark){.tile.l4{color:#141416}}
i.tile-sw{display:inline-block;width:14px;height:14px;border-radius:3px;border:1px solid var(--line)}
.mapside{flex:1 1 240px;min-width:0}
ul.stl{columns:2;column-gap:24px;font-size:.85rem}ul.stl li{break-inside:avoid;margin:.2em 0}
@media(max-width:600px){ul.stl{columns:1}.orow{grid-template-columns:1fr 1fr;}.orow .ol{grid-column:1/-1}.orow.oh .ol{display:none}}
"""

CSS = """:root{--bg:#fbfaf7;--fg:#1d1d21;--mut:#5b5b63;--card:#fff;--line:#e3e0d8;--acc:#b45309;--s:#2f5f9e;--p:#9b2c8a;--c:#b45309;--b:#4a7d3a;--l:#7a5a1e;--u:#7a7a85;--t:#4a5a8a}
@media (prefers-color-scheme:dark){:root{--bg:#141416;--fg:#ececef;--mut:#a3a3ad;--card:#1d1d21;--line:#2e2e35;--acc:#ffb454;--s:#4f86cc;--p:#a8559b;--c:#c27a1e;--b:#5f9a4c;--l:#a07f3c;--u:#6f6f7a;--t:#6a7cb0}}
html{scroll-behavior:smooth}
body{background:var(--bg);color:var(--fg);font:16px/1.6 system-ui,sans-serif;max-width:1100px;margin:0 auto;padding:16px}
section:target,tr:target{outline:3px solid #ffb454;outline-offset:8px;border-radius:8px}
h1{font-size:1.6rem}h2{margin-top:2.2rem;border-top:1px solid var(--line);padding-top:1rem}h3{font-size:1.05rem;margin:1.2rem 0 .3rem}
a{color:inherit}small,.mut{color:var(--mut)}
.callout{background:var(--card);border-left:4px solid var(--acc);padding:10px 14px;border-radius:6px;margin:10px 0}
.pill{display:inline-block;padding:0 8px;border-radius:99px;font-size:.72rem;border:1px solid var(--line);white-space:nowrap;cursor:help}
.pill.verified{border-color:#4a7d3a;color:#4a7d3a}.pill.corrected{border-color:#2f5f9e;color:#2f5f9e}.pill.unverified{border-color:var(--acc);color:var(--acc)}.pill.disputed{border-color:#b3261e;color:#b3261e}
@media (prefers-color-scheme:dark){.pill.verified{color:#8fcf7a;border-color:#8fcf7a}.pill.corrected{color:#6ea8ee;border-color:#6ea8ee}.pill.disputed{color:#ff8a80;border-color:#ff8a80}}
.bar{display:flex;align-items:center;gap:8px;margin:4px 0}.bl{flex:0 0 260px;font-size:.9rem}.bt{flex:1;background:var(--line);border-radius:4px;height:16px;overflow:hidden}.bt i{display:block;height:100%}.bn{min-width:2em}
.own-s{background:var(--s)}.own-p{background:var(--p)}.own-c{background:var(--c)}.own-b{background:var(--b)}.own-l{background:var(--l)}.own-u{background:var(--u)}.own-t{background:var(--t)}
@media(max-width:600px){.bl{flex-basis:130px;font-size:.78rem}}
.filters button{font:inherit;font-size:.9rem;padding:4px 12px;margin:2px;border-radius:99px;border:1px solid var(--line);background:var(--card);color:var(--fg);cursor:pointer}
.filters button[aria-pressed=true]{background:var(--acc);color:#fff;border-color:var(--acc)}
.tw,.tw2{overflow-x:auto;border:1px solid var(--line);border-radius:8px}.tw{max-height:80vh}
table{border-collapse:collapse;width:100%;font-size:.85rem}#dtable{min-width:1350px}.ft{min-width:520px}
th,td{border-bottom:1px solid var(--line);padding:6px 8px;text-align:left;vertical-align:top}
th{position:sticky;top:0;background:var(--card);z-index:1}#dtable td:nth-child(2){min-width:240px}#dtable td:nth-child(n+4){min-width:150px}.nw{white-space:nowrap}
.tag{font-size:.72rem;color:var(--mut)}
.own{display:inline-block;color:#fff;font-size:.72rem;padding:0 8px;border-radius:99px;margin-bottom:2px}
details summary{cursor:pointer;color:var(--mut);font-size:.8rem}details.src ul{margin:4px 0;padding-left:16px}
.toc li{margin:2px 0}
""" + CHART_CSS

JS = """(function(){var b=document.querySelectorAll('#filters button'),r=document.querySelectorAll('#dtable tbody tr');
function f(k){b.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.f===k)});r.forEach(function(t){t.hidden=!(k==='all'||t.dataset.t===k)})}
b.forEach(function(x){x.addEventListener('click',function(){f(x.dataset.f)})});
function h(){var t=location.hash&&document.getElementById(location.hash.slice(1));if(t&&t.tagName==='TR'){f('all');t.scrollIntoView()}}
window.addEventListener('hashchange',h);h()})();
document.querySelectorAll('.sx[data-end]').forEach(function(s){s.scrollLeft=s.scrollWidth});"""

toc = [('double-check', 'What was double-checked'), ('answer', 'Short answer'), ('fig-dis-time', 'Chart: disasters over time'), ('by-ownership', 'Counts by ownership and type'), ('fig-ownership', 'Chart: disasters and deaths by ownership'),
       ('list', f'The list ({N} rows, newest first)'), ('linked', 'Disasters linked to a privatization or concession'), ('fig-dis-chain', 'Chart: from deal to disaster'),
       ('patterns', 'Patterns in the data'), ('fig-dis-map', 'Chart: disasters by state'), ('gaps', 'Gaps')]
tocl = ''.join(f'<li><a href="#{i}">{e(t)}</a></li>' for i, t in toc)

out = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Disasters in Brazil: ecological and social damage</title>
<style>{CSS}</style></head><body>
<p><a href="index.html">&larr; Back to the main page</a> &middot; <a href="index.html#profile">profile section</a> &middot; <a href="index.html#wealth-moved">wealth moved section</a></p>
<h1 id="top">Disasters in Brazil: ecological and social damage</h1>

<section id="double-check"><h2 id="double-check-h">What was double-checked, corrected and added</h2>
<div class="callout"><p><b>This page was rebuilt after a second check.</b> Each fact-check pass re-opened the cited pages and compared them with the claims. Many claims changed or lost their support.</p></div>
<div class="tw2"><table style="min-width:640px"><thead><tr><th>Area</th><th>Figures checked</th><th>Confirmed</th><th>Corrected</th><th>Not confirmable</th><th>Cases added from gap search</th></tr></thead><tbody>
<tr><td>Mining</td><td>95</td><td>40</td><td>17</td><td>30</td><td>14 entries (8 new cases, 6 additions)</td></tr>
<tr><td>Oil, chemical, nuclear, energy</td><td>90</td><td>38</td><td>30</td><td>22</td><td>13 entries</td></tr>
<tr><td>Hydro, infrastructure, land, agro</td><td>170 (75 + 95)</td><td>76 (38 + 38)</td><td>45 (21 + 24)</td><td>36 (16 + 20)</td><td>13 entries</td></tr></tbody></table></div>
<p class="mut"><small>Counts are the fact-checkers' own approximate tallies.</small></p>
<h3 id="double-check-corrections">Main corrections applied</h3>
<ul>
<li><b>Serra Pelada / Marabá:</b> "3 official dead, 60+ claimed" belongs to the 1987 Marabá bridge protest, not the mine.</li>
<li><b>Brumadinho:</b> asset freeze is R$ 11 bn (no source for R$ 16 bn); tailings about 12 million m3; one headline said 242 dead but its body says 272.</li>
<li><b>Rio Verde 2001:</b> at least 2 dead and 3 missing, 8 km, 30 ha (not 5 dead).</li>
<li><b>Mariana 2024 deal:</b> R$ 170 bn split as R$ 100 bn public, R$ 32 bn Samarco, R$ 8 bn Indigenous and traditional peoples.</li>
<li><b>Angra 1:</b> official admission 30 Jan 2023; the 90 litres is the company's own estimate.</li>
<li><b>REPAR:</b> R$ 610 million is a court-ordered minimum compensation, not a fine; the settlement was about R$ 1.4 bn.</li>
<li><b>Vila Socó:</b> the "11 dead" figure was wrong; official count 93, other counts up to 508.</li>
<li><b>Pau d'Arco:</b> no convictions. The "155 police, two convicted" line is Eldorado dos Carajás.</li>
<li><b>Petrópolis:</b> 876 displaced and 5 missing are Petrópolis figures, not Niterói.</li>
<li><b>Madeira dams:</b> the auctions were 2007 and 2008 and included state-owned partners (Furnas, Chesf, Eletrosul), so "private concession" needs qualifying.</li>
<li><b>Endosulfan:</b> no 12 Sept 2010 ban; Anvisa RDC 28/2010 set a phase-out ending 2013-2014.</li>
</ul>
<h3 id="double-check-status">Figure status on this page</h3>
<p>{NF} figures in {N} cases: {pill('verified')} {st['verified']}, {pill('corrected')} {st['corrected']}, {pill('disputed')} {st['disputed']}, {pill('unverified')} {st['unverified']}. Hover over a pill for the note.</p>
<p class="mut"><small>Cases that came from the added gap notes were not independently fact-checked; their figures carry the status the builders gave them, mostly unverified.</small></p>
</section>

<section id="answer"><h2 id="answer-h">Short answer</h2>
<div class="callout">
<p><b>{N} disasters</b>: mining ({tc['mining']}), oil, chemical, nuclear and energy ({tc['oil-chemical-nuclear-energy']}), hydro and infrastructure ({tc['hydro-infrastructure']}), land and agribusiness ({tc['land-agro']}).</p>
<p>By owner at the time: private company {oc['private-company']}, state-owned {oc['state-owned']}, privatized {oc['privatized']}, private concession {oc['private-concession']}, private landholders {oc['private-landholders']}, unknown {oc['unknown']}. <b>{len(linked)} cases</b> carry a note linking them to a privatization or concession.</p>
<p>This damage is one cost to set beside the transfers on the <a href="index.html#wealth-moved">main page</a>. An entry shows who held the asset at the time; it does not prove the transfer caused the disaster.</p>
</div>
{FIG_TIME}</section>

<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ul class="toc">{tocl}</ul></nav>

<section id="by-ownership"><h2 id="by-ownership-h">Counts by ownership at the time, and by type</h2>
<h3 id="by-owner-h">By ownership at the time</h3>
{FIG_OWN}
<p class="mut"><small>Privatized means the company or its parent was sold to private owners (for example Vale in 1997 or Eletrobras in 2022), sometimes long after the event.</small></p>
<h3 id="by-type-h">By type</h3>
{bars([(n, tc[k], 't') for k, n in TYP], max(tc.values()), 't')}
</section>

<section id="list"><h2 id="list-h">All disasters, newest first</h2>
<p class="mut">Click a filter to show one type. Open "Summary and figures" in a row for detail. Status pills show how well each figure is supported.</p>
<div class="filters" id="filters">{filt}</div>
<div class="tw"><table id="dtable"><thead><tr><th>Date</th><th>Name</th><th>Place</th><th>Operator and ownership (year privatized or conceded)</th><th>Deaths</th><th>People affected</th><th>Damage</th><th>Legal outcome</th><th>Sources</th></tr></thead><tbody>
{rows}</tbody></table></div>
</section>

<section id="linked"><h2 id="linked-h">Disasters that followed a privatization or concession</h2>
<p><b>{len(linked)} of {N} cases</b> have a linked transfer in the data: {', '.join(f'{OWNL[k][0]} {v}' for k, v in lk_own.items())}.</p>
<p class="mut">The "years after" column is the event year minus the transfer year, where the data gives one. A transfer before an event does not show cause.</p>
<div class="tw2"><table style="min-width:800px"><thead><tr><th>Date</th><th>Disaster</th><th>Ownership</th><th>Linked transfer (from the data)</th><th>Years after</th></tr></thead><tbody>
{lrows}</tbody></table></div>
{FIG_CHAIN}
</section>

<section id="patterns"><h2 id="patterns-h">Patterns in the data</h2>
<div class="callout"><p>These are counts taken straight from the cases above. They describe the sample, not all disasters in Brazil.</p></div>
{FIG_MAP}
<h3 id="patterns-matrix">Ownership by type</h3>
<div class="tw2"><table style="min-width:600px"><thead><tr><th>Ownership</th>{''.join(f'<th>{e(n)}</th>' for _, n in TYP)}<th>Total</th></tr></thead><tbody>{matrix}</tbody></table></div>
<h3 id="patterns-decades">Cases by decade of the event</h3>
{decbars}
<h3 id="patterns-status">Figure status by type</h3>
<div class="tw2"><table style="min-width:520px"><thead><tr><th>Type</th><th>verified</th><th>corrected</th><th>disputed</th><th>unverified</th></tr></thead><tbody>{strows}</tbody></table></div>
<h3 id="patterns-other">Other counts</h3>
<ul>
<li>Cases where a transfer year is given: {len(gaps_y)}. Years between that transfer and the event: from {min(gaps_y)} to {max(gaps_y)}; a negative number means the event came before the transfer.</li>
<li>Cases whose deaths field says none were reported: {nodeath}.</li>
<li>Cases whose legal-outcome field starts with a "no fine, charge or case" statement: {nolegal}.</li>
<li>Cases with ownership unknown or mixed: {vc}.</li>
</ul>
</section>

<section id="gaps"><h2 id="gaps-h">Gaps</h2>
<div class="callout"><p><b>{st['unverified']} of {NF} figures are unverified</b> and {st['disputed']} are disputed. Treat them as leads.</p></div>
<ul>
<li>{nolink} figures have no source link.</li>
<li>The added cases (13 for oil and energy, 13 for hydro and land, 14 for mining) were read once and not independently checked.</li>
<li><b>Mining, not found:</b> Itabira dust from the Cauê and Conceição mines, the Caetité STF outcome, the Herculano jury verdict, the Munich TÜV SÜD hearing results, the final Minas-Rio fine payment, Congonhas evacuations, MRN's current shareholders. Rests on search summaries: the Brumadinho STJ ruling of 16 June 2026, Vale's 41.7% stake sold in 1997, the Córrego do Sítio self-rescue zone population.</li>
<li><b>Oil and energy, not found:</b> a P-20 leak, a 2022 São Sebastião leak, fuel-theft pipeline explosions with deaths, a 1990s Ultrafértil leak, Pampulha, deaths from the 2019 spill, Amapá court rulings, Paulínia and Rhodia settlement details. Rests on search summaries: ANEEL fines for the 2018 blackout, the ONS cause for 2009 and 2018, the Transpetro 2013 TRF3 pages, the Landulpho Alves 1992 R$ 300M Ibama fine.</li>
<li><b>Hydro and land, not covered:</b> Santa Helena and other dam breaks, Rio Madeira 2014 follow-up, Chapada do Apodi follow-up. Unconfirmed: Colniza sentences, Raposa's 1.7 million ha, the Aracruz settlement area, the Orós death toll, the Teles Pires blasting year, the final Barra Grande outcome. The link between deforestation and the 2023 drought was not supported by the pages opened.</li>
<li>Several sources returned 403 or timed out, so some items rest on search snippets.</li>
<li>Judgment calls in the data: Balbina, Tucuruí and Sobradinho are labelled privatized (2021) because of the Eletrobras law, long after the dams; Hydro Alunorte was a private-to-private sale; Mariana is marked privatized because Vale co-owned Samarco.</li>
</ul>
</section>
<script>{JS}</script>
</body></html>
"""
open(os.path.join(D, 'disasters.html'), 'w', encoding='utf-8').write(out)
print(N, dict(oc), dict(tc))
