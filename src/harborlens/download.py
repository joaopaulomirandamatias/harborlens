"""Optional download of official nationwide daily NOAA archives; opt-in only."""
import argparse
import hashlib
from datetime import date
from pathlib import Path
from urllib.request import Request,urlopen

def main():
    p=argparse.ArgumentParser(description="Experimental NOAA AIS daily downloader")
    p.add_argument("--date",required=True,help="YYYY-MM-DD")
    p.add_argument("--directory",default="data")
    p.add_argument("--max-mib",type=int,default=1024)
    a=p.parse_args()
    d=date.fromisoformat(a.date)
    if not (2019<=d.year<=2026):
        p.error("Check available NOAA vintage first")
    name=f"ais-{d.isoformat()}.csv.zst"
    url=f"https://noaaocm.blob.core.windows.net/ais/csv2/csv{d.year}/{name}"
    target=Path(a.directory)/name
    target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists():
        p.error("Refusing to overwrite existing file")
    limit=a.max_mib*1024*1024
    size=0
    digest=hashlib.sha256()
    temp=target.with_suffix(target.suffix+".partial")
    try:
        with urlopen(Request(url,headers={"User-Agent":"HarborLens-research-POC/0.1"}),timeout=60) as response:
            if int(response.headers.get("Content-Length","0"))>limit:
                raise ValueError("Exceeded maximum file size")
            with temp.open("wb") as output:
                while chunk:=response.read(1024*1024):
                    size+=len(chunk)
                    if size>limit:
                        raise ValueError("Exceeded download limit")
                    output.write(chunk)
                    digest.update(chunk)
        temp.replace(target)
    except Exception:
        temp.unlink(missing_ok=True)
        raise
    print("Source:",url,"Bytes:",size,"SHA256:",digest.hexdigest())

if __name__=="__main__":
    main()
