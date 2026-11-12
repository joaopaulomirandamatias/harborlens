# Nonfunctional Requirements

References: ISO/IEC 25010 quality vocabulary, NIST SSDF SP 800-218, OWASP ASVS, JSON Schema 2020-12. These are engineering references, not asserted certifications or audited compliance.

| ID | Priority | Dimension | Requirement/target |
| --- | --- | --- | --- |
| NFR-001 | P0 | Safety | All outputs MUST display NOT FOR NAVIGATION and pre-alpha status |
| NFR-002 | P0 | Reproducibility | Input SHA-256 and thresholds MUST accompany each run; output hashes are planned |
| NFR-003 | P0 | Portability | Python >=3.10; synthetic sample MUST run offline without external credentials |
| NFR-004 | P0 | Determinism | Same input and method SHOULD yield identical events/QA, subject to documented ordering |
| NFR-005 | P0 | Data quality | Invalid, excluded, duplicated and retained records MUST be counted separately |
| NFR-006 | P0 | Information security | No public commitment of secrets or unauthorized customer or third-party AIS data |
| NFR-007 | P1 | Scalability | Multi-day segmentation keeps a fixed SQLite cache (8192 KiB), memory mapping off, and `temp_store=FILE` so that working set does not grow with day count (SPEC-002). The 8 MiB soft heap limit is a bound only when `soft_heap_limit_enforced` is true. Real national daily files still need a bounded-memory benchmark before capacity is claimed. |
| NFR-008 | P2 | Availability | No current SLA; future SLA targets must be negotiated and tested |
| NFR-009 | P1 | Observability | Track input lineage, runtime, errors and data gaps; no sensitive log leakage |
| NFR-010 | P1 | Interoperability | JSON Schema 2020-12 and, if implemented, OpenAPI 3.1 contract compatibility |
| NFR-011 | P1 | Units | UTC time, WGS84 lon/lat and explicitly stated knots/minutes/meters |
| NFR-012 | P1 | Data integrity | Immutable source/run identity and output fingerprint for production validation |
| NFR-013 | P1 | Privacy | Source-specific retention, access and redistribution policy |
| NFR-014 | P1 | Maintainability | Tests, ADRs, specs and traceability reviewed for behavioral changes |
| NFR-015 | P0 | Cost | Optional downloads MUST have explicit file/date and size cap |
| NFR-016 | P1 | Accessibility | Target WCAG 2.2 AA for future reference UI; not yet implemented |
| NFR-017 | P2 | Security isolation | Future multi-tenancy MUST demonstrate isolation, least privilege and encryption |
| NFR-018 | P2 | Reliability | Any paid service requires approved RPO/RTO and tested restore/incident plans |
| NFR-019 | P2 | Legal | External data use MUST respect source-specific rights and contracts |
| NFR-020 | P1 | Interpretability | Separate reported, inferred, validated, simulated and unknown observations |

P1/P2 requirements are proposed future gates. The current CLI has no production availability or security SLA.
