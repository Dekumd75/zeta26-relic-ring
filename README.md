# 🌌 ZETA-26 — Relic Ring Protocol
### Interplanetary Routing Simulator | Launch26 Phase 01

> **IEEE CS Chapter — University of Kelaniya**

---

## 📁 Project Structure

```
zeta26-relic-ring/
├── backend/
│   ├── app.py                 ← Flask server (routing, encoding, latency engine)
│   ├── universe-config.json   ← Planet configuration (parsed dynamically)
│   └── requirements.txt       ← Python dependencies
├── frontend/
│   └── index.html             ← Full UI (single-file, no build step needed)
├── README.md
└── .gitignore
```

---

## 🚀 Overview

ZETA-26 is an **interplanetary network routing simulator** built for the Launch26 Phase 01 challenge. It simulates laser-based packet transmission across 6 planets in the fictional Zeta-26 universe, featuring:

- **Shortest-path routing** using Dijkstra's algorithm
- **Base-N encoding** — each planet speaks a unique numerical base (codex)
- **Precise latency calculation** — void travel, atmospheric refraction, fiber transit & tower delays
- **Chaos testing** — kill planets or links, watch the network reroute in real time
- **Live visualizer** — animated space map with flying packet animations

---

## 🪐 The Universe — Zeta-26

| Planet | Codex (Base) | Towers | Radius (km) | Atmosphere (km) |
|--------|-------------|--------|-------------|-----------------|
| Aegis  | Base 8      | 8      | 6,371       | 120             |
| Boreas | Base 5      | 4      | 3,389       | 85              |
| Dawn   | Base 6      | 6      | 1,500       | 30              |
| Elysium| Base 10     | 12     | 6,051       | 250             |
| Fenix  | Base 16     | 4      | 1,200       | 15              |
| Caelum | Base 14     | 16     | 58,232      | 500             |

---

## ⚙️ Setup & Running

### Prerequisites
- Python 3.9+
- pip

### Installation

```bash
# Clone the repository
git clone https://github.com/YOUR_USERNAME/zeta26-relic-ring.git
cd zeta26-relic-ring

# Install backend dependencies
cd backend
pip install -r requirements.txt

# Run the backend server
python app.py
```

### Open the app
Navigate to **http://localhost:5000** in your browser.

> The Flask server automatically serves the `frontend/index.html` — no separate frontend server needed!

---

## 👥 For Team Members

### Working on the Backend (`/backend`)
```bash
cd backend
pip install -r requirements.txt
python app.py          # Starts server on http://localhost:5000
```
- `app.py` — All routing, encoding and latency logic
- `universe-config.json` — Planet data (never hardcode values!)
- `requirements.txt` — Add new Python packages here

### Working on the Frontend (`/frontend`)
- Edit `frontend/index.html` directly — it's a single self-contained file
- No build tools, no npm, no node required
- Refresh the browser to see changes (backend must be running)

---

## 📐 Physics & Math

### 1. Void Distance `L`
The vacuum gap between two planet atmospheres:
```
L = √((x₂−x₁)² + (y₂−y₁)²) × S  −  (R₁+h₁)  −  (R₂+h₂)
```
- `S` = 100,000 km/grid-unit (coordinate scale)
- `R` = planet radius, `h` = atmosphere thickness
- **Constraint:** L > 50,000,000 km → hop is impossible, must relay

### 2. Void Travel Time `Tv`
Light slows in atmosphere (refraction index `n`):
```
Tv = [(h₁×n₁) + (h₂×n₂) + L] / c
```
- `c` = 300,000 km/s (speed of light)

### 3. Internal Planet Transit `Tp`
Fiber ring travel between entry and exit towers + processing delay:
```
Tp = (2π × r × s) / (N × f × c)  +  m × Δt
```
- `s` = ring segments (shortest arc between towers)
- `f` = 0.67 (fiber speed fraction)
- `m` = towers hit, `Δt` = 7 ms per tower

### 4. Total End-to-End Latency
```
Total = Σ Tp(Pᵢ) + Σ Tv(Pᵢ → Pᵢ₊₁)
```

### 5. Data Encoding (Codex Conversion)
Each hop converts the ASCII payload to the next planet's numerical base:
```
'H' (ASCII 72) → Base 5 = "242" → Base 14 = "52" → ASCII 72 → 'H'
```

---

## 🏗️ Architecture

```
app.py          ← Flask backend (routing, encoding, latency engine)
index.html      ← Single-file frontend (Canvas UI, dark space theme)
universe-config.json  ← Planet configuration (parsed dynamically — no hardcoding)
requirements.txt
```

### API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET  | `/api/universe` | All planets, edges, tower positions |
| POST | `/api/route` | Find fastest route (Dijkstra) |
| POST | `/api/send` | Full transmission + hop-by-hop encoding log |
| POST | `/api/kill_planet` | Mark a planet as dead |
| POST | `/api/kill_link` | Sever a link between two planets |
| POST | `/api/restore` | Restore all failed nodes/links |
| POST | `/api/encode` | Encode a message into a specific base |

---

## 🎮 Features

- **Universe Map** — 2D canvas with animated starfield, planet glow, tower dots
- **Route Highlight** — fastest path shown in green, over-limit links in dashed gray
- **Packet Animation** — flying particle travels along the route in real time
- **Latency Breakdown Bar** — visual split of fiber / atmosphere / tower / void delay
- **Hop Table** — per-hop: towers used, void distance, all latency components, encoded sample
- **Message Log** — live color-coded event stream (encode → send → receive → decode)
- **Chaos Controls** — kill any planet or link, instant rerouting on next transmission
- **Pan & Zoom** — drag and scroll to explore the universe map

---

## 🔧 Assumed Constants

All constants are read from `universe-config.json` — **no hardcoded planetary values**.

| Constant | Value | Source |
|----------|-------|--------|
| Speed of light `c` | 300,000 km/s | `universe_metadata.speed_of_light_kms` |
| Max void hop | 50,000,000 km | `universe_metadata.max_void_hop_distance_km` |
| Coordinate scale | 100,000 km/unit | `universe_metadata.coordinate_scale_unit_km` |
| Fiber speed fraction | 0.67 | `universe_metadata.fiber_speed_fraction` |
| Tower delay | 7 ms | `universe_metadata.tower_processing_delay_ms` |

---

## 🛠️ Tech Stack

| Layer | Technology |
|-------|------------|
| **Backend** | Python 3 + Flask |
| **Frontend** | Vanilla HTML5 + CSS3 + JavaScript (Canvas API) |
| **Routing** | Dijkstra's shortest-path algorithm |
| **Styling** | Pure CSS — no Tailwind, no Bootstrap |
| **JS Libs** | None — zero frontend dependencies |

---

*Built for Launch26 Phase 01 — IEEE CS Chapter, University of Kelaniya*
