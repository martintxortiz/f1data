"""Build data/circuits.json from open sources.

Usage: python scripts/fetch.py 2025 2026
Each circuit is taken from the first listed season in which it has a completed session
(so `2025 2026` = every 2025 circuit plus circuits that are new in 2026).
Sources: OpenF1 (timing/telemetry), MultiViewer (corners, marshal sectors, rotation, pit loss),
bacinger/f1-circuits (metadata), data/inputs/*.json (hand-transcribed FIA documents)."""
import json, math, os, sys
from datetime import datetime, timedelta, timezone
import numpy as np
from common import (BACINGER, DATA, MULTIVIEWER, OPENF1, SCHEMA_VERSION, get, load_input, outward_label, rotate, slug)

SESSION_PREFERENCE = ['Qualifying', 'Race', 'Sprint Qualifying', 'Sprint Shootout', 'Practice 3', 'Practice 2', 'Practice 1']
# OpenF1 location -> bacinger/f1-circuits location, where they differ
LOCATION_ALIAS = {'miami gardens': 'miami', 'marina bay': 'singapore', 'yas island': 'yas marina', 'yas marina': 'yas marina',
                  'monte carlo': 'monaco', 'kuala lumpur': 'sepang', 'montreal': 'montreal', 'sao paulo': 'sao paulo',
                  'spa francorchamps': 'spa francorchamps'}
DRS_OPEN = 10          # OpenF1 drs >= 10 means flap open
FULL_THROTTLE = 98     # % considered full throttle
CORNER_WINDOW_M = 80   # +/- window around a corner for min speed / gear
LABEL_OFFSET = 500     # corner label offset in track units (as in FastF1's example)


def ts(s):
    return datetime.fromisoformat(s.replace('Z', '+00:00'))


def iso(d):
    return d.isoformat().replace('+00:00', '')


def lap_telemetry(sk, lap):
    """Car data + positions for one lap, distance from integrated speed (FastF1 method)."""
    t0 = ts(lap['date_start']); t1 = t0 + timedelta(seconds=lap['lap_duration'])
    q = f"session_key={sk}&driver_number={lap['driver_number']}&date>={iso(t0 - timedelta(seconds=2))}&date<={iso(t1 + timedelta(seconds=2))}"
    car, loc = get(OPENF1 + 'car_data?' + q), get(OPENF1 + 'location?' + q)
    if len(car) < 50 or len(loc) < 50:
        return None
    car = sorted(car, key=lambda c: c['date']); loc = sorted(loc, key=lambda p: p['date'])
    ct = np.array([(ts(c['date']) - t0).total_seconds() for c in car])
    col = lambda k: np.array([c[k] or 0 for c in car], float)
    sp = col('speed')
    dist = np.concatenate([[0], np.cumsum(sp[1:] / 3.6 * np.diff(ct))]); dist -= np.interp(0, ct, dist)
    m = (ct >= 0) & (ct <= lap['lap_duration'])
    T = dict(t=ct[m], dist=dist[m], speed=sp[m], throttle=col('throttle')[m], brake=col('brake')[m],
             drs=col('drs')[m], gear=col('n_gear')[m], rpm=col('rpm')[m])
    lt = np.array([(ts(p['date']) - t0).total_seconds() for p in loc])
    lx = np.array([p['x'] for p in loc], float); ly = np.array([p['y'] for p in loc], float)
    k = (lt >= -0.3) & (lt <= lap['lap_duration'] + 0.3) & ~((lx == 0) & (ly == 0))
    T.update(pt=lt[k], x=lx[k], y=ly[k])
    T['pdist'] = np.clip(np.interp(T['pt'], T['t'], T['dist']), 0, T['dist'].max())
    T['pspeed'] = np.interp(T['pt'], T['t'], T['speed'])
    return T


def auto_corners(x, y):
    """Fallback when no corner map exists: curvature peaks of the smoothed outline (approximate)."""
    from scipy.signal import find_peaks
    from scipy.ndimage import gaussian_filter1d
    x = x / 10; y = y / 10
    s = np.concatenate([[0], np.cumsum(np.hypot(np.diff(x), np.diff(y)))]); u = np.arange(0, s[-1], 2.0)
    xs = gaussian_filter1d(np.interp(u, s, x), 4, mode='wrap'); ys = gaussian_filter1d(np.interp(u, s, y), 4, mode='wrap')
    dx, dy = np.gradient(xs), np.gradient(ys); ddx, ddy = np.gradient(dx), np.gradient(dy)
    k = gaussian_filter1d((dx * ddy - dy * ddx) / np.power(dx * dx + dy * dy, 1.5) / 2.0, 4, mode='wrap')
    pk, _ = find_peaks(np.abs(k), height=1 / 500, distance=23, prominence=1 / 400)
    return [(xs[i] * 10, ys[i] * 10) for i in pk]


def zones_from_mask(mask, dist, L, min_len=50):
    zones, start = [], None
    for i, m in enumerate(mask):
        if m and start is None: start = i
        if (not m or i == len(mask) - 1) and start is not None:
            end = i if m else i - 1
            if dist[end] - dist[start] > min_len: zones.append([int(dist[start]), int(dist[end])])
            start = None
    if len(zones) >= 2 and zones[0][0] < 60 and zones[-1][1] > L - 60:   # zone crossing the line
        zones = [[zones[-1][0], zones[0][1]]] + zones[1:-1]
    return zones


def build_record(season, sess, race_sess, meeting, overrides):
    sk = sess['session_key']
    laps = sorted([l for l in get(OPENF1 + f'laps?session_key={sk}') if l.get('lap_duration') and l.get('date_start')],
                  key=lambda l: l['lap_duration'])
    if not laps: raise RuntimeError('no timed laps')
    lap = T = None
    for cand in laps[:5]:
        T = lap_telemetry(sk, cand)
        if T is not None: lap = cand; break
    if lap is None: raise RuntimeError('no telemetry for the fastest laps')
    L = float(T['dist'].max())
    cid = slug(sess['circuit_short_name'])
    mv = get(MULTIVIEWER.format(key=sess['circuit_key'], season=season)) or {}
    nearest = lambda x, y: int(np.argmin((T['x'] - x) ** 2 + (T['y'] - y) ** 2))
    # corners: MultiViewer -> FIA override -> curvature fallback
    raw = []   # (number, letter, raw_x, raw_y, label_angle_deg or None)
    ov = next((o for o in overrides if o['circuit_id'] == cid and o['season'] == season), None)
    if mv.get('corners'):
        corners_source = 'multiviewer'
        raw = [(c['number'], c.get('letter') or '', c['trackPosition']['x'], c['trackPosition']['y'], c['angle']) for c in mv['corners']]
    elif ov:
        corners_source = ov['source']
        for c in ov['corners']:
            i = int(np.argmin(np.abs(T['pdist'] - c['distance_m']))); raw.append((c['number'], c['letter'], T['x'][i], T['y'][i], None))
    else:
        corners_source = 'auto_curvature'
        pts = sorted(auto_corners(T['x'], T['y']), key=lambda p: T['pdist'][nearest(*p)])
        raw = [(i + 1, '', x, y, None) for i, (x, y) in enumerate(pts)]
    rot = float(mv.get('rotation', 0)) if mv else 0.0
    if not mv:   # landscape orientation for circuits without a MultiViewer entry
        rot = max(range(0, 180, 5), key=lambda r: np.ptp(rotate(T['x'], T['y'], r)[0]) / np.ptp(rotate(T['x'], T['y'], r)[1]))
    R = lambda x, y: rotate(np.asarray(x, float), np.asarray(y, float), rot)
    PX, PY = R(T['x'], T['y']); P = np.column_stack([PX, PY])
    # sectors: boundary = position sample closest in time to the end of S1 / S2
    s1, s2, s3 = (lap.get(f'duration_sector_{i}') for i in (1, 2, 3))
    bounds = [int(T['pdist'][int(np.abs(T['pt'] - tb).argmin())]) for tb in (s1, (s1 or 0) + (s2 or 0))] if s1 and s2 else [None, None]
    sector_of = lambda d: None if bounds[0] is None else (1 if d < bounds[0] else 2 if d < bounds[1] else 3)
    corners = []
    span = max(np.ptp(PX), np.ptp(PY))
    for n, letter, x, y, ang in raw:
        i = nearest(x, y); d = float(T['pdist'][i])
        if ang is not None:
            ox, oy = rotate(LABEL_OFFSET, 0, ang); lx, ly = R(x + ox, y + oy)
        else:
            lx, ly = outward_label(P, i, span * 0.035)
        w = np.abs(T['dist'] - d) <= CORNER_WINDOW_M
        g = T['gear'][w]; g = g[g > 0]
        px, py = R(x, y)
        corners.append(dict(number=int(n), letter=letter, distance_m=int(round(d)), x=int(round(px)), y=int(round(py)),
                            label_x=int(round(lx)), label_y=int(round(ly)),
                            min_speed_kph=int(T['speed'][w].min()) if w.any() else None,
                            min_gear=int(g.min()) if len(g) else None, sector=sector_of(d)))
    corners.sort(key=lambda c: c['distance_m'])
    def marshal(items):
        out = []
        for c in items or []:
            x, y = c['trackPosition']['x'], c['trackPosition']['y']; px, py = R(x, y)
            out.append(dict(number=int(c['number']), distance_m=int(T['pdist'][nearest(x, y)]), x=int(round(px)), y=int(round(py))))
        return out
    dd = np.diff(T['dist'], prepend=0)
    drivers = {d['driver_number']: d for d in get(OPENF1 + f'drivers?session_key={sk}')}
    code = lambda n: drivers.get(n, {}).get('name_acronym')
    bests = []
    for i in (1, 2, 3):
        c = [l for l in laps if l.get(f'duration_sector_{i}')]
        if c:
            b = min(c, key=lambda l: l[f'duration_sector_{i}'])
            bests.append(dict(sector=i, time_s=b[f'duration_sector_{i}'], driver_code=code(b['driver_number'])))
    fd = drivers.get(lap['driver_number'], {})
    drs_url = OPENF1 + f'car_data?session_key={sk}&driver_number={lap["driver_number"]}'
    aero = [dict(type='drs', season=season, name=f'DRS{k + 1}', start_m=a, end_m=b, end_basis='telemetry',
                 low_grip_start_m=None, activation=None, low_grip_activation=None, source_url=drs_url)
            for k, (a, b) in enumerate(zones_from_mask(T['drs'] >= DRS_OPEN, T['dist'], L))]
    trap = [l['st_speed'] for l in laps if l.get('st_speed')]
    pit = (mv or {}).get('pitLoss') or {}
    rec = dict(
        id=f'{season}-{cid}', season=season, round=None, circuit_id=cid, circuit_name=None,
        event_name=meeting.get('meeting_name'), official_event_name=meeting.get('meeting_official_name'),
        location=meeting.get('location'), country=meeting.get('country_name'), country_code=meeting.get('country_code'),
        latitude_deg=None, longitude_deg=None, opened_year=None, first_gp_year=None, altitude_m=None, official_length_m=None,
        fia_centreline_m=None, lap_length_m=int(round(L)), rotation_deg=rot,
        session_name=sess['session_name'], session_date=sess['date_start'][:10], openf1_session_key=sk,
        corners_source=corners_source,
        mini_sectors=sum(len(lap.get(f'segments_sector_{i}') or []) for i in (1, 2, 3)) or None,
        pit_loss_s=float(pit['normal']) if pit.get('normal') else None, pit_loss_sc_s=float(pit['sc']) if pit.get('sc') else None,
        pit_loss_vsc_s=float(pit['vsc']) if pit.get('vsc') else None,
        race_laps=None, race_winner=None, race_winner_team=None, race_time_s=None,
        race_fastest_lap_driver=None, race_fastest_lap_s=None, race_fastest_lap_number=None,
        fastest_lap=dict(driver_code=fd.get('name_acronym'), driver_name=fd.get('full_name'), team=fd.get('team_name'),
                         team_colour=fd.get('team_colour'), lap_number=lap['lap_number'], lap_time_s=lap['lap_duration'],
                         sector_times_s=[s1, s2, s3], speed_trap_kph=lap.get('st_speed'), intermediate1_kph=lap.get('i1_speed'),
                         intermediate2_kph=lap.get('i2_speed'), top_speed_kph=int(T['speed'].max()), min_speed_kph=int(T['speed'].min()),
                         avg_speed_kph=round(L / lap['lap_duration'] * 3.6, 1),
                         full_throttle_pct=round(float(dd[T['throttle'] >= FULL_THROTTLE].sum() / dd.sum() * 100), 1),
                         braking_pct=round(float(dd[T['brake'] > 0].sum() / dd.sum() * 100), 1),
                         max_gear=int(T['gear'].max()), max_rpm=int(T['rpm'].max()), gear_changes=int((np.diff(T['gear']) != 0).sum())),
        session_best_sectors=bests, session_top_speed_trap_kph=max(trap) if trap else None,
        sector_boundaries_m=bounds,
        track=dict(x=[int(round(v)) for v in PX], y=[int(round(v)) for v in PY], distance_m=[int(round(v)) for v in T['pdist']],
                   speed_kph=[int(round(v)) for v in T['pspeed']]),
        corners=corners, marshal_sectors=marshal(mv.get('marshalSectors')), marshal_lights=marshal(mv.get('marshalLights')),
        aero_zones=aero, energy_limits=None, notes=[])
    if race_sess:
        res = get(OPENF1 + f'session_result?session_key={race_sess["session_key"]}')
        rd = {d['driver_number']: d for d in get(OPENF1 + f'drivers?session_key={race_sess["session_key"]}')}
        w = next((r for r in res if r.get('position') == 1), None)
        if w:
            rec.update(race_laps=w.get('number_of_laps'), race_winner=rd.get(w['driver_number'], {}).get('full_name'),
                       race_winner_team=rd.get(w['driver_number'], {}).get('team_name'),
                       race_time_s=w['duration'] if isinstance(w.get('duration'), (int, float)) else None)
        rl = [l for l in get(OPENF1 + f'laps?session_key={race_sess["session_key"]}') if l.get('lap_duration')]
        if rl:
            f = min(rl, key=lambda l: l['lap_duration'])
            rec.update(race_fastest_lap_driver=rd.get(f['driver_number'], {}).get('name_acronym'),
                       race_fastest_lap_s=f['lap_duration'], race_fastest_lap_number=f['lap_number'])
    return rec


def enrich(rec, locs, geo):
    norm = lambda s: slug(s).replace('-', ' ')
    loc = norm(rec['location']); loc = LOCATION_ALIAS.get(loc, loc)
    m = next((l for l in locs if norm(l['location']) == loc), None)
    if not m: return
    g = geo.get(m['id'], {})
    rec.update(circuit_name=m['name'], latitude_deg=m['lat'], longitude_deg=m['lon'], opened_year=g.get('opened'),
               first_gp_year=g.get('firstgp'), altitude_m=g.get('altitude'), official_length_m=g.get('length'))


def apply_fia_documents(rec, docs):
    """Attach Straight Mode zones and energy limits transcribed from FIA documents (any season) for this circuit."""
    for doc in [d for d in docs if d['circuit_id'] == rec['circuit_id']]:
        rec['fia_centreline_m'] = doc.get('fia_centreline_m') if doc['season'] == rec['season'] or rec['fia_centreline_m'] is None else rec['fia_centreline_m']
        if doc.get('note'): rec['notes'].append(f"{doc['season']} FIA: {doc['note']}")
        if doc.get('energy_limits'): rec['energy_limits'] = dict(season=doc['season'], **doc['energy_limits'])
        seq = rec['corners']; L = rec['lap_length_m']
        def resolve(ref):
            if ref is None: return None
            c = next((c for c in seq if c['number'] == ref['turn'] and c['letter'] == ref.get('letter', '')), None)
            return None if c is None else (c['distance_m'] + ref['offset_m']) % L
        def text(ref):
            if ref is None: return None
            t = f"T{ref['turn']}{ref.get('letter', '')}"; m = ref['offset_m']
            return {'after': f'{m}m after {t}', 'entry': f'{m}m after {t} entry',
                    'exit': (f'{-m}m before {t} exit' if m < 0 else f'{m}m after {t} exit' if m else f'{t} exit')}[ref['ref']]
        for z in doc['straight_mode_zones']:
            a, lg = z['activation'], z.get('low_grip_activation')
            start = resolve(a); ref_c = next((c for c in seq if c['number'] == a['turn']), None)
            end = None
            if start is not None:
                base = max(start, ref_c['distance_m']) if a['ref'] == 'exit' else start
                end = next((c for c in seq if c['distance_m'] > base + 20 and c['number'] != a['turn']), seq[0])['distance_m']
            else:
                rec['notes'].append(f"{doc['season']} Straight Mode {z['name']}: reference turn {text(a)} not in corner data; not placed.")
            rec['aero_zones'].append(dict(type='straight_mode', season=doc['season'], name=z['name'],
                                          start_m=None if start is None else int(start), end_m=end, end_basis='next_turn',
                                          low_grip_start_m=None if resolve(lg) is None else int(resolve(lg)),
                                          activation=text(a), low_grip_activation=text(lg), source_url=doc['circuit_map_url']))


def main(seasons):
    now = datetime.now(timezone.utc)
    overrides, docs = load_input('corner_overrides.json'), load_input('fia_documents.json')
    locs = get(BACINGER + 'f1-locations.json')
    geo = {f['properties']['id']: f['properties'] for f in get(BACINGER + 'f1-circuits.geojson')['features']}
    records, skipped, seen = [], [], set()
    for season in seasons:
        sessions = [s for s in get(OPENF1 + f'sessions?year={season}') if not s.get('is_cancelled')]
        meetings = {m['meeting_key']: m for m in get(OPENF1 + f'meetings?year={season}')}
        order = sorted({s['meeting_key'] for s in sessions}, key=lambda k: meetings.get(k, {}).get('date_start', ''))
        rnd = 0
        for mk in order:
            meeting = meetings.get(mk, {})
            if 'test' in (meeting.get('meeting_name') or '').lower(): continue
            rnd += 1
            ms = [s for s in sessions if s['meeting_key'] == mk]
            cid = slug(ms[0]['circuit_short_name'])
            if cid in seen: continue
            race = next((s for s in ms if s['session_name'] == 'Race' and ts(s['date_end']) < now), None)
            errors, rec = [], None
            for name in SESSION_PREFERENCE:
                s = next((s for s in ms if s['session_name'] == name), None)
                if not s or ts(s['date_end']) > now: continue
                try:
                    rec = build_record(season, s, race, meeting, overrides); break
                except Exception as e:
                    errors.append(f'{name}: {e}')
            if rec is None:
                if errors: skipped.append(dict(season=season, location=meeting.get('location'), reason='; '.join(errors)))
                continue
            rec['round'] = rnd; enrich(rec, locs, geo); apply_fia_documents(rec, docs)
            rec['circuit_name'] = rec['circuit_name'] or meeting.get('circuit_short_name') or rec['location']
            records.append(rec); seen.add(cid)
            print(f"{rec['id']}: {rec['session_name']}, {len(rec['corners'])} corners ({rec['corners_source']}), "
                  f"{sum(z['type'] == 'drs' for z in rec['aero_zones'])} DRS, {sum(z['type'] == 'straight_mode' for z in rec['aero_zones'])} SM", flush=True)
    sources = [
        dict(id='openf1', name='OpenF1 API', url='https://openf1.org', license='MIT (API code); F1 live-timing data', used_for='sessions, laps, sector times, car telemetry, positions, results'),
        dict(id='multiviewer', name='MultiViewer circuit API', url='https://api.multiviewer.app', license='public API (also used by FastF1)', used_for='corners, marshal sectors and lights, rotation, pit loss'),
        dict(id='bacinger', name='bacinger/f1-circuits', url='https://github.com/bacinger/f1-circuits', license='MIT', used_for='circuit name, coordinates, official length, opened/first GP, altitude'),
        dict(id='fia', name='FIA Formula 1 documents and regulations', url='https://www.fia.com/documents/championships/fia-formula-one-world-championship-14', license='FIA public documents', used_for='Straight Mode zones, centreline length, event energy limits, regulations (transcribed in data/inputs)'),
    ]
    out = dict(schema_version=SCHEMA_VERSION, generated_at=now.strftime('%Y-%m-%dT%H:%M:%SZ'), seasons=seasons, sources=sources,
               regulations=load_input('regulations.json'), circuits=records, skipped=skipped)
    with open(os.path.join(DATA, 'circuits.json'), 'w') as f:
        json.dump(out, f, ensure_ascii=False, separators=(',', ':'))
    print(f'{len(records)} circuits, {len(skipped)} skipped -> data/circuits.json')


if __name__ == '__main__':
    main([int(a) for a in sys.argv[1:]] or [2025, 2026])
