# der-decomp

Capacity-expansion model for distributed energy resources, behind Jones (2020), "Decomposing systems:
illustrating the utility of distributed energy resources with decomposition techniques",
*Proceedings of the 2020 IISE Annual Conference*.

A utility chooses hourly generation from natural gas, solar and wind, plus integer investment in units
of each, to meet an hourly demand profile at least cost — 3 technologies × 8,760 hours, so roughly
35,040 rows × 26,283 columns.

**This paper has no DOI.** IISE Annual Conference proceedings from 2020 were not DOI-registered. That
is a venue policy, not a comment on the work; the repository is named for the venue and year instead.

## Private, and why

The original reads **Pecan Street** licensed data — demand profiles for 30 single-family homes in the
Mueller neighbourhood of Austin, plus derived capacity factors. The R source says so itself:

> `#These files included that are commented out are not included due to licensing requirements from Pecan Street`

**That exclusion was incomplete.** The commented-out loads were removed, but `indata1.xlsx` — which is
read by the live code path, `read_excel(filename, sheet='Demand_kWh')` — was not. This repository
therefore ships **no data at all**: `*.xlsx` and `*.RData` are gitignored, and that was verified with
`git check-ignore` rather than assumed.

Whether the derived `.RData` objects are redistributable is a question for Pecan Street. Until it is
answered, this stays private.

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
