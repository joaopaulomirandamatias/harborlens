"""Command-line interface for a historical, non-operational AIS research tool."""
import argparse
import json
from pathlib import Path
from harborlens.ais import BBOX_HOUSTON, run
from harborlens.cli_usage import add_debug_argument, add_version_argument, report_domain_error
from harborlens.io_safe import AISInputError
from harborlens.segmentation import add_threshold_arguments, params_from_args

def main():
    p = argparse.ArgumentParser(
        description=(
            "HarborLens pre-alpha AIS research tool. NOT FOR NAVIGATION. "
            "Writes unvalidated low-speed stationary candidates. A candidate is not "
            "a berth, anchorage, wait, port call, or emissions claim."
        ),
        epilog=(
            "example:\n"
            "  harborlens --input tests/fixtures/synthetic_ais.csv --out results\n"
            "  harborlens-verify --manifest results/manifest.json\n"
            "\n"
            "Related commands: harborlens-verify, harborlens-multiday, harborlens-evaluate.\n"
            "Run each with --help. This tool does not provide a map or HTTP API.\n"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    add_version_argument(p)
    p.add_argument("--input", required=True, help="local AIS CSV to read (required)")
    p.add_argument("--out", default="results", help="output directory (default: results)")
    p.add_argument(
        "--bbox", type=float, nargs=4, default=BBOX_HOUSTON, metavar=("W", "S", "E", "N"),
        help="bounding box, west south east north in WGS84 degrees "
             "(default: -95.7 29.1 -94.2 30.1, Houston–Galveston)",
    )
    p.add_argument("--max-rows", type=int, default=None,
                   help="optional cap on input rows (default: no cap)")
    p.add_argument("--source-url", default=None, help="Unverified user-declared dataset URL")
    p.add_argument("--window-start", default=None,
                   help="Window start: YYYY-MM-DDTHH:MM:SSZ or ±HH:MM, 0-6 fraction digits; "
                        "default: verified acquisition sidecar")
    p.add_argument("--window-end", default=None,
                   help="Window end: YYYY-MM-DDTHH:MM:SSZ or ±HH:MM, 0-6 fraction digits; "
                        "default: verified acquisition sidecar")
    add_debug_argument(p)
    add_threshold_arguments(p)
    a = p.parse_args()
    try:
        result = run(Path(a.input), Path(a.out), tuple(a.bbox), a.max_rows, a.source_url,
                     a.window_start, a.window_end, params_from_args(a))
    except AISInputError as exc:
        report_domain_error(p, exc, a.debug)
    print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()
