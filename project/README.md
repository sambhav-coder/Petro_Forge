# SIH26120 — Baghewala Field Well-to-Surface Digital Twin (CSS + SRP)

Prototype Digital Twin for **Smart India Hackathon 2026** problem statement `SIH26120`
(Oil India Limited): deterministic well telemetry → prototype thermal/viscosity/inflow/
pump physics → engineering risk indicators → side-effect-free what-if simulation →
joint CSS × SRP grid optimization → dashboard. No ML, no database, no field control.

## Architecture

- `app.py` — FastAPI routes, Pydantic validation, in-memory well store + SHA-256 audit log
- `twin_physics.py` — deterministic prototype engineering models (documented in module docstring)
- `twin_optimize.py` — scenario comparison + 243-scenario grid optimizer (weights 0.40/0.25/0.15/0.20, prototype)
- `index.html` — dashboard; real `fetch()` calls only, no mock engineering values
- `test_app.py` / `test_twin_physics.py` / `test_twin_optimize.py` — 56 tests
- `solution.md` — full technical solution document

## API overview

| Endpoint | Purpose |
|---|---|
| `GET /` | Health + problem metadata |
| `POST /api/v1/telemetry/ingest` | Validate + store well telemetry, attach twin summary |
| `GET /api/v1/wells` / `GET /api/v1/wells/{id}` | List wells / latest well state |
| `GET /api/v1/wells/{id}/twin` | Deterministic engineering snapshot |
| `POST /api/v1/wells/{id}/simulate` | Side-effect-free what-if (current vs scenario + deltas) |
| `POST /api/v1/wells/{id}/optimize` | Joint CSS × SRP grid search (recommended + top-5 + reasons) |
| `GET /api/v1/audit/logs` | SHA-256 audit records |

## 🚀 Execution Instructions

### FastAPI backend (start first)
```bash
pip install -r requirements.txt
python app.py
```
- API: `http://127.0.0.1:8000`
- Docs: `http://127.0.0.1:8000/docs`

### Dashboard (needs the backend running)
Serve this folder and open the page (the page calls the API at
`http://127.0.0.1:8000` by default; adjustable in the header):
```bash
python -m http.server 8080
```
Visit: [http://localhost:8080](http://localhost:8080)

### Automated tests
```bash
pytest -q
```
Expected: 56 passed.

### Docker
```bash
docker-compose up --build
```
(`api` on :8000, `web_preview` nginx on :8080 serving `index.html`.)

## Example demo flow

1. Start backend (`python app.py`), open dashboard, click **Load BGW-DEMO baseline**.
2. Select `BGW-DEMO`; inspect KPIs, Reservoir → Wellbore → SRP → Surface flow, CSS phase, risks.
3. **Run Simulation** with raised steam/SPM; read current-vs-scenario deltas.
4. **Run Optimization** (243 scenarios); read recommended scenario, deltas, top-5, reasons.
5. Check audit timeline. All numbers are computed live by the prototype.

## Prototype assumptions (not field-calibrated)

Thermal τ=72 h / ΔTmax=180 °C; μref=350 cP@47 °C, B=4500 K; J=0.8 bopd/bar;
pump bore 2.0 in, fillage 0.85, efficiency 0.75; SOR window 30 d (prototype t/bbl units);
750 kWh/t steam, 0.5 kWh/(SPM·in·day); objective weights 0.40/0.25/0.15/0.20.
PS-derived references only: 47 °C (PS 46–48 °C), 18° API (PS 17–19° API).

## Limitations

In-memory state (restart wipes data); uncalibrated prototype physics; fixed
fillage/efficiency; no historical time-series; no trained ML; no field control;
CDN-dependent dashboard. See `solution.md` §19–§20.
