"""Discover sessions, fetch raw data, normalize, write MCAP + Parquet, verify."""
from __future__ import annotations

import json
import math
import os
import shutil
import time
import unicodedata
from datetime import datetime, timedelta, timezone
from typing import Any

import pyarrow as pa
import pyarrow.parquet as pq
from mcap.reader import make_reader

from . import __version__
from .mcap_out import write_session
from .openf1 import RawCache, fetch
from .tables import TABLES, normalize, ts_ns

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.environ.get("F1PIPE_CACHE", os.path.join(ROOT, ".cache", "openf1"))
OUT_DIR = os.environ.get("F1PIPE_OUT", os.path.join(os.path.dirname(ROOT), "f1data-out"))
CIRCUITS_JSON = os.path.join(ROOT, "data", "circuits.json")
READY_AFTER = timedelta(hours=3)  # OpenF1 needs some time after a session to finalize historical data
SESSION_SLUG = {"Practice 1": "fp1", "Practice 2": "fp2", "Practice 3": "fp3", "Sprint Qualifying": "sprint_qualifying",
                "Sprint Shootout": "sprint_qualifying", "Sprint": "sprint", "Qualifying": "qualifying", "Race": "race"}
NOT_PUBLISHED = ["active aero state (Straight Mode / wing positions)", "ERS / battery state of charge, deployment and harvesting",
                 "tyre temperatures and pressures", "steering angle", "lateral/longitudinal acceleration"]


def slug(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return "-".join("".join(c if c.isalnum() else " " for c in s).split())


def season_sessions(season: int) -> list[dict]:
    """All completed, non-cancelled sessions of Grand Prix weekends, with round numbers and output paths."""
    now = datetime.now(timezone.utc)
    meetings = sorted(fetch("meetings", {"year": season}), key=lambda m: m["date_start"])
    sessions = fetch("sessions", {"year": season})
    out, rnd = [], 0
    for m in meetings:
        ms = [s for s in sessions if s["meeting_key"] == m["meeting_key"] and not s.get("is_cancelled")]
        if "test" in (m.get("meeting_name") or "").lower() or not ms:
            continue
        rnd += 1
        gp = f"{rnd:02d}_{slug(m['country_name'])}"
        for s in sorted(ms, key=lambda s: s["date_start"]):
            end = datetime.fromisoformat(s["date_end"])
            out.append(dict(session=s, meeting=m, round=rnd, gp=gp, slug=SESSION_SLUG.get(s["session_name"], slug(s["session_name"])),
                            ready=end + READY_AFTER < now, tag=f"data-{season}-r{rnd:02d}-{slug(m['country_name'])}"))
    return out


def session_paths(item: dict) -> dict[str, str]:
    d = os.path.join(OUT_DIR, str(item["session"]["year"]), item["gp"])
    return {"dir": d, "mcap": os.path.join(d, f"{item['slug']}.mcap"), "parquet": os.path.join(d, item["slug"]),
            "manifest": os.path.join(d, f"{item['slug']}.json")}


def is_done(item: dict) -> bool:
    p = session_paths(item)
    if not (os.path.exists(p["manifest"]) and os.path.exists(p["mcap"])):
        return False
    with open(p["manifest"]) as f:
        m = json.load(f)
    return m.get("pipeline_version") == __version__ and m.get("verify", {}).get("ok", False)


def fetch_raw(sk: int, cache: RawCache) -> tuple[dict[str, list[dict]], dict[str, int]]:
    """Raw rows per table (per-driver endpoints concatenated) and raw row counts."""
    drivers = cache.get(sk, "drivers", "drivers", {"session_key": sk})
    numbers = sorted({d["driver_number"] for d in drivers})
    raw: dict[str, list[dict]] = {}
    for tb in TABLES:
        if tb.per_driver:
            rows: list[dict] = []
            for n in numbers:
                rows.extend(cache.get(sk, f"{tb.endpoint}__{n}", tb.endpoint, {"session_key": sk, "driver_number": n}))
            raw[tb.name] = rows
        else:
            raw[tb.name] = drivers if tb.name == "drivers" else cache.get(sk, tb.endpoint, tb.endpoint, {"session_key": sk})
    return raw, {k: len(v) for k, v in raw.items()}


def track_static(session: dict) -> dict | None:
    """Static circuit data from data/circuits.json, converted back to the raw timing frame."""
    if not os.path.exists(CIRCUITS_JSON):
        return None
    with open(CIRCUITS_JSON) as f:
        data = json.load(f)
    c = next((c for c in data["circuits"] if c["circuit_id"] == slug(session["circuit_short_name"])), None)
    if c is None:
        return None
    a = math.radians(-c["rotation_deg"]); ca, sa = math.cos(a), math.sin(a)
    un = lambda x, y: (round(x * ca - y * sa), round(x * sa + y * ca))
    xs, ys = zip(*(un(x, y) for x, y in zip(c["track"]["x"], c["track"]["y"])))
    corners = []
    for k in c["corners"]:
        x, y = un(k["x"], k["y"])
        corners.append({"number": k["number"], "letter": k["letter"], "distance_m": k["distance_m"], "x": x, "y": y,
                        "sector": k["sector"], "source": c["corners_source"]})
    return {"circuit_record_id": c["id"], "outline": {"x": list(xs), "y": list(ys), "distance_m": c["track"]["distance_m"],
            "source_session_key": c["openf1_session_key"]}, "corners": corners,
            "aero_zones": c["aero_zones"], "energy_limits": c["energy_limits"]}


def find_gaps(tables: dict[str, pa.Table], raw_counts: dict[str, int], season: int) -> list[dict]:
    gaps = [{"kind": "not_in_public_feed", "item": x} for x in NOT_PUBLISHED]
    for tb in TABLES:
        if raw_counts.get(tb.name, 0) == 0:
            gaps.append({"kind": "no_data", "table": tb.name, "endpoint": tb.endpoint})
    t = tables.get("telemetry")
    if t is not None and t.num_rows and t.column("drs").null_count == t.num_rows:
        gaps.append({"kind": "all_null", "table": "telemetry", "field": "drs",
                     "note": "DRS abolished in 2026; active aero state not published" if season >= 2026 else "no DRS data"})
    laps = tables.get("laps")
    if laps is not None and laps.num_rows:
        n = laps.column("timestamp_ns").null_count
        if n:
            gaps.append({"kind": "rows_without_time", "table": "laps", "count": n, "note": "laps without date_start are in Parquet but not in MCAP"})
    p = tables.get("position")
    if p is not None and p.num_rows:
        import pyarrow.compute as pc
        zeros = pc.sum(pc.and_(pc.equal(p.column("x"), 0), pc.equal(p.column("y"), 0))).as_py() or 0
        if zeros:
            gaps.append({"kind": "placeholder_values", "table": "position", "count": zeros, "note": "x=y=0 samples (car not located), kept as published"})
    return gaps


def verify(path: str, tables: dict[str, pa.Table]) -> dict:
    """Re-open the MCAP, compare per-topic counts with the normalized tables, report time ranges."""
    with open(path, "rb") as f:
        summary = make_reader(f).get_summary()
    stats = summary.statistics
    topics = {ch.topic: stats.channel_message_counts.get(cid, 0) for cid, ch in summary.channels.items()}
    expected: dict[str, int] = {}
    for tb in TABLES:
        t = tables.get(tb.name)
        if t is None or not t.num_rows:
            continue
        if tb.kind == "snapshot":
            expected[tb.topic] = 1
        elif tb.per_driver:
            ts = t.column("timestamp_ns").to_pylist(); dn = t.column("driver_number").to_pylist()
            for d, x in zip(dn, ts):
                if x is not None:
                    k = tb.topic.format(driver=d); expected[k] = expected.get(k, 0) + 1
        else:
            expected[tb.topic] = t.num_rows - t.column("timestamp_ns").null_count
    if tables.get("position") is not None:
        expected["/scene/cars"] = tables["position"].num_rows
    mismatches = {k: {"expected": v, "mcap": topics.get(k, 0)} for k, v in expected.items() if topics.get(k, 0) != v}
    return {"ok": not mismatches, "mismatches": mismatches, "message_count": stats.message_count,
            "start_ns": stats.message_start_time, "end_ns": stats.message_end_time, "topics": topics}


def process(item: dict, cache: RawCache, log=print) -> dict:
    s, m = item["session"], item["meeting"]
    sk = s["session_key"]; p = session_paths(item)
    t_start = time.time()
    raw, raw_counts = fetch_raw(sk, cache)
    tables = {tb.name: normalize(tb, raw[tb.name]) for tb in TABLES}
    del raw
    os.makedirs(p["dir"], exist_ok=True)
    shutil.rmtree(p["parquet"], ignore_errors=True); os.makedirs(p["parquet"])
    for name, t in tables.items():
        if t.num_rows:
            pq.write_table(t, os.path.join(p["parquet"], f"{name}.parquet"), compression="zstd")
    track = track_static(s)
    gaps = find_gaps(tables, raw_counts, s["year"])
    if track is None:
        gaps.append({"kind": "no_static_track", "note": "circuit not in data/circuits.json"})
    info = {"season": s["year"], "round": item["round"], "meeting_key": m["meeting_key"], "session_key": sk,
            "event_name": m.get("meeting_name"), "official_event_name": m.get("meeting_official_name"),
            "country": m.get("country_name"), "location": m.get("location"), "circuit_short_name": s.get("circuit_short_name"),
            "circuit_key": s.get("circuit_key"), "session_name": s["session_name"], "session_type": s.get("session_type"),
            "date_start_ns": ts_ns(s["date_start"]), "date_end_ns": ts_ns(s["date_end"]), "gmt_offset": s.get("gmt_offset"),
            "pipeline_version": __version__, "source": "OpenF1 (api.openf1.org/v1)", "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    tmp = p["mcap"] + ".tmp"
    counts = write_session(tmp, info, tables, track, gaps)
    os.replace(tmp, p["mcap"])
    check = verify(p["mcap"], tables)
    manifest = {"pipeline_version": __version__, "info": info, "raw_rows": raw_counts,
                "normalized_rows": {k: v.num_rows for k, v in tables.items()},
                "drivers": len(set(tables["drivers"].column("driver_number").to_pylist())) if tables["drivers"].num_rows else 0,
                "mcap_bytes": os.path.getsize(p["mcap"]),
                "parquet_bytes": sum(os.path.getsize(os.path.join(p["parquet"], x)) for x in os.listdir(p["parquet"])),
                "gaps": gaps, "verify": check, "seconds": round(time.time() - t_start, 1)}
    with open(p["manifest"], "w") as f:
        json.dump(manifest, f, indent=1)
    log(f"{item['gp']}/{item['slug']} (session {sk}): {check['message_count']} msgs, "
        f"{manifest['mcap_bytes'] / 1e6:.1f} MB mcap, verify {'OK' if check['ok'] else 'FAILED'}, {manifest['seconds']} s")
    return manifest


def update(season: int, session_key: int | None = None, force: bool = False, log=print, rounds: list[int] | None = None) -> list[dict]:
    cache = RawCache(CACHE_DIR)
    done = []
    for item in season_sessions(season):
        sk = item["session"]["session_key"]
        if (session_key is not None and sk != session_key) or (rounds and item["round"] not in rounds):
            continue
        if not item["ready"]:
            log(f"skip {item['gp']}/{item['slug']}: not finished / not yet final"); continue
        if not force and session_key is None and is_done(item):
            continue
        try:
            done.append(process(item, cache, log))
        except Exception as e:  # keep going; the session is retried on the next run
            log(f"ERROR {item['gp']}/{item['slug']} (session {sk}): {e}")
    return done
