"""What KIND of news is this?

Two signals, combined:

  1. Alpha Vantage's own topic tags, which are broad (Earnings, Mergers &
     Acquisitions, Technology...) and come free in the feed.
  2. Keyword rules over the headline and summary, which catch the specific
     things investors actually react to and no feed labels: layoffs,
     lawsuits, recalls, guidance cuts, executive departures, short-seller
     reports.

The point is not a perfect classifier. It is that "NVDA after a product
launch" and "NVDA after a lawsuit" become separate rows in the evidence
ledger, so the fingerprint can say which kinds of news actually move a
stock and which it shrugs off. That is a claim no brokerage app makes.

Rules are ordered: the first match wins, and the list runs from most
specific (layoffs) to most generic (market commentary), so a headline that
mentions both a lawsuit and the stock price lands on "legal".
"""
from __future__ import annotations

import re

# (topic, weight, patterns). Weight becomes the confidence when matched
# by keyword alone; a vendor tag agreeing pushes it higher.
RULES: list[tuple[str, float, list[str]]] = [
    ("layoffs", 0.9, [
        r"\blay ?offs?\b", r"\blaying off\b", r"\bjob cuts?\b", r"\bcut(?:s|ting)? \d+[,\d]* jobs\b",
        r"\bworkforce reduction\b", r"\bredundanc", r"\bhiring freeze\b", r"\bstaff cuts?\b",
        r"\bslash(?:es|ing)? (?:its )?(?:work ?force|staff|jobs)\b", r"\brestructuring plan\b",
    ]),
    ("legal", 0.85, [
        r"\blawsuits?\b", r"\bsue[sd]?\b", r"\bsuing\b", r"\bsettle(?:s|d|ment)\b",
        r"\bclass action\b", r"\bantitrust\b", r"\bpatent (?:suit|dispute|infringement)\b",
        r"\bcourt\b", r"\bjudge\b", r"\bverdict\b", r"\bfine[sd]? \$", r"\bpenalt(?:y|ies)\b",
    ]),
    ("regulation", 0.8, [
        r"\bregulator", r"\bSEC (?:probe|investigation|charges|filing)\b", r"\bFTC\b", r"\bDOJ\b",
        r"\bFDA (?:approv|reject|warning)", r"\bprobe\b", r"\binvestigat(?:ion|ing)\b",
        r"\bsubpoena\b", r"\bexport (?:ban|curbs?|controls?|restrictions?)\b", r"\btariffs?\b",
        r"\bsanctions?\b", r"\bban(?:s|ned)? (?:the )?sale\b",
    ]),
    ("recall_safety", 0.85, [
        r"\brecall(?:s|ed|ing)?\b", r"\bdefect", r"\bsafety (?:probe|issue|concern)",
        r"\bcrash(?:es)? involv", r"\bcontamina",
    ]),
    ("guidance", 0.85, [
        r"\bguidance\b", r"\bforecasts?\b", r"\boutlook\b", r"\brais(?:es|ed) (?:its )?(?:full-year|annual|Q\d)\b",
        r"\bcuts? (?:its )?(?:full-year|annual|outlook|forecast)\b", r"\bwarn(?:s|ed|ing)\b",
        r"\bprofit warning\b", r"\bpre-?announce",
    ]),
    ("earnings", 0.9, [
        r"\bearnings\b", r"\bquarterly results\b", r"\bQ[1-4] (?:results|report)\b",
        r"\bbeats? (?:on )?(?:estimates|expectations|the street)\b", r"\bmisses? (?:estimates|expectations)\b",
        r"\brevenue (?:rose|fell|jumped|grew|declined)\b", r"\beps\b",
    ]),
    ("m_and_a", 0.85, [
        r"\bacquir(?:e|es|ed|ing|ition)\b", r"\bmerge(?:r|s|d)?\b", r"\btakeover\b",
        r"\bbuys? (?:stake|out)\b", r"\bdeal to buy\b", r"\bspin-?off\b", r"\bdivest",
    ]),
    ("executive", 0.8, [
        r"\bceo\b", r"\bcfo\b", r"\bchief executive\b", r"\bsteps? down\b", r"\bresign",
        r"\bappoint(?:s|ed|ment)\b", r"\bnames? new\b", r"\bousted\b", r"\bsuccession\b",
    ]),
    ("product", 0.75, [
        r"\blaunch(?:es|ed|ing)?\b", r"\bunveil", r"\bannounce[sd]? (?:the )?new\b",
        r"\brelease[sd]? (?:the )?new\b", r"\bnext-gen", r"\bchip\b", r"\bmodel\b",
        r"\bpartnership with\b", r"\bcontract (?:win|award)",
    ]),
    ("supply_chain", 0.8, [
        r"\bsupply chain\b", r"\bshortage\b", r"\bproduction (?:halt|cut|delay)",
        r"\bfactory\b", r"\bplant (?:closure|shutdown)\b", r"\bbacklog\b", r"\bdelivery delays?\b",
    ]),
    ("analyst", 0.7, [
        r"\bupgrade[sd]?\b", r"\bdowngrade[sd]?\b", r"\bprice target\b", r"\binitiates? coverage\b",
        r"\bbuy rating\b", r"\bsell rating\b", r"\boverweight\b", r"\bunderweight\b",
    ]),
    ("short_seller", 0.9, [
        r"\bshort seller\b", r"\bshort-seller\b", r"\bfraud allegations?\b",
        r"\baccounting (?:probe|irregularities|concerns)\b",
    ]),
    ("capital_return", 0.8, [
        r"\bbuy ?backs?\b", r"\brepurchase\b", r"\bdividend\b", r"\bstock split\b",
        r"\bsecondary offering\b", r"\bconvertible notes?\b",
    ]),
    ("macro_linked", 0.6, [
        r"\bfed\b", r"\binflation\b", r"\brate (?:cut|hike|decision)\b", r"\brecession\b",
        r"\bjobs report\b", r"\bcpi\b",
    ]),
]

COMPILED = [(name, weight, [re.compile(p, re.I) for p in pats])
            for name, weight, pats in RULES]

# Alpha Vantage's tags mapped onto ours, used to confirm a keyword hit or
# to label an article no rule matched.
VENDOR_MAP = {
    "earnings": "earnings",
    "ipo": "capital_return",
    "mergers & acquisitions": "m_and_a",
    "financial markets": "market",
    "economy - fiscal": "macro_linked",
    "economy - monetary": "macro_linked",
    "economy - macro": "macro_linked",
    "energy & transportation": "sector",
    "finance": "sector",
    "life sciences": "sector",
    "manufacturing": "sector",
    "real estate & construction": "sector",
    "retail & wholesale": "sector",
    "technology": "sector",
    "blockchain": "sector",
}

# Topics whose direction is obvious enough to note in an alert.
NEGATIVE_BY_NATURE = {"layoffs", "legal", "recall_safety", "short_seller"}

LABELS = {
    "layoffs": "layoffs / job cuts",
    "legal": "lawsuit or settlement",
    "regulation": "regulator or government action",
    "recall_safety": "recall or safety issue",
    "guidance": "guidance change",
    "earnings": "earnings report",
    "m_and_a": "merger or acquisition",
    "executive": "executive change",
    "product": "product or partnership",
    "supply_chain": "supply chain",
    "analyst": "analyst rating change",
    "short_seller": "short-seller or fraud claim",
    "capital_return": "buyback or dividend",
    "macro_linked": "macro-driven story",
    "market": "market commentary",
    "sector": "sector news",
    "other": "general company news",
}


def classify(title: str, summary: str = "", vendor_topics: list[str] | None = None
             ) -> tuple[str, float]:
    """Return (topic, confidence). First rule to match wins."""
    text = f"{title or ''}. {summary or ''}"
    vendor = [VENDOR_MAP.get((v or "").lower()) for v in (vendor_topics or [])]
    vendor = [v for v in vendor if v]

    for name, weight, patterns in COMPILED:
        if any(p.search(text) for p in patterns):
            conf = min(0.98, weight + 0.08) if name in vendor else weight
            return name, round(conf, 2)

    for v in vendor:                      # no keyword hit: fall back to the feed
        if v not in {"sector", "market"}:
            return v, 0.5
    if vendor:
        return vendor[0], 0.4
    return "other", 0.3


def label(topic: str) -> str:
    return LABELS.get(topic, topic.replace("_", " "))