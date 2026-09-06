"""Reproduction against the paper. **Partly green, partly RED by design.**

Green: the shipped synthetic instance loads and solves to a pinned value, so the
data path and the model are covered end to end without any restricted file.

Red: the paper's published figures are NOT reproduced, and the reason is structural
rather than missing data. `src/der_decomp/model.py` implements the **utility** model
only. The paper's whole point is a *decomposition* — a utility model and a community
model solved alternately, exchanging demand and price until they agree — and DER
investment happens on the community side, which faces retail prices, not the
utility's wholesale cost.

That is not a guess. At the paper's own cost parameters:

    NG      $0.0652 / kWh
    Solar   $0.0763 / kWh
    Wind    $0.0840 / kWh

so a utility minimising cost builds natural gas and nothing else — which is exactly
what this model does. The paper reports DER shares from 1.8% up to 86.7%, reached
through community investment at retail prices of $0.057-$0.153/kWh.

Completing this means porting the community model and the iteration from
`r-original/Utility Linking.Rmd`, which contains all of it (14 solver calls, loops
for 1/10/20/30/40 communities).
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from der_decomp.data import HOURS_PER_YEAR, load_instance   # noqa: E402
from der_decomp.model import TECHS, build                   # noqa: E402

SYNTHETIC = ROOT / "data" / "raw" / "indata-synthetic.xlsx"
ANNUAL_DEMAND_KWH = 3_000_000 * 40            # 40 communities, per the paper

# Solving the shipped synthetic instance. Pinned so a change in the generator, the
# loader or the model shows up here rather than silently.
SYNTHETIC_OBJECTIVE = 10_749_243.92
SYNTHETIC_INVESTMENT = {"NG": 2, "Solar": 0, "Wind": 0}

# From the paper's own result figures (cost.pdf, price.pdf), by number of communities
# investing in DERs: 0, 1, 10, 20, 30, 40.
PAPER_TOTAL_COST_MILLIONS = [9.7, 9.91, 10.202, 10.894, 9.662, 10.688]
PAPER_MEAN_PRICE_PER_KWH = [0.057, 0.057, 0.058, 0.061, 0.058, 0.069]
PAPER_DER_SHARE_PCT = [1.8, 9.2, 18.5, 37.0, 55.4, 86.7]


@pytest.fixture(scope="module")
def solved():
    if not SYNTHETIC.exists():
        pytest.fail(f"{SYNTHETIC} is missing; run scripts/make_synthetic_inputs.py")
    demand, cf = load_instance(SYNTHETIC)
    m = build(demand, cf, ANNUAL_DEMAND_KWH)
    m.Params.OutputFlag = 0
    m.Params.MIPGap = 0.0
    m.optimize()
    assert m.Status == 2, f"expected OPTIMAL, got status {m.Status}"
    return m


def test_synthetic_instance_has_the_right_shape():
    demand, cf = load_instance(SYNTHETIC)
    assert len(demand) == HOURS_PER_YEAR
    assert sum(demand) == pytest.approx(1.0, abs=1e-9), "demand must be a profile summing to 1"
    for t in TECHS:
        assert len(cf[t]) == HOURS_PER_YEAR
        assert all(0.0 <= v <= 1.0 for v in cf[t]), f"{t}: capacity factor outside [0,1]"


def test_synthetic_solar_keeps_its_day_night_structure():
    """A solar profile that never goes dark is wrong, whatever its mean.

    The mean alone does not catch this: a single lognormal matched the mean and put
    1% of hours below the night threshold where the real series has ~45%.
    """
    _, cf = load_instance(SYNTHETIC)
    dark = sum(1 for v in cf["Solar"] if v <= 0.11)     # 0.009 + the 0.10 adjustment
    assert 0.35 <= dark / HOURS_PER_YEAR <= 0.55, f"only {100*dark/HOURS_PER_YEAR:.1f}% of hours are dark"


def test_synthetic_solves_to_the_pinned_value(solved):
    assert solved.ObjVal == pytest.approx(SYNTHETIC_OBJECTIVE, rel=1e-6)
    got = {t: round(solved._invest[t].X) for t in TECHS}
    assert got == SYNTHETIC_INVESTMENT


def test_utility_alone_builds_no_renewables(solved):
    """Documents WHY the paper is not reproduced, as an assertion rather than prose.

    If a future change makes the utility model build renewables unprompted, this fails
    and the explanation in the module docstring needs revisiting.
    """
    assert solved._invest["Solar"].X == 0 and solved._invest["Wind"].X == 0


@pytest.mark.xfail(reason="community model and decomposition iteration not ported yet", strict=True)
def test_reproduces_the_papers_der_shares():
    """The paper's headline result: DER share rising to 86.7% as communities invest.

    Cannot be produced by a utility-only model at any parameterisation, because DER is
    uneconomic at wholesale cost. Marked strict-xfail so it announces itself the moment
    the community model lands and this starts passing.
    """
    _, cf = load_instance(SYNTHETIC)
    demand, _ = load_instance(SYNTHETIC)
    m = build(demand, cf, ANNUAL_DEMAND_KWH)
    m.Params.OutputFlag = 0
    m.optimize()
    total = sum(m._gen[t][h].X for t in TECHS for h in range(HOURS_PER_YEAR))
    der = sum(m._gen[t][h].X for t in ("Solar", "Wind") for h in range(HOURS_PER_YEAR))
    assert 100 * der / total == pytest.approx(PAPER_DER_SHARE_PCT[-1], rel=0.05)
