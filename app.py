"""
Launch26 — The Relic Ring Protocol
Interplanetary Routing Simulator Backend
IEEE CS Chapter, University of Kelaniya
"""

import json
import math
import heapq
import time
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory
from flask import send_file
import os

app = Flask(__name__, static_folder='.')

# ─── Load Universe Config ──────────────────────────────────────────────────────
CONFIG_PATH = os.path.join(os.path.dirname(__file__), 'universe-config.json')

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

# ─── Global State ─────────────────────────────────────────────────────────────
universe = load_config()
meta     = universe['universe_metadata']
planets  = {p['id']: p for p in universe['nodes']}

dead_planets = set()
dead_links   = set()

# ─── Constants ────────────────────────────────────────────────────────────────
C     = meta['speed_of_light_kms']          # 300,000 km/s
S     = meta['coordinate_scale_unit_km']     # 100,000 km/grid-unit
L_MAX = meta['max_void_hop_distance_km']     # 50,000,000 km
F     = meta['fiber_speed_fraction']         # 0.67
DT    = meta['tower_processing_delay_ms']    # 7 ms

# ─── Geometry ─────────────────────────────────────────────────────────────────

def void_distance(p1, p2):
    """Vacuum distance between two planet atmospheres (km)."""
    dx = p2['x'] - p1['x']
    dy = p2['y'] - p1['y']
    center_km = math.sqrt(dx**2 + dy**2) * S
    L = center_km - (p1['radius_km'] + p1['atmosphere_thickness_km']) \
                  - (p2['radius_km'] + p2['atmosphere_thickness_km'])
    return max(0.0, L)

def tower_angle_deg(planet, tower_idx):
    """Clockwise angle from positive y-axis for tower i."""
    N = planet['active_towers']
    return (360.0 / N) * tower_idx

def tower_position(planet, tower_idx):
    """(x, y) of a tower in grid units."""
    angle_deg = tower_angle_deg(planet, tower_idx)
    angle_rad = math.radians(angle_deg)
    r_grid = planet['radius_km'] / S
    tx = planet['x'] + r_grid * math.sin(angle_rad)
    ty = planet['y'] + r_grid * math.cos(angle_rad)
    return (tx, ty)

def closest_tower(planet, direction_planet):
    """Index of the tower on `planet` that faces `direction_planet`."""
    N = planet['active_towers']
    dx = direction_planet['x'] - planet['x']
    dy = direction_planet['y'] - planet['y']
    # atan2(x, y) → clockwise angle from positive y-axis
    angle_deg = math.degrees(math.atan2(dx, dy))
    if angle_deg < 0:
        angle_deg += 360.0
    spacing = 360.0 / N
    idx = round(angle_deg / spacing) % N
    return idx

def ring_segments(entry, exit_t, N):
    """Minimum arc segments between two tower indices."""
    if entry == exit_t:
        return 0
    cw  = (exit_t - entry) % N
    ccw = (entry - exit_t) % N
    return min(cw, ccw)

# ─── Latency Formulas ─────────────────────────────────────────────────────────

def tv(p1, p2, L):
    """Void travel time (seconds)."""
    h1, n1 = p1['atmosphere_thickness_km'], p1['refraction_index']
    h2, n2 = p2['atmosphere_thickness_km'], p2['refraction_index']
    return ((h1 * n1) + (h2 * n2) + L) / C

def tp(planet, from_planet, to_planet):
    """
    Internal crust transit time (seconds).
    from_planet: planet we arrived FROM (entry tower direction).
    to_planet:   planet we're sending TO (exit tower direction).
    Returns dict with breakdown.
    """
    N = planet['active_towers']
    r = planet['radius_km']

    entry_idx = closest_tower(planet, from_planet) if from_planet else 0
    exit_idx  = closest_tower(planet, to_planet)   if to_planet  else 0

    s = ring_segments(entry_idx, exit_idx, N)
    m = (s + 1) if s > 0 else 1

    arc_km     = (2 * math.pi * r * s) / N
    fiber_time = arc_km / (F * C)          # seconds
    tower_time = m * (DT / 1000.0)         # seconds

    total = fiber_time + tower_time
    return {
        'entry_tower': entry_idx,
        'exit_tower':  exit_idx,
        'segments':    s,
        'towers_hit':  m,
        'arc_km':      arc_km,
        'fiber_s':     fiber_time,
        'tower_s':     tower_time,
        'total_s':     total,
    }

# ─── Base-N Encoding ──────────────────────────────────────────────────────────

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def to_base(n, base):
    if n == 0:
        return "0"
    result = []
    while n > 0:
        result.append(DIGITS[n % base])
        n //= base
    return ''.join(reversed(result))

def from_base(s, base):
    result = 0
    for ch in s.upper():
        result = result * base + DIGITS.index(ch)
    return result

def encode_message(text, target_base):
    return [to_base(ord(ch), target_base) for ch in text]

def decode_message(encoded, source_base):
    return ''.join(chr(from_base(v, source_base)) for v in encoded)

# ─── Graph Builder ────────────────────────────────────────────────────────────

def build_edges():
    """Build list of (p1_id, p2_id, L, Tv) for all feasible pairs."""
    plist = list(planets.values())
    edges = []
    for i in range(len(plist)):
        for j in range(i+1, len(plist)):
            p1, p2 = plist[i], plist[j]
            L = void_distance(p1, p2)
            if L <= L_MAX:
                t_v = tv(p1, p2, L)
                edges.append((p1['id'], p2['id'], L, t_v))
    return edges

def build_graph(edges):
    """Adjacency list respecting current dead planets/links."""
    graph = {pid: [] for pid in planets}
    for p1id, p2id, L, t_v in edges:
        if p1id in dead_planets or p2id in dead_planets:
            continue
        link_key = frozenset([p1id, p2id])
        if link_key in dead_links:
            continue
        graph[p1id].append((p2id, L, t_v))
        graph[p2id].append((p1id, L, t_v))
    return graph

ALL_EDGES = build_edges()

# ─── Dijkstra ────────────────────────────────────────────────────────────────

def dijkstra(source, destination):
    """
    Find lowest-latency path. Returns (total_latency, path_list, hop_details).
    """
    graph = build_graph(ALL_EDGES)

    if source in dead_planets or destination in dead_planets:
        return None, [], []

    # dist[node] = (total_latency, path, prev_planet)
    dist = {pid: float('inf') for pid in planets}
    dist[source] = 0

    # (latency, planet_id, path, prev_planet)
    pq = [(0.0, source, [source], None)]
    visited = set()
    prev_map = {}  # pid → prev_pid

    while pq:
        lat, cur, path, prev = heapq.heappop(pq)
        if cur in visited:
            continue
        visited.add(cur)
        prev_map[cur] = prev

        if cur == destination:
            return lat, path, prev_map

        cur_planet = planets[cur]

        for nbr_id, L, t_v in graph[cur]:
            if nbr_id in visited:
                continue
            nbr_planet = planets[nbr_id]

            # Tp at current planet (exiting toward nbr)
            tp_info = tp(cur_planet, planets[prev] if prev else None, nbr_planet)

            # Tp at nbr planet (arriving from cur) — will be added when we expand nbr
            # But we need to account for Tp at source when first leaving
            hop_latency = tp_info['total_s'] + t_v

            new_lat = lat + hop_latency
            if new_lat < dist[nbr_id]:
                dist[nbr_id] = new_lat
                heapq.heappush(pq, (new_lat, nbr_id, path + [nbr_id], cur))

    return None, [], {}

# ─── Full Transmission ────────────────────────────────────────────────────────

def full_transmission(source, destination, message):
    """
    Simulate full message transmission.
    Returns detailed hop-by-hop breakdown.
    """
    total_lat, path, _ = dijkstra(source, destination)

    if not path:
        return {
            'status': 'UNDELIVERABLE',
            'reason': 'No valid path between planets (void distance exceeds limit or node is dead)',
            'path': [],
            'hops': [],
            'log': [],
            'total_latency': 0,
        }

    log = []
    hops = []
    now = time.time()
    cumulative = 0.0

    def ts():
        from datetime import timezone
        return datetime.fromtimestamp(now + cumulative, tz=timezone.utc).strftime('%H:%M:%S.%f')[:-3]

    log.append({'time': ts(), 'type': 'info',
                'msg': f'Message created on <b>{source}</b>'})
    log.append({'time': ts(), 'type': 'info',
                'msg': f'Original payload: <code>{message[:40]}{"..." if len(message)>40 else ""}</code>'})

    # ASCII values
    ascii_vals = [ord(c) for c in message]
    current_encoded = message  # starts as plain text internally

    total_void_km   = 0.0
    total_fiber_s   = 0.0
    total_atm_s     = 0.0
    total_tower_s   = 0.0
    total_latency_s = 0.0

    for hop_idx in range(len(path) - 1):
        p1_id = path[hop_idx]
        p2_id = path[hop_idx + 1]
        p1    = planets[p1_id]
        p2    = planets[p2_id]
        prev_id = path[hop_idx - 1] if hop_idx > 0 else None

        # ── Encoding at p1 → encode to p2's codex ──
        target_base = p2['codex']
        encoded_vals = encode_message(message, target_base)
        encoded_str  = ' '.join(encoded_vals[:6]) + (' ...' if len(encoded_vals) > 6 else '')

        log.append({'time': ts(), 'type': 'encode',
                    'msg': f'Converted payload to <b>Base {target_base}</b> for <b>{p2_id}</b>'})

        # ── Internal transit at p1 ──
        tp_info = tp(p1,
                     planets[prev_id] if prev_id else None,
                     p2)
        cumulative += tp_info['total_s']
        total_fiber_s  += tp_info['fiber_s']
        total_tower_s  += tp_info['tower_s']
        total_latency_s += tp_info['total_s']

        log.append({'time': ts(), 'type': 'send',
                    'msg': f'Sent from <b>{p1_id} T{tp_info["exit_tower"]}</b> via laser'})

        # ── Void hop ──
        L   = void_distance(p1, p2)
        t_v = tv(p1, p2, L)
        atm_s = ((p1['atmosphere_thickness_km'] * p1['refraction_index']) +
                  (p2['atmosphere_thickness_km'] * p2['refraction_index'])) / C
        vac_s = L / C
        cumulative += t_v
        total_void_km   += L
        total_atm_s     += atm_s
        total_latency_s += t_v

        # Entry tower at p2
        entry_at_p2 = closest_tower(p2, p1)

        log.append({'time': ts(), 'type': 'receive',
                    'msg': f'Received at <b>{p2_id} T{entry_at_p2}</b>'})
        log.append({'time': ts(), 'type': 'decode',
                    'msg': f'Decoded Base {target_base} → ASCII internally'})

        # If last hop, also add arrival tp at destination
        if hop_idx == len(path) - 2:
            # Tp at destination (entry to final delivery)
            next_p = None  # no further planet, same tower
            tp_dest = tp(p2, p1, None)
            # At final destination, entry == exit if no further routing
            # Actually entry_tower used for Tp_dest
            cumulative      += tp_dest['tower_s']  # just processing delay at arrival tower
            total_tower_s   += tp_dest['tower_s']
            total_latency_s += tp_dest['tower_s']

        hops.append({
            'hop':          hop_idx + 1,
            'from_planet':  p1_id,
            'to_planet':    p2_id,
            'from_codex':   p1['codex'],
            'to_codex':     p2['codex'],
            'send_tower':   tp_info['exit_tower'],
            'recv_tower':   entry_at_p2,
            'void_km':      round(L, 2),
            'void_au':      round(L / 1.496e8, 4),
            'fiber_s':      round(tp_info['fiber_s'], 6),
            'atm_s':        round(atm_s, 6),
            'tower_s':      round(tp_info['tower_s'], 6),
            'void_s':       round(vac_s, 6),
            'total_s':      round(tp_info['total_s'] + t_v, 6),
            'encoded':      encoded_str,
            'status':       'Success',
        })

    log.append({'time': ts(), 'type': 'success',
                'msg': f'Message delivered successfully to <b>{destination}</b>'})

    return {
        'status':        'DELIVERED',
        'path':          path,
        'hops':          hops,
        'log':           log,
        'total_latency': round(total_latency_s, 6),
        'total_hops':    len(path) - 1,
        'total_void_km': round(total_void_km, 2),
        'fiber_s':       round(total_fiber_s, 6),
        'atm_s':         round(total_atm_s, 6),
        'tower_s':       round(total_tower_s, 6),
    }

# ─── API Routes ───────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/api/universe')
def api_universe():
    """Return full universe state including edge list and tower positions."""
    planet_list = []
    for pid, p in planets.items():
        N = p['active_towers']
        towers = []
        for i in range(N):
            tx, ty = tower_position(p, i)
            towers.append({'idx': i, 'x': tx, 'y': ty,
                           'angle': tower_angle_deg(p, i)})
        planet_list.append({
            **p,
            'dead':   pid in dead_planets,
            'towers': towers,
        })

    edge_list = []
    for p1id, p2id, L, t_v in ALL_EDGES:
        link_key = frozenset([p1id, p2id])
        is_dead  = (p1id in dead_planets or p2id in dead_planets or
                    link_key in dead_links)
        edge_list.append({
            'from': p1id, 'to': p2id,
            'void_km': round(L, 2),
            'void_au': round(L / 1.496e8, 4),
            'tv_s':    round(t_v, 4),
            'dead':    is_dead,
            'over_limit': False,  # already filtered by build_edges
        })

    # Also report over-limit edges (for display)
    plist = list(planets.values())
    for i in range(len(plist)):
        for j in range(i+1, len(plist)):
            p1, p2 = plist[i], plist[j]
            L = void_distance(p1, p2)
            if L > L_MAX:
                edge_list.append({
                    'from': p1['id'], 'to': p2['id'],
                    'void_km': round(L, 2),
                    'void_au': round(L / 1.496e8, 4),
                    'tv_s':    None,
                    'dead':    True,
                    'over_limit': True,
                })

    return jsonify({
        'planets':  planet_list,
        'edges':    edge_list,
        'meta':     meta,
        'dead_planets': list(dead_planets),
        'dead_links':   [list(lk) for lk in dead_links],
    })

@app.route('/api/route', methods=['POST'])
def api_route():
    """Find fastest route between two planets."""
    data = request.json
    src  = data.get('source')
    dst  = data.get('destination')

    if src not in planets or dst not in planets:
        return jsonify({'error': 'Unknown planet'}), 400
    if src == dst:
        return jsonify({'error': 'Source and destination are the same'}), 400

    lat, path, _ = dijkstra(src, dst)
    if not path:
        return jsonify({'status': 'UNDELIVERABLE', 'path': [], 'latency': None})

    return jsonify({'status': 'ROUTE_FOUND', 'path': path,
                    'latency': round(lat, 6)})

@app.route('/api/send', methods=['POST'])
def api_send():
    """Full transmission simulation."""
    data    = request.json
    src     = data.get('source')
    dst     = data.get('destination')
    message = data.get('message', 'Hello, Universe!')

    if src not in planets or dst not in planets:
        return jsonify({'error': 'Unknown planet'}), 400
    if src == dst:
        return jsonify({'error': 'Source and destination are the same'}), 400

    result = full_transmission(src, dst, message)
    return jsonify(result)

@app.route('/api/kill_planet', methods=['POST'])
def api_kill_planet():
    pid = request.json.get('planet')
    if pid in planets:
        dead_planets.add(pid)
    return jsonify({'dead_planets': list(dead_planets),
                    'dead_links':   [list(lk) for lk in dead_links]})

@app.route('/api/kill_link', methods=['POST'])
def api_kill_link():
    p1 = request.json.get('planet1')
    p2 = request.json.get('planet2')
    if p1 in planets and p2 in planets:
        dead_links.add(frozenset([p1, p2]))
    return jsonify({'dead_planets': list(dead_planets),
                    'dead_links':   [list(lk) for lk in dead_links]})

@app.route('/api/restore', methods=['POST'])
def api_restore():
    dead_planets.clear()
    dead_links.clear()
    return jsonify({'status': 'restored'})

@app.route('/api/encode', methods=['POST'])
def api_encode():
    """Encode a message into a specific base."""
    data    = request.json
    message = data.get('message', '')
    base    = int(data.get('base', 10))
    encoded = encode_message(message, base)
    return jsonify({'encoded': encoded, 'base': base})

if __name__ == '__main__':
    print("Zeta-26 Relic Ring Protocol -- Server starting...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
