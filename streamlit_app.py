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
# DATA / COEFFICIENTS
# =============================================================================
# NOTE:
# - Anything marked PLACEHOLDER should be replaced with defensible NZ-specific sources.
# - Some defaults are informed by Homestar v5.1.0 Technical Manual (NZGBC, published 24 Mar 2025).
#   This prototype does NOT replicate Homestar/ECCHO. It only borrows *directional* structures.

# --- Climate (HDD) ---
# PLACEHOLDER: Replace with defensible HDD dataset / NZ climate-zone mapping.
HDD_LOOKUP_BASE18 = {
    "Zone 1 (Warmest - e.g., Northland)": 1200,
    "Zone 2 (Warm - e.g., Auckland)": 1600,
    "Zone 3 (Mild - e.g., Wellington)": 2000,
    "Zone 4 (Cool - e.g., Christchurch)": 2400,
    "Zone 5 (Cold - e.g., Queenstown)": 2800,
    "Zone 6 (Coldest - e.g., Central Otago)": 3200,
}

# --- Envelope ---
# PLACEHOLDER: Replace with NZ building code / BRANZ guidance + consistent mapping to typical assemblies.
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

# --- Systems (COP/Efficiency) ---
# Homestar v5.1 manual includes conservative default COP examples for space heating and hot water.
# We align placeholders to those values where feasible, but this tool is not ECCHO.
# Source (Homestar v5.1.0 Technical Manual): default COP table includes:
# - Electric panel heater 1.0
# - High wall (split) heat pump 2.5
# - Electric (immersion) cylinder 1.0
# - Electric heat pump hot water 2.0
# (NZGBC Homestar v5.1.0 manual excerpts):contentReference[oaicite:3]{index=3}
HEATING_SYSTEMS = {
    "None": 0.0,
    "Electric resistance (COP 1.0)": 1.0,
    "Heat pump (COP 2.5)": 2.5,
}
WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder (COP 1.0)": 1.0,
    "Heat pump hot water (COP 2.0)": 2.0,
}

# --- Water fixtures ---
# PLACEHOLDER: Replace with WELS-aligned ranges and/or NZ typical product data.
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

# --- Appliance water (kept IN water model) ---
# PLACEHOLDER: Replace with WELS defaults, typical L/cycle, typical household usage distributions.
WASHING_MACHINE_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 60}
DISHWASHER_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 12}

# --- Lighting (kept in Energy; not treated as "plug load") ---
# PLACEHOLDER: Replace with bedroom-based lighting assumptions if desired.
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}

# --- Carbon and tariffs (PLACEHOLDER) ---
GRID_EMISSION_FACTOR = 0.10   # kgCO2e/kWh (PLACEHOLDER)
ELECTRICITY_TARIFF = 0.30     # NZD/kWh (PLACEHOLDER)
WATER_TARIFF = 2.50           # NZD/m³ (PLACEHOLDER)
WATER_EMISSION_FACTOR = 0.63  # kgCO2e/m³ (PLACEHOLDER)

# =============================================================================
# CAPEX (MINIMAL, PLACEHOLDER ASSUMPTIONS)
# =============================================================================
# Philosophy: keep minimal, transparent, and non-invasive.
# We compute incremental capex as (option assumed cost - baseline assumed cost) per element.
# PLACEHOLDER: Replace with QS ranges or published cost guides.

CAPEX_ENVELOPE_NZD_PER_M2 = {
    # incremental install cost per m² of element area (NOT total build cost)
    "Uninsulated": 0.0,
    "Basic": 15.0,
    "Code minimum": 25.0,
    "Good": 40.0,
    "Excellent": 60.0,
}
CAPEX_WINDOW_NZD_PER_M2_WINDOW = {
    "Single glazed": 0.0,
    "Standard double glazed": 250.0,
    "Low-E double glazed": 400.0,
    "High performance triple": 700.0,
}
CAPEX_HEATING_LUMP_NZD = {
    "None": 0.0,
    "Electric resistance (COP 1.0)": 800.0,
    "Heat pump (COP 2.5)": 3500.0,
}
CAPEX_WATER_HEATING_LUMP_NZD = {
    "Electric storage cylinder (COP 1.0)": 0.0,
    "Heat pump hot water (COP 2.0)": 5500.0,
}
CAPEX_FIXTURES_LUMP_NZD = {
    # simple per-dwelling increments; avoids needing counts
    "Toilet upgrade": 600.0,
    "Shower upgrade": 250.0,
    "Tap upgrade": 200.0,
}

# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================
def calculate_space_heating(inputs: dict) -> dict:
    """
    Steady-state, envelope-only heat loss approach using HDD (base 18°C).
    Purpose: early-stage *comparative* differences only.
    Excludes: infiltration/ventilation losses, internal/solar gains, zoning, behavioural effects.
    """
    HDD = HDD_LOOKUP_BASE18[inputs["climateZone"]]

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
        "breakdown_W_per_K": {
            "H_roof": H_roof,
            "H_wall": H_wall,
            "H_floor": H_floor,
            "H_window": H_window,
        },
    }

def calculate_water_heating(inputs: dict, advanced: dict) -> dict:
    """
    Simplified water heating: annual hot water volume * deltaT * Cp.
    Note: ECCHO has richer hot-water assumptions (e.g., shower frequency/duration),
    but this prototype uses a single user-friendly L/person/day input.
    """
    n = inputs["householdSize"]
    L_per_person_day = advanced["hotWater_L_per_person_day"]
    T_hot = advanced["hotWater_setpoint_C"]
    T_cold = advanced["coldWater_inlet_C"]

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
    }

def calculate_lighting(inputs: dict) -> dict:
    """
    Lighting-only electricity (no plug loads / appliances / cooking).
    """
    lighting = inputs["lighting"]
    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_total_kwh_y": Q_lighting}

def calculate_water_consumption(inputs: dict, advanced: dict) -> dict:
    """
    Indoor water only. Reports m³/year.
    Includes appliance water (dishwasher, washing machine) but NOT their energy.
    """
    n = inputs["householdSize"]

    toiletL = TOILET_TYPES[inputs["toiletType"]]
    showerLmin = SHOWER_TYPES[inputs["showerType"]]
    tapLmin = TAP_TYPES[inputs["tapType"]]

    flushes = advanced["toiletFlushes_per_person_day"]
    showers = advanced["showers_per_person_day"]
    showerMinutes = advanced["minutes_per_shower"]
    tapMinutes = advanced["tapMinutes_per_person_day"]

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
    }

def calculate_operational_carbon(total_kwh_y: float, total_m3_y: float) -> dict:
    CO2_e = total_kwh_y * GRID_EMISSION_FACTOR
    CO2_w = total_m3_y * WATER_EMISSION_FACTOR
    return {"CO2_total_kg_y": CO2_e + CO2_w, "CO2_electricity_kg_y": CO2_e, "CO2_water_kg_y": CO2_w}

def calculate_opex(total_kwh_y: float, total_m3_y: float) -> dict:
    c_e = total_kwh_y * ELECTRICITY_TARIFF
    c_w = total_m3_y * WATER_TARIFF
    return {"opex_total_nzd_y": c_e + c_w, "opex_electricity_nzd_y": c_e, "opex_water_nzd_y": c_w}

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

def calculate_incremental_capex(base_inputs: dict, opt_inputs: dict) -> dict:
    """
    Minimal incremental capex with placeholder assumptions.
    Returns a breakdown and total capex delta: option - baseline.
    """
    # areas (simplified to match heating geometry)
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

    # use option geometry for costing (same-house comparisons can still vary in your tool;
    # we use each scenario's own geometry to avoid "locked" constraints)
    # If you want geometry "locked", simply cost using baseline areas.
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

    # fixtures: only charge if option is "more efficient" than baseline in our simple ordering
    # (kept minimal; replace with a better rule later)
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

def calculate_scenario(inputs: dict, advanced: dict) -> dict:
    space = calculate_space_heating(inputs)
    water_heat = calculate_water_heating(inputs, advanced)
    lighting = calculate_lighting(inputs)
    water_use = calculate_water_consumption(inputs, advanced)

    # Total electricity: EXCLUDES appliances/plug loads (Homestar EF4 excludes appliances)
    # Homestar EF4 includes heating, hot water, ventilation, lighting, refrigerants.:contentReference[oaicite:4]{index=4}
    total_electricity_kwh_y = space["Q_purchased_kwh_y"] + water_heat["Q_purchased_kwh_y"] + lighting["Q_total_kwh_y"]

    carbon = calculate_operational_carbon(total_electricity_kwh_y, water_use["V_total_m3_y"])
    opex = calculate_opex(total_electricity_kwh_y, water_use["V_total_m3_y"])
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
    # Advanced (editable later; for now they remain visible and transparent)
    # Note: Homestar water calculator has its own default usage assumptions (L/person/day):contentReference[oaicite:5]{index=5}
    # ECCHO also uses shower frequency/duration defaults (0.9/day, 6 min):contentReference[oaicite:6]{index=6}
    st.session_state.setdefault("adv_hotWater_L_per_person_day", 50.0)  # PLACEHOLDER (simplified)
    st.session_state.setdefault("adv_hotWater_setpoint_C", 60.0)        # PLACEHOLDER
    st.session_state.setdefault("adv_coldWater_inlet_C", 15.0)          # PLACEHOLDER

    st.session_state.setdefault("adv_toiletFlushes_per_person_day", 5.0)     # aligns with 4 half + 1 full logic in Homestar defaults
    st.session_state.setdefault("adv_showers_per_person_day", 1.0)           # water calculator uses 1 shower/day; ECCHO ~0.9/day
    st.session_state.setdefault("adv_minutes_per_shower", 6.21)              # Homestar water calculator default minutes:contentReference[oaicite:7]{index=7}
    st.session_state.setdefault("adv_tapMinutes_per_person_day", 10.0)       # PLACEHOLDER

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

def get_advanced_settings() -> dict:
    return {
        "hotWater_L_per_person_day": float(st.session_state["adv_hotWater_L_per_person_day"]),
        "hotWater_setpoint_C": float(st.session_state["adv_hotWater_setpoint_C"]),
        "coldWater_inlet_C": float(st.session_state["adv_coldWater_inlet_C"]),
        "toiletFlushes_per_person_day": float(st.session_state["adv_toiletFlushes_per_person_day"]),
        "showers_per_person_day": float(st.session_state["adv_showers_per_person_day"]),
        "minutes_per_shower": float(st.session_state["adv_minutes_per_shower"]),
        "tapMinutes_per_person_day": float(st.session_state["adv_tapMinutes_per_person_day"]),
    }

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

        "roofRValue": map_lookup(roof_label, R_VALUES_ROOF),
        "wallRValue": map_lookup(wall_label, R_VALUES_WALLS),
        "floorRValue": map_lookup(floor_label, R_VALUES_FLOOR),
        "windowUValue": map_lookup(win_label, U_VALUES_WINDOWS),

        "heatingSystemEfficiency": map_lookup(heat_sys, HEATING_SYSTEMS),
        "waterHeatingEfficiency": map_lookup(hw_sys, WATER_HEATING_SYSTEMS),

        "toiletType": None if toilet == PLACEHOLDER else toilet,
        "showerType": None if shower == PLACEHOLDER else shower,
        "tapType": None if tap == PLACEHOLDER else tap,

        # energy: lighting only
        "lighting": {
            "numberOfLights": int(st.session_state[f"{prefix}_light_n"]),
            "wattsPerLight": float(st.session_state[f"{prefix}_light_watts"]),
            "hoursPerDay": float(st.session_state[f"{prefix}_light_hours"]),
        },

        # water: include appliance water
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

# -----------------------------------------------------------------------------
# TAB 1: Scenario (Inputs + Results)
# -----------------------------------------------------------------------------
with tabs[0]:
    adv = get_advanced_settings()

    with st.expander("Advanced settings (transparent defaults; can be replaced later)", expanded=False):
        st.number_input("Hot water demand (L/person/day) [PLACEHOLDER]", min_value=0.0, max_value=300.0, step=1.0, key="adv_hotWater_L_per_person_day")
        st.number_input("Hot water setpoint (°C) [PLACEHOLDER]", min_value=30.0, max_value=80.0, step=1.0, key="adv_hotWater_setpoint_C")
        st.number_input("Cold water inlet temperature (°C) [PLACEHOLDER]", min_value=0.0, max_value=30.0, step=1.0, key="adv_coldWater_inlet_C")

        st.number_input("Toilet flushes/person/day (count)", min_value=0.0, max_value=20.0, step=0.5, key="adv_toiletFlushes_per_person_day")
        st.number_input("Showers/person/day (count)", min_value=0.0, max_value=5.0, step=0.1, key="adv_showers_per_person_day")
        st.number_input("Minutes/shower (min)", min_value=0.0, max_value=60.0, step=0.1, key="adv_minutes_per_shower")
        st.number_input("Tap minutes/person/day (min) [PLACEHOLDER]", min_value=0.0, max_value=120.0, step=0.5, key="adv_tapMinutes_per_person_day")

    col_b, col_o = st.columns([1.05, 1.05], gap="large")

    # -------------------- Baseline --------------------
    with col_b:
        st.subheader("Baseline")

        with st.expander("A) Core inputs", expanded=True):
            select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="b_climateZone")
            if st.session_state["b_climateZone"] != PLACEHOLDER:
                st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['b_climateZone']]}** (PLACEHOLDER)")

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
            st.caption("Energy excludes appliances/plug loads (aligned to Homestar EF4 framing).")

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

    # -------------------- Option --------------------
    with col_o:
        st.subheader("Option")

        with st.expander("A) Core inputs", expanded=True):
            select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="o_climateZone")
            if st.session_state["o_climateZone"] != PLACEHOLDER:
                st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['o_climateZone']]}** (PLACEHOLDER)")

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

    # -------------------- Results (below inputs, collapsible) --------------------
    st.divider()

    baseline_now = get_scenario("b")
    option_now = get_scenario("o")

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

    # Always compute baseline results (fast, deterministic).
    base_r = calculate_scenario(baseline_now, adv)

    # Compute option results if complete.
    opt_r = None if missing_o else calculate_scenario(option_now, adv)

    # Capex only if option complete
    capex = None
    if opt_r is not None:
        capex = calculate_incremental_capex(baseline_now, option_now)

    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "advancedSettings": adv,
        "baseline": {"inputs": baseline_now, "results": base_r, "missing": []},
        "option": {"inputs": option_now, "results": opt_r, "missing": missing_o},
        "capex": capex,
        "notes": {
            "scope": "Early-stage decision support; not certification; not predictive modelling.",
            "energy_boundary": "Energy excludes appliances/plug loads; includes space heating + water heating + lighting.",
            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
            "coefficients": "Many coefficients are placeholders unless replaced with sourced NZ values.",
        },
    }

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

    # Download JSON at bottom
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

# -----------------------------------------------------------------------------
# TAB 2: Assumptions (Provenance Table)
# -----------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Assumptions and Provenance (Transparent Defaults)")
    st.write("This tab documents what the prototype assumes, and whether each assumption is sourced or still a placeholder.")

    rows = [
        {
            "Assumption": "Energy boundary excludes appliances/plug loads",
            "Current value": "Space heating + water heating + lighting only",
            "Source / provenance": "Homestar EF4 frames operational energy as excluding appliances (heating, hot water, ventilation, lighting, refrigerants).",
            "Status": "SOURCED (Homestar)",
        },
        {
            "Assumption": "Dishwasher + washing machine included in water model",
            "Current value": "Included as water end-uses (m³/year)",
            "Source / provenance": "Homestar Water Calculator estimates indoor water using fixtures + appliances.",
            "Status": "SOURCED (Homestar)",
        },
        {
            "Assumption": "Default shower duration (minutes)",
            "Current value": st.session_state["adv_minutes_per_shower"],
            "Source / provenance": "Homestar Water Calculator default shower duration is 6.21 minutes.",
            "Status": "SOURCED (Homestar)",
        },
        {
            "Assumption": "Space heating COP default for heat pump",
            "Current value": "2.5",
            "Source / provenance": "Homestar manual provides a conservative default COP 2.5 for split/ducted heat pumps.",
            "Status": "SOURCED (Homestar)",
        },
        {
            "Assumption": "Hot water heat pump COP default",
            "Current value": "2.0",
            "Source / provenance": "Homestar manual provides default COP 2.0 for heat pump hot water systems.",
            "Status": "SOURCED (Homestar)",
        },
        {
            "Assumption": "HDD lookup values (base 18°C)",
            "Current value": "Zone 1–6 HDD values",
            "Source / provenance": "Placeholder mapping; replace with authoritative NZ HDD dataset and climate zone mapping.",
            "Status": "PLACEHOLDER",
        },
        {
            "Assumption": "Grid emission factor",
            "Current value": GRID_EMISSION_FACTOR,
            "Source / provenance": "Placeholder; replace with NZ electricity emissions factor (define year + scope).",
            "Status": "PLACEHOLDER",
        },
        {
            "Assumption": "Water supply emission factor",
            "Current value": WATER_EMISSION_FACTOR,
            "Source / provenance": "Placeholder; replace with NZ water supply/utility factor (region-specific if possible).",
            "Status": "PLACEHOLDER",
        },
        {
            "Assumption": "Electricity and water tariffs",
            "Current value": f"{ELECTRICITY_TARIFF} NZD/kWh; {WATER_TARIFF} NZD/m³",
            "Source / provenance": "Placeholder; replace with representative tariffs (or region-selectable).",
            "Status": "PLACEHOLDER",
        },
        {
            "Assumption": "Capex cost curves",
            "Current value": "Per-m² envelope + window per-m² + lump sums (placeholder)",
            "Source / provenance": "Placeholder; replace with QS / cost guide ranges and document basis.",
            "Status": "PLACEHOLDER",
        },
    ]

    df = pd.DataFrame(rows)
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.caption(
        "Homestar citations for EF4 and Water Calculator defaults are used for provenance only. "
        "This prototype does not attempt to replicate Homestar/ECCHO scoring."
    )

# -----------------------------------------------------------------------------
# TAB 3: Calculations (Formulas + “where from”)
# -----------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Calculations (How the Prototype Computes Outputs)")
    st.markdown(
        """
**Important:** These equations are simplified and intentionally transparent. They are not ECCHO.

### 1) Space Heating (steady-state heat loss + HDD)
- Compute heat loss coefficient:
  - \(H = A_{roof}U_{roof} + A_{wall}U_{wall} + A_{floor}U_{floor} + A_{win}U_{win}\)
- Annual delivered heat (kWh/y):
  - \(Q_{del} = (H \\times HDD \\times 24) / 1000\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

**Provenance:** The overall structure is common in early-stage steady-state methods.  
**Note:** ECCHO uses more detailed envelope, bridging, and adjacency handling.

### 2) Water Heating (volume + temperature rise)
- Annual hot water volume:
  - \(V_y = n \\times L_{ppd} \\times 365\)
- Delivered thermal energy:
  - \(Q_{del} = (V_y \\times \\Delta T \\times C_p) / 3600\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

**Provenance:** Simplified physics-based method. ECCHO has richer default hot-water assumptions for showers etc.

### 3) Lighting Electricity
- \(Q_{light} = (N_{lights} \\times W_{light} \\times h_{day} \\times 365)/1000\)

**Boundary:** Appliances/plug loads excluded (aligned to Homestar EF4 framing).

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
- Convert to m³/y by dividing litres by 1000.

**Provenance:** Homestar Water Calculator conceptually uses fixtures + appliances to estimate indoor L/person/day.

### 5) Operational Carbon (placeholder factors)
- Electricity:
  - \(CO2_e = kWh \\times EF_{grid}\)
- Water:
  - \(CO2_w = m^3 \\times EF_{water}\)
- Total:
  - \(CO2 = CO2_e + CO2_w\)

### 6) Opex (placeholder tariffs)
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

# -----------------------------------------------------------------------------
# TAB 4: Indicators (Definitions + Boundaries)
# -----------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Indicators (Definitions and Scope)")
    st.markdown(
        """
### Energy (kWh/year)
**What it includes:** Space heating electricity + water heating electricity + lighting.  
**What it excludes:** Appliances/plug loads (e.g., dishwasher energy, washing machine energy, cooking).  
**Rationale:** Homestar EF4 frames operational energy as excluding appliances.

### Water (m³/year)
**What it includes:** Indoor water end uses (toilets, showers, taps) + appliance water (dishwasher, washing machine).  
**What it excludes:** Outdoor irrigation, leakage, seasonal variation, rainwater harvesting offsets (not implemented yet).

### Operational Carbon (kgCO₂e/year)
**What it includes:** Emissions associated with electricity and supplied water only (average factors).  
**What it excludes:** Embodied carbon, marginal emissions, time-of-use effects.

### Operating Cost / Opex (NZD/year)
**What it includes:** Electricity cost + water cost (average tariffs).  
**What it excludes:** Fixed charges, time-of-use pricing, demand charges, maintenance.

### Incremental Capex (NZD)
**What it represents:** A minimal, transparent estimate of upgrade cost differences (Option − Baseline).  
**Limitations:** Not a QS estimate; uses placeholder unit costs; does not include financing, replacement cycles, discount rates.
        """
    )
