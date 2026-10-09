"""Prediction API. Run: uvicorn wzm.api.main:app --reload"""
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from wzm import __version__
from wzm.api.scenario import router as scenario_router
from wzm.models.baseline_hcm import WorkZone, capacity_vph, predict_queue
from wzm.registry import status

app = FastAPI(title="WZM: Work Zone Impact API", version=__version__)
app.include_router(scenario_router)
app.mount("/map", StaticFiles(directory=Path(__file__).parents[1] / "web", html=True), name="map")


@app.get("/", include_in_schema=False)
def root() -> RedirectResponse:
    return RedirectResponse("/map/")


class PredictRequest(BaseModel):
    normal_lanes: int = Field(ge=1)
    open_lanes: int = Field(ge=1)
    hard_barrier: bool = False
    rural: bool = False
    lateral_distance_ft: float = 0
    night: bool = False
    heavy_vehicle_pct: float = 5.0
    demand_vph: list[float] = Field(description="Arriving volume per 15-min interval, veh/h")


@app.get("/health")
def health() -> dict:
    return {"ok": True, "version": __version__}


@app.get("/streams")
def streams() -> list[dict]:
    """Which data streams and outputs are configured."""
    return status()


@app.post("/predict/baseline")
def predict_baseline(req: PredictRequest) -> dict:
    z = WorkZone(**req.model_dump(exclude={"demand_vph"}))
    intervals = predict_queue(z, req.demand_vph)
    return {
        "model": "hcm-baseline",
        "capacity_vph": round(capacity_vph(z)),
        "max_queue_miles": max((i["queue_miles"] for i in intervals), default=0),
        "total_delay_veh_hours": round(sum(i["delay_veh_hours"] for i in intervals), 1),
        "intervals": intervals,
    }


@app.get("/zones")
def zones() -> list[dict]:
    # TODO: read active and planned zones from the database
    return []


@app.get("/zones/{zone_id}/forecast")
def zone_forecast(zone_id: str) -> dict:
    # TODO: load zone + forecast demand, run ML model (falls back to baseline)
    return {"zone_id": zone_id, "status": "not implemented"}
