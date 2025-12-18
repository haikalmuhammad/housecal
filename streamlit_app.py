# streamlit_app.py
import copy
import json
import math
import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="NZ Housing Sustainability Calculator (Prototype)", layout="wide")
PLACEHOLDER = "— Select —"

# =============================================================================
# ASSUMPTIONS REGISTRY (SINGLE SOURCE OF TRUTH)
# =============================================================================
# Notes:
# - "Value (default)" is the default used when no manual override is provided.
# - Overrides are Level A only (Tab 1), bounded with validation rules.
# - Some entries are dictionaries (e.g., HDD lookup, capex tables). The assumptions table renders a readable summary.
ASSUMPTIONS = {
    # --- Level A (User-facing overrides) ---
    "HOT_WATER_L_PPD": {
        "value": 50.0,
        "unit": "L/person/day",
        "where_used": "Water heating → calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Homestar / ECCHO defaults (TBD)",
        "rationale": "Aggregated proxy for hot water demand suitable for early-stage comparisons.",
        "sensitivity": "High",
        "override_allowed": True,
        "override_ui": "Tab 1 → User overrides (Level A)",
        "validation_rule": "10–200 L/person/day",
        "min": 10.0,
        "max": 200.0,
        "step": 1.0,
    },
    "MINUTES_PER_SHOWER": {
        "value": 6.21,
        "unit": "minutes",
        "where_used": "Water consumption → calculate_water_consumption()",
        "source_type": "Homestar",
        "citation": "Homestar Water Calculator default shower duration (document/page TBD)",
        "rationale": "Empirical default used by Homestar Water Calculator; retained for transparency.",
        "sensitivity": "Medium",
        "override_allowed": True,
        "override_ui": "Tab 1 → User overrides (Level A)",
        "validation_rule": "1–30 minutes",
        "min": 1.0,
        "max": 30.0,
        "step": 0.1,
    },
    "ELECTRICITY_TARIFF": {
        "value": 0.30,
        "unit": "NZD/kWh",
        "where_used": "Opex → calculate_opex()",
        "source_type": "Placeholder",
        "citation": "Representative residential tariff (TBD)",
        "rationale": "Average volumetric price used to estimate annual operating cost for comparisons.",
        "sensitivity": "Medium",
        "override_allowed": True,
        "override_ui": "Tab 1 → User overrides (Level A)",
        "validation_rule": "0.05–1.00 NZD/kWh",
        "min": 0.05,
        "max": 1.00,
        "step": 0.01,
    },
    "WATER_TARIFF": {
        "value": 2.50,
        "unit": "NZD/m³",
        "where_used": "Opex → calculate_opex()",
        "source_type": "Placeholder",
        "citation": "Council tariffs (TBD)",
        "rationale": "Average volumetric charge used for annual water cost comparisons.",
        "sensitivity": "Low",
        "override_allowed": True,
        "override_ui": "Tab 1 → User overrides (Level A)",
        "validation_rule": "0.00–10.00 NZD/m³",
        "min": 0.0,
        "max": 10.0,
        "step": 0.10,
    },

    # --- Climate lookup (supports HDD override at scenario-level) ---
    "HDD_LOOKUP_BASE18": {
        "value": {
            "Zone 1 (Warmest - e.g., Northland)": 1200,
            "Zone 2 (Warm - e.g., Auckland)": 1600,
            "Zone 3 (Mild - e.g., Wellington)": 2000,
            "Zone 4 (Cool - e.g., Christchurch)": 2400,
            "Zone 5 (Cold - e.g., Queenstown)": 2800,
            "Zone 6 (Coldest - e.g., Central Otago)": 3200,
        },
        "unit": "°C·day (base 18°C)",
        "where_used": "Space heating → calculate_space_heating() when HDD override not supplied",
        "source_type": "Placeholder",
        "citation": "Authoritative NZ HDD dataset + mapping (TBD)",
        "rationale": "HDD is the dominant climate driver in steady-state space-heating demand estimates.",
        "sensitivity": "High",
        "override_allowed": True,  # via scenario-level HDD override input
        "override_ui": "Tab 1 → Baseline/Option → Core inputs → 'Override HDD'",
        "validation_rule": "500–5000 °C·day",
        "min": 500.0,
        "max": 5000.0,
        "step": 10.0,
    },

    # --- Fixed (no override; placeholders until sourced) ---
    "GRID_EMISSION_FACTOR": {
        "value": 0.10,
        "unit": "kgCO₂e/kWh",
        "where_used": "Carbon → calculate_operational_carbon()",
        "source_type": "Placeholder",
        "citation": "NZ electricity emissions factor (year/scope to be defined; TBD)",
        "rationale": "Average operational electricity emissions factor for indicative comparisons.",
        "sensitivity": "High",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "0.02–1.00 kgCO₂e/kWh",
        "min": 0.02,
        "max": 1.00,
    },
    "WATER_EMISSION_FACTOR": {
        "value": 0.63,
        "unit": "kgCO₂e/m³",
        "where_used": "Carbon → calculate_operational_carbon()",
        "source_type": "Placeholder",
        "citation": "NZ water supply emissions factor (region-specific if possible; TBD)",
        "rationale": "Captures energy intensity of potable water supply in a simple operational carbon scope.",
        "sensitivity": "Medium",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "0.10–2.00 kgCO₂e/m³",
        "min": 0.10,
        "max": 2.00,
    },

    # --- Water behaviour defaults retained but not user-editable (still auditable) ---
    "TOILET_FLUSHES_PER_PERSON_DAY": {
        "value": 5.0,
        "unit": "flushes/person/day",
        "where_used": "Water consumption → calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "Homestar water usage assumptions (TBD)",
        "rationale": "Reasonable default usage intensity to support early-stage comparisons.",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "0–20",
        "min": 0.0,
        "max": 20.0,
    },
    "SHOWERS_PER_PERSON_DAY": {
        "value": 1.0,
        "unit": "showers/person/day",
        "where_used": "Water consumption → calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "Homestar/ECCHO defaults (TBD)",
        "rationale": "Simple daily frequency assumption; minutes/shower remains overrideable (Level A).",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "0–5",
        "min": 0.0,
        "max": 5.0,
    },
    "TAP_MINUTES_PER_PERSON_DAY": {
        "value": 10.0,
        "unit": "minutes/person/day",
        "where_used": "Water consumption → calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "NZ indoor water end-use assumptions (TBD)",
        "rationale": "Simple taps usage intensity for early-stage comparisons.",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "0–120",
        "min": 0.0,
        "max": 120.0,
    },

    # --- Water heating thermodynamics defaults retained but not user-editable ---
    "HOT_WATER_SETPOINT_C": {
        "value": 60.0,
        "unit": "°C",
        "where_used": "Water heating → calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Typical cylinder setpoint / Homestar default context (TBD)",
        "rationale": "Typical hot water storage setpoint for simplified ΔT calculation.",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "45–75",
        "min": 45.0,
        "max": 75.0,
    },
    "COLD_WATER_INLET_C": {
        "value": 15.0,
        "unit": "°C",
        "where_used": "Water heating → calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Regional cold inlet water temperature (TBD)",
        "rationale": "Simplified cold inlet temperature for ΔT calculation; regionally variable in practice.",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "5–25",
        "min": 5.0,
        "max": 25.0,
    },

    # --- Capex unit cost placeholders (data model ready) ---
    "CAPEX_ENVELOPE_NZD_PER_M2": {
        "value": {
            "Uninsulated": 0.0,
            "Basic": 15.0,
            "Code minimum": 25.0,
            "Good": 40.0,
            "Excellent": 60.0,
        },
        "unit": "NZD/m²",
        "where_used": "Capex → calculate_incremental_capex()",
        "source_type": "Placeholder",
        "citation": "QS / published cost guide ranges (TBD)",
        "rationale": "Placeholder incremental unit costs to support indicative trade-offs (not QS-grade).",
        "sensitivity": "Medium",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "Non-negative; replace with sourced ranges later",
    },
    "CAPEX_WINDOW_NZD_PER_M2_WINDOW": {
        "value": {
            "Single glazed": 0.0,
            "Standard double glazed": 250.0,
            "Low-E double glazed": 400.0,
            "High performance triple": 700.0,
        },
        "unit": "NZD/m² window",
        "where_used": "Capex → calculate_incremental_capex()",
        "source_type": "Placeholder",
        "citation": "QS / published cost guide ranges (TBD)",
        "rationale": "Placeholder incremental glazing upgrade costs.",
        "sensitivity": "Medium",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "Non-negative; replace with sourced ranges later",
    },
    "CAPEX_HEATING_LUMP_NZD": {
        "value": {
            "None": 0.0,
            "Electric resistance (COP 1.0)": 800.0,
            "Heat pump (COP 2.5)": 3500.0,
        },
        "unit": "NZD (lump sum)",
        "where_used": "Capex → calculate_incremental_capex()",
        "source_type": "Placeholder",
        "citation": "Supplier/QS indicative ranges (TBD)",
        "rationale": "Placeholder lump-sum upgrades for systems.",
        "sensitivity": "Medium",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "Non-negative; replace with sourced ranges later",
    },
    "CAPEX_WATER_HEATING_LUMP_NZD": {
        "value": {
            "Electric storage cylinder (COP 1.0)": 0.0,
            "Heat pump hot water (COP 2.0)": 5500.0,
        },
        "unit": "NZD (lump sum)",
        "where_used": "Capex → calculate_incremental_capex()",
        "source_type": "Placeholder",
        "citation": "Supplier/QS indicative ranges (TBD)",
        "rationale": "Placeholder lump-sum upgrades for water heating systems.",
        "sensitivity": "Medium",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "Non-negative; replace with sourced ranges later",
    },
    "CAPEX_FIXTURES_LUMP_NZD": {
        "value": {
            "Toilet upgrade": 600.0,
            "Shower upgrade": 250.0,
            "Tap upgrade": 200.0,
        },
        "unit": "NZD (lump sum)",
        "where_used": "Capex → calculate_incremental_capex()",
        "source_type": "Placeholder",
        "citation": "Supplier/QS indicative ranges (TBD)",
        "rationale": "Placeholder incremental upgrade costs for fixtures.",
        "sensitivity": "Low",
        "override_allowed": False,
        "override_ui": "—",
        "validation_rule": "Non-negative; replace with sourced ranges later",
    },
}

# =============================================================================
# DATA / COEFFICIENTS (NON-REGISTRY LOOKUPS / USER INPUT OPTIONS)
# =============================================================================
# Envelope
R_VALUES_ROOF = {
    "Uninsulated": 0.5,
    "Basic (R2.0)": 2.0,
    "Code minimum (R3.3)": 3.3,
    "Good (R4.6)": 4.6,
    "Excellent (R6.0)": 6.0,
}
R_VALUES_WALLS = {
    "Uninsulated": 0.5,
    "Basic (R1.5)": 1.5,
    "Code minimum (R2.0)": 2.0,
    "Good (R2.8)": 2.8,
    "Excellent (R4.0)": 4.0,
}
R_VALUES_FLOOR = {
    "Uninsulated": 0.5,
    "Basic (R1.3)": 1.3,
    "Code minimum (R2.0)": 2.0,
    "Good (R3.0)": 3.0,
    "Excellent (R4.0)": 4.0,
}
U_VALUES_WINDOWS = {
    "Single glazed": 5.8,
    "Standard double glazed": 3.0,
    "Low-E double glazed": 2.0,
    "High performance triple": 1.0,
}

# Systems (COP/Efficiency)
HEATING_SYSTEMS = {
    "None": 0.0,
    "Electric resistance (COP 1.0)": 1.0,
    "Heat pump (COP 2.5)": 2.5,
}
WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder (COP 1.0)": 1.0,
    "Heat pump hot water (COP 2.0)": 2.0,
}

# Water fixtures
TOILET_TYPES = {
    "Single flush (9L)": 9.0,
    "Dual flush standard (6/3L avg 5L)": 5.0,
    "Dual flush efficient (4.5/3L avg 4L)": 4.0,
}
SHOWER_TYPES = {
    "Standard (9 L/min)": 9.0,
    "Low-flow (7 L/min)": 7.0,
    "Efficient (6 L/min)": 6.0,
}
TAP_TYPES = {
    "Standard (8 L/min)": 8.0,
    "Efficient (6 L/min)": 6.0,
    "Very efficient (4 L/min)": 4.0,
}

# Appliance water (kept IN water model)
WASHING_MACHINE_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 60}
DISHWASHER_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 12}

# Lighting (kept in Energy; not treated as plug load)
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}

# =============================================================================
# ASSUMPTION RESOLUTION
# =============================================================================
def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def get_level_a_overrides() -> dict:
    """
    Returns Level A override values (global), bounded.
    """
    overrides = {}

    # Hot water L/person/day
    hw = float(st.session_state.get("ov_hot_water_l_ppd", ASSUMPTIONS["HOT_WATER_L_PPD"]["value"]))
    overrides["HOT_WATER_L_PPD"] = _clamp(hw, ASSUMPTIONS["HOT_WATER_L_PPD"]["min"], ASSUMPTIONS["HOT_WATER_L_PPD"]["max"])

    # Minutes per shower
    ms = float(st.session_state.get("ov_minutes_per_shower", ASSUMPTIONS["MINUTES_PER_SHOWER"]["value"]))
    overrides["MINUTES_PER_SHOWER"] = _clamp(ms, ASSUMPTIONS["MINUTES_PER_SHOWER"]["min"], ASSUMPTIONS["MINUTES_PER_SHOWER"]["max"])

    # Tariffs
    et = float(st.session_state.get("ov_electricity_tariff", ASSUMPTIONS["ELECTRICITY_TARIFF"]["value"]))
    overrides["ELECTRICITY_TARIFF"] = _clamp(et, ASSUMPTIONS["ELECTRICITY_TARIFF"]["min"], ASSUMPTIONS["ELECTRICITY_TARIFF"]["max"])

    wt = float(st.session_state.get("ov_water_tariff", ASSUMPTIONS["WATER_TARIFF"]["value"]))
    overrides["WATER_TARIFF"] = _clamp(wt, ASSUMPTIONS["WATER_TARIFF"]["min"], ASSUMPTIONS["WATER_TARIFF"]["max"])

    return overrides

def resolve_assumptions(level_a_overrides: dict) -> dict:
    """
    Produces resolved assumptions (single source of truth used by calculations).
    Only Level A overrides are applied.
    """
    A = {}
    for k, meta in ASSUMPTIONS.items():
        A[k] = copy.deepcopy(meta["value"])

    # Apply Level A overrides
    A["HOT_WATER_L_PPD"] = level_a_overrides["HOT_WATER_L_PPD"]
    A["MINUTES_PER_SHOWER"] = level_a_overrides["MINUTES_PER_SHOWER"]
    A["ELECTRICITY_TARIFF"] = level_a_overrides["ELECTRICITY_TARIFF"]
    A["WATER_TARIFF"] = level_a_overrides["WATER_TARIFF"]

    return A

# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================
def calculate_space_heating(inputs: dict, A: dict) -> dict:
    """
    Steady-state, envelope-only heat loss approach using HDD (base 18°C).
    Purpose: early-stage *comparative* differences only.
    Excludes: infiltration/ventilation losses, internal/solar gains, zoning, behavioural effects.

    HDD source:
    - Uses scenario HDD override if provided
    - Else uses climate-zone lookup in ASSUMPTIONS["HDD_LOOKUP_BASE18"]
    """
    if inputs.get("HDD_override_base18") is not None:
        HDD = float(inputs["HDD_override_base18"])
    else:
        HDD = float(A["HDD_LOOKUP_BASE18"][inputs["climateZone"]])

    roofU = 1.0 / inputs["roofRValue"]
    wallU = 1.0 / inputs["wallRValue"]
    floorU = 1.0 / inputs["floorRValue"]

    floorArea = inputs["floorArea"]
    ceilingHeight = inputs["ceilingHeight"]
    windowArea = inputs["windowArea"]

    roofArea = floorArea
    perimeter = 4.0 * math.sqrt(floorArea)  # simplification
    wallArea = max(perimeter * ceilingHeight - windowArea, 0.0)
    floorAreaCalc = floorArea

    H_roof = roofArea * roofU
    H_wall = wallArea * wallU
    H_floor = floorAreaCalc * floorU
    H_window = windowArea * inputs["windowUValue"]
    H_total = H_roof + H_wall + H_floor + H_window

    Q_delivered = (H_total * HDD * 24.0) / 1000.0  # kWh/year (delivered)
    eff = inputs["heatingSystemEfficiency"]
    Q_purchased = (Q_delivered / eff) if eff and eff > 0 else 0.0

    return {
        "Q_delivered_kwh_y": Q_delivered,
        "Q_purchased_kwh_y": Q_purchased,
        "H_total_W_per_K": H_total,
        "HDD_base18": HDD,
        "breakdown_W_per_K": {
            "H_roof": H_roof,
            "H_wall": H_wall,
            "H_floor": H_floor,
            "H_window": H_window,
        },
    }

def calculate_water_heating(inputs: dict, A: dict) -> dict:
    """
    Simplified water heating: annual hot water volume * deltaT * Cp.
    Uses resolved assumptions: HOT_WATER_L_PPD, HOT_WATER_SETPOINT_C, COLD_WATER_INLET_C.
    """
    n = inputs["householdSize"]

    L_per_person_day = float(A["HOT_WATER_L_PPD"])
    T_hot = float(A["HOT_WATER_SETPOINT_C"])
    T_cold = float(A["COLD_WATER_INLET_C"])

    V_annual_L = n * L_per_person_day * 365.0
    deltaT = T_hot - T_cold

    specificHeat_kJ_per_kgC = 4.186
    Q_delivered_kwh_y = (V_annual_L * deltaT * specificHeat_kJ_per_kgC) / 3600.0

    eff = inputs["waterHeatingEfficiency"]
    Q_purchased_kwh_y = (Q_delivered_kwh_y / eff) if eff and eff > 0 else Q_delivered_kwh_y

    return {
        "V_annual_L": V_annual_L,
        "Q_delivered_kwh_y": Q_delivered_kwh_y,
        "Q_purchased_kwh_y": Q_purchased_kwh_y,
        "assumptions_used": {
            "HOT_WATER_L_PPD": L_per_person_day,
            "HOT_WATER_SETPOINT_C": T_hot,
            "COLD_WATER_INLET_C": T_cold,
        },
    }

def calculate_lighting(inputs: dict) -> dict:
    """
    Lighting-only electricity (no plug loads / appliances / cooking).
    """
    lighting = inputs["lighting"]
    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_total_kwh_y": Q_lighting}

def calculate_water_consumption(inputs: dict, A: dict) -> dict:
    """
    Indoor water only. Reports m³/year.
    Includes appliance water (dishwasher, washing machine) but NOT their energy.
    Uses resolved assumptions for behavioural intensity.
    """
    n = inputs["householdSize"]

    toiletL = TOILET_TYPES[inputs["toiletType"]]
    showerLmin = SHOWER_TYPES[inputs["showerType"]]
    tapLmin = TAP_TYPES[inputs["tapType"]]

    flushes = float(A["TOILET_FLUSHES_PER_PERSON_DAY"])
    showers = float(A["SHOWERS_PER_PERSON_DAY"])
    showerMinutes = float(A["MINUTES_PER_SHOWER"])  # Level A override applies here
    tapMinutes = float(A["TAP_MINUTES_PER_PERSON_DAY"])

    V_toilet_L_y = n * flushes * toiletL * 365.0
    V_shower_L_y = n * showers * showerMinutes * showerLmin * 365.0
    V_taps_L_y = n * tapMinutes * tapLmin * 365.0

    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]

    V_laundry_L_y = (washing["cyclesPerWeek"] * washing["waterPerCycle_L"] * 52.0) if washing["hasAppliance"] else 0.0
    V_dish_L_y = (dish["cyclesPerWeek"] * dish["waterPerCycle_L"] * 52.0) if dish["hasAppliance"] else 0.0

    V_total_m3_y = (V_toilet_L_y + V_shower_L_y + V_taps_L_y + V_laundry_L_y + V_dish_L_y) / 1000.0

    return {
        "V_total_m3_y": V_total_m3_y,
        "breakdown_m3_y": {
            "Toilets": V_toilet_L_y / 1000.0,
            "Showers": V_shower_L_y / 1000.0,
            "Taps": V_taps_L_y / 1000.0,
            "Laundry": V_laundry_L_y / 1000.0,
            "Dishwasher": V_dish_L_y / 1000.0,
        },
        "assumptions_used": {
            "TOILET_FLUSHES_PER_PERSON_DAY": flushes,
            "SHOWERS_PER_PERSON_DAY": showers,
            "MINUTES_PER_SHOWER": showerMinutes,
            "TAP_MINUTES_PER_PERSON_DAY": tapMinutes,
        },
    }

def calculate_operational_carbon(total_kwh_y: float, total_m3_y: float, A: dict) -> dict:
    CO2_e = total_kwh_y * float(A["GRID_EMISSION_FACTOR"])
    CO2_w = total_m3_y * float(A["WATER_EMISSION_FACTOR"])
    return {
        "CO2_total_kg_y": CO2_e + CO2_w,
        "CO2_electricity_kg_y": CO2_e,
        "CO2_water_kg_y": CO2_w,
        "assumptions_used": {
            "GRID_EMISSION_FACTOR": float(A["GRID_EMISSION_FACTOR"]),
            "WATER_EMISSION_FACTOR": float(A["WATER_EMISSION_FACTOR"]),
        }
    }

def calculate_opex(total_kwh_y: float, total_m3_y: float, A: dict) -> dict:
    c_e = total_kwh_y * float(A["ELECTRICITY_TARIFF"])
    c_w = total_m3_y * float(A["WATER_TARIFF"])
    return {
        "opex_total_nzd_y": c_e + c_w,
        "opex_electricity_nzd_y": c_e,
        "opex_water_nzd_y": c_w,
        "assumptions_used": {
            "ELECTRICITY_TARIFF": float(A["ELECTRICITY_TARIFF"]),
            "WATER_TARIFF": float(A["WATER_TARIFF"]),
        }
    }

def _label_bucket_from_r_label(label: str) -> str:
    if label.startswith("Uninsulated"):
        return "Uninsulated"
    if label.startswith("Basic"):
        return "Basic"
    if label.startswith("Code minimum"):
        return "Code minimum"
    if label.startswith("Good"):
        return "Good"
    if label.startswith("Excellent"):
        return "Excellent"
    return "Uninsulated"

def calculate_incremental_capex(base_inputs: dict, opt_inputs: dict, A: dict) -> dict:
    """
    Minimal incremental capex with placeholder assumptions (stored in ASSUMPTIONS registry).
    Returns a breakdown and total capex delta: option - baseline.
    """
    CAPEX_ENVELOPE_NZD_PER_M2 = A["CAPEX_ENVELOPE_NZD_PER_M2"]
    CAPEX_WINDOW_NZD_PER_M2_WINDOW = A["CAPEX_WINDOW_NZD_PER_M2_WINDOW"]
    CAPEX_HEATING_LUMP_NZD = A["CAPEX_HEATING_LUMP_NZD"]
    CAPEX_WATER_HEATING_LUMP_NZD = A["CAPEX_WATER_HEATING_LUMP_NZD"]
    CAPEX_FIXTURES_LUMP_NZD = A["CAPEX_FIXTURES_LUMP_NZD"]

    def areas(inp: dict):
        floorArea = inp["floorArea"]
        ceilingHeight = inp["ceilingHeight"]
        windowArea = inp["windowArea"]
        roofArea = floorArea
        perimeter = 4.0 * math.sqrt(floorArea)
        wallArea = max(perimeter * ceilingHeight - windowArea, 0.0)
        return roofArea, wallArea, floorArea, windowArea

    b_roofA, b_wallA, b_floorA, b_winA = areas(base_inputs)
    o_roofA, o_wallA, o_floorA, o_winA = areas(opt_inputs)

    roof_bucket_b = _label_bucket_from_r_label(base_inputs["_roof_label"])
    roof_bucket_o = _label_bucket_from_r_label(opt_inputs["_roof_label"])
    wall_bucket_b = _label_bucket_from_r_label(base_inputs["_wall_label"])
    wall_bucket_o = _label_bucket_from_r_label(opt_inputs["_wall_label"])
    floor_bucket_b = _label_bucket_from_r_label(base_inputs["_floor_label"])
    floor_bucket_o = _label_bucket_from_r_label(opt_inputs["_floor_label"])

    roof_cost_b = CAPEX_ENVELOPE_NZD_PER_M2[roof_bucket_b] * b_roofA
    roof_cost_o = CAPEX_ENVELOPE_NZD_PER_M2[roof_bucket_o] * o_roofA

    wall_cost_b = CAPEX_ENVELOPE_NZD_PER_M2[wall_bucket_b] * b_wallA
    wall_cost_o = CAPEX_ENVELOPE_NZD_PER_M2[wall_bucket_o] * o_wallA

    floor_cost_b = CAPEX_ENVELOPE_NZD_PER_M2[floor_bucket_b] * b_floorA
    floor_cost_o = CAPEX_ENVELOPE_NZD_PER_M2[floor_bucket_o] * o_floorA

    win_cost_b = CAPEX_WINDOW_NZD_PER_M2_WINDOW[base_inputs["_window_label"]] * b_winA
    win_cost_o = CAPEX_WINDOW_NZD_PER_M2_WINDOW[opt_inputs["_window_label"]] * o_winA

    heat_cost_b = CAPEX_HEATING_LUMP_NZD[base_inputs["_heating_label"]]
    heat_cost_o = CAPEX_HEATING_LUMP_NZD[opt_inputs["_heating_label"]]

    hw_cost_b = CAPEX_WATER_HEATING_LUMP_NZD[base_inputs["_water_heating_label"]]
    hw_cost_o = CAPEX_WATER_HEATING_LUMP_NZD[opt_inputs["_water_heating_label"]]

    def eff_rank_toilet(k: str): return {"Single flush (9L)": 0, "Dual flush standard (6/3L avg 5L)": 1, "Dual flush efficient (4.5/3L avg 4L)": 2}[k]
    def eff_rank_shower(k: str): return {"Standard (9 L/min)": 0, "Low-flow (7 L/min)": 1, "Efficient (6 L/min)": 2}[k]
    def eff_rank_tap(k: str): return {"Standard (8 L/min)": 0, "Efficient (6 L/min)": 1, "Very efficient (4 L/min)": 2}[k]

    toilet_upgrade = CAPEX_FIXTURES_LUMP_NZD["Toilet upgrade"] if eff_rank_toilet(opt_inputs["toiletType"]) > eff_rank_toilet(base_inputs["toiletType"]) else 0.0
    shower_upgrade = CAPEX_FIXTURES_LUMP_NZD["Shower upgrade"] if eff_rank_shower(opt_inputs["showerType"]) > eff_rank_shower(base_inputs["showerType"]) else 0.0
    tap_upgrade = CAPEX_FIXTURES_LUMP_NZD["Tap upgrade"] if eff_rank_tap(opt_inputs["tapType"]) > eff_rank_tap(base_inputs["tapType"]) else 0.0

    fixtures_cost_b = 0.0
    fixtures_cost_o = toilet_upgrade + shower_upgrade + tap_upgrade

    breakdown = {
        "Roof insulation": roof_cost_o - roof_cost_b,
        "Wall insulation": wall_cost_o - wall_cost_b,
        "Floor insulation": floor_cost_o - floor_cost_b,
        "Windows": win_cost_o - win_cost_b,
        "Space heating system": heat_cost_o - heat_cost_b,
        "Water heating system": hw_cost_o - hw_cost_b,
        "Fixtures (efficiency upgrades)": fixtures_cost_o - fixtures_cost_b,
    }
    total = sum(breakdown.values())
    return {"capex_incremental_nzd": total, "breakdown_nzd": breakdown}

def calculate_scenario(inputs: dict, A: dict) -> dict:
    space = calculate_space_heating(inputs, A)
    water_heat = calculate_water_heating(inputs, A)
    lighting = calculate_lighting(inputs)
    water_use = calculate_water_consumption(inputs, A)

    # Total electricity: EXCLUDES appliances/plug loads
    total_electricity_kwh_y = space["Q_purchased_kwh_y"] + water_heat["Q_purchased_kwh_y"] + lighting["Q_total_kwh_y"]

    carbon = calculate_operational_carbon(total_electricity_kwh_y, water_use["V_total_m3_y"], A)
    opex = calculate_opex(total_electricity_kwh_y, water_use["V_total_m3_y"], A)
    energy_intensity = (total_electricity_kwh_y / inputs["floorArea"]) if inputs["floorArea"] > 0 else 0.0

    return {
        "spaceHeating": space,
        "waterHeating": water_heat,
        "lighting": lighting,
        "waterConsumption": water_use,
        "totalElectricity_kwh_y": total_electricity_kwh_y,
        "energyIntensity_kwh_m2_y": energy_intensity,
        "carbon": carbon,
        "opex": opex,
    }

# =============================================================================
# STATE / UTIL
# =============================================================================
def _stable_hash(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def fmt_num(x: float, decimals: int = 1):
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}"

def direction_arrow(delta: float) -> str:
    if delta < 0:
        return "▼"
    if delta > 0:
        return "▲"
    return "—"

def stacked_bar_chart(df: pd.DataFrame, title: str, y_label: str):
    pivot = df.pivot_table(index="Scenario", columns="Component", values="Value", aggfunc="sum").fillna(0)
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    pivot.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(y_label)
    ax.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    st.pyplot(fig)

def kpi_grouped_barh(df_kpi: pd.DataFrame, title: str):
    metrics = df_kpi["Metric"].tolist()
    baseline_vals = df_kpi["Baseline"].tolist()
    option_vals = df_kpi["Option"].tolist()

    y = list(range(len(metrics)))
    h = 0.35

    fig, ax = plt.subplots(figsize=(8.5, 4.8))
    ax.barh([yy - h/2 for yy in y], baseline_vals, height=h, label="Baseline")
    ax.barh([yy + h/2 for yy in y], option_vals, height=h, label="Option")
    ax.set_yticks(y)
    ax.set_yticklabels(metrics)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    st.pyplot(fig)

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)

def _yn_to_bool(v: str):
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None

# =============================================================================
# DEFAULTS
# =============================================================================
def init_defaults():
    # Level A overrides (global)
    st.session_state.setdefault("ov_hot_water_l_ppd", float(ASSUMPTIONS["HOT_WATER_L_PPD"]["value"]))
    st.session_state.setdefault("ov_minutes_per_shower", float(ASSUMPTIONS["MINUTES_PER_SHOWER"]["value"]))
    st.session_state.setdefault("ov_electricity_tariff", float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["value"]))
    st.session_state.setdefault("ov_water_tariff", float(ASSUMPTIONS["WATER_TARIFF"]["value"]))

    # Scenario-level HDD override controls (Baseline & Option)
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_hdd_override_enabled", False)
        st.session_state.setdefault(f"{p}_hdd_override_value", None)

    # Scenario numeric defaults
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", 2.4)
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        st.session_state.setdefault(f"{p}_light_n", LIGHTING_DEFAULTS["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LIGHTING_DEFAULTS["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LIGHTING_DEFAULTS["hoursPerDay"])

        # Appliance water only
        st.session_state.setdefault(f"{p}_wash_has", "Yes")
        st.session_state.setdefault(f"{p}_wash_cycles", WASHING_MACHINE_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", WASHING_MACHINE_DEFAULTS["waterPerCycle_L"])

        st.session_state.setdefault(f"{p}_dish_has", "Yes")
        st.session_state.setdefault(f"{p}_dish_cycles", DISHWASHER_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", DISHWASHER_DEFAULTS["waterPerCycle_L"])

    # categorical defaults MUST be unselected
    cat_keys = [
        "climateZone", "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "heatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

    st.session_state.setdefault("show_results", False)
    st.session_state.setdefault("show_charts", True)

def get_scenario(prefix: str, A: dict) -> dict:
    climateZone = st.session_state[f"{prefix}_climateZone"]
    roof_label = st.session_state[f"{prefix}_roofRLabel"]
    wall_label = st.session_state[f"{prefix}_wallRLabel"]
    floor_label = st.session_state[f"{prefix}_floorRLabel"]
    win_label = st.session_state[f"{prefix}_windowULabel"]
    heat_sys = st.session_state[f"{prefix}_heatingSystem"]
    hw_sys = st.session_state[f"{prefix}_waterHeatingSystem"]
    toilet = st.session_state[f"{prefix}_toiletType"]
    shower = st.session_state[f"{prefix}_showerType"]
    tap = st.session_state[f"{prefix}_tapType"]

    wash_has = _yn_to_bool(st.session_state[f"{prefix}_wash_has"])
    dish_has = _yn_to_bool(st.session_state[f"{prefix}_dish_has"])

    def map_lookup(label, lookup):
        return None if label == PLACEHOLDER else float(lookup[label])

    # HDD override (per scenario)
    hdd_override = None
    if bool(st.session_state.get(f"{prefix}_hdd_override_enabled", False)):
        val = st.session_state.get(f"{prefix}_hdd_override_value", None)
        if val is not None:
            hdd_override = float(val)
            hdd_override = _clamp(hdd_override, ASSUMPTIONS["HDD_LOOKUP_BASE18"]["min"], ASSUMPTIONS["HDD_LOOKUP_BASE18"]["max"])

    scenario = {
        "climateZone": None if climateZone == PLACEHOLDER else climateZone,
        "HDD_override_base18": hdd_override,

        "floorArea": float(st.session_state[f"{prefix}_floorArea"]),
        "ceilingHeight": float(st.session_state[f"{prefix}_ceilingHeight"]),
        "householdSize": int(st.session_state[f"{prefix}_householdSize"]),
        "windowArea": float(st.session_state[f"{prefix}_windowArea"]),

        "roofRValue": map_lookup(roof_label, R_VALUES_ROOF),
        "wallRValue": map_lookup(wall_label, R_VALUES_WALLS),
        "floorRValue": map_lookup(floor_label, R_VALUES_FLOOR),
        "windowUValue": map_lookup(win_label, U_VALUES_WINDOWS),

        "heatingSystemEfficiency": map_lookup(heat_sys, HEATING_SYSTEMS),
        "waterHeatingEfficiency": map_lookup(hw_sys, WATER_HEATING_SYSTEMS),

        "toiletType": None if toilet == PLACEHOLDER else toilet,
        "showerType": None if shower == PLACEHOLDER else shower,
        "tapType": None if tap == PLACEHOLDER else tap,

        "lighting": {
            "numberOfLights": int(st.session_state[f"{prefix}_light_n"]),
            "wattsPerLight": float(st.session_state[f"{prefix}_light_watts"]),
            "hoursPerDay": float(st.session_state[f"{prefix}_light_hours"]),
        },

        "washingMachine": {
            "hasAppliance": wash_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_wash_cycles"]),
            "waterPerCycle_L": float(st.session_state[f"{prefix}_wash_L"]),
        },
        "dishwasher": {
            "hasAppliance": dish_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_dish_cycles"]),
            "waterPerCycle_L": float(st.session_state[f"{prefix}_dish_L"]),
        },

        # keep labels for capex (do not affect calculations)
        "_roof_label": roof_label if roof_label != PLACEHOLDER else "Uninsulated",
        "_wall_label": wall_label if wall_label != PLACEHOLDER else "Uninsulated",
        "_floor_label": floor_label if floor_label != PLACEHOLDER else "Uninsulated",
        "_window_label": win_label if win_label != PLACEHOLDER else "Single glazed",
        "_heating_label": heat_sys if heat_sys != PLACEHOLDER else "None",
        "_water_heating_label": hw_sys if hw_sys != PLACEHOLDER else "Electric storage cylinder (COP 1.0)",
    }
    return scenario

def validate_scenario(s: dict) -> list:
    missing = []
    if s["climateZone"] is None: missing.append("Climate zone")
    if s["roofRValue"] is None: missing.append("Roof insulation (R-value)")
    if s["wallRValue"] is None: missing.append("Wall insulation (R-value)")
    if s["floorRValue"] is None: missing.append("Floor insulation (R-value)")
    if s["windowUValue"] is None: missing.append("Window type (U-value)")
    if s["heatingSystemEfficiency"] is None: missing.append("Space heating system")
    if s["waterHeatingEfficiency"] is None: missing.append("Water heating system")
    if s["toiletType"] is None: missing.append("Toilet type")
    if s["showerType"] is None: missing.append("Shower type")
    if s["tapType"] is None: missing.append("Tap type")
    if s["washingMachine"]["hasAppliance"] is None: missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None: missing.append("Dishwasher (Yes/No)")
    return missing

def copy_baseline_to_option():
    mappings = [
        # categorical
        ("b_climateZone", "o_climateZone"),
        ("b_roofRLabel", "o_roofRLabel"),
        ("b_wallRLabel", "o_wallRLabel"),
        ("b_floorRLabel", "o_floorRLabel"),
        ("b_windowULabel", "o_windowULabel"),
        ("b_heatingSystem", "o_heatingSystem"),
        ("b_waterHeatingSystem", "o_waterHeatingSystem"),
        ("b_toiletType", "o_toiletType"),
        ("b_showerType", "o_showerType"),
        ("b_tapType", "o_tapType"),

        # numeric
        ("b_floorArea", "o_floorArea"),
        ("b_ceilingHeight", "o_ceilingHeight"),
        ("b_householdSize", "o_householdSize"),
        ("b_windowArea", "o_windowArea"),

        # lighting
        ("b_light_n", "o_light_n"),
        ("b_light_watts", "o_light_watts"),
        ("b_light_hours", "o_light_hours"),

        # appliance water
        ("b_wash_has", "o_wash_has"),
        ("b_wash_cycles", "o_wash_cycles"),
        ("b_wash_L", "o_wash_L"),
        ("b_dish_has", "o_dish_has"),
        ("b_dish_cycles", "o_dish_cycles"),
        ("b_dish_L", "o_dish_L"),

        # HDD override controls
        ("b_hdd_override_enabled", "o_hdd_override_enabled"),
        ("b_hdd_override_value", "o_hdd_override_value"),
    ]
    for src, dst in mappings:
        st.session_state[dst] = copy.deepcopy(st.session_state[src])

# =============================================================================
# APP
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.write(
    "Early-stage decision support for comparing housing scenarios. "
    "**Not a certification tool.** This prototype is designed for transparency and iteration."
)

tabs = st.tabs(["1) Scenario", "2) Assumptions", "3) Calculations", "4) Indicators"])

# -----------------------------------------------------------------------------#
# TAB 1: Scenario (Inputs + Results)
# -----------------------------------------------------------------------------#
with tabs[0]:
    # Resolve assumptions once per render
    level_a_overrides = get_level_a_overrides()
    A = resolve_assumptions(level_a_overrides)

    with st.expander("User overrides (Level A — limited, high-impact)", expanded=True):
        st.number_input(
            "Hot water demand (L/person/day)",
            min_value=float(ASSUMPTIONS["HOT_WATER_L_PPD"]["min"]),
            max_value=float(ASSUMPTIONS["HOT_WATER_L_PPD"]["max"]),
            step=float(ASSUMPTIONS["HOT_WATER_L_PPD"]["step"]),
            key="ov_hot_water_l_ppd",
            help="Overrides the default hot water demand assumption used in water heating."
        )
        st.number_input(
            "Minutes per shower (min)",
            min_value=float(ASSUMPTIONS["MINUTES_PER_SHOWER"]["min"]),
            max_value=float(ASSUMPTIONS["MINUTES_PER_SHOWER"]["max"]),
            step=float(ASSUMPTIONS["MINUTES_PER_SHOWER"]["step"]),
            key="ov_minutes_per_shower",
            help="Overrides shower duration used in indoor water consumption."
        )
        st.number_input(
            "Electricity tariff (NZD/kWh)",
            min_value=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["min"]),
            max_value=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["max"]),
            step=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["step"]),
            key="ov_electricity_tariff",
            help="Overrides tariff used for annual electricity cost."
        )
        st.number_input(
            "Water tariff (NZD/m³)",
            min_value=float(ASSUMPTIONS["WATER_TARIFF"]["min"]),
            max_value=float(ASSUMPTIONS["WATER_TARIFF"]["max"]),
            step=float(ASSUMPTIONS["WATER_TARIFF"]["step"]),
            key="ov_water_tariff",
            help="Overrides tariff used for annual water cost."
        )
        st.caption("HDD can be overridden per scenario under Core inputs.")

    col_b, col_o = st.columns([1.05, 1.05], gap="large")

    HDD_LOOKUP_BASE18 = A["HDD_LOOKUP_BASE18"]

    # -------------------- Baseline -------------------- #
    with col_b:
        st.subheader("Baseline")

        with st.expander("A) Core inputs", expanded=True):
            select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="b_climateZone")

            if st.session_state["b_climateZone"] != PLACEHOLDER:
                inferred = HDD_LOOKUP_BASE18[st.session_state["b_climateZone"]]
                st.caption(f"HDD (base 18°C, from lookup): **{inferred}**")

            st.checkbox("Override HDD for Baseline", key="b_hdd_override_enabled")
            if st.session_state["b_hdd_override_enabled"]:
                default_val = float(HDD_LOOKUP_BASE18.get(st.session_state["b_climateZone"], 2000)) if st.session_state["b_climateZone"] != PLACEHOLDER else 2000.0
                st.number_input(
                    "Baseline HDD override (base 18°C)",
                    min_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["min"]),
                    max_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["max"]),
                    step=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["step"]),
                    value=float(default_val) if st.session_state.get("b_hdd_override_value") is None else float(st.session_state["b_hdd_override_value"]),
                    key="b_hdd_override_value",
                    help="If enabled, this HDD value replaces the climate-zone lookup for space heating."
                )

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="b_floorArea")
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="b_ceilingHeight")
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="b_householdSize")
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="b_windowArea")

        with st.expander("B) Thermal envelope", expanded=False):
            select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key="b_roofRLabel")
            if st.session_state["b_roofRLabel"] != PLACEHOLDER:
                r = R_VALUES_ROOF[st.session_state["b_roofRLabel"]]
                st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

            select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key="b_wallRLabel")
            if st.session_state["b_wallRLabel"] != PLACEHOLDER:
                r = R_VALUES_WALLS[st.session_state["b_wallRLabel"]]
                st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

            select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key="b_floorRLabel")
            if st.session_state["b_floorRLabel"] != PLACEHOLDER:
                r = R_VALUES_FLOOR[st.session_state["b_floorRLabel"]]
                st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

            select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key="b_windowULabel")
            if st.session_state["b_windowULabel"] != PLACEHOLDER:
                u = U_VALUES_WINDOWS[st.session_state["b_windowULabel"]]
                st.caption(f"U={u:.1f} W/m²K")

        with st.expander("C) Systems (Energy)", expanded=False):
            select_with_placeholder("Space heating system", list(HEATING_SYSTEMS.keys()), key="b_heatingSystem")
            if st.session_state["b_heatingSystem"] != PLACEHOLDER:
                st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[st.session_state['b_heatingSystem']]}**")

            select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="b_waterHeatingSystem")
            if st.session_state["b_waterHeatingSystem"] != PLACEHOLDER:
                st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[st.session_state['b_waterHeatingSystem']]}**")

        with st.expander("D) Lighting (Energy; no plug loads)", expanded=False):
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="b_light_n")
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="b_light_watts")
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="b_light_hours")
            st.caption("Energy excludes appliances/plug loads (see Tab 4 for boundary).")

        with st.expander("E) Water fixtures + appliance water", expanded=False):
            select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="b_toiletType")
            select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="b_showerType")
            select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="b_tapType")

            st.markdown("**Washing machine (water only)**")
            select_with_placeholder("Has washing machine?", ["Yes", "No"], key="b_wash_has")
            if st.session_state["b_wash_has"] == "Yes":
                st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="b_wash_cycles")
                st.number_input("L/cycle (washing) [PLACEHOLDER]", min_value=0.0, max_value=300.0, step=5.0, key="b_wash_L")

            st.markdown("**Dishwasher (water only)**")
            select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="b_dish_has")
            if st.session_state["b_dish_has"] == "Yes":
                st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="b_dish_cycles")
                st.number_input("L/cycle (dishwasher) [PLACEHOLDER]", min_value=0.0, max_value=100.0, step=1.0, key="b_dish_L")

        st.divider()
        if st.button("Copy Baseline → Option", use_container_width=True):
            copy_baseline_to_option()
            st.rerun()

    # -------------------- Option -------------------- #
    with col_o:
        st.subheader("Option")

        with st.expander("A) Core inputs", expanded=True):
            select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="o_climateZone")

            if st.session_state["o_climateZone"] != PLACEHOLDER:
                inferred = HDD_LOOKUP_BASE18[st.session_state["o_climateZone"]]
                st.caption(f"HDD (base 18°C, from lookup): **{inferred}**")

            st.checkbox("Override HDD for Option", key="o_hdd_override_enabled")
            if st.session_state["o_hdd_override_enabled"]:
                default_val = float(HDD_LOOKUP_BASE18.get(st.session_state["o_climateZone"], 2000)) if st.session_state["o_climateZone"] != PLACEHOLDER else 2000.0
                st.number_input(
                    "Option HDD override (base 18°C)",
                    min_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["min"]),
                    max_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["max"]),
                    step=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["step"]),
                    value=float(default_val) if st.session_state.get("o_hdd_override_value") is None else float(st.session_state["o_hdd_override_value"]),
                    key="o_hdd_override_value",
                    help="If enabled, this HDD value replaces the climate-zone lookup for space heating."
                )

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="o_floorArea")
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="o_ceilingHeight")
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="o_householdSize")
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="o_windowArea")

        with st.expander("B) Thermal envelope", expanded=False):
            select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key="o_roofRLabel")
            select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key="o_wallRLabel")
            select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key="o_floorRLabel")
            select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key="o_windowULabel")

        with st.expander("C) Systems (Energy)", expanded=False):
            select_with_placeholder("Space heating system", list(HEATING_SYSTEMS.keys()), key="o_heatingSystem")
            select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="o_waterHeatingSystem")

        with st.expander("D) Lighting (Energy; no plug loads)", expanded=False):
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="o_light_n")
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="o_light_watts")
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="o_light_hours")

        with st.expander("E) Water fixtures + appliance water", expanded=False):
            select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="o_toiletType")
            select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="o_showerType")
            select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="o_tapType")

            st.markdown("**Washing machine (water only)**")
            select_with_placeholder("Has washing machine?", ["Yes", "No"], key="o_wash_has")
            if st.session_state["o_wash_has"] == "Yes":
                st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="o_wash_cycles")
                st.number_input("L/cycle (washing) [PLACEHOLDER]", min_value=0.0, max_value=300.0, step=5.0, key="o_wash_L")

            st.markdown("**Dishwasher (water only)**")
            select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="o_dish_has")
            if st.session_state["o_dish_has"] == "Yes":
                st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="o_dish_cycles")
                st.number_input("L/cycle (dishwasher) [PLACEHOLDER]", min_value=0.0, max_value=100.0, step=1.0, key="o_dish_L")

    # -------------------- Results -------------------- #
    st.divider()

    baseline_now = get_scenario("b", A)
    option_now = get_scenario("o", A)

    missing_b = validate_scenario(baseline_now)
    missing_o = validate_scenario(option_now)

    top_left, top_right = st.columns([1, 1])
    with top_left:
        st.session_state["show_results"] = st.toggle("Show results", value=st.session_state["show_results"])
    with top_right:
        st.session_state["show_charts"] = st.toggle("Show charts", value=st.session_state["show_charts"])

    if missing_b:
        st.info("Baseline incomplete. Missing: " + ", ".join(missing_b))
        st.stop()

    base_r = calculate_scenario(baseline_now, A)

    opt_r = None if missing_o else calculate_scenario(option_now, A)

    capex = None
    if opt_r is not None:
        capex = calculate_incremental_capex(baseline_now, option_now, A)

    # Payload includes: resolved assumptions + overrides + hash for audit
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "assumptions": {
            "resolved": {
                # Keep resolved values compact and audit-friendly
                "HOT_WATER_L_PPD": float(A["HOT_WATER_L_PPD"]),
                "MINUTES_PER_SHOWER": float(A["MINUTES_PER_SHOWER"]),
                "ELECTRICITY_TARIFF": float(A["ELECTRICITY_TARIFF"]),
                "WATER_TARIFF": float(A["WATER_TARIFF"]),
                "GRID_EMISSION_FACTOR": float(A["GRID_EMISSION_FACTOR"]),
                "WATER_EMISSION_FACTOR": float(A["WATER_EMISSION_FACTOR"]),
                "TOILET_FLUSHES_PER_PERSON_DAY": float(A["TOILET_FLUSHES_PER_PERSON_DAY"]),
                "SHOWERS_PER_PERSON_DAY": float(A["SHOWERS_PER_PERSON_DAY"]),
                "TAP_MINUTES_PER_PERSON_DAY": float(A["TAP_MINUTES_PER_PERSON_DAY"]),
                "HOT_WATER_SETPOINT_C": float(A["HOT_WATER_SETPOINT_C"]),
                "COLD_WATER_INLET_C": float(A["COLD_WATER_INLET_C"]),
            },
            "level_a_overrides": level_a_overrides,
        },
        "baseline": {"inputs": baseline_now, "results": base_r, "missing": []},
        "option": {"inputs": option_now, "results": opt_r, "missing": missing_o},
        "capex": capex,
        "notes": {
            "scope": "Early-stage decision support; not certification; not predictive modelling.",
            "energy_boundary": "Energy excludes appliances/plug loads; includes space heating + water heating + lighting.",
            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
            "carbon_scope": "Electricity + supplied water only (average factors). No embodied carbon.",
            "coefficients": "Some coefficients are placeholders unless replaced with sourced NZ values.",
        },
    }
    payload["payload_hash_sha256"] = _stable_hash(payload)

    if not st.session_state["show_results"]:
        st.caption("Results are computed in the background; enable **Show results** to view.")
        st.stop()

    # KPI table
    def kpi_rows():
        rows = [
            ("Total Energy (excl. plug loads)", base_r["totalElectricity_kwh_y"], None if opt_r is None else opt_r["totalElectricity_kwh_y"], "kWh/year", 1),
            ("Energy Intensity", base_r["energyIntensity_kwh_m2_y"], None if opt_r is None else opt_r["energyIntensity_kwh_m2_y"], "kWh/m²/year", 2),
            ("Water Consumption", base_r["waterConsumption"]["V_total_m3_y"], None if opt_r is None else opt_r["waterConsumption"]["V_total_m3_y"], "m³/year", 2),
            ("Operational Carbon", base_r["carbon"]["CO2_total_kg_y"], None if opt_r is None else opt_r["carbon"]["CO2_total_kg_y"], "kgCO₂e/year", 1),
            ("Annual Operating Cost (Opex)", base_r["opex"]["opex_total_nzd_y"], None if opt_r is None else opt_r["opex"]["opex_total_nzd_y"], "NZD/year", 0),
        ]
        if capex is not None:
            rows.append(("Incremental Capex (Option−Baseline)", 0.0, capex["capex_incremental_nzd"], "NZD", 0))

            savings = base_r["opex"]["opex_total_nzd_y"] - opt_r["opex"]["opex_total_nzd_y"]
            pb = (capex["capex_incremental_nzd"] / savings) if savings and savings > 0 else None
            rows.append(("Simple Payback", None, pb, "years", 1))

        out = []
        for name, b, o, unit, dec in rows:
            if o is None:
                out.append({"Metric": name, "Baseline": fmt_num(b, dec) if b is not None else "—", "Option": "—", "Δ (Option−Base)": "—", "Dir": "—", "Unit": unit})
            else:
                d = (o - b) if (b is not None and o is not None) else None
                out.append({"Metric": name, "Baseline": fmt_num(b, dec) if b is not None else "—", "Option": fmt_num(o, dec), "Δ (Option−Base)": fmt_num(d, dec) if d is not None else "—", "Dir": direction_arrow(d) if d is not None else "—", "Unit": unit})
        return out

    st.markdown("### Key Performance Indicators")
    st.dataframe(pd.DataFrame(kpi_rows()), use_container_width=True, hide_index=True)

    if opt_r is None:
        st.info("Option incomplete. Complete Option inputs (or use **Copy Baseline → Option**) to enable comparison charts and capex.")
        st.stop()

    # Charts
    if st.session_state["show_charts"]:
        st.divider()
        tabs2 = st.tabs(["KPIs", "Energy", "Water", "Carbon", "Opex", "Capex (placeholder)"])

        with tabs2[0]:
            df_kpi = pd.DataFrame([
                {"Metric": "Energy (kWh/y)", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
                {"Metric": "Energy Intensity (kWh/m²/y)", "Baseline": base_r["energyIntensity_kwh_m2_y"], "Option": opt_r["energyIntensity_kwh_m2_y"]},
                {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
                {"Metric": "Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
                {"Metric": "Opex (NZD/y)", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
            ])
            kpi_grouped_barh(df_kpi, "KPIs: Baseline vs Option")

        with tabs2[1]:
            df_energy = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
                {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_total_kwh_y"]},
            ])
            stacked_bar_chart(df_energy, "Energy breakdown (excl. plug loads)", "kWh/year")

        with tabs2[2]:
            b = base_r["waterConsumption"]["breakdown_m3_y"]
            o = opt_r["waterConsumption"]["breakdown_m3_y"]
            df_water = pd.DataFrame(
                [{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b.items()] +
                [{"Scenario": "Option", "Component": k, "Value": v} for k, v in o.items()]
            )
            stacked_bar_chart(df_water, "Indoor water breakdown", "m³/year")

        with tabs2[3]:
            df_carbon = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity_kg_y"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water_kg_y"]},
            ])
            stacked_bar_chart(df_carbon, "Operational carbon breakdown", "kgCO₂e/year")

        with tabs2[4]:
            df_opex = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["opex"]["opex_electricity_nzd_y"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["opex"]["opex_water_nzd_y"]},
            ])
            stacked_bar_chart(df_opex, "Opex breakdown", "NZD/year")

        with tabs2[5]:
            st.caption("Capex is a minimal placeholder model to support early-stage trade-offs (not investment-grade).")
            df_capex = pd.DataFrame(
                [{"Component": k, "Incremental Capex (NZD)": v} for k, v in capex["breakdown_nzd"].items()]
            )
            st.dataframe(df_capex, use_container_width=True, hide_index=True)

    st.divider()
    st.download_button(
        "Download results (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"housing-sustainability-comparison-{int(datetime.utcnow().timestamp())}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.caption(
        "Notes: Simplified and indicative. No embodied carbon. No behavioural modelling. "
        "No ventilation/infiltration gains/losses. Many coefficients remain placeholders."
    )

# -----------------------------------------------------------------------------#
# TAB 2: Assumptions (Auditable Provenance Table)
# -----------------------------------------------------------------------------#
with tabs[1]:
    st.subheader("Assumptions and Provenance (Auditable)")
    st.write(
        "This tab documents the model’s parameters and default assumptions, including provenance and governance. "
        "Only **Level A** overrides are available (Tab 1)."
    )

    # Build a fully auditable assumptions table
    level_a_overrides = get_level_a_overrides()
    A = resolve_assumptions(level_a_overrides)

    def _render_value(v):
        if isinstance(v, dict):
            # show compact summary for dicts
            keys = list(v.keys())
            if len(keys) <= 6:
                return "; ".join([f"{k}={v[k]}" for k in keys])
            return f"<dict> ({len(keys)} items)"
        return v

    rows = []
    for k, meta in ASSUMPTIONS.items():
        rows.append({
            "Parameter name (machine-readable)": k,
            "Value (default) + unit": f"{_render_value(meta.get('value'))} {meta.get('unit','')}".strip(),
            "Where used": meta.get("where_used", "—"),
            "Source type": meta.get("source_type", "—"),
            "Citation / link / doc": meta.get("citation", "—"),
            "Rationale": meta.get("rationale", "—"),
            "Sensitivity": meta.get("sensitivity", "—"),
            "Override allowed?": "Yes" if meta.get("override_allowed", False) else "No",
            "Override location (UI)": meta.get("override_ui", "—"),
            "Validation rule": meta.get("validation_rule", "—"),
            "Resolved value used now": _render_value(A.get(k, meta.get("value"))),
        })

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "Governance note: Defaults remain authoritative; overrides only replace the resolved value used by calculations. "
        "No certification logic is implemented."
    )

# -----------------------------------------------------------------------------#
# TAB 3: Calculations (Formulas + “where from”)
# -----------------------------------------------------------------------------#
with tabs[2]:
    st.subheader("Calculations (How the Prototype Computes Outputs)")
    st.markdown(
        """
**Important:** These equations are simplified and intentionally transparent. They are not ECCHO.

### 1) Space Heating (steady-state heat loss + HDD)
- Heat loss coefficient:
  - \(H = A_{roof}U_{roof} + A_{wall}U_{wall} + A_{floor}U_{floor} + A_{win}U_{win}\)
- Annual delivered heat (kWh/y):
  - \(Q_{del} = (H \\times HDD \\times 24) / 1000\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

**HDD governance:** HDD is derived from the climate zone lookup by default; users may override HDD per scenario (Level A).

### 2) Water Heating (volume + temperature rise)
- Annual hot water volume:
  - \(V_y = n \\times L_{ppd} \\times 365\)
- Delivered thermal energy:
  - \(Q_{del} = (V_y \\times \\Delta T \\times C_p) / 3600\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

**Governance:** \(L_{ppd}\) is user overrideable (Level A); setpoint and inlet temperature are fixed defaults.

### 3) Lighting Electricity
- \(Q_{light} = (N_{lights} \\times W_{light} \\times h_{day} \\times 365)/1000\)

### 4) Water Consumption (indoor end-use)
- Toilets:
  - \(V_{toilet} = n \\times flushes \\times L_{flush} \\times 365\)
- Showers:
  - \(V_{shower} = n \\times showers \\times min_{shower} \\times L/min \\times 365\)
- Taps:
  - \(V_{tap} = n \\times min_{tap} \\times L/min \\times 365\)
- Appliances (water only):
  - \(V_{wash} = cycles/wk \\times L/cycle \\times 52\)
  - \(V_{dish} = cycles/wk \\times L/cycle \\times 52\)

### 5) Operational Carbon
- Electricity:
  - \(CO2_e = kWh \\times EF_{grid}\)
- Water:
  - \(CO2_w = m^3 \\times EF_{water}\)
- Total:
  - \(CO2 = CO2_e + CO2_w\)

### 6) Opex
- Electricity:
  - \(Cost_e = kWh \\times tariff_e\)
- Water:
  - \(Cost_w = m^3 \\times tariff_w\)

### 7) Incremental Capex (placeholder)
- Element-level deltas (Option − Baseline), aggregated to a single incremental capex.
- Simple payback:
  - \(Payback = Capex / (Opex_{base} - Opex_{option})\) when savings > 0.
        """
    )

# -----------------------------------------------------------------------------#
# TAB 4: Indicators (Definitions + Boundaries)
# -----------------------------------------------------------------------------#
with tabs[3]:
    st.subheader("Indicators (Definitions and Scope)")
    st.markdown(
        """
### Energy KPI (kWh/year)
**Includes:** space heating + water heating + lighting.  
**Excludes:** appliances and plug loads (dishwasher energy, washing machine energy, cooking, electronics).  
**Why:** This prototype intentionally isolates design-sensitive drivers and avoids behavioural noise at early-stage design.

### Water KPI (m³/year)
**Includes:** toilets, showers, taps, plus dishwasher and washing machine water use.  
**Excludes:** outdoor irrigation, leakage, seasonal variation, rainwater offsets (not implemented).  
**Why:** appliance water is a material indoor end-use and supports demand realism.

### Operational Carbon (kgCO₂e/year)
**Includes:** electricity + supplied water only, using average emission factors.  
**Excludes:** embodied carbon, marginal emissions, time-of-use effects, refrigerants.  
**Why:** scope is constrained to operational flows with transparent coefficients.

### Operating Cost / Opex (NZD/year)
**Includes:** variable electricity + variable water costs.  
**Excludes:** fixed charges, time-of-use pricing, demand charges, maintenance.

### Incremental Capex (NZD)
**Represents:** a minimal, transparent estimate of upgrade deltas (Option − Baseline).  
**Limitations:** not QS-grade; placeholder unit costs; no financing, discounting, replacement cycles.

### What this tool is not
This is **not** a Homestar or ECCHO calculator, **not** a simulation model, and **not** suitable for certification or compliance.
        """
    )
