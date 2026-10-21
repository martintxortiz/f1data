"""Single source of truth for the normalized tables: column names, types, units, OpenF1 mapping.

Every table is used three ways: Parquet columns, MCAP JSON-schema fields and docs/MCAP_FORMAT.md."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

import pyarrow as pa


@dataclass(frozen=True)
class Col:
    name: str
    type: str  # int | float | str | bool | int_list | float_list
    unit: str = ""
    src: str | None = None  # OpenF1 field (None = derived)
    desc: str = ""
    fn: Callable[[dict], Any] | None = None  # derive value from the raw row


@dataclass(frozen=True)
class Table:
    name: str
    endpoint: str
    topic: str  # MCAP topic; "{driver}" expands per car
    kind: str  # "stream" (one message per row) | "snapshot" (one message holding all rows)
    desc: str
    cols: tuple[Col, ...]
    per_driver: bool = False  # fetched driver by driver (high-rate channels)
    time_src: str | None = "date"  # OpenF1 time field; None for snapshot tables without time
    sort: tuple[str, ...] = field(default=("timestamp_ns",))


_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def ts_ns(s: str | None) -> int | None:
    if not s:
        return None
    dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    return (dt - _EPOCH) // timedelta(microseconds=1) * 1000


def _gap(v: Any) -> tuple[float | None, int | None]:
    """OpenF1 gaps are seconds (number) or strings such as '+1 LAP'."""
    if v is None:
        return None, None
    if isinstance(v, (int, float)):
        return float(v), None
    s = str(v).strip().upper()
    if "LAP" in s:
        try:
            return None, int(s.lstrip("+").split()[0])
        except ValueError:
            return None, None
    try:
        return float(s.lstrip("+")), None
    except ValueError:
        return None, None


def _as_list(v: Any) -> list:
    return v if isinstance(v, list) else ([] if v is None else [v])


TIME = Col("timestamp_ns", "int", "ns", None, "Event time, UTC, nanoseconds since Unix epoch")
DRV = Col("driver_number", "int", "", "driver_number", "Car number")

TABLES: tuple[Table, ...] = (
    Table("telemetry", "car_data", "/car/{driver}/telemetry", "stream", "Car channels at native rate (~3.7 Hz)", (
        TIME, DRV,
        Col("speed_kph", "float", "km/h", "speed", "Speed"),
        Col("rpm", "int", "rpm", "rpm", "Engine speed"),
        Col("gear", "int", "", "n_gear", "Gear (0 = neutral)"),
        Col("throttle_pct", "float", "%", "throttle", "Throttle pedal"),
        Col("brake_pct", "float", "%", "brake", "Brake pedal (0 or 100 in the public feed)"),
        Col("drs", "int", "", "drs", "Raw DRS status code (null from 2026: DRS removed, active aero not published)"),
    ), per_driver=True),
    Table("position", "location", "/car/{driver}/position", "stream", "Car position at native rate (~3.7 Hz)", (
        TIME, DRV,
        Col("x", "float", "track units (≈0.1 m)", "x", "X in the F1 timing frame"),
        Col("y", "float", "track units (≈0.1 m)", "y", "Y in the F1 timing frame"),
        Col("z", "float", "track units (≈0.1 m)", "z", "Z (elevation) in the F1 timing frame"),
    ), per_driver=True),
    Table("laps", "laps", "/timing/laps", "stream", "One message per completed lap (time = lap start)", (
        TIME, DRV,
        Col("lap_number", "int", "", "lap_number", "Lap number"),
        Col("lap_time_s", "float", "s", "lap_duration", "Lap time"),
        Col("sector_1_s", "float", "s", "duration_sector_1", "Sector 1 time"),
        Col("sector_2_s", "float", "s", "duration_sector_2", "Sector 2 time"),
        Col("sector_3_s", "float", "s", "duration_sector_3", "Sector 3 time"),
        Col("intermediate_1_kph", "float", "km/h", "i1_speed", "Speed at intermediate 1"),
        Col("intermediate_2_kph", "float", "km/h", "i2_speed", "Speed at intermediate 2"),
        Col("speed_trap_kph", "float", "km/h", "st_speed", "Speed-trap speed"),
        Col("is_pit_out_lap", "bool", "", "is_pit_out_lap", "Lap started from the pit exit"),
        Col("segments_sector_1", "int_list", "", "segments_sector_1", "Mini-sector status codes, sector 1"),
        Col("segments_sector_2", "int_list", "", "segments_sector_2", "Mini-sector status codes, sector 2"),
        Col("segments_sector_3", "int_list", "", "segments_sector_3", "Mini-sector status codes, sector 3"),
    ), time_src="date_start"),
    Table("intervals", "intervals", "/timing/intervals", "stream", "Gaps (race/sprint only, ~4 s cadence)", (
        TIME, DRV,
        Col("gap_to_leader_s", "float", "s", None, "Gap to leader (null when lapped)", lambda r: _gap(r.get("gap_to_leader"))[0]),
        Col("gap_to_leader_laps", "int", "laps", None, "Laps behind leader when lapped", lambda r: _gap(r.get("gap_to_leader"))[1]),
        Col("interval_s", "float", "s", None, "Gap to car ahead", lambda r: _gap(r.get("interval"))[0]),
        Col("interval_laps", "int", "laps", None, "Laps behind car ahead when lapped", lambda r: _gap(r.get("interval"))[1]),
    )),
    Table("positions", "position", "/timing/positions", "stream", "Classification position changes", (
        TIME, DRV, Col("position", "int", "", "position", "Running position"),
    )),
    Table("overtakes", "overtakes", "/timing/overtakes", "stream", "Overtakes (race/sprint)", (
        TIME,
        Col("overtaking_driver_number", "int", "", "overtaking_driver_number", "Car that overtook"),
        Col("overtaken_driver_number", "int", "", "overtaken_driver_number", "Car that was overtaken"),
        Col("position", "int", "", "position", "Position gained"),
    )),
    Table("pit", "pit", "/pit", "stream", "Pit stops", (
        TIME, DRV,
        Col("lap_number", "int", "", "lap_number", "Lap of the stop"),
        Col("pit_duration_s", "float", "s", "pit_duration", "Pit lane time as published by OpenF1"),
        Col("lane_duration_s", "float", "s", "lane_duration", "Pit lane entry-to-exit time"),
        Col("stop_duration_s", "float", "s", "stop_duration", "Stationary time"),
    )),
    Table("race_control", "race_control", "/race_control", "stream", "Race control messages and flags", (
        TIME,
        Col("category", "str", "", "category", "Flag, SafetyCar, Drs, CarEvent, Other, ..."),
        Col("flag", "str", "", "flag", "GREEN, YELLOW, DOUBLE YELLOW, RED, BLUE, CHEQUERED, CLEAR, ..."),
        Col("scope", "str", "", "scope", "Track, Sector or Driver"),
        Col("sector", "int", "", "sector", "Marshal sector, when scope is Sector"),
        Col("lap_number", "int", "", "lap_number", "Leader's lap"),
        Col("driver_number", "int", "", "driver_number", "Driver concerned, if any"),
        Col("qualifying_phase", "int", "", "qualifying_phase", "Q1/Q2/Q3 phase (qualifying only)"),
        Col("message", "str", "", "message", "Message text"),
    )),
    Table("weather", "weather", "/weather", "stream", "Weather station (~1/min)", (
        TIME,
        Col("air_temperature_c", "float", "°C", "air_temperature", "Air temperature"),
        Col("track_temperature_c", "float", "°C", "track_temperature", "Track temperature"),
        Col("humidity_pct", "float", "%", "humidity", "Relative humidity"),
        Col("pressure_mbar", "float", "mbar", "pressure", "Air pressure"),
        Col("rainfall", "int", "", "rainfall", "Rain indicator (0 = none)"),
        Col("wind_direction_deg", "int", "deg", "wind_direction", "Wind direction"),
        Col("wind_speed_mps", "float", "m/s", "wind_speed", "Wind speed"),
    )),
    Table("team_radio", "team_radio", "/team_radio", "stream", "Team radio clips (URL to audio)", (
        TIME, DRV, Col("recording_url", "str", "", "recording_url", "MP3 URL"),
    )),
    Table("drivers", "drivers", "/drivers", "snapshot", "Entry list", (
        DRV,
        Col("code", "str", "", "name_acronym", "Three-letter code"),
        Col("full_name", "str", "", "full_name", "Full name"),
        Col("first_name", "str", "", "first_name", "First name"),
        Col("last_name", "str", "", "last_name", "Last name"),
        Col("broadcast_name", "str", "", "broadcast_name", "Name on TV graphics"),
        Col("team_name", "str", "", "team_name", "Team"),
        Col("team_colour", "str", "hex RGB", "team_colour", "Team colour without '#'"),
        Col("country_code", "str", "", "country_code", "Nationality code"),
        Col("headshot_url", "str", "", "headshot_url", "Photo URL"),
    ), time_src=None, sort=("driver_number",)),
    Table("stints", "stints", "/stints", "snapshot", "Tyre stints", (
        DRV,
        Col("stint_number", "int", "", "stint_number", "Stint number"),
        Col("lap_start", "int", "", "lap_start", "First lap of the stint"),
        Col("lap_end", "int", "", "lap_end", "Last lap of the stint"),
        Col("compound", "str", "", "compound", "SOFT, MEDIUM, HARD, INTERMEDIATE, WET"),
        Col("tyre_age_at_start_laps", "int", "laps", "tyre_age_at_start", "Tyre age when fitted"),
    ), time_src=None, sort=("driver_number", "stint_number")),
    Table("session_result", "session_result", "/results/session", "snapshot", "Final classification", (
        Col("position", "int", "", "position", "Final position"), DRV,
        Col("number_of_laps", "int", "laps", "number_of_laps", "Laps completed"),
        Col("points", "float", "", "points", "Points scored"),
        Col("dnf", "bool", "", "dnf", "Did not finish"),
        Col("dns", "bool", "", "dns", "Did not start"),
        Col("dsq", "bool", "", "dsq", "Disqualified"),
        Col("durations_s", "float_list", "s", None, "Race time, or best lap per qualifying phase (Q1, Q2, Q3)",
            lambda r: [None if x is None else float(x) for x in _as_list(r.get("duration"))]),
        Col("gaps_to_leader_s", "float_list", "s", None, "Gap to leader (per qualifying phase); null when lapped",
            lambda r: [_gap(x)[0] for x in _as_list(r.get("gap_to_leader"))]),
        Col("gap_to_leader_laps", "int", "laps", None, "Laps behind the winner (race)",
            lambda r: next((_gap(x)[1] for x in _as_list(r.get("gap_to_leader")) if _gap(x)[1] is not None), None)),
    ), time_src=None, sort=("position",)),
    Table("starting_grid", "starting_grid", "/results/starting_grid", "snapshot", "Starting grid", (
        Col("position", "int", "", "position", "Grid slot"), DRV,
        Col("qualifying_lap_time_s", "float", "s", "lap_duration", "Qualifying lap time"),
    ), time_src=None, sort=("position",)),
    Table("championship_drivers", "championship_drivers", "/championship/drivers", "snapshot", "Drivers' standings after the session", (
        DRV,
        Col("position_start", "int", "", "position_start", "Position before the session"),
        Col("position_current", "int", "", "position_current", "Position after the session"),
        Col("points_start", "float", "", "points_start", "Points before"),
        Col("points_current", "float", "", "points_current", "Points after"),
    ), time_src=None, sort=("position_current",)),
    Table("championship_teams", "championship_teams", "/championship/teams", "snapshot", "Constructors' standings after the session", (
        Col("team_name", "str", "", "team_name", "Team"),
        Col("position_start", "int", "", "position_start", "Position before the session"),
        Col("position_current", "int", "", "position_current", "Position after the session"),
        Col("points_start", "float", "", "points_start", "Points before"),
        Col("points_current", "float", "", "points_current", "Points after"),
    ), time_src=None, sort=("position_current",)),
)
BY_NAME = {t.name: t for t in TABLES}

_ARROW = {"int": pa.int64(), "float": pa.float64(), "str": pa.string(), "bool": pa.bool_(),
          "int_list": pa.list_(pa.int64()), "float_list": pa.list_(pa.float64())}
_CAST: dict[str, Callable[[Any], Any]] = {"int": int, "float": float, "str": str, "bool": bool}


def _value(col: Col, row: dict, table: Table) -> Any:
    if col.name == "timestamp_ns":
        return ts_ns(row.get(table.time_src)) if table.time_src else None
    v = col.fn(row) if col.fn else row.get(col.src)
    if v is None or col.type.endswith("_list"):
        return v
    try:
        return _CAST[col.type](v)
    except (TypeError, ValueError):
        return None


def arrow_schema(table: Table) -> pa.Schema:
    return pa.schema([pa.field(c.name, _ARROW[c.type]) for c in table.cols])


def normalize(table: Table, rows: list[dict]) -> pa.Table:
    """Raw OpenF1 rows -> typed Arrow table, sorted; rows are kept exactly as published (no dedup, no resampling)."""
    data = {c.name: [_value(c, r, table) for r in rows] for c in table.cols}
    t = pa.table(data, schema=arrow_schema(table))
    keys = [k for k in table.sort if k in t.column_names]
    if keys and t.num_rows:
        t = t.sort_by([(k, "ascending") for k in keys])
    return t


def json_schema(table: Table) -> dict:
    jt = {"int": "integer", "float": "number", "str": "string", "bool": "boolean"}
    def prop(c: Col) -> dict:
        if c.type.endswith("_list"):
            p: dict = {"type": "array", "items": {"type": [jt[c.type.split("_")[0]], "null"]}}
        else:
            p = {"type": jt[c.type] if c.name == "timestamp_ns" else [jt[c.type], "null"]}
        p["description"] = c.desc + (f" [{c.unit}]" if c.unit else "")
        return p
    props = {c.name: prop(c) for c in table.cols}
    if table.kind == "snapshot":
        return {"title": f"f1.{table.name}", "type": "object", "description": table.desc,
                "properties": {"timestamp_ns": prop(TIME), "rows": {"type": "array", "items": {"type": "object", "properties": props}}}}
    return {"title": f"f1.{table.name}", "type": "object", "description": table.desc, "properties": props}
