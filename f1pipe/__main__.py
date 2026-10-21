"""CLI: python -m f1pipe {update,status,publish,docs}"""
from __future__ import annotations

import argparse
import sys

from . import pipeline


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="f1pipe", description="OpenF1 -> MCAP/Parquet pipeline")
    sub = ap.add_subparsers(dest="cmd", required=True)
    u = sub.add_parser("update", help="fetch and process new or missing sessions")
    u.add_argument("--season", type=int, required=True)
    u.add_argument("--session", type=int, help="rebuild one session_key")
    u.add_argument("--round", type=int, action="append", help="only this round (repeatable)")
    u.add_argument("--force", action="store_true", help="rebuild even if already done")
    st = sub.add_parser("status", help="per-session coverage table")
    st.add_argument("--season", type=int, required=True)
    pb = sub.add_parser("publish", help="upload outputs as GitHub release assets (one release per GP)")
    pb.add_argument("--season", type=int, required=True)
    pb.add_argument("--repo", default="martintxortiz/f1data")
    sub.add_parser("docs", help="regenerate the table reference in docs/MCAP_FORMAT.md")
    a = ap.parse_args(argv)
    if a.cmd == "update":
        pipeline.update(a.season, a.session, a.force, log=lambda s: print(s, flush=True), rounds=a.round)
    elif a.cmd == "status":
        from .report import status
        print(status(a.season))
    elif a.cmd == "publish":
        from .publish import publish
        publish(a.season, a.repo)
    elif a.cmd == "docs":
        from .report import write_docs
        write_docs()
    return 0


if __name__ == "__main__":
    sys.exit(main())
