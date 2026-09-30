# Interpreting results

Read the persisted result and summary before recommending a configuration. Separate these signals:

- Quality: validation and end-to-end success on representative cases.
- Reliability: provider successes, provider errors, and retry behavior.
- Latency: observed median and tail latency under the tested concurrency and inputs.
- Cost: provider-reported or configured pricing for this run. Unknown cost is not zero cost.
- Constraints: hard requirements that make a candidate ineligible even when another metric is good.

The Pareto frontier contains configurations that are not dominated across the measured objectives.
Explain the trade-off instead of collapsing it into a universal ranking. A recommendation must name
the workload, dataset coverage, objective, constraints, pricing basis, and repetition count that
produced it.

Treat fixture success as a plumbing check only. Treat a small live run as exploratory evidence. A
selection-grade decision needs representative production examples, stable ground truth or a
reviewed rubric, and enough repetitions for the workload's variability.

Before expanding a run, compare what uncertainty remains with the additional request count and
known or unknown cost. Get confirmation for unknown pricing, large inputs, or any expansion beyond
three candidates, five cases, and one repetition. InferenceFit constraints are evaluated after
requests complete; they exclude results from selection but do not prevent the requests from being
billed.

Report provider failures and missing cost data directly. Do not silently rank missing values as
free or convert an ineligible candidate into a recommendation.
