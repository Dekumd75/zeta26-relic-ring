import { useCallback, useEffect, useMemo, useRef, useState } from "react";

const API_BASE = import.meta.env.VITE_API_BASE || "";
const DEFAULT_MESSAGE = "Hello Zeta-26";

async function api(path, options = {}) {
  const response = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  if (!response.ok) {
    let detail = `Request failed: ${response.status}`;
    try {
      const data = await response.json();
      detail = data.detail || data.error || detail;
    } catch {
      // Keep default error.
    }
    throw new Error(detail);
  }
  return response.json();
}

function postJson(path, body) {
  return api(path, { method: "POST", body: JSON.stringify(body) });
}

function deleteJson(path, body) {
  return api(path, { method: "DELETE", body: JSON.stringify(body) });
}

function formatMs(ms) {
  if (!Number.isFinite(ms)) return "-";
  if (ms >= 1000) return `${(ms / 1000).toFixed(3)} s`;
  return `${ms.toFixed(2)} ms`;
}

function formatKm(km) {
  if (!Number.isFinite(km)) return "-";
  if (km >= 1_000_000) return `${(km / 1_000_000).toFixed(2)}M km`;
  return `${Math.round(km).toLocaleString()} km`;
}

function packetToRouteResult(packet) {
  return {
    status: packet.status,
    origin_id: packet.origin?.planet,
    destination_id: packet.destination?.planet,
    route: packet.route || [],
    total_latency_ms: packet.total_latency_ms,
    latency_breakdown: {
      void_delay_ms: packet.latency_breakdown_ms?.void || 0,
      atmosphere_delay_ms: packet.latency_breakdown_ms?.atmosphere || 0,
      fiber_delay_ms: packet.latency_breakdown_ms?.fiber || 0,
      tower_processing_delay_ms: packet.latency_breakdown_ms?.tower_processing || 0,
    },
    hop_log: (packet.hop_log || []).map((hop) => ({
      hop_number: hop.hop_index,
      from_planet: hop.from_planet,
      to_planet: hop.to_planet,
      send_tower: hop.send_tower,
      receive_tower: hop.receive_tower,
      encoded_payload_for_next_planet: String(hop.payload_encoded_for_next || "").split(" ").filter(Boolean),
      to_codex: hop.to_codex,
      void_distance_km: hop.void_distance_km,
      latency_ms: hop.latency_ms?.total || 0,
      latency_breakdown: hop.latency_ms || {},
      status: "sent",
    })),
  };
}

function routePairs(route) {
  const pairs = new Set();
  for (let i = 0; i < route.length - 1; i += 1) {
    pairs.add([route[i], route[i + 1]].sort().join("::"));
  }
  return pairs;
}

function towerIndex(value) {
  if (typeof value === "number") return value;
  const match = String(value || "T0").match(/\d+/);
  return match ? Number(match[0]) : 0;
}

function useUniverse() {
  const [universe, setUniverse] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const loadUniverse = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      setUniverse(await api("/api/universe"));
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadUniverse();
  }, [loadUniverse]);

  return { universe, loading, error, reload: loadUniverse };
}

function useCanvasScene({ universe, route, hopLog, packetKey }) {
  const canvasRef = useRef(null);
  const viewRef = useRef({ scale: 1, ox: 0, oy: 0, dragging: false, lastX: 0, lastY: 0 });
  const [hovered, setHovered] = useState(null);
  const stars = useMemo(() => Array.from({ length: 150 }, (_, i) => ({
    x: (Math.sin(i * 71.17) + 1) / 2,
    y: (Math.cos(i * 29.91) + 1) / 2,
    r: 0.4 + ((i * 13) % 17) / 18,
    a: 0.18 + ((i * 7) % 19) / 45,
  })), []);

  const bounds = useMemo(() => {
    const planets = universe?.planets || [];
    if (!planets.length) return null;
    const xs = planets.map((p) => p.x);
    const ys = planets.map((p) => p.y);
    return {
      minX: Math.min(...xs), maxX: Math.max(...xs),
      minY: Math.min(...ys), maxY: Math.max(...ys),
    };
  }, [universe]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !universe || !bounds) return undefined;
    const ctx = canvas.getContext("2d");
    const planets = universe.planets || [];
    const edges = universe.edges || universe.links || [];
    const planetsById = new Map(planets.map((planet) => [planet.id, planet]));
    const activeRoute = route || [];
    const activeHops = hopLog || [];
    const activePairs = routePairs(activeRoute);
    const towerRoles = new Map();
    const startedAt = performance.now();
    let frame = 0;
    let animationId = 0;

    activeHops.forEach((hop, index) => {
      const sendKey = `${hop.from_planet}:${towerIndex(hop.send_tower)}`;
      const receiveKey = `${hop.to_planet}:${towerIndex(hop.receive_tower)}`;
      towerRoles.set(sendKey, { type: "send", label: hop.send_tower, hop: index + 1 });
      towerRoles.set(receiveKey, { type: "receive", label: hop.receive_tower, hop: index + 1 });
    });

    function resize() {
      const rect = canvas.getBoundingClientRect();
      const dpr = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }

    function baseScale() {
      const rect = canvas.getBoundingClientRect();
      const spanX = Math.max(1, bounds.maxX - bounds.minX);
      const spanY = Math.max(1, bounds.maxY - bounds.minY);
      return Math.min((rect.width - 100) / spanX, (rect.height - 90) / spanY);
    }

    function project(x, y) {
      const rect = canvas.getBoundingClientRect();
      const view = viewRef.current;
      const scale = baseScale() * view.scale;
      const cx = (bounds.minX + bounds.maxX) / 2;
      const cy = (bounds.minY + bounds.maxY) / 2;
      return {
        x: rect.width / 2 + (x - cx) * scale + view.ox,
        y: rect.height / 2 - (y - cy) * scale + view.oy,
      };
    }

    function planetRadius(planet) {
      return Math.max(11, Math.min(28, 8 + Math.sqrt(planet.radius_km) / 12));
    }

    function towerPoint(planet, tower, lift = 8) {
      const p = project(planet.x, planet.y);
      const radius = planetRadius(planet);
      const angle = ((Math.PI * 2) / Math.max(1, planet.active_towers || 1)) * (tower?.idx ?? towerIndex(tower));
      return {
        x: p.x + Math.sin(angle) * (radius + lift),
        y: p.y - Math.cos(angle) * (radius + lift),
      };
    }

    function getTowerPoint(planetId, towerName) {
      const planet = planetsById.get(planetId);
      if (!planet) return null;
      return towerPoint(planet, { idx: towerIndex(towerName) }, 9);
    }

    function drawEdge(edge) {
      const from = planetsById.get(edge.from || edge.from_planet);
      const to = planetsById.get(edge.to || edge.to_planet);
      if (!from || !to) return;
      const a = project(from.x, from.y);
      const b = project(to.x, to.y);
      const dx = b.x - a.x;
      const dy = b.y - a.y;
      const length = Math.max(1, Math.hypot(dx, dy));
      const ux = dx / length;
      const uy = dy / length;
      const startOffset = planetRadius(from) + 10;
      const endOffset = planetRadius(to) + 10;
      const pair = [from.id, to.id].sort().join("::");
      const onRoute = activePairs.has(pair);
      const hasTowerRoute = activeHops.some((hop) => (
        [hop.from_planet, hop.to_planet].sort().join("::") === pair
      ));
      if (onRoute && hasTowerRoute) return;
      ctx.save();
      ctx.beginPath();
      ctx.moveTo(a.x + ux * startOffset, a.y + uy * startOffset);
      ctx.lineTo(b.x - ux * endOffset, b.y - uy * endOffset);
      if (edge.over_limit) {
        ctx.setLineDash([7, 8]);
        ctx.strokeStyle = "rgba(117, 130, 148, 0.32)";
        ctx.lineWidth = 1;
      } else if (edge.dead) {
        ctx.setLineDash([5, 6]);
        ctx.strokeStyle = "rgba(255, 77, 109, 0.5)";
        ctx.lineWidth = 1.2;
      } else if (onRoute) {
        ctx.strokeStyle = "rgba(95, 255, 180, 0.95)";
        ctx.shadowColor = "rgba(95, 255, 180, 0.45)";
        ctx.shadowBlur = 12;
        ctx.lineWidth = 3;
      } else {
        ctx.strokeStyle = "rgba(80, 184, 255, 0.28)";
        ctx.lineWidth = 1.4;
      }
      ctx.stroke();
      ctx.restore();
    }

    function drawPlanet(planet) {
      const p = project(planet.x, planet.y);
      const radius = planetRadius(planet);
      const dead = planet.dead;
      ctx.save();
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius + 8, 0, Math.PI * 2);
      ctx.fillStyle = dead ? "rgba(255, 77, 109, 0.08)" : "rgba(60, 180, 255, 0.08)";
      ctx.fill();
      ctx.beginPath();
      ctx.arc(p.x, p.y, radius, 0, Math.PI * 2);
      const gradient = ctx.createRadialGradient(p.x - radius / 3, p.y - radius / 3, 2, p.x, p.y, radius);
      gradient.addColorStop(0, dead ? "#66313e" : "#8bdcff");
      gradient.addColorStop(1, dead ? "#240d16" : "#123354");
      ctx.fillStyle = gradient;
      ctx.fill();
      ctx.strokeStyle = dead ? "rgba(255, 77, 109, 0.85)" : "rgba(111, 222, 255, 0.75)";
      ctx.lineWidth = 1.4;
      ctx.stroke();
      ctx.fillStyle = dead ? "#ff8aa0" : "#eaf7ff";
      ctx.font = "600 12px Inter, system-ui, sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(planet.id, p.x, p.y + radius + 18);
      ctx.fillStyle = "rgba(212, 226, 241, 0.72)";
      ctx.font = "10px ui-monospace, SFMono-Regular, Consolas, monospace";
      ctx.fillText(`B${planet.codex} / T${planet.active_towers}`, p.x, p.y + radius + 32);
      for (const tower of planet.towers || []) {
        const t = towerPoint(planet, tower);
        const role = towerRoles.get(`${planet.id}:${tower.idx}`);
        ctx.beginPath();
        ctx.moveTo(p.x, p.y);
        ctx.lineTo(t.x, t.y);
        ctx.strokeStyle = role
          ? (role.type === "send" ? "rgba(255, 214, 102, 0.72)" : "rgba(95, 255, 180, 0.72)")
          : "rgba(170, 204, 226, 0.18)";
        ctx.lineWidth = role ? 1.4 : 0.7;
        ctx.stroke();
        ctx.beginPath();
        ctx.arc(t.x, t.y, role ? 5.2 : 3.4, 0, Math.PI * 2);
        ctx.fillStyle = dead
          ? "rgba(255, 77, 109, 0.55)"
          : role?.type === "send"
            ? "rgba(255, 214, 102, 0.96)"
            : role?.type === "receive"
              ? "rgba(95, 255, 180, 0.96)"
              : "rgba(226, 237, 248, 0.82)";
        ctx.fill();
        ctx.strokeStyle = role ? "rgba(255, 255, 255, 0.86)" : "rgba(255, 255, 255, 0.32)";
        ctx.lineWidth = role ? 1.5 : 0.8;
        ctx.stroke();
        if (role) {
          ctx.fillStyle = role.type === "send" ? "#ffd666" : "#5fffb4";
          ctx.font = "700 10px Montserrat, Inter, system-ui, sans-serif";
          ctx.fillText(`${role.label} ${role.type === "send" ? "SEND" : "RECV"}`, t.x, t.y - 9);
        }
      }
      ctx.restore();
    }

    function drawPacket() {
      const segmentCount = activeHops.length || Math.max(0, activeRoute.length - 1);
      if (!segmentCount) return;
      const duration = 1800 + segmentCount * 360;
      const t = ((performance.now() - startedAt) % duration) / duration;
      const segFloat = t * segmentCount;
      const seg = Math.min(segmentCount - 1, Math.floor(segFloat));
      const local = segFloat - seg;
      const hop = activeHops[seg];
      const a = planetsById.get(activeRoute[seg]);
      const b = planetsById.get(activeRoute[seg + 1]);
      const pa = hop ? getTowerPoint(hop.from_planet, hop.send_tower) : (a ? project(a.x, a.y) : null);
      const pb = hop ? getTowerPoint(hop.to_planet, hop.receive_tower) : (b ? project(b.x, b.y) : null);
      if (!pa || !pb) return;
      const x = pa.x + (pb.x - pa.x) * local;
      const y = pa.y + (pb.y - pa.y) * local;
      const angle = Math.atan2(pb.y - pa.y, pb.x - pa.x);
      const trailX = x - Math.cos(angle) * 16;
      const trailY = y - Math.sin(angle) * 16;
      ctx.save();
      ctx.lineCap = "round";
      ctx.beginPath();
      ctx.moveTo(trailX, trailY);
      ctx.lineTo(x, y);
      ctx.strokeStyle = "rgba(255, 236, 130, 0.86)";
      ctx.shadowColor = "rgba(255, 214, 102, 0.86)";
      ctx.shadowBlur = 24;
      ctx.lineWidth = 6;
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(x, y, 8, 0, Math.PI * 2);
      ctx.fillStyle = "#fff6c7";
      ctx.shadowColor = "rgba(255, 246, 199, 0.95)";
      ctx.shadowBlur = 28;
      ctx.fill();
      ctx.strokeStyle = "rgba(3, 18, 32, 0.9)";
      ctx.lineWidth = 2;
      ctx.stroke();
      ctx.restore();
    }

    function drawTowerLinks() {
      activeHops.forEach((hop) => {
        const a = getTowerPoint(hop.from_planet, hop.send_tower);
        const b = getTowerPoint(hop.to_planet, hop.receive_tower);
        if (!a || !b) return;
        ctx.save();
        ctx.beginPath();
        ctx.moveTo(a.x, a.y);
        ctx.lineTo(b.x, b.y);
        ctx.strokeStyle = "rgba(95, 255, 180, 0.96)";
        ctx.shadowColor = "rgba(95, 255, 180, 0.52)";
        ctx.shadowBlur = 14;
        ctx.lineWidth = 3;
        ctx.stroke();
        ctx.globalCompositeOperation = "lighter";
        ctx.strokeStyle = "rgba(255, 214, 102, 0.54)";
        ctx.lineWidth = 1.2;
        ctx.stroke();
        ctx.restore();
      });
    }

    function draw() {
      frame += 1;
      const rect = canvas.getBoundingClientRect();
      ctx.clearRect(0, 0, rect.width, rect.height);
      const bg = ctx.createRadialGradient(rect.width * 0.45, rect.height * 0.4, 10, rect.width / 2, rect.height / 2, Math.max(rect.width, rect.height) * 0.75);
      bg.addColorStop(0, "#081526");
      bg.addColorStop(1, "#020407");
      ctx.fillStyle = bg;
      ctx.fillRect(0, 0, rect.width, rect.height);
      for (const star of stars) {
        ctx.beginPath();
        ctx.arc(star.x * rect.width, star.y * rect.height, star.r, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(230, 246, 255, ${star.a})`;
        ctx.fill();
      }
      edges.forEach(drawEdge);
      drawTowerLinks();
      planets.forEach(drawPlanet);
      drawPacket();
      animationId = requestAnimationFrame(draw);
    }

    resize();
    draw();
    window.addEventListener("resize", resize);

    function pointerPosition(event) {
      const rect = canvas.getBoundingClientRect();
      return { x: event.clientX - rect.left, y: event.clientY - rect.top };
    }

    function findPlanetAt(point) {
      return planets.find((planet) => {
        const p = project(planet.x, planet.y);
        return Math.hypot(point.x - p.x, point.y - p.y) <= planetRadius(planet) + 8;
      });
    }

    function onPointerMove(event) {
      const point = pointerPosition(event);
      const view = viewRef.current;
      if (view.dragging) {
        view.ox += point.x - view.lastX;
        view.oy += point.y - view.lastY;
        view.lastX = point.x;
        view.lastY = point.y;
        return;
      }
      const planet = findPlanetAt(point);
      canvas.style.cursor = planet ? "pointer" : "grab";
      setHovered(planet ? { planet, x: point.x, y: point.y } : null);
    }

    function onPointerDown(event) {
      const point = pointerPosition(event);
      Object.assign(viewRef.current, { dragging: true, lastX: point.x, lastY: point.y });
      canvas.setPointerCapture?.(event.pointerId);
    }

    function onPointerUp() {
      viewRef.current.dragging = false;
    }

    function onWheel(event) {
      event.preventDefault();
      const factor = event.deltaY > 0 ? 0.92 : 1.08;
      viewRef.current.scale = Math.max(0.55, Math.min(2.8, viewRef.current.scale * factor));
    }

    canvas.addEventListener("pointermove", onPointerMove);
    canvas.addEventListener("pointerdown", onPointerDown);
    canvas.addEventListener("pointerup", onPointerUp);
    canvas.addEventListener("pointerleave", onPointerUp);
    canvas.addEventListener("wheel", onWheel, { passive: false });
    return () => {
      cancelAnimationFrame(animationId);
      window.removeEventListener("resize", resize);
      canvas.removeEventListener("pointermove", onPointerMove);
      canvas.removeEventListener("pointerdown", onPointerDown);
      canvas.removeEventListener("pointerup", onPointerUp);
      canvas.removeEventListener("pointerleave", onPointerUp);
      canvas.removeEventListener("wheel", onWheel);
    };
  }, [universe, bounds, route, hopLog, packetKey, stars]);

  const resetView = useCallback(() => {
    viewRef.current = { scale: 1, ox: 0, oy: 0, dragging: false, lastX: 0, lastY: 0 };
  }, []);

  return { canvasRef, hovered, resetView };
}

function MapPanel({ universe, route, hopLog, packetKey }) {
  const { canvasRef, hovered, resetView } = useCanvasScene({ universe, route, hopLog, packetKey });
  return (
    <section className="map-panel" aria-label="Universe map">
      <canvas ref={canvasRef} className="universe-canvas" />
      <div className="map-tools">
        <div className="map-title">Zeta-26 relay field</div>
        <div className="legend">
          <span><i className="line route" /> Active route</span>
          <span><i className="line link" /> Valid link</span>
          <span><i className="line blocked" /> Blocked link</span>
        </div>
      </div>
      <button className="map-reset" type="button" onClick={resetView}>Reset view</button>
      {hovered && (
        <div className="tooltip" style={{ left: hovered.x + 14, top: hovered.y + 14 }}>
          <strong>{hovered.planet.id}</strong>
          <span>Base {hovered.planet.codex}</span>
          <span>{hovered.planet.active_towers} towers</span>
          <span>{hovered.planet.dead ? "Deactivated" : "Active"}</span>
        </div>
      )}
    </section>
  );
}

function StatusBadge({ status }) {
  const label = status === "delivered" ? "Delivered" : status === "undeliverable" ? "Undeliverable" : status === "route" ? "Route ready" : "Idle";
  return <span className={`status-badge ${status || "idle"}`}>{label}</span>;
}

function RoutePath({ route }) {
  if (!route?.length) return <div className="route-path empty">No active route</div>;
  return (
    <div className="route-path">
      {route.map((planet, index) => (
        <span className="route-node" key={`${planet}-${index}`}>{planet}{index < route.length - 1 ? <b>{"->"}</b> : null}</span>
      ))}
    </div>
  );
}

function Controls({ universe, selected, setSelected, fromTower, setFromTower, message, setMessage, onFindRoute, onSend, busy, onDeactivatePlanet, onDeactivateLink, onRestorePlanet, onRestoreLink, onRestoreAll }) {
  const planets = universe?.planets || [];
  const origin = planets.find((planet) => planet.id === selected.from);
  const towers = Array.from({ length: origin?.active_towers || 0 }, (_, i) => i);
  const activeLinks = (universe?.links || universe?.edges || []).filter((edge) => !edge.over_limit);

  return (
    <aside className="side-panel" aria-label="Routing controls">
      <section className="panel-section">
        <div className="section-title">Packet route</div>
        <label>
          Origin planet
          <select value={selected.from} onChange={(event) => { setSelected((v) => ({ ...v, from: event.target.value })); setFromTower(0); }}>
            {planets.map((planet) => <option key={planet.id} value={planet.id}>{planet.id}</option>)}
          </select>
        </label>
        <label>
          Origin tower
          <select value={fromTower} onChange={(event) => setFromTower(Number(event.target.value))}>
            {towers.map((tower) => <option key={tower} value={tower}>T{tower}</option>)}
          </select>
        </label>
        <label>
          Destination planet
          <select value={selected.to} onChange={(event) => setSelected((v) => ({ ...v, to: event.target.value }))}>
            {planets.map((planet) => <option key={planet.id} value={planet.id}>{planet.id}</option>)}
          </select>
        </label>
        <label>
          Message payload
          <textarea value={message} onChange={(event) => setMessage(event.target.value)} maxLength={240} />
        </label>
        <div className="button-row">
          <button type="button" className="button secondary" onClick={onFindRoute} disabled={busy}>Find path</button>
          <button type="button" className="button primary" onClick={onSend} disabled={busy}>Send packet</button>
        </div>
      </section>

      <section className="panel-section">
        <div className="section-title">Failure controls</div>
        <div className="failure-list">
          {planets.map((planet) => (
            <div className="failure-row" key={planet.id}>
              <span>{planet.id}</span>
              {planet.dead ? (
                <button type="button" onClick={() => onRestorePlanet(planet.id)}>Restore</button>
              ) : (
                <button type="button" onClick={() => onDeactivatePlanet(planet.id)}>Deactivate</button>
              )}
            </div>
          ))}
        </div>
        <div className="link-grid">
          {activeLinks.slice(0, 8).map((link) => {
            const from = link.from || link.from_planet;
            const to = link.to || link.to_planet;
            const dead = link.dead;
            return (
              <button key={`${from}-${to}`} type="button" className={dead ? "link-toggle dead" : "link-toggle"} onClick={() => dead ? onRestoreLink(from, to) : onDeactivateLink(from, to)}>
                {from} - {to}
              </button>
            );
          })}
        </div>
        <button className="button secondary full" type="button" onClick={onRestoreAll}>Restore network</button>
      </section>
    </aside>
  );
}

function Summary({ routeResult, packetsSent, packetResult, onDownloadPacket }) {
  const breakdown = routeResult?.latency_breakdown || {};
  const total = routeResult?.total_latency_ms || 0;
  const values = [
    ["Fiber", breakdown.fiber_delay_ms || 0, "fiber"],
    ["Atmosphere", breakdown.atmosphere_delay_ms || 0, "atm"],
    ["Tower", breakdown.tower_processing_delay_ms || 0, "tower"],
    ["Void", breakdown.void_delay_ms || 0, "void"],
  ];
  return (
    <section className="summary-panel">
      <div className="summary-header">
        <StatusBadge status={routeResult?.status || "idle"} />
        <span>{packetsSent} packets sent</span>
      </div>
      <RoutePath route={routeResult?.route || []} />
      <div className="stat-grid">
        <div><span>Total latency</span><strong>{total ? formatMs(total) : "-"}</strong></div>
        <div><span>Hops</span><strong>{routeResult?.hop_log?.length ?? "-"}</strong></div>
        <div><span>Origin</span><strong>{routeResult?.origin_id || "-"}</strong></div>
        <div><span>Destination</span><strong>{routeResult?.destination_id || "-"}</strong></div>
      </div>
      <div className="latency-bar" aria-label="Latency breakdown">
        {values.map(([label, value, cls]) => (
          <i key={label} className={cls} style={{ width: `${total ? Math.max(1, (value / total) * 100) : 25}%` }} />
        ))}
      </div>
      <div className="latency-legend">
        {values.map(([label, value, cls]) => <span key={label}><i className={cls} />{label}: {formatMs(value)}</span>)}
      </div>
      <button className="button download full" type="button" onClick={onDownloadPacket} disabled={!packetResult?.packet_id}>
        Download Final Packet JSON
      </button>
      {packetResult?.packet_id ? <div className="packet-id">packet_id: {packetResult.packet_id}</div> : null}
    </section>
  );
}

function HopTable({ hops }) {
  return (
    <section className="table-panel">
      <div className="section-title">Hop telemetry</div>
      <div className="table-scroll">
        <table>
          <thead>
            <tr>
              <th>Hop</th><th>From</th><th>To</th><th>Send</th><th>Receive</th><th>Void</th><th>Latency</th><th>Payload</th>
            </tr>
          </thead>
          <tbody>
            {hops?.length ? hops.map((hop) => (
              <tr key={hop.hop_number}>
                <td>{hop.hop_number}</td>
                <td>{hop.from_planet}</td>
                <td>{hop.to_planet}</td>
                <td>{hop.send_tower}</td>
                <td>{hop.receive_tower}</td>
                <td>{formatKm(hop.void_distance_km)}</td>
                <td>{formatMs(hop.latency_ms)}</td>
                <td className="payload">{hop.encoded_payload_for_next_planet.slice(0, 5).join(" ")}</td>
              </tr>
            )) : (
              <tr><td colSpan="8" className="empty-cell">Send a packet to inspect hop data.</td></tr>
            )}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function EventLog({ logs }) {
  return (
    <section className="log-panel">
      <div className="section-title">Packet log</div>
      <div className="log-scroll">
        {logs.length ? logs.map((log, index) => (
          <div className={`log-row ${log.type}`} key={`${log.message}-${index}`}>
            <span>{log.type}</span>
            <p>{log.message}</p>
          </div>
        )) : <div className="empty-log">No packet activity yet.</div>}
      </div>
    </section>
  );
}

export default function App() {
  const { universe, loading, error, reload } = useUniverse();
  const [selected, setSelected] = useState({ from: "", to: "" });
  const [fromTower, setFromTower] = useState(0);
  const [message, setMessage] = useState(DEFAULT_MESSAGE);
  const [routeResult, setRouteResult] = useState(null);
  const [packetResult, setPacketResult] = useState(null);
  const [logs, setLogs] = useState([]);
  const [busy, setBusy] = useState(false);
  const [packetsSent, setPacketsSent] = useState(0);
  const [packetKey, setPacketKey] = useState(0);

  useEffect(() => {
    if (!universe?.planets?.length || selected.from) return;
    setSelected({ from: universe.planets[0].id, to: universe.planets[universe.planets.length - 1].id });
  }, [universe, selected.from]);

  const addLog = useCallback((type, messageText) => {
    setLogs((current) => [{ type, message: messageText }, ...current].slice(0, 80));
  }, []);

  const validateSelection = useCallback(() => {
    if (!selected.from || !selected.to) throw new Error("Select origin and destination planets.");
    if (selected.from === selected.to) throw new Error("Origin and destination must be different.");
    if (!message.trim()) throw new Error("Enter a message payload.");
  }, [selected, message]);

  const runRoute = useCallback(async (sendPacket = false) => {
    try {
      validateSelection();
      setBusy(true);
      const result = sendPacket
        ? await postJson("/api/packets/send", {
            from_planet: selected.from,
            from_tower: `T${fromTower}`,
            to_planet: selected.to,
            message,
            disabled_planets: [],
          })
        : await postJson("/api/routes/shortest-path", {
            from_planet: selected.from,
            from_tower: fromTower,
            to_planet: selected.to,
            message,
          });
      const uiResult = result.packet_id ? packetToRouteResult(result) : result;
      setRouteResult(uiResult);
      setPacketResult(result.packet_id ? result : null);
      if (uiResult.status === "delivered") {
        setPacketKey((key) => key + 1);
        if (sendPacket) setPacketsSent((value) => value + 1);
        addLog("route", `Route ${uiResult.route.join(" -> ")} delivered in ${formatMs(uiResult.total_latency_ms)}.`);
        uiResult.hop_log.forEach((hop) => {
          addLog("send", `${hop.from_planet} ${hop.send_tower} -> ${hop.to_planet} ${hop.receive_tower}; Base ${hop.to_codex}.`);
        });
      } else {
        addLog("error", uiResult.reason || "No valid route found.");
      }
    } catch (err) {
      addLog("error", err.message);
    } finally {
      setBusy(false);
    }
  }, [addLog, fromTower, message, selected, validateSelection]);

  const mutateFailure = useCallback(async (action) => {
    try {
      setBusy(true);
      await action();
      await reload();
      setRouteResult(null);
      setPacketResult(null);
    } catch (err) {
      addLog("error", err.message);
    } finally {
      setBusy(false);
    }
  }, [addLog, reload]);

  const restoreAll = useCallback(() => mutateFailure(async () => {
    const failures = await api("/api/failures");
    await Promise.all([
      ...failures.deactivated_planets.map((id) => api(`/api/failures/planets/${encodeURIComponent(id)}`, { method: "DELETE" })),
      ...failures.deactivated_links.map((link) => deleteJson("/api/failures/links", link)),
    ]);
    addLog("route", "Network restored.");
  }), [addLog, mutateFailure]);

  const downloadPacket = useCallback(() => {
    if (!packetResult?.packet_id) return;
    const href = `${API_BASE}/api/packets/${packetResult.packet_id}/download`;
    const link = document.createElement("a");
    link.href = href;
    link.download = `packet_${packetResult.packet_id}.json`;
    document.body.appendChild(link);
    link.click();
    link.remove();
  }, [packetResult]);

  const route = routeResult?.status === "delivered" ? routeResult.route : [];
  const activePlanets = universe?.planets?.filter((planet) => !planet.dead).length || 0;
  const activeLinks = (universe?.links || universe?.edges || []).filter((edge) => !edge.dead && !edge.over_limit).length;

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand-mark" aria-hidden="true">Z26</div>
        <div>
          <h1>Relic Ring Protocol</h1>
          <p>Minimum-latency packet routing simulator</p>
        </div>
        <div className="top-stats">
          <span><b>{activePlanets}</b> planets online</span>
          <span><b>{activeLinks}</b> valid links</span>
          <span><b>{packetsSent}</b> packets</span>
        </div>
      </header>

      {error && <div className="error-banner">{error}</div>}
      <main className="workspace">
        <MapPanel universe={universe} route={route} hopLog={routeResult?.hop_log || []} packetKey={packetKey} />
        <Controls
          universe={universe}
          selected={selected}
          setSelected={setSelected}
          fromTower={fromTower}
          setFromTower={setFromTower}
          message={message}
          setMessage={setMessage}
          onFindRoute={() => runRoute(false)}
          onSend={() => runRoute(true)}
          busy={busy || loading}
          onDeactivatePlanet={(id) => mutateFailure(async () => { await api(`/api/failures/planets/${encodeURIComponent(id)}`, { method: "POST" }); addLog("failure", `${id} deactivated.`); })}
          onRestorePlanet={(id) => mutateFailure(async () => { await api(`/api/failures/planets/${encodeURIComponent(id)}`, { method: "DELETE" }); addLog("route", `${id} restored.`); })}
          onDeactivateLink={(from, to) => mutateFailure(async () => { await postJson("/api/failures/links", { from_planet: from, to_planet: to }); addLog("failure", `${from} - ${to} deactivated.`); })}
          onRestoreLink={(from, to) => mutateFailure(async () => { await deleteJson("/api/failures/links", { from_planet: from, to_planet: to }); addLog("route", `${from} - ${to} restored.`); })}
          onRestoreAll={restoreAll}
        />
      </main>

      <footer className="inspector">
        <Summary routeResult={routeResult} packetsSent={packetsSent} packetResult={packetResult} onDownloadPacket={downloadPacket} />
        <HopTable hops={routeResult?.hop_log || []} />
        <EventLog logs={logs} />
      </footer>
    </div>
  );
}

