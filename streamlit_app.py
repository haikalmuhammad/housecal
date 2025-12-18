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
# MODEL + ASSUMPTIONS (kept in this single script, versioned, exportable)
# =============================================================================
MODEL_VERSION = "0.3.0"
ASSUMPTIONS_VERSION = "0.3.0"
ASSUMPTIONS_NOTE = (
    "Prototype assumptions. Replace HDD/emission factors/tariffs/CAPEX costs with authoritative NZ sources "
    "for production use."
)

# ------------------------------
# Climate (HDD base 18°C)
# ------------------------------
HDD_LOOKUP_BASE18 = {
    "Zone 1 (Warmest - e.g., Northland)": 1200,
    "Zone 2 (Warm - e.g., Auckland)": 1600,
    "Zone 3 (Mild - e.g., Wellington)": 2000,
    "Zone 4 (Cool - e.g., Christchurch)": 2400,
    "Zone 5 (Cold - e.g., Queenstown)": 2800,
    "Zone 6 (Coldest - e.g., Central Otago)": 3200,
}

# ------------------------------
# Envelope performance
# ------------------------------
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

# ------------------------------
# Systems (efficiency / COP)
# ------------------------------
HEATING_SYSTEMS = {
    "Electric resistance": 1.0,
    "Heat pump (COP 3.0)": 3.0,
    "Heat pump (COP 4.0)": 4.0,
}

WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder": 1.0,
    "Heat pump hot water (COP 2.5)": 2.5,
    "Heat pump hot water (COP 3.0)": 3.0,
}

# ------------------------------
# Fixtures (water intensities)
# ------------------------------
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

# ------------------------------
# Usage defaults (lighting is energy; laundry/dish are water only)
# ------------------------------
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}
WASHING_MACHINE_DEFAULTS = {"cyclesPerWeek": 4, "waterPerCycle": 60}
DISHWASHER_DEFAULTS = {"cyclesPerWeek": 4, "waterPerCycle": 12}

# ------------------------------
# Carbon + tariffs (placeholders)
# ------------------------------
GRID_EMISSION_FACTOR = 0.10   # kgCO2e/kWh (placeholder)
GRID_EF_YEAR = "PLACEHOLDER"
WATER_EMISSION_FACTOR = 0.63  # kgCO2e/m³ (placeholder)
WATER_EF_YEAR = "PLACEHOLDER"

ELECTRICITY_TARIFF = 0.30  # NZD/kWh (placeholder)
WATER_TARIFF = 2.50        # NZD/m³ (placeholder)

# ------------------------------
# CAPEX assumptions (minimal; no extra user inputs)
# Incremental upgrade costs, applied using BASELINE geometry for comparability.
# Negative deltas are clamped to 0 (no credit for downgrades).
# ------------------------------
ASSUME_NUM_TOILETS = 1
ASSUME_NUM_SHOWERS = 1
ASSUME_NUM_TAPS = 3

CAPEX_ROOF_NZD_PER_M2 = {
    "Uninsulated": 0,
    "Basic (R2.0)": 25,
    "Code minimum (R3.3)": 35,
    "Good (R4.6)": 50,
    "Excellent (R6.0)": 70,
}
CAPEX_WALL_NZD_PER_M2 = {
    "Uninsulated": 0,
    "Basic (R1.5)": 30,
    "Code minimum (R2.0)": 40,
    "Good (R2.8)": 55,
    "Excellent (R4.0)": 80,
}
CAPEX_FLOOR_NZD_PER_M2 = {
    "Uninsulated": 0,
    "Basic (R1.3)": 25,
    "Code minimum (R2.0)": 35,
    "Good (R3.0)": 55,
    "Excellent (R4.0)": 75,
}
CAPEX_WINDOW_NZD_PER_M2 = {
    "Single glazed": 0,
    "Standard double glazed": 350,
    "Low-E double glazed": 550,
    "High performance triple": 900,
}
CAPEX_HEATING_SYSTEM_NZD = {
    "Electric resistance": 0,
    "Heat pump (COP 3.0)": 3500,
    "Heat pump (COP 4.0)": 4500,
}
CAPEX_WATER_HEATING_SYSTEM_NZD = {
    "Electric storage cylinder": 0,
    "Heat pump hot water (COP 2.5)": 4200,
    "Heat pump hot water (COP 3.0)": 5200,
}
CAPEX_TOILET_NZD = {
    "Single flush (9L)": 0,
    "Dual flush standard (6/3L avg 5L)": 250,
    "Dual flush efficient (4.5/3L avg 4L)": 400,
}
CAPEX_SHOWER_NZD = {
    "Standard (9 L/min)": 0,
    "Low-flow (7 L/min)": 80,
    "Efficient (6 L/min)": 140,
}
CAPEX_TAP_NZD = {
    "Standard (8 L/min)": 0,
    "Efficient (6 L/min)": 20,
    "Very efficient (4 L/min)": 40,
}

PROVENANCE = {
    "energy_scope": "Core operational electricity excludes plug loads (appliances) to preserve comparability.",
    "geometry": "Wall area uses a square-footprint approximation: perimeter = 4*sqrt(floorArea).",
    "capex": "CAPEX values are placeholders (order-of-magnitude). Replace with NZ cost data for production.",
    "efs_tariffs": "Emission factors and tariffs are placeholders; replace with authoritative NZ sources and reference year.",
    "water_units": "Water is calculated/stored in m³/year for costing and emissions; L/person/day is derived for interpretability.",
}

# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================

def estimate_geometry_areas(inputs: dict) -> dict:
    """
    Assumes square footprint: perimeter = 4*sqrt(floorArea)
    Wall area = perimeter*height - windowArea (clamped at >=0)
    """
    floor_area = float(inputs["floorArea"])
    ceiling_h = float(inputs["ceilingHeight"])
    window_area = float(inputs["windowArea"])

    roof_area = floor_area
    perimeter = 4.0 * math.sqrt(max(floor_area, 0.0))
    wall_area = max(perimeter * ceiling_h - window_area, 0.0)

    return {
        "roofArea": roof_area,
        "floorArea": floor_area,
        "perimeter": perimeter,
        "wallArea": wall_area,
        "windowArea": window_area,
    }

def calculate_space_heating(inputs: dict) -> dict:
    HDD = HDD_LOOKUP_BASE18[inputs["climateZone"]]

    roofU = 1.0 / inputs["roofRValue"]
    wallU = 1.0 / inputs["wallRValue"]
    floorU = 1.0 / inputs["floorRValue"]

    areas = estimate_geometry_areas(inputs)

    H_roof = areas["roofArea"] * roofU
    H_wall = areas["wallArea"] * wallU
    H_floor = areas["floorArea"] * floorU
    H_window = areas["windowArea"] * inputs["windowUValue"]
    H_total = H_roof + H_wall + H_floor + H_window

    Q_delivered = (H_total * HDD * 24.0) / 1000.0  # kWh/year

    eff = inputs["heatingSystemEfficiency"]
    Q_purchased = (Q_delivered / eff) if eff and eff > 0 else 0.0

    return {
        "Q_delivered": Q_delivered,
        "Q_purchased": Q_purchased,
        "H_total": H_total,
        "areas": areas,
        "breakdown": {"H_roof": H_roof, "H_wall": H_wall, "H_floor": H_floor, "H_window": H_window},
    }

def calculate_water_heating(inputs: dict, advanced: dict) -> dict:
    n = int(inputs["householdSize"])
    L_per_person_day = float(advanced["hotWaterPerPersonPerDay"])
    T_hot = float(advanced["hotWaterTemp"])
    T_cold = float(advanced["coldWaterTemp"])

    V_annual_L = n * L_per_person_day * 365.0
    deltaT = T_hot - T_cold

    specificHeat = 4.186  # kJ/kg°C
    Q_delivered = (V_annual_L * deltaT * specificHeat) / 3600.0  # kWh/year

    eff = inputs["waterHeatingEfficiency"]
    Q_purchased = (Q_delivered / eff) if eff and eff > 0 else Q_delivered

    return {"Q_delivered": Q_delivered, "Q_purchased": Q_purchased, "V_annual_L": V_annual_L}

def calculate_lighting(inputs: dict) -> dict:
    lighting = inputs["lighting"]
    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_lighting": Q_lighting}

def calculate_water_consumption(inputs: dict, advanced: dict) -> dict:
    """
    Returns totals in m³/year (internal standard), plus breakdown in m³/year.
    Includes: toilets, showers, taps, laundry, dishwasher.
    """
    n = int(inputs["householdSize"])

    toiletL = TOILET_TYPES[inputs["toiletType"]]
    showerLmin = SHOWER_TYPES[inputs["showerType"]]
    tapLmin = TAP_TYPES[inputs["tapType"]]

    flushes = float(advanced["toiletFlushesPerDay"])
    showers = float(advanced["showersPerDay"])
    showerMinutes = float(advanced["showerMinutes"])
    tapMinutes = float(advanced["tapMinutesPerDay"])

    V_toilet_L = n * flushes * toiletL * 365.0
    V_shower_L = n * showers * showerMinutes * showerLmin * 365.0
    V_taps_L = n * tapMinutes * tapLmin * 365.0

    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]

    V_laundry_L = washing["cyclesPerWeek"] * washing["waterPerCycle"] * 52.0 if washing["hasAppliance"] else 0.0
    V_dish_L = dish["cyclesPerWeek"] * dish["waterPerCycle"] * 52.0 if dish["hasAppliance"] else 0.0

    V_total_m3 = (V_toilet_L + V_shower_L + V_taps_L + V_laundry_L + V_dish_L) / 1000.0

    return {
        "V_total_m3": V_total_m3,
        "breakdown_m3": {
            "V_toilet": V_toilet_L / 1000.0,
            "V_shower": V_shower_L / 1000.0,
            "V_taps": V_taps_L / 1000.0,
            "V_laundry": V_laundry_L / 1000.0,
            "V_dishwasher": V_dish_L / 1000.0,
        },
    }

def calculate_operational_carbon(total_kwh: float, total_m3: float) -> dict:
    CO2_e = total_kwh * GRID_EMISSION_FACTOR
    CO2_w = total_m3 * WATER_EMISSION_FACTOR
    return {"CO2_total": CO2_e + CO2_w, "CO2_electricity": CO2_e, "CO2_water": CO2_w}

def calculate_opex(total_kwh: float, total_m3: float) -> dict:
    c_e = total_kwh * ELECTRICITY_TARIFF
    c_w = total_m3 * WATER_TARIFF
    return {"cost_total": c_e + c_w, "cost_electricity": c_e, "cost_water": c_w}

def _capex_delta(new_cost: float, old_cost: float) -> float:
    return max(0.0, float(new_cost) - float(old_cost))

def estimate_capex_incremental(baseline_inputs: dict, option_inputs: dict) -> dict:
    """
    Minimal incremental CAPEX using baseline geometry.
    Uses selection labels (R/U/system/fixtures) and applies assumed unit costs.
    """
    geom = estimate_geometry_areas(baseline_inputs)

    # Envelope deltas (NZD/m²)
    capex_roof = geom["roofArea"] * _capex_delta(
        CAPEX_ROOF_NZD_PER_M2[option_inputs["roofRLabel"]],
        CAPEX_ROOF_NZD_PER_M2[baseline_inputs["roofRLabel"]],
    )
    capex_wall = geom["wallArea"] * _capex_delta(
        CAPEX_WALL_NZD_PER_M2[option_inputs["wallRLabel"]],
        CAPEX_WALL_NZD_PER_M2[baseline_inputs["wallRLabel"]],
    )
    capex_floor = geom["floorArea"] * _capex_delta(
        CAPEX_FLOOR_NZD_PER_M2[option_inputs["floorRLabel"]],
        CAPEX_FLOOR_NZD_PER_M2[baseline_inputs["floorRLabel"]],
    )
    capex_windows = geom["windowArea"] * _capex_delta(
        CAPEX_WINDOW_NZD_PER_M2[option_inputs["windowULabel"]],
        CAPEX_WINDOW_NZD_PER_M2[baseline_inputs["windowULabel"]],
    )

    # Systems (NZD per dwelling)
    capex_heating = _capex_delta(
        CAPEX_HEATING_SYSTEM_NZD[option_inputs["heatingSystemLabel"]],
        CAPEX_HEATING_SYSTEM_NZD[baseline_inputs["heatingSystemLabel"]],
    )
    capex_hw = _capex_delta(
        CAPEX_WATER_HEATING_SYSTEM_NZD[option_inputs["waterHeatingSystemLabel"]],
        CAPEX_WATER_HEATING_SYSTEM_NZD[baseline_inputs["waterHeatingSystemLabel"]],
    )

    # Fixtures (assumed counts)
    capex_toilet = ASSUME_NUM_TOILETS * _capex_delta(
        CAPEX_TOILET_NZD[option_inputs["toiletTypeLabel"]],
        CAPEX_TOILET_NZD[baseline_inputs["toiletTypeLabel"]],
    )
    capex_shower = ASSUME_NUM_SHOWERS * _capex_delta(
        CAPEX_SHOWER_NZD[option_inputs["showerTypeLabel"]],
        CAPEX_SHOWER_NZD[baseline_inputs["showerTypeLabel"]],
    )
    capex_taps = ASSUME_NUM_TAPS * _capex_delta(
        CAPEX_TAP_NZD[option_inputs["tapTypeLabel"]],
        CAPEX_TAP_NZD[baseline_inputs["tapTypeLabel"]],
    )

    breakdown = {
        "Insulation - Roof": capex_roof,
        "Insulation - Walls": capex_wall,
        "Insulation - Floor": capex_floor,
        "Windows": capex_windows,
        "Heating system": capex_heating,
        "Water heating system": capex_hw,
        "Toilet fixtures": capex_toilet,
        "Shower fixtures": capex_shower,
        "Tap fixtures": capex_taps,
    }
    total = float(sum(breakdown.values()))

    return {
        "capex_total": total,
        "capex_breakdown": breakdown,
        "capex_geometry_basis": "baseline",
        "assumed_counts": {"toilets": ASSUME_NUM_TOILETS, "showers": ASSUME_NUM_SHOWERS, "taps": ASSUME_NUM_TAPS},
    }

def calculate_scenario(inputs: dict, advanced: dict) -> dict:
    space = calculate_space_heating(inputs)
    water_heat = calculate_water_heating(inputs, advanced)
    lighting = calculate_lighting(inputs)
    water_use = calculate_water_consumption(inputs, advanced)

    # Core operational electricity ONLY: space heating + water heating + lighting
    total_kwh = space["Q_purchased"] + water_heat["Q_purchased"] + lighting["Q_lighting"]

    carbon = calculate_operational_carbon(total_kwh, water_use["V_total_m3"])
    costs = calculate_opex(total_kwh, water_use["V_total_m3"])

    energy_intensity = (total_kwh / inputs["floorArea"]) if inputs["floorArea"] > 0 else 0.0

    n = max(int(inputs["householdSize"]), 1)
    water_L_per_person_day = (water_use["V_total_m3"] * 1000.0) / n / 365.0

    return {
        "spaceHeating": space,
        "waterHeating": water_heat,
        "lighting": lighting,
        "waterConsumption": water_use,
        "totalElectricity_kwh": total_kwh,
        "carbon": carbon,
        "costs": costs,
        "energyIntensity": energy_intensity,
        "water_L_per_person_day": water_L_per_person_day,
    }

# =============================================================================
# STATE / UTIL
# =============================================================================

def _stable_hash(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def init_defaults():
    # Advanced settings (user-overridable)
    st.session_state.setdefault("adv_hotWaterPerPersonPerDay", 50.0)
    st.session_state.setdefault("adv_hotWaterTemp", 60.0)
    st.session_state.setdefault("adv_coldWaterTemp", 15.0)
    st.session_state.setdefault("adv_toiletFlushesPerDay", 5.0)
    st.session_state.setdefault("adv_showersPerDay", 1.0)
    st.session_state.setdefault("adv_showerMinutes", 8.0)
    st.session_state.setdefault("adv_tapMinutesPerDay", 10.0)

    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", 2.4)
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        # Lighting (energy)
        st.session_state.setdefault(f"{p}_light_n", LIGHTING_DEFAULTS["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LIGHTING_DEFAULTS["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LIGHTING_DEFAULTS["hoursPerDay"])

        # Laundry + dishwasher (water only)
        st.session_state.setdefault(f"{p}_wash_cycles", WASHING_MACHINE_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", WASHING_MACHINE_DEFAULTS["waterPerCycle"])

        st.session_state.setdefault(f"{p}_dish_cycles", DISHWASHER_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", DISHWASHER_DEFAULTS["waterPerCycle"])

    # categorical defaults MUST be unselected
    cat_keys = [
        "climateZone", "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "heatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
        "wash_has", "dish_has",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

    st.session_state.setdefault("has_calculated", False)
    st.session_state.setdefault("last_payload", None)
    st.session_state.setdefault("last_signature", None)
    st.session_state.setdefault("show_advanced", False)

def get_advanced_settings() -> dict:
    return {
        "hotWaterPerPersonPerDay": float(st.session_state["adv_hotWaterPerPersonPerDay"]),
        "hotWaterTemp": float(st.session_state["adv_hotWaterTemp"]),
        "coldWaterTemp": float(st.session_state["adv_coldWaterTemp"]),
        "toiletFlushesPerDay": float(st.session_state["adv_toiletFlushesPerDay"]),
        "showersPerDay": float(st.session_state["adv_showersPerDay"]),
        "showerMinutes": float(st.session_state["adv_showerMinutes"]),
        "tapMinutesPerDay": float(st.session_state["adv_tapMinutesPerDay"]),
    }

def _yn_to_bool(v: str):
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None

def get_scenario(prefix: str) -> dict:
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

    scenario = {
        "climateZone": None if climateZone == PLACEHOLDER else climateZone,
        "floorArea": float(st.session_state[f"{prefix}_floorArea"]),
        "ceilingHeight": float(st.session_state[f"{prefix}_ceilingHeight"]),
        "householdSize": int(st.session_state[f"{prefix}_householdSize"]),
        "windowArea": float(st.session_state[f"{prefix}_windowArea"]),

        # numeric values
        "roofRValue": map_lookup(roof_label, R_VALUES_ROOF),
        "wallRValue": map_lookup(wall_label, R_VALUES_WALLS),
        "floorRValue": map_lookup(floor_label, R_VALUES_FLOOR),
        "windowUValue": map_lookup(win_label, U_VALUES_WINDOWS),
        "heatingSystemEfficiency": map_lookup(heat_sys, HEATING_SYSTEMS),
        "waterHeatingEfficiency": map_lookup(hw_sys, WATER_HEATING_SYSTEMS),

        # labels for CAPEX (must not be None once validated)
        "roofRLabel": None if roof_label == PLACEHOLDER else roof_label,
        "wallRLabel": None if wall_label == PLACEHOLDER else wall_label,
        "floorRLabel": None if floor_label == PLACEHOLDER else floor_label,
        "windowULabel": None if win_label == PLACEHOLDER else win_label,
        "heatingSystemLabel": None if heat_sys == PLACEHOLDER else heat_sys,
        "waterHeatingSystemLabel": None if hw_sys == PLACEHOLDER else hw_sys,
        "toiletTypeLabel": None if toilet == PLACEHOLDER else toilet,
        "showerTypeLabel": None if shower == PLACEHOLDER else shower,
        "tapTypeLabel": None if tap == PLACEHOLDER else tap,

        # categorical values for water consumption
        "toiletType": None if toilet == PLACEHOLDER else toilet,
        "showerType": None if shower == PLACEHOLDER else shower,
        "tapType": None if tap == PLACEHOLDER else tap,

        "lighting": {
            "numberOfLights": int(st.session_state[f"{prefix}_light_n"]),
            "wattsPerLight": float(st.session_state[f"{prefix}_light_watts"]),
            "hoursPerDay": float(st.session_state[f"{prefix}_light_hours"]),
        },

        # Laundry + dishwasher retained for WATER ONLY
        "washingMachine": {
            "hasAppliance": wash_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_wash_cycles"]),
            "waterPerCycle": float(st.session_state[f"{prefix}_wash_L"]),
        },
        "dishwasher": {
            "hasAppliance": dish_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_dish_cycles"]),
            "waterPerCycle": float(st.session_state[f"{prefix}_dish_L"]),
        },
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

    # CAPEX labels must exist for validated scenarios
    if s["roofRLabel"] is None: missing.append("Roof insulation label")
    if s["wallRLabel"] is None: missing.append("Wall insulation label")
    if s["floorRLabel"] is None: missing.append("Floor insulation label")
    if s["windowULabel"] is None: missing.append("Window label")
    if s["heatingSystemLabel"] is None: missing.append("Heating system label")
    if s["waterHeatingSystemLabel"] is None: missing.append("Water heating system label")
    if s["toiletTypeLabel"] is None: missing.append("Toilet label")
    if s["showerTypeLabel"] is None: missing.append("Shower label")
    if s["tapTypeLabel"] is None: missing.append("Tap label")

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
        ("b_wash_has", "o_wash_has"),
        ("b_dish_has", "o_dish_has"),

        # numeric
        ("b_floorArea", "o_floorArea"),
        ("b_ceilingHeight", "o_ceilingHeight"),
        ("b_householdSize", "o_householdSize"),
        ("b_windowArea", "o_windowArea"),

        # lighting
        ("b_light_n", "o_light_n"),
        ("b_light_watts", "o_light_watts"),
        ("b_light_hours", "o_light_hours"),

        # laundry + dishwasher (water only)
        ("b_wash_cycles", "o_wash_cycles"),
        ("b_wash_L", "o_wash_L"),
        ("b_dish_cycles", "o_dish_cycles"),
        ("b_dish_L", "o_dish_L"),
    ]
    for src, dst in mappings:
        st.session_state[dst] = copy.deepcopy(st.session_state[src])

    st.session_state["has_calculated"] = False
    st.session_state["last_payload"] = None
    st.session_state["last_signature"] = None

# =============================================================================
# UI HELPERS
# =============================================================================

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)

def direction_arrow(delta: float) -> str:
    if delta < 0: return "▼"
    if delta > 0: return "▲"
    return "—"

def fmt_num(x: float, decimals: int = 1):
    if x is None: return "—"
    return f"{x:,.{decimals}f}"

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

def comparison_mode(b_inputs: dict, o_inputs: dict) -> str:
    same_geo = (
        abs(b_inputs["floorArea"] - o_inputs["floorArea"]) < 1e-9 and
        abs(b_inputs["ceilingHeight"] - o_inputs["ceilingHeight"]) < 1e-9 and
        abs(b_inputs["windowArea"] - o_inputs["windowArea"]) < 1e-9
    )
    same_household = (b_inputs["householdSize"] == o_inputs["householdSize"])
    same_climate = (b_inputs["climateZone"] == o_inputs["climateZone"])

    if same_geo and same_household and same_climate:
        return "Controlled upgrade comparison (same house, same occupants, same climate)"
    return "Sensitivity test (one or more of geometry/occupants/climate differs)"

# =============================================================================
# APP
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.write(
    "Early-stage decision support for comparing housing scenarios. "
    "**Not a certification tool.** Coefficients and costs are placeholders unless replaced."
)

with st.expander("Assumptions & scope (read before interpreting results)", expanded=False):
    st.markdown(
        "- **Energy scope:** space heating + water heating + lighting only (excludes plug loads).\n"
        "- **Water scope:** indoor end uses (toilets, showers, taps, laundry, dishwasher).\n"
        "- **Geometry:** square-footprint approximation for wall area.\n"
        "- **Carbon:** electricity + water only (no embodied carbon).\n"
        "- **Costs:** OPEX only for electricity + water; CAPEX is incremental upgrade cost (placeholder assumptions).\n"
    )
    st.caption(PROVENANCE["energy_scope"])
    st.caption(PROVENANCE["water_units"])
    st.caption(PROVENANCE["geometry"])
    st.caption(PROVENANCE["efs_tariffs"])
    st.caption(PROVENANCE["capex"])

with st.expander("Advanced settings (optional overrides)", expanded=st.session_state["show_advanced"]):
    st.session_state["show_advanced"] = True
    st.number_input("Hot water demand (L/person/day)", min_value=0.0, max_value=300.0, step=1.0, key="adv_hotWaterPerPersonPerDay")
    st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key="adv_hotWaterTemp")
    st.number_input("Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0, step=1.0, key="adv_coldWaterTemp")
    st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key="adv_toiletFlushesPerDay")
    st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key="adv_showersPerDay")
    st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.5, key="adv_showerMinutes")
    st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key="adv_tapMinutesPerDay")

adv = get_advanced_settings()

col_b, col_o, col_r = st.columns([1.05, 1.05, 1.30], gap="large")

# -------------------- Baseline --------------------
with col_b:
    st.subheader("Baseline")

    with st.expander("1) Basic information", expanded=True):
        select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="b_climateZone")
        if st.session_state["b_climateZone"] != PLACEHOLDER:
            st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['b_climateZone']]}** (placeholder)")
        st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="b_floorArea")
        st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="b_ceilingHeight")
        st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="b_householdSize")

    with st.expander("1.1) Thermal envelope", expanded=False):
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

        st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="b_windowArea")

    with st.expander("1.1.4) Space heating system", expanded=False):
        select_with_placeholder("Heating system", list(HEATING_SYSTEMS.keys()), key="b_heatingSystem")
        if st.session_state["b_heatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[st.session_state['b_heatingSystem']]}** (placeholder)")

    with st.expander("1.2) Water heating system", expanded=False):
        select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="b_waterHeatingSystem")
        if st.session_state["b_waterHeatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[st.session_state['b_waterHeatingSystem']]}** (placeholder)")

    with st.expander("1.3) Lighting (energy)", expanded=False):
        st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="b_light_n")
        st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="b_light_watts")
        st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="b_light_hours")

    with st.expander("2) Water fixtures + appliances (water only)", expanded=False):
        st.markdown("**Fixtures**")
        select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="b_toiletType")
        if st.session_state["b_toiletType"] != PLACEHOLDER:
            st.caption(f"{TOILET_TYPES[st.session_state['b_toiletType']]} L/flush (placeholder)")
        select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="b_showerType")
        if st.session_state["b_showerType"] != PLACEHOLDER:
            st.caption(f"{SHOWER_TYPES[st.session_state['b_showerType']]} L/min (placeholder)")
        select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="b_tapType")
        if st.session_state["b_tapType"] != PLACEHOLDER:
            st.caption(f"{TAP_TYPES[st.session_state['b_tapType']]} L/min (placeholder)")

        st.markdown("**Laundry (water only)**")
        select_with_placeholder("Has washing machine?", ["Yes", "No"], key="b_wash_has")
        if st.session_state["b_wash_has"] == "Yes":
            st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="b_wash_cycles")
            st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key="b_wash_L")

        st.markdown("**Dishwasher (water only)**")
        select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="b_dish_has")
        if st.session_state["b_dish_has"] == "Yes":
            st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="b_dish_cycles")
            st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key="b_dish_L")

    st.divider()
    if st.button("Copy Baseline → Option", use_container_width=True):
        copy_baseline_to_option()
        st.rerun()

# -------------------- Option --------------------
with col_o:
    st.subheader("Option")

    with st.expander("1) Basic information", expanded=True):
        select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="o_climateZone")
        if st.session_state["o_climateZone"] != PLACEHOLDER:
            st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['o_climateZone']]}** (placeholder)")
        st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="o_floorArea")
        st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="o_ceilingHeight")
        st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="o_householdSize")

    with st.expander("1.1) Thermal envelope", expanded=False):
        select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key="o_roofRLabel")
        if st.session_state["o_roofRLabel"] != PLACEHOLDER:
            r = R_VALUES_ROOF[st.session_state["o_roofRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key="o_wallRLabel")
        if st.session_state["o_wallRLabel"] != PLACEHOLDER:
            r = R_VALUES_WALLS[st.session_state["o_wallRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key="o_floorRLabel")
        if st.session_state["o_floorRLabel"] != PLACEHOLDER:
            r = R_VALUES_FLOOR[st.session_state["o_floorRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key="o_windowULabel")
        if st.session_state["o_windowULabel"] != PLACEHOLDER:
            u = U_VALUES_WINDOWS[st.session_state["o_windowULabel"]]
            st.caption(f"U={u:.1f} W/m²K")

        st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="o_windowArea")

    with st.expander("1.1.4) Space heating system", expanded=False):
        select_with_placeholder("Heating system", list(HEATING_SYSTEMS.keys()), key="o_heatingSystem")
        if st.session_state["o_heatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[st.session_state['o_heatingSystem']]}** (placeholder)")

    with st.expander("1.2) Water heating system", expanded=False):
        select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="o_waterHeatingSystem")
        if st.session_state["o_waterHeatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[st.session_state['o_waterHeatingSystem']]}** (placeholder)")

    with st.expander("1.3) Lighting (energy)", expanded=False):
        st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="o_light_n")
        st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="o_light_watts")
        st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="o_light_hours")

    with st.expander("2) Water fixtures + appliances (water only)", expanded=False):
        st.markdown("**Fixtures**")
        select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="o_toiletType")
        if st.session_state["o_toiletType"] != PLACEHOLDER:
            st.caption(f"{TOILET_TYPES[st.session_state['o_toiletType']]} L/flush (placeholder)")
        select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="o_showerType")
        if st.session_state["o_showerType"] != PLACEHOLDER:
            st.caption(f"{SHOWER_TYPES[st.session_state['o_showerType']]} L/min (placeholder)")
        select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="o_tapType")
        if st.session_state["o_tapType"] != PLACEHOLDER:
            st.caption(f"{TAP_TYPES[st.session_state['o_tapType']]} L/min (placeholder)")

        st.markdown("**Laundry (water only)**")
        select_with_placeholder("Has washing machine?", ["Yes", "No"], key="o_wash_has")
        if st.session_state["o_wash_has"] == "Yes":
            st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="o_wash_cycles")
            st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key="o_wash_L")

        st.markdown("**Dishwasher (water only)**")
        select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="o_dish_has")
        if st.session_state["o_dish_has"] == "Yes":
            st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="o_dish_cycles")
            st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key="o_dish_L")

# -------------------- Results --------------------
with col_r:
    st.subheader("Results")

    baseline_now = get_scenario("b")
    option_now = get_scenario("o")

    signature_now = _stable_hash({"advanced": adv, "baseline": baseline_now, "option": option_now})

    c1, c2 = st.columns([1, 1])
    with c1:
        do_calc = st.button("Calculate results", type="primary", use_container_width=True)
    with c2:
        show_charts = st.toggle("Show charts", value=True)

    if do_calc:
        missing_b = validate_scenario(baseline_now)
        if missing_b:
            st.error("Baseline is incomplete. Missing: " + ", ".join(missing_b))
            st.session_state["has_calculated"] = False
            st.session_state["last_payload"] = None
            st.session_state["last_signature"] = None
        else:
            base_r = calculate_scenario(baseline_now, adv)

            missing_o = validate_scenario(option_now)
            opt_r = None if missing_o else calculate_scenario(option_now, adv)

            capex = None
            payback_years = None
            if opt_r is not None:
                capex = estimate_capex_incremental(baseline_now, option_now)
                annual_savings = base_r["costs"]["cost_total"] - opt_r["costs"]["cost_total"]
                if annual_savings > 0 and capex["capex_total"] > 0:
                    payback_years = capex["capex_total"] / annual_savings

            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "modelVersion": MODEL_VERSION,
                "assumptionsVersion": ASSUMPTIONS_VERSION,
                "assumptionsNote": ASSUMPTIONS_NOTE,
                "advancedSettings": adv,
                "assumptions": {
                    "gridEmissionFactor_kgCO2e_per_kWh": GRID_EMISSION_FACTOR,
                    "gridEmissionFactorYear": GRID_EF_YEAR,
                    "waterEmissionFactor_kgCO2e_per_m3": WATER_EMISSION_FACTOR,
                    "waterEmissionFactorYear": WATER_EF_YEAR,
                    "electricityTariff_NZD_per_kWh": ELECTRICITY_TARIFF,
                    "waterTariff_NZD_per_m3": WATER_TARIFF,
                    "capexAssumedCounts": {"toilets": ASSUME_NUM_TOILETS, "showers": ASSUME_NUM_SHOWERS, "taps": ASSUME_NUM_TAPS},
                },
                "baseline": {"inputs": baseline_now, "results": base_r},
                "option": {"inputs": option_now, "results": opt_r, "missing": missing_o},
                "comparisonMode": comparison_mode(baseline_now, option_now),
                "capex": capex,
                "simplePaybackYears": payback_years,
                "notes": {
                    "energyScope": "Space heating + Water heating + Lighting only (excludes appliances/plug loads).",
                    "waterScope": "Indoor end uses incl. toilets/showers/taps/laundry/dishwasher.",
                    "geometry": PROVENANCE["geometry"],
                    "coefficients": "Placeholders unless replaced.",
                    "tool_scope": "Early-stage decision support; not certification; not predictive simulation.",
                },
            }

            st.session_state["has_calculated"] = True
            st.session_state["last_payload"] = payload
            st.session_state["last_signature"] = signature_now

    if not st.session_state["has_calculated"] or st.session_state["last_payload"] is None:
        st.info("Press **Calculate results** to generate outputs. Results do not update live.")
        st.stop()

    if st.session_state["last_signature"] != signature_now:
        st.warning("Inputs have changed since the last calculation. Press **Calculate results** to refresh outputs.")

    payload = st.session_state["last_payload"]
    base_r = payload["baseline"]["results"]
    opt_r = payload["option"]["results"]
    opt_missing = payload["option"]["missing"]
    capex = payload.get("capex")
    payback_years = payload.get("simplePaybackYears")

    st.caption(f"Comparison mode: **{payload.get('comparisonMode')}**")

    # Geometry basis note for CAPEX if geometry differs
    if opt_r is not None:
        if comparison_mode(baseline_now, option_now).startswith("Sensitivity test"):
            st.warning("Note: CAPEX is calculated using **baseline geometry** for comparability, even if option geometry differs.")

    st.download_button(
        "Download results (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"housing-sustainability-comparison-{int(datetime.utcnow().timestamp())}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()

    def kpi_rows():
        rows = [
            ("Total Electricity (core)", base_r["totalElectricity_kwh"], None if opt_r is None else opt_r["totalElectricity_kwh"], "kWh/year", 1),
            ("Energy Intensity (core)", base_r["energyIntensity"], None if opt_r is None else opt_r["energyIntensity"], "kWh/m²/year", 2),
            ("Water (total)", base_r["waterConsumption"]["V_total_m3"], None if opt_r is None else opt_r["waterConsumption"]["V_total_m3"], "m³/year", 2),
            ("Water Intensity", base_r["water_L_per_person_day"], None if opt_r is None else opt_r["water_L_per_person_day"], "L/person/day", 1),
            ("Operational Carbon", base_r["carbon"]["CO2_total"], None if opt_r is None else opt_r["carbon"]["CO2_total"], "kgCO₂e/year", 1),
            ("Annual Operating Cost", base_r["costs"]["cost_total"], None if opt_r is None else opt_r["costs"]["cost_total"], "NZD/year", 0),
        ]

        # CAPEX + payback only if option is complete
        if opt_r is not None and capex is not None:
            rows.append(("Incremental CAPEX (Option vs Baseline)", capex["capex_total"], capex["capex_total"], "NZD", 0))
            rows.append(("Simple Payback", None, payback_years, "years", 1))

        out = []
        for name, b, o, unit, dec in rows:
            if o is None:
                out.append({"Metric": name, "Baseline": fmt_num(b, dec), "Option": "—", "Δ (Option−Base)": "—", "Dir": "—", "Unit": unit})
            else:
                if b is None:
                    # For payback we only show option value
                    out.append({"Metric": name, "Baseline": "—", "Option": fmt_num(o, dec), "Δ (Option−Base)": "—", "Dir": "—", "Unit": unit})
                else:
                    d = o - b
                    out.append({"Metric": name, "Baseline": fmt_num(b, dec), "Option": fmt_num(o, dec), "Δ (Option−Base)": fmt_num(d, dec), "Dir": direction_arrow(d), "Unit": unit})
        return out

    st.markdown("**Key Performance Indicators**")
    st.dataframe(pd.DataFrame(kpi_rows()), use_container_width=True, hide_index=True)

    if opt_r is None:
        st.info("Option is incomplete. Complete Option inputs (or use **Copy Baseline → Option**) and recalculate to see comparison and charts.")
        st.stop()

    if show_charts:
        st.divider()
        tabs = st.tabs(["KPIs", "Energy", "Water", "Carbon", "Cost", "CAPEX"])

        with tabs[0]:
            df_kpi = pd.DataFrame([
                {"Metric": "Total Electricity (kWh/y)", "Baseline": base_r["totalElectricity_kwh"], "Option": opt_r["totalElectricity_kwh"]},
                {"Metric": "Energy Intensity (kWh/m²/y)", "Baseline": base_r["energyIntensity"], "Option": opt_r["energyIntensity"]},
                {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total_m3"], "Option": opt_r["waterConsumption"]["V_total_m3"]},
                {"Metric": "Water (L/person/day)", "Baseline": base_r["water_L_per_person_day"], "Option": opt_r["water_L_per_person_day"]},
                {"Metric": "Operational Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total"], "Option": opt_r["carbon"]["CO2_total"]},
                {"Metric": "OPEX (NZD/y)", "Baseline": base_r["costs"]["cost_total"], "Option": opt_r["costs"]["cost_total"]},
            ])
            kpi_grouped_barh(df_kpi, "KPIs: Baseline vs Option")

        with tabs[1]:
            df_energy = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased"]},
                {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased"]},
                {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_lighting"]},
                {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased"]},
                {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased"]},
                {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_lighting"]},
            ])
            stacked_bar_chart(df_energy, "Electricity breakdown (stacked)", "kWh/year")

        with tabs[2]:
            b = base_r["waterConsumption"]["breakdown_m3"]
            o = opt_r["waterConsumption"]["breakdown_m3"]
            df_water = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Toilets", "Value": b["V_toilet"]},
                {"Scenario": "Baseline", "Component": "Showers", "Value": b["V_shower"]},
                {"Scenario": "Baseline", "Component": "Taps", "Value": b["V_taps"]},
                {"Scenario": "Baseline", "Component": "Laundry", "Value": b["V_laundry"]},
                {"Scenario": "Baseline", "Component": "Dishwasher", "Value": b["V_dishwasher"]},
                {"Scenario": "Option", "Component": "Toilets", "Value": o["V_toilet"]},
                {"Scenario": "Option", "Component": "Showers", "Value": o["V_shower"]},
                {"Scenario": "Option", "Component": "Taps", "Value": o["V_taps"]},
                {"Scenario": "Option", "Component": "Laundry", "Value": o["V_laundry"]},
                {"Scenario": "Option", "Component": "Dishwasher", "Value": o["V_dishwasher"]},
            ])
            stacked_bar_chart(df_water, "Water breakdown (stacked)", "m³/year")

        with tabs[3]:
            df_carbon = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water"]},
            ])
            stacked_bar_chart(df_carbon, "Operational carbon breakdown (stacked)", "kgCO₂e/year")

        with tabs[4]:
            df_cost = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["costs"]["cost_electricity"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["costs"]["cost_water"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["costs"]["cost_electricity"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["costs"]["cost_water"]},
            ])
            stacked_bar_chart(df_cost, "Operating cost breakdown (stacked)", "NZD/year")

        with tabs[5]:
            if capex is None:
                st.info("CAPEX not available.")
            else:
                df_capex = pd.DataFrame([
                    {"Scenario": "Option vs Baseline", "Component": k, "Value": v}
                    for k, v in capex["capex_breakdown"].items()
                ])
                stacked_bar_chart(df_capex, "Incremental CAPEX breakdown (stacked)", "NZD")
                if payback_years is None:
                    st.caption("Simple payback: — (no savings or no CAPEX).")
                else:
                    st.caption(f"Simple payback (non-discounted): **{payback_years:.1f} years**")

st.caption(
    "Notes: Results are simplified and indicative. This prototype uses placeholder coefficients unless you replace them. "
    "No embodied carbon, no detailed simulation, no behavioural modelling, no time-of-use pricing."
)
