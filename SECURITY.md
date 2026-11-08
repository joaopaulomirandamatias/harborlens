# Security Policy

**Supported status:** pre-alpha research only; no production security warranty or SLA.

Report vulnerabilities using GitHub private vulnerability reporting if enabled, or contact the maintainer privately. Do not post exploit details, secrets, raw AIS customer records or personal information in public issues.

Current risks include adversarial CSV input, malformed timestamps and paths, ZIP decompression bombs, excessive input RAM, spoofed MMSI, third-party data license violations and unreviewed spreadsheets. The current CLI is **not hardened for arbitrary public uploads**. The future public API and SaaS are not implemented.

Before managed deployment, require threat modeling, secure identity, tenant isolation, dependency and secret scanning, incident handling, retention control, encryption, backups, and restore testing. See [Threat Model](docs/security/threat-model.md).
