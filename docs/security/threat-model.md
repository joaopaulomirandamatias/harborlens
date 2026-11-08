# Threat Model (Research CLI)

| Risk | Consequence | Current control / gap |
| --- | --- | --- |
| Malformed CSV or timestamps | Wrong records or crash | Per-row validation; fuzz/property tests remain pending |
| ZIP bomb / large datasets | Unbounded CPU/RAM | Reader byte caps and ZIP ratio check are proposed in #4; not an upload sandbox; stress testing remains pending |
| MMSI reuse, AIS spoofing | Incorrect vessel identity and event inference | Unvalidated stationary-candidate label only; identity resolution pending |
| Corrupted archives/results | Failed reproducibility | Input SHA-256; output hashes and immutability pending |
| Spreadsheet formula injection | Malicious formula execution | Export sanitization pending before spreadsheet workflows |
| License or confidentiality breach | Legal and operational harm | No real/proprietary AIS in repo; rights checklist and data segregation required |
| Future public API | Unauthorized access or denial of service | No HTTP API deployed; auth, limits, SSRF/security review required |
| Future multi-tenancy | Cross-customer data leakage | Not implemented; independently verify tenant isolation before any sale |

Follow [NIST SSDF](https://csrc.nist.gov/pubs/sp/800/218/final) and [OWASP ASVS](https://owasp.org/www-project-application-security-verification-standard/) as references, not as claimed certifications.
