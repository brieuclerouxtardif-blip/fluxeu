"""M1 referential integrity: zones, borders, EIC codes, geojson."""

from entsoe.mappings import Area
from fastapi.testclient import TestClient

from app.domain.interconnectors import load_interconnectors
from app.domain.zones import load_zones, load_zones_geojson
from app.main import app

client = TestClient(app)


def test_zones_load_and_count():
    zones = load_zones()
    assert len(zones) >= 40
    assert len({z.key for z in zones}) == len(zones)


def test_eic_codes_come_from_entsoe_py():
    valid_eics = {a.value for a in Area}
    for z in load_zones():
        assert z.code in valid_eics, f"{z.key}: {z.code} not in entsoe-py Area"


def test_known_borders_present():
    pairs = {tuple(sorted((b.from_zone, b.to_zone))) for b in load_interconnectors()}
    for expected in [
        ("BE", "FR"), ("DE-LU", "FR"), ("ES", "FR"), ("FR", "GB"),
        ("EE", "FI"), ("DK1", "GB"), ("NL", "NO2"), ("LT", "SE4"),
        ("ES", "PT"), ("FR", "IT-NORD"),
    ]:
        assert expected in pairs, f"missing border {expected}"


def test_border_endpoints_exist_and_no_self_loops():
    keys = {z.key for z in load_zones()}
    for b in load_interconnectors():
        assert b.from_zone in keys and b.to_zone in keys
        assert b.from_zone != b.to_zone


def test_gb_borders_tagged_decoupled():
    for b in load_interconnectors():
        is_gb = "GB" in (b.from_zone, b.to_zone)
        assert b.gb_decoupled == is_gb


def test_flow_based_only_within_core_or_nordic():
    regions = {z.key: z.region for z in load_zones()}
    for b in load_interconnectors():
        if b.capacity_regime == "FLOW_BASED":
            ra, rb = regions[b.from_zone], regions[b.to_zone]
            assert ra == rb and ra in ("CORE", "NORDIC"), (b.from_zone, b.to_zone)


def test_geojson_keys_match_zones():
    zones = {z.key: z for z in load_zones()}
    gj_keys = {f["properties"]["key"] for f in load_zones_geojson()["features"]}
    assert gj_keys <= set(zones)
    for key, z in zones.items():
        assert (key in gj_keys) == z.has_geometry


def test_api_endpoints():
    r = client.get("/api/zones")
    assert r.status_code == 200 and len(r.json()) >= 40
    r = client.get("/api/interconnectors")
    assert r.status_code == 200
    borders = r.json()
    assert len(borders) >= 70
    assert all(c["name"] for b in borders for c in b["cables"])
    r = client.get("/api/zones.geojson")
    assert r.status_code == 200 and r.json()["type"] == "FeatureCollection"
