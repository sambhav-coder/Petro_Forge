"""Baghewala constraint table (Priority 1, Part C/S).

Two tiers — never mixed:
- SOURCE_CONSTRAINED: value + unit + source_id (see data_catalog/provenance.json).
- ENGINEERING_ASSUMPTIONS: generator choices with no field source.
"""

# value, unit, source_id, measured|estimated|reported, notes
SOURCE_CONSTRAINED = {
    "api_gravity_range": {
        "value": [17.0, 19.0], "unit": "API",
        "source_id": "oilindia_rajasthan_fields",
        "kind": "reported", "notes": "Heavy crude band for Baghewala.",
    },
    "reservoir_temperature_baseline": {
        "value": [46.0, 48.0], "unit": "C",
        "source_id": "sih26120_problem_statement",
        "kind": "reported", "notes": "Low reservoir temperature, primary recovery.",
    },
    "jodhpur_sandstone_avg_depth_m": {
        "value": 1150.0, "unit": "m",
        "source_id": "oilindia_rajasthan_fields",
        "kind": "reported", "notes": "Average reservoir depth; informative only.",
    },
    "field_area_sqkm": {
        "value": 200.26, "unit": "km2",
        "source_id": "et_rajasthan_record_2026",
        "kind": "reported",
        "notes": "CONFLICT retained: oilindia_rajasthan_fields says 200 sq km (PML); "
                 "projectx_baghewala_pml says 210 sq km (expansion block). "
                 "200.26 used as most specific published figure.",
    },
    "wells_drilled_vs_producing": {
        "value": {"oilindia_page": [35, 23], "et_2026": [52, 33]},
        "unit": "count",
        "source_id": "oilindia_rajasthan_fields+et_rajasthan_record_2026",
        "kind": "reported",
        "notes": "CONFLICT retained: different reporting years (undated page vs FY25-26).",
    },
    "field_rate_bopd": {
        "value": {"oilindia_page_gt": 600.0, "et_record_2026": 1202.0, "fy24_25": 705.0},
        "unit": "bopd",
        "source_id": "oilindia_rajasthan_fields+et_rajasthan_record_2026",
        "kind": "reported",
        "notes": "Growth over time; per-well synthetic rates stay modest (5-60 bopd).",
    },
    "css_wells_count_2026": {
        "value": 19, "unit": "count",
        "source_id": "et_rajasthan_record_2026",
        "kind": "reported", "notes": "CSS operations completed in 19 wells (FY25-26).",
    },
    "css_pilot_year": {
        "value": 2018, "unit": "year",
        "source_id": "et_rajasthan_record_2026",
        "kind": "reported", "notes": "CSS first piloted 2018; production since 2017.",
    },
    "steam_temperature_typical": {
        "value": [300.0, 350.0], "unit": "C",
        "source_id": "discoveryalert_baghewala_2026",
        "kind": "estimated",
        "notes": "Secondary press summary; LOW confidence — used only as loose bound.",
    },
    "css_cycle_structure": {
        "value": ["injection", "soak", "production"],
        "unit": "phase",
        "source_id": "wikipedia_heavy_oil_css+oilindia_rajasthan_fields",
        "kind": "reported",
        "notes": "Three-stage CSS; soak spans days to weeks (reference literature).",
    },
    "lift_method": {
        "value": "sucker rod pump (conventional + hydraulic), thermal wellhead, VIT",
        "unit": "equipment",
        "source_id": "oilindia_rajasthan_fields+et_rajasthan_record_2026",
        "kind": "reported", "notes": "Defines SRP telemetry variables.",
    },
}

ENGINEERING_ASSUMPTIONS = {
    "spm_operating_band": {"value": [3.0, 8.0], "unit": "SPM",
                           "notes": "Typical SRP band assumed for demo wells."},
    "stroke_band_in": {"value": [60.0, 120.0], "unit": "in",
                       "notes": "Assumed stroke band for demo wells."},
    "steam_volume_band_t": {"value": [400.0, 1200.0], "unit": "t",
                            "notes": "Assumed per-cycle steam band."},
    "soak_band_h": {"value": [24.0, 120.0], "unit": "h",
                    "notes": "Assumed soak band (days to weeks per literature)."},
    "oil_rate_band_bopd": {"value": [5.0, 60.0], "unit": "bopd",
                           "notes": "Assumed per-well rates consistent with field totals."},
    "water_cut_band": {"value": [0.1, 0.6], "unit": "fraction",
                       "notes": "Assumed water-cut band."},
    "rod_failure_rate": {"value": 0.04, "unit": "probability",
                         "notes": "Assumed rare-event rate for synthetic failure flags."},
    "pump_unsetting_rate": {"value": 0.03, "unit": "probability",
                            "notes": "Assumed rare-event rate for synthetic unsetting flags."},
}
