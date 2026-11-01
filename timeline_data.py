"""Shared loaders for build_timeline.py and build.py.

Loads terms, people (merged across the six era files), cases, disasters and
series, and decides which term each case and each person belongs to. The rules
are written out on timeline.html#method.
"""
import collections
import datetime
import glob
import json
import os
import re

ROOT = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(ROOT, "data")

CASE_FILES = ["g1-colony", "g2-republic", "g3-dictatorship", "g4-privatization",
              "g5-2003-2016", "g6-2016-2026", "g7-cross-cutting"]
DIS_FILES = ["g8-dis-mining", "g9-dis-oil", "g10-dis-hydro-land"]
SERIES_FILES = ["series-patrimony", "series-purchasing", "series-concentration", "series-political"]
TODAY = datetime.date(2026, 11, 1)
COLONY = "colony"

# People-file term labels -> terms.json ids. Labels before 1822 go to the colony block.
LABEL_TERMS = {
    "Pedro I, 1822-1831": ["t-pedro-i-1822"],
    "Pedro II, 1840-1889": ["t-pedro-ii-1840"],
    "Deodoro da Fonseca 1889-1891": ["t-deodoro-1889"],
    "Floriano Peixoto and Prudente de Morais 1891-1898": ["t-floriano-1891", "t-prudente-de-morais-1894"],
    "Campos Sales 1898-1902": ["t-campos-sales-1898"],
    "Rodrigues Alves 1902-1906": ["t-rodrigues-alves-1902"],
    "Afonso Pena 1906-1909": ["t-afonso-pena-1906"],
    "Nilo Pecanha 1909-1910": ["t-nilo-pecanha-1909"],
    "Hermes da Fonseca 1910-1914": ["t-hermes-da-fonseca-1910"],
    "Epitacio Pessoa 1919-1922": ["t-epitacio-pessoa-1919"],
    "Washington Luis 1926-1930": ["t-washington-luis-1926"],
    "Vargas 1930-1945": ["t-vargas-1930", "t-vargas-1934", "t-vargas-1937"],
    "Dutra 1946-1951": ["t-dutra-1946"],
    "Vargas 1951-1954": ["t-vargas-1951"],
    "Kubitschek 1956-1961": ["t-juscelino-kubitschek-1956"],
    "Janio Quadros 1961": ["t-janio-quadros-1961"],
    "Goulart 1961-1964": ["t-joao-goulart-1961"],
    "Castelo Branco 1964": ["t-castelo-branco-1964"],
    "Castelo Branco 1964-1967": ["t-castelo-branco-1964"],
    "Costa e Silva 1967-1969": ["t-costa-e-silva-1967"],
    "Médici 1969-1974": ["t-medici-1969"],
    "Geisel 1974-1979": ["t-geisel-1974"],
    "Figueiredo 1979-1985": ["t-figueiredo-1979"],
    "Sarney 1985 (first civilian term)": ["t-sarney-1985"],
    "José Sarney, 1985-1990": ["t-sarney-1985"],
    "Fernando Collor, 1990-1992": ["t-collor-1990"],
    "Itamar Franco, 1992-1994": ["t-itamar-franco-1992"],
    "Fernando Henrique Cardoso, 1995-1998": ["t-fhc-1995"],
    "Fernando Henrique Cardoso, 1999-2002": ["t-fhc-1999"],
    "Lula 1 (2003-2006)": ["t-lula-2003"],
    "Lula 2 (2007-2010)": ["t-lula-2007"],
    "Dilma 1 (2011-2014)": ["t-dilma-2011"],
    "Dilma 2 (2015-2016)": ["t-dilma-2015"],
    "Michel Temer, 2016-2019": ["t-temer-2016"],
    "Jair Bolsonaro, 2019-2023": ["t-bolsonaro-2019"],
    "Luiz Inacio Lula da Silva (third term), 2023-": ["t-lula-2023"],
}

BASIS_TEXT = {"documented-act": "acted", "in-office": "in office at the time"}


def load(name):
    with open(os.path.join(DATA, name + ".json"), encoding="utf-8") as fh:
        return json.load(fh)


def first_year(v):
    if v is None:
        return None
    if isinstance(v, int):
        return v
    m = re.search(r"\b(1[4-9]\d\d|20\d\d)\b", str(v))
    return int(m.group(1)) if m else None


def parse_date(s):
    """'YYYY-MM-DD' / 'YYYY-MM' / 'YYYY' / int -> date, else None."""
    if s is None or s == "":
        return None
    if isinstance(s, int):
        return datetime.date(s, 7, 1)
    m = re.fullmatch(r"(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", str(s).strip())
    if not m:
        y = first_year(s)
        return datetime.date(y, 7, 1) if y else None
    y, mo, d = int(m.group(1)), int(m.group(2) or 7), int(m.group(3) or 1)
    return datetime.date(y, mo, d)


def frac(d):
    return d.year + (d.timetuple().tm_yday - 1) / 365.25


# ---------------------------------------------------------------- terms
def load_terms():
    terms = load("terms")["terms"]
    out = []
    for t in terms:
        t = dict(t)
        t["_start"] = parse_date(t["start"])
        t["_end"] = parse_date(t["end"]) if t.get("end") else TODAY
        t["_open"] = not t.get("end")
        t["_sid"] = "term-" + t["id"][2:]
        out.append(t)
    out.sort(key=lambda t: t["_start"])
    return out


def term_ref_years(t):
    """Start = last full year before taking office (or the start year if the term began after March).
    End = last year in office (the year before, if it ended in January-March)."""
    s, e = t["_start"], t["_end"]
    sy = s.year - 1 if s.month <= 3 else s.year
    if t["_open"]:
        ey = None
    else:
        ey = e.year - 1 if e.month <= 3 else e.year
    return sy, ey


# ---------------------------------------------------------------- cases and disasters
def load_cases():
    cases = []
    for f in CASE_FILES:
        for c in load(f):
            c = dict(c)
            c["_y"] = int(c["start_year"])
            c["_group"] = f
            cases.append(c)
    return cases


def load_disasters():
    out = []
    for f in DIS_FILES:
        for d in load(f):
            d = dict(d)
            d["_y"] = first_year(d.get("date"))
            out.append(d)
    return out


def load_series():
    S = collections.OrderedDict()
    for f in SERIES_FILES:
        for s in load(f)["series"]:
            s = dict(s)
            s["_pts"] = {int(y): v for y, v in s["points"] if v is not None}
            S[s["id"]] = s
    return S


# ---------------------------------------------------------------- people
def _key_post(p):
    return (p.get("post"), str(p.get("start")), str(p.get("end")))


def load_people():
    """Returns (people_by_id, groups) where groups = [(file, label, [pids])]."""
    people = collections.OrderedDict()
    groups = []
    extra = {}
    for f in sorted(glob.glob(os.path.join(DATA, "people-e*.json"))):
        d = json.load(open(f, encoding="utf-8"))
        fname = os.path.basename(f)[:-5]
        extra[fname] = {k: v for k, v in d.items() if k not in ("terms", "people", "foreign_counterparts")}
        extra[fname]["foreign_counterparts"] = d.get("foreign_counterparts", [])
        for p in d["people"]:
            pid = p["id"]
            if pid not in people:
                q = {"id": pid, "name": p["name"], "posts": [], "before": [], "after": [], "foreign_ties": [],
                     "case_links": [], "controversies": [], "sources": [], "verified_sources": [], "_files": []}
                people[pid] = q
            q = people[pid]
            q["_files"].append(fname)
            seen = {_key_post(x) for x in q["posts"]}
            for x in p.get("posts") or []:
                if _key_post(x) not in seen:
                    q["posts"].append(x)
                    seen.add(_key_post(x))
            for fld in ("before", "after"):
                v = (p.get(fld) or "").strip()
                if v and v not in q[fld]:
                    q[fld].append(v)
            for fld, key in (("foreign_ties", ("counterpart", "kind")), ("case_links", ("case_id", "role")),
                             ("controversies", ("what",)), ("sources", ("url",))):
                seen = {tuple(x.get(k) for k in key) for x in q[fld]}
                for x in p.get(fld) or []:
                    kk = tuple(x.get(k) for k in key)
                    if kk not in seen:
                        q[fld].append(x)
                        seen.add(kk)
            for u in p.get("verified_sources") or []:
                if u not in q["verified_sources"]:
                    q["verified_sources"].append(u)
        for t in d["terms"]:
            groups.append((fname, t["term"], list(t["decision_makers"])))
    for p in people.values():
        p["_status"] = "verified" if any(x.get("status") == "verified" for x in p["posts"]) else "unverified"
    return people, groups, extra


def post_span(x):
    s = parse_date(x.get("start"))
    e = parse_date(x.get("end"))
    if s is None and e is None:
        return None
    if s is None:
        s = e
    if e is None:
        e = s
    return s, e


def assign_people(terms, people, groups):
    """term id (or COLONY) -> ordered list of pids; also colony groups [(label, [pids])]."""
    tid = {t["id"]: t for t in terms}
    out = collections.defaultdict(list)
    colony_groups = []
    unmapped = []
    for fname, label, pids in groups:
        for pid in pids:
            assert pid in people, (fname, pid)
        if label not in LABEL_TERMS:
            y = first_year(label)
            if y is not None and y < 1822:
                colony_groups.append((label, pids))
                for pid in pids:
                    if pid not in out[COLONY]:
                        out[COLONY].append(pid)
                continue
            unmapped.append(label)
            continue
        ids = LABEL_TERMS[label]
        for i in ids:
            assert i in tid, (label, i)
        for pid in pids:
            if len(ids) == 1:
                targets = ids
            else:
                spans = [post_span(x) for x in people[pid]["posts"]]
                spans = [s for s in spans if s]
                targets = [i for i in ids if any(s <= tid[i]["_end"] and e >= tid[i]["_start"] for s, e in spans)]
                if not targets:
                    targets = ids
            for i in targets:
                if pid not in out[i]:
                    out[i].append(pid)
    assert not unmapped, unmapped
    colony_groups.sort(key=lambda g: first_year(g[0]))
    return out, colony_groups


def case_people(people):
    """case id -> list of (pid, link) with links deduped per person and basis."""
    out = collections.defaultdict(list)
    for pid, p in people.items():
        seen = set()
        for l in p["case_links"]:
            k = (l["case_id"], l["basis"])
            if k in seen:
                continue
            seen.add(k)
            out[l["case_id"]].append((pid, l))
    for cid in out:
        out[cid].sort(key=lambda t: (t[1]["basis"] != "documented-act", people[t[0]]["name"]))
    return out


def assign_cases(terms, cases, term_people, cp):
    """case id -> term id (or COLONY).
    Rule: the term(s) in office during the case's start year. If several, the term whose mapped
    decision-makers have the most links to the case wins (documented-act counts 2, in-office 1);
    on a tie, the term in office on 1 July of that year."""
    first = terms[0]["_start"]
    out = {}
    for c in cases:
        y = c["_y"]
        if datetime.date(y, 12, 31) < first:
            out[c["id"]] = COLONY
            continue
        cand = [t for t in terms if t["_start"] <= datetime.date(y, 12, 31) and t["_end"] >= datetime.date(y, 1, 1)]
        if not cand:
            out[c["id"]] = COLONY
            continue
        mid = datetime.date(y, 7, 1)

        def score(t):
            members = set(term_people.get(t["id"], []))
            sc = sum(2 if l["basis"] == "documented-act" else 1 for pid, l in cp.get(c["id"], []) if pid in members)
            on_mid = t["_start"] <= mid <= t["_end"]
            return (sc, on_mid)
        best = max(cand, key=score)
        if y == 1822 and best["_start"] > mid and score(best)[0] == 0:
            out[c["id"]] = COLONY
        else:
            out[c["id"]] = best["id"]
    return out


def person_anchor(pid, place):
    short = COLONY if place == COLONY else place[2:]
    return f"{pid}-in-{short}"


def load_all():
    terms = load_terms()
    people, groups, extra = load_people()
    term_people, colony_groups = assign_people(terms, people, groups)
    cases = load_cases()
    cp = case_people(people)
    case_term = assign_cases(terms, cases, term_people, cp)
    # first appearance of each person (chronological), used as their main anchor
    # people in no decision-maker list: place them in the term of each case they are linked to
    placed = {pid for v in term_people.values() for pid in v}
    added_by_case = set()
    for pid, p in people.items():
        if pid in placed:
            continue
        for l in p["case_links"]:
            place = case_term.get(l["case_id"])
            if place and pid not in term_people[place]:
                term_people[place].append(pid)
                added_by_case.add(pid)
    order = [COLONY] + [t["id"] for t in terms]
    first_place = {}
    for place in order:
        for pid in term_people.get(place, []):
            first_place.setdefault(pid, place)
    return {
        "terms": terms, "people": people, "groups": groups, "extra": extra,
        "term_people": term_people, "colony_groups": colony_groups, "cases": cases,
        "case_people": cp, "case_term": case_term, "first_place": first_place, "added_by_case": added_by_case,
        "disasters": load_disasters(), "series": load_series(),
    }


def person_link_target(pid, case_id, D):
    """Where a 'Decided by' link should point on timeline.html."""
    place = D["case_term"].get(case_id)
    if place and pid in D["term_people"].get(place, []):
        return person_anchor(pid, place)
    fp = D["first_place"].get(pid)
    if fp:
        return person_anchor(pid, fp)
    return None


# ---------------------------------------------------------------- deals ledger
# Rules are stated on timeline.html#deals. Pure functions only: no printing here.

# Not a transfer into private or foreign hands, or a tally of other cases.
NOT_DEALS = {
    "e2-16": "the state created its own companies (public sector got the assets)",
    "e3-02": "pollution costs of a state-led pole; no one was handed an asset (who got: not applicable)",
    "e4-03": "tally of the PND sales, already listed one by one",
    "e6-21": "the Union's attempt to win back voting power after a sale",
    "x-01": "cost estimates for the Zona Franca, listed under e3-07",
    "x-03": "estimate of the scale of land-grabbing, not one act",
    "x-19": "yearly series of tax expenditures, not one act",
    "e6-28": "yearly total of tax expenditures, not one act",
}

# Long processes with no single signing act: shown as "ongoing under" the start term.
ONGOING = {
    "e1-08": "gold royalty collection over a century",
    "e3-01": "public land passed to colonisers over decades",
    "e3-05": "occupation of Xavante land over decades",
    "e3-21": "open-pit gold rush run by the state and a cooperative",
    "e4-18": "evasion through CC5 accounts, uncovered later",
    "e5-03": "cartel and kickbacks over a decade",
    "e6-03": "pricing policy kept across terms, no signed act",
    "e6-09": "illegal mining expansion, no signed act",
    "e6-13": "budget practice over three years",
    "x-04": "private colonisation over two decades",
    "x-05": "land-grabbing through the courts over decades",
    "x-07": "fraudulent land titles over decades",
    "x-08": "fraudulent land titles over decades",
    "x-18": "registry fraud uncovered over years",
    "x-24": "self-declared claims on public forest over years",
}

# Cross-cutting entries that describe the same deal as an era entry: listed once, under the era entry.
SAME_DEAL = {"x-06": "e3-11", "x-10": "e4-13", "x-13": "e4-17", "x-20": "e5-13", "x-23": "e5-14"}

# Later signing acts in another term, each taken from the case's own "what" text.
EXTRA_SIGNINGS = {
    "e2-20": [("1964-11", "Amforp subsidiaries sold to Eletrobras, Nov 1964")],
    "e4-05": [("1993-04-02", "CSN control block auctioned, 2 Apr 1993")],
    "e4-12": [("1999-09-23", "ANP round 1, 23 Sep 1999")],
    "e4-25": [("1999", "Paranapanema sold to Duke Energy, 1999")],
    "e5-17": [("2013-10-21", "Libra auction, 21 Oct 2013")],
    "e6-02": [("2019-06-13", "TAG sale closed, 13 Jun 2019")],
    "e6-04": [("2020-05-27", "concession addendum signed, 27 May 2020")],
}

# Disaster -> case links decided by hand: (case id or None, reason). Checked before fuzzy matching.
DIS_LINK_OVERRIDES = {
    "d-hydro-alunorte-barcarena-2018": (None, "the text names a 2011 sale between two private firms, which is not a case"),
    "d-belo-monte-blackout-2018": (None, "the text names the 2014 transmission auction, not the dam concession (e5-15)"),
    "d-chevron-frade-2011": (None, "the text says the concession round was not identified"),
    "d-amapa-blackout-2020": (None, "the 2008 LMTE transmission concession is not a case"),
    "d-jirau-riot-2011": ("e5-06", "the text names the Jirau concession auction of 19 May 2008; e5-06 covers Jirau"),
    "d-belo-monte-2010": ("e5-15", "the text names the April 2010 concession auction of this dam; e5-15 is the Belo Monte concession"),
}

# Disasters dated before their deal that still count as later: (reason).
DIS_AFTER_OVERRIDES = {
    "d-carajas-railway-1985": "the railway dates from 1985, but the 39 deaths are counted from 2010, after the 1997 sale",
}

_MON = {m: i + 1 for i, m in enumerate(["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"])}
_STOP = set("the and for from with was were that this into after under its sold sale were state public private by of in on to a an".split())


def term_on(terms, d):
    for t in terms:
        if t["_start"] <= d < t["_end"] or (t["_open"] and t["_start"] <= d):
            return t["id"]
    return None


def signing_date(c):
    """First full date ('30 Nov 2016') in the title or 'what' text that falls in the case's start year, else None."""
    for txt in (c.get("title") or "", c.get("what") or ""):
        for d, mo, y in re.findall(r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b", txt):
            if int(y) == c["_y"]:
                return datetime.date(int(y), _MON[mo.lower()], int(d))
    return None


def deal_places(terms, cases, case_term):
    """case id -> list of (place, year, note) where place is a term id or COLONY, plus status
    'deal' / 'ongoing' / 'not-deal' / 'same'. Start term: the term in office on the signing date when the
    case text gives one in the start year and several terms held office that year; else the case's term on
    the page (case_term)."""
    out = {}
    for c in cases:
        cid = c["id"]
        if cid in NOT_DEALS:
            out[cid] = ("not-deal", [])
            continue
        if cid in SAME_DEAL:
            out[cid] = ("same", [])
            continue
        start = case_term[cid]
        y = c["_y"]
        if start != COLONY:
            cand = [t for t in terms if t["_start"] <= datetime.date(y, 12, 31) and t["_end"] >= datetime.date(y, 1, 1)]
            sd = signing_date(c)
            if len(cand) > 1 and sd:
                start = term_on(terms, sd) or start
        places = [(start, y, None)]
        for ds, note in EXTRA_SIGNINGS.get(cid, []):
            p = term_on(terms, parse_date(ds))
            if p and p not in [x[0] for x in places]:
                places.append((p, first_year(ds), note))
        out[cid] = ("ongoing" if cid in ONGOING else "deal", places)
    return out


def _fold(s):
    import unicodedata
    return "".join(ch for ch in unicodedata.normalize("NFKD", str(s).lower()) if not unicodedata.combining(ch))


def _toks(s):
    """Word stems (first 7 letters) of words with 3+ letters, no stop words, no numbers."""
    return {w[:7] for w in re.findall(r"[a-z]+", _fold(s)) if len(w) >= 3 and w not in _STOP}


_DATE_RE = r"\b(\d{1,2}) (Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* (\d{4})\b"


def match_disasters(cases, disasters):
    """disaster id -> (case id or None, how, detail). how: 'override', 'fuzzy', 'unmatched'.
    Only the linked_transfer text is matched, against case titles. Score = share of the title's word stems
    found in the text, each stem weighted by how rare it is across titles; +0.3 when a year in the text equals
    the case start year; +0.5 when a full date in the text ('6 May 1997') appears in the case title or text.
    Entries that are not deals, or duplicates, are not candidates. A match needs a score of at least 0.6 and
    a lead of 0.15 over the runner-up; anything else is reported as unmatched."""
    import math
    cand = [c for c in cases if c["id"] not in NOT_DEALS and c["id"] not in SAME_DEAL]
    ctoks = {c["id"]: _toks(re.sub(r"\(.*?\)", " ", c["title"])) for c in cand}
    df = collections.Counter(w for ts in ctoks.values() for w in ts)
    idf = {w: math.log((1 + len(cand)) / (1 + n)) + 1 for w, n in df.items()}
    out = {}
    for d in disasters:
        lt = (d.get("linked_transfer") or "").strip()
        if not lt:
            continue
        if d["id"] in DIS_LINK_OVERRIDES:
            cid, why = DIS_LINK_OVERRIDES[d["id"]]
            out[d["id"]] = (cid, "override", why)
            continue
        lt_t = _toks(lt)
        years = {int(y) for y in re.findall(r"\b(1[5-9]\d\d|20\d\d)\b", lt)}
        dates = {(int(a), m.lower(), int(y)) for a, m, y in re.findall(_DATE_RE, lt)}
        scored = []
        for c in cand:
            ct = ctoks[c["id"]]
            if not ct:
                continue
            s = sum(idf[w] for w in ct & lt_t) / sum(idf[w] for w in ct)
            if c["_y"] in years:
                s += 0.3
            cdates = {(int(a), m.lower(), int(y)) for a, m, y in re.findall(_DATE_RE, c["title"] + " " + (c.get("what") or ""))}
            if dates & cdates:
                s += 0.5
            scored.append((round(s, 3), c["id"]))
        scored.sort(reverse=True)
        (s1, c1), (s2, c2) = scored[0], scored[1]
        if s1 >= 0.6 and s1 - s2 >= 0.15:
            out[d["id"]] = (c1, "fuzzy", f"score {s1:.2f}, next {c2} {s2:.2f}")
        else:
            out[d["id"]] = (None, "unmatched", f"best {c1} {s1:.2f}, next {c2} {s2:.2f}")
    return out


def deaths_count(text):
    """Leading number -> int; text starting with 'None' -> 0; anything else -> None (no count)."""
    t = (text or "").strip()
    m = re.match(r"(\d[\d,]*)", t)
    if m:
        return int(m.group(1).replace(",", ""))
    if t.lower().startswith("none"):
        return 0
    return None
