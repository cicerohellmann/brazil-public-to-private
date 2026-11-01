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
"""

JS = """(function(){var b=document.querySelectorAll('#filters button'),r=document.querySelectorAll('#dtable tbody tr');
function f(k){b.forEach(function(x){x.setAttribute('aria-pressed',x.dataset.f===k)});r.forEach(function(t){t.hidden=!(k==='all'||t.dataset.t===k)})}
b.forEach(function(x){x.addEventListener('click',function(){f(x.dataset.f)})});
function h(){var t=location.hash&&document.getElementById(location.hash.slice(1));if(t&&t.tagName==='TR'){f('all');t.scrollIntoView()}}
window.addEventListener('hashchange',h);h()})();"""

toc = [('double-check', 'What was double-checked'), ('answer', 'Short answer'), ('by-ownership', 'Counts by ownership and type'),
       ('list', f'The list ({N} rows, newest first)'), ('linked', 'Disasters linked to a privatization or concession'),
       ('patterns', 'Patterns in the data'), ('gaps', 'Gaps')]
tocl = ''.join(f'<li><a href="#{i}">{e(t)}</a></li>' for i, t in toc)

out = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Disasters in Brazil: ecological and social damage</title>
<style>{CSS}</style></head><body>
<p><a href="index.html">&larr; Back to the main page</a> &middot; <a href="index.html#profile">profile section</a> &middot; <a href="index.html#wealth-moved">wealth moved section</a></p>
<h1 id="top">Disasters in Brazil: ecological and social damage</h1>

<section id="double-check"><h2 id="double-check-h">What was double-checked, corrected and added</h2>
<div class="callout"><p><b>This page was rebuilt after a second check.</b> Each fact-check pass re-opened the cited pages and compared them with the claims. Many claims changed or lost their support.</p></div>
<table><thead><tr><th>Area</th><th>Figures checked</th><th>Confirmed</th><th>Corrected</th><th>Not confirmable</th><th>Cases added from gap search</th></tr></thead><tbody>
<tr><td>Mining</td><td>95</td><td>40</td><td>17</td><td>30</td><td>14 entries (8 new cases, 6 additions)</td></tr>
<tr><td>Oil, chemical, nuclear, energy</td><td>90</td><td>38</td><td>30</td><td>22</td><td>13 entries</td></tr>
<tr><td>Hydro, infrastructure, land, agro</td><td>170 (75 + 95)</td><td>76 (38 + 38)</td><td>45 (21 + 24)</td><td>36 (16 + 20)</td><td>13 entries</td></tr></tbody></table>
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
</div></section>

<nav id="contents" aria-label="Contents"><h2 id="contents-h">Contents</h2><ul class="toc">{tocl}</ul></nav>

<section id="by-ownership"><h2 id="by-ownership-h">Counts by ownership at the time, and by type</h2>
<h3 id="by-owner-h">By ownership at the time</h3>
{bars([(n, oc[k], c) for k, n, c in OWN], max(oc.values()), 'o')}
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
</section>

<section id="patterns"><h2 id="patterns-h">Patterns in the data</h2>
<div class="callout"><p>These are counts taken straight from the cases above. They describe the sample, not all disasters in Brazil.</p></div>
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
