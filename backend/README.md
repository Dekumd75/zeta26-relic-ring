# Relic Ring Backend

FastAPI backend for the Zeta-26 Relic Ring Protocol simulator.

## Run

```bash
pip install -r requirements.txt
python app.py
```

The API serves the existing frontend at `http://localhost:5000` and exposes the planned routes under `/api`.

## Key Endpoints

- `GET /api/health`
- `GET /api/universe`
- `POST /api/routes/shortest-path`
- `POST /api/routes/shortest-path/without-planet`
- `POST /api/routes/details`
- `GET /api/routes/stream-logs`
- `GET /api/failures`
- `POST/DELETE /api/failures/planets/{planet_id}`
- `POST/DELETE /api/failures/links`

Compatibility endpoints for the existing frontend are still available: `/api/route`, `/api/send`, `/api/kill_planet`, `/api/kill_link`, `/api/restore`, `/api/route_analysis`, and `/api/encode`.

## Assumptions

- Planet `x/y` coordinates are center points and are scaled by `coordinate_scale_unit_km`.
- Planet radius and atmosphere thickness are already in kilometers.
- Tower 0 starts at the top; tower indexes increase clockwise.
- The closest tower pair is selected by tower-to-tower Euclidean distance.
- Official void distance `L` uses center-to-center distance minus radius and atmosphere shells.
- Tower positions do not affect `L` or direct-link validity.
- Dijkstra runs on expanded `(planet, tower)` states and minimizes total latency.
- Destination delivery ends at the receiving tower, so no extra destination fiber movement is added.
- Deactivated links are treated as bidirectional.
