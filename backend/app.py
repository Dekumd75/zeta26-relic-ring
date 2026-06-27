from __future__ import annotations

import asyncio
import heapq
import json
import math
import os
from typing import Any, Dict, List, Optional, Set, Tuple

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(BASE_DIR, "universe-config.json")
FRONTEND_INDEX = os.path.abspath(os.path.join(BASE_DIR, "..", "frontend", "index.html"))
DIGITS = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

app = FastAPI(title="Relic Ring Protocol API")


class ShortestPathRequest(BaseModel):
    from_planet: str
    from_tower: int = 0
    to_planet: str
    message: str = ""


class ShortestPathWithoutPlanetRequest(ShortestPathRequest):
    deactivated_planet: str


class LinkFailureRequest(BaseModel):
    from_planet: str
    to_planet: str


def load_universe_config(file_path: str) -> Dict[str, Any]:
    with open(file_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def tower_id(index: int) -> str:
    return f"T{index}"


def parse_tower_index(value: str) -> int:
    return int(value[1:] if str(value).upper().startswith("T") else value)


def link_key(from_planet: str, to_planet: str) -> str:
    return f"{from_planet}->{to_planet}"


def canonical_link(from_planet: str, to_planet: str) -> Tuple[str, str]:
    return tuple(sorted((from_planet, to_planet)))


def scale_planet_coordinates(planet: Dict[str, Any], scale_km: float) -> Dict[str, Any]:
    planet = dict(planet)
    planet["scaled_x_km"] = planet["x"] * scale_km
    planet["scaled_y_km"] = planet["y"] * scale_km
    return planet


def generate_towers_for_planet(planet: Dict[str, Any]) -> List[Dict[str, Any]]:
    towers = []
    for index in range(planet["active_towers"]):
        angle = 2.0 * math.pi * index / planet["active_towers"]
        x_km = planet["scaled_x_km"] + planet["radius_km"] * math.sin(angle)
        y_km = planet["scaled_y_km"] + planet["radius_km"] * math.cos(angle)
        towers.append({"id": tower_id(index), "index": index, "idx": index, "x_km": x_km, "y_km": y_km})
    return towers


def calculate_center_distance_km(planet_a: Dict[str, Any], planet_b: Dict[str, Any]) -> float:
    return math.hypot(planet_b["scaled_x_km"] - planet_a["scaled_x_km"], planet_b["scaled_y_km"] - planet_a["scaled_y_km"])


def calculate_void_distance_km(planet_a: Dict[str, Any], planet_b: Dict[str, Any]) -> float:
    center_distance = calculate_center_distance_km(planet_a, planet_b)
    shell_a = planet_a["radius_km"] + planet_a["atmosphere_thickness_km"]
    shell_b = planet_b["radius_km"] + planet_b["atmosphere_thickness_km"]
    return max(0.0, center_distance - shell_a - shell_b)


def is_direct_link_valid(void_distance_km: float, max_void_hop_distance_km: float) -> bool:
    return void_distance_km <= max_void_hop_distance_km


def calculate_tower_distance_km(tower_a: Dict[str, Any], tower_b: Dict[str, Any]) -> float:
    return math.hypot(tower_b["x_km"] - tower_a["x_km"], tower_b["y_km"] - tower_a["y_km"])


def find_closest_tower_pair(planet_a: Dict[str, Any], planet_b: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any], float]:
    best = None
    for tower_a in planet_a["towers"]:
        for tower_b in planet_b["towers"]:
            distance = calculate_tower_distance_km(tower_a, tower_b)
            if best is None or distance < best[2]:
                best = (tower_a, tower_b, distance)
    if best is None:
        raise ValueError("Planets must have towers")
    return best


def calculate_planet_atmosphere_delay_ms(planet: Dict[str, Any], speed_of_light_kms: float) -> float:
    return ((planet["atmosphere_thickness_km"] * planet["refraction_index"]) / speed_of_light_kms) * 1000.0


def calculate_hop_atmosphere_delay_ms(planet_a: Dict[str, Any], planet_b: Dict[str, Any], speed_of_light_kms: float) -> float:
    return calculate_planet_atmosphere_delay_ms(planet_a, speed_of_light_kms) + calculate_planet_atmosphere_delay_ms(planet_b, speed_of_light_kms)


def calculate_void_delay_ms(void_distance_km: float, speed_of_light_kms: float) -> float:
    return (void_distance_km / speed_of_light_kms) * 1000.0


def calculate_shortest_tower_segments(entry_index: int, exit_index: int, total_towers: int) -> int:
    raw_diff = abs(exit_index - entry_index)
    return min(raw_diff, total_towers - raw_diff)


def calculate_fiber_distance_km(planet: Dict[str, Any], segment_count: int) -> float:
    return (2.0 * math.pi * planet["radius_km"] * segment_count) / planet["active_towers"]


def calculate_fiber_delay_ms(fiber_distance_km: float, speed_of_light_kms: float, fiber_speed_fraction: float) -> float:
    return (fiber_distance_km / (speed_of_light_kms * fiber_speed_fraction)) * 1000.0


def calculate_processing_tower_count(segment_count: int) -> int:
    return 1 if segment_count == 0 else segment_count + 1


def calculate_tower_processing_delay_ms(processing_tower_count: int, tower_processing_delay_ms: float) -> float:
    return processing_tower_count * tower_processing_delay_ms


def calculate_internal_transit_delay_ms(planet: Dict[str, Any], entry_tower_index: int, exit_tower_index: int, speed_of_light_kms: float, fiber_speed_fraction: float, tower_processing_delay_ms: float) -> Dict[str, float]:
    segment_count = calculate_shortest_tower_segments(entry_tower_index, exit_tower_index, planet["active_towers"])
    fiber_distance_km = calculate_fiber_distance_km(planet, segment_count)
    fiber_delay_ms = calculate_fiber_delay_ms(fiber_distance_km, speed_of_light_kms, fiber_speed_fraction)
    processing_count = calculate_processing_tower_count(segment_count)
    tower_delay_ms = calculate_tower_processing_delay_ms(processing_count, tower_processing_delay_ms)
    return {
        "segment_count": segment_count,
        "fiber_distance_km": fiber_distance_km,
        "fiber_delay_ms": fiber_delay_ms,
        "processing_tower_count": processing_count,
        "tower_processing_delay_ms": tower_delay_ms,
        "internal_total_ms": fiber_delay_ms + tower_delay_ms,
    }


def calculate_void_transit_delay_ms(planet_a: Dict[str, Any], planet_b: Dict[str, Any], void_distance_km: float, speed_of_light_kms: float) -> Dict[str, float]:
    atmosphere_delay_ms = calculate_hop_atmosphere_delay_ms(planet_a, planet_b, speed_of_light_kms)
    void_delay_ms = calculate_void_delay_ms(void_distance_km, speed_of_light_kms)
    return {"atmosphere_delay_ms": atmosphere_delay_ms, "void_delay_ms": void_delay_ms, "void_transit_total_ms": atmosphere_delay_ms + void_delay_ms}


def build_direct_links(planets: List[Dict[str, Any]], metadata: Dict[str, Any]) -> List[Dict[str, Any]]:
    links = []
    for i, planet_a in enumerate(planets):
        for planet_b in planets[i + 1:]:
            void_distance = calculate_void_distance_km(planet_a, planet_b)
            valid = is_direct_link_valid(void_distance, metadata["max_void_hop_distance_km"])
            tower_a, tower_b, tower_distance = find_closest_tower_pair(planet_a, planet_b)
            breakdown = calculate_void_transit_delay_ms(planet_a, planet_b, void_distance, metadata["speed_of_light_kms"])
            for from_planet, to_planet, send_tower, receive_tower in ((planet_a, planet_b, tower_a, tower_b), (planet_b, planet_a, tower_b, tower_a)):
                links.append({
                    "from_planet": from_planet["id"],
                    "to_planet": to_planet["id"],
                    "send_tower": send_tower["id"],
                    "receive_tower": receive_tower["id"],
                    "tower_pair_distance_km": tower_distance,
                    "void_distance_km": void_distance,
                    "valid": valid,
                    "latency_ms": breakdown["void_transit_total_ms"],
                    "latency_breakdown": dict(breakdown),
                })
    return links


def build_graph_from_links(planets: List[Dict[str, Any]], links: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    graph = {planet["id"]: [] for planet in planets}
    for link in links:
        if link["valid"]:
            graph[link["from_planet"]].append(link)
    return graph


def initialize_universe(file_path: str) -> Dict[str, Any]:
    raw = load_universe_config(file_path)
    metadata = raw["universe_metadata"]
    planets = [scale_planet_coordinates(planet, metadata["coordinate_scale_unit_km"]) for planet in raw["nodes"]]
    for planet in planets:
        planet["towers"] = generate_towers_for_planet(planet)
    links = build_direct_links(planets, metadata)
    return {
        "metadata": metadata,
        "planets_by_id": {planet["id"]: planet for planet in planets},
        "links_by_key": {link_key(link["from_planet"], link["to_planet"]): link for link in links},
        "graph": build_graph_from_links(planets, links),
        "all_links": links,
        "deactivated_planets": set(),
        "deactivated_links": set(),
    }


state = initialize_universe(CONFIG_PATH)


def is_planet_active(planet_id: str, extra_dead: Optional[Set[str]] = None) -> bool:
    return planet_id not in state["deactivated_planets"] and planet_id not in (extra_dead or set())


def is_link_active(from_planet: str, to_planet: str, extra_dead: Optional[Set[Tuple[str, str]]] = None) -> bool:
    inactive = set(state["deactivated_links"])
    if extra_dead:
        inactive.update(extra_dead)
    return canonical_link(from_planet, to_planet) not in inactive


def validate_route_request(request_data: ShortestPathRequest, extra_dead_planets: Optional[Set[str]] = None) -> None:
    planets = state["planets_by_id"]
    if request_data.from_planet not in planets:
        raise HTTPException(status_code=400, detail="Unknown origin planet")
    if request_data.to_planet not in planets:
        raise HTTPException(status_code=400, detail="Unknown destination planet")
    if not request_data.message.strip():
        raise HTTPException(status_code=400, detail="Message must not be empty")
    origin = planets[request_data.from_planet]
    if request_data.from_tower < 0 or request_data.from_tower >= origin["active_towers"]:
        raise HTTPException(status_code=400, detail=f"Origin tower must be between 0 and {origin['active_towers'] - 1}")
    if not is_planet_active(request_data.from_planet, extra_dead_planets) or not is_planet_active(request_data.to_planet, extra_dead_planets):
        raise HTTPException(status_code=400, detail="Origin or destination planet is deactivated")


def reconstruct_dijkstra_path(previous: Dict[Tuple[str, int], Tuple[Tuple[str, int], Dict[str, Any]]], end_state: Tuple[str, int]) -> Tuple[List[Tuple[str, int]], List[Dict[str, Any]]]:
    route_states = [end_state]
    route_links = []
    current = end_state
    while current in previous:
        previous_state, link = previous[current]
        route_links.append(link)
        route_states.append(previous_state)
        current = previous_state
    route_states.reverse()
    route_links.reverse()
    return route_states, route_links


def find_minimum_latency_path(origin_planet_id: str, origin_tower_index: int, destination_planet_id: str, graph: Dict[str, List[Dict[str, Any]]], planets_by_id: Dict[str, Dict[str, Any]], metadata: Dict[str, Any], deactivated_planets: Optional[Set[str]] = None, deactivated_links: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Any]:
    if origin_planet_id == destination_planet_id:
        return {"status": "delivered", "origin_id": origin_planet_id, "destination_id": destination_planet_id, "route": [origin_planet_id], "route_states": [(origin_planet_id, origin_tower_index)], "route_links": [], "total_latency_ms": 0.0}
    start_state = (origin_planet_id, origin_tower_index)
    heap = [(0.0, start_state)]
    distances = {start_state: 0.0}
    previous: Dict[Tuple[str, int], Tuple[Tuple[str, int], Dict[str, Any]]] = {}
    while heap:
        current_cost, (current_planet_id, current_tower_index) = heapq.heappop(heap)
        if current_cost > distances[(current_planet_id, current_tower_index)]:
            continue
        if current_planet_id == destination_planet_id:
            route_states, route_links = reconstruct_dijkstra_path(previous, (current_planet_id, current_tower_index))
            return {"status": "delivered", "origin_id": origin_planet_id, "destination_id": destination_planet_id, "route": [planet for planet, _ in route_states], "route_states": route_states, "route_links": route_links, "total_latency_ms": current_cost}
        if not is_planet_active(current_planet_id, deactivated_planets):
            continue
        for link in graph.get(current_planet_id, []):
            neighbor_id = link["to_planet"]
            if not is_planet_active(neighbor_id, deactivated_planets) or not is_link_active(current_planet_id, neighbor_id, deactivated_links):
                continue
            send_tower_index = parse_tower_index(link["send_tower"])
            receive_tower_index = parse_tower_index(link["receive_tower"])
            internal_cost = calculate_internal_transit_delay_ms(planets_by_id[current_planet_id], current_tower_index, send_tower_index, metadata["speed_of_light_kms"], metadata["fiber_speed_fraction"], metadata["tower_processing_delay_ms"])["internal_total_ms"]
            edge_cost = internal_cost + link["latency_breakdown"]["void_transit_total_ms"]
            next_state = (neighbor_id, receive_tower_index)
            new_cost = current_cost + edge_cost
            if new_cost < distances.get(next_state, float("inf")):
                distances[next_state] = new_cost
                previous[next_state] = ((current_planet_id, current_tower_index), link)
                heapq.heappush(heap, (new_cost, next_state))
    return {"status": "undeliverable", "origin_id": origin_planet_id, "destination_id": destination_planet_id, "reason": "No valid route found with current failures.", "route": [], "route_states": [], "route_links": [], "total_latency_ms": 0.0}


def text_to_ascii_values(message: str) -> List[int]:
    return [ord(char) for char in message]


def integer_to_base(value: int, base: int) -> str:
    if base < 2 or base > len(DIGITS):
        raise ValueError("Base must be between 2 and 36")
    if value == 0:
        return "0"
    digits = []
    while value > 0:
        digits.append(DIGITS[value % base])
        value //= base
    return "".join(reversed(digits))


def ascii_values_to_codex(ascii_values: List[int], codex: int) -> List[str]:
    return [integer_to_base(value, codex) for value in ascii_values]


def decode_codex_to_ascii(encoded_values: List[str], codex: int) -> List[int]:
    values = []
    for encoded in encoded_values:
        value = 0
        for char in encoded.upper():
            digit = DIGITS.index(char)
            if digit >= codex:
                raise ValueError(f"Digit {char} is invalid for base {codex}")
            value = value * codex + digit
        values.append(value)
    return values


def simulate_packet_route(route_states: List[Tuple[str, int]], route_links: List[Dict[str, Any]], message: str, planets_by_id: Dict[str, Dict[str, Any]], metadata: Dict[str, Any]) -> Dict[str, Any]:
    ascii_values = text_to_ascii_values(message)
    hop_log = []
    totals = {"fiber_delay_ms": 0.0, "tower_processing_delay_ms": 0.0, "atmosphere_delay_ms": 0.0, "void_delay_ms": 0.0}
    for index, link in enumerate(route_links):
        from_planet_id, entry_tower_index = route_states[index]
        to_planet = planets_by_id[link["to_planet"]]
        internal = calculate_internal_transit_delay_ms(planets_by_id[from_planet_id], entry_tower_index, parse_tower_index(link["send_tower"]), metadata["speed_of_light_kms"], metadata["fiber_speed_fraction"], metadata["tower_processing_delay_ms"])
        void_breakdown = link["latency_breakdown"]
        latency_ms = internal["internal_total_ms"] + void_breakdown["void_transit_total_ms"]
        totals["fiber_delay_ms"] += internal["fiber_delay_ms"]
        totals["tower_processing_delay_ms"] += internal["tower_processing_delay_ms"]
        totals["atmosphere_delay_ms"] += void_breakdown["atmosphere_delay_ms"]
        totals["void_delay_ms"] += void_breakdown["void_delay_ms"]
        hop_log.append({
            "hop_number": index + 1,
            "from_planet": link["from_planet"],
            "to_planet": link["to_planet"],
            "send_tower": link["send_tower"],
            "receive_tower": link["receive_tower"],
            "encoded_payload_for_next_planet": ascii_values_to_codex(ascii_values, to_planet["codex"]),
            "to_codex": to_planet["codex"],
            "void_distance_km": link["void_distance_km"],
            "latency_ms": latency_ms,
            "latency_breakdown": {**internal, "internal_fiber_ms": internal["fiber_delay_ms"], "tower_processing_ms": internal["tower_processing_delay_ms"], "atmosphere_ms": void_breakdown["atmosphere_delay_ms"], "void_ms": void_breakdown["void_delay_ms"], "void_transit_total_ms": void_breakdown["void_transit_total_ms"]},
            "status": "sent",
        })
    return {"hop_log": hop_log, "latency_breakdown": totals, "total_latency_ms": sum(totals.values())}


def route_response_from_search(search: Dict[str, Any], message: str) -> Dict[str, Any]:
    if search["status"] != "delivered":
        return {"status": "undeliverable", "origin_id": search["origin_id"], "destination_id": search["destination_id"], "reason": search.get("reason", "No valid route found with current failures."), "route": [], "route_states": [], "total_latency_ms": 0.0, "latency_breakdown": {}, "hop_log": []}
    simulation = simulate_packet_route(search["route_states"], search["route_links"], message, state["planets_by_id"], state["metadata"])
    return {"status": "delivered", "origin_id": search["origin_id"], "destination_id": search["destination_id"], "route": search["route"], "route_states": [{"planet": p, "tower": tower_id(t)} for p, t in search["route_states"]], "total_latency_ms": simulation["total_latency_ms"], "latency_breakdown": simulation["latency_breakdown"], "hop_log": simulation["hop_log"]}


def find_route_response(request_data: ShortestPathRequest, extra_dead_planets: Optional[Set[str]] = None, extra_dead_links: Optional[Set[Tuple[str, str]]] = None) -> Dict[str, Any]:
    validate_route_request(request_data, extra_dead_planets)
    search = find_minimum_latency_path(request_data.from_planet, request_data.from_tower, request_data.to_planet, state["graph"], state["planets_by_id"], state["metadata"], extra_dead_planets, extra_dead_links)
    return route_response_from_search(search, request_data.message)


def deactivate_planet(planet_id: str) -> None:
    if planet_id not in state["planets_by_id"]:
        raise HTTPException(status_code=404, detail="Unknown planet")
    state["deactivated_planets"].add(planet_id)


def restore_planet(planet_id: str) -> None:
    state["deactivated_planets"].discard(planet_id)


def deactivate_link(from_planet: str, to_planet: str) -> None:
    if link_key(from_planet, to_planet) not in state["links_by_key"]:
        raise HTTPException(status_code=404, detail="Unknown link")
    state["deactivated_links"].add(canonical_link(from_planet, to_planet))


def restore_link(from_planet: str, to_planet: str) -> None:
    state["deactivated_links"].discard(canonical_link(from_planet, to_planet))


def failure_state_response() -> Dict[str, Any]:
    return {"status": "success", "deactivated_planets": sorted(state["deactivated_planets"]), "deactivated_links": [{"from_planet": a, "to_planet": b} for a, b in sorted(state["deactivated_links"])]}


def tower_public_dict(planet: Dict[str, Any], tower: Dict[str, Any]) -> Dict[str, Any]:
    scale = state["metadata"]["coordinate_scale_unit_km"]
    angle = (360.0 / planet["active_towers"]) * tower["index"]
    return {**tower, "x": tower["x_km"] / scale, "y": tower["y_km"] / scale, "angle": angle}


def planet_public_dict(planet: Dict[str, Any]) -> Dict[str, Any]:
    public = {k: v for k, v in planet.items() if k != "towers"}
    public["dead"] = planet["id"] in state["deactivated_planets"]
    public["towers"] = [tower_public_dict(planet, tower) for tower in planet["towers"]]
    return public


def link_public_dict(link: Dict[str, Any]) -> Dict[str, Any]:
    dead = (not is_planet_active(link["from_planet"])) or (not is_planet_active(link["to_planet"])) or (not is_link_active(link["from_planet"], link["to_planet"]))
    return {**link, "from": link["from_planet"], "to": link["to_planet"], "void_km": round(link["void_distance_km"], 2), "void_au": round(link["void_distance_km"] / 1.496e8, 4), "tv_s": round(link["latency_breakdown"]["void_transit_total_ms"] / 1000.0, 6) if link["valid"] else None, "dead": dead or not link["valid"], "over_limit": not link["valid"]}


@app.get("/")
async def index() -> FileResponse:
    return FileResponse(FRONTEND_INDEX)


@app.get("/api/health")
async def health_check() -> Dict[str, str]:
    return {"status": "ok", "service": "Relic Ring Protocol API"}


@app.get("/api/universe")
async def get_universe() -> Dict[str, Any]:
    planets = [planet_public_dict(p) for p in state["planets_by_id"].values()]
    unique_links = [link for link in state["all_links"] if link["from_planet"] < link["to_planet"]]
    links = [link_public_dict(link) for link in unique_links]
    return {"metadata": state["metadata"], "meta": state["metadata"], "planets": planets, "links": links, "edges": links, "dead_planets": sorted(state["deactivated_planets"]), "dead_links": [list(pair) for pair in sorted(state["deactivated_links"])]}


@app.post("/api/routes/shortest-path")
async def find_shortest_path_route(request_data: ShortestPathRequest) -> Dict[str, Any]:
    return find_route_response(request_data)


@app.post("/api/routes/shortest-path/without-planet")
async def find_shortest_path_without_planet(request_data: ShortestPathWithoutPlanetRequest) -> Dict[str, Any]:
    return find_route_response(request_data, extra_dead_planets={request_data.deactivated_planet})


@app.post("/api/failures/planets/{planet_id}")
async def deactivate_planet_route(planet_id: str) -> Dict[str, Any]:
    deactivate_planet(planet_id)
    return failure_state_response()


@app.delete("/api/failures/planets/{planet_id}")
async def restore_planet_route(planet_id: str) -> Dict[str, Any]:
    restore_planet(planet_id)
    return failure_state_response()


@app.post("/api/failures/links")
async def deactivate_link_route(request_data: LinkFailureRequest) -> Dict[str, Any]:
    deactivate_link(request_data.from_planet, request_data.to_planet)
    return failure_state_response()


@app.delete("/api/failures/links")
async def restore_link_route(request_data: LinkFailureRequest) -> Dict[str, Any]:
    restore_link(request_data.from_planet, request_data.to_planet)
    return failure_state_response()


@app.get("/api/failures")
async def get_failure_state() -> Dict[str, Any]:
    return failure_state_response()


@app.post("/api/routes/details")
async def get_route_details(request_data: ShortestPathRequest) -> Dict[str, Any]:
    route = find_route_response(request_data)
    if route["status"] != "delivered":
        return {"route_summary": route, "route_details": [], "message_logs": []}
    details = []
    for hop in route["hop_log"]:
        b = hop["latency_breakdown"]
        details.append({"hop": hop["hop_number"], "from": hop["from_planet"], "to": hop["to_planet"], "send_tower": hop["send_tower"], "receive_tower": hop["receive_tower"], "segments_inside_from_planet": b["segment_count"], "void_distance_km": hop["void_distance_km"], "fiber_delay_ms": b["fiber_delay_ms"], "tower_delay_ms": b["tower_processing_delay_ms"], "atmosphere_delay_ms": b["atmosphere_ms"], "void_delay_ms": b["void_ms"], "hop_total_ms": hop["latency_ms"]})
    return {"route_summary": {"status": route["status"], "route": route["route"], "total_latency_ms": route["total_latency_ms"], "total_hops": len(route["hop_log"])}, "route_details": details, "message_logs": route["hop_log"]}


async def generate_packet_log_stream(route_result: Dict[str, Any]):
    if route_result["status"] != "delivered":
        yield f"data: {json.dumps({'type': 'undeliverable', 'message': route_result.get('reason', 'No route found')})}\n\n"
        return
    yield f"data: {json.dumps({'type': 'packet_created', 'message': 'Packet created at ' + route_result['origin_id']})}\n\n"
    await asyncio.sleep(0.05)
    for hop in route_result["hop_log"]:
        yield f"data: {json.dumps({'type': 'conversion', 'message': 'Payload converted to Base ' + str(hop['to_codex']) + ' for ' + hop['to_planet']})}\n\n"
        await asyncio.sleep(0.05)
        yield f"data: {json.dumps({'type': 'send', 'message': 'Sent from ' + hop['from_planet'] + ' ' + hop['send_tower'] + ' to ' + hop['to_planet'] + ' ' + hop['receive_tower']})}\n\n"
        await asyncio.sleep(0.05)
        yield f"data: {json.dumps({'type': 'receive', 'message': 'Received at ' + hop['to_planet'] + ' ' + hop['receive_tower']})}\n\n"
        await asyncio.sleep(0.05)
    yield f"data: {json.dumps({'type': 'delivered', 'message': 'Message delivered to ' + route_result['destination_id']})}\n\n"


@app.get("/api/routes/stream-logs")
async def stream_route_logs(from_planet: str = Query(...), from_tower: int = Query(0), to_planet: str = Query(...), message: str = Query(...)) -> StreamingResponse:
    route = find_route_response(ShortestPathRequest(from_planet=from_planet, from_tower=from_tower, to_planet=to_planet, message=message))
    return StreamingResponse(generate_packet_log_stream(route), media_type="text/event-stream")


def legacy_send_response(route: Dict[str, Any]) -> Dict[str, Any]:
    if route["status"] != "delivered":
        return {"status": "UNDELIVERABLE", "reason": route.get("reason", "No valid route found"), "path": [], "hops": [], "log": [], "total_latency": 0}
    hops = []
    log = [{"time": "", "type": "info", "msg": f"Message created on <b>{route['origin_id']}</b>"}]
    total_void_km = 0.0
    for hop in route["hop_log"]:
        from_planet = state["planets_by_id"][hop["from_planet"]]
        to_planet = state["planets_by_id"][hop["to_planet"]]
        b = hop["latency_breakdown"]
        encoded = " ".join(hop["encoded_payload_for_next_planet"][:6]) + (" ..." if len(hop["encoded_payload_for_next_planet"]) > 6 else "")
        log.extend([
            {"time": "", "type": "encode", "msg": f"Payload -> <b>Base {hop['to_codex']}</b> (codex of {hop['to_planet']})"},
            {"time": "", "type": "send", "msg": f"Laser sent from <b>{hop['from_planet']} {hop['send_tower']}</b>"},
            {"time": "", "type": "receive", "msg": f"Arrived at <b>{hop['to_planet']} {hop['receive_tower']}</b>"},
            {"time": "", "type": "decode", "msg": f"Base {hop['to_codex']} decoded back to ASCII"},
        ])
        total_void_km += hop["void_distance_km"]
        hops.append({"hop": hop["hop_number"], "from_planet": hop["from_planet"], "to_planet": hop["to_planet"], "from_codex": from_planet["codex"], "to_codex": to_planet["codex"], "send_tower": parse_tower_index(hop["send_tower"]), "recv_tower": parse_tower_index(hop["receive_tower"]), "void_km": round(hop["void_distance_km"], 2), "void_au": round(hop["void_distance_km"] / 1.496e8, 4), "fiber_s": round(b["fiber_delay_ms"] / 1000.0, 6), "atm_s": round(b["atmosphere_ms"] / 1000.0, 6), "tower_s": round(b["tower_processing_delay_ms"] / 1000.0, 6), "void_s": round(b["void_ms"] / 1000.0, 6), "total_s": round(hop["latency_ms"] / 1000.0, 6), "encoded": encoded, "status": "Success"})
    log.append({"time": "", "type": "success", "msg": f"Delivered to <b>{route['destination_id']}</b>"})
    br = route["latency_breakdown"]
    return {"status": "DELIVERED", "path": route["route"], "hops": hops, "log": log, "total_latency": round(route["total_latency_ms"] / 1000.0, 6), "total_hops": len(hops), "total_void_km": round(total_void_km, 2), "fiber_s": round(br["fiber_delay_ms"] / 1000.0, 6), "atm_s": round(br["atmosphere_delay_ms"] / 1000.0, 6), "tower_s": round(br["tower_processing_delay_ms"] / 1000.0, 6)}


@app.post("/api/route")
async def legacy_route(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_data = ShortestPathRequest(from_planet=payload.get("source"), from_tower=int(payload.get("from_tower", 0)), to_planet=payload.get("destination"), message=payload.get("message", "route probe"))
    route = find_route_response(request_data)
    if route["status"] != "delivered":
        return {"status": "UNDELIVERABLE", "path": [], "latency": None}
    return {"status": "ROUTE_FOUND", "path": route["route"], "latency": round(route["total_latency_ms"] / 1000.0, 6)}


@app.post("/api/send")
async def legacy_send(payload: Dict[str, Any]) -> Dict[str, Any]:
    request_data = ShortestPathRequest(from_planet=payload.get("source"), from_tower=int(payload.get("from_tower", 0)), to_planet=payload.get("destination"), message=payload.get("message", "Hello, Universe!"))
    return legacy_send_response(find_route_response(request_data))


@app.post("/api/kill_planet")
async def legacy_kill_planet(payload: Dict[str, Any]) -> Dict[str, Any]:
    deactivate_planet(payload.get("planet"))
    return {"dead_planets": sorted(state["deactivated_planets"]), "dead_links": [list(pair) for pair in sorted(state["deactivated_links"])]}


@app.post("/api/kill_link")
async def legacy_kill_link(payload: Dict[str, Any]) -> Dict[str, Any]:
    deactivate_link(payload.get("planet1"), payload.get("planet2"))
    return {"dead_planets": sorted(state["deactivated_planets"]), "dead_links": [list(pair) for pair in sorted(state["deactivated_links"])]}


@app.post("/api/restore")
async def legacy_restore() -> Dict[str, str]:
    state["deactivated_planets"].clear()
    state["deactivated_links"].clear()
    return {"status": "restored"}


@app.post("/api/encode")
async def legacy_encode(payload: Dict[str, Any]) -> Dict[str, Any]:
    base = int(payload.get("base", 10))
    return {"encoded": ascii_values_to_codex(text_to_ascii_values(payload.get("message", "")), base), "base": base}


def void_distance_breakdown(planet_a: Dict[str, Any], planet_b: Dict[str, Any]) -> Dict[str, Any]:
    dx = planet_b["x"] - planet_a["x"]
    dy = planet_b["y"] - planet_a["y"]
    grid_dist = math.hypot(dx, dy)
    center_km = grid_dist * state["metadata"]["coordinate_scale_unit_km"]
    shell1 = planet_a["radius_km"] + planet_a["atmosphere_thickness_km"]
    shell2 = planet_b["radius_km"] + planet_b["atmosphere_thickness_km"]
    distance = calculate_void_distance_km(planet_a, planet_b)
    return {"dx": dx, "dy": dy, "grid_dist": round(grid_dist, 4), "center_km": round(center_km, 2), "shell1_km": round(shell1, 2), "shell2_km": round(shell2, 2), "L_km": round(distance, 2), "feasible": distance <= state["metadata"]["max_void_hop_distance_km"], "over_by_km": round(max(0.0, distance - state["metadata"]["max_void_hop_distance_km"]), 2)}


def tv_breakdown(planet_a: Dict[str, Any], planet_b: Dict[str, Any], void_distance_km: float) -> Dict[str, Any]:
    h1n1 = planet_a["atmosphere_thickness_km"] * planet_a["refraction_index"]
    h2n2 = planet_b["atmosphere_thickness_km"] * planet_b["refraction_index"]
    numerator = h1n1 + h2n2 + void_distance_km
    tv_s = numerator / state["metadata"]["speed_of_light_kms"]
    return {"h1": planet_a["atmosphere_thickness_km"], "n1": planet_a["refraction_index"], "h2": planet_b["atmosphere_thickness_km"], "n2": planet_b["refraction_index"], "h1n1": round(h1n1, 4), "h2n2": round(h2n2, 4), "L_km": round(void_distance_km, 2), "numerator_km": round(numerator, 4), "C_kms": state["metadata"]["speed_of_light_kms"], "Tv_s": round(tv_s, 6), "atm_s": round((h1n1 + h2n2) / state["metadata"]["speed_of_light_kms"], 6), "vac_s": round(void_distance_km / state["metadata"]["speed_of_light_kms"], 6)}


def enumerate_all_paths(source: str, destination: str) -> List[List[str]]:
    graph = {pid: [link["to_planet"] for link in links if is_link_active(link["from_planet"], link["to_planet"])] for pid, links in state["graph"].items() if is_planet_active(pid)}
    result: List[List[str]] = []

    def dfs(current: str, path: List[str], seen: Set[str]) -> None:
        if current == destination:
            result.append(path[:])
            return
        for neighbor in graph.get(current, []):
            if neighbor not in seen and is_planet_active(neighbor):
                seen.add(neighbor)
                path.append(neighbor)
                dfs(neighbor, path, seen)
                path.pop()
                seen.remove(neighbor)

    dfs(source, [source], {source})
    return result


def compute_path_latency_full(path: List[str]) -> Tuple[float, List[Dict[str, Any]]]:
    if len(path) < 2:
        return 0.0, []
    current_tower = 0
    total_ms = 0.0
    hops = []
    for index in range(len(path) - 1):
        link = state["links_by_key"][link_key(path[index], path[index + 1])]
        internal = calculate_internal_transit_delay_ms(state["planets_by_id"][path[index]], current_tower, parse_tower_index(link["send_tower"]), state["metadata"]["speed_of_light_kms"], state["metadata"]["fiber_speed_fraction"], state["metadata"]["tower_processing_delay_ms"])
        hop_ms = internal["internal_total_ms"] + link["latency_breakdown"]["void_transit_total_ms"]
        total_ms += hop_ms
        current_tower = parse_tower_index(link["receive_tower"])
        hops.append({"from": path[index], "to": path[index + 1], "L_km": round(link["void_distance_km"], 2), "Tv_s": round(link["latency_breakdown"]["void_transit_total_ms"] / 1000.0, 4), "Tp_s": round(internal["internal_total_ms"] / 1000.0, 4), "total_s": round(hop_ms / 1000.0, 4)})
    return round(total_ms / 1000.0, 6), hops


@app.post("/api/route_analysis")
async def legacy_route_analysis(payload: Dict[str, Any]) -> Dict[str, Any]:
    source = payload.get("source")
    destination = payload.get("destination")
    if source not in state["planets_by_id"] or destination not in state["planets_by_id"]:
        return {"error": "Unknown planet"}
    route = find_route_response(ShortestPathRequest(from_planet=source, from_tower=0, to_planet=destination, message="Hello"))
    all_paths = []
    for path in enumerate_all_paths(source, destination):
        latency, hops = compute_path_latency_full(path)
        all_paths.append({"path": path, "latency": latency, "feasible": True, "is_optimal": path == route.get("route"), "hops": hops, "hop_count": len(path) - 1})
    all_paths.sort(key=lambda item: item["latency"])

    planets = list(state["planets_by_id"].values())
    constraints = []
    for i, planet_a in enumerate(planets):
        for planet_b in planets[i + 1:]:
            breakdown = void_distance_breakdown(planet_a, planet_b)
            constraints.append({"from": planet_a["id"], "to": planet_b["id"], "x1": planet_a["x"], "y1": planet_a["y"], "x2": planet_b["x"], "y2": planet_b["y"], **breakdown, "tv": tv_breakdown(planet_a, planet_b, breakdown["L_km"]) if breakdown["feasible"] else None})
    constraints.sort(key=lambda item: item["L_km"])

    hop_math = []
    if route["status"] == "delivered":
        current_tower = 0
        for hop in route["hop_log"]:
            planet_a = state["planets_by_id"][hop["from_planet"]]
            planet_b = state["planets_by_id"][hop["to_planet"]]
            link = state["links_by_key"][link_key(planet_a["id"], planet_b["id"])]
            entry_tower = current_tower
            exit_tower = parse_tower_index(link["send_tower"])
            internal = calculate_internal_transit_delay_ms(planet_a, entry_tower, exit_tower, state["metadata"]["speed_of_light_kms"], state["metadata"]["fiber_speed_fraction"], state["metadata"]["tower_processing_delay_ms"])
            current_tower = parse_tower_index(link["receive_tower"])
            hop_math.append({"hop": hop["hop_number"], "from": planet_a["id"], "to": planet_b["id"], "void_distance": void_distance_breakdown(planet_a, planet_b), "void_travel": tv_breakdown(planet_a, planet_b, link["void_distance_km"]), "planet_transit": {"entry_tower": entry_tower, "exit_tower": exit_tower, "segments": internal["segment_count"], "towers_hit": internal["processing_tower_count"], "arc_km": internal["fiber_distance_km"], "fiber_s": internal["fiber_delay_ms"] / 1000.0, "tower_s": internal["tower_processing_delay_ms"] / 1000.0, "total_s": internal["internal_total_ms"] / 1000.0}, "constraint_ok": True, "encoding": {"source_codex": planet_a["codex"], "target_codex": planet_b["codex"], "sample_char": "H", "ascii_val": 72, "encoded": integer_to_base(72, planet_b["codex"]), "decoded_back": 72}})

    feasible_count = len([item for item in all_paths if item["feasible"]])
    return {"source": source, "destination": destination, "optimal_path": route.get("route", []), "optimal_latency": round(route.get("total_latency_ms", 0.0) / 1000.0, 6) if route["status"] == "delivered" else None, "all_paths": all_paths, "hop_math": hop_math, "constraint_analysis": constraints, "constants": {"C": state["metadata"]["speed_of_light_kms"], "S": state["metadata"]["coordinate_scale_unit_km"], "L_MAX": state["metadata"]["max_void_hop_distance_km"], "F": state["metadata"]["fiber_speed_fraction"], "DT": state["metadata"]["tower_processing_delay_ms"]}, "optimality_reason": "Expanded-state Dijkstra minimized total latency using planet and tower state." if route["status"] == "delivered" else "No feasible active route exists.", "total_paths_found": len(all_paths), "feasible_paths_count": feasible_count, "infeasible_paths_count": 0}


if __name__ == "__main__":
    import uvicorn

    print("Zeta-26 Relic Ring Protocol API starting on http://localhost:5000")
    uvicorn.run("app:app", host="127.0.0.1", port=5000, reload=False)


