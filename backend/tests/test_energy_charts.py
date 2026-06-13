"""M2 Energy-Charts normalisation: sign convention, GW->MW, country mapping.

Offline — the live API is mocked so CI never hits the network. A live smoke
test is gated behind FLUXEU_LIVE_TEST=1.
"""

import os
from datetime import datetime, timezone

import pytest

from app.domain.countries import (
    CANONICAL,
    COUNTRY_ZONES,
    country_pair_regime,
    load_flow_nodes,
)
from app.domain.zones import load_zones
from app.models import LiveSnapshot
from app.sources.base import live_from_history
from app.sources.energy_charts import ZONE_BZN, EnergyChartsSource, _latest


def test_latest_picks_most_recent_at_or_before_now():
    now = 1_000_000
    secs = [now - 7200, now - 3600, now + 3600]
    vals = [10.0, 20.0, 99.0]  # +3600 is in the future, must be ignored
    ts, v = _latest(secs, vals, now)
    assert v == 20.0
    assert ts == datetime.fromtimestamp(now - 3600, tz=timezone.utc)


def test_latest_falls_back_to_future_when_no_past_point():
    now = 1_000_000
    ts, v = _latest([now + 60, now + 120], [5.0, 6.0], now)
    assert v == 6.0


def test_latest_skips_nulls_and_handles_empty():
    now = 1_000_000
    assert _latest([now - 60, now], [None, 7.0], now)[1] == 7.0
    assert _latest([], [], now) is None
    assert _latest([now], [None], now) is None


def test_zone_bzn_keys_are_real_zones():
    keys = {z.key for z in load_zones()}
    for k in ZONE_BZN:
        assert k in keys, f"ZONE_BZN key {k} is not a known zone"


def test_country_zones_reference_real_zones():
    keys = {z.key for z in load_zones()}
    for cc, zs in COUNTRY_ZONES.items():
        for z in zs:
            assert z in keys, f"{cc} references unknown zone {z}"


def test_flow_nodes_have_centroids_within_europe():
    nodes = load_flow_nodes()
    codes = {n.code for n in nodes}
    assert {"FR", "DE", "IT", "NO", "SE", "DK", "GB"} <= codes
    for n in nodes:
        lon, lat = n.centroid
        assert -25 <= lon <= 45 and 33 <= lat <= 72, f"{n.code} centroid off-map"


def test_country_pair_regime_matches_domain():
    # FR-BE both Core -> flow-based; FR-CH and FR-GB are NTC
    assert country_pair_regime("FR", "BE") == "FLOW_BASED"
    assert country_pair_regime("FR", "CH") == "NTC"
    assert country_pair_regime("FR", "GB") == "NTC"


def _fake_get_factory():
    """Patched _get: France only, others empty. Encodes a known sign scenario."""
    now = int(datetime.now(timezone.utc).timestamp())
    secs = [now - 3600, now - 1800]

    async def fake_get(self, client, sem, path, params):
        if path == "/price" and params.get("bzn") == "FR":
            return {"unix_seconds": secs, "price": [50.0, 55.0], "unit": "EUR / MWh"}
        if path == "/cbet" and params.get("country") == "fr":
            return {
                "unix_seconds": secs,
                "countries": [
                    {"name": "Belgium", "data": [-2.0, -2.0]},      # FR exports 2 GW -> BE
                    {"name": "Germany", "data": [1.0, 1.0]},        # FR imports 1 GW from DE
                    {"name": "Switzerland", "data": [3.0, 3.0]},    # FR imports 3 GW from CH (NTC)
                    {"name": "sum", "data": [2.0, 2.0]},            # net import +2 GW
                ],
            }
        if path == "/cbpf" and params.get("country") == "fr":
            return {
                "unix_seconds": secs,
                "countries": [{"name": "Belgium", "data": [-1.5, -1.5]}],  # physical 1.5 GW FR->BE
            }
        return None

    return fake_get


@pytest.mark.asyncio
async def test_snapshot_sign_convention_and_scaling(monkeypatch):
    monkeypatch.setattr(EnergyChartsSource, "_get", _fake_get_factory())
    snap = await EnergyChartsSource().fetch_snapshot()

    assert isinstance(snap, LiveSnapshot)
    assert snap.source == "energy_charts"
    assert snap.granularity == {"prices": "bidding_zone", "flows": "country"}
    assert snap.prices["FR"] == 55.0

    edges = {(e.from_zone, e.to_zone): e for e in snap.edges}

    # commercial: + means from_zone -> to_zone. FR exports to BE.
    be_fr = edges[("BE", "FR")]
    assert be_fr.commercial_mw == -2000.0   # BE->FR negative => FR->BE +2000 MW
    assert be_fr.physical_mw == -1500.0     # physical FR->BE 1500 MW
    assert be_fr.capacity_regime == "FLOW_BASED"
    assert be_fr.ntc_mw is None

    de_fr = edges[("DE", "FR")]
    assert de_fr.commercial_mw == 1000.0    # DE->FR +1000 (FR imports 1 GW)
    assert de_fr.physical_mw is None        # no physical entry

    ch_fr = edges[("CH", "FR")]
    assert ch_fr.commercial_mw == 3000.0    # CH->FR +3000 (FR imports 3 GW)
    assert ch_fr.capacity_regime == "NTC"   # FR-CH is NTC, never fabricate utilisation
    assert ch_fr.ntc_mw is None

    # net position: + = net import. France sum = +2 GW -> +2000 MW
    assert snap.net_positions["FR"] == 2000.0


@pytest.mark.asyncio
async def test_history_builds_stepped_frames(monkeypatch):
    """One sweep -> a frame per timestamp; prices step (not interpolated);
    the live snapshot is the latest frame."""
    monkeypatch.setattr(EnergyChartsSource, "_get", _fake_get_factory())
    hist = await EnergyChartsSource().fetch_history()

    assert hist.source == "energy_charts"
    assert hist.granularity == {"prices": "bidding_zone", "flows": "country"}
    assert len(hist.frames) == 2  # two timestamps in the mock
    assert hist.frames[0].ts < hist.frames[1].ts

    # prices step: each frame keeps its own cleared price, no interpolation
    assert hist.frames[0].prices["FR"] == 50.0
    assert hist.frames[1].prices["FR"] == 55.0

    # sign convention preserved per frame (+ = from_zone -> to_zone)
    e0 = {(e.from_zone, e.to_zone): e for e in hist.frames[0].edges}
    assert e0[("BE", "FR")].commercial_mw == -2000.0  # FR exports 2 GW -> BE
    assert e0[("BE", "FR")].physical_mw == -1500.0
    assert e0[("DE", "FR")].commercial_mw == 1000.0   # FR imports 1 GW from DE
    assert hist.frames[0].net_positions["FR"] == 2000.0

    # live snapshot derived from the history == its latest frame
    live = live_from_history(hist)
    assert live is not None
    assert live.data_ts == hist.frames[-1].ts
    assert live.prices["FR"] == 55.0


@pytest.mark.skipif(
    os.environ.get("FLUXEU_LIVE_TEST") != "1",
    reason="set FLUXEU_LIVE_TEST=1 to hit the real Energy-Charts API",
)
@pytest.mark.asyncio
async def test_live_snapshot_real_api():
    snap = await EnergyChartsSource().fetch_snapshot()
    assert len(snap.prices) >= 20
    assert len(snap.edges) >= 15
    assert snap.data_ts is not None
