"""Deterministic baseline: HCM work zone capacity + input-output queue.

Capacity follows the HCM 7th edition freeway work zone method (Chapter 10):
    QDR   = 2093 - 154*LCSI - 194*f_Br - 179*f_AT + 9*f_LAT + 59*f_DN   (pc/h/ln)
    LCSI  = 1 / (OR * N)   OR = open lanes / normal lanes, N = open lanes
    c_pre = QDR / (1 - alpha_wz/100), alpha_wz = 13.4
Verify the coefficients against your copy of the HCM before relying on outputs.
"""
from dataclasses import dataclass

ALPHA_WZ = 13.4             # % capacity drop at breakdown
QUEUE_DENSITY = 150.0       # veh/mi/ln inside a moving queue (calibrate locally)


@dataclass
class WorkZone:
    normal_lanes: int
    open_lanes: int
    hard_barrier: bool = False      # concrete barrier vs. cones/drums
    rural: bool = False
    lateral_distance_ft: float = 0  # travel lane edge to barrier, 0-12
    night: bool = False
    heavy_vehicle_pct: float = 5.0
    pce_truck: float = 2.0


def lane_closure_severity_index(z: WorkZone) -> float:
    open_ratio = z.open_lanes / z.normal_lanes
    return 1.0 / (open_ratio * z.open_lanes)


def queue_discharge_rate(z: WorkZone) -> float:
    """pc/h/ln after breakdown."""
    return (2093
            - 154 * lane_closure_severity_index(z)
            - 194 * (0 if z.hard_barrier else 1)
            - 179 * (1 if z.rural else 0)
            + 9 * min(max(z.lateral_distance_ft, 0), 12)
            + 59 * (1 if z.night else 0))


def capacity_vph(z: WorkZone) -> float:
    """Pre-breakdown capacity of the open lanes, in vehicles per hour."""
    f_hv = 1.0 / (1.0 + z.heavy_vehicle_pct / 100 * (z.pce_truck - 1))
    c_pre = queue_discharge_rate(z) / (1 - ALPHA_WZ / 100)
    return c_pre * f_hv * z.open_lanes


def discharge_vph(z: WorkZone) -> float:
    f_hv = 1.0 / (1.0 + z.heavy_vehicle_pct / 100 * (z.pce_truck - 1))
    return queue_discharge_rate(z) * f_hv * z.open_lanes


def predict_queue(z: WorkZone, demand_vph: list[float], interval_min: float = 15) -> list[dict]:
    """Input-output queue per interval. demand_vph = arriving flow in each interval."""
    cap, qdr = capacity_vph(z), discharge_vph(z)
    hours = interval_min / 60
    queued = 0.0
    out = []
    for i, d in enumerate(demand_vph):
        service = qdr if queued > 0 or d > cap else min(d, cap)
        queued = max(0.0, queued + (d - service) * hours)
        out.append({
            "interval": i,
            "demand_vph": round(d),
            "capacity_vph": round(cap),
            "queued_vehicles": round(queued, 1),
            "queue_miles": round(queued / (QUEUE_DENSITY * z.normal_lanes), 2),
            "delay_veh_hours": round(queued * hours, 1),
        })
    return out
