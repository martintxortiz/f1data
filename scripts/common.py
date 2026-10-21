"""Shared helpers: cached HTTP GET, geometry, paths."""
import hashlib, json, math, os, time, urllib.error, urllib.request
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.environ.get('F1DATA_CACHE', os.path.join(ROOT, '.cache', 'http'))
DATA = os.path.join(ROOT, 'data')
OPENF1 = 'https://api.openf1.org/v1/'
MULTIVIEWER = 'https://api.multiviewer.app/api/v1/circuits/{key}/{season}'
BACINGER = 'https://raw.githubusercontent.com/bacinger/f1-circuits/master/'
SCHEMA_VERSION = '1.0'


def get(url):
    """GET JSON with an on-disk cache and polite retry. 404 -> []."""
    os.makedirs(CACHE, exist_ok=True)
    fn = os.path.join(CACHE, hashlib.md5(url.encode()).hexdigest() + '.json')
    if os.path.exists(fn):
        with open(fn) as f:
            return json.load(f)
    for attempt in range(8):
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'f1data/1.0'})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read())
            with open(fn, 'w') as f:
                json.dump(data, f)
            time.sleep(0.5)
            return data
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return []
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(5 * (attempt + 1)); continue
            raise
        except OSError:
            time.sleep(3 * (attempt + 1))
    raise RuntimeError('failed: ' + url)


def rotate(x, y, deg):
    """Rotate points by deg (same convention as FastF1's circuit rotation)."""
    a = math.radians(deg); c, s = math.cos(a), math.sin(a)
    return x * c - y * s, x * s + y * c


def slug(s):
    import unicodedata
    s = unicodedata.normalize('NFKD', s or '').encode('ascii', 'ignore').decode().lower()
    return '-'.join(''.join(ch if ch.isalnum() else ' ' for ch in s).split())


def load_input(name):
    with open(os.path.join(DATA, 'inputs', name)) as f:
        return json.load(f)


def outward_label(P, k, off):
    """Label position for track point k: offset `off` along the normal pointing away from the track centroid."""
    a, b = P[(k + 1) % len(P)] - P[k - 1]
    n = np.array([-b, a]) / (math.hypot(a, b) or 1)
    if np.dot(n, P[k] - P.mean(0)) < 0:
        n = -n
    return P[k] + n * off
