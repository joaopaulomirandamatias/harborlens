# Specification-Driven Development (SDD)

The specification is the source of truth: **problem → requirement → design/ADR → acceptance criteria → issue → tests → review → evidence**. A GitHub issue is an implementation slice, not a new source of behavior.

Each feature folder contains `spec.md`, `design.md`, `tasks.md`. Every requirement has a stable ID and priority. Write acceptance tests as **Given / When / Then**. The repository uses MUST/SHOULD/MAY under RFC 2119/8174. A proposed capability is not implemented, and an implemented synthetic test is not an empirical validation. Include negative cases, uncertainty, data rights, security, compatibility, and traceability in every review. Use Conventional Commits and SemVer; record consequential design choices in ADRs.

Definition of Done: tests pass; specs and traceability match code; source licenses reviewed; documented outputs are reproducible; reviewer accepts limitations. A real-world accuracy claim requires independent labelled truth and test methodology.
