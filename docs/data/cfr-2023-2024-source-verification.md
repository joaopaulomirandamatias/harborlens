# Official 2023 and 2024 USCG Anchorage Coordinate Source Comparison

**Evidence date:** 2026-11-09 UTC.  
**Successful GPO source scan:** https://github.com/joaopaulomirandamatias/harborlens/actions/runs/42657424659  
**Scope:** Source-text DMS verification only. Not a day-exact January 2, 2024 legal-status certification, not a datum transformation, not for navigation, and not evidence of vessels anchoring.

## Official annual government sources

Both annual editions were fetched directly from the U.S. Government Publishing Office (GPO).

| Official edition | Revision date | Complete annual HTML SHA-256 |
| --- | --- | --- |
| [2023 Title 33 vol. 1](https://www.govinfo.gov/content/pkg/CFR-2023-title33-vol1/html/CFR-2023-title33-vol1.htm) | July 1, 2023 | 060d91f9730530836edc25ab4f6716fdea32b518807126c75339b00ec62cff14 |
| [2024 Title 33 vol. 1](https://www.govinfo.gov/content/pkg/CFR-2024-title33-vol1/html/CFR-2024-title33-vol1.htm) | July 1, 2024 | 88a88cee56190b0b7706064f11e2eea063077e251daafc9db5f881bca4af12cd |

Both official 33 CFR 110.197 Galveston Harbor/Bolivar Roads Channel sections contained the same **16 of 16 DMS corner-coordinate pairs** used by the HarborLens regulatory-coordinate registry, across Areas A, B, C and A East. Both government sources were actually retrieved and checked in an isolated GitHub Actions job. Their file bytes were not committed.

## Evidence status

| Verification | Observed result |
| --- | --- |
| GPO 2023 full source accessed and checksummed | PASS |
| GPO 2024 full source accessed and checksummed | PASS |
| Original 2024 federal DMS pairs vs HarborLens text | 16 / 16 present |
| Original 2023 federal DMS pairs vs HarborLens text | 16 / 16 present |
| Areas A/B/C explicitly designated NAD83 | NO |
| Area A East explicitly designated NAD83 | YES |
| A/B/C raw corner-order planar rings | No self-intersection detected |
| A East raw vertex-order ring | **Self-intersection; independent review required** |
| Automatic conversion into WGS84 AIS-joinable polygons | **BLOCKED** |
| Verified vessel waiting/anchorage/berth events | **ZERO** |

The A East finding is a Shapely engineering diagnostic of the **published literal vertex order**, not a legal judgment that the federal rule is defective. The intended nautical polygon or source exhibit must be reviewed by a qualified expert. For A/B/C, 33 CFR 110.1(d) warns against treating coordinates as NAD83 without explicit labeling and source corrections.

## Exact historical-date limitation

The 2023 and 2024 annual publications bracket January 2, 2024. Their matching text is important historical evidence, but does **not** conclusively rule out an intervening Federal Register amendment, implementation date or later repeal between the annual editions.

An exact-as-of-January 2024 assessment must separately inspect the Federal Register/List of CFR Sections Affected (LSA), effective dates, original chart-datum information and applicable agency notices. The implementation reports a study-date status of prior_to_available_annual_edition_unverified for a January 2 query based on a July 2024 edition.

The legal-regulation corner lists are also **not** proved to correspond one-for-one to the current NOAA OceanReports six polygon features. They are separate source types and should not be combined as though equivalent.

## Available source-audit tool

The offline CLI named harborlens-cfr-anchorage-audit emits a versioned **ordinary JSON** register with source DMS coordinates, native/unknown datum declarations, literal topology diagnostics, source edition scope and conservative review blockers. It does NOT produce WGS84 GeoJSON and never authorizes an AIS zone-join.

The official-source verification GitHub workflow is manual-only, not tied to every push.

## Next acceptance gates

1. Check interim 2023–2024 Federal Register/LSA amendments and effective dates for section 110.197.
2. Independently establish source horizontal datum and correction method for A/B/C.
3. Review A East original rulemaking exhibits and intended corner order/topology; no automated repair.
4. Produce a separately reviewed date-compatible WGS84 registry with documented source, transformation, license and reviewer.
5. Only then test AIS spatial context and independent vessel/terminal labels; never infer occupancy or waiting from location alone.

**NOT FOR NAVIGATION. NOT CERTIFIED HISTORIC GEOMETRY OR MARITIME ACTIVITY.**
