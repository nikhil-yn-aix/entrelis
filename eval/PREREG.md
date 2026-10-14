# pre-registration

frozen spec for every evaluation of entrelis. written before any test run. any later change goes in the deviation log at the bottom, with a date and a reason. nothing above the log is edited after this commit.

## 1. hypotheses

all directional, all tested on the test split only.

1. **recall vs sqlite:** on the benchmark recall category, entrelis bucket macro-f1 exceeds the sqlite recursive cte baseline by at least 0.10 (oracle extraction).
2. **recall vs graph:** on the same set, entrelis bucket macro-f1 exceeds the benchmark's stock graph condition by at least 0.10 (oracle extraction).
3. **rederive vs reachability:** on deaths whose affected set includes or-supported answers, entrelis bucket macro-f1 exceeds the reachability ablation (no delete-and-rederive) by at least 0.10.
4. **time rule:** removing the two-clock rule lowers bucket macro-f1 compared to full entrelis.
5. **stock questions:** entrelis stock accuracy on each of the five stock categories is no more than 0.05 below the best other system (non-inferiority).
6. **freshness:** entrelis has a lower stale-answer rate than vector rag and full context on questions asked after a retraction.
7. **real extraction:** with real extraction, entrelis bucket macro-f1 stays above the sqlite baseline with real extraction.
8. **ietf zombies:** at every cutoff, zombie precision is at least 0.90 and zombie recall at least 0.80.
9. **gate safety:** on death-bearing real messages, the missed-death rate has a 95% clopper-pearson upper bound of at most 0.05.
10. **gate cost:** at the frozen threshold, the local gate avoids at least 60% of llm calls on the full labelled set.
11. **shift:** bucket macro-f1 and missed-death rate on shifted text are reported next to clean text. no direction is claimed, the drop is the reported number.
12. **latency:** on a 100k-edge tenant, `impacted` p99 < 50 ms and the guard check round trip p99 < 50 ms.

## 2. primary metrics

**bucket precision, recall, f1** (recall category and ietf):
- for each death d and each bucket b in {stale, unlucky, preventable}: pred = items the system puts in b, gold = items truly in b
- p = |pred ∩ gold| / |pred|, r = |pred ∩ gold| / |gold|, f1 = 2pr / (p + r)
- empty-set rule: pred and gold both empty gives p = r = f1 = 1. exactly one empty gives f1 = 0, with the undefined term set to 0
- per-death f1 = mean of the three bucket f1 values
- **primary = macro**: mean of per-death f1 over all deaths. micro (pooled counts over all deaths) is a sensitivity check
- bucket rule: t_use = the latest time the item touched the dead fact on its path. t_use < valid_to is stale, t_use < the learned-at time of the death is unlucky, otherwise preventable
- normaliser: benchmark items are question ids (exact match). ietf items are rfc numbers as integers

**stock accuracy** (benchmark): the benchmark's own grader, unmodified. exact set equality after its alias normalisation, per category, plus its per-question f1.

**zombie precision and recall** (ietf):
- zombie = an rfc that cites r normatively, was published on or after r's death, and does not also cite r's successor
- pred = citers entrelis flags as built on dead r at the cutoff
- p and r per cited rfc with the empty-set rule above, then macro over cited rfcs
- same-month cases (citer and death in the same month) are their own stratum, reported separately and left out of the primary

**missed-death rate** (signals): fn / (tp + fn) on death-bearing messages, with a 95% clopper-pearson upper bound.

**latency**: p50, p95, p99 in ms, server and wall both reported.

## 3. secondary metrics

- micro bucket f1, and p and r per bucket
- freshness: share of answers that reflect the latest valid fact. stale-answer rate: share of answers equal to a retracted value
- extraction p, r, f1: triples normalised (lowercased, whitespace collapsed, aliases resolved to the canonical name) against generator truth. asserts and retracts reported separately, micro over messages
- llm calls avoided: 1 − (messages passed to the llm / all messages), with an operating curve over thresholds
- signal accuracy per provider, macro-f1 over labels
- calibration: ece with 15 equal-width bins on the top-class probability, a reliability diagram with counts, brier score
- cost: usd per 1k events, split into ingest and query, from logged tokens × a dated price table
- routing top-1 and top-3: the suggested fixer vs who actually authored the successor or fix
- transitive zombies in ietf (citers of zombies)
- dogfood counts (cards, true and false alarms, edits denied, re-plans). descriptive only, no inferential claim

## 4. systems

| system | what |
|---|---|
| full context | every event in the prompt |
| vector rag | bm25 + dense retrieval fused with rrf |
| sqlite recursive cte | the same rules as entrelis on sqlite, no graph database |
| stock graph | the benchmark's own graph condition |
| entrelis | full system |
| entrelis, no time rule | one clock only |
| entrelis, reachability | everything downstream of a death is affected, no delete-and-rederive |

- every system runs with oracle extraction and with real extraction
- the same answering model, prompt and caching serve every llm arm
- llm-agent arms may be capped at 10 worlds for cost. if so, it is stated next to every number they produce
- agent-memory-bench pinned at `b8ccc40348a49623949ce9754c96771ff1f2e7b0`
- graph database: falkordb 6.0.2. image digest fixed before any test run, logged in the deviation log
- model ids (extraction, answering, embeddings, local classifiers with revision shas), prompt hashes and the gate threshold: fixed before any test run, logged in the deviation log

## 5. datasets

| set | what | size | truth |
|---|---|---|---|
| benchmark | agent-memory-bench worlds, length 200, test seeds 1 to 20, dev seeds 101 to 105 | 20 test worlds × 25 stock questions + the recall category | the generator's asserts, retracts, final state and aliases |
| recall category | a wrapper over each world: earlier questions are the consumers. affected = earlier questions whose answer on the snapshot after a retraction differs from their gold. includes or-support cases. a second clock from a separate rng stream (stock questions stay byte-identical) gives each retraction valid_to = learned − Δ | every retraction in every world | derived from generator snapshots. labelled "ours" in every report |
| ietf | `rfc-index.xml` + datatracker normative references, rfc citers only, drafts excluded | all eligible deaths at 4 cutoffs, at least 300 death events and 2k citer pairs | obsoleted-by + publication months |
| labelled messages | 200 death-bearing, 100 other fact changes, 300 chatter, over 6 or more kinds. 200 real (our slack, public github issues and prs), 400 llm-written in realistic styles, each label agreed by a second model, every 5th checked by hand | 600 | hand labels + checked generation |
| real-text set | 150 or more real messages, pr bodies and issue comments, separate from the 200 above, all hand-labelled | 150+ | hand labels |
| shifted text | 4 to 6 held-out templates per retract kind, hard negatives (negations, quotes, hypotheticals), 300 llm paraphrases (20 hand-checked), 10 entity-swapped worlds | as listed | carried over from the generator |
| dogfood | our own slack, github and claude code sessions during the build | whatever happens | outcomes we click |
| latency graphs | seeded synthetic tenants at 10k and 100k edges, 1m optional, from `eval/data/synth_graph.py` | as listed | n/a |

- ietf cutoffs: end of 2005, 2010, 2015, 2020. at cutoff t only rfcs published in or before t are used, and obsoleted-by only where the successor was published in or before t
- sha256 of `rfc-index.xml` and of the datatracker dump, the snapshot date, and the synthetic generator seeds: fixed before any test run, logged in the deviation log

## 6. dev and test splits

- benchmark: tuning on dev seeds 101 to 105 only. test seeds 1 to 20 are not run until freeze
- ietf: tuning on a 2000 cutoff only, never reported as a result. the 4 test cutoffs run once after freeze
- labelled messages: a stratified 30% dev split by a fixed seed. thresholds are chosen on dev. the other 70%, the real-text set and the shifted set are test only
- shifted templates are never seen by any tuned component
- freeze = the commit that logs model ids, prompt hashes and thresholds in the deviation log. test runs happen only after it

## 7. stats plan

- 95% percentile bootstrap, b = 10,000, resampled by cluster: world in the benchmark, cited rfc in ietf, message in signals
- paired comparisons: per-cluster difference with a paired bootstrap ci. mcnemar exact for binary outcomes
- holm correction over the 3 main comparisons only (hypotheses 1, 2, 3), family alpha 0.05. everything else is reported uncorrected and called exploratory
- effect sizes always shown next to p values
- under 15 clusters, a caveat is printed next to the number
- binomial bounds by clopper-pearson

## 8. sample sizes

- ±5% at p ≈ 0.9 needs n ≈ 139, so every proportion we headline has at least 139 cases or says it doesn't
- a paired difference of 0.10 at sd 0.15 needs about 18 clusters, hence 20 test worlds
- zero misses in 300 death-bearing positives bounds the miss rate at ≤ 1% (95%), hence 200 death-bearing messages plus the real-text positives
- ietf: at least 300 deaths and 2k citer pairs over the 4 cutoffs

## 9. exclusions

- an unparsable or empty system output counts as wrong, never dropped
- failed or timed-out runs are counted as wrong and reported with their count
- no seed picking: every test seed is run and reported
- ietf drafts are excluded by design (only their current revision is visible). same-month cases go to their own stratum
- no other exclusions

## 10. budget

- max usd and max runs per eval: fixed before any test run, logged in the deviation log
- `FULL=1 make eval` enforces the budget and stops when it is reached. a stopped run is reported as stopped

## 11. deviation log

| date | change | reason |
|---|---|---|

## 12. reporting

- negative and null results are published next to the positive ones
- every baseline appears in every table it ran on
- real-text and generated numbers side by side, never generated alone as the headline
- clean, paraphrased and held-out-template numbers side by side
- every table in the readme is generated by `make eval` from the latest test reports
- each report records the git sha, date, seeds and model ids

## 13. latency protocol

- hardware, os, cpu model, ram, falkordb image digest and config recorded in each report
- 20 warmup runs discarded, then 3 separate process runs × 2000 ops, coefficient of variation across runs reported
- server ms (falkordb query stats) and wall ms (client side) both reported
- graph sizes 10k and 100k edges generated, plus the real ietf tenant. 1m optional, in the slow suite
- every latency table says whether its data is real or generated

## 14. known threats

- the generator has 2 to 3 templates per kind, so clean-text extraction overstates real quality. mitigated by the real-text and shifted sets
- the recall category and the second clock are our own construct over the sponsor's generator
- ietf dates are month-granular, handled by the same-month stratum
- drafts only show their current references, so they are excluded
- llm-written messages may share style with the llm extractor. the real-text set is reported separately
- hand labels come from the team that built the system. every 5th generated label and every real label is checked by hand, disagreements logged
