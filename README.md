# der-decomp

Capacity-expansion model for distributed energy resources, behind Jones (2020), "Decomposing systems:
illustrating the utility of distributed energy resources with decomposition techniques",
*Proceedings of the 2020 IISE Annual Conference*.

A utility chooses hourly generation from natural gas, solar and wind, plus integer investment in units
of each, to meet an hourly demand profile at least cost — 3 technologies × 8,760 hours, so roughly
35,040 rows × 26,283 columns.

**This paper has no DOI.** IISE Annual Conference proceedings from 2020 were not DOI-registered. That
is a venue policy, not a comment on the work; the repository is named for the venue and year instead.

## A synthetic instance ships, and the model runs without any restricted file

```bash
pip install gurobipy openpyxl pytest
pytest                  # 20 pass, 1 strict xfail (see below)
```

`data/raw/indata-synthetic.xlsx` is sampled from fitted aggregate parameters, not perturbed from the
originals, so it reproduces no Pecan Street series. `scripts/make_synthetic_inputs.py` regenerates it
deterministically; `data/raw/fitted_parameters.json` holds the fit.

**It gives the same answer as the real data** - objective 10,749,243.92 and the same investment
decision, to the cent. That is a real result but a weak test on its own, because the optimum here is
insensitive to most of the series (see below).

Two properties of the real data are preserved deliberately, and both matter:

| Property | Real | Synthetic |
|---|---|---|
| Solar mean capacity factor (after the model's adjustment) | 0.26656 | 0.26277 |
| Wind mean capacity factor | 0.36677 | 0.36768 |
| Fraction of solar hours below the night threshold | 44.8% | 43.9% |

The paper states 0.266 and 0.366, so the **loader is verified against the published table**, not just
against the R source. The night fraction is the one that needed work: a single lognormal matched the
mean and put 1% of hours in darkness instead of 45%. Solar is bimodal, so the generator uses a
two-component mixture.

## What this port does NOT do, and why

`src/der_decomp/model.py` implements the **utility** model only. The paper is a *decomposition* - a
utility model and a community model solved alternately, exchanging demand and price until they agree
- and DER investment happens on the community side.

That is structural, not a tuning problem. At the paper's own cost parameters:

| | all-in cost |
|---|---|
| NG | **$0.0652 / kWh** |
| Solar | $0.0763 / kWh |
| Wind | $0.0840 / kWh |

A utility minimising cost builds natural gas and nothing else, which is exactly what this model does.
The paper reports DER shares from 1.8% to 86.7%, reached through community investment at *retail*
prices of $0.057-$0.153/kWh. `tests/test_reproduces_paper.py` carries that as a strict xfail rather
than a comment, so it announces itself the moment the community model lands.

`r-original/Utility Linking.Rmd` contains the whole thing - both models, and the iterations for
1/10/20/30/40 communities, across 14 solver calls. Porting it is the remaining work.

## On the underlying data

The paper states its sources in print: *"the hourly electricity demand profile from a subset of 30
houses in the Mueller neighborhood in Austin, TX via Pecan Street Inc., Dataport"*, plus ERCOT, EIA
and NREL. Per the author, that data was already de-identified and was available to academics on
request at the time; the paywall came later.

The original workbook is **not distributed here** - `.gitignore` admits only the synthetic instance
and blocks every other spreadsheet. It lives outside version control at
`University of Texas at Austin\Research\Restricted Data (Pecan Street)\`.

## What is here

```
src/der_decomp/model.py   Python/gurobipy port. Takes data as arguments; reads no file.
tests/test_model.py       16 structural tests. Green.
tests/test_reproduces_paper.py   Reproduction against the published figures. RED.
r-original/               the original R implementation, unmodified
figures/                  published figures (cost, price, table, time-of-day)
```

## The port, and what "verified" means for it

`src/der_decomp/model.py` is a port of `r-original/Utility Linking.Rmd`, which built the constraint
matrix by hand with `spMatrix` and called Gurobi's R interface.

**It takes its data as arguments and never reads a file.** That is the design consequence of the
licence problem: a model that reads `indata1.xlsx` cannot be tested by anyone who does not have
`indata1.xlsx`. A model that accepts a demand profile and capacity factors can be tested by anyone.

So the 16 tests in `tests/test_model.py` verify what can be verified without the restricted data, and
each case is small enough to check by hand:

- the annuity arithmetic against a closed-form value, and its degenerate cases
- model dimensions against the formulation
- a single-hour, single-technology instance whose optimal cost is computed by hand
- demand met in every hour; generation never above installed capacity
- investment integral when asked, and the relaxation a lower bound on the integer solution
- infeasibility when nothing is available
- cheaper solar capex never reduces solar investment

**None of that reproduces the paper.** `tests/test_reproduces_paper.py` is the test that would, and it
is red, because the data it needs cannot be distributed.

### One faithfulness note

The original computes variable cost as `(fuel + vom) / 1000` for gas and wind but `/ 500` for solar —
the unit size rather than a unit conversion. Both solar numerators are zero, so the divisor never
affects the answer and **the published results are unaffected**. The port reproduces the arithmetic
term for term, with the quirk documented at the call site rather than silently corrected.

## Running it

```bash
pip install gurobipy pytest
pytest tests/test_model.py        # green
pytest                            # includes the red reproduction test
```

At ~35,040 × 26,283 the full instance **exceeds Gurobi's size-limited licence** and needs a full one.
The test instances are tiny and run under any licence.

## How to cite

> Jones, Erick C., Jr. "Decomposing systems: illustrating the utility of distributed energy resources
> with decomposition techniques." *Proceedings of the 2020 IISE Annual Conference*, New Orleans, LA.

BibTeX: `author = {Jones, Jr., Erick C.}` — the suffix is the middle field.

## Licence

MIT for this repository's contents — see `LICENSE`. It does not extend to the Pecan Street data, which
is not here.
