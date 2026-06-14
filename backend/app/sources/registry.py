"""Active data source selection.

Energy-Charts is the zero-config default. ENTSO-E (M6) takes over when a token is
present (config.active_source == "entsoe"); if the token is missing or entsoe-py
fails to initialise we fall back to Energy-Charts so the app always boots.
"""

from __future__ import annotations

import logging

from ..config import settings
from .base import DataSource
from .energy_charts import EnergyChartsSource

log = logging.getLogger("fluxeu.sources")


def get_source() -> DataSource:
    if settings.active_source == "entsoe":
        token = settings.entsoe_api
        if not token:
            log.warning("active_source=entsoe but no token set — using Energy-Charts")
        else:
            try:
                from .entsoe import EntsoeSource

                return EntsoeSource(token)
            except Exception:  # noqa: BLE001 — never let source init break startup
                log.exception("ENTSO-E source init failed — falling back to Energy-Charts")
    return EnergyChartsSource()
