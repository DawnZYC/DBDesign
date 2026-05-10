"""Abstract base class for all VT model converters.

To add a new model (for example ``VT_SG_IND``):
  1. Create ``models/vt_sg_ind.py``
  2. Subclass :class:`BaseConverter`
  3. Implement :meth:`extract_power_records` (and future sector methods)
  4. Register the new class in :mod:`app.converters.engine`
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


MISSING = "-"  # Standard placeholder for missing values in EcoTEA


@dataclass
class PowerRecord:
    """One row in the EcoTEA Power sheet (one process x one year)."""

    # Traceability columns (A-G) — constant per model
    wp6_title: str = "Power"
    data_owner: str = MISSING
    data_provider: str = MISSING
    data_source: str = MISSING
    data_source_desc: str = MISSING
    data_user: str = MISSING
    usage_purpose: str = MISSING

    # Dataset descriptor columns (H-M)
    process_code: str = MISSING
    description: str = MISSING
    geography: str = MISSING
    year: int = 2018
    start_year: int = 2018
    lifetime: object = MISSING

    # EcoTEA columns (N-AK)
    grade: str = MISSING
    ef: object = MISSING
    ef_unit: str = "PJ"
    currency: str = "MSGD2016"
    capex: object = MISSING
    capex_unit: str = "GW"
    fixed_opex: object = MISSING
    fixed_opex_unit: str = "GW*yr(2018)"
    variable_opex: object = MISSING
    variable_opex_unit: str = "PJ (2018)"
    tax_cost: str = MISSING
    sub_cost: str = MISSING
    efficiency: object = MISSING
    tech_efficiency: str = MISSING
    commodity_share: object = MISSING
    commodity: object = MISSING
    commodity_demand: str = MISSING
    interpolation_rule: object = MISSING
    afa: object = MISSING
    heat_rate: object = MISSING
    capacity: object = MISSING
    capacity_type: object = MISSING
    constraint: str = MISSING
    uc_rhsrt: object = MISSING
    uc_rhsrt_note: str = MISSING


class BaseConverter(ABC):
    """Abstract base class every model adapter must inherit from."""

    def __init__(self, file_path: str) -> None:
        self.file_path = file_path
        self._sheets: dict = {}

    def _load_sheets(self) -> None:
        """Lazy-load all sheets from the source Excel file."""
        import pandas as pd

        if not self._sheets:
            self._sheets = pd.read_excel(self.file_path, sheet_name=None, header=None)

    @abstractmethod
    def extract_power_records(self) -> list[PowerRecord]:
        """Return all PowerRecord rows for the EcoTEA Power sheet."""
