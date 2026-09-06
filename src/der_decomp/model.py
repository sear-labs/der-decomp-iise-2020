"""Capacity-expansion MILP for distributed energy resources.

Python/gurobipy port of the R model in `r-original/Utility Linking.Rmd`.

Choose hourly generation from natural gas, solar and wind plus integer investment in
units of each, to meet an hourly demand profile at least cost.

The model **takes its data as arguments and never reads a file**. That is deliberate:
the original's inputs are Pecan Street licensed data that cannot be redistributed, so
the model has to be runnable — and testable — on data the caller supplies. See README.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import gurobipy as gp
from gurobipy import GRB

TECHS = ("NG", "Solar", "Wind")


@dataclass(frozen=True)
class TechSpec:
    """Cost and size of one technology. Costs in the original's units."""

    fuel_cost_per_mwh: float
    variable_om_per_mwh: float
    capex_per_kw: float
    fixed_om_per_kw_yr: float
    unit_capacity_mw: float

    @property
    def unit_capacity_kw(self) -> float:
        return self.unit_capacity_mw * 1000.0


# Table from the original notebook (cost.df1). Unit sizes 25 MW / 0.5 MW / 1 MW as used
# in the R code's CF vector: NG x25000, Solar x500, Wind x1000 (kW).
DEFAULT_TECHS: dict[str, TechSpec] = {
    "NG": TechSpec(21.0, 3.0, 927.0, 11.0, 25.0),
    "Solar": TechSpec(0.0, 0.0, 1096.0, 20.0, 0.5),
    "Wind": TechSpec(0.0, 0.0, 1610.0, 44.0, 1.0),
}


@dataclass
class Costs:
    discount_rate: float = 0.05
    payback_period_years: int = 20
    transmission_distribution_per_kwh: float = 0.03
    techs: dict[str, TechSpec] = field(default_factory=lambda: dict(DEFAULT_TECHS))


def annuity_payment(rate: float, periods: int, present_value: float) -> float:
    """Level annual payment amortising `present_value`. R's FinCal::pmt, sign-flipped.

    pmt returns a negative cash flow; the original negates it, so this returns a
    positive cost.
    """
    if periods <= 0:
        raise ValueError("payback period must be positive")
    if rate == 0:
        return present_value / periods
    return present_value * rate / (1.0 - (1.0 + rate) ** -periods)


def annual_fixed_cost(spec: TechSpec, costs: Costs) -> float:
    """Annuitised CAPEX plus fixed O&M, per unit installed ($/unit/year)."""
    per_kw = (
        annuity_payment(costs.discount_rate, costs.payback_period_years, spec.capex_per_kw)
        + spec.fixed_om_per_kw_yr
    )
    return per_kw * spec.unit_capacity_kw


def variable_cost_per_kwh(name: str, spec: TechSpec, costs: Costs) -> float:
    """Fuel plus variable O&M, converted to $/kWh, plus T&D.

    NOTE: this reproduces the original's arithmetic exactly, including a quirk.
    The R code divides by the unit size rather than by 1000 for Solar and Wind:

        cost.variable.NG     <- (fuel + vom) / 1000
        cost.variable.Solar  <- (fuel + vom) / 500
        cost.variable.Wind   <- (fuel + vom) / 1000

    For Solar and Wind both numerators are zero, so the divisor never affects the
    answer and the published results are unaffected. It is preserved here so the port
    matches the original term for term; `strict_original=False` uses a consistent
    /1000 instead.
    """
    numerator = spec.fuel_cost_per_mwh + spec.variable_om_per_mwh
    divisor = {"NG": 1000.0, "Solar": 500.0, "Wind": 1000.0}[name]
    return numerator / divisor + costs.transmission_distribution_per_kwh


def build(
    demand_profile,
    capacity_factors: dict[str, list[float]],
    annual_demand_kwh: float,
    costs: Costs | None = None,
    integer_investment: bool = True,
):
    """Build the MILP.

    Parameters
    ----------
    demand_profile
        Fraction of annual demand in each hour. Must sum to ~1 over the horizon.
    capacity_factors
        Per-technology hourly availability in [0, 1]; one list per name in TECHS.
    annual_demand_kwh
        Total annual demand. The original uses 3,000,000 x 40 = 120 GWh.
    integer_investment
        Investment in whole units, as in the paper. False relaxes it, which is what
        the decomposition work compares against.
    """
    costs = costs or Costs()
    n = len(demand_profile)
    if n == 0:
        raise ValueError("demand_profile is empty")
    for name in TECHS:
        if name not in capacity_factors:
            raise ValueError(f"no capacity factor supplied for {name!r}")
        if len(capacity_factors[name]) < n:
            raise ValueError(
                f"capacity factor for {name!r} has {len(capacity_factors[name])} "
                f"entries, need at least {n}"
            )

    m = gp.Model("der_decomp")
    hours = range(n)
    gen = {t: m.addVars(hours, name=f"gen_{t}") for t in TECHS}
    vtype = GRB.INTEGER if integer_investment else GRB.CONTINUOUS
    invest = m.addVars(TECHS, vtype=vtype, name="invest")

    # C1: hourly supply must meet hourly demand.
    for h in hours:
        m.addConstr(
            gp.quicksum(gen[t][h] for t in TECHS)
            >= annual_demand_kwh * demand_profile[h],
            f"demand[{h}]",
        )

    # C2: generation in each hour bounded by installed units x availability x unit size.
    for t in TECHS:
        spec = costs.techs[t]
        for h in hours:
            m.addConstr(
                gen[t][h]
                <= capacity_factors[t][h] * spec.unit_capacity_kw * invest[t],
                f"capacity[{t},{h}]",
            )

    m.setObjective(
        gp.quicksum(
            variable_cost_per_kwh(t, costs.techs[t], costs) * gen[t][h]
            for t in TECHS
            for h in hours
        )
        + gp.quicksum(annual_fixed_cost(costs.techs[t], costs) * invest[t] for t in TECHS),
        GRB.MINIMIZE,
    )
    m._gen, m._invest, m._hours = gen, invest, n
    return m
