"""Country-level flow graph.

Energy-Charts exposes cross-border flows per *country*, not per bidding zone.
This module bridges the M1 zone graph (data/zones.json + interconnectors.json)
to a country-level graph: one FlowNode per country, centroid = mean of its
member zones, plus a regime lookup derived from the real zone borders.

ISO-2 codes are used as node ids. They coincide with the zone key for
single-zone countries (FR, BE, NL...); multi-zone countries (IT, NO, SE, DK)
and DE-LU get a dedicated country node. LU is an alias of DE (same bidding
zone DE-LU), kept only so Energy-Charts' "Luxembourg" neighbour folds in.
"""

from __future__ import annotations

from functools import lru_cache

from .interconnectors import load_interconnectors
from .zones import load_zones
from ..models import FlowNode

# ISO-2 country -> member zone keys. Domain structure (not EIC codes).
COUNTRY_ZONES: dict[str, list[str]] = {
    "FR": ["FR"],
    "DE": ["DE-LU"],
    "BE": ["BE"],
    "NL": ["NL"],
    "AT": ["AT"],
    "PL": ["PL"],
    "CZ": ["CZ"],
    "SK": ["SK"],
    "HU": ["HU"],
    "SI": ["SI"],
    "HR": ["HR"],
    "RO": ["RO"],
    "CH": ["CH"],
    "ES": ["ES"],
    "PT": ["PT"],
    "GR": ["GR"],
    "BG": ["BG"],
    "RS": ["RS"],
    "GB": ["GB"],
    "IE": ["IE-SEM"],
    "FI": ["FI"],
    "EE": ["EE"],
    "LV": ["LV"],
    "LT": ["LT"],
    "IT": ["IT-NORD", "IT-CNOR", "IT-CSUD", "IT-SUD", "IT-CALA", "IT-SICI", "IT-SARD"],
    "NO": ["NO1", "NO2", "NO3", "NO4", "NO5"],
    "SE": ["SE1", "SE2", "SE3", "SE4"],
    "DK": ["DK1", "DK2"],
    "LU": ["DE-LU"],  # alias: Luxembourg shares the DE-LU bidding zone
}

COUNTRY_NAMES: dict[str, str] = {
    "FR": "France", "DE": "Germany", "BE": "Belgium", "NL": "Netherlands",
    "AT": "Austria", "PL": "Poland", "CZ": "Czechia", "SK": "Slovakia",
    "HU": "Hungary", "SI": "Slovenia", "HR": "Croatia", "RO": "Romania",
    "CH": "Switzerland", "ES": "Spain", "PT": "Portugal", "GR": "Greece",
    "BG": "Bulgaria", "RS": "Serbia", "GB": "Great Britain", "IE": "Ireland",
    "FI": "Finland", "EE": "Estonia", "LV": "Latvia", "LT": "Lithuania",
    "IT": "Italy", "NO": "Norway", "SE": "Sweden", "DK": "Denmark",
}

# canonical countries get a FlowNode; LU is an alias only
CANONICAL = [cc for cc in COUNTRY_ZONES if cc != "LU"]

# zone key -> canonical country code (DE-LU -> DE, IT-NORD -> IT, ...)
ZONE_TO_CC: dict[str, str] = {
    z: cc for cc in CANONICAL for z in COUNTRY_ZONES[cc]
}


def zone_country(zone_key: str) -> str | None:
    return ZONE_TO_CC.get(zone_key)


@lru_cache(maxsize=1)
def load_flow_nodes() -> tuple[FlowNode, ...]:
    """One node per canonical country, centroid = mean of member zone centroids."""
    by_key = {z.key: z for z in load_zones()}
    nodes = []
    for cc in CANONICAL:
        members = [by_key[z] for z in COUNTRY_ZONES[cc] if z in by_key]
        if not members:
            continue
        lon = sum(z.centroid[0] for z in members) / len(members)
        lat = sum(z.centroid[1] for z in members) / len(members)
        nodes.append(
            FlowNode(
                code=cc,
                name=COUNTRY_NAMES.get(cc, cc),
                centroid=(round(lon, 4), round(lat, 4)),
                zones=[z.key for z in members],
            )
        )
    return tuple(nodes)


@lru_cache(maxsize=1)
def _pair_regimes() -> dict[frozenset[str], str]:
    """country pair -> regime, FLOW_BASED only if every connecting zone border is."""
    acc: dict[frozenset[str], list[str]] = {}
    for b in load_interconnectors():
        ca, cb = ZONE_TO_CC.get(b.from_zone), ZONE_TO_CC.get(b.to_zone)
        if not ca or not cb or ca == cb:
            continue
        acc.setdefault(frozenset((ca, cb)), []).append(b.capacity_regime)
    return {
        pair: ("FLOW_BASED" if all(r == "FLOW_BASED" for r in regs) else "NTC")
        for pair, regs in acc.items()
    }


def country_pair_regime(cc_a: str, cc_b: str) -> str:
    return _pair_regimes().get(frozenset((cc_a, cc_b)), "NTC")


@lru_cache(maxsize=1)
def flow_query_countries() -> tuple[str, ...]:
    """Minimal-ish set of countries to query so every border is covered once.

    Energy-Charts' /cbet|/cbpf return *all* of a country's borders in one call,
    and its rate limit is tight — so instead of querying all ~28 countries we
    greedily pick a vertex cover of the country adjacency graph.
    """
    pairs = {tuple(sorted(p)) for p in _pair_regimes()}
    cover: list[str] = []
    while pairs:
        # country touching the most still-uncovered borders
        degree: dict[str, int] = {}
        for a, b in pairs:
            degree[a] = degree.get(a, 0) + 1
            degree[b] = degree.get(b, 0) + 1
        pick = max(degree, key=lambda c: (degree[c], c))
        cover.append(pick)
        pairs = {p for p in pairs if pick not in p}
    return tuple(cover)
