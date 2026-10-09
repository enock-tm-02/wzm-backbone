"""Scenario analysis endpoints used by the map UI at /map."""
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, model_validator

from wzm.scenario.analyze import analyze, zone_attributes
from wzm.scenario.impacts import DetourOption, Scenario
from wzm.scenario.osm import NetworkUnavailable, fetch_network
from wzm.scenario.params import get_params

router = APIRouter(prefix="/scenario", tags=["scenario"])

LonLat = tuple[float, float]


class SegmentRequest(BaseModel):
    start: LonLat
    end: LonLat


class ManualDetour(BaseModel):
    extra_time_min: float = Field(ge=0)
    extra_miles: float = Field(ge=0)
    spare_capacity_vph: float = Field(gt=0)
    length_mi: float = 0
    facility: Literal["freeway", "arterial"] = "arterial"


class ScenarioRequest(BaseModel):
    # Work zone location: clicked points along the road (first = upstream end, last = downstream end)
    coordinates: list[LonLat] = Field(default_factory=list, description="[lon, lat] points, upstream to downstream")
    snap_to_network: bool = Field(True, description="Follow the OSM road between the first and last point and search detours")
    length_mi: float | None = Field(None, gt=0, description="Used when no coordinates are given")
    facility: Literal["freeway", "arterial"] = "freeway"
    normal_lanes: int = Field(ge=1, le=8)
    lanes_closed: int = Field(0, ge=0, description="Equal to normal_lanes means a full closure")
    shoulder_closed: bool = False
    free_flow_speed_mph: float = Field(65, gt=0)
    work_zone_speed_mph: float = Field(55, gt=0)
    aadt: float | None = Field(None, gt=0)
    hourly_volume_vph: list[float] | None = Field(None, description="24 hourly volumes, analysed direction")
    heavy_vehicle_pct: float = Field(8, ge=0, le=100)
    start_hour: float = Field(9, ge=0, lt=24)
    end_hour: float = Field(15, ge=0, le=24)
    days: int = Field(1, ge=1)
    hard_barrier: bool = False
    lateral_distance_ft: float = Field(2, ge=0, le=12)
    diversion_share: float | None = Field(None, ge=0, le=1, description="Leave empty to optimise")
    detours: list[ManualDetour] = Field(default_factory=list, description="Known detours, if not routing on OSM")
    params: dict = Field(default_factory=dict, description="Overrides for config/scenario_defaults.yaml")

    @model_validator(mode="after")
    def _check(self):
        if self.lanes_closed > self.normal_lanes:
            raise ValueError("lanes_closed cannot exceed normal_lanes")
        if self.aadt is None and not self.hourly_volume_vph:
            raise ValueError("Give aadt or hourly_volume_vph")
        if len(self.coordinates) == 1:
            raise ValueError("Give at least two coordinates (upstream and downstream end)")
        if not self.coordinates and not self.length_mi:
            raise ValueError("Give coordinates or length_mi")
        if self.start_hour == self.end_hour:
            raise ValueError("start_hour and end_hour must differ")
        return self


@router.get("/defaults")
def defaults() -> dict:
    """Default parameters (value of time, CMFs, demand profile...) that requests can override."""
    return get_params()


@router.post("/segment")
def segment(req: SegmentRequest) -> dict:
    """Snap a work zone to the road network between two clicked points and return its attributes."""
    try:
        g = fetch_network([req.start, req.end])
    except NetworkUnavailable as exc:
        raise HTTPException(503, str(exc)) from exc
    path = g.route_between(req.start, req.end)
    if path is None or not path.edges:
        raise HTTPException(404, "No road connects those two points in the travel direction")
    return zone_attributes(path)


@router.post("/analyze")
def analyze_scenario(req: ScenarioRequest) -> dict:
    sc = Scenario(**req.model_dump(exclude={"coordinates", "snap_to_network", "detours", "params"},
                                   exclude_none=True) | {"diversion_share": req.diversion_share},
                  params=get_params(req.params))
    zone = network = None
    warnings = []
    if req.coordinates and req.snap_to_network and len(req.coordinates) >= 2:
        try:
            network = fetch_network(req.coordinates)
            zone = network.route_between(req.coordinates[0], req.coordinates[-1])
            if zone is None or not zone.edges:
                warnings.append("Could not follow the road between the first and last point; using the drawn line.")
                zone = None
        except NetworkUnavailable as exc:
            warnings.append(f"Road network unavailable, no detours searched: {exc}")
    try:
        result = analyze(sc, zone=zone, network=network if zone else None,
                         manual_detours=[DetourOption(**d.model_dump()) for d in req.detours],
                         zone_coords=req.coordinates or None)
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    result["warnings"] = warnings + result["warnings"]
    return result
