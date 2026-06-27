"""
Launch26 ΓÇö The Relic Ring Protocol
Interplanetary Routing Simulator ΓÇö Backend
IEEE CS Chapter, University of Kelaniya
"""

import json, math, heapq, time, os
from datetime import datetime, timezone
from flask import Flask, request, jsonify, send_from_directory

BASE_DIR     = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH  = os.path.join(BASE_DIR, 'universe-config.json')
FRONTEND_DIR = os.path.join(BASE_DIR, '..', 'frontend')

app = Flask(__name__, static_folder=FRONTEND_DIR)

# ΓöÇΓöÇΓöÇ Config ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
def load_config():
    with open(CONFIG_PATH) as f:
        return json.load(f)

universe     = load_config()
meta         = universe['universe_metadata']
planets      = {p['id']: p for p in universe['nodes']}
dead_planets = set()
dead_links   = set()

# ΓöÇΓöÇΓöÇ Universe Constants (from config ΓÇö never hardcoded) ΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇΓöÇ
C     = meta['speed_of_light_kms']           # km/s
S     = meta['coordinate_scale_unit_km']      # km per grid unit
L_MAX = meta['max_void_hop_distance_km']      # km ΓÇö single hop limit
F     = meta['fiber_speed_fraction']          # fraction of c for fiber
DT    = meta['tower_processing_delay_ms']     # ms per tower

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  GEOMETRY
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def void_distance(p1, p2):
    """
    Equation 1 ΓÇö Void (vacuum) distance between two planet atmospheres:
      L = sqrt((x2-x1)^2 + (y2-y1)^2) * S  -  (R1+h1)  -  (R2+h2)
    where S = coordinate_scale_unit_km (100,000 km/grid-unit).
    """
    dx = p2['x'] - p1['x']
    dy = p2['y'] - p1['y']
    center_km = math.sqrt(dx**2 + dy**2) * S
    L = center_km - (p1['radius_km'] + p1['atmosphere_thickness_km']) \
                  - (p2['radius_km'] + p2['atmosphere_thickness_km'])
    return max(0.0, L)

def void_distance_breakdown(p1, p2):
    """Return full breakdown of void distance calculation for display."""
    dx = p2['x'] - p1['x']
    dy = p2['y'] - p1['y']
    grid_dist   = math.sqrt(dx**2 + dy**2)
    center_km   = grid_dist * S
    shell1_km   = p1['radius_km'] + p1['atmosphere_thickness_km']
    shell2_km   = p2['radius_km'] + p2['atmosphere_thickness_km']
    L           = max(0.0, center_km - shell1_km - shell2_km)
    return {
        'dx': dx, 'dy': dy,
        'grid_dist': round(grid_dist, 4),
        'center_km': round(center_km, 2),
        'shell1_km': round(shell1_km, 2),
        'shell2_km': round(shell2_km, 2),
        'L_km':      round(L, 2),
        'feasible':  L <= L_MAX,
        'over_by_km': round(max(0, L - L_MAX), 2),
    }

def tower_angle_deg(planet, tower_idx):
    N = planet['active_towers']
    return (360.0 / N) * tower_idx

def tower_position(planet, tower_idx):
    angle_rad = math.radians(tower_angle_deg(planet, tower_idx))
    r_grid    = planet['radius_km'] / S
    return (planet['x'] + r_grid * math.sin(angle_rad),
            planet['y'] + r_grid * math.cos(angle_rad))

def closest_tower(planet, direction_planet):
    """Tower on `planet` whose angular position is closest to `direction_planet`."""
    N   = planet['active_towers']
    dx  = direction_planet['x'] - planet['x']
    dy  = direction_planet['y'] - planet['y']
    ang = math.degrees(math.atan2(dx, dy))
    if ang < 0: ang += 360.0
    return round(ang / (360.0 / N)) % N

def ring_segments(entry, exit_t, N):
    """Shortest arc (in segments) between two tower indices on the ring."""
    if entry == exit_t: return 0
    return min((exit_t - entry) % N, (entry - exit_t) % N)

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  LATENCY EQUATIONS
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def tv(p1, p2, L):
    """
    Equation 2 ΓÇö Void travel time:
      Tv = [(h1*n1) + (h2*n2) + L] / c
    Atmosphere slows light proportionally to its refraction index.
    """
    return ((p1['atmosphere_thickness_km'] * p1['refraction_index']) +
            (p2['atmosphere_thickness_km'] * p2['refraction_index']) + L) / C

def tv_breakdown(p1, p2, L):
    h1n1 = p1['atmosphere_thickness_km'] * p1['refraction_index']
    h2n2 = p2['atmosphere_thickness_km'] * p2['refraction_index']
    numerator = h1n1 + h2n2 + L
    Tv = numerator / C
    return {
        'h1': p1['atmosphere_thickness_km'], 'n1': p1['refraction_index'],
        'h2': p2['atmosphere_thickness_km'], 'n2': p2['refraction_index'],
        'h1n1': round(h1n1, 4), 'h2n2': round(h2n2, 4),
        'L_km': round(L, 2),
        'numerator_km': round(numerator, 4),
        'C_kms': C,
        'Tv_s': round(Tv, 6),
        'atm_s': round((h1n1 + h2n2) / C, 6),
        'vac_s': round(L / C, 6),
    }

def tp(planet, from_planet, to_planet):
    """
    Equation 3 ΓÇö Internal planet crust transit time:
      Tp = (2*pi*r*s) / (N*f*c)  +  m*dt
    where s = ring segments traversed, m = towers hit, dt = tower_processing_delay.
    """
    N = planet['active_towers']
    r = planet['radius_km']
    entry_idx = closest_tower(planet, from_planet) if from_planet else 0
    exit_idx  = closest_tower(planet, to_planet)   if to_planet  else 0
    s = ring_segments(entry_idx, exit_idx, N)
    m = (s + 1) if s > 0 else 1
    arc_km     = (2 * math.pi * r * s) / N
    fiber_time = arc_km / (F * C)
    tower_time = m * (DT / 1000.0)
    return {
        'entry_tower': entry_idx, 'exit_tower': exit_idx,
        'segments': s, 'towers_hit': m,
        'arc_km': arc_km, 'fiber_s': fiber_time, 'tower_s': tower_time,
        'total_s': fiber_time + tower_time,
    }

def tp_breakdown(planet, from_planet, to_planet):
    r  = planet['radius_km']
    N  = planet['active_towers']
    tp_info = tp(planet, from_planet, to_planet)
    s  = tp_info['segments']
    m  = tp_info['towers_hit']
    return {
        **tp_info,
        'r_km': r, 'N': N, 'f': F, 'C_kms': C, 'dt_ms': DT,
        'circumference_km': round(2 * math.pi * r, 2),
        'arc_km':           round(tp_info['arc_km'], 4),
        'fiber_speed_kms':  round(F * C, 2),
        'eq_fiber': f'(2╧Ç ├ù {r} ├ù {s}) / ({N} ├ù {F} ├ù {C}) = {tp_info["fiber_s"]:.6f} s',
        'eq_tower': f'{m} ├ù {DT}ms/1000 = {tp_info["tower_s"]:.6f} s',
        'eq_total': f'{tp_info["fiber_s"]:.6f} + {tp_info["tower_s"]:.6f} = {tp_info["total_s"]:.6f} s',
    }

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  BASE-N ENCODING
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

def to_base(n, base):
    if n == 0: return "0"
    r = []
    while n > 0:
        r.append(DIGITS[n % base])
        n //= base
    return ''.join(reversed(r))

def from_base(s, base):
    result = 0
    for ch in s.upper():
        result = result * base + DIGITS.index(ch)
    return result

def encode_message(text, base):
    return [to_base(ord(ch), base) for ch in text]

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  GRAPH
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def build_edges():
    plist = list(planets.values())
    edges = []
    for i in range(len(plist)):
        for j in range(i+1, len(plist)):
            p1, p2 = plist[i], plist[j]
            L = void_distance(p1, p2)
            if L <= L_MAX:
                edges.append((p1['id'], p2['id'], L, tv(p1, p2, L)))
    return edges

def build_graph(edges):
    graph = {pid: [] for pid in planets}
    for p1id, p2id, L, t_v in edges:
        if p1id in dead_planets or p2id in dead_planets: continue
        if frozenset([p1id, p2id]) in dead_links:        continue
        graph[p1id].append((p2id, L, t_v))
        graph[p2id].append((p1id, L, t_v))
    return graph

ALL_EDGES = build_edges()

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  DIJKSTRA
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def dijkstra(source, destination):
    graph = build_graph(ALL_EDGES)
    if source in dead_planets or destination in dead_planets:
        return None, [], {}
    dist, pq, visited, prev_map = {pid: float('inf') for pid in planets}, \
                                   [(0.0, source, [source], None)], set(), {}
    dist[source] = 0
    while pq:
        lat, cur, path, prev = heapq.heappop(pq)
        if cur in visited: continue
        visited.add(cur); prev_map[cur] = prev
        if cur == destination: return lat, path, prev_map
        for nbr_id, L, t_v in graph[cur]:
            if nbr_id in visited: continue
            tp_info     = tp(planets[cur], planets[prev] if prev else None, planets[nbr_id])
            new_lat     = lat + tp_info['total_s'] + t_v
            if new_lat < dist[nbr_id]:
                dist[nbr_id] = new_lat
                heapq.heappush(pq, (new_lat, nbr_id, path + [nbr_id], cur))
    return None, [], {}

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  PATH ENUMERATION (for route analysis)
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def compute_path_latency_full(path):
    """Compute complete latency for a given path with full breakdown."""
    if len(path) < 2: return 0.0, []
    total, hops = 0.0, []
    for i in range(len(path) - 1):
        p1_id   = path[i]
        p2_id   = path[i+1]
        p1, p2  = planets[p1_id], planets[p2_id]
        prev_id = path[i-1] if i > 0 else None
        L = void_distance(p1, p2)
        if L > L_MAX: return float('inf'), []   # constraint violated
        tp_info = tp(p1, planets[prev_id] if prev_id else None, p2)
        t_v     = tv(p1, p2, L)
        hop_lat = tp_info['total_s'] + t_v
        total  += hop_lat
        # At final destination add arrival processing
        if i == len(path) - 2:
            tp_dest = tp(p2, p1, None)
            total  += tp_dest['tower_s']
        hops.append({
            'from': p1_id, 'to': p2_id,
            'L_km': round(L, 2),
            'Tv_s': round(t_v, 4),
            'Tp_s': round(tp_info['total_s'], 4),
            'total_s': round(hop_lat, 4),
        })
    return round(total, 6), hops

def enumerate_all_paths(source, destination):
    """DFS to enumerate all simple paths (6-node graph ΓÇö computationally trivial)."""
    graph  = build_graph(ALL_EDGES)
    result = []
    def dfs(cur, path, visited):
        if cur == destination:
            result.append(list(path)); return
        if len(path) >= len(planets): return
        for nbr, *_ in graph.get(cur, []):
            if nbr not in visited:
                visited.add(nbr); path.append(nbr)
                dfs(nbr, path, visited)
                path.pop(); visited.remove(nbr)
    dfs(source, [source], {source})
    return result

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  FULL TRANSMISSION SIMULATION
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

def full_transmission(source, destination, message):
    total_lat, path, _ = dijkstra(source, destination)
    if not path:
        return {'status':'UNDELIVERABLE',
                'reason':'No valid path ΓÇö void distance exceeds limit or node is dead',
                'path':[], 'hops':[], 'log':[], 'total_latency':0}
    log, hops = [], []
    now, cumulative = time.time(), 0.0
    def ts():
        return datetime.fromtimestamp(now+cumulative, tz=timezone.utc).strftime('%H:%M:%S.%f')[:-3]

    log.append({'time':ts(),'type':'info','msg':f'Message created on <b>{source}</b>'})
    log.append({'time':ts(),'type':'info',
                'msg':f'Payload: <code>{message[:40]}{"..." if len(message)>40 else ""}</code>'})

    total_void_km = total_fiber_s = total_atm_s = total_tower_s = total_latency_s = 0.0

    for i in range(len(path)-1):
        p1_id, p2_id   = path[i], path[i+1]
        p1, p2         = planets[p1_id], planets[p2_id]
        prev_id        = path[i-1] if i > 0 else None
        target_base    = p2['codex']
        encoded_vals   = encode_message(message, target_base)
        encoded_str    = ' '.join(encoded_vals[:6]) + (' ...' if len(encoded_vals)>6 else '')

        log.append({'time':ts(),'type':'encode',
                    'msg':f'Payload ΓåÆ <b>Base {target_base}</b> (codex of {p2_id})'})

        tp_info = tp(p1, planets[prev_id] if prev_id else None, p2)
        cumulative += tp_info['total_s']
        total_fiber_s  += tp_info['fiber_s']
        total_tower_s  += tp_info['tower_s']
        total_latency_s+= tp_info['total_s']

        log.append({'time':ts(),'type':'send',
                    'msg':f'Laser sent from <b>{p1_id} T{tp_info["exit_tower"]}</b>'})

        L     = void_distance(p1, p2)
        t_v   = tv(p1, p2, L)
        atm_s = ((p1['atmosphere_thickness_km']*p1['refraction_index']) +
                  (p2['atmosphere_thickness_km']*p2['refraction_index'])) / C
        vac_s = L / C
        cumulative      += t_v
        total_void_km   += L
        total_atm_s     += atm_s
        total_latency_s += t_v

        entry_at_p2 = closest_tower(p2, p1)
        log.append({'time':ts(),'type':'receive','msg':f'Arrived at <b>{p2_id} T{entry_at_p2}</b>'})
        log.append({'time':ts(),'type':'decode',
                    'msg':f'Base {target_base} decoded back to ASCII'})

        if i == len(path)-2:
            tp_dest = tp(p2, p1, None)
            cumulative += tp_dest['tower_s']
            total_tower_s   += tp_dest['tower_s']
            total_latency_s += tp_dest['tower_s']

        hops.append({
            'hop': i+1, 'from_planet': p1_id, 'to_planet': p2_id,
            'from_codex': p1['codex'], 'to_codex': p2['codex'],
            'send_tower': tp_info['exit_tower'], 'recv_tower': entry_at_p2,
            'void_km': round(L, 2), 'void_au': round(L/1.496e8, 4),
            'fiber_s': round(tp_info['fiber_s'], 6),
            'atm_s':   round(atm_s, 6),
            'tower_s': round(tp_info['tower_s'], 6),
            'void_s':  round(vac_s, 6),
            'total_s': round(tp_info['total_s']+t_v, 6),
            'encoded': encoded_str, 'status': 'Success',
        })

    log.append({'time':ts(),'type':'success',
                'msg':f'Delivered to <b>{destination}</b>'})
    return {
        'status':'DELIVERED', 'path':path, 'hops':hops, 'log':log,
        'total_latency': round(total_latency_s, 6),
        'total_hops':    len(path)-1,
        'total_void_km': round(total_void_km, 2),
        'fiber_s':       round(total_fiber_s, 6),
        'atm_s':         round(total_atm_s, 6),
        'tower_s':       round(total_tower_s, 6),
    }

# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ
#  API ROUTES
# ΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉΓòÉ

@app.route('/')
def index():
    return send_from_directory(FRONTEND_DIR, 'index.html')

@app.route('/api/universe')
def api_universe():
    planet_list = []
    for pid, p in planets.items():
        N      = p['active_towers']
        towers = [{'idx':i,'x':tower_position(p,i)[0],'y':tower_position(p,i)[1],
                   'angle':tower_angle_deg(p,i)} for i in range(N)]
        planet_list.append({**p, 'dead': pid in dead_planets, 'towers': towers})

    edge_list = []
    for p1id, p2id, L, t_v in ALL_EDGES:
        lk = frozenset([p1id, p2id])
        is_dead = p1id in dead_planets or p2id in dead_planets or lk in dead_links
        edge_list.append({'from':p1id,'to':p2id,'void_km':round(L,2),
                          'void_au':round(L/1.496e8,4),'tv_s':round(t_v,4),
                          'dead':is_dead,'over_limit':False})

    plist = list(planets.values())
    for i in range(len(plist)):
        for j in range(i+1, len(plist)):
            p1, p2 = plist[i], plist[j]
            L = void_distance(p1, p2)
            if L > L_MAX:
                edge_list.append({'from':p1['id'],'to':p2['id'],'void_km':round(L,2),
                                   'void_au':round(L/1.496e8,4),'tv_s':None,
                                   'dead':True,'over_limit':True})

    return jsonify({'planets':planet_list,'edges':edge_list,'meta':meta,
                    'dead_planets':list(dead_planets),
                    'dead_links':[list(lk) for lk in dead_links]})

@app.route('/api/route', methods=['POST'])
def api_route():
    data = request.json
    src, dst = data.get('source'), data.get('destination')
    if src not in planets or dst not in planets:
        return jsonify({'error':'Unknown planet'}), 400
    if src == dst:
        return jsonify({'error':'Source and destination must differ'}), 400
    lat, path, _ = dijkstra(src, dst)
    if not path:
        return jsonify({'status':'UNDELIVERABLE','path':[],'latency':None})
    return jsonify({'status':'ROUTE_FOUND','path':path,'latency':round(lat,6)})

@app.route('/api/send', methods=['POST'])
def api_send():
    data = request.json
    src, dst = data.get('source'), data.get('destination')
    msg = data.get('message','Hello, Universe!')
    if src not in planets or dst not in planets:
        return jsonify({'error':'Unknown planet'}), 400
    if src == dst:
        return jsonify({'error':'Source and destination must differ'}), 400
    return jsonify(full_transmission(src, dst, msg))

@app.route('/api/route_analysis', methods=['POST'])
def api_route_analysis():
    """
    Deep analysis of a route:
    - All possible paths ranked by latency
    - Constraint analysis for every planet pair
    - Mathematical breakdown (L, Tv, Tp) for each hop of the optimal path
    - Explanation of why the optimal path wins
    """
    data = request.json
    src, dst = data.get('source'), data.get('destination')
    if src not in planets or dst not in planets:
        return jsonify({'error':'Unknown planet'}), 400
    if src == dst:
        return jsonify({'error':'Same planet'}), 400

    # ΓöÇΓöÇ Optimal path ΓöÇΓöÇ
    opt_lat, opt_path, _ = dijkstra(src, dst)

    # ΓöÇΓöÇ All simple paths + their latencies ΓöÇΓöÇ
    all_paths_raw = enumerate_all_paths(src, dst)
    path_analysis = []
    for p in all_paths_raw:
        lat, hops = compute_path_latency_full(p)
        path_analysis.append({
            'path': p,
            'latency': lat if lat != float('inf') else None,
            'feasible': lat != float('inf'),
            'is_optimal': (p == opt_path),
            'hops': hops,
            'hop_count': len(p)-1,
        })
    path_analysis.sort(key=lambda x: x['latency'] if x['latency'] is not None else float('inf'))

    # ΓöÇΓöÇ All-pairs constraint analysis ΓöÇΓöÇ
    plist = list(planets.values())
    all_pairs = []
    for i in range(len(plist)):
        for j in range(i+1, len(plist)):
            p1, p2 = plist[i], plist[j]
            bd = void_distance_breakdown(p1, p2)
            tv_info = tv_breakdown(p1, p2, bd['L_km']) if bd['feasible'] else None
            all_pairs.append({
                'from': p1['id'], 'to': p2['id'],
                'x1': p1['x'], 'y1': p1['y'],
                'x2': p2['x'], 'y2': p2['y'],
                **bd,
                'tv': tv_info,
                'L_MAX_km': L_MAX,
                'constraint_eq':
                    f"L = ΓêÜ(({p2['x']}-{p1['x']})┬▓+({p2['y']}-{p1['y']})┬▓)├ù{int(S)}"
                    f" ΓêÆ ({int(p1['radius_km'])}+{int(p1['atmosphere_thickness_km'])})"
                    f" ΓêÆ ({int(p2['radius_km'])}+{int(p2['atmosphere_thickness_km'])})"
                    f" = {bd['L_km']:,.0f} km",
            })
    all_pairs.sort(key=lambda x: x['L_km'])

    # ΓöÇΓöÇ Hop-level math breakdown for optimal path ΓöÇΓöÇ
    hop_math = []
    if opt_path:
        for i in range(len(opt_path)-1):
            p1_id, p2_id = opt_path[i], opt_path[i+1]
            p1, p2 = planets[p1_id], planets[p2_id]
            prev_id = opt_path[i-1] if i > 0 else None
            L   = void_distance(p1, p2)
            bd  = void_distance_breakdown(p1, p2)
            tvb = tv_breakdown(p1, p2, L)
            tpb = tp_breakdown(p1, planets[prev_id] if prev_id else None, p2)
            hop_math.append({
                'hop': i+1,
                'from': p1_id, 'to': p2_id,
                'void_distance': bd,
                'void_travel':   tvb,
                'planet_transit': tpb,
                'constraint_ok': L <= L_MAX,
                'encoding': {
                    'source_codex': p1['codex'],
                    'target_codex': p2['codex'],
                    'sample_char': 'H',
                    'ascii_val':   72,
                    'encoded':     to_base(72, p2['codex']),
                    'decoded_back': from_base(to_base(72, p2['codex']), p2['codex']),
                }
            })

    # ΓöÇΓöÇ Optimality reason ΓöÇΓöÇ
    feasible_paths = [p for p in path_analysis if p['feasible']]
    reason = ""
    if opt_path and feasible_paths:
        if len(feasible_paths) == 1:
            reason = f"Only 1 feasible path exists from {src} to {dst} ΓÇö all others violate the L_MAX = {int(L_MAX/1e6)}M km void hop constraint."
        else:
            second = feasible_paths[1] if len(feasible_paths) > 1 else None
            diff   = round(second['latency'] - feasible_paths[0]['latency'], 4) if second else 0
            reason = (f"Dijkstra explored all {len(feasible_paths)} feasible paths. "
                      f"The chosen path {' ΓåÆ '.join(opt_path)} has the minimum total latency "
                      f"({round(opt_lat,4)} s). "
                      f"The next-best path {' ΓåÆ '.join(second['path'])} is {diff} s slower.")
    elif not opt_path:
        reason = f"No feasible path exists ΓÇö all routes from {src} to {dst} require a void hop exceeding L_MAX = {int(L_MAX/1e6)}M km."

    return jsonify({
        'source': src, 'destination': dst,
        'optimal_path': opt_path,
        'optimal_latency': round(opt_lat, 6) if opt_lat else None,
        'all_paths': path_analysis,
        'hop_math': hop_math,
        'constraint_analysis': all_pairs,
        'constants': {'C':C,'S':S,'L_MAX':L_MAX,'F':F,'DT':DT},
        'optimality_reason': reason,
        'total_paths_found': len(all_paths_raw),
        'feasible_paths_count': len(feasible_paths),
        'infeasible_paths_count': len(all_paths_raw) - len(feasible_paths),
    })

@app.route('/api/kill_planet', methods=['POST'])
def api_kill_planet():
    pid = request.json.get('planet')
    if pid in planets: dead_planets.add(pid)
    return jsonify({'dead_planets':list(dead_planets),'dead_links':[list(lk) for lk in dead_links]})

@app.route('/api/kill_link', methods=['POST'])
def api_kill_link():
    p1, p2 = request.json.get('planet1'), request.json.get('planet2')
    if p1 in planets and p2 in planets: dead_links.add(frozenset([p1, p2]))
    return jsonify({'dead_planets':list(dead_planets),'dead_links':[list(lk) for lk in dead_links]})

@app.route('/api/restore', methods=['POST'])
def api_restore():
    dead_planets.clear(); dead_links.clear()
    return jsonify({'status':'restored'})

@app.route('/api/encode', methods=['POST'])
def api_encode():
    data = request.json
    return jsonify({'encoded': encode_message(data.get('message',''), int(data.get('base',10))),
                    'base': int(data.get('base',10))})

if __name__ == '__main__':
    print("Zeta-26 Relic Ring Protocol -- Backend starting...")
    print("Open http://localhost:5000 in your browser")
    app.run(debug=True, port=5000)
