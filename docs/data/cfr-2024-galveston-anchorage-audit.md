# U.S. Coast Guard 2024 Federal Anchorage Boundaries — Documentary Audit

**SPEC-004 — Regulatory reference data only. NOT FOR NAVIGATION. No WGS84 polygons or verified AIS states are produced.**

## Authoritative historic federal text

The **July 1, 2024** annual Code of Federal Regulations (CFR) contains 33 CFR 110.197, Galveston Harbor, Bolivar Roads Channel, Texas. It explicitly lists four anchorage areas with latitude/longitude corner coordinates in degrees/minutes/seconds.

- [Government Publishing Office 2024 official annual CFR Title 33, Vol. 1](https://www.govinfo.gov/content/pkg/CFR-2024-title33-vol1/html/CFR-2024-title33-vol1.htm): see printed page 538, 33 CFR 110.197(a)(1)–(4).
- [33 CFR 110.1(d) in the same official annual edition](https://www.govinfo.gov/content/pkg/CFR-2024-title33-vol1/html/CFR-2024-title33-vol1.htm): latitude/longitude coordinates not expressly designated NAD83 require correction before plotting on NAD83-referenced charts.
- [2018 Federal Register rule establishing Anchorage A East](https://www.govinfo.gov/content/pkg/FR-2018-04-27/pdf/2018-08873.pdf): includes express NAD83 datum and the A East corner transcription.
- [2021 final rule on anchorage B duration](https://www.govinfo.gov/content/pkg/FR-2021-02-01/pdf/FR-2021-02-01.pdf): amended paragraph (b)(2) regarding time limits, not automatically the geometry.

**Historical date distinction:** the government-published **2024 annual edition is revised as of July 1, 2024**. That alone does not verify that every regulatory text paragraph was unchanged on January 2, 2024. The previous amendments provide useful historical context, but this implementation does not claim to have completed a day-exact legal status audit (including intervening Federal Register revisions) for January 2024.

## Four anchored areas and safety flags

| Area | Coordinate source | Reference datum | Literal ring topology | Auto AIS join |
| --- | --- | --- | --- | --- |
| A | 33 CFR 110.197(a)(1), 2024 edition | NOT explicitly labeled NAD83 | Valid literal ring in 2-D | **Blocked** |
| B | 33 CFR 110.197(a)(2), 2024 edition | NOT explicitly labeled NAD83 | Valid literal ring in 2-D | **Blocked** |
| C | 33 CFR 110.197(a)(3), 2024 edition | NOT explicitly labeled NAD83 | Valid literal ring in 2-D | **Blocked** |
| A East | 33 CFR 110.197(a)(4), 2024 edition | Explicit NAD83 | **Invalid in published vertex order** | **Blocked** |

The A East sequence, when converted literally from published DMS and connected in the printed order, yields a self-intersection under Shapely planar topology checking. This is an **engineering review finding**, not a claim that the official regulation is legally defective. We must determine the intended polygon from authoritative original rulemaking exhibits/ENC and obtain qualified human review before using it. Do **not** silently sort coordinates or repair the shape with a convex hull.

The other three locations are valid literal rings in raw latitude/longitude number space but **lack explicit NAD83 designation**, and 33 CFR 110.1(d) warns against assuming one. Therefore, the numeric coordinates cannot simply be treated as EPSG:4326 WGS84 polygons and overlaid with historical AIS.

## Implementation and usage

Install the existing optional geographic dependency (Shapely) and execute a bounded, offline documentary transcription QA:

~~~bash
python -m pip install -e '.[geo,dev]'
harborlens-cfr-anchorage-audit \
  --study-date 2024-07-01 \
  --out results/cfr-2024-galveston-anchorages.json
~~~

For an AIS study dated January 2, 2024:

~~~bash
harborlens-cfr-anchorage-audit \
  --study-date 2024-01-02 \
  --out results/cfr-jan-2024-legal-screen.json
~~~

The output is **JSON with original DMS strings, raw decimal-degree transcription in source datum, topology diagnostics, source references, the annual-edition date and explicit review blockers**. It is deliberately NOT GeoJSON, has NO authorization for AIS spatial joins, and provides no waiting, anchorage occupancy or berth state.

Each run produces the same deterministic source transcription fingerprint; it does not yet hash the full official GPO original HTML document. The source URL is official, but independent archived-document integrity verification and an exact-as-of-January-2024 legal timeline remain separate work.

## Follow-up development requirements

1. Independently confirm source text and the exact January 2024 legal effective-date timeline from official 2023/2024 CFR editions, Federal Register documents and LSA.
2. Resolve the unspecified horizontal datum for A/B/C from original charts and appropriate geodetic transformation references.
3. Resolve A East published-vertex order/topology through official rulemaking attachments, map figures or authoritative agency interpretation; do not manufacture a perimeter.
4. Once independently documented, create a **separately reviewed, dated WGS84 EPSG:4326 polygon registry** with qualified reviewer decision and source hashes.
5. Compare those accepted polygons against historical AIS only as preliminary spatial context until independent vessel/terminal event labels justify any operational classification.

### Scientific and legal boundaries

A regulatory anchorage boundary proves only the designated legal area in its confirmed edition and datum, not whether an individual vessel anchored, waited for service or remained continuously inside its limits. Vessel location reporting and anchoring are different observations. This software is not a navigation aid, regulatory interpretation service or evidence of government endorsement.
