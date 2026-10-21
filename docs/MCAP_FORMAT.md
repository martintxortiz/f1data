# Session data format (MCAP + Parquet), version 1.0

`python -m f1pipe` turns every session of a season (FP1-3, sprint qualifying, sprint, qualifying, race) into:

```
f1data-out/<season>/<RR>_<country>/<session>.mcap        # replay file (Foxglove)
f1data-out/<season>/<RR>_<country>/<session>/<table>.parquet  # same data, one tidy table per file
f1data-out/<season>/<RR>_<country>/<session>.json        # manifest: source row counts, sizes, gaps, verification
```

`<session>` is one of `fp1 fp2 fp3 sprint_qualifying sprint qualifying race`. Rounds are numbered by date over the season's Grand Prix weekends (testing excluded).

## Conventions

- Source: [OpenF1](https://openf1.org) historical API. Rows are kept exactly as published: native timestamps, no resampling, no interpolation, no dedup.
- Field names are `snake_case` with a unit suffix (`_s`, `_kph`, `_pct`, `_c`, `_m`, `_ns` ...), as in `data/circuits.json`. Missing values are `null`.
- Every message and every Parquet row has `timestamp_ns`: event time, UTC, integer nanoseconds since the Unix epoch (OpenF1 times have microsecond precision). MCAP `log_time` = `publish_time` = `timestamp_ns`.
- MCAP: `jsonschema` schemas, `json` messages, zstd chunks, messages written in time order. A message is exactly the Parquet row (snapshot topics: `{"timestamp_ns", "rows": [...]}`).
- Positions (`x`, `y`, `z`) are in the OpenF1 timing frame, units of about 0.1 m. `/track/*` use the same frame, so they overlay directly. The 3D scene (`/scene/*`, frame `track`) is the same frame scaled to metres (x 0.1).
- Snapshot topics are stamped at session start (`/drivers`, `/results/starting_grid`) or session end (stints, results, standings).

## Measured resolution (2026)

| channel | topic | typical interval |
|---|---|---|
| speed, rpm, gear, throttle, brake | `/car/<NUM>/telemetry` | ~0.24 s median (0.16-0.40 s), ~3.7-4 Hz |
| x, y, z | `/car/<NUM>/position` | ~0.24 s median, ~3.7-4 Hz |
| gaps / intervals (race, sprint) | `/timing/intervals` | ~4 s per car |
| laps, sectors, mini-sectors, speed traps | `/timing/laps` | per lap |
| classification changes | `/timing/positions` | on change |
| weather | `/weather` | 60 s |
| race control, pit, overtakes, radio | event topics | per event |

There is no free, login-free source with higher resolution for 2026: the F1 live-timing archive (used by FastF1) requires an F1 account since October 2026, and F1 stopped publishing active aero and ERS / battery data in the 2026 public feed.

## Static topics (one message at session start)

| topic | schema | content |
|---|---|---|
| `/session/info` | `f1.session_info` | season, round, meeting/session keys, event and session names, country, location, circuit, `date_start_ns`, `date_end_ns`, `gmt_offset`, pipeline version, source, generation time |
| `/track/outline` | `f1.track_outline` | reference lap `x[]`, `y[]` (timing frame) and `distance_m[]` from `data/circuits.json`; `source_session_key` |
| `/track/corners` | `f1.track_corners` | `corners[]`: `number`, `letter`, `distance_m`, `x`, `y`, `sector`, `source` |
| `/track/aero_zones` | `f1.track_aero_zones` | `aero_zones[]` and `energy_limits` exactly as in `data/circuits.json` (see `docs/DATA_FORMAT.md`), `circuit_record_id` |
| `/scene/track` | `foxglove.SceneUpdate` | track line strip and S/F label for the Foxglove 3D panel |

## Replay topic

| topic | schema | content |
|---|---|---|
| `/scene/cars` | `foxglove.SceneUpdate` | one message per position sample: entity `car_<NUM>`, team-coloured sphere + driver code. Samples at x = y = 0 (car not located) delete the entity instead. |

In Foxglove: open the `.mcap`, add a 3D panel (display frame `track`, enable `/scene/track` and `/scene/cars`), and plots on `/car/<NUM>/telemetry.speed_kph` etc.

## Metadata and attachments

- Metadata `session`: the `/session/info` fields as strings.
- Metadata `gaps` and attachment `gaps.json`: what is missing for this session. Kinds: `not_in_public_feed` (never published in 2026: active aero, ERS / battery, tyre temperatures, steering, accelerations), `no_data` (endpoint empty for this session), `all_null` (e.g. `drs` from 2026), `rows_without_time` (kept in Parquet only), `placeholder_values` (x = y = 0 position samples), `no_static_track`.

## Data topics and fields

Generated from `f1pipe/tables.py` with `python -m f1pipe docs`.

<!-- tables:begin -->
### `/car/<NUM>/telemetry` — `f1.telemetry`

Car channels at native rate (~3.7 Hz). OpenF1 `/car_data` (fetched per driver); one message per row. Parquet: `telemetry.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `speed_kph` | float | km/h | speed | Speed |
| `rpm` | int | rpm | rpm | Engine speed |
| `gear` | int |  | n_gear | Gear (0 = neutral) |
| `throttle_pct` | float | % | throttle | Throttle pedal |
| `brake_pct` | float | % | brake | Brake pedal (0 or 100 in the public feed) |
| `drs` | int |  | drs | Raw DRS status code (null from 2026: DRS removed, active aero not published) |

### `/car/<NUM>/position` — `f1.position`

Car position at native rate (~3.7 Hz). OpenF1 `/location` (fetched per driver); one message per row. Parquet: `position.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `x` | float | track units (≈0.1 m) | x | X in the F1 timing frame |
| `y` | float | track units (≈0.1 m) | y | Y in the F1 timing frame |
| `z` | float | track units (≈0.1 m) | z | Z (elevation) in the F1 timing frame |

### `/timing/laps` — `f1.laps`

One message per completed lap (time = lap start). OpenF1 `/laps`; one message per row. Parquet: `laps.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date_start | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `lap_number` | int |  | lap_number | Lap number |
| `lap_time_s` | float | s | lap_duration | Lap time |
| `sector_1_s` | float | s | duration_sector_1 | Sector 1 time |
| `sector_2_s` | float | s | duration_sector_2 | Sector 2 time |
| `sector_3_s` | float | s | duration_sector_3 | Sector 3 time |
| `intermediate_1_kph` | float | km/h | i1_speed | Speed at intermediate 1 |
| `intermediate_2_kph` | float | km/h | i2_speed | Speed at intermediate 2 |
| `speed_trap_kph` | float | km/h | st_speed | Speed-trap speed |
| `is_pit_out_lap` | bool |  | is_pit_out_lap | Lap started from the pit exit |
| `segments_sector_1` | int_list |  | segments_sector_1 | Mini-sector status codes, sector 1 |
| `segments_sector_2` | int_list |  | segments_sector_2 | Mini-sector status codes, sector 2 |
| `segments_sector_3` | int_list |  | segments_sector_3 | Mini-sector status codes, sector 3 |

### `/timing/intervals` — `f1.intervals`

Gaps (race/sprint only, ~4 s cadence). OpenF1 `/intervals`; one message per row. Parquet: `intervals.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `gap_to_leader_s` | float | s | derived | Gap to leader (null when lapped) |
| `gap_to_leader_laps` | int | laps | derived | Laps behind leader when lapped |
| `interval_s` | float | s | derived | Gap to car ahead |
| `interval_laps` | int | laps | derived | Laps behind car ahead when lapped |

### `/timing/positions` — `f1.positions`

Classification position changes. OpenF1 `/position`; one message per row. Parquet: `positions.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `position` | int |  | position | Running position |

### `/timing/overtakes` — `f1.overtakes`

Overtakes (race/sprint). OpenF1 `/overtakes`; one message per row. Parquet: `overtakes.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `overtaking_driver_number` | int |  | overtaking_driver_number | Car that overtook |
| `overtaken_driver_number` | int |  | overtaken_driver_number | Car that was overtaken |
| `position` | int |  | position | Position gained |

### `/pit` — `f1.pit`

Pit stops. OpenF1 `/pit`; one message per row. Parquet: `pit.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `lap_number` | int |  | lap_number | Lap of the stop |
| `pit_duration_s` | float | s | pit_duration | Pit lane time as published by OpenF1 |
| `lane_duration_s` | float | s | lane_duration | Pit lane entry-to-exit time |
| `stop_duration_s` | float | s | stop_duration | Stationary time |

### `/race_control` — `f1.race_control`

Race control messages and flags. OpenF1 `/race_control`; one message per row. Parquet: `race_control.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `category` | str |  | category | Flag, SafetyCar, Drs, CarEvent, Other, ... |
| `flag` | str |  | flag | GREEN, YELLOW, DOUBLE YELLOW, RED, BLUE, CHEQUERED, CLEAR, ... |
| `scope` | str |  | scope | Track, Sector or Driver |
| `sector` | int |  | sector | Marshal sector, when scope is Sector |
| `lap_number` | int |  | lap_number | Leader's lap |
| `driver_number` | int |  | driver_number | Driver concerned, if any |
| `qualifying_phase` | int |  | qualifying_phase | Q1/Q2/Q3 phase (qualifying only) |
| `message` | str |  | message | Message text |

### `/weather` — `f1.weather`

Weather station (~1/min). OpenF1 `/weather`; one message per row. Parquet: `weather.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `air_temperature_c` | float | °C | air_temperature | Air temperature |
| `track_temperature_c` | float | °C | track_temperature | Track temperature |
| `humidity_pct` | float | % | humidity | Relative humidity |
| `pressure_mbar` | float | mbar | pressure | Air pressure |
| `rainfall` | int |  | rainfall | Rain indicator (0 = none) |
| `wind_direction_deg` | int | deg | wind_direction | Wind direction |
| `wind_speed_mps` | float | m/s | wind_speed | Wind speed |

### `/team_radio` — `f1.team_radio`

Team radio clips (URL to audio). OpenF1 `/team_radio`; one message per row. Parquet: `team_radio.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `timestamp_ns` | int | ns | time: date | Event time, UTC, nanoseconds since Unix epoch |
| `driver_number` | int |  | driver_number | Car number |
| `recording_url` | str |  | recording_url | MP3 URL |

### `/drivers` — `f1.drivers`

Entry list. OpenF1 `/drivers`; one message, all rows in `rows`. Parquet: `drivers.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `driver_number` | int |  | driver_number | Car number |
| `code` | str |  | name_acronym | Three-letter code |
| `full_name` | str |  | full_name | Full name |
| `first_name` | str |  | first_name | First name |
| `last_name` | str |  | last_name | Last name |
| `broadcast_name` | str |  | broadcast_name | Name on TV graphics |
| `team_name` | str |  | team_name | Team |
| `team_colour` | str | hex RGB | team_colour | Team colour without '#' |
| `country_code` | str |  | country_code | Nationality code |
| `headshot_url` | str |  | headshot_url | Photo URL |

### `/stints` — `f1.stints`

Tyre stints. OpenF1 `/stints`; one message, all rows in `rows`. Parquet: `stints.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `driver_number` | int |  | driver_number | Car number |
| `stint_number` | int |  | stint_number | Stint number |
| `lap_start` | int |  | lap_start | First lap of the stint |
| `lap_end` | int |  | lap_end | Last lap of the stint |
| `compound` | str |  | compound | SOFT, MEDIUM, HARD, INTERMEDIATE, WET |
| `tyre_age_at_start_laps` | int | laps | tyre_age_at_start | Tyre age when fitted |

### `/results/session` — `f1.session_result`

Final classification. OpenF1 `/session_result`; one message, all rows in `rows`. Parquet: `session_result.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `position` | int |  | position | Final position |
| `driver_number` | int |  | driver_number | Car number |
| `number_of_laps` | int | laps | number_of_laps | Laps completed |
| `points` | float |  | points | Points scored |
| `dnf` | bool |  | dnf | Did not finish |
| `dns` | bool |  | dns | Did not start |
| `dsq` | bool |  | dsq | Disqualified |
| `durations_s` | float_list | s | derived | Race time, or best lap per qualifying phase (Q1, Q2, Q3) |
| `gaps_to_leader_s` | float_list | s | derived | Gap to leader (per qualifying phase); null when lapped |
| `gap_to_leader_laps` | int | laps | derived | Laps behind the winner (race) |

### `/results/starting_grid` — `f1.starting_grid`

Starting grid. OpenF1 `/starting_grid`; one message, all rows in `rows`. Parquet: `starting_grid.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `position` | int |  | position | Grid slot |
| `driver_number` | int |  | driver_number | Car number |
| `qualifying_lap_time_s` | float | s | lap_duration | Qualifying lap time |

### `/championship/drivers` — `f1.championship_drivers`

Drivers' standings after the session. OpenF1 `/championship_drivers`; one message, all rows in `rows`. Parquet: `championship_drivers.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `driver_number` | int |  | driver_number | Car number |
| `position_start` | int |  | position_start | Position before the session |
| `position_current` | int |  | position_current | Position after the session |
| `points_start` | float |  | points_start | Points before |
| `points_current` | float |  | points_current | Points after |

### `/championship/teams` — `f1.championship_teams`

Constructors' standings after the session. OpenF1 `/championship_teams`; one message, all rows in `rows`. Parquet: `championship_teams.parquet`.

| field | type | unit | OpenF1 source | description |
|---|---|---|---|---|
| `team_name` | str |  | team_name | Team |
| `position_start` | int |  | position_start | Position before the session |
| `position_current` | int |  | position_current | Position after the session |
| `points_start` | float |  | points_start | Points before |
| `points_current` | float |  | points_current | Points after |
<!-- tables:end -->
