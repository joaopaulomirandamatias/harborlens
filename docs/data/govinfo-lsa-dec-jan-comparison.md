# Official 2023-12 vs 2024-01 GPO LSA Title 33 Source Comparison

**SPEC-004 | Implementation status: synthetic regression tests complete; official two-PDF reproducibility run pending.** This file is an engineering procedure. It is not a certificate that 33 CFR 110.197 was legally unchanged on January 2, 2024, and it is not a berth, anchorage, wait, port-call, or accuracy claim.

## Why these two issues are the comparison window

The [December 2023 List of CFR Sections Affected (LSA)](https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf) is the monthly cumulative index through December 29, 2023. The [January 2024 LSA](https://www.govinfo.gov/content/pkg/LSA-2024-01/pdf/LSA-2024-01.pdf) is the monthly cumulative index through January 31, 2024. The HarborLens study date, January 2, 2024, falls between those two publication dates. This note identifies the URLs. It does not assert what the official PDFs contain, because this change does not store a live download or a live PDF hash.

The module is built to record, when a human later opts in, whether both indexes show the same four Part 110 proposed-rule page citations (`47837`, `89644`, `89646`, `89648`) and how many direct `110.197` tokens appear in the extracted Title 33 span. A match of those citations is an index observation only. It does not mean a proposal became a final amendment.

The official 2023/2024 GPO annual CFR source text and the [Federal Register original-document triage](fr-2023-original-fulltext-evidence-2026-11-09.md) remain separate sources to reconcile. That earlier triage is non-certifying. GPO LSA review is still outstanding.

## How to run the comparison

The tool is not a console script. Ordinary `harborlens` and `harborlens-verify` do not import it. Without `--fetch` the process exits 2 and opens no socket.

~~~bash
python -m pip install -e '.[lsa]'
python -m harborlens.lsa_compare --fetch --out results/lsa-2023-12-versus-2024-01.json
~~~

`--fetch` is the only network opt-in. The code then requests exactly these two URLs:

- `https://www.govinfo.gov/content/pkg/LSA-2023-12/pdf/LSA-2023-12.pdf`
- `https://www.govinfo.gov/content/pkg/LSA-2024-01/pdf/LSA-2024-01.pdf`

A redirect that changes either URL is refused, including a redirect to the other month, another GovInfo path, another host, or `http`. At most three redirects are followed, and only when the target is the same fixed URL. Each response must declare a decimal Content-Length at or below 10 MiB when that header is present, and the body is read with a 10 MiB cap (one extra byte detects overflow). The timeout is 60 seconds. The PDF must start with `%PDF-` and match a pinned SHA-256 and byte length before `pypdf` is called. December 2023 is `c226121a7617f1b4578a0fcf79f58d4735696e0405c5522615699bdb5bab037d` (554882 bytes, 117 pages). January 2024 is `5ce3c08a45ed6853643a105690d332cbf9813400d4da391de794ef1237305348` (516462 bytes, 82 pages). A mismatch exits 2 and writes nothing. `MAX_PDF_PAGES` is 299. pypdf's `page_tree_maximum_entries` is set to 299 so a larger page tree fails before it is fully flattened. `page_tree_maximum_page_entries` counts copied page-dictionary keys, not pages, and is set to 1024 (the pinned December PDF needs 586). Title 33 text starts at the Title 33 header, includes text on the Title 34 page only before that header, and stops there. The 500,000-character ceiling is applied while that span is accumulated. `pypdf` is imported only on that path. Install it with the `lsa` extra (`pypdf>=6.21.4,<7`). The opener passes an empty proxy map, so `HTTPS_PROXY` is not used. Redirects 301, 302, 303, 307, and 308 are accepted only when the next URL is exactly the requested GovInfo PDF and the method stays GET. That request is built here, so Python 3.10 and 3.12 follow the same rule. `http_error_308` is registered on both. There is no wall-clock timeout around pypdf parsing; that residual is accepted for this opt-in command. A missing install, a page count above 299, a pin mismatch, or any parser exception exits 2, writes nothing, and prints no traceback.

The report records:

- SHA-256 of each original PDF and of the extracted Title 33 text; digest comparisons use `hmac.compare_digest`
- Title 33 page range and the count of direct `110.197` tokens
- the Part 110 proposed-rule page list, which must be the four citations above or the run fails closed
- `legal_effect_on_study_date=NOT_DETERMINED`
- `rights_status=review_required` on the report and on each document
- `historical_wgs84_geometry_approved=false` and `ais_spatial_join_permitted=false`

Package `0.2.0.dev9` identifies this artifact. The report field `harborlens_version` is that version. The comparison behavior is unchanged from `0.2.0.dev8`; the version string moved with the package. Ordinary AIS `run_id` values also change, because they hash `harborlens_version`. The module is still not a console script and is not imported by `harborlens` or `harborlens-verify`.

The schema is `schemas/v1/govinfo-lsa-dec-jan-comparison.schema.json`, registered in `schemas/README.md`. It is not copied into the wheel. setuptools packages `src/harborlens/schemas/v1/*.json`: the rights register and the three release-gate schemas (`public-summary`, `publication-review`, `release-verification-result`).

No original source PDF, extracted legal text, AIS records, or nautical chart polygons should be committed. Tests use a short synthetic `%PDF-SYNTHETIC` body and an in-memory page reader.

## Current validation evidence and limits

Synthetic tests cover the non-certifying receipt, schema rejection of any approval value, page-reference drift, ambiguous Part 110 lines, missing section bounds, page-count and extracted-text bounds, source-size caps, non-integer Content-Length, PDF signature rejection, fixed-URL and redirect refusal, default and CLI refusal to open a socket, overwrite refusal, and the absence of an AIS import or console script. The removed real-source workflow `.github/workflows/lsa-dec-2023-jan-2024-comparison.yml` stays removed. No official PDF SHA-256 is claimed.

Further source review must examine the official January 2024 Federal Register early dates, amendments published before the window with later effective dates, the December and January LSA pages themselves, and any Coast Guard corrections. Those steps are still open on issue #7.

## Remaining issue #7 gates

1. Execute the source-pinned December/January GovInfo PDF comparison in a verified environment and preserve source hash, page range, and the no-approval result.
2. Independently review original Federal Register effective-date records, including rules published before the search window with later effective dates.
3. Resolve A/B/C geodetic datum ambiguity under 33 CFR 110.1(d) and A East printed-ring topology through Coast Guard exhibits or qualified review.
4. Only after a documented, legally date-valid WGS84 geometry exists, compare historical AIS spatial evidence. Presence of a vessel inside a polygon is not proof of anchoring or waiting.

**NOT FOR NAVIGATION. NO VERIFIED 2024 REGULATORY GEOMETRY OR MARITIME OPERATIONAL CLASSIFICATION.**
