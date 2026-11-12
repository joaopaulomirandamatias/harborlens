# Source rights register and offline review gate (SPEC-003 / #42)

**Status: initial engineering inventory, not reviewed authorization.** No source is approved for public data redistribution or commercial reuse by this record. The gate only reports a recorded and **version-matched** reviewer assertion; it is not a legal opinion, a cryptographic signature or proof of the upstream license. All default entries remain `review_required`.

## Registry and review

The machine-readable register is [rights-register.json](rights-register.json). Pending sources may have a null `terms_url` when exact applicable licensing terms have not been verified; a generic dataset webpage must not be mislabeled as a legal grant. It deliberately separates the source URL from the terms URL, exact dataset version, proposed uses, rights decision, reviewer, UTC review time, evidence URL, SHA-256 of the reviewed terms snapshot, and attribution. Do not paste private credentials, personal vessel data or raw AIS into this register.

**Before approving an entry**, a named reviewer must verify the exact dataset, date/vintage and hosting route; capture primary-source terms and a SHA-256 snapshot; record specific permitted uses (`research`, `public_aggregates`, `commercial`) and actual restrictions; record attribution and evidence URL; obtain specialist/legal review when commercial reuse is proposed. An archived public webpage is evidence of access, not evidence of every reuse right. Approval is proposed through an independently reviewed PR, not by automatic scraping.

Run the conservative offline audit:

```bash
python -m pip install -e '.[rights]'
python -m harborlens.rights --register docs/data/rights-register.json \
  --source-id noaa_pmel_erddap --dataset-version AIS2024_AIS \
  --purpose public_aggregates
```

`harborlens[rights]` installs `jsonschema`. It is not a core dependency. If that library is missing, the helper exits 2 and the JSON `error` field says to run `pip install 'harborlens[rights]'`. Validation is not skipped.

The helper loads the schema shipped inside the package (`importlib.resources` only; it does not search parent directories). That file is a byte-identical copy of [schemas/v1/source-rights-register.schema.json](../../schemas/v1/source-rights-register.schema.json). Evidence and terms URLs must be `https` and must name a real ASCII host: `https://`, `https:///path`, `https://user@`, `https://user@example.org/terms`, `https://.`, `https:// `, `https://@`, a trailing space or tab on the path, an uppercase `HTTPS` scheme, an IPv6 literal, and a raw IDN hostname do not qualify. Punycode (`xn--`) does qualify. A port must be 1-65535; port 0 and any port above 65535 do not qualify. A backslash, a C0 or C1 control, or DEL anywhere in the URL does not qualify. A repeated object key is a load error, `Rights register has a duplicate key`. A deeply nested document is `Rights register is unreadable`. `reviewed_at_utc` must be an ASCII timestamp `YYYY-MM-DDTHH:MM:SS` with no fraction or 1 to 6 fractional digits, then `Z` or `+00:00`. The parser builds that clock from the captured fields and does not call `fromisoformat`, so Python 3.10 and 3.12 agree. A string that only ends in `Z`, a date-only day, a space separator, a lowercase `t` or `z`, another offset, a non-ASCII digit, and seven fractional digits do not qualify. A shape that is not a real calendar time (31 February, 29 February in a non-leap year, hour 24 or 25) matches the schema pattern and is still denied by the parser. A file that starts with a UTF-8 BOM is not decoded as UTF-8 and is not an approval: the CLI exits 2 and the JSON `error` is `Rights register has a UTF-8 BOM`. YAML is not JSON and is `Rights register is unreadable`. Case or whitespace variants of a status or purpose do not grant. JSON is written to stdout in every case.

| Exit code | When |
| --- | --- |
| 0 | `rights_status` is `reviewed_public_domain_attribution_required` or `reviewed_permitted_with_conditions` |
| 1 | Any other status, including `review_required` and `use_restricted` |
| 2 | The register cannot be loaded, parsed or schema-validated, including a UTF-8 BOM, YAML, or a schema-invalid timestamp or URL. The JSON includes `error` and `rights_status` stays `review_required`, so a broken file is not the same result as a pending source |

Until review, the checked-in register answers `rights_status: review_required` (exit 1). Unknown sources, missing versions, absent metadata, malformed/oversized/duplicate records and missing reviewer evidence also fail closed. A correctly reviewed entry may return `reviewed_public_domain_attribution_required`, `reviewed_permitted_with_conditions` or `use_restricted` for a specifically prohibited purpose. Nothing in this repository auto-approves a source.

## Source-specific preliminary findings (not approvals)

| Source | Preliminary primary-source evidence | Unresolved before approval |
| --- | --- | --- |
| NOAA daily 2024 AIS archive | [NOAA daily archive index](https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2024/index.html); [InPort AIS *Vessel Tracks* 2024](https://www.fisheries.noaa.gov/inport/item/75937) | The InPort record covers derived **tracks**; do not apply its constraints/permissions mechanically to raw daily AIS. Verify exact producer, vintage and redistribution rights. |
| NOAA PMEL ERDDAP AIS2024_AIS | [NOAA PMEL dataset metadata](https://data.pmel.noaa.gov/pmel/erddap/info/AIS2024_AIS/index.htmlTable) explicitly states CC0-1.0 | Confirm terms apply to the exact downloaded subset, independent rights and attribution; record reviewer and terms snapshot. |
| NOAA OceanReports Anchorage Areas | [Official MapServer layer](https://maps.coast.noaa.gov/arcgis/rest/services/OceanReports/DesignatedAnchorageAreas/MapServer/0) | Confirm dataset/service terms and provenance; **current** polygons are not verified January 2024 geofences. |
| USACE Navigation Facilities / USDOT NTAD | [Federal data.gov catalog](https://catalog.data.gov/dataset/docks) lists a U.S. public-domain label | Confirm hosted snapshot and version, cite agency; POINT coordinates are not berth polygons. |
| 33 CFR 110.197 | [eCFR rule](https://www.ecfr.gov/current/title-33/chapter-I/subchapter-I/part-110/section-110.197) and [GPO 2024 collection](https://www.govinfo.gov/app/collection/cfr/2024/title33) | Verify the effective 2024-01-02 timeline via Federal Register/LSA, source datum and polygon topology. |

## Security and compatibility notes

This increment adds an explicit **audit helper**, not automatic promotion of existing acquisition metadata. **No source has been approved.** Optional adapter receipts ([rights-adapter-integration.md](rights-adapter-integration.md)) read this same gate and still default to `review_required`. A receipt is not an approval. Existing CLI outputs stay `review_required` until a reviewer approves a version-matched registry entry. In particular, an independently reviewed data license does not validate vessel events, historical anchorages or navigation suitability.

**NOT FOR NAVIGATION. Not a government endorsement.**
