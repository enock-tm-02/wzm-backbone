// Map UI for the work zone scenario analysis. Talks to /scenario/* on the same server.
(() => {
  const $ = (sel) => document.querySelector(sel);
  const form = $("#form");
  const map = L.map("map").setView([39.5, -98.35], 4);
  window.wzmMap = map; // handy from the browser console
  L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap contributors",
  }).addTo(map);

  const css = (name) => getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  const layers = { zone: L.layerGroup().addTo(map), detours: L.layerGroup().addTo(map), clicks: L.layerGroup().addTo(map) };
  const state = { drawing: false, clicks: [], zoneCoords: null, result: null, view: "recommended", detourLines: [] };

  // ---- defaults -------------------------------------------------------------------
  fetch("../scenario/defaults").then((r) => r.json()).then((p) => {
    const v = p.value_of_time, c = p.crash;
    form.vot.value = v.personal_usd_per_person_hour;
    form.vot_truck.value = v.truck_usd_per_vehicle_hour;
    form.occ.value = v.car_occupancy;
    form.crash_rate.value = c.base_rate_per_mvmt.freeway;
    form.max_share.value = Math.round(p.diversion.max_share * 100);
    state.defaults = p;
  }).catch(() => {});

  // ---- closure controls -------------------------------------------------------------
  function refreshLanesClosed() {
    const n = +form.normal_lanes.value || 1;
    const sel = form.lanes_closed;
    const keep = +sel.value || 1;
    sel.innerHTML = "";
    for (let i = 1; i <= n; i++) {
      const o = document.createElement("option");
      o.value = i;
      o.textContent = i === n ? `${i} (full closure, all traffic detours)` : `${i} of ${n} (${n - i} open)`;
      sel.appendChild(o);
    }
    sel.value = Math.min(keep, n);
    $("#lanes-closed-wrap").hidden = form.closure.value !== "lanes";
  }
  form.normal_lanes.addEventListener("input", refreshLanesClosed);
  form.querySelectorAll("input[name=closure]").forEach((r) => r.addEventListener("change", refreshLanesClosed));
  form.facility.addEventListener("change", () => {
    if (state.defaults) form.crash_rate.value = state.defaults.crash.base_rate_per_mvmt[form.facility.value];
  });
  refreshLanesClosed();

  // ---- drawing the work zone -------------------------------------------------------
  $("#draw").addEventListener("click", () => {
    clearAll();
    state.drawing = true;
    document.body.classList.add("drawing");
    $("#seg-help").textContent = "Click the upstream end of the work zone.";
  });
  $("#clear").addEventListener("click", clearAll);

  function clearAll() {
    Object.values(layers).forEach((l) => l.clearLayers());
    Object.assign(state, { drawing: false, clicks: [], zoneCoords: null, snapped: false, result: null, detourLines: [] });
    document.body.classList.remove("drawing");
    $("#seg-info").textContent = "";
    $("#seg-help").textContent = "Click the upstream end, then the downstream end, in the direction of travel.";
    $("#results").hidden = true;
    $("#run").disabled = true;
  }

  map.on("click", async (e) => {
    if (!state.drawing) return;
    const pt = [e.latlng.lng, e.latlng.lat];
    state.clicks.push(pt);
    L.circleMarker(e.latlng, { radius: 6, color: css("--zone"), fillOpacity: 1 }).addTo(layers.clicks);
    if (state.clicks.length === 1) {
      $("#seg-help").textContent = "Now click the downstream end.";
      return;
    }
    state.drawing = false;
    document.body.classList.remove("drawing");
    $("#seg-help").textContent = "Following the road between your clicks...";
    try {
      const r = await fetch("../scenario/segment", {
        method: "POST", headers: { "content-type": "application/json" },
        body: JSON.stringify({ start: state.clicks[0], end: state.clicks[1] }),
      });
      if (!r.ok) throw new Error((await r.json()).detail || r.statusText);
      const seg = await r.json();
      state.zoneCoords = seg.geometry.coordinates;
      state.snapped = true;
      form.facility.value = seg.facility;
      form.normal_lanes.value = seg.lanes;
      form.free_flow_speed_mph.value = seg.speed_mph;
      form.work_zone_speed_mph.value = Math.max(25, seg.speed_mph - 10);
      form.facility.dispatchEvent(new Event("change"));
      refreshLanesClosed();
      setInfo(`${seg.road}, ${seg.length_mi.toFixed(2)} mi, ${seg.lanes} lane(s), ${seg.speed_mph} mph`);
      $("#seg-help").textContent = "Lanes and speed were read from OpenStreetMap; check them before you run.";
    } catch (err) {
      state.zoneCoords = state.clicks.slice();
      state.snapped = false;
      setInfo("Straight line between your clicks");
      $("#seg-help").textContent = `Road network not available (${err.message}). Enter lanes and speed yourself; detours will not be searched.`;
    }
    drawZone();
    $("#run").disabled = false;
  });

  function setInfo(text) { $("#seg-info").textContent = text; }

  function drawZone() {
    layers.zone.clearLayers();
    const ll = state.zoneCoords.map(([lon, lat]) => [lat, lon]);
    const line = L.polyline(ll, { color: css("--zone"), weight: 8, opacity: 0.9 }).addTo(layers.zone);
    line.bindTooltip("Work zone");
    map.fitBounds(line.getBounds().pad(1.5));
  }

  // ---- analysis ----------------------------------------------------------------------
  const hours = (t) => { const [h, m] = t.split(":").map(Number); return h + m / 60; };

  function payload() {
    const n = +form.normal_lanes.value;
    const closure = form.closure.value;
    const params = {
      value_of_time: { personal_usd_per_person_hour: +form.vot.value, truck_usd_per_vehicle_hour: +form.vot_truck.value,
                       car_occupancy: +form.occ.value },
      diversion: { max_share: +form.max_share.value / 100 },
      crash: { base_rate_per_mvmt: { [form.facility.value]: +form.crash_rate.value } },
    };
    if (!form.vot.value) delete params.value_of_time;
    if (!form.crash_rate.value) delete params.crash;
    let end = hours(form.end.value);
    if (end === 0) end = 24;
    return {
      coordinates: state.clicks,
      snap_to_network: !!state.snapped,
      facility: form.facility.value,
      normal_lanes: n,
      lanes_closed: closure === "lanes" ? +form.lanes_closed.value : 0,
      shoulder_closed: closure === "shoulder",
      free_flow_speed_mph: +form.free_flow_speed_mph.value,
      work_zone_speed_mph: +form.work_zone_speed_mph.value,
      aadt: +form.aadt.value,
      heavy_vehicle_pct: +form.heavy_vehicle_pct.value,
      start_hour: hours(form.start.value),
      end_hour: end,
      days: +form.days.value,
      hard_barrier: form.hard_barrier.checked,
      params,
    };
  }

  form.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = $("#run");
    btn.disabled = true;
    btn.textContent = "Analyzing...";
    try {
      const r = await fetch("../scenario/analyze", {
        method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(payload()),
      });
      const body = await r.json();
      if (!r.ok) throw new Error(typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail));
      state.result = body;
      render();
    } catch (err) {
      alert(`Analysis failed: ${err.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "Analyze scenario";
    }
  });

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x === b));
    state.view = b.dataset.view;
    renderSummary(state.result[state.view]);
  }));

  // ---- rendering -----------------------------------------------------------------------
  const fmt = (n, d = 0) => Number(n).toLocaleString(undefined, { maximumFractionDigits: d, minimumFractionDigits: d });
  const money = (n) => "$" + fmt(n);
  const pct = (p) => (p * 100 < 1 && p > 0 ? "<1" : fmt(p * 100)) + "%";

  function render() {
    const res = state.result;
    $("#results").hidden = false;
    $("#recommendation").textContent = res.recommendation;
    const w = $("#warnings");
    w.innerHTML = "";
    res.warnings.forEach((t) => { const li = document.createElement("li"); li.textContent = t; w.appendChild(li); });
    if (res.work_zone.geometry) { state.zoneCoords = res.work_zone.geometry.coordinates; drawZone(); }
    state.view = "recommended";
    document.querySelectorAll(".tabs button").forEach((x) => x.classList.toggle("on", x.dataset.view === "recommended"));
    renderSummary(res.recommended);
    renderDetours(res.detours);
    $("#results").scrollIntoView({ behavior: "smooth" });
  }

  function renderSummary(r) {
    const o = r.operations, c = r.user_cost, s = r.safety;
    const tiles = [
      [`${fmt(o.max_queue_miles, 2)} mi`, "Longest queue"],
      [`${fmt(o.avg_delay_min_per_vehicle, 1)} min`, "Average delay per vehicle"],
      [`${fmt(o.delay_veh_hours_per_day)} veh-h`, "Delay per day"],
      [money(c.total_usd), `User cost, ${state.result.work_zone.days} day(s)`],
      [pct(s.probability_any_crash), "Chance of at least one crash"],
      [`${fmt(s.crash_risk_ratio ?? 0, 2)}x`, "Crash risk vs. no work zone"],
      [pct(s.probability_fatal_or_serious_injury), "Chance of a fatal or serious injury crash"],
      [`${fmt(o.vehicles_diverted_per_day)} / day`, `Vehicles diverted (${fmt(r.diversion_share * 100)}%)`],
    ];
    if (o.max_detour_queued_vehicles > 0) tiles.push([`${fmt(o.max_detour_queued_vehicles)} veh`, "Queue at the detour bottleneck"]);
    const box = $("#kpis");
    box.innerHTML = "";
    tiles.forEach(([v, label]) => {
      const d = document.createElement("div");
      d.className = "kpi";
      const b = document.createElement("b"); b.textContent = v;
      const sp = document.createElement("span"); sp.textContent = label;
      d.append(b, sp);
      box.appendChild(d);
    });
    renderChart(r.intervals);
  }

  function renderChart(iv) {
    const el = $("#chart");
    if (!iv.length) { el.textContent = "No intervals."; return; }
    const W = 360, H = 150, P = { l: 46, r: 8, t: 8, b: 22 };
    const max = Math.max(0.1, ...iv.map((i) => i.queue_miles));
    const x = (i) => P.l + (i / Math.max(1, iv.length - 1)) * (W - P.l - P.r);
    const y = (v) => H - P.b - (v / max) * (H - P.t - P.b);
    const closureEnd = iv.findIndex((i) => !i.in_closure);
    const shadeW = closureEnd === -1 ? iv.length - 1 : closureEnd;
    const pts = iv.map((i, k) => `${x(k).toFixed(1)},${y(i.queue_miles).toFixed(1)}`).join(" ");
    const step = Math.max(1, Math.ceil(iv.length / 6));
    const ticks = iv.map((i, k) => (k % step === 0 ? `<text x="${x(k)}" y="${H - 6}" text-anchor="middle">${i.time}</text>` : "")).join("");
    el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Queue length over time">
      <rect x="${P.l}" y="${P.t}" width="${x(shadeW) - P.l}" height="${H - P.t - P.b}" fill="${css("--zone")}" opacity="0.08"/>
      <line x1="${P.l}" x2="${W - P.r}" y1="${y(0)}" y2="${y(0)}" stroke="${css("--line")}"/>
      <text x="${P.l - 4}" y="${y(max) + 4}" text-anchor="end">${fmt(max, 1)} mi</text>
      <text x="${P.l - 4}" y="${y(0)}" text-anchor="end">0</text>
      <polyline points="${pts}" fill="none" stroke="${css("--accent")}" stroke-width="2"/>
      ${ticks}
    </svg><p class="muted">Shaded: closure in place. Line: queue length (miles).</p>`;
  }

  function renderDetours(detours) {
    layers.detours.clearLayers();
    state.detourLines = [];
    const tbody = $("#detours tbody");
    tbody.innerHTML = "";
    if (!detours.length) {
      const tr = document.createElement("tr");
      const td = document.createElement("td"); td.colSpan = 5; td.textContent = "No detours found.";
      tr.appendChild(td); tbody.appendChild(tr);
      return;
    }
    [...detours].reverse().forEach((d) => {
      if (!d.geometry) return;
      const best = d.rank === 1;
      const line = L.polyline(d.geometry.coordinates.map(([lon, lat]) => [lat, lon]), {
        color: best ? css("--best") : css("--alt"), weight: best ? 6 : 4, opacity: best ? 0.9 : 0.7,
        dashArray: best ? null : "6 6",
      }).addTo(layers.detours);
      line.bindTooltip(`Detour ${d.rank}: +${d.extra_time_min} min, +${d.extra_miles} mi`);
      state.detourLines[d.rank] = line;
    });
    detours.forEach((d) => {
      const tr = document.createElement("tr");
      const cells = [d.rank, (d.roads.filter((r) => r !== "ramp").join(" > ") || "ramps only"), fmt(d.extra_time_min, 1),
                     `${fmt(d.result.diversion_share * 100)}%`, money(d.total_cost_usd)];
      cells.forEach((v, k) => { const td = document.createElement("td"); td.textContent = v; if (k > 1) td.className = "num"; tr.appendChild(td); });
      tr.addEventListener("click", () => {
        tbody.querySelectorAll("tr").forEach((x) => x.classList.toggle("sel", x === tr));
        renderSummary(d.result);
        const line = state.detourLines[d.rank];
        if (line) { line.bringToFront(); map.fitBounds(line.getBounds().pad(0.3)); }
      });
      tbody.appendChild(tr);
    });
  }
})();
