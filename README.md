# WZM: Predictive Work Zone Impact System (backbone)

Skeleton for predicting queue length, delay, speed drop and crash risk for planned
and active work zones. It follows the build guide: sources -> data platform ->
models -> delivery.

## Quick start

```bash
cp .env.example .env              # fill in the TODO values you have
pip install -e ".[dev]"
wzm status                        # which data streams are ON / OFF and what each needs
pytest
uvicorn wzm.api.main:app --reload # http://localhost:8000/docs
docker compose up db              # PostGIS with db/schema.sql loaded
```

Try the baseline without any data feeds:

```bash
curl -X POST localhost:8000/predict/baseline -H 'content-type: application/json' \
  -d '{"normal_lanes":3,"open_lanes":1,"demand_vph":[3000,3000,1500,1000]}'
```

## Layout

| Path | What it is | State |
| --- | --- | --- |
| `.env.example` | Every API key and endpoint the system needs | Placeholders |
| `config/datastreams.yaml` | Registry of input streams and output channels, with the settings each needs | Done |
| `src/wzm/connectors/` | One connector per stream (`fetch` + `normalize`) | WZDx and NOAA weather work once configured; the rest are stubs |
| `src/wzm/pipeline/` | `ingest` (works), `reconcile` and `features` | Stubs except ingest |
| `src/wzm/models/baseline_hcm.py` | HCM work zone capacity + input-output queue | Working |
| `src/wzm/models/train.py`, `crash_risk.py` | Boosted models, crash risk | Stubs |
| `src/wzm/api/main.py` | FastAPI: `/health`, `/streams`, `/predict/baseline`, `/zones` | Baseline works; zones stubbed |
| `src/wzm/alerts/notify.py` | DMS, 511, email | Stubs |
| `db/schema.sql` | Segments, work zones, speeds, volumes, crashes, context, predictions | Done |

## Data streams to connect

| Stream | Settings in `.env` | Priority |
| --- | --- | --- |
| WZDx work zone feed | `WZDX_FEED_URL`, `WZDX_API_KEY` (if needed) | Must |
| Lane closure permits | `PERMITS_API_URL`, `PERMITS_API_KEY` | Must |
| NPMRDS (RITIS) historical speeds | `NPMRDS_USERNAME`, `NPMRDS_PASSWORD` | Must |
| INRIX live speeds (or HERE) | `INRIX_APP_ID`, `INRIX_HASH_TOKEN` / `HERE_API_KEY` | Must (one) |
| Detector volumes | `DETECTORS_API_URL`, `DETECTORS_API_KEY` | Must |
| Crash records | `CRASHES_DB_URL` | High |
| NOAA weather | `NOAA_USER_AGENT` (+ station list in `weather.py`) | Medium |
| Special events | `EVENTS_API_URL` | Medium |
| Incidents / 511 | `INCIDENTS_API_URL`, `INCIDENTS_API_KEY` | Medium |
| Outputs: DMS, 511, email | `DMS_API_*`, `ALERT_511_URL`, `SMTP_URL`, `ALERT_EMAIL_TO` | Phase 3 |

## Adding a connector

1. Add the stream to `config/datastreams.yaml` with its `env` keys.
2. Add those keys to `.env.example` and `src/wzm/config.py`.
3. Subclass `Connector` in `src/wzm/connectors/`, set `required_env`, implement `fetch` and `normalize`.
4. Register the class in `src/wzm/connectors/__init__.py`. The registry test checks steps 1 and 3 agree.

## Notes

- The HCM coefficients in `baseline_hcm.py` follow HCM 7th edition Chapter 10; verify them against your copy.
- `QUEUE_DENSITY` (150 veh/mi/ln) is a placeholder to calibrate with local queue observations.
