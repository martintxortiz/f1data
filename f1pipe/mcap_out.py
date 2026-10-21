"""Write one session to MCAP (JSON-schema encoded messages, zstd chunks)."""
from __future__ import annotations

import heapq
import json
import math
from typing import Any, Iterator

import pyarrow as pa
import pyarrow.compute as pc
from mcap.writer import CompressionType, Writer

from . import __version__
from .tables import TABLES, Table, json_schema

TRACK_SCALE = 0.1  # track units -> metres for the 3D scene

# Minimal JSON schemas for the Foxglove well-known types used (structure follows foxglove schemas).
_VEC3 = {"type": "object", "properties": {k: {"type": "number"} for k in "xyz"}}
_QUAT = {"type": "object", "properties": {k: {"type": "number"} for k in "xyzw"}}
_COLOR = {"type": "object", "properties": {k: {"type": "number"} for k in "rgba"}}
_TIME = {"type": "object", "properties": {"sec": {"type": "integer"}, "nsec": {"type": "integer"}}}
_POSE = {"type": "object", "properties": {"position": _VEC3, "orientation": _QUAT}}
SCENE_UPDATE_SCHEMA = {"title": "foxglove.SceneUpdate", "type": "object", "properties": {
    "deletions": {"type": "array", "items": {"type": "object"}},
    "entities": {"type": "array", "items": {"type": "object", "properties": {
        "timestamp": _TIME, "frame_id": {"type": "string"}, "id": {"type": "string"}, "lifetime": _TIME,
        "frame_locked": {"type": "boolean"}, "metadata": {"type": "array"},
        "spheres": {"type": "array", "items": {"type": "object", "properties": {"pose": _POSE, "size": _VEC3, "color": _COLOR}}},
        "lines": {"type": "array", "items": {"type": "object", "properties": {
            "type": {"type": "integer"}, "pose": _POSE, "thickness": {"type": "number"}, "scale_invariant": {"type": "boolean"},
            "points": {"type": "array", "items": _VEC3}, "color": _COLOR}}},
        "texts": {"type": "array", "items": {"type": "object", "properties": {
            "pose": _POSE, "billboard": {"type": "boolean"}, "font_size": {"type": "number"},
            "scale_invariant": {"type": "boolean"}, "color": _COLOR, "text": {"type": "string"}}}},
        "arrows": {"type": "array"}, "cubes": {"type": "array"}, "cylinders": {"type": "array"},
        "triangles": {"type": "array"}, "models": {"type": "array"}}}}}}
STATIC_SCHEMAS = {
    "f1.session_info": {"title": "f1.session_info", "type": "object", "description": "Session and event metadata"},
    "f1.track_outline": {"title": "f1.track_outline", "type": "object", "description": "Reference-lap outline in the timing frame (same frame as /car/*/position)",
                          "properties": {"timestamp_ns": {"type": "integer"}, "x": {"type": "array"}, "y": {"type": "array"}, "distance_m": {"type": "array"}}},
    "f1.track_corners": {"title": "f1.track_corners", "type": "object", "description": "Turns in the timing frame"},
    "f1.track_aero_zones": {"title": "f1.track_aero_zones", "type": "object", "description": "DRS / Straight Mode zones and event energy limits"},
}

_ID = {"position": {"x": 0, "y": 0, "z": 0}, "orientation": {"x": 0, "y": 0, "z": 0, "w": 1}}


def _t(ns: int) -> dict:
    return {"sec": ns // 1_000_000_000, "nsec": ns % 1_000_000_000}


def _rgb(hex_colour: str | None) -> dict:
    h = (hex_colour or "FFFFFF").lstrip("#")
    try:
        r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    except ValueError:
        r = g = b = 1.0
    return {"r": r, "g": g, "b": b, "a": 1.0}


def _clean(v: Any) -> Any:
    return None if isinstance(v, float) and math.isnan(v) else v


def _rows(table: pa.Table, batch: int = 50_000) -> Iterator[dict]:
    for b in table.to_batches(batch):
        yield from b.to_pylist()


def write_session(path: str, info: dict, tables: dict[str, pa.Table], track: dict | None, gaps: list[dict]) -> dict[str, int]:
    """Write the MCAP file; returns message count per topic."""
    t0, t1 = info["date_start_ns"], info["date_end_ns"]
    counts: dict[str, int] = {}
    with open(path, "wb") as f:
        w = Writer(f, compression=CompressionType.ZSTD, chunk_size=4 * 1024 * 1024)
        w.start(profile="", library=f"f1pipe {__version__}")
        schema_ids: dict[str, int] = {}
        channel_ids: dict[str, int] = {}

        def channel(topic: str, schema_name: str, schema: dict) -> int:
            if schema_name not in schema_ids:
                schema_ids[schema_name] = w.register_schema(schema_name, "jsonschema", json.dumps(schema).encode())
            if topic not in channel_ids:
                channel_ids[topic] = w.register_channel(topic, "json", schema_ids[schema_name])
            return channel_ids[topic]

        def emit(topic: str, schema_name: str, schema: dict, ns: int, msg: dict) -> None:
            cid = channel(topic, schema_name, schema)
            w.add_message(cid, log_time=ns, publish_time=ns, data=json.dumps(msg, separators=(",", ":")).encode())
            counts[topic] = counts.get(topic, 0) + 1

        # static / snapshot messages at session start
        emit("/session/info", "f1.session_info", STATIC_SCHEMAS["f1.session_info"], t0, {"timestamp_ns": t0, **info})
        drivers = {r["driver_number"]: r for r in _rows(tables["drivers"])} if "drivers" in tables else {}
        for tb in TABLES:
            if tb.kind == "snapshot" and tables.get(tb.name) is not None and tables[tb.name].num_rows:
                ns = t0 if tb.name in ("drivers", "starting_grid") else t1
                emit(tb.topic, f"f1.{tb.name}", json_schema(tb), ns, {"timestamp_ns": ns, "rows": [{k: _clean(v) for k, v in r.items()} for r in _rows(tables[tb.name])]})
        if track:
            emit("/track/outline", "f1.track_outline", STATIC_SCHEMAS["f1.track_outline"], t0, {"timestamp_ns": t0, **track["outline"]})
            emit("/track/corners", "f1.track_corners", STATIC_SCHEMAS["f1.track_corners"], t0, {"timestamp_ns": t0, "corners": track["corners"]})
            emit("/track/aero_zones", "f1.track_aero_zones", STATIC_SCHEMAS["f1.track_aero_zones"], t0,
                 {"timestamp_ns": t0, "aero_zones": track["aero_zones"], "energy_limits": track["energy_limits"], "circuit_record_id": track["circuit_record_id"]})
            o = track["outline"]
            pts = [{"x": x * TRACK_SCALE, "y": y * TRACK_SCALE, "z": 0.0} for x, y in zip(o["x"], o["y"])]
            pts.append(pts[0])
            emit("/scene/track", "foxglove.SceneUpdate", SCENE_UPDATE_SCHEMA, t0, {"deletions": [], "entities": [{
                "timestamp": _t(t0), "frame_id": "track", "id": "track", "lifetime": _t(0), "frame_locked": False, "metadata": [],
                "lines": [{"type": 0, "pose": _ID, "thickness": 12.0, "scale_invariant": False, "points": pts, "color": {"r": .35, "g": .35, "b": .4, "a": 1}}],
                "spheres": [], "texts": [{"pose": {"position": {**pts[0], "z": 5.0}, "orientation": _ID["orientation"]}, "billboard": True, "font_size": 14,
                                         "scale_invariant": True, "color": {"r": 1, "g": 1, "b": 1, "a": 1}, "text": "S/F"}],
                "arrows": [], "cubes": [], "cylinders": [], "triangles": [], "models": []}]})

        # time-ordered streams, k-way merged so the file is written in log-time order
        def stream(tb: Table, t: pa.Table, driver: int | None) -> Iterator[tuple[int, str, Table, dict]]:
            topic = tb.topic.format(driver=driver)
            for r in _rows(t):
                if r["timestamp_ns"] is not None:
                    yield r["timestamp_ns"], topic, tb, r

        streams = []
        for tb in TABLES:
            t = tables.get(tb.name)
            if tb.kind != "stream" or t is None or not t.num_rows:
                continue
            if tb.per_driver:
                for d in sorted(set(t.column("driver_number").to_pylist())):
                    streams.append(stream(tb, t.filter(pc.equal(t.column("driver_number"), d)), d))
            else:
                streams.append(stream(tb, t, None))
        for ns, topic, tb, r in heapq.merge(*streams, key=lambda x: x[0]):
            emit(topic, f"f1.{tb.name}", json_schema(tb), ns, {k: _clean(v) for k, v in r.items()})
            if tb.name == "position":
                d = drivers.get(r["driver_number"], {})
                if r["x"] == 0 and r["y"] == 0:  # car not located: hide it instead of drawing it at the origin
                    emit("/scene/cars", "foxglove.SceneUpdate", SCENE_UPDATE_SCHEMA, ns,
                         {"deletions": [{"timestamp": _t(ns), "type": 0, "id": f"car_{r['driver_number']}"}], "entities": []})
                    continue
                p = {"x": r["x"] * TRACK_SCALE, "y": r["y"] * TRACK_SCALE, "z": 0.0}
                emit("/scene/cars", "foxglove.SceneUpdate", SCENE_UPDATE_SCHEMA, ns, {"deletions": [], "entities": [{
                    "timestamp": _t(ns), "frame_id": "track", "id": f"car_{r['driver_number']}", "lifetime": _t(0), "frame_locked": False,
                    "metadata": [], "spheres": [{"pose": {"position": p, "orientation": _ID["orientation"]}, "size": {"x": 30, "y": 30, "z": 30},
                                                 "color": _rgb(d.get("team_colour"))}],
                    "texts": [{"pose": {"position": {**p, "z": 40.0}, "orientation": _ID["orientation"]}, "billboard": True, "font_size": 12,
                               "scale_invariant": True, "color": {"r": 1, "g": 1, "b": 1, "a": 1}, "text": d.get("code") or str(r["driver_number"])}],
                    "lines": [], "arrows": [], "cubes": [], "cylinders": [], "triangles": [], "models": []}]})

        w.add_metadata("session", {k: str(v) for k, v in info.items()})
        w.add_metadata("gaps", {f"gap_{i:02d}": json.dumps(g) for i, g in enumerate(gaps)})
        w.add_attachment(t1, t1, "gaps.json", "application/json", json.dumps(gaps, indent=1).encode())
        w.finish()
    return counts
