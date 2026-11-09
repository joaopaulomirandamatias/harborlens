# Historical NOAA Geometry Vintage Audit (SPEC-004)

**Research-only. This workflow never certifies historical geometry, port operations, anchorage, berth occupancy, or navigation.**

## Why it is needed

NOAA [ENC edition and issue-date documentation](https://charts.noaa.gov/ENCs/ENCDates.html) distinguishes base cell availability (Update Application Date) from update issue date. Current NOAA [ENC downloads](https://charts.noaa.gov/ENCs/ENCs.shtml) are maintained and are not equivalent to a January 2024 edition. An edition's date alone does not prove that a current NOAA OceanReports Anchorage Area polygon matched the historical chart polygon.

This offline audit records source/receipt hashes and checks date conflicts. It never authorizes historically valid geometry, commercial data reuse or confirmed vessel states.

## Basic usage, with no ENC evidence

First obtain an authorized local NOAA polygon GeoJSON and its adjacent source receipt using the existing opt-in geographic command. Then execute:

~~~bash
harborlens-geometry-vintage \
  --polygons data/houston-anchorages.geojson \
  --start 2024-01-02T00:00:00Z \
  --end 2024-01-02T06:00:00Z \
  --out results/noaa-vintage-audit.json
~~~

The command will return a date_assessment of no_documentary_enc_evidence. Geometry, source receipt and output are hash-linked; historical validity remains not_verified.

## Optional documentary ENC metadata

For a separate NOAA ENC document whose exact cell, edition, issue date and content checksum are known, a user can supply a **strictly unverified** metadata JSON file. This is not a permit to use current polygons as historic facts.

~~~json
{
  "source_kind": "NOAA_ENC",
  "cell_id": "US5TX1234",
  "edition_number": 4,
  "edition_date": "2026-08-04",
  "last_issue_date": "2026-10-01",
  "evidence_url": "https://charts.noaa.gov/ENCs/ENCsIndv.shtml",
  "referenced_document_sha256": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "evidence_status": "user_supplied_unverified"
}
~~~

**The above values are synthetic examples, not a real verified 2026 ENC cell/edition or authentic source file hash.** Obtain the actual historic cell independently before using evidence in a research paper.

~~~bash
harborlens-geometry-vintage \
  --polygons data/houston-anchorages.geojson \
  --enc-evidence data/enc-documentary-record.json \
  --start 2024-01-02T00:00:00Z \
  --end 2024-01-02T06:00:00Z \
  --out results/houston-vintage-documentary-audit.json
~~~

The optional evidence contract is schemas/v1/noaa-enc-documentary-evidence.schema.json. The output receipt contract is schemas/v1/geometry-vintage-audit.schema.json. A report can return: no_documentary_enc_evidence; edition_postdates_study; update_issue_after_study_start; document_dates_compatible_but_geometry_unverified.

**None of those statuses is an approval.** Every report still has historical_geometry_validity=not_verified and operational_event_validation=not_verified. A date preceding 2024 does not mean that the same polygon boundaries remained unchanged through the study period, or that OceanReports was derived from the cited ENC.

## Source integrity and no-data protection

- Requires the NOAA Polygon source receipt with a matching SHA-256 and explicit historically unverified, unreviewed and rights-review-required statuses.
- Input polygon file is capped at 32 MiB, source/evidence JSON at 128 KiB, output paths cannot overwrite the source files or an existing report.
- Does not access network resources, transmit source files, or modify any AIS result.
- External ENC documentary metadata must retain evidence_status=user_supplied_unverified; unreviewed metadata can never claim historic certification.
- Does not parse actual S-57 edition files or reconstruct old chart cells; that is a separate future engineering and data-rights task.

## Primary NOAA sources

- [NOAA ENC issue and update date definitions](https://charts.noaa.gov/ENCs/ENCDates.html)
- [NOAA ENC downloads and catalog](https://charts.noaa.gov/ENCs/ENCs.shtml)
- [NOAA ENC Direct to GIS FAQ (weekly updates and potential duplicates across scale bands)](https://www.nauticalcharts.noaa.gov/learn/encdirect/)
- [NOAA ENC GIS data and services](https://www.nauticalcharts.noaa.gov/data/gis-data-and-services.html)

## Next acceptance gates

1. Locate actual date-compatible January 2024 ENC/anchorage source files, with independent source authenticity, edition/update applications and licensing evidence.
2. Validate that the archival cell area, scale, source feature IDs and topology correspond to the current NOAA polygon source.
3. Preserve geometry and source-version uncertainty in historical AIS outputs.
4. Use independently labeled operational port/terminal events before declaring anchorage waiting or berth occupancy.

**NOT FOR NAVIGATION. NO CERTIFIED HISTORICAL GEOMETRY OR VESSEL EVENTS.**
