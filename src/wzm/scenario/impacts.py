"""Operational, cost and safety impacts of one work zone scenario.

Per 15-minute interval over the closure window (plus a recovery period for the queue to clear):
  * capacity: HCM 7 Ch. 10 work zone capacity for lane closures (baseline_hcm.py); a calibrated
    factor on base capacity for shoulder-only closures
  * queue: deterministic input-output model, discharging at the queue discharge rate once broken down
  * delay: queue delay + reduced-speed delay through the zone + extra travel time of diverted traffic
  * user cost: delay x value of time (cars x occupancy, trucks per vehicle) + detour operating cost
  * crashes: rate x VMT x crash modification factors, with a multiplier on travel inside the queue;
    Poisson probability of at least one crash, split by KABCO severity
"""
import math
from dataclasses import dataclass, field

from wzm.models.baseline_hcm import ALPHA_WZ, QUEUE_DENSITY, WorkZone, capacity_vph, discharge_vph

INTERVAL_H = 0.25


@dataclass
class DetourOption:
    extra_time_min: float           # free-flow detour time minus free-flow through time
    extra_miles: float
    spare_capacity_vph: float       # what the detour can absorb from the work zone
    length_mi: float = 0.0
    facility: str = "arterial"      # sets the crash rate used for diverted travel


@dataclass
class Scenario:
    normal_lanes: int
    lanes_closed: int = 0
    shoulder_closed: bool = False
    length_mi: float = 1.0
    facility: str = "freeway"
    free_flow_speed_mph: float = 65
    work_zone_speed_mph: float = 55
    aadt: float | None = None
    hourly_volume_vph: list[float] | None = None   # 24 values, analysed direction; overrides aadt
    heavy_vehicle_pct: float = 8.0
    start_hour: float = 9.0
    end_hour: float = 15.0
    days: int = 1
    hard_barrier: bool = False
    lateral_distance_ft: float = 2.0
    diversion_share: float | None = None            # None = choose the cost-minimising share
    params: dict = field(default_factory=dict)

    @property
    def open_lanes(self) -> int:
        return self.normal_lanes - self.lanes_closed

    @property
    def closure_hours(self) -> float:
        end = self.end_hour if self.end_hour > self.start_hour else self.end_hour + 24
        return end - self.start_hour


def hourly_demand(sc: Scenario) -> list[float]:
    """Directional demand (veh/h) for each hour 0..23."""
    if sc.hourly_volume_vph:
        if len(sc.hourly_volume_vph) != 24:
            raise ValueError("hourly_volume_vph needs 24 values")
        return list(sc.hourly_volume_vph)
    if not sc.aadt:
        raise ValueError("Give either aadt or hourly_volume_vph")
    d = sc.params["demand"]
    return [sc.aadt * d["directional_split"] * s for s in d["hourly_share"]]


def _is_night(hour: float, night: list[int]) -> bool:
    start, end = night
    h = hour % 24
    return h >= start or h < end if start > end else start <= h < end


def _f_hv(sc: Scenario) -> float:
    return 1.0 / (1.0 + sc.heavy_vehicle_pct / 100 * (2.0 - 1))


def capacities(sc: Scenario, night: bool) -> dict[str, float]:
    """Normal capacity and work zone pre-breakdown / queue discharge capacity, veh/h."""
    cap_p = sc.params["capacity"]
    base = cap_p["base_lane_capacity_vph"].get(sc.facility, 2200)
    normal = base * sc.normal_lanes * _f_hv(sc)
    if sc.open_lanes <= 0:
        return {"normal_vph": normal, "work_zone_vph": 0.0, "discharge_vph": 0.0}
    if sc.lanes_closed > 0:
        wz = WorkZone(normal_lanes=sc.normal_lanes, open_lanes=sc.open_lanes, hard_barrier=sc.hard_barrier,
                      lateral_distance_ft=sc.lateral_distance_ft, night=night,
                      heavy_vehicle_pct=sc.heavy_vehicle_pct)
        pre, dis = capacity_vph(wz), discharge_vph(wz)
        if sc.facility != "freeway":     # HCM Ch. 10 is a freeway method: scale to the arterial base
            pre, dis = pre * base / 2200, dis * base / 2200
    elif sc.shoulder_closed:
        pre = normal * cap_p["shoulder_closure_factor"]
        dis = pre * (1 - ALPHA_WZ / 100)
    else:
        pre = dis = normal
    return {"normal_vph": normal, "work_zone_vph": min(pre, normal), "discharge_vph": min(dis, normal)}


def _crash_cmf(sc: Scenario, night: bool) -> float:
    c = sc.params["crash"]
    cmf = c["cmf_work_zone_presence"]
    cmf *= 1 + c["cmf_per_lane_closed_share"] * sc.lanes_closed / sc.normal_lanes
    if sc.shoulder_closed:
        cmf *= c["cmf_shoulder_closure"]
    if not sc.hard_barrier:
        cmf *= c["cmf_no_barrier"]
    if night:
        cmf *= c["cmf_night"]
    return cmf


def simulate(sc: Scenario, share: float = 0.0, detour: DetourOption | None = None) -> dict:
    """Run one day of the scenario with `share` of arriving traffic diverted to `detour`."""
    p = sc.params
    hourly = hourly_demand(sc)
    night_hours = p["demand"]["night_hours"]
    n_closure = round(sc.closure_hours / INTERVAL_H)
    n_max = n_closure + round(p["capacity"]["recovery_hours"] / INTERVAL_H)
    length = sc.length_mi
    wz_speed = min(sc.work_zone_speed_mph, sc.free_flow_speed_mph)
    speed_delay_h = length / wz_speed - length / sc.free_flow_speed_mph
    base_rate = p["crash"]["base_rate_per_mvmt"]
    rate = base_rate.get(sc.facility, base_rate["freeway"])
    detour_rate = base_rate.get(detour.facility, base_rate["arterial"]) if detour else 0.0

    queued, broken_down = 0.0, False
    tot = dict(queue_vh=0.0, speed_vh=0.0, detour_vh=0.0, arrivals=0.0, diverted=0.0, queued_arrivals=0.0,
               vmt_zone=0.0, vmt_queue=0.0, vmt_detour=0.0, crashes=0.0, crashes_base=0.0, queue_h=0.0)
    intervals = []
    for i in range(n_max):
        in_closure = i < n_closure
        if not in_closure and queued <= 0:
            break
        hour = sc.start_hour + i * INTERVAL_H
        night = _is_night(hour, night_hours)
        demand = hourly[int(hour) % 24]
        caps = capacities(sc, night)
        diverted = demand * share if in_closure else 0.0
        if detour and in_closure and sc.open_lanes > 0:   # a full closure sends everyone, over capacity or not
            diverted = min(diverted, detour.spare_capacity_vph)
        main = demand - diverted
        if in_closure:
            cap = caps["discharge_vph"] if broken_down or queued > 0 else caps["work_zone_vph"]
        else:
            cap = caps["normal_vph"]
        if in_closure and main > caps["work_zone_vph"]:
            broken_down = True
            cap = caps["discharge_vph"]
        served = min(main + queued / INTERVAL_H, cap)
        q_prev, queued = queued, max(0.0, queued + (main - served) * INTERVAL_H)
        if queued == 0:
            broken_down = False
        q_avg = (q_prev + queued) / 2
        q_miles = queued / (QUEUE_DENSITY * sc.normal_lanes)
        q_miles_avg = q_avg / (QUEUE_DENSITY * sc.normal_lanes)
        served_veh = served * INTERVAL_H

        tot["queue_vh"] += q_avg * INTERVAL_H
        tot["queue_h"] += INTERVAL_H if q_avg > 0 else 0.0
        tot["arrivals"] += demand * INTERVAL_H
        tot["diverted"] += diverted * INTERVAL_H
        if q_avg > 0:
            tot["queued_arrivals"] += main * INTERVAL_H
        if in_closure:
            tot["speed_vh"] += served_veh * speed_delay_h
            tot["vmt_zone"] += served_veh * length
        tot["vmt_queue"] += served_veh * q_miles_avg
        detour_mi = (detour.length_mi or length + detour.extra_miles) if detour else 0.0
        if detour:
            tot["detour_vh"] += diverted * INTERVAL_H * detour.extra_time_min / 60
            tot["vmt_detour"] += diverted * INTERVAL_H * detour_mi
        cmf = _crash_cmf(sc, night) if in_closure else 1.0
        tot["crashes"] += rate * cmf * served_veh * length / 1e6
        # Upstream miles are driven anyway; the queue adds only its extra risk on top of the base rate
        tot["crashes"] += rate * (p["crash"]["queue_risk_multiplier"] - 1) * served_veh * q_miles_avg / 1e6
        if detour:
            tot["crashes"] += detour_rate * diverted * INTERVAL_H * detour_mi / 1e6
        tot["crashes_base"] += rate * demand * INTERVAL_H * length / 1e6

        intervals.append({
            "time": f"{int(hour) % 24:02d}:{int(round((hour % 1) * 60)):02d}",
            "in_closure": in_closure,
            "demand_vph": round(demand),
            "diverted_vph": round(diverted),
            "capacity_vph": round(cap),
            "queued_vehicles": round(queued, 1),
            "queue_miles": round(q_miles, 2),
        })
    tot["intervals"] = intervals
    tot["cost"] = user_cost(sc, tot, share, detour)
    return tot


def user_cost(sc: Scenario, tot: dict, share: float, detour: DetourOption | None) -> dict:
    v = sc.params["value_of_time"]
    truck = sc.heavy_vehicle_pct / 100
    delay_vh = tot["queue_vh"] + tot["speed_vh"] + tot["detour_vh"]
    per_vh = (1 - truck) * v["car_occupancy"] * v["personal_usd_per_person_hour"] + truck * v["truck_usd_per_vehicle_hour"]
    delay_cost = delay_vh * per_vh
    voc = 0.0
    if detour:
        voc = tot["diverted"] * detour.extra_miles * ((1 - truck) * v["car_voc_usd_per_mile"] + truck * v["truck_voc_usd_per_mile"])
    return {"delay_cost_usd": delay_cost, "vehicle_operating_cost_usd": voc, "total_usd": delay_cost + voc,
            "usd_per_vehicle_hour": per_vh}


def best_share(sc: Scenario, detour: DetourOption) -> float:
    """Diversion share in [0, max_share] that minimises user cost plus added crash cost (system optimum)."""
    if sc.diversion_share is not None:
        return sc.diversion_share
    cap = sc.params["diversion"]["max_share"]
    grid = [cap * i / 50 for i in range(51)]
    return min(grid, key=lambda s: total_cost(summarize(sc, simulate(sc, s, detour), s)))


def total_cost(summary: dict) -> float:
    """What detours are ranked on: user delay and operating cost plus crashes added by the work zone."""
    return summary["user_cost"]["total_usd"] + summary["safety"]["excess_crash_cost_usd"]


def summarize(sc: Scenario, run: dict, share: float = 0.0) -> dict:
    """Shape one simulation into the per-day and whole-duration figures the API returns."""
    c = sc.params["crash"]
    days = max(sc.days, 1)
    delay_vh = run["queue_vh"] + run["speed_vh"] + run["detour_vh"]
    n_day = run["crashes"]
    n_all = n_day * days
    sev = {k: n_all * s for k, s in c["severity_share"].items()}
    ka = sev.get("K", 0) + sev.get("A", 0)
    crash_cost = sum(sev[k] * c["cost_usd"].get(k, 0) for k in sev)
    base_all = run["crashes_base"] * days
    excess_cost = crash_cost * (n_all - base_all) / n_all if n_all else 0.0
    queue_max = max((i["queue_miles"] for i in run["intervals"]), default=0.0)
    veh_max = max((i["queued_vehicles"] for i in run["intervals"]), default=0.0)
    return {
        "diversion_share": round(share, 3),
        "operations": {
            "max_queue_miles": queue_max,
            "max_queued_vehicles": round(veh_max),
            "queue_duration_hours": round(run["queue_h"], 2),
            "vehicles_in_window_per_day": round(run["arrivals"]),
            "vehicles_in_queue_per_day": round(run["queued_arrivals"]),
            "vehicles_diverted_per_day": round(run["diverted"]),
            "delay_veh_hours_per_day": round(delay_vh, 1),
            "delay_breakdown_veh_hours": {"queue": round(run["queue_vh"], 1),
                                          "reduced_speed": round(run["speed_vh"], 1),
                                          "detour": round(run["detour_vh"], 1)},
            "avg_delay_min_per_vehicle": round(60 * delay_vh / run["arrivals"], 2) if run["arrivals"] else 0.0,
            "total_delay_veh_hours": round(delay_vh * days, 1),
        },
        "user_cost": {
            "delay_cost_usd_per_day": round(run["cost"]["delay_cost_usd"]),
            "vehicle_operating_cost_usd_per_day": round(run["cost"]["vehicle_operating_cost_usd"]),
            "total_usd_per_day": round(run["cost"]["total_usd"]),
            "total_usd": round(run["cost"]["total_usd"] * days),
            "usd_per_vehicle_hour": round(run["cost"]["usd_per_vehicle_hour"], 2),
        },
        "safety": {
            "expected_crashes_per_day": round(n_day, 4),
            "expected_crashes": round(n_all, 4),
            "expected_crashes_without_work_zone": round(base_all, 4),
            "crash_risk_ratio": round(n_day / run["crashes_base"], 2) if run["crashes_base"] else None,
            "probability_any_crash_per_day": round(1 - math.exp(-n_day), 4),
            "probability_any_crash": round(1 - math.exp(-n_all), 4),
            "probability_fatal_or_serious_injury": round(1 - math.exp(-ka), 4),
            "expected_by_severity": {k: round(v, 5) for k, v in sev.items()},
            "expected_crash_cost_usd": round(crash_cost),
            "excess_crash_cost_usd": round(excess_cost),
        },
        "intervals": run["intervals"],
    }
