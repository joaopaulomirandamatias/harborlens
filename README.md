# HarborLens USA

**Pre-alpha research code. Synthetic fixtures only. NOT FOR NAVIGATION.**

HarborLens explores auditable AIS ingest and provisional low-speed stationary candidates in the Houston–Galveston area. A candidate is **not** a verified berth, anchorage, queue, port call, or emissions claim.

```bash
python -m pip install -e .
python -m unittest discover -s tests -v
harborlens --input tests/fixtures/synthetic_ais.csv --out results
```

[Specification-driven process](docs/engineering/spec-driven-development.md) · [Requirements](docs/requirements/functional.md) · [Open-source versus paid scope](docs/product/open-core.md). No real-world AIS accuracy or commercial product is claimed.

Sources: [NOAA AIS](https://marinecadastre.gov/ais/), [USACE](https://www.iwr.usace.army.mil/About/Technical-Centers/WCSC-Waterborne-Commerce-Statistics-Center/), [BTS](https://www.bts.gov/ports), [EPA emissions guidance](https://www.epa.gov/state-and-local-transportation/port-emissions-inventory-guidance).
