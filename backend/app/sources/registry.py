"""Active data source selection.

Energy-Charts is the zero-config default. ENTSO-E (token) is wired in M6;
until then we fall back to Energy-Charts even if a token is present.
"""

from __future__ import annotations

import logging

from ..config import settings
from .base import DataSource
from .energy_charts import EnergyChartsSource

log = logging.getLogger("fluxeu.sources")


def get_source() -> DataSource:
    if settings.active_source == "entsoe":
        log.warning("ENTSO-E source not implemented yet (M6) — using Energy-Charts")
    return EnergyChartsSource()
