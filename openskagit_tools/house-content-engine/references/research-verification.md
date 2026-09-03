# Research & Verification Workflow

## Goal

Determine what the evidence actually supports. The hypothesis is something to test, not an editorial instruction.

Required output: verified evidence package + fact ledger + disposition.

## 1. Restate the analytical question

Identify population, outcome, characteristic, geography, time period, and major controls without pretending to precision the data cannot support.

## 2. Define population before interpreting results

Set inclusion/exclusion logic for property use, valid sales, date range, geography, property characteristics, active records, and required completeness.

If filters later change for legitimate data-quality reasons, record why.

## 3. Establish authoritative context

For rules, use current official Washington/local sources. Do not use social discussion as legal/administrative authority.

## 4. Inspect fields and analytical unit

Verify field meaning, year/version, nulls, codes, units, and whether rows represent parcel, parcel-year, sale, improvement, land segment, permit, or another entity.

Prevent one-to-many joins from inflating sample counts.

## 5. Data quality

Inspect counts, missingness, duplicates, impossible values, unusual prices, coding consistency, zero/nominal sales, and historical/current mixing.

## 6. Sale validation

Use legitimate market transactions where the question depends on market behavior. Apply available sale-validity logic and record it.

## 7. Sample assessment

Classify sample quality as strong, moderate, exploratory, or insufficient. Quality and comparability matter more than raw count.

## 8. Describe the sample

Before the central comparison, examine counts and central tendencies for price, living area, acreage, age, geography, time, and target-feature prevalence.

Look for obvious imbalance.

## 9. Start simple

Use descriptive medians/distributions/ratios first. Then investigate whether the apparent relationship survives reasonable controls.

## 10. Confounders

Always ask what else could explain the result. Common confounders:

- location/neighborhood
- living area
- acreage
- age/effective age
- condition/quality
- waterfront/view
- garage/shop/outbuildings
- utilities/zoning/access
- sale date/market cycle

## 11. Control strategy

Use the simplest credible approach:

- restricted cohort
- stratification
- matching
- multivariable analysis when warranted

Do not use complexity for appearance.

## 12. Geography and time

Prefer within-market comparisons where feasible. Avoid comparing substantially different markets or time periods without adjustment/stratification.

## 13. Nonlinearity

For acreage, living area, age, waterfront footage, and similar variables, test bins/thresholds/plateaus rather than assuming a linear unit contribution.

## 14. Outliers

Inspect before excluding. Record the reason for exclusion. Never remove legitimate observations merely because they weaken the story.

## 15. Robustness

For strong claims, check whether the finding survives reasonable alternatives such as median vs. average, different periods, slightly different cohorts, geography restrictions, or removal of genuine data errors/extremes.

## 16. Negative and inconclusive results

A rejected hypothesis can be a strong story. Distinguish “hypothesis unsupported” from “evidence cannot answer the question.”

Never convert uncertainty into a conclusion.

## 17. Practical importance

Evaluate magnitude and homeowner relevance, not statistical significance alone.

## 18. Causation

Default to association language. Observational property data rarely proves a clean fixed contributory value.

## 19. Fact ledger

Every potential production claim must be classified:

- `VERIFIED_FACT`
- `CALCULATED_RESULT`
- `ANALYSIS_INTERPRETATION`

Each important ledger record should retain:

- fact ID
- statement
- class
- value/unit where applicable
- source/source reference
- population/property references
- calculation/method where applicable
- confidence
- limitations
- public-use approval

## 20. Traceability/reproducibility

Preserve source/tool, filters, date range, grouping logic, exclusions, and calculation method for important results. Store query/spec/hash identifiers when practical.

## 21. Privacy

Research may inspect public property records where appropriate. Flag owner names, exact addresses, parcel IDs, or unusually personal details as not approved for public use unless specifically justified.

## 22. Evidence grade

- `A` strong
- `B` good with limitations
- `C` exploratory
- `D` insufficient

Rate storyworthiness separately: strong / moderate / weak / none.

## 23. Disposition

End with exactly one:

- `ADVANCE`
- `ADVANCE_WITH_LIMITATIONS`
- `REFRAME`
- `RETURN_TO_DISCOVERY`

Do not advance because of sunk cost.

## 24. Research handoff

Pass to Story:

- research question
- homeowner concern
- answer summary
- surprising finding
- evidence grade
- storyworthiness
- fact ledger
- sample description
- methodology summary
- major controls
- limitations
- authoritative context
- approved statistics/examples
- visualizable findings
- prohibited claims
- source references

## 25. Prohibited claims

Explicitly list tempting claims the evidence does not support. Downstream stages must treat these as hard guardrails.
