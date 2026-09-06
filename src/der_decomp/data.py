"""Load a workbook instance into the arrays `model.build` expects.

Mirrors the reshaping the original R does in `r-original/Utility Linking.Rmd`:

    demand.kwh.raw[-c(1:7), -c(1:2,15:16)]     drop header rows and label columns
    [721:nrow, c(4,6,9,11)] <- NA              30-day months carry 720 hours
    [673:nrow, 2]           <- NA              February carries 672
    unlist -> drop NA -> divide by the sum     one 8760-long profile, summing to 1

The month lengths are what turn a 744 x 12 grid into 8760 hours; without the trim you
get 8,928 and every downstream index is silently wrong.
"""
from __future__ import annotations

from pathlib import Path

import openpyxl

# Hours per month, non-leap. 744 for 31-day months, 720 for 30-day, 672 for February.
COM_EFF_IMPROVE = 0.10          # industrial panels vs household, from the original R

MONTH_HOURS = (744, 672, 744, 720, 744, 720, 744, 744, 720, 744, 720, 744)
HOURS_PER_YEAR = sum(MONTH_HOURS)                       # 8760

FIRST_DATA_ROW = 11                                     # row 10 is the month header
MONTH_COLS = tuple(range(5, 17))
TECH_COL, SLICE_COL = 3, 4


def _column_major(ws, last_row, tech=None):
    """Read a timeslice x month block and flatten it month by month, trimmed to length."""
    out = []
    for i, col in enumerate(MONTH_COLS):
        taken = 0
        for r in range(FIRST_DATA_ROW, last_row + 1):
            if tech is not None and ws.cell(r, TECH_COL).value != tech:
                continue
            v = ws.cell(r, col).value
            if not isinstance(v, (int, float)):
                continue
            if taken >= MONTH_HOURS[i]:
                break
            out.append(float(v))
            taken += 1
        if taken != MONTH_HOURS[i]:
            raise ValueError(
                f"{ws.title}{'' if tech is None else f' [{tech}]'}: month {i+1} yielded "
                f"{taken} hours, expected {MONTH_HOURS[i]}"
            )
    return out


def load_instance(path: str | Path):
    """Return (demand_profile, capacity_factors) from a workbook.

    `demand_profile` is 8760 fractions summing to 1. `capacity_factors` maps each of
    NG/Solar/Wind to 8760 availabilities in [0, 1].
    """
    wb = openpyxl.load_workbook(path, data_only=True, read_only=False)
    demand = _column_major(wb["Demand_kWh"], 754)
    total = sum(demand)
    if total <= 0:
        raise ValueError("demand profile sums to zero")
    demand = [v / total for v in demand]

    cf_sheet = wb["CapacityFactor"]
    techs = {}
    present = {cf_sheet.cell(r, TECH_COL).value for r in range(FIRST_DATA_ROW, 1500)}
    for name, key in (("Solar", "H_PV"), ("Wind", "H_WND")):
        if key not in present:                          # fall back to whatever PV/WND row exists
            key = next((t for t in present if t and name[:1].upper() in str(t).upper()), None)
        if key is None:
            raise ValueError(f"no capacity-factor rows for {name}; present: {sorted(str(p) for p in present if p)}")
        techs[name] = _column_major(cf_sheet, 1499, tech=key)

    # Commercial-efficiency adjustment, from the original R:
    #
    #     com.eff.improve <- 0.10
    #     capacity.factor.solar <- capacity.factor.solar + com.eff.improve
    #     ... revert it where the original value was <= 0.009 (night) or the result >= 1
    #
    # The series in the workbook is HOUSEHOLD PV; the utility model builds industrial
    # panels, which are more efficient. Night hours must not be lifted off zero, and
    # nothing may exceed 1. This is what takes the mean from ~0.21 to the ~0.266 the
    # paper reports, so leaving it out silently understates solar all year.
    techs["Solar"] = [
        v if (v <= 0.009 or v + COM_EFF_IMPROVE >= 1.0) else v + COM_EFF_IMPROVE
        for v in techs["Solar"]
    ]

    # Natural gas is dispatchable: the paper fixes its capacity factor at 0.87 rather
    # than reading a series, so there is nothing in the workbook to load for it.
    techs["NG"] = [0.87] * HOURS_PER_YEAR

    for name, series in techs.items():
        bad = [v for v in series if not 0.0 <= v <= 1.0]
        if bad:
            raise ValueError(f"{name}: {len(bad)} capacity factors outside [0,1], e.g. {bad[:3]}")
    return demand, techs
