"""Coverage table and docs/MCAP_FORMAT.md generation."""
from __future__ import annotations

import glob
import json
import os
from datetime import datetime, timezone

from .pipeline import OUT_DIR, ROOT
from .tables import TABLES


def _manifests(season: int) -> list[dict]:
    out = []
    for p in sorted(glob.glob(os.path.join(OUT_DIR, str(season), "*", "*.json"))):
        with open(p) as f:
            m = json.load(f)
        m["_path"] = p
        out.append(m)
    return out


def status(season: int) -> str:
    lines = ["| GP | session | key | drivers | telemetry | position | laps | intervals | rc | weather | radio | MCAP MB | verify | missing |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for m in _manifests(season):
        n = m["normalized_rows"]
        missing = ", ".join(g["table"] for g in m["gaps"] if g["kind"] == "no_data")
        gp = os.path.basename(os.path.dirname(m["_path"]))
        lines.append(f"| {gp} | {os.path.basename(m['_path'])[:-5]} | {m['info']['session_key']} | {m['drivers']} | {n['telemetry']} | "
                     f"{n['position']} | {n['laps']} | {n['intervals']} | {n['race_control']} | {n['weather']} | {n['team_radio']} | "
                     f"{m['mcap_bytes'] / 1e6:.1f} | {'OK' if m['verify']['ok'] else 'FAIL'} | {missing} |")
    return "\n".join(lines)


BEGIN, END = "<!-- tables:begin -->", "<!-- tables:end -->"


def tables_markdown() -> str:
    out = []
    for tb in TABLES:
        topic = tb.topic.replace("{driver}", "<NUM>")
        how = "one message per row" if tb.kind == "stream" else "one message, all rows in `rows`"
        out += [f"### `{topic}` — `f1.{tb.name}`", "",
                f"{tb.desc}. OpenF1 `/{tb.endpoint}`{' (fetched per driver)' if tb.per_driver else ''}; {how}. "
                f"Parquet: `{tb.name}.parquet`.", "", "| field | type | unit | OpenF1 source | description |", "|---|---|---|---|---|"]
        for c in tb.cols:
            src = "time: " + tb.time_src if c.name == "timestamp_ns" and tb.time_src else (c.src or "derived")
            out.append(f"| `{c.name}` | {c.type} | {c.unit} | {src} | {c.desc} |")
        out.append("")
    return "\n".join(out)


def write_docs() -> None:
    path = os.path.join(ROOT, "docs", "MCAP_FORMAT.md")
    with open(path) as f:
        s = f.read()
    a, b = s.index(BEGIN) + len(BEGIN), s.index(END)
    with open(path, "w") as f:
        f.write(s[:a] + "\n" + tables_markdown() + s[b:])
    print(f"updated {path}")
