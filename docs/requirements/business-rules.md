# Domain and Business Rules

The rules protect the integrity of scientific and operational claims. The baseline has not been validated against authentic AIS or port authority ground truth.

| ID | Rule |
| --- | --- |
| BR-001 | A stationary_candidate MUST NOT be interpreted as berth, anchorage, waiting, congestion or port call |
| BR-002 | Naive NOAA BaseDateTime timestamps are interpreted as UTC; ISO UTC is exported |
| BR-003 | v0.1 candidate requires >=8 points, SOG <=0.5 knots, duration >=30 minutes, <=15-minute gaps and <=1-km radius; thresholds are research hypotheses |
| BR-004 | Houston AOI is a research rectangle (-95.70,29.10,-94.20,30.10), not official port geometry |
| BR-005 | Exact duplicates use MMSI, timestamp and coordinates rounded to 6 digits |
| BR-006 | Invalid and out-of-zone observations MUST not enter the cleaned dataset |
| BR-007 | Missing AIS / gaps require unknown status, not interpolation or fabricated continuity |
| BR-008 | MMSI MUST NOT be treated as guaranteed permanent vessel identity |
| BR-009 | Verified berth or anchorage assignment requires authoritative dated geofences and independently evaluated evidence |
| BR-010 | Waiting time requires verified port call linkage, not merely low speed |
| BR-011 | AIS nav_status is transmitted auxiliary evidence, not independent truth |
| BR-012 | Coverage, denominators and unknown share accompany all population metrics |
| BR-013 | Aggregated BTS statistics are only aggregate cross-checks, not vessel ground truth |
| BR-014 | Emissions results are modeled scenarios with engine/load/fuel/factor uncertainty; not direct measurements |
| BR-015 | Software license does not transfer third-party data reuse or redistribution rights |
| BR-016 | Public research data exports MUST exclude customer-confidential and unauthorized licensed records |
| BR-017 | Open scientific methods must remain independently reproducible when wrapped by paid services |
| BR-018 | No operational, commercial or migration-impact claims without verified supporting evidence |
| BR-019 | A candidate whose first or last observation lies within one `max_gap_minutes` of an analysis-window edge is censored; its duration is a lower bound and MUST be excluded from, or reported separately in, duration statistics. Without a known window, censoring is `unknown`, never `not_censored` |

Every event label and data-rights decision must preserve the source version, method version, responsible reviewer and known unknowns.
