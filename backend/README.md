# ZETA-26 Backend

Flask backend for the ZETA-26 Relic Ring Protocol simulator. This service owns the universe configuration, routing engine, latency calculations, packet transmission flow, failure state, and packet download endpoints.

## Responsibilities

- Load planet and simulation constants from `universe-config.json`.
- Build valid interplanetary links using the maximum void-hop distance.
- Calculate shortest valid packet routes.
- Select send and receive towers for each hop.
- Encode payloads into the next planet's codex base.
- Track deactivated planets and links.
- Store sent packets in memory for JSON download.

## Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Start the server:

```bash
python app.py
```

The API runs at:

```text
http://localhost:5000
```

## Core Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/universe` | Returns planets, towers, edges, metadata, and failure state. |
| `POST` | `/api/routes/shortest-path` | Computes the lowest-latency route without storing a packet. |
| `GET` | `/api/routes/details` | Computes route details from query parameters. |
| `POST` | `/api/packets/send` | Sends and stores a packet with hop telemetry. |
| `GET` | `/api/packets/<packet_id>/download` | Downloads a stored packet JSON file. |
| `GET` | `/api/packets/<packet_id>/logs/stream` | Streams packet hop logs as SSE. |

## Failure Endpoints

| Method | Endpoint | Description |
| --- | --- | --- |
| `GET` | `/api/failures` | Returns current failed planets and links. |
| `POST` | `/api/failures/planets/<planet_id>` | Deactivates a planet. |
| `DELETE` | `/api/failures/planets/<planet_id>` | Restores a planet. |
| `POST` | `/api/failures/links` | Deactivates a bidirectional link. |
| `DELETE` | `/api/failures/links` | Restores a bidirectional link. |

## Compatibility Endpoints

The backend also exposes earlier routes used by older clients:

- `POST /api/route`
- `POST /api/send`
- `POST /api/route_analysis`
- `POST /api/kill_planet`
- `POST /api/kill_link`
- `POST /api/restore`
- `POST /api/encode`

## Configuration Notes

- Planet `x` and `y` values are center coordinates in a 2D plane.
- `coordinate_scale_unit_km` converts coordinate units to kilometers.
- Planet radius and atmosphere thickness are stored in kilometers.
- Tower `T0` starts at the top of the planet ring.
- Tower indexes increase clockwise.
- Deactivated links are treated as bidirectional.
- Packet storage is in memory and resets when the server restarts.
