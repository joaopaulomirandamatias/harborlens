# Event Labeling Protocol (SPEC-003, issue #8)

**Status:** protocol and tooling defined; **no labels have been collected yet**. Research-only. NOT FOR NAVIGATION.

This protocol describes how sampled AIS intervals are labeled so that the stationary-candidate method (`stationary-v0.2`) can later be evaluated (#9). It does not make any candidate a verified event by itself.

## 1. What is labeled

A **sample unit** is one time interval of one MMSI drawn by `harborlens-label-sample` from a single, versioned run:

- **candidate** units are stationary candidates (`event_id`, `parameter_set`, censoring flags);
- **negative** units are intervals of observed movement from the same run that do not overlap any candidate.

Annotators label the unit, not the method. The sheet hides whether a unit is a candidate or a negative (`sample_id` only); the key is in the sampling manifest.

## 2. Label taxonomy

| Label | Meaning |
| --- | --- |
| `at_berth` | Moored at a berth or dock for most of the interval |
| `at_anchor` | Anchored or holding position in an anchorage or open water for most of the interval |
| `other_stationary` | Stationary but neither berth nor anchor (for example drifting, fleeting area, lock, shipyard, tug standby) |
| `maneuvering` | Low-speed movement: docking, undocking, assisted turning, channel creep |
| `transit` | Underway between places |
| `mixed` | The interval clearly contains two or more of the states above; record the split time in `notes` |
| `unknown` | The evidence available to the annotator cannot support any label |

`unknown` is a valid answer and must be used rather than a guess. It is never counted as a correct negative (#9).

## 3. Evidence levels

Every label records the evidence it rests on (`evidence_level`, `evidence_sources`):

- **L2 — expert review of AIS:** the AIS track itself (speed, heading, positions, transmitted navigation status) plus public reference geography (NOAA/CFR anchorage areas, USACE facility points, imagery). This is the expected level for the pilot. It is **not** independent ground truth: AIS-based labels share the input with the method.
- **L3 — independent operational record:** a terminal, pilot, port or vessel-schedule record for that vessel and time, obtained with permission. Only L3 labels support claims about real-world accuracy.

Transmitted `nav_status` is auxiliary evidence only (BR-011).

## 4. Rules annotators follow

1. **Censoring.** If the unit is flagged `left_censoring`/`right_censoring = censored`, label the observed state but do not judge its full duration; set `duration_judgement = not_assessable`.
2. **Fragmentation.** If the same stop continues in an adjacent unit or candidate (short gap or speed spike), set `fragment_of_longer_stop = true` and name the neighbouring `sample_id` or `event_id` in `notes` when known. Do not merge units yourself.
3. **Gaps.** Do not infer what happened inside AIS gaps; if the gap decides the label, use `unknown`.
4. **Identity.** If the track suggests two vessels share the MMSI, use `unknown` and say so in `notes`.
5. **Confidence.** `high`, `medium` or `low`, about the label, not about the vessel.
6. **No outside facts without a source.** Any external fact must appear in `evidence_sources`.

## 5. Double annotation and adjudication

- At least two annotators label every unit in the pilot independently, without seeing each other's labels or the candidate/negative key.
- `harborlens-label-agreement` validates both sheets, reports raw agreement, Cohen's kappa over all seven labels and over the collapsed classes (stationary vs moving vs unknown), and lists every disagreement.
- A third person adjudicates disagreements; the adjudicated label keeps both original labels and the adjudicator's id. Disagreements are kept, not overwritten.
- Annotator ids are pseudonymous (for example `A1`, `A2`); no personal data enters the repository.

## 6. Pilot size and sampling

- Target: **at least 100 units**, roughly 70 candidates and 30 negatives, from one run. One hundred is a pilot objective, not a statistical guarantee.
- Strata for candidates: duration band (`<60`, `60–180`, `>180` minutes) × censoring (`uncensored`, `censored`, `unknown`) × vessel group (cargo, tanker, passenger, tug/service, other or unknown) × transceiver class (`A`, `B`, `absent_or_unknown`). Negatives are stratified by vessel group × transceiver class. `absent_or_unknown` is a missing, blank or other non-A/B class; those units stay in the sample. Transceiver class is a stratum because, on the recorded seven Houston days, Class B carried 7.4% of points but 32% of candidates (`docs/data/noaa-real-data-rerun-2026-11-09.md`), so class coverage must not be left to chance (FR-013, #65). Candidates also carry `length_m`, `draft_m` and `mmsi_category` for post-stratified analysis; units with a non-ship `mmsi_category` stay in the sample and are expected to be labeled `other_stationary` or `unknown`. The annotator sheet does not show the class.
- Coverage (FR-013, #65). Every non-empty stratum gets at least one unit when the requested count is at least the number of non-empty strata; the rest is allocated proportionally. When the requested count is smaller than the number of non-empty strata, full cross-cell coverage is impossible: `stratification.all_non_empty_strata_drawn` is false, and some duration × censoring × vessel group × class cells are omitted. Per-class coverage is still guaranteed. Every transceiver class present in the frame (`A`, `B`, `absent_or_unknown`) is drawn when the request is at least as large as the number of those classes. A 70-candidate pilot can therefore leave the flag false. Empty classes are omitted from the frame and are not a gap.
- Sampling is seeded and reproducible; the manifest records the run, `parameter_set`, seed, frame counts per stratum and the hidden candidate/negative key.

## 7. Data rights and storage

Labeling sheets contain MMSIs and timestamps from NOAA AIS. Keep them outside the public repository until the data-rights review (#42) says otherwise. Only aggregate agreement and evaluation results are published.

## 8. What this does not do

It does not select thresholds, does not upgrade any candidate to a verified berth, anchorage, wait or port call, and does not by itself produce precision or recall. Those require the evaluator (#9) and, for real-world claims, L3 evidence.

## 9. Adjudicated file for evaluation

After adjudication, one CSV per sample holds the final label per unit with the columns `sample_id`, `label`, `evidence_level`, `duration_judgement`, `true_start_utc`, `true_end_utc`, `adjudicator_id` (`schemas/v1/adjudicated-label.schema.json`). Give `true_start_utc`/`true_end_utc` (both or neither) only when the start and end of the labeled state are visible in the evidence; they feed the boundary-error metrics. `harborlens-evaluate --run … --sampling <sheet>.sampling.json --labels adjudicated.csv --out evaluation.json` produces the report.
