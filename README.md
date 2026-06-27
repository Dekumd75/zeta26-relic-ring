# ZETA-26 Relic Ring Protocol

An interplanetary packet-routing simulator built for the Launch26 Phase 01 challenge. ZETA-26 models a fictional planetary relay network where messages are routed across planets, encoded per-hop using each planet's codex base, and evaluated using latency components from void travel, atmosphere, fiber transit, and tower processing.

## Overview

The system combines a Flask backend with a React/Vite frontend:

- The backend loads all planetary constants from `backend/universe-config.json`.
- Dijkstra-based routing finds the minimum-latency valid path across the network.
- Packet transmission records hop-by-hop tower selection, encoded payloads, and latency breakdowns.
- The frontend visualizes the ZETA-26 map as a 2D X/Y coordinate field with planet towers, active routes, packet animation, failure controls, route telemetry, and event logs.

## Key Features

- Shortest-path routing with current network failure state.
- Planet-to-planet void-hop validation using a maximum hop distance.
- Per-hop payload encoding into the destination planet's codex base.
- Send and receive tower selection for each hop.
- Latency breakdown across void, atmosphere, fiber, and tower processing.
- Interactive failure simulation for planets and links.
- Packet JSON download for delivered transmissions.
- Canvas-based 2D universe map with tower-to-tower route visualization.

## Project Structure

```text
zeta26-relic-ring/
├── backend/
│   ├── app.py                  # Flask API, routing, encoding, latency logic
│   ├── requirements.txt        # Python dependencies
│   ├── universe-config.json    # Source of truth for planet data and constants
│   └── README.md
├── frontend/
│   ├── index.html
│   ├── package.json
│   ├── package-lock.json
│   ├── universe-config.json
│   └── src/
│       ├── App.jsx             # React application and canvas scene
│       ├── main.jsx
│       └── styles.css
|
└── README.md
```

## Tech Stack

| Layer | Technology |
| --- | --- |
| Backend | Python, Flask |
| Frontend | React, Vite |
| Visualization | HTML Canvas |
| Routing | Dijkstra shortest path |
| Data format | JSON |
| Styling | CSS |

## Requirements

- Python 3.9 or newer
- Node.js 18 or newer
- npm

## Setup

Install backend dependencies:

```bash
cd backend
pip install -r requirements.txt
```

Install frontend dependencies:

```bash
cd frontend
npm install
```

## Running the Application

Start the backend API:

```bash
cd backend
python app.py
```

The backend runs on:

```text
http://localhost:5000
```

Start the frontend development server in a second terminal:

```bash
cd frontend
npm run dev
```

The frontend runs on:

```text
http://127.0.0.1:5173
```

## Production Build

Build the frontend:

```bash
cd frontend
npm run build
```

Preview the built frontend:

```bash
cd frontend
npm run preview
```

## Universe Configuration

Planet data and simulation constants are defined in:

```text
backend/universe-config.json
```

Each planet includes:

- `id`
- `codex`
- `x` and `y` coordinate center points
- `radius_km`
- `active_towers`
- `atmosphere_thickness_km`
- `refraction_index`

The current ZETA-26 planets are:

| Planet | Coordinates | Codex | Towers | Radius |
| --- | --- | ---: | ---: | ---: |
| Aegis | `(0, 0)` | 8 | 8 | 6,371 km |
| Boreas | `(150, 100)` | 5 | 4 | 3,389 km |
| Dawn | `(350, 50)` | 6 | 6 | 1,500 km |
| Elysium | `(300, 350)` | 10 | 12 | 6,051 km |
| Fenix | `(500, -100)` | 16 | 4 | 1,200 km |
| Caelum | `(650, 200)` | 14 | 16 | 58,232 km |

## Simulation Model

### Void Distance

The void distance between two planets is calculated from center-to-center coordinate distance, then reduced by each planet's radius and atmosphere shell:

```text
L = sqrt((x2 - x1)^2 + (y2 - y1)^2) * S - (R1 + h1) - (R2 + h2)
```

Where:

- `S` is `coordinate_scale_unit_km`
- `R` is planet radius
- `h` is atmosphere thickness
- `L` must not exceed `max_void_hop_distance_km`

### Void Travel Time

```text
Tv = ((h1 * n1) + (h2 * n2) + L) / c
```

Where:

- `n` is atmosphere refraction index
- `c` is `speed_of_light_kms`

### Internal Fiber Transit

Internal movement across a planet is based on the shortest tower-ring segment path:

```text
fiber_ms = ((2 * pi * radius_km * segments) / active_towers) / (fiber_speed_fraction * c) * 1000
```

Tower processing is added per hop using `tower_processing_delay_ms`.

## API Reference

### Universe

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/universe` | Returns planets, towers, edges, metadata, and failure state. |

### Routing and Packets

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/routes/shortest-path` | Calculates the lowest-latency route without storing a packet. |
| `GET` | `/api/routes/details` | Returns route details from query parameters. |
| `POST` | `/api/packets/send` | Sends and stores a packet with hop telemetry. |
| `GET` | `/api/packets/<packet_id>/download` | Downloads a stored packet as JSON. |
| `GET` | `/api/packets/<packet_id>/logs/stream` | Streams packet hop logs as server-sent events. |

### Failures

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/failures` | Returns deactivated planets and links. |
| `POST` | `/api/failures/planets/<planet_id>` | Deactivates a planet. |
| `DELETE` | `/api/failures/planets/<planet_id>` | Restores a planet. |
| `POST` | `/api/failures/links` | Deactivates a bidirectional link. |
| `DELETE` | `/api/failures/links` | Restores a bidirectional link. |

### Compatibility Endpoints

The backend also keeps earlier compatibility routes:

| Method | Endpoint | Description |
| --- | --- | --- |
| `POST` | `/api/route` | Legacy route lookup. |
| `POST` | `/api/send` | Legacy packet transmission. |
| `POST` | `/api/route_analysis` | Detailed route analysis. |
| `POST` | `/api/kill_planet` | Legacy planet failure endpoint. |
| `POST` | `/api/kill_link` | Legacy link failure endpoint. |
| `POST` | `/api/restore` | Restores all failures. |
| `POST` | `/api/encode` | Encodes a message into a requested base. |

## Example Packet Request

```bash
curl -X POST http://localhost:5000/api/packets/send \
  -H "Content-Type: application/json" \
  -d "{\"from_planet\":\"Aegis\",\"from_tower\":\"T0\",\"to_planet\":\"Caelum\",\"message\":\"Hello Zeta-26\",\"disabled_planets\":[]}"
```

## Frontend Notes

The frontend map uses the planet `x` and `y` values as a 2D coordinate plane:

- Positive X moves right.
- Positive Y moves upward.
- Packet routes are drawn directly between the selected sending and receiving towers.
- Failure controls and route telemetry update through the Flask API.

## Verification

Use these commands before submitting changes:

```bash
cd frontend
npm run build
```

```bash
cd backend
python app.py
```

Then open:

```text
http://127.0.0.1:5173
```


## Acknowledgements

Built for Launch26 Phase 01 and the IEEE CS Chapter, University of Kelaniya.
