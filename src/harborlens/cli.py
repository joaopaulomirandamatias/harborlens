"""Command-line interface for a historical, non-operational AIS research tool."""
import argparse
import json
from pathlib import Path
from harborlens.ais import BBOX_HOUSTON, run

def main():
    p = argparse.ArgumentParser(description="HarborLens AIS prototype; NOT FOR NAVIGATION")
    p.add_argument("--input", required=True)
    p.add_argument("--out", default="results")
    p.add_argument("--bbox", type=float, nargs=4, default=BBOX_HOUSTON, metavar=("W","S","E","N"))
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--source-url", default=None, help="Unverified user-declared dataset URL")
    p.add_argument("--window-start", default=None,
                   help="Analysis window start (ISO 8601 with Z); default: verified acquisition sidecar")
    p.add_argument("--window-end", default=None,
                   help="Analysis window end (ISO 8601 with Z); default: verified acquisition sidecar")
    a = p.parse_args()
    print(json.dumps(run(Path(a.input),Path(a.out),tuple(a.bbox),a.max_rows,a.source_url,
                         a.window_start,a.window_end),indent=2))

if __name__ == "__main__":
    main()
