# Contributing to HarborLens

All code, commit messages, GitHub issues and documentation must be written in English.

1. Pick a SPEC-### from `specs/`, or propose a new specification before changing behavior.
2. Link FR/NFR/BR requirement IDs, Given/When/Then acceptance criteria, dependencies and measurable evidence in the GitHub issue.
3. Branch using `feat/SPEC-###-name`, `fix/ISSUE-###-name` or `docs/name` and follow Conventional Commits.
4. Add positive, negative, boundary and regression tests. Run `python -m unittest discover -s tests -v`.
5. Update JSON Schemas, ADRs, traceability and changelog when behavior or contracts change. Bump the package version (`pyproject.toml`, `src/harborlens/__init__.py`, `CITATION.cff`) for any change that can alter outputs: it is part of every `run_id`.
6. Do not commit authentic NOAA AIS, licensed data, private terminals' data, secrets, or third-party IP without explicit rights verification.
7. A reviewer must confirm requirements, tests, license, security, uncertainty claims and documentation before merging.

**Definition of Done:** Accepted spec linked, tests pass, outputs reproducible, data provenance and rights documented, and no synthetic-only claim is presented as empirically validated.
