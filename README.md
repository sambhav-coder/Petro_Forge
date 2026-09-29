# SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.

[![Smart India Hackathon 2026](https://img.shields.io/badge/SIH-2026-blue.svg)](https://sih.gov.in)
[![Category](https://img.shields.io/badge/Category-Software-emerald.svg)](https://sih.gov.in)
[![Ministry / Org](https://img.shields.io/badge/Organization-Oil%20India%20Limited-indigo.svg)]()
[![Theme](https://img.shields.io/badge/Theme-Smart%20Automation-purple.svg)]()
[![Domain](https://img.shields.io/badge/Domain-Heavy%20Oil%20CSS%20SRP%20Digital%20Twin-orange.svg)]()

---

## 🎯 Problem Statement Overview
- **Problem Statement ID:** `SIH26120`
- **Title:** Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation (CSS) and Sucker Rod Pump (SRP) Operations for Heavy Oil Wells of Baghewala Field.
- **Sponsoring Organization:** Oil India Limited
- **Department:** Oil India Limited
- **Category:** Software
- **Theme:** Smart Automation

### 📖 Official Description
• Background Baghewala Field in Rajasthan produces heavy crude oil (17â€“19Â° API) from the Jodhpur Sandstone reservoir. The reservoir is characterized by High crude viscosity, High asphaltene content, Low reservoir pressure, Low reservoir temperature (46â€“48Â°C) and Poor oil mobility under primary recovery. Consequently, artificial lift and thermal enhanced oil recovery are critical for sustained production. At present, CSS cycle design and SRP operation are optimized separately using historical experience. As reservoir temperature declines after steam injection, crude viscosity increases, leading to reduced pump efficiency, higher energy consumption, rod floating issues, rod failures and lower oil recovery. There is a need for an integrated, data-driven system that continuously optimizes both CSS and artificial lift operations.• Problem Description Current operations face the following challenges:• CSS parameters (steam volume, injection pressure, soak time and production cut-off)are largely based on historical practices.• SRP operating parameters (stroke length, SPM and VFD settings) are adjusted manually and reactively.• Heavy crude causes rod floating, impact loading, frequent pump unsetting, rod failures and increased maintenance.• Reservoir behaviour, wellbore conditions and SRP performance are not optimized together.• Lack of predictive analytics results in higher Steam-Oil Ratio (SOR), increased energy consumption and reduced production efficiency.• Expected Outcome / Solution Develop an AI-enabled Well-to-Surface Digital Twin that integrates reservoir, wellbore and surface production systems to provide real-time monitoring, prediction and optimization.The solution should:• Optimize CSS cycle parameters.• Predict reservoir heating, cooling and production performance.• Continuously optimize SRP operation by adjusting stroke speed and SPM based on well conditions.• Detect rod floating and minimize impact loading.• Improve pump efficiency and equipment reliability.• Optimize steam and energy consumption while reducing operating cost.• Expected Benefits• Increased oil production and recovery.• Reduced Steam-Oil Ratio (SOR).• Lower energy consumption per barrel.• Reduced rod failures and pump unsetting.• Improved equipment life and operational reliability.• Data-driven and predictive decision making.• Relevant Data Availability The field has sufficient historical and operational data, including:• Production history• CSS cycle records• Steam injection parameters• VFD and SRP operating data• Rod failure and pump unsetting history• Well completion and reservoir data• Fluid properties and pressure data

---

## 💡 Implemented Prototype (decision-support simulator, not field control)
Our team has built a deterministic prototype for **Oil India Limited**:
1. **Baghewala Digital Twin Dashboard (`project/index.html`):** Dark engineering UI with well selector, KPI cards, Reservoir → Wellbore → SRP → Surface flow, CSS phase, what-if simulation, joint optimization results, top-5 scenarios, risk cards, and audit timeline — all rendered from real API responses, no mock values.
2. **FastAPI Service (`project/app.py` + `twin_physics.py` + `twin_optimize.py`):** Pydantic-validated well telemetry, in-memory well store, deterministic prototype thermal/viscosity/inflow/pump/SOR/energy models, deterministic engineering risk indicators, side-effect-free simulation, and a 243-scenario CSS × SRP grid optimizer with value-traceable reasons. Swagger docs included; SHA-256 per-record audit hashes.
3. **Technical Solution Document (`project/solution.md`):** Problem analysis, implemented equations with prototype-vs-PS provenance, SOR/energy conventions, optimizer specification, validation results, limitations, and demo flow.
4. **Automated Test Suite (`project/test_*.py`):** 56 tests covering telemetry, physics directional behavior, simulation side-effect freedom, optimizer determinism/bounds/edge cases, and API contracts.
5. **Containerization (`project/Dockerfile` & `project/docker-compose.yml`):** API on :8000 plus nginx preview of the dashboard on :8080.

---

## 🚀 Quick Start Guide

### Option 1: Instant Browser Demo (Zero Setup)
Simply open `project/index.html` in any modern web browser or serve it locally:
```bash
cd "SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation/project"
python -m http.server 8080
```
Open [http://localhost:8080](http://localhost:8080) to access the command center.

### Option 2: Run Full Python FastAPI Microservice
```bash
cd "SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation/project"
pip install -r requirements.txt
python app.py
```
- API Server: [http://127.0.0.1:8000](http://127.0.0.1:8000)
- Interactive OpenAPI Docs: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)

### Option 3: Run Automated Tests
```bash
cd "SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation/project"
pytest -q
```
Expected: 56 passed.

---

## 📂 Project Repository Structure
```plaintext
SIH26120 - Digital Twin for Well-to-Surface Optimization of Cyclic Steam Stimulation/
├── README.md                           # Problem statement pitch & guide
├── problem_statement.json              # Official SIH 2026 metadata
└── project/
    ├── index.html                      # Baghewala Digital Twin dashboard (real API integration)
    ├── app.py                          # FastAPI routes, validation, well store, audit log
    ├── twin_physics.py                 # Deterministic prototype engineering models
    ├── twin_optimize.py                # What-if comparison + CSS×SRP grid optimizer
    ├── test_app.py                     # Telemetry/API regression tests
    ├── test_twin_physics.py            # Physics directional-behavior tests
    ├── test_twin_optimize.py           # Simulation/optimizer tests
    ├── solution.md                     # SIH 26120 technical solution document
    ├── requirements.txt                # Python backend dependencies
    ├── Dockerfile                      # API container definition
    ├── docker-compose.yml              # API + dashboard preview orchestration
    └── README.md                       # Run guide, API overview, assumptions, limitations
```
