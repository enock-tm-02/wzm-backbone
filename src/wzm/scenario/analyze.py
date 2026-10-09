"""Runs a full scenario: snap the work zone to the road network, find detours, pick the best one."""
from dataclasses import replace

from wzm.scenario.geo import M_PER_MILE, line_length_m
from wzm.scenario.impacts import DetourOption, Scenario, best_share, capacities, simulate, summarize, total_cost
from wzm.scenario.network import FREEWAY_CLASSES, Path, RoadNetwork, edges_not_in


def zone_attributes(path: Path) -> dict:
    """Road attributes of the dominant link along a snapped work zone, to prefill the form."""
    by_len: dict[tuple, float] = {}
    for e in path.edges:
        key = (e.name, e.highway, e.lanes, round(e.speed_mph))
        by_len[key] = by_len.get(key, 0) + e.length_m
    name, highway, lanes, speed = max(by_len, key=by_len.get)
    return {"road": name or highway.replace("_", " "), "highway": highway, "lanes": lanes,
            "speed_mph": speed, "facility": "freeway" if highway in FREEWAY_CLASSES else "arterial",
            "length_mi": round(path.length_m / M_PER_MILE, 3),
            "geometry": {"type": "LineString", "coordinates": path.coords}}


def find_detours(g: RoadNetwork, zone: Path, params: dict) -> list[dict]:
    """Candidate detours from upstream of the zone to downstream of it, avoiding the zone's links."""
    d = params["diversion"]
    zone_nodes = {e.u for e in zone.edges} | {e.v for e in zone.edges}
    up = g.extend(zone.edges[0].u, zone.edges[0], d["upstream_search_m"], upstream=True, avoid=zone_nodes)
    up_nodes = {e.u for e in up}
    down = g.extend(zone.edges[-1].v, zone.edges[-1], d["upstream_search_m"], upstream=False,
                    avoid=zone_nodes | up_nodes)
    through = Path(up + zone.edges + down)
    origin = through.edges[0].u
    dest = through.edges[-1].v
    out = []
    for alt in g.alternatives(origin, dest, banned=zone.keys, k=d["alternatives"], common=through.keys):
        off = edges_not_in(alt, through.keys)
        if not off:
            continue
        fwy_len = sum(e.length_m for e in off if e.highway in FREEWAY_CLASSES)
        off_len = sum(e.length_m for e in off)
        bottleneck = min(e.capacity_vph for e in off)
        out.append({
            "option": DetourOption(
                extra_time_min=max(0.0, (alt.time_s - through.time_s) / 60),
                extra_miles=max(0.0, (alt.length_m - through.length_m) / M_PER_MILE),
                spare_capacity_vph=bottleneck * d["detour_spare_capacity_share"],
                length_mi=off_len / M_PER_MILE,
                facility="freeway" if fwy_len > off_len / 2 else "arterial"),
            "roads": Path(off).road_names(),
            "geometry": {"type": "LineString", "coordinates": alt.coords},
            "bottleneck_capacity_vph": round(bottleneck),
        })
    return out


def analyze(sc: Scenario, zone: Path | None = None, network: RoadNetwork | None = None,
            manual_detours: list[DetourOption] | None = None, zone_coords: list | None = None) -> dict:
    warnings: list[str] = []
    if zone is not None:
        sc = replace(sc, length_mi=zone.length_m / M_PER_MILE)
        geometry = {"type": "LineString", "coordinates": zone.coords}
    elif zone_coords:
        sc = replace(sc, length_mi=line_length_m(zone_coords) / M_PER_MILE)
        geometry = {"type": "LineString", "coordinates": zone_coords}
    else:
        geometry = None
    if sc.lanes_closed >= sc.normal_lanes:
        sc = replace(sc, lanes_closed=sc.normal_lanes, diversion_share=1.0)

    candidates: list[dict] = []
    if network is not None and zone is not None:
        candidates = find_detours(network, zone, sc.params)
        if not candidates:
            warnings.append("No detour found on the road network around this work zone.")
    for i, m in enumerate(manual_detours or []):
        candidates.append({"option": m, "roads": [f"manual detour {i + 1}"], "geometry": None,
                           "bottleneck_capacity_vph": None})

    full_closure = sc.open_lanes == 0
    no_detour = summarize(sc, simulate(sc), 0.0)
    if full_closure and not candidates:
        warnings.append("Full closure with no detour: all traffic is stranded; add a detour.")

    total = total_cost
    detours = []
    for c in candidates:
        opt: DetourOption = c["option"]
        share = best_share(sc, opt)
        result = summarize(sc, simulate(sc, share, opt), share)
        peak_diverted = max((iv["diverted_vph"] for iv in result["intervals"]), default=0)
        if full_closure and peak_diverted > opt.spare_capacity_vph:
            warnings.append(f"Detour via {_via(c['roads'])} would carry {peak_diverted} veh/h, above its "
                            f"estimated spare capacity of {round(opt.spare_capacity_vph)} veh/h.")
        detours.append({
            "roads": c["roads"],
            "geometry": c["geometry"],
            "extra_time_min": round(opt.extra_time_min, 1),
            "extra_miles": round(opt.extra_miles, 2),
            "detour_miles": round(opt.length_mi, 2),
            "facility": opt.facility,
            "spare_capacity_vph": round(opt.spare_capacity_vph),
            "bottleneck_capacity_vph": c["bottleneck_capacity_vph"],
            "total_cost_usd": round(total(result)),
            "result": result,
        })
    detours.sort(key=lambda x: x["total_cost_usd"])
    for rank, dt in enumerate(detours, 1):
        dt["rank"] = rank

    best = detours[0] if detours else None
    if full_closure:
        recommendation = (f"Full closure: route traffic via {_via(best['roads'])}." if best
                          else "Full closure needs a detour; none was found.")
    elif best and best["result"]["diversion_share"] > 0 and total(best["result"]) < total(no_detour):
        recommendation = (f"Sign a detour via {_via(best['roads'])} and divert about "
                          f"{round(100 * best['result']['diversion_share'])}% of traffic: saves "
                          f"${round(total(no_detour) - total(best['result'])):,} over the work.")
    else:
        recommendation = "Keep traffic on the mainline: diverting does not reduce total user and crash cost."
    chosen = best["result"] if best and (full_closure or total(best["result"]) < total(no_detour)) else no_detour

    return {
        "work_zone": {"geometry": geometry, "length_mi": round(sc.length_mi, 3), "normal_lanes": sc.normal_lanes,
                      "lanes_closed": sc.lanes_closed, "open_lanes": sc.open_lanes,
                      "shoulder_closed": sc.shoulder_closed, "closure_hours": sc.closure_hours, "days": sc.days},
        "capacity": {k: round(v) for k, v in capacities(sc, night=False).items()},
        "recommendation": recommendation,
        "recommended": chosen,
        "without_diversion": no_detour,
        "detours": detours,
        "warnings": warnings,
        "assumptions": "Defaults in config/scenario_defaults.yaml are placeholders to calibrate locally.",
    }



def _via(roads: list[str]) -> str:
    named = [r for r in roads if r != "ramp"] or roads
    return " / ".join(named[:4])
