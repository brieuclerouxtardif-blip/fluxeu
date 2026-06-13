"""Generate data/zones.json, data/interconnectors.json and data/zones.geojson.

Source of truth for EIC codes and adjacency: entsoe-py (Area enum + NEIGHBOURS).
Geometries: electricitymaps-contrib geo/world.geojson (download separately,
pass its path as argv[1]). Starter metadata (capacity regimes, DC cables,
TSO names) comes from PLAN.md §6.

Usage:
    python scripts/build_referential.py %TEMP%/em_world.geojson
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

from entsoe.mappings import Area, NEIGHBOURS
from shapely.geometry import mapping, shape
from shapely.ops import unary_union

DATA_DIR = Path(__file__).resolve().parents[2] / "data"
SIMPLIFY_TOLERANCE = 0.02  # degrees, ~2 km
COORD_DECIMALS = 4

# our zone key -> electricitymaps zoneName(s) to union (empty = no geometry)
ZONES: dict[str, dict] = {
    "FR":      {"em": ["FR"], "country": "France", "name": "France", "tso": ["RTE"], "region": "CORE"},
    "DE-LU":   {"em": ["DE", "LU"], "country": "Germany+Luxembourg", "name": "Germany-Luxembourg", "tso": ["50Hertz", "Amprion", "TenneT DE", "TransnetBW", "Creos"], "region": "CORE"},
    "BE":      {"em": ["BE"], "country": "Belgium", "name": "Belgium", "tso": ["Elia"], "region": "CORE"},
    "NL":      {"em": ["NL"], "country": "Netherlands", "name": "Netherlands", "tso": ["TenneT NL"], "region": "CORE"},
    "AT":      {"em": ["AT"], "country": "Austria", "name": "Austria", "tso": ["APG"], "region": "CORE"},
    "PL":      {"em": ["PL"], "country": "Poland", "name": "Poland", "tso": ["PSE"], "region": "CORE"},
    "CZ":      {"em": ["CZ"], "country": "Czechia", "name": "Czechia", "tso": ["CEPS"], "region": "CORE"},
    "SK":      {"em": ["SK"], "country": "Slovakia", "name": "Slovakia", "tso": ["SEPS"], "region": "CORE"},
    "HU":      {"em": ["HU"], "country": "Hungary", "name": "Hungary", "tso": ["MAVIR"], "region": "CORE"},
    "SI":      {"em": ["SI"], "country": "Slovenia", "name": "Slovenia", "tso": ["ELES"], "region": "CORE"},
    "HR":      {"em": ["HR"], "country": "Croatia", "name": "Croatia", "tso": ["HOPS"], "region": "CORE"},
    "RO":      {"em": ["RO"], "country": "Romania", "name": "Romania", "tso": ["Transelectrica"], "region": "CORE"},
    "CH":      {"em": ["CH"], "country": "Switzerland", "name": "Switzerland", "tso": ["Swissgrid"], "region": "CH"},
    "ES":      {"em": ["ES"], "country": "Spain", "name": "Spain", "tso": ["REE"], "region": "IBERIA"},
    "PT":      {"em": ["PT"], "country": "Portugal", "name": "Portugal", "tso": ["REN"], "region": "IBERIA"},
    "IT-NORD": {"em": ["IT-NO"], "country": "Italy", "name": "Italy North", "tso": ["Terna"], "region": "ITALY"},
    "IT-CNOR": {"em": ["IT-CNO"], "country": "Italy", "name": "Italy Centre-North", "tso": ["Terna"], "region": "ITALY"},
    "IT-CSUD": {"em": ["IT-CSO"], "country": "Italy", "name": "Italy Centre-South", "tso": ["Terna"], "region": "ITALY"},
    # Calabria has its own bidding zone since 2021 but electricitymaps still
    # draws it inside IT-SO; no own polygon, manual centroid, flagged below.
    "IT-SUD":  {"em": ["IT-SO"], "country": "Italy", "name": "Italy South", "tso": ["Terna"], "region": "ITALY"},
    "IT-CALA": {"em": [], "country": "Italy", "name": "Italy Calabria", "tso": ["Terna"], "region": "ITALY", "centroid": [16.4, 39.0]},
    "IT-SICI": {"em": ["IT-SIC"], "country": "Italy", "name": "Italy Sicily", "tso": ["Terna"], "region": "ITALY"},
    "IT-SARD": {"em": ["IT-SAR"], "country": "Italy", "name": "Italy Sardinia", "tso": ["Terna"], "region": "ITALY"},
    "GR":      {"em": ["GR"], "country": "Greece", "name": "Greece", "tso": ["IPTO"], "region": "SEE"},
    "BG":      {"em": ["BG"], "country": "Bulgaria", "name": "Bulgaria", "tso": ["ESO"], "region": "SEE"},
    "RS":      {"em": ["RS"], "country": "Serbia", "name": "Serbia", "tso": ["EMS"], "region": "SEE"},
    "GB":      {"em": ["GB", "GB-ZET"], "country": "Great Britain", "name": "Great Britain", "tso": ["NESO"], "region": "GB"},
    "IE-SEM":  {"em": ["IE", "GB-NIR"], "country": "Ireland (SEM)", "name": "Ireland SEM", "tso": ["EirGrid", "SONI"], "region": "SEM"},
    "DK1":     {"em": ["DK-DK1"], "country": "Denmark", "name": "Denmark West", "tso": ["Energinet"], "region": "NORDIC"},
    "DK2":     {"em": ["DK-DK2"], "country": "Denmark", "name": "Denmark East", "tso": ["Energinet"], "region": "NORDIC"},
    "NO1":     {"em": ["NO-NO1"], "country": "Norway", "name": "Norway Southeast", "tso": ["Statnett"], "region": "NORDIC"},
    "NO2":     {"em": ["NO-NO2"], "country": "Norway", "name": "Norway Southwest", "tso": ["Statnett"], "region": "NORDIC"},
    "NO3":     {"em": ["NO-NO3"], "country": "Norway", "name": "Norway Mid", "tso": ["Statnett"], "region": "NORDIC"},
    "NO4":     {"em": ["NO-NO4"], "country": "Norway", "name": "Norway North", "tso": ["Statnett"], "region": "NORDIC"},
    "NO5":     {"em": ["NO-NO5"], "country": "Norway", "name": "Norway West", "tso": ["Statnett"], "region": "NORDIC"},
    "SE1":     {"em": ["SE-SE1"], "country": "Sweden", "name": "Sweden North", "tso": ["Svenska kraftnat"], "region": "NORDIC"},
    "SE2":     {"em": ["SE-SE2"], "country": "Sweden", "name": "Sweden Mid-North", "tso": ["Svenska kraftnat"], "region": "NORDIC"},
    "SE3":     {"em": ["SE-SE3"], "country": "Sweden", "name": "Sweden Mid-South", "tso": ["Svenska kraftnat"], "region": "NORDIC"},
    "SE4":     {"em": ["SE-SE4"], "country": "Sweden", "name": "Sweden South", "tso": ["Svenska kraftnat"], "region": "NORDIC"},
    "FI":      {"em": ["FI"], "country": "Finland", "name": "Finland", "tso": ["Fingrid"], "region": "NORDIC"},
    "EE":      {"em": ["EE"], "country": "Estonia", "name": "Estonia", "tso": ["Elering"], "region": "BALTIC"},
    "LV":      {"em": ["LV"], "country": "Latvia", "name": "Latvia", "tso": ["AST"], "region": "BALTIC"},
    "LT":      {"em": ["LT"], "country": "Lithuania", "name": "Lithuania", "tso": ["Litgrid"], "region": "BALTIC"},
}

FLOW_BASED_REGIONS = {"CORE", "NORDIC"}

# PLAN.md §6 — named DC cables (both endpoints must be in ZONES).
# MONITA (IT-ME) skipped: Montenegro is out of scope for v1.
CABLES = [
    {"name": "IFA", "border": ("FR", "GB"), "mw": 2000, "tech": "HVDC", "year": "1986"},
    {"name": "IFA2", "border": ("FR", "GB"), "mw": 1000, "tech": "HVDC", "year": "2021"},
    {"name": "ElecLink", "border": ("FR", "GB"), "mw": 1000, "tech": "HVDC", "year": "2022", "note": "Channel Tunnel"},
    {"name": "BritNed", "border": ("GB", "NL"), "mw": 1000, "tech": "HVDC", "year": "2011"},
    {"name": "Nemo Link", "border": ("BE", "GB"), "mw": 1000, "tech": "HVDC", "year": "2019"},
    {"name": "North Sea Link", "border": ("GB", "NO2"), "mw": 1400, "tech": "HVDC", "year": "2021"},
    {"name": "Viking Link", "border": ("DK1", "GB"), "mw": 1400, "tech": "HVDC", "year": "2023", "note": "ramping up"},
    {"name": "East-West (EWIC)", "border": ("GB", "IE-SEM"), "mw": 500, "tech": "HVDC", "year": "2012"},
    {"name": "Greenlink", "border": ("GB", "IE-SEM"), "mw": 500, "tech": "HVDC", "year": "2024"},
    {"name": "Moyle", "border": ("GB", "IE-SEM"), "mw": 500, "tech": "HVDC", "year": "2001", "note": "to Northern Ireland"},
    {"name": "NorNed", "border": ("NL", "NO2"), "mw": 700, "tech": "HVDC", "year": "2008"},
    {"name": "NordLink", "border": ("DE-LU", "NO2"), "mw": 1400, "tech": "HVDC", "year": "2021"},
    {"name": "Skagerrak 1-4", "border": ("DK1", "NO2"), "mw": 1700, "tech": "HVDC", "year": "1977-2014"},
    {"name": "COBRAcable", "border": ("DK1", "NL"), "mw": 700, "tech": "HVDC", "year": "2019"},
    {"name": "Kontek", "border": ("DE-LU", "DK2"), "mw": 600, "tech": "HVDC", "year": "1996"},
    {"name": "SwePol", "border": ("PL", "SE4"), "mw": 600, "tech": "HVDC", "year": "2000"},
    {"name": "NordBalt", "border": ("LT", "SE4"), "mw": 700, "tech": "HVDC", "year": "2016"},
    {"name": "EstLink 1+2", "border": ("EE", "FI"), "mw": 1000, "tech": "HVDC", "year": "2007/2014"},
    {"name": "LitPol", "border": ("LT", "PL"), "mw": 500, "tech": "HVAC/HVDC", "year": "2015"},
    {"name": "INELFE", "border": ("ES", "FR"), "mw": 2000, "tech": "HVDC", "year": "2015", "note": "plus AC lines"},
    {"name": "GRITA", "border": ("GR", "IT-SUD"), "mw": 500, "tech": "HVDC", "year": "2002"},
    {"name": "Celtic", "border": ("FR", "IE-SEM"), "mw": 700, "tech": "HVDC", "year": "~2026", "note": "under construction", "commissioned": False},
]


def member_name(key: str) -> str:
    """Our zone key -> entsoe-py Area member name (FR, DE_LU, DK_1, NO_2...)."""
    key = re.sub(r"^(DK|NO|SE)(\d)$", r"\1_\2", key)
    return key.replace("-", "_")


def round_coords(obj, nd=COORD_DECIMALS):
    if isinstance(obj, (list, tuple)):
        if obj and isinstance(obj[0], (int, float)):
            return [round(c, nd) for c in obj]
        return [round_coords(o, nd) for o in obj]
    return obj


def main() -> None:
    geo_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    generated_at = datetime.now(timezone.utc).isoformat()

    # --- geometries ------------------------------------------------------
    geoms: dict[str, object] = {}
    if geo_path and geo_path.exists():
        world = json.loads(geo_path.read_text(encoding="utf-8"))
        by_em = {}
        for feat in world["features"]:
            zn = feat["properties"].get("zoneName")
            if zn:
                by_em.setdefault(zn, []).append(shape(feat["geometry"]))
        for key, meta in ZONES.items():
            shapes = [g for em in meta["em"] for g in by_em.get(em, [])]
            missing = [em for em in meta["em"] if em not in by_em]
            if missing:
                print(f"WARN geometry missing for {key}: {missing}")
            if shapes:
                geom = unary_union(shapes).simplify(SIMPLIFY_TOLERANCE, preserve_topology=True)
                geoms[key] = geom
    else:
        print("WARN no geojson input — centroids will use starter values only")

    # --- zones.json ------------------------------------------------------
    zones = []
    for key, meta in ZONES.items():
        member = member_name(key)
        eic = Area[member].value  # KeyError = referential drift, fail loudly
        geom = geoms.get(key)
        if geom is not None:
            c = geom.centroid
            centroid = [round(c.x, 3), round(c.y, 3)]
        else:
            centroid = meta.get("centroid")
            if centroid is None:
                raise SystemExit(f"no geometry and no manual centroid for {key}")
        zones.append({
            "code": eic,
            "key": key,
            "name": meta["name"],
            "country": meta["country"],
            "centroid": centroid,  # [lon, lat]
            "tso": meta["tso"],
            "capacity_regime": "FLOW_BASED" if meta["region"] in FLOW_BASED_REGIONS else "NTC",
            "region": meta["region"],
            "has_geometry": geom is not None,
        })

    # --- borders from NEIGHBOURS ------------------------------------------
    member_to_key = {member_name(k): k for k in ZONES}
    pairs: set[tuple[str, str]] = set()
    for m, neighbours in NEIGHBOURS.items():
        if m not in member_to_key:
            continue
        for n in neighbours:
            if n in member_to_key:
                pairs.add(tuple(sorted((member_to_key[m], member_to_key[n]))))

    cable_pairs = {tuple(sorted(c["border"])) for c in CABLES}
    for cp in cable_pairs - pairs:
        print(f"WARN cable border {cp} absent from NEIGHBOURS — added manually")
        pairs.add(cp)

    borders = []
    for a, b in sorted(pairs):
        ra, rb = ZONES[a]["region"], ZONES[b]["region"]
        flow_based = ra == rb and ra in FLOW_BASED_REGIONS
        cables = [
            {k: v for k, v in c.items() if k != "border"}
            for c in CABLES
            if tuple(sorted(c["border"])) == (a, b)
        ]
        borders.append({
            "from_zone": a,
            "to_zone": b,
            "capacity_regime": "FLOW_BASED" if flow_based else "NTC",
            "gb_decoupled": "GB" in (a, b),
            "cables": cables,
        })

    # --- write -------------------------------------------------------------
    DATA_DIR.mkdir(exist_ok=True)
    (DATA_DIR / "zones.json").write_text(
        json.dumps({"generated_at": generated_at, "source": "entsoe-py Area/NEIGHBOURS + electricitymaps-contrib geometries", "zones": zones}, indent=1),
        encoding="utf-8")
    (DATA_DIR / "interconnectors.json").write_text(
        json.dumps({"generated_at": generated_at, "source": "entsoe-py NEIGHBOURS + PLAN.md §6 cables", "borders": borders}, indent=1),
        encoding="utf-8")

    if geoms:
        features = []
        for key, geom in geoms.items():
            gj = mapping(geom)
            features.append({
                "type": "Feature",
                "properties": {"key": key, "name": ZONES[key]["name"], "country": ZONES[key]["country"]},
                "geometry": {"type": gj["type"], "coordinates": round_coords(gj["coordinates"])},
            })
        (DATA_DIR / "zones.geojson").write_text(
            json.dumps({"type": "FeatureCollection", "features": features}),
            encoding="utf-8")

    print(f"OK {len(zones)} zones, {len(borders)} borders, {len(geoms)} geometries -> {DATA_DIR}")


if __name__ == "__main__":
    main()
