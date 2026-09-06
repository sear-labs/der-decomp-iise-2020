"""Structural verification of the DER capacity-expansion port.

The original's inputs are Pecan Street licensed data that cannot be redistributed, so
these tests supply their own. They do not reproduce the paper's numbers — that is
`test_reproduces_paper.py`, which is red. What they do verify is that the model means
what it says: the cost arithmetic, the energy balance, the capacity linking, and the
integrality relationship. Each case is small enough to check by hand.
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from der_decomp.model import (  # noqa: E402
    TECHS,
    Costs,
    TechSpec,
    annual_fixed_cost,
    annuity_payment,
    build,
    variable_cost_per_kwh,
)


def flat(value, n):
    return [value] * n


def solve(m):
    m.Params.OutputFlag = 0
    m.Params.MIPGap = 0.0
    m.optimize()
    assert m.Status == 2, f"expected OPTIMAL, got {m.Status}"
    return m


# --------------------------------------------------------------------------- costs


def test_annuity_matches_hand_calculation():
    """$1000 at 5% over 20 years -> 1000 * 0.05 / (1 - 1.05^-20)."""
    expected = 1000 * 0.05 / (1 - 1.05**-20)
    assert annuity_payment(0.05, 20, 1000.0) == pytest.approx(expected)
    assert annuity_payment(0.05, 20, 1000.0) == pytest.approx(80.2426, abs=1e-4)


def test_zero_rate_annuity_is_straight_line():
    assert annuity_payment(0.0, 10, 1000.0) == pytest.approx(100.0)


def test_annuity_rejects_nonpositive_period():
    with pytest.raises(ValueError):
        annuity_payment(0.05, 0, 1000.0)


def test_annual_fixed_cost_includes_fixed_om():
    spec = TechSpec(0, 0, capex_per_kw=1000.0, fixed_om_per_kw_yr=10.0, unit_capacity_mw=1.0)
    per_kw = annuity_payment(0.05, 20, 1000.0) + 10.0
    assert annual_fixed_cost(spec, Costs()) == pytest.approx(per_kw * 1000.0)


def test_zero_fuel_technologies_have_only_td_variable_cost():
    """Solar and Wind have no fuel or variable O&M, so only T&D remains.

    This is also what makes the original's inconsistent /500 divisor harmless.
    """
    c = Costs()
    for name in ("Solar", "Wind"):
        assert variable_cost_per_kwh(name, c.techs[name], c) == pytest.approx(
            c.transmission_distribution_per_kwh
        )


# --------------------------------------------------------------------- model shape


def test_model_dimensions_match_the_formulation():
    n = 24
    m = build(flat(1 / n, n), {t: flat(1.0, n) for t in TECHS}, 1000.0)
    m.update()
    assert m.NumVars == n * len(TECHS) + len(TECHS)
    assert m.NumConstrs == n + n * len(TECHS)


def test_missing_capacity_factor_is_rejected():
    with pytest.raises(ValueError, match="Wind"):
        build([1.0], {"NG": [1.0], "Solar": [1.0]}, 100.0)


def test_short_capacity_factor_series_is_rejected():
    with pytest.raises(ValueError, match="need at least"):
        build(flat(0.5, 4), {t: flat(1.0, 2) for t in TECHS}, 100.0)


def test_empty_demand_profile_is_rejected():
    with pytest.raises(ValueError):
        build([], {t: [] for t in TECHS}, 100.0)


# ------------------------------------------------------------------ domain content


def test_single_hour_single_technology_has_a_hand_computable_cost():
    """Only NG available. One unit is 25 MW = 25,000 kW; demand 1,000 kWh fits in one.

    Cost = 1 unit of fixed cost + 1000 kWh at NG's variable rate.
    """
    c = Costs()
    cf = {"NG": [1.0], "Solar": [0.0], "Wind": [0.0]}
    m = solve(build([1.0], cf, 1000.0, costs=c))
    expected = annual_fixed_cost(c.techs["NG"], c) + 1000.0 * variable_cost_per_kwh(
        "NG", c.techs["NG"], c
    )
    assert m.ObjVal == pytest.approx(expected, rel=1e-9)
    assert m._invest["NG"].X == pytest.approx(1.0)


def test_demand_is_always_met():
    n = 12
    profile = [1 / n] * n
    m = solve(build(profile, {t: flat(1.0, n) for t in TECHS}, 6000.0))
    for h in range(n):
        supplied = sum(m._gen[t][h].X for t in TECHS)
        assert supplied >= 6000.0 * profile[h] - 1e-6, f"hour {h} short"


def test_generation_never_exceeds_installed_capacity():
    n = 8
    c = Costs()
    cf = {"NG": flat(0.5, n), "Solar": flat(0.3, n), "Wind": flat(0.7, n)}
    m = solve(build(flat(1 / n, n), cf, 40000.0, costs=c))
    for t in TECHS:
        limit = c.techs[t].unit_capacity_kw * m._invest[t].X
        for h in range(n):
            assert m._gen[t][h].X <= cf[t][h] * limit + 1e-6, f"{t} over capacity at {h}"


def test_investment_is_integral_when_asked():
    n = 6
    m = solve(build(flat(1 / n, n), {t: flat(1.0, n) for t in TECHS}, 90000.0))
    for t in TECHS:
        x = m._invest[t].X
        assert abs(x - round(x)) < 1e-6, f"{t} investment {x} is not integral"


def test_relaxation_is_a_lower_bound_on_the_integer_solution():
    """Relaxing integrality cannot make the problem more expensive."""
    n = 6
    profile, cf = flat(1 / n, n), {t: flat(1.0, n) for t in TECHS}
    integer = solve(build(profile, cf, 90000.0, integer_investment=True))
    relaxed = solve(build(profile, cf, 90000.0, integer_investment=False))
    assert relaxed.ObjVal <= integer.ObjVal + 1e-6


def test_zero_capacity_factors_make_the_problem_infeasible():
    """No availability anywhere and non-zero demand: there must be no answer."""
    INFEASIBLE, INF_OR_UNBD = 3, 4
    m = build([1.0], {t: [0.0] for t in TECHS}, 1000.0)
    m.Params.OutputFlag = 0
    m.optimize()
    assert m.Status in (INFEASIBLE, INF_OR_UNBD), f"expected infeasible, got {m.Status}"


def test_cheaper_capital_shifts_the_build():
    """A large solar capex cut must not reduce solar investment."""
    n = 24
    profile, cf = flat(1 / n, n), {t: flat(1.0, n) for t in TECHS}
    base = solve(build(profile, cf, 240000.0))
    cheap = Costs()
    cheap.techs["Solar"] = TechSpec(0.0, 0.0, 10.0, 0.5, 0.5)
    shifted = solve(build(profile, cf, 240000.0, costs=cheap))
    assert shifted._invest["Solar"].X >= base._invest["Solar"].X
    assert shifted.ObjVal <= base.ObjVal + 1e-6
