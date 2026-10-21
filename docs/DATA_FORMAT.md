# Data format (schema 1.0)

All lengths are in **metres**, times in **seconds**, speeds in **km/h**, energy in **MJ** and angles in **degrees**.
Field names use `snake_case` and carry their unit as a suffix (`_m`, `_s`, `_kph`, `_mj`, `_deg`, `_pct`).
`null` means unknown or not published. It never means zero.
Distances along a lap (`*_m` positions) are measured from the timing line in the direction of travel, along the reference lap described below.

| File | Kind | Written by |
|---|---|---|
| `data/circuits.json` | Generated dataset (single source for the app) | `scripts/fetch.py` |
| `app/index.html` | Generated viewer with `circuits.json` inlined | `scripts/render.py` |
| `data/inputs/fia_documents.json` | Hand-transcribed FIA event documents | maintainer |
| `data/inputs/corner_overrides.json` | Official corner positions where no corner map API exists | maintainer |
| `data/inputs/regulations.json` | Summaries of regulation articles | maintainer |

## `data/circuits.json`

### Root

| Field | Type | Nullable | Meaning | Example |
|---|---|---|---|---|
| `schema_version` | string | no | Version of this format | `"1.0"` |
| `generated_at` | string (ISO 8601 UTC) | no | Build time | `"2026-10-21T07:40:00Z"` |
| `seasons` | int[] | no | Seasons requested, in priority order | `[2025, 2026]` |
| `sources` | Source[] | no | Data sources and licences | |
| `regulations` | Regulation[] | no | Copy of `data/inputs/regulations.json` | |
| `circuits` | Circuit[] | no | One entry per circuit (first season with data wins) | |
| `skipped` | Skipped[] | no | Events with no usable session | `[]` |

### Source

| Field | Type | Nullable | Meaning | Example |
|---|---|---|---|---|
| `id` | string | no | Short identifier | `"openf1"` |
| `name` | string | no | Display name | `"OpenF1 API"` |
| `url` | string | no | Homepage | `"https://openf1.org"` |
| `license` | string | no | Licence or terms | `"MIT"` |
| `used_for` | string | no | Which fields come from it | `"sessions, laps, ..."` |

### Regulation

| Field | Type | Nullable | Meaning | Example |
|---|---|---|---|---|
| `season` | int | no | Season the article applies to | `2026` |
| `article` | string | no | Article number(s) | `"C5.2.10"` |
| `document_url` | string | no | Official PDF | `"https://www.fia.com/..."` |
| `summary` | string | no | Short paraphrase. The PDF is authoritative | `"Recharge ≤ 8.5 MJ per lap..."` |

### Skipped

| Field | Type | Nullable | Meaning | Example |
|---|---|---|---|---|
| `season` | int | no | Season | `2026` |
| `location` | string | yes | Event location | `"Madrid"` |
| `reason` | string | no | Why each session failed | `"Qualifying: no timed laps"` |

### Circuit

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `id` | string | | no | `<season>-<circuit_id>`, unique | `"2026-madring"` |
| `season` | int | | no | Season of the session used | `2026` |
| `round` | int | | no | Round number in that season | `14` |
| `circuit_id` | string | | no | Season-independent slug of OpenF1 `circuit_short_name` | `"madring"` |
| `circuit_name` | string | | no | Circuit name (bacinger, else OpenF1) | `"Circuito de Madring"` |
| `event_name` | string | | no | Grand Prix name | `"Spanish Grand Prix"` |
| `official_event_name` | string | | yes | Full official name | `"FORMULA 1 ... 2026"` |
| `location` | string | | no | City or area (OpenF1) | `"Madrid"` |
| `country` | string | | no | Country | `"Spain"` |
| `country_code` | string | | yes | IOC/F1 3-letter code | `"ESP"` |
| `latitude_deg` | number | deg | yes | Latitude | `40.471` |
| `longitude_deg` | number | deg | yes | Longitude | `-3.62` |
| `opened_year` | int | | yes | Year the venue opened | `2026` |
| `first_gp_year` | int | | yes | First F1 Grand Prix | `2026` |
| `altitude_m` | number | m | yes | Altitude above sea level | `646` |
| `official_length_m` | number | m | yes | Length from bacinger/f1-circuits | `5474` |
| `fia_centreline_m` | number | m | yes | Centreline length from the FIA circuit map | `5414` |
| `lap_length_m` | int | m | no | Length of the reference lap (integrated speed). About 1–2% below the centreline | `5319` |
| `rotation_deg` | number | deg | no | Rotation already applied to all `x`/`y` values (MultiViewer, or chosen for landscape orientation) | `60` |
| `session_name` | string | | no | Session the reference lap comes from | `"Qualifying"` |
| `session_date` | string (YYYY-MM-DD) | | no | Session start date (UTC) | `"2026-09-12"` |
| `openf1_session_key` | int | | no | OpenF1 `session_key` | `11365` |
| `corners_source` | enum | | no | `multiviewer`, `fia_circuit_map` (see inputs) or `auto_curvature` (approximate) | `"fia_circuit_map"` |
| `mini_sectors` | int | | yes | Timing mini-sectors on the reference lap | `26` |
| `pit_loss_s` | number | s | yes | Typical pit-stop time loss, green flag | `20.81` |
| `pit_loss_sc_s` | number | s | yes | Pit loss under Safety Car | `13.19` |
| `pit_loss_vsc_s` | number | s | yes | Pit loss under Virtual Safety Car | `15.05` |
| `race_laps` | int | | yes | Laps completed by the race winner | `57` |
| `race_winner` | string | | yes | Winner's full name | `"Lando NORRIS"` |
| `race_winner_team` | string | | yes | Winner's team | `"McLaren"` |
| `race_time_s` | number | s | yes | Winner's race time | `6126.304` |
| `race_fastest_lap_driver` | string | | yes | Three-letter code of the driver who set the race's fastest lap | `"NOR"` |
| `race_fastest_lap_s` | number | s | yes | Race fastest lap time | `82.167` |
| `race_fastest_lap_number` | int | | yes | Lap number of that lap | `43` |
| `fastest_lap` | FastestLap | | no | Reference lap (fastest timed lap of the session) | |
| `session_best_sectors` | BestSector[] | | no | Best time per sector in the session (any driver) | |
| `session_top_speed_trap_kph` | number | km/h | yes | Highest speed-trap reading in the session | `332` |
| `sector_boundaries_m` | [int, int] | m | no | Lap distance of the S1/S2 and S2/S3 boundaries | `[1741, 3120]` |
| `track` | Track | | no | Outline of the reference lap | |
| `corners` | Corner[] | | no | Turns, sorted by `distance_m` | |
| `marshal_sectors` | Marker[] | | no | Marshal sector starts (empty if unknown) | |
| `marshal_lights` | Marker[] | | no | Marshal light panels (empty if unknown) | |
| `aero_zones` | AeroZone[] | | no | DRS and Straight Mode zones, any season | |
| `energy_limits` | EnergyLimits | | yes | Event power-unit limits, where transcribed | |
| `notes` | string[] | | no | Caveats for this circuit | `["2026 FIA: ..."]` |

### FastestLap

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `driver_code` | string | | yes | Three-letter code | `"NOR"` |
| `driver_name` | string | | yes | Full name | `"Lando NORRIS"` |
| `team` | string | | yes | Team | `"McLaren"` |
| `team_colour` | string | hex RGB | yes | Team colour without `#` | `"FF8000"` |
| `lap_number` | int | | no | Lap number within the session | `19` |
| `lap_time_s` | number | s | no | Lap time | `75.096` |
| `sector_times_s` | [number\|null ×3] | s | no | Sector 1–3 times | `[25.961, 16.997, 32.138]` |
| `speed_trap_kph` | number | km/h | yes | Speed trap on this lap | `326` |
| `intermediate1_kph` | number | km/h | yes | Intermediate 1 speed | `288` |
| `intermediate2_kph` | number | km/h | yes | Intermediate 2 speed | `325` |
| `top_speed_kph` | number | km/h | no | Max telemetry speed | `329` |
| `min_speed_kph` | number | km/h | no | Min telemetry speed | `98` |
| `avg_speed_kph` | number | km/h | no | `lap_length_m / lap_time_s` | `249.6` |
| `full_throttle_pct` | number | % of distance | no | Share of the lap at ≥ 98% throttle | `78.8` |
| `braking_pct` | number | % of distance | no | Share of the lap with brake applied | `8.7` |
| `max_gear` | int | | no | Highest gear | `8` |
| `max_rpm` | int | rpm | no | Highest engine speed | `12225` |
| `gear_changes` | int | | no | Number of gear changes | `29` |

### BestSector

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `sector` | int (1–3) | | no | Sector number | `2` |
| `time_s` | number | s | no | Best time | `16.915` |
| `driver_code` | string | | yes | Who set it | `"VER"` |

### Track

Columnar arrays of equal length. Index *i* is one position sample of the reference lap (~3.7 Hz).

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `x` | int[] | track units (≈ 0.1 m), rotated | no | X coordinate | `[-1185, ...]` |
| `y` | int[] | track units (≈ 0.1 m), rotated, y up | no | Y coordinate | `[-1341, ...]` |
| `distance_m` | int[] | m | no | Lap distance at the sample | `[0, 21, ...]` |
| `speed_kph` | int[] | km/h | no | Speed at the sample | `[298, ...]` |

### Corner

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `number` | int | | no | Official turn number | `5` |
| `letter` | string | | no | Suffix for sub-corners, `""` if none | `"A"` |
| `distance_m` | int | m | no | Lap distance of the apex marker | `1508` |
| `x`, `y` | int | track units | no | Position on the track | `1200` |
| `label_x`, `label_y` | int | track units | no | Suggested label position (offset from the track) | `1700` |
| `min_speed_kph` | int | km/h | yes | Minimum speed within ±80 m on the reference lap | `112` |
| `min_gear` | int | | yes | Lowest gear within ±80 m | `3` |
| `sector` | int (1–3) | | yes | Timing sector containing the corner | `1` |

### Marker (marshal sector / light)

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `number` | int | | no | Marker number | `7` |
| `distance_m` | int | m | no | Lap distance | `1912` |
| `x`, `y` | int | track units | no | Position | `-3650` |

### AeroZone

One list covers both DRS (up to 2025) and Straight Mode (2026 on). A zone may come from a different season than the circuit entry; it is then drawn on that entry's outline. If `start_m > end_m`, the zone crosses the start/finish line.

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `type` | enum | | no | `drs` or `straight_mode` | `"straight_mode"` |
| `season` | int | | no | Season the zone applies to | `2026` |
| `name` | string | | no | `DRS1..n`, or the FIA zone name | `"A1"` |
| `start_m` | int | m | yes | Activation point. `null` if the reference turn is not in `corners` | `5257` |
| `end_m` | int | m | yes | End point | `506` |
| `end_basis` | enum | | no | `telemetry` = flap observed closed on the reference lap. `next_turn` = the FIA publishes no end, so this is the next numbered turn (indicative) | `"next_turn"` |
| `low_grip_start_m` | int | m | yes | Low Grip activation point | `5287` |
| `activation` | string | | yes | Activation as published, e.g. `100m after T22`. `null` for DRS | `"100m after T22"` |
| `low_grip_activation` | string | | yes | Low Grip activation as published | `"130m after T22"` |
| `source_url` | string | | no | FIA PDF, or OpenF1 query for telemetry zones | `"https://www.fia.com/..."` |

### EnergyLimits

From the FIA "Power Unit Information" document of one event. `null` fields were not given or were marked TBC.

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `season` | int | | no | Season of the document | `2026` |
| `source_url` | string | | no | FIA PDF | `"https://www.fia.com/..."` |
| `max_recharge_race_mj` | number | MJ/lap | yes | Race, Overtake not active (C5.2.10) | `8.5` |
| `max_recharge_race_overtake_mj` | number | MJ/lap | yes | Race, Overtake active | `9.0` |
| `max_recharge_qualifying_mj` | number | MJ/lap | yes | Qualifying | `7.5` |
| `max_recharge_practice_mj` | number | MJ/lap | yes | Free practice | `9.0` |
| `power_limited_distance_m` | number | m | yes | Power Limited Distance (C5.12.8) | `3206` |
| `power_reduction_rate_kw_per_s` | number | kW/s | yes | Max PU power reduction rate (C5.12.8) | `100` |
| `overtake_detection_m` | number | m | yes | Overtake Detection Line (B7.2.1b.viii) | `5110` |
| `overtake_activation_m` | number | m | yes | Overtake Activation Line (B7.2.1b.ix) | `5160` |
| `overtake_detection_gap_s` | number | s | yes | Detection gap | `1.0` |
| `alt_power_curve_sectors` | string | | yes | Sectors where the C5.2.8iii curve applies, as published | `"T5-T22 (1500-5100 m)"` |

## Input files (`data/inputs/`)

### `fia_documents.json`: array of FiaDocument

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `circuit_id` | string | | no | Matches `Circuit.circuit_id` | `"madring"` |
| `season` | int | | no | Season of the documents | `2026` |
| `circuit_map_url` | string | | no | FIA "Circuit Map" PDF | `"https://www.fia.com/..."` |
| `fia_centreline_m` | int | m | yes | Centreline length printed on the map | `5414` |
| `note` | string | | yes | Free-text caveat copied to `Circuit.notes` | `"FIA map lists no ... (N/A)."` |
| `straight_mode_zones` | object[] | | no | `{name, activation, low_grip_activation}`. Each activation is a TurnRef. `low_grip_activation` may be `null` | |
| `energy_limits` | object | | yes | `EnergyLimits` without `season` | |

**TurnRef** `{turn: int, letter: string, ref: "after" | "entry" | "exit", offset_m: int}` encodes the FIA wording.
`"100m after T22"` → `{turn: 22, letter: "", ref: "after", offset_m: 100}`.
`"40m before T3 exit"` → `{turn: 3, ref: "exit", offset_m: -40}`.
The position is `corner.distance_m + offset_m`. Entry and exit are placed at the corner marker.

### `corner_overrides.json`: array

| Field | Type | Unit | Nullable | Meaning | Example |
|---|---|---|---|---|---|
| `circuit_id`, `season` | string, int | | no | Circuit entry the override applies to | `"madring"`, `2026` |
| `source` | enum | | no | Written to `Circuit.corners_source` | `"fia_circuit_map"` |
| `source_url` | string | | no | Document the turn numbers come from | |
| `method` | string | | no | How distances were obtained | |
| `corners` | object[] | | no | `{number, letter, distance_m}` along the reference lap | `{"number": 5, "letter": "A", "distance_m": 1537}` |

### `regulations.json`

Array of `Regulation` (see above).
