"""Reproduction of the published figures. **RED by design.**

The paper's instance uses Pecan Street licensed demand and capacity-factor data, which
is not in this repository and cannot be put there. Nothing here can regenerate the
published numbers until that licence question is answered.

Part 6 of the standard: a requirement kept as prose has already failed, because prose
is read after the thing it was meant to prevent. So the requirement is a test that
fails, and it names exactly what would make it pass.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

ROOT = Path(__file__).resolve().parents[1]

# The original's instance, from r-original/Utility Linking.Rmd:
#   demand.annual <- 3000000 * 40      # 40 communities, 120 GWh/yr
#   nTimePeriods  <- 8760
ANNUAL_DEMAND_KWH = 3_000_000 * 40
HOURS = 8760


def load_paper_inputs():
    """Return (demand_profile, capacity_factors) for the published instance.

    Not available: both come from `indata1.xlsx`, sheets `Demand_kWh` and
    `CapacityFactor`, which carry Pecan Street licensed data.
    """
    candidates = sorted(ROOT.glob("data/**/indata1.xlsx"))
    if not candidates:
        pytest.fail(
            "RED BY DESIGN: the paper's instance needs Pecan Street data "
            "(indata1.xlsx, sheets Demand_kWh and CapacityFactor), which is not "
            "distributable and is gitignored. See README 'Private, and why'. This "
            "test goes green only if that data becomes redistributable, or is "
            "replaced by an open substitute with the paper's numbers re-derived."
        )
    raise NotImplementedError("loader not written: no input file has ever been present")


def test_published_instance_reproduces():
    demand_profile, capacity_factors = load_paper_inputs()
    assert len(demand_profile) == HOURS
    for tech in ("NG", "Solar", "Wind"):
        assert len(capacity_factors[tech]) >= HOURS
