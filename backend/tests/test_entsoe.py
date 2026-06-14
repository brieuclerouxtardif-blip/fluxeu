"""M6 ENTSO-E source — offline parts only (no token, no network).

Covers the bits that must be right *before* a token ever arrives: the zone graph
derived from entsoe-py's own Area/NEIGHBOURS mappings (the anti-hardcoding rule),
the pure transforms (UTC normalisation, signed netting, frame assembly), and the
registry fallback. The live query path is integration-gated on a real token."""

from datetime import timezone

import pandas as pd
import pytest

from app.sources import entsoe as E


def test_zone_area_map_covers_all_zones_via_entsoe_py():
    from app.domain.zones import load_zones

    zam = E.zone_area_map()
    keys = {z.key for z in load_zones()}
    assert set(zam) == keys, "every modelled zone must map to an entsoe Area"
    # hyphen/underscore + trailing-digit bridging
    assert zam["FR"] == "FR"
    assert zam["DE-LU"] == "DE_LU"
    assert zam["NO2"] == "NO_2"
    assert zam["IT-NORD"] == "IT_NORD"


def test_eic_codes_come_from_entsoe_py_not_memory():
    """EIC is read back from Area[...].code — grounded, not hardcoded."""
    from entsoe.mappings import Area

    zam = E.zone_area_map()
    assert Area[zam["FR"]].code == "10YFR-RTE------C"
    assert Area[zam["DE-LU"]].code == "10Y1001A1001A82H"


def test_modelled_borders_are_zone_level_and_real():
    borders = E.modelled_borders()
    assert all(a < b for a, b in borders), "pairs sorted/canonical"
    assert len(borders) == len(set(borders)), "deduped"
    fr = {tuple(sorted(("FR", z))) for z in ("BE", "CH", "DE-LU", "ES", "GB", "IT-NORD")}
    assert fr <= set(borders), "France's real neighbours present"
    # virtual/aggregate Areas (DE_AT_LU, IT_NORD_FR) must not leak in as zones
    flat = {z for pair in borders for z in pair}
    assert "DE_AT_LU" not in flat and "IT_NORD_FR" not in flat


def test_series_points_normalises_to_utc_and_drops_nan():
    idx = pd.to_datetime(["2026-06-14T00:00", "2026-06-14T01:00", "2026-06-14T02:00"])
    idx = idx.tz_localize("Europe/Brussels")  # entsoe-py returns local tz
    s = pd.Series([50.0, float("nan"), 60.0], index=idx)
    pts = E.series_points(s)
    assert len(pts) == 2  # NaN dropped
    # 00:00 Brussels (CEST, +2) == 22:00 UTC the day before
    assert pts[0][0] == int(pd.Timestamp("2026-06-13T22:00", tz="UTC").timestamp())
    assert pts[0][1] == 50.0
    assert E.series_points(None) == []
    assert E.series_points(pd.Series([], dtype=float)) == []


def test_net_signed_subtracts_reverse_direction():
    # 800 MW a->b and 300 MW b->a net to +500 a->b at the same instant
    assert E._net_signed([(100, 800.0)], [(100, 300.0)]) == [(100, 500.0)]
    # disjoint timestamps are kept separately
    assert E._net_signed([(1, 10.0)], [(2, 4.0)]) == [(1, 10.0), (2, -4.0)]


def test_build_history_sign_ntc_regime_and_net_positions():
    frames = E.build_history(
        price_series={"FR": [(100, 50.0)], "BE": [(100, 40.0)]},
        comm_series={("BE", "FR"): [(100, 500.0)]},   # + = BE -> FR
        phys_series={("BE", "FR"): [(100, 450.0)]},
        ntc_series={("BE", "FR"): [(100, 2000.0)]},
        start_ts=50,
        now_ts=200,
    )
    assert len(frames) == 1
    f = frames[0]
    assert f.ts.tzinfo == timezone.utc
    assert f.prices == {"FR": 50.0, "BE": 40.0}
    e = f.edges[0]
    assert (e.from_zone, e.to_zone) == ("BE", "FR")
    assert e.commercial_mw == 500.0 and e.physical_mw == 450.0 and e.ntc_mw == 2000.0
    assert e.capacity_regime == "NTC"  # NTC present -> regime NTC (else FLOW_BASED)
    # net position (+ = net import): FR imports 500, BE exports 500
    assert f.net_positions == {"FR": 500.0, "BE": -500.0}


def test_build_history_regime_flow_based_without_ntc():
    frames = E.build_history(
        {"FR": [(100, 50.0)]},
        {("BE", "FR"): [(100, 100.0)]},
        {},
        {},  # no NTC
        50, 200,
    )
    assert frames[0].edges[0].capacity_regime == "FLOW_BASED"
    assert frames[0].edges[0].ntc_mw is None


def test_registry_falls_back_without_token(monkeypatch):
    from app.config import settings
    from app.sources import registry
    from app.sources.energy_charts import EnergyChartsSource

    monkeypatch.setattr(settings, "data_source", "entsoe")
    monkeypatch.setattr(settings, "entsoe_api", None)
    assert isinstance(registry.get_source(), EnergyChartsSource)
