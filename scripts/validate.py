"""Validate data/circuits.json against the documented schema (docs/DATA_FORMAT.md).

Usage: python scripts/validate.py [--browser [--screenshot PATH --circuit ID]]
--browser renders app/index.html in headless Chromium (needs `playwright`) and checks every circuit."""
import json, os, sys
from common import DATA, ROOT, SCHEMA_VERSION

I, F, S, B, N = int, (int, float), str, bool, type(None)
# field: (types, nullable)
TOP = dict(schema_version=(S, 0), generated_at=(S, 0), seasons=(list, 0), sources=(list, 0), regulations=(list, 0), circuits=(list, 0), skipped=(list, 0))
SOURCE = dict(id=(S, 0), name=(S, 0), url=(S, 0), license=(S, 0), used_for=(S, 0))
REGULATION = dict(season=(I, 0), article=(S, 0), document_url=(S, 0), summary=(S, 0))
SKIPPED = dict(season=(I, 0), location=(S, 1), reason=(S, 0))
CIRCUIT = dict(id=(S, 0), season=(I, 0), round=(I, 0), circuit_id=(S, 0), circuit_name=(S, 0), event_name=(S, 0), official_event_name=(S, 1),
    location=(S, 0), country=(S, 0), country_code=(S, 1), latitude_deg=(F, 1), longitude_deg=(F, 1), opened_year=(I, 1), first_gp_year=(I, 1),
    altitude_m=(F, 1), official_length_m=(F, 1), fia_centreline_m=(F, 1), lap_length_m=(I, 0), rotation_deg=(F, 0),
    session_name=(S, 0), session_date=(S, 0), openf1_session_key=(I, 0), corners_source=(S, 0), mini_sectors=(I, 1),
    pit_loss_s=(F, 1), pit_loss_sc_s=(F, 1), pit_loss_vsc_s=(F, 1), race_laps=(I, 1), race_winner=(S, 1), race_winner_team=(S, 1),
    race_time_s=(F, 1), race_fastest_lap_driver=(S, 1), race_fastest_lap_s=(F, 1), race_fastest_lap_number=(I, 1),
    fastest_lap=(dict, 0), session_best_sectors=(list, 0), session_top_speed_trap_kph=(F, 1), sector_boundaries_m=(list, 0),
    track=(dict, 0), corners=(list, 0), marshal_sectors=(list, 0), marshal_lights=(list, 0), aero_zones=(list, 0),
    energy_limits=(dict, 1), notes=(list, 0))
FASTEST_LAP = dict(driver_code=(S, 1), driver_name=(S, 1), team=(S, 1), team_colour=(S, 1), lap_number=(I, 0), lap_time_s=(F, 0),
    sector_times_s=(list, 0), speed_trap_kph=(F, 1), intermediate1_kph=(F, 1), intermediate2_kph=(F, 1), top_speed_kph=(F, 0),
    min_speed_kph=(F, 0), avg_speed_kph=(F, 0), full_throttle_pct=(F, 0), braking_pct=(F, 0), max_gear=(I, 0), max_rpm=(I, 0), gear_changes=(I, 0))
BEST_SECTOR = dict(sector=(I, 0), time_s=(F, 0), driver_code=(S, 1))
TRACK = dict(x=(list, 0), y=(list, 0), distance_m=(list, 0), speed_kph=(list, 0))
CORNER = dict(number=(I, 0), letter=(S, 0), distance_m=(I, 0), x=(I, 0), y=(I, 0), label_x=(I, 0), label_y=(I, 0),
    min_speed_kph=(I, 1), min_gear=(I, 1), sector=(I, 1))
MARSHAL = dict(number=(I, 0), distance_m=(I, 0), x=(I, 0), y=(I, 0))
AERO_ZONE = dict(type=(S, 0), season=(I, 0), name=(S, 0), start_m=(I, 1), end_m=(I, 1), end_basis=(S, 0), low_grip_start_m=(I, 1),
    activation=(S, 1), low_grip_activation=(S, 1), source_url=(S, 0))
ENERGY = dict(season=(I, 0), source_url=(S, 0), max_recharge_race_mj=(F, 1), max_recharge_race_overtake_mj=(F, 1),
    max_recharge_qualifying_mj=(F, 1), max_recharge_practice_mj=(F, 1), power_limited_distance_m=(F, 1),
    power_reduction_rate_kw_per_s=(F, 1), overtake_detection_m=(F, 1), overtake_activation_m=(F, 1),
    overtake_detection_gap_s=(F, 1), alt_power_curve_sectors=(S, 1))
ENUMS = {('aero_zone', 'type'): {'drs', 'straight_mode'}, ('aero_zone', 'end_basis'): {'telemetry', 'next_turn'},
         ('circuit', 'corners_source'): {'multiviewer', 'fia_circuit_map', 'auto_curvature'}}
errors = []


def check(obj, spec, where, kind=None):
    if not isinstance(obj, dict):
        errors.append(f'{where}: expected object'); return
    for k in set(obj) - set(spec): errors.append(f'{where}: unexpected field {k}')
    for k, (t, nullable) in spec.items():
        if k not in obj: errors.append(f'{where}: missing {k}'); continue
        val = obj[k]
        if val is None:
            if not nullable: errors.append(f'{where}.{k}: null not allowed')
        elif isinstance(val, bool) or not isinstance(val, t):
            errors.append(f'{where}.{k}: wrong type {type(val).__name__}')
        elif (kind, k) in ENUMS and val not in ENUMS[(kind, k)]:
            errors.append(f'{where}.{k}: invalid value {val!r}')


def main():
    with open(os.path.join(DATA, 'circuits.json')) as f:
        d = json.load(f)
    check(d, TOP, 'root')
    if d.get('schema_version') != SCHEMA_VERSION: errors.append('schema_version mismatch')
    for i, x in enumerate(d['sources']): check(x, SOURCE, f'sources[{i}]')
    for i, x in enumerate(d['regulations']): check(x, REGULATION, f'regulations[{i}]')
    for i, x in enumerate(d['skipped']): check(x, SKIPPED, f'skipped[{i}]')
    ids = [c['id'] for c in d['circuits']]
    if len(ids) != len(set(ids)): errors.append('duplicate circuit ids')
    for c in d['circuits']:
        w = c.get('id', '?'); check(c, CIRCUIT, w, 'circuit')
        check(c['fastest_lap'], FASTEST_LAP, w + '.fastest_lap'); check(c['track'], TRACK, w + '.track')
        if c['energy_limits']: check(c['energy_limits'], ENERGY, w + '.energy_limits')
        for j, x in enumerate(c['session_best_sectors']): check(x, BEST_SECTOR, f'{w}.session_best_sectors[{j}]')
        for j, x in enumerate(c['corners']): check(x, CORNER, f'{w}.corners[{j}]')
        for key in ('marshal_sectors', 'marshal_lights'):
            for j, x in enumerate(c[key]): check(x, MARSHAL, f'{w}.{key}[{j}]')
        for j, x in enumerate(c['aero_zones']): check(x, AERO_ZONE, f'{w}.aero_zones[{j}]', 'aero_zone')
        t = c['track']; n = len(t['x'])
        if n < 100 or any(len(t[k]) != n for k in TRACK): errors.append(f'{w}: track arrays too short or of unequal length')
        if not c['corners']: errors.append(f'{w}: no corners')
        if len(c['sector_boundaries_m']) != 2 or None in c['sector_boundaries_m']: errors.append(f'{w}: missing sector boundaries')
        if len(c['fastest_lap']['sector_times_s']) != 3: errors.append(f'{w}: sector_times_s must have 3 items')
        for z in c['aero_zones']:
            for k in ('start_m', 'end_m', 'low_grip_start_m'):
                if z[k] is not None and not 0 <= z[k] <= c['lap_length_m']: errors.append(f"{w}: {z['name']}.{k} outside lap")
    print(f"{len(d['circuits'])} circuits, {sum(len(c['aero_zones']) for c in d['circuits'])} aero zones, {len(d['skipped'])} skipped")
    if '--browser' in sys.argv: browser(d, sys.argv)
    if errors:
        print('\n'.join(errors[:50])); print(f'FAILED: {len(errors)} errors'); sys.exit(1)
    print('OK')


def browser(d, argv):
    import asyncio
    from playwright.async_api import async_playwright
    shot = argv[argv.index('--screenshot') + 1] if '--screenshot' in argv else None
    cid = argv[argv.index('--circuit') + 1] if '--circuit' in argv else None
    async def run():
        async with async_playwright() as p:
            b = await p.chromium.launch(); pg = await b.new_page(viewport={'width': 1500, 'height': 950})
            js = []; pg.on('pageerror', lambda e: js.append(str(e)))
            pg.on('console', lambda m: m.type == 'error' and js.append(m.text))
            await pg.goto('file://' + os.path.join(ROOT, 'app', 'index.html')); await pg.wait_for_timeout(300)
            for c in d['circuits']:
                await pg.select_option('#sel', str(d['circuits'].index(c))); await pg.wait_for_timeout(20)
                if await pg.eval_on_selector_all('svg .corner', 'e => e.length') != len(c['corners']):
                    errors.append(f"{c['id']}: turn markers not rendered")
            if shot:
                i = next((k for k, c in enumerate(d['circuits']) if c['id'] == cid), 0)
                await pg.select_option('#sel', str(i)); await pg.wait_for_timeout(200); await pg.screenshot(path=shot)
            await b.close()
            errors.extend(f'JS error: {e}' for e in js)
            print(f"browser: rendered {len(d['circuits'])} circuits, {len(js)} JS errors")
    asyncio.run(run())


if __name__ == '__main__':
    main()
