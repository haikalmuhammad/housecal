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
# ASSUMPTIONS REGISTRY (Single Source of Truth)
# - Use this to render Tab 2 (auditable provenance)
# - Defaults may be overridden via UI at approved locations
# =============================================================================
ASSUMPTIONS = {
    # --- Climate / Heating ---
    "HDD_LOOKUP_BASE18": {
        "value": "Zone lookup (placeholder dataset)",
        "unit": "HDD (base 18°C)",
        "where_used": "calculate_space_heating()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with authoritative NZ HDD dataset + method definition (base 18°C).",
        "rationale": "Heating degree days provide a transparent early-stage proxy for space-heating demand by climate.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Core inputs → HDD source",
        "validation_rule": "If custom, 0–6000 HDD (base 18°C).",
        "min": 0.0, "max": 6000.0, "step": 50.0,
    },

    # --- Water / Usage defaults ---
    "HOT_WATER_L_PER_PERSON_DAY": {
        "value": 50.0,
        "unit": "L/person/day",
        "where_used": "calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with Homestar/BRANZ/MBIE defensible default and reference page.",
        "rationale": "A single L/person/day input keeps the model transparent and supports early-stage comparison.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–300 L/person/day",
        "min": 0.0, "max": 300.0, "step": 1.0,
    },
    "HOT_WATER_SETPOINT_C": {
        "value": 60.0,
        "unit": "°C",
        "where_used": "calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with NZ practice guidance (setpoint range) + citation.",
        "rationale": "Setpoint and inlet temperature define the temperature rise required for hot water heating.",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "30–80 °C",
        "min": 30.0, "max": 80.0, "step": 1.0,
    },
    "COLD_WATER_INLET_C": {
        "value": 15.0,
        "unit": "°C",
        "where_used": "calculate_water_heating()",
        "source_type": "Placeholder",
        "citation": "Placeholder — region/season varies; replace with defensible assumed inlet temp approach.",
        "rationale": "Inlet temperature materially affects hot water energy; simplified as a transparent constant per scenario.",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–30 °C",
        "min": 0.0, "max": 30.0, "step": 1.0,
    },
    "TOILET_FLUSHES_PER_PERSON_DAY": {
        "value": 5.0,
        "unit": "flushes/person/day",
        "where_used": "calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with Homestar/BRANZ usage default + reference.",
        "rationale": "Daily flush frequency is a major driver of indoor water consumption.",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–20 flushes/person/day",
        "min": 0.0, "max": 20.0, "step": 0.5,
    },
    "SHOWERS_PER_PERSON_DAY": {
        "value": 1.0,
        "unit": "showers/person/day",
        "where_used": "calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with Homestar/ECCHO/BRANZ default + reference.",
        "rationale": "Shower frequency is a primary driver of both water use and (indirectly) hot water energy.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–5 showers/person/day",
        "min": 0.0, "max": 5.0, "step": 0.1,
    },
    "MINUTES_PER_SHOWER": {
        "value": 6.21,
        "unit": "minutes/shower",
        "where_used": "calculate_water_consumption()",
        "source_type": "Homestar",
        "citation": "Homestar Water Calculator default shower duration — add doc name + page reference (to be filled).",
        "rationale": "A transparent default supports comparability and reduces user burden for early-stage scenarios.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–60 minutes/shower",
        "min": 0.0, "max": 60.0, "step": 0.1,
    },
    "TAP_MINUTES_PER_PERSON_DAY": {
        "value": 10.0,
        "unit": "minutes/person/day",
        "where_used": "calculate_water_consumption()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with defensible NZ indoor water end-use assumption + reference.",
        "rationale": "Tap runtime provides a simple, auditable proxy for handwashing, cooking, and cleaning use.",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Scenario → Usage assumptions",
        "validation_rule": "0–120 minutes/person/day",
        "min": 0.0, "max": 120.0, "step": 0.5,
    },

    # --- Carbon & tariffs (configured just before KPIs) ---
    "GRID_EMISSION_FACTOR": {
        "value": 0.10,
        "unit": "kgCO2e/kWh",
        "where_used": "calculate_operational_carbon()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with NZ electricity emissions factor (define year + scope) + citation.",
        "rationale": "Operational carbon is reported using average factors for transparency and consistency.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Results → Tariffs & factors",
        "validation_rule": "0–1 kgCO2e/kWh",
        "min": 0.0, "max": 1.0, "step": 0.01,
    },
    "WATER_EMISSION_FACTOR": {
        "value": 0.63,
        "unit": "kgCO2e/m³",
        "where_used": "calculate_operational_carbon()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with NZ utility / MBIE / peer-reviewed factor + reference.",
        "rationale": "Supplied water has embodied operational emissions (treatment + pumping) approximated by an average factor.",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Results → Tariffs & factors",
        "validation_rule": "0–5 kgCO2e/m³",
        "min": 0.0, "max": 5.0, "step": 0.01,
    },
    "ELECTRICITY_TARIFF": {
        "value": 0.30,
        "unit": "NZD/kWh",
        "where_used": "calculate_opex()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with representative tariff assumptions (or region-selectable) + reference.",
        "rationale": "Opex uses transparent unit rates to allow early-stage cost comparison between scenarios.",
        "sensitivity": "High",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Results → Tariffs & factors",
        "validation_rule": "0–2 NZD/kWh",
        "min": 0.0, "max": 2.0, "step": 0.01,
    },
    "WATER_TARIFF": {
        "value": 2.50,
        "unit": "NZD/m³",
        "where_used": "calculate_opex()",
        "source_type": "Placeholder",
        "citation": "Placeholder — replace with representative water tariff basis + reference.",
        "rationale": "Opex includes supplied water unit cost for transparent comparison (excludes fixed charges).",
        "sensitivity": "Medium",
        "override_allowed": "Yes",
        "override_location": "Tab 1 → Results → Tariffs & factors",
        "validation_rule": "0–20 NZD/m³",
        "min": 0.0, "max": 20.0, "step": 0.1,
    },
}

# =============================================================================
# LOOKUP TABLES (performance + placeholder capex)
# =============================================================================
# Climate zones -> HDD (PLACEHOLDER)
HDD_LOOKUP_BASE18 = {
    "Zone 1 (Warmest - e.g., Northland)": 1200,
    "Zone 2 (Warm - e.g., Auckland)": 1600,
    "Zone 3 (Mild - e.g., Wellington)": 2000,
    "Zone 4 (Cool - e.g., Christchurch)": 2400,
    "Zone 5 (Cold - e.g., Queenstown)": 2800,
    "Zone 6 (Coldest - e.g., Central Otago)": 3200,
}

# Envelope (R-values / U-values)
R_VALUES_ROOF = {
    "Uninsulated": 0.5,
    "Basic (R2.0)": 2.0,
    "Code minimum (R3.3)": 3.3,
    "Good (R4.6)": 4.6,
    "Excellent (R6.0)": 6.0,
    "Custom": None,
}
R_VALUES_WALLS = {
    "Uninsulated": 0.5,
    "Basic (R1.5)": 1.5,
    "Code minimum (R2.0)": 2.0,
    "Good (R2.8)": 2.8,
    "Excellent (R4.0)": 4.0,
    "Custom": None,
}
R_VALUES_FLOOR = {
    "Uninsulated": 0.5,
    "Basic (R1.3)": 1.3,
    "Code minimum (R2.0)": 2.0,
    "Good (R3.0)": 3.0,
    "Excellent (R4.0)": 4.0,
    "Custom": None,
}
U_VALUES_WINDOWS = {
    "Single glazed": 5.8,
    "Standard double glazed": 3.0,
    "Low-E double glazed": 2.0,
    "High performance triple": 1.0,
    "Custom": None,
}

# Systems (efficiency/COP)
HEATING_SYSTEMS = {
    "None": 0.0,
    "Electric resistance (COP 1.0)": 1.0,
    "Heat pump (COP 2.5)": 2.5,
    "Custom": None,
}
WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder (COP 1.0)": 1.0,
    "Heat pump hot water (COP 2.0)": 2.0,
    "Custom": None,
}

# Fixtures (flow / litres)
TOILET_TYPES = {
    "Single flush (9L)": 9.0,
    "Dual flush standard (6/3L avg 5L)": 5.0,
    "Dual flush efficient (4.5/3L avg 4L)": 4.0,
    "Custom": None,
}
SHOWER_TYPES = {
    "Standard (9 L/min)": 9.0,
    "Low-flow (7 L/min)": 7.0,
    "Efficient (6 L/min)": 6.0,
    "Custom": None,
}
TAP_TYPES = {
    "Standard (8 L/min)": 8.0,
    "Efficient (6 L/min)": 6.0,
    "Very efficient (4 L/min)": 4.0,
    "Custom": None,
}

# Appliance water defaults (still editable per scenario)
WASHING_MACHINE_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 60}
DISHWASHER_DEFAULTS = {"hasAppliance": True, "cyclesPerWeek": 4, "waterPerCycle_L": 12}

# Lighting defaults (editable per scenario)
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}

# CAPEX placeholder unit costs (now scenario-specific, with Custom paths)
CAPEX_ENVELOPE_NZD_PER_M2 = {
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
    "Toilet upgrade": 600.0,
    "Shower upgrade": 250.0,
    "Tap upgrade": 200.0,
}

# =============================================================================
# UTIL
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

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

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

# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================
def calculate_space_heating(s: dict) -> dict:
    """
    Steady-state, envelope-only heat loss approach using HDD (base 18°C).
    Early-stage comparative method; excludes infiltration/ventilation losses, gains, zoning, behaviour.
    """
    HDD = s["HDD_base18"]

    roofU = 1.0 / s["roofRValue"]
    wallU = 1.0 / s["wallRValue"]
    floorU = 1.0 / s["floorRValue"]

    floorArea = s["floorArea"]
    ceilingHeight = s["ceilingHeight"]
    windowArea = s["windowArea"]

    roofArea = floorArea
    perimeter = 4.0 * math.sqrt(floorArea)  # simplification
    wallArea = max(perimeter * ceilingHeight - windowArea, 0.0)
    floorAreaCalc = floorArea

    H_roof = roofArea * roofU
    H_wall = wallArea * wallU
    H_floor = floorAreaCalc * floorU
    H_window = windowArea * s["windowUValue"]
    H_total = H_roof + H_wall + H_floor + H_window

    Q_delivered = (H_total * HDD * 24.0) / 1000.0  # kWh/year (delivered)
    eff = s["heatingSystemEfficiency"]
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

def calculate_water_heating(s: dict) -> dict:
    """
    Simplified hot water: annual volume * deltaT * Cp.
    """
    n = s["householdSize"]
    usage = s["usage"]

    L_per_person_day = usage["hotWater_L_per_person_day"]
    T_hot = usage["hotWater_setpoint_C"]
    T_cold = usage["coldWater_inlet_C"]

    V_annual_L = n * L_per_person_day * 365.0
    deltaT = T_hot - T_cold

    specificHeat_kJ_per_kgC = 4.186
    Q_delivered_kwh_y = (V_annual_L * deltaT * specificHeat_kJ_per_kgC) / 3600.0

    eff = s["waterHeatingEfficiency"]
    Q_purchased_kwh_y = (Q_delivered_kwh_y / eff) if eff and eff > 0 else Q_delivered_kwh_y

    return {
        "V_annual_L": V_annual_L,
        "Q_delivered_kwh_y": Q_delivered_kwh_y,
        "Q_purchased_kwh_y": Q_purchased_kwh_y,
    }

def calculate_lighting(s: dict) -> dict:
    """
    Lighting-only electricity (no plug loads / appliance energy).
    """
    lighting = s["lighting"]
    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_total_kwh_y": Q_lighting}

def calculate_water_consumption(s: dict) -> dict:
    """
    Indoor water only. Reports m³/year.
    Includes appliance water (dishwasher, washing machine) but NOT their energy.
    """
    n = s["householdSize"]
    usage = s["usage"]

    toiletL = s["toilet_L_per_flush"]
    showerLmin = s["shower_L_per_min"]
    tapLmin = s["tap_L_per_min"]

    flushes = usage["toiletFlushes_per_person_day"]
    showers = usage["showers_per_person_day"]
    showerMinutes = usage["minutes_per_shower"]
    tapMinutes = usage["tapMinutes_per_person_day"]

    V_toilet_L_y = n * flushes * toiletL * 365.0
    V_shower_L_y = n * showers * showerMinutes * showerLmin * 365.0
    V_taps_L_y = n * tapMinutes * tapLmin * 365.0

    washing = s["washingMachine"]
    dish = s["dishwasher"]

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

def calculate_operational_carbon(total_kwh_y: float, total_m3_y: float, coeffs: dict) -> dict:
    CO2_e = total_kwh_y * coeffs["grid_ef"]
    CO2_w = total_m3_y * coeffs["water_ef"]
    return {"CO2_total_kg_y": CO2_e + CO2_w, "CO2_electricity_kg_y": CO2_e, "CO2_water_kg_y": CO2_w}

def calculate_opex(total_kwh_y: float, total_m3_y: float, coeffs: dict) -> dict:
    c_e = total_kwh_y * coeffs["elec_tariff"]
    c_w = total_m3_y * coeffs["water_tariff"]
    return {"opex_total_nzd_y": c_e + c_w, "opex_electricity_nzd_y": c_e, "opex_water_nzd_y": c_w}

def calculate_incremental_capex(base_s: dict, opt_s: dict) -> dict:
    """
    Transparent incremental capex using scenario-specific unit costs:
    Option cost − Baseline cost (by element).
    """
    def areas(s: dict):
        floorArea = s["floorArea"]
        ceilingHeight = s["ceilingHeight"]
        windowArea = s["windowArea"]
        roofArea = floorArea
        perimeter = 4.0 * math.sqrt(floorArea)
        wallArea = max(perimeter * ceilingHeight - windowArea, 0.0)
        return roofArea, wallArea, floorArea, windowArea

    b_roofA, b_wallA, b_floorA, b_winA = areas(base_s)
    o_roofA, o_wallA, o_floorA, o_winA = areas(opt_s)

    b = base_s["capex"]
    o = opt_s["capex"]

    roof_cost_b = b["roof_nzd_per_m2"] * b_roofA
    roof_cost_o = o["roof_nzd_per_m2"] * o_roofA

    wall_cost_b = b["wall_nzd_per_m2"] * b_wallA
    wall_cost_o = o["wall_nzd_per_m2"] * o_wallA

    floor_cost_b = b["floor_nzd_per_m2"] * b_floorA
    floor_cost_o = o["floor_nzd_per_m2"] * o_floorA

    win_cost_b = b["window_nzd_per_m2_window"] * b_winA
    win_cost_o = o["window_nzd_per_m2_window"] * o_winA

    heat_cost_b = b["space_heating_install_nzd"]
    heat_cost_o = o["space_heating_install_nzd"]

    hw_cost_b = b["water_heating_install_nzd"]
    hw_cost_o = o["water_heating_install_nzd"]

    fixtures_cost_b = b["fixtures_install_nzd"]
    fixtures_cost_o = o["fixtures_install_nzd"]

    breakdown = {
        "Roof insulation": roof_cost_o - roof_cost_b,
        "Wall insulation": wall_cost_o - wall_cost_b,
        "Floor insulation": floor_cost_o - floor_cost_b,
        "Windows": win_cost_o - win_cost_b,
        "Space heating system": heat_cost_o - heat_cost_b,
        "Water heating system": hw_cost_o - hw_cost_b,
        "Fixtures (toilet/shower/tap)": fixtures_cost_o - fixtures_cost_b,
    }
    total = sum(breakdown.values())
    return {"capex_incremental_nzd": total, "breakdown_nzd": breakdown}

def calculate_scenario(s: dict, coeffs: dict) -> dict:
    space = calculate_space_heating(s)
    water_heat = calculate_water_heating(s)
    lighting = calculate_lighting(s)
    water_use = calculate_water_consumption(s)

    # Energy boundary: excludes appliances/plug loads; includes space heating + water heating + lighting.
    total_electricity_kwh_y = space["Q_purchased_kwh_y"] + water_heat["Q_purchased_kwh_y"] + lighting["Q_total_kwh_y"]

    carbon = calculate_operational_carbon(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    opex = calculate_opex(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    energy_intensity = (total_electricity_kwh_y / s["floorArea"]) if s["floorArea"] > 0 else 0.0

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
# CHARTS (Matplotlib, 2 per line layout)
# =============================================================================
def fig_stacked_bar(df: pd.DataFrame, title: str, y_label: str):
    pivot = df.pivot_table(index="Scenario", columns="Component", values="Value", aggfunc="sum").fillna(0)
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    pivot.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(y_label)
    ax.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return fig

def fig_grouped_barh(df_kpi: pd.DataFrame, title: str):
    metrics = df_kpi["Metric"].tolist()
    baseline_vals = df_kpi["Baseline"].tolist()
    option_vals = df_kpi["Option"].tolist()

    y = list(range(len(metrics)))
    h = 0.35

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh([yy - h/2 for yy in y], baseline_vals, height=h, label="Baseline")
    ax.barh([yy + h/2 for yy in y], option_vals, height=h, label="Option")
    ax.set_yticks(y)
    ax.set_yticklabels(metrics)
    ax.invert_yaxis()
    ax.set_title(title)
    ax.legend(loc="lower right")
    fig.tight_layout()
    return fig

def fig_capex_breakdown(breakdown: dict):
    items = list(breakdown.items())
    labels = [k for k, _ in items]
    vals = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.barh(labels, vals)
    ax.invert_yaxis()
    ax.set_title("Incremental capex breakdown (Option − Baseline)")
    ax.set_xlabel("NZD")
    fig.tight_layout()
    return fig

# =============================================================================
# DEFAULTS / STATE
# =============================================================================
def init_defaults():
    # Results coefficients (configured just before KPI)
    st.session_state.setdefault("coef_grid_ef", float(ASSUMPTIONS["GRID_EMISSION_FACTOR"]["value"]))
    st.session_state.setdefault("coef_water_ef", float(ASSUMPTIONS["WATER_EMISSION_FACTOR"]["value"]))
    st.session_state.setdefault("coef_elec_tariff", float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["value"]))
    st.session_state.setdefault("coef_water_tariff", float(ASSUMPTIONS["WATER_TARIFF"]["value"]))

    # Scenario numeric defaults
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", 2.4)
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        # lighting
        st.session_state.setdefault(f"{p}_light_n", LIGHTING_DEFAULTS["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LIGHTING_DEFAULTS["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LIGHTING_DEFAULTS["hoursPerDay"])

        # appliance water
        st.session_state.setdefault(f"{p}_wash_has", "Yes")
        st.session_state.setdefault(f"{p}_wash_cycles", WASHING_MACHINE_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", WASHING_MACHINE_DEFAULTS["waterPerCycle_L"])

        st.session_state.setdefault(f"{p}_dish_has", "Yes")
        st.session_state.setdefault(f"{p}_dish_cycles", DISHWASHER_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", DISHWASHER_DEFAULTS["waterPerCycle_L"])

        # HDD mode
        st.session_state.setdefault(f"{p}_hdd_mode", "From climate zone (default)")
        st.session_state.setdefault(f"{p}_hdd_override_value", None)

        # Custom performance + costs (only used if selected = Custom)
        st.session_state.setdefault(f"{p}_roofR_custom", 3.3)
        st.session_state.setdefault(f"{p}_roofCost_custom", 25.0)
        st.session_state.setdefault(f"{p}_wallR_custom", 2.0)
        st.session_state.setdefault(f"{p}_wallCost_custom", 25.0)
        st.session_state.setdefault(f"{p}_floorR_custom", 2.0)
        st.session_state.setdefault(f"{p}_floorCost_custom", 25.0)

        st.session_state.setdefault(f"{p}_windowU_custom", 3.0)
        st.session_state.setdefault(f"{p}_windowCost_custom", 250.0)

        st.session_state.setdefault(f"{p}_heatCOP_custom", 2.5)
        st.session_state.setdefault(f"{p}_heatInstall_custom", 3500.0)
        st.session_state.setdefault(f"{p}_hwCOP_custom", 2.0)
        st.session_state.setdefault(f"{p}_hwInstall_custom", 5500.0)

        st.session_state.setdefault(f"{p}_toiletL_custom", 5.0)
        st.session_state.setdefault(f"{p}_showerLmin_custom", 7.0)
        st.session_state.setdefault(f"{p}_tapLmin_custom", 6.0)
        st.session_state.setdefault(f"{p}_toiletCost_custom", 600.0)
        st.session_state.setdefault(f"{p}_showerCost_custom", 250.0)
        st.session_state.setdefault(f"{p}_tapCost_custom", 200.0)

        # Usage assumptions (now per scenario, not global expander)
        st.session_state.setdefault(f"{p}_hotWater_L_ppd", float(ASSUMPTIONS["HOT_WATER_L_PER_PERSON_DAY"]["value"]))
        st.session_state.setdefault(f"{p}_hotWater_setpoint_C", float(ASSUMPTIONS["HOT_WATER_SETPOINT_C"]["value"]))
        st.session_state.setdefault(f"{p}_coldWater_inlet_C", float(ASSUMPTIONS["COLD_WATER_INLET_C"]["value"]))
        st.session_state.setdefault(f"{p}_toiletFlushes_ppd", float(ASSUMPTIONS["TOILET_FLUSHES_PER_PERSON_DAY"]["value"]))
        st.session_state.setdefault(f"{p}_showers_ppd", float(ASSUMPTIONS["SHOWERS_PER_PERSON_DAY"]["value"]))
        st.session_state.setdefault(f"{p}_minutes_per_shower", float(ASSUMPTIONS["MINUTES_PER_SHOWER"]["value"]))
        st.session_state.setdefault(f"{p}_tapMinutes_ppd", float(ASSUMPTIONS["TAP_MINUTES_PER_PERSON_DAY"]["value"]))

    # categorical defaults MUST be unselected
    cat_keys = [
        "climateZone",
        "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "heatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

def get_coeffs() -> dict:
    return {
        "grid_ef": float(st.session_state["coef_grid_ef"]),
        "water_ef": float(st.session_state["coef_water_ef"]),
        "elec_tariff": float(st.session_state["coef_elec_tariff"]),
        "water_tariff": float(st.session_state["coef_water_tariff"]),
    }

def _resolve_hdd(prefix: str) -> float | None:
    mode = st.session_state.get(f"{prefix}_hdd_mode", "From climate zone (default)")
    if mode == "Custom HDD input":
        val = st.session_state.get(f"{prefix}_hdd_override_value", None)
        if val is None:
            return None
        return _clamp(float(val), float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["min"]), float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["max"]))

    zone = st.session_state.get(f"{prefix}_climateZone", PLACEHOLDER)
    if zone == PLACEHOLDER:
        return None
    return float(HDD_LOOKUP_BASE18[zone])

def _resolve_r_value(prefix: str, which: str, label: str, lookup: dict) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(lookup[label])
    return float(st.session_state[f"{prefix}_{which}R_custom"])

def _resolve_r_cost(prefix: str, which: str, label: str) -> float:
    if label != "Custom":
        bucket = _label_bucket_from_r_label(label)
        return float(CAPEX_ENVELOPE_NZD_PER_M2[bucket])
    return float(st.session_state[f"{prefix}_{which}Cost_custom"])

def _resolve_u_value(prefix: str, label: str) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(U_VALUES_WINDOWS[label])
    return float(st.session_state[f"{prefix}_windowU_custom"])

def _resolve_u_cost(prefix: str, label: str) -> float:
    if label != "Custom":
        return float(CAPEX_WINDOW_NZD_PER_M2_WINDOW[label])
    return float(st.session_state[f"{prefix}_windowCost_custom"])

def _resolve_system_eff(prefix: str, sys_label: str, is_hw: bool) -> float | None:
    if sys_label == PLACEHOLDER:
        return None
    if sys_label != "Custom":
        return float(WATER_HEATING_SYSTEMS[sys_label] if is_hw else HEATING_SYSTEMS[sys_label])
    return float(st.session_state[f"{prefix}_{'hwCOP' if is_hw else 'heatCOP'}_custom"])

def _resolve_system_cost(prefix: str, sys_label: str, is_hw: bool) -> float:
    if sys_label != "Custom":
        return float(CAPEX_WATER_HEATING_LUMP_NZD[sys_label] if is_hw else CAPEX_HEATING_LUMP_NZD[sys_label])
    return float(st.session_state[f"{prefix}_{'hwInstall' if is_hw else 'heatInstall'}_custom"])

def _resolve_fixture_value(prefix: str, label: str, kind: str, lookup: dict) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(lookup[label])
    if kind == "toilet":
        return float(st.session_state[f"{prefix}_toiletL_custom"])
    if kind == "shower":
        return float(st.session_state[f"{prefix}_showerLmin_custom"])
    if kind == "tap":
        return float(st.session_state[f"{prefix}_tapLmin_custom"])
    return None

def _resolve_fixture_costs(prefix: str, toilet_label: str, shower_label: str, tap_label: str) -> float:
    """
    Scenario-level fixture install cost. If predefined, uses placeholder lumps; if custom, uses user inputs.
    """
    def c_for(label: str, k: str):
        if label == "Custom":
            return float(st.session_state[f"{prefix}_{k}Cost_custom"])
        # If not custom, use placeholder upgrade lumps; baseline may legitimately be non-zero (transparent absolute basis)
        return float(CAPEX_FIXTURES_LUMP_NZD["Toilet upgrade" if k == "toilet" else "Shower upgrade" if k == "shower" else "Tap upgrade"])

    # For simplicity, always sum scenario's selected fixture costs.
    # If you later want “incremental only if upgrade vs baseline”, implement a rank-based rule.
    return c_for(toilet_label, "toilet") + c_for(shower_label, "shower") + c_for(tap_label, "tap")

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

    scenario = {
        "climateZone": None if climateZone == PLACEHOLDER else climateZone,
        "HDD_base18": _resolve_hdd(prefix),

        "floorArea": float(st.session_state[f"{prefix}_floorArea"]),
        "ceilingHeight": float(st.session_state[f"{prefix}_ceilingHeight"]),
        "householdSize": int(st.session_state[f"{prefix}_householdSize"]),
        "windowArea": float(st.session_state[f"{prefix}_windowArea"]),

        "roofRValue": _resolve_r_value(prefix, "roof", roof_label, R_VALUES_ROOF),
        "wallRValue": _resolve_r_value(prefix, "wall", wall_label, R_VALUES_WALLS),
        "floorRValue": _resolve_r_value(prefix, "floor", floor_label, R_VALUES_FLOOR),
        "windowUValue": _resolve_u_value(prefix, win_label),

        "heatingSystemEfficiency": _resolve_system_eff(prefix, heat_sys, is_hw=False),
        "waterHeatingEfficiency": _resolve_system_eff(prefix, hw_sys, is_hw=True),

        "toilet_L_per_flush": _resolve_fixture_value(prefix, toilet, "toilet", TOILET_TYPES),
        "shower_L_per_min": _resolve_fixture_value(prefix, shower, "shower", SHOWER_TYPES),
        "tap_L_per_min": _resolve_fixture_value(prefix, tap, "tap", TAP_TYPES),

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

        "usage": {
            "hotWater_L_per_person_day": float(st.session_state[f"{prefix}_hotWater_L_ppd"]),
            "hotWater_setpoint_C": float(st.session_state[f"{prefix}_hotWater_setpoint_C"]),
            "coldWater_inlet_C": float(st.session_state[f"{prefix}_coldWater_inlet_C"]),
            "toiletFlushes_per_person_day": float(st.session_state[f"{prefix}_toiletFlushes_ppd"]),
            "showers_per_person_day": float(st.session_state[f"{prefix}_showers_ppd"]),
            "minutes_per_shower": float(st.session_state[f"{prefix}_minutes_per_shower"]),
            "tapMinutes_per_person_day": float(st.session_state[f"{prefix}_tapMinutes_ppd"]),
        },

        "capex": {
            "roof_nzd_per_m2": _resolve_r_cost(prefix, "roof", roof_label) if roof_label != PLACEHOLDER else 0.0,
            "wall_nzd_per_m2": _resolve_r_cost(prefix, "wall", wall_label) if wall_label != PLACEHOLDER else 0.0,
            "floor_nzd_per_m2": _resolve_r_cost(prefix, "floor", floor_label) if floor_label != PLACEHOLDER else 0.0,
            "window_nzd_per_m2_window": _resolve_u_cost(prefix, win_label) if win_label != PLACEHOLDER else 0.0,
            "space_heating_install_nzd": _resolve_system_cost(prefix, heat_sys, is_hw=False) if heat_sys != PLACEHOLDER else 0.0,
            "water_heating_install_nzd": _resolve_system_cost(prefix, hw_sys, is_hw=True) if hw_sys != PLACEHOLDER else 0.0,
            "fixtures_install_nzd": _resolve_fixture_costs(prefix, toilet, shower, tap) if (toilet != PLACEHOLDER and shower != PLACEHOLDER and tap != PLACEHOLDER) else 0.0,
        },

        # keep labels for payload/audit
        "_labels": {
            "roof": roof_label, "wall": wall_label, "floor": floor_label, "window": win_label,
            "heatingSystem": heat_sys, "waterHeatingSystem": hw_sys,
            "toilet": toilet, "shower": shower, "tap": tap,
            "hdd_mode": st.session_state.get(f"{prefix}_hdd_mode", "From climate zone (default)"),
        }
    }
    return scenario

def validate_scenario(s: dict) -> list:
    missing = []
    if s["climateZone"] is None:
        missing.append("Climate zone")
    if s["HDD_base18"] is None:
        missing.append("HDD (source selection incomplete)")
    if s["roofRValue"] is None: missing.append("Roof insulation (R-value)")
    if s["wallRValue"] is None: missing.append("Wall insulation (R-value)")
    if s["floorRValue"] is None: missing.append("Floor insulation (R-value)")
    if s["windowUValue"] is None: missing.append("Window type (U-value)")
    if s["heatingSystemEfficiency"] is None: missing.append("Space heating system (efficiency/COP)")
    if s["waterHeatingEfficiency"] is None: missing.append("Water heating system (efficiency/COP)")
    if s["toilet_L_per_flush"] is None: missing.append("Toilet type (L/flush)")
    if s["shower_L_per_min"] is None: missing.append("Shower type (L/min)")
    if s["tap_L_per_min"] is None: missing.append("Tap type (L/min)")
    if s["washingMachine"]["hasAppliance"] is None: missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None: missing.append("Dishwasher (Yes/No)")
    return missing

def copy_baseline_to_option():
    mappings = [
        # categorical
        ("b_climateZone", "o_climateZone"),
        ("b_hdd_mode", "o_hdd_mode"),
        ("b_hdd_override_value", "o_hdd_override_value"),

        ("b_roofRLabel", "o_roofRLabel"),
        ("b_wallRLabel", "o_wallRLabel"),
        ("b_floorRLabel", "o_floorRLabel"),
        ("b_windowULabel", "o_windowULabel"),
        ("b_heatingSystem", "o_heatingSystem"),
        ("b_waterHeatingSystem", "o_waterHeatingSystem"),
        ("b_toiletType", "o_toiletType"),
        ("b_showerType", "o_showerType"),
        ("b_tapType", "o_tapType"),

        # numeric geometry
        ("b_floorArea", "o_floorArea"),
        ("b_ceilingHeight", "o_ceilingHeight"),
        ("b_householdSize", "o_householdSize"),
        ("b_windowArea", "o_windowArea"),

        # custom performance/cost
        ("b_roofR_custom", "o_roofR_custom"),
        ("b_roofCost_custom", "o_roofCost_custom"),
        ("b_wallR_custom", "o_wallR_custom"),
        ("b_wallCost_custom", "o_wallCost_custom"),
        ("b_floorR_custom", "o_floorR_custom"),
        ("b_floorCost_custom", "o_floorCost_custom"),
        ("b_windowU_custom", "o_windowU_custom"),
        ("b_windowCost_custom", "o_windowCost_custom"),
        ("b_heatCOP_custom", "o_heatCOP_custom"),
        ("b_heatInstall_custom", "o_heatInstall_custom"),
        ("b_hwCOP_custom", "o_hwCOP_custom"),
        ("b_hwInstall_custom", "o_hwInstall_custom"),
        ("b_toiletL_custom", "o_toiletL_custom"),
        ("b_showerLmin_custom", "o_showerLmin_custom"),
        ("b_tapLmin_custom", "o_tapLmin_custom"),
        ("b_toiletCost_custom", "o_toiletCost_custom"),
        ("b_showerCost_custom", "o_showerCost_custom"),
        ("b_tapCost_custom", "o_tapCost_custom"),

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

        # usage assumptions
        ("b_hotWater_L_ppd", "o_hotWater_L_ppd"),
        ("b_hotWater_setpoint_C", "o_hotWater_setpoint_C"),
        ("b_coldWater_inlet_C", "o_coldWater_inlet_C"),
        ("b_toiletFlushes_ppd", "o_toiletFlushes_ppd"),
        ("b_showers_ppd", "o_showers_ppd"),
        ("b_minutes_per_shower", "o_minutes_per_shower"),
        ("b_tapMinutes_ppd", "o_tapMinutes_ppd"),
    ]
    for src, dst in mappings:
        st.session_state[dst] = copy.deepcopy(st.session_state[src])

# =============================================================================
# TAB 2 (Assumptions table builder)
# =============================================================================
def assumptions_dataframe() -> pd.DataFrame:
    rows = []
    for k, meta in ASSUMPTIONS.items():
        rows.append({
            "Parameter name (machine-readable)": k,
            "Value (default)": meta.get("value"),
            "Unit": meta.get("unit"),
            "Where used": meta.get("where_used"),
            "Source type": meta.get("source_type"),
            "Citation / link / doc + page": meta.get("citation"),
            "Rationale": meta.get("rationale"),
            "Sensitivity": meta.get("sensitivity"),
            "Override allowed?": meta.get("override_allowed"),
            "Override location (UI)": meta.get("override_location"),
            "Validation rule": meta.get("validation_rule"),
        })
    # Add boundary assumptions explicitly (auditable narrative assumptions)
    rows.extend([
        {
            "Parameter name (machine-readable)": "ENERGY_BOUNDARY",
            "Value (default)": "Space heating + water heating + lighting (excludes appliances/plug loads)",
            "Unit": "",
            "Where used": "calculate_scenario() aggregation",
            "Source type": "Homestar",
            "Citation / link / doc + page": "Homestar EF4 framing — add doc name + page reference (to be filled).",
            "Rationale": "Keeps the KPI defensible and aligned with rating-system operational energy boundaries.",
            "Sensitivity": "High",
            "Override allowed?": "No",
            "Override location (UI)": "N/A",
            "Validation rule": "Boundary is fixed in this prototype.",
        },
        {
            "Parameter name (machine-readable)": "CARBON_SCOPE",
            "Value (default)": "Electricity + supplied water only (average factors)",
            "Unit": "",
            "Where used": "calculate_operational_carbon()",
            "Source type": "Placeholder",
            "Citation / link / doc + page": "Replace with NZ scope framing reference (e.g., MBIE / utility guidance).",
            "Rationale": "A narrow scope reduces implied accuracy and maintains transparency for an early-stage tool.",
            "Sensitivity": "Medium",
            "Override allowed?": "No",
            "Override location (UI)": "N/A",
            "Validation rule": "Scope is fixed; factors are editable.",
        },
    ])
    return pd.DataFrame(rows)

# =============================================================================
# APP
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.write(
    "Early-stage decision support for comparing housing scenarios. "
    "**Not a certification tool. Not ECCHO.** Designed for transparency and iteration."
)

tabs = st.tabs(["1) Scenario", "2) Assumptions", "3) Calculations", "4) Indicators"])

# -----------------------------------------------------------------------------
# TAB 1: Scenario (Inputs + Results)
# -----------------------------------------------------------------------------
with tabs[0]:
    col_b, col_o = st.columns([1.05, 1.05], gap="large")

    def scenario_inputs(prefix: str, title: str):
        st.subheader(title)

        # A) Core
        with st.expander("A) Core inputs", expanded=True):
            select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key=f"{prefix}_climateZone")

            st.session_state.setdefault(f"{prefix}_hdd_mode", "From climate zone (default)")
            hdd_mode = st.selectbox(
                "HDD source",
                ["From climate zone (default)", "Custom HDD input"],
                index=0 if st.session_state.get(f"{prefix}_hdd_mode") == "From climate zone (default)" else 1,
                key=f"{prefix}_hdd_mode",
            )

            if st.session_state[f"{prefix}_climateZone"] != PLACEHOLDER and hdd_mode == "From climate zone (default)":
                st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state[f'{prefix}_climateZone']]}** (placeholder lookup)")

            if hdd_mode == "Custom HDD input":
                default_val = float(HDD_LOOKUP_BASE18.get(st.session_state[f"{prefix}_climateZone"], 2000)) if st.session_state[f"{prefix}_climateZone"] != PLACEHOLDER else 2000.0
                st.number_input(
                    "HDD (base 18°C)",
                    min_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["min"]),
                    max_value=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["max"]),
                    step=float(ASSUMPTIONS["HDD_LOOKUP_BASE18"]["step"]),
                    value=float(default_val) if st.session_state.get(f"{prefix}_hdd_override_value") is None else float(st.session_state[f"{prefix}_hdd_override_value"]),
                    key=f"{prefix}_hdd_override_value",
                    help="Uses this HDD value instead of the climate-zone lookup for space heating.",
                )

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea")
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight")
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize")
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea")

        # B) Thermal envelope (with Custom + custom cost)
        with st.expander("B) Thermal envelope (performance + capex)", expanded=False):
            select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key=f"{prefix}_roofRLabel")
            if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom")
                st.number_input("Roof capex (NZD/m² of roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom")

            select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key=f"{prefix}_wallRLabel")
            if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom")
                st.number_input("Wall capex (NZD/m² of wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom")

            select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key=f"{prefix}_floorRLabel")
            if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom")
                st.number_input("Floor capex (NZD/m² of floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom")

            select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key=f"{prefix}_windowULabel")
            if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom")
                st.number_input("Windows capex (NZD/m² of window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom")

        # C) Systems (with Custom + install cost)
        with st.expander("C) Systems (energy performance + capex)", expanded=False):
            select_with_placeholder("Space heating system", list(HEATING_SYSTEMS.keys()), key=f"{prefix}_heatingSystem")
            if st.session_state[f"{prefix}_heatingSystem"] == "Custom":
                st.number_input("Space heating COP/efficiency", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_heatCOP_custom")
                st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_heatInstall_custom")

            select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key=f"{prefix}_waterHeatingSystem")
            if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                st.number_input("Water heating COP/efficiency", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_hwCOP_custom")
                st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_hwInstall_custom")

        # D) Lighting
        with st.expander("D) Lighting (energy; no plug loads)", expanded=False):
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n")
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts")
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours")
            st.caption("Energy excludes appliances/plug loads by design.")

        # E) Water fixtures + appliance water (with Custom + capex)
        with st.expander("E) Water fixtures + appliance water (plus capex)", expanded=False):
            select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key=f"{prefix}_toiletType")
            if st.session_state[f"{prefix}_toiletType"] == "Custom":
                st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletL_custom")
                st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toiletCost_custom")

            select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key=f"{prefix}_showerType")
            if st.session_state[f"{prefix}_showerType"] == "Custom":
                st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_showerLmin_custom")
                st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_showerCost_custom")

            select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key=f"{prefix}_tapType")
            if st.session_state[f"{prefix}_tapType"] == "Custom":
                st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tapLmin_custom")
                st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tapCost_custom")

            st.markdown("**Washing machine (water only)**")
            select_with_placeholder("Has washing machine?", ["Yes", "No"], key=f"{prefix}_wash_has")
            if st.session_state[f"{prefix}_wash_has"] == "Yes":
                st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles")
                st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L")

            st.markdown("**Dishwasher (water only)**")
            select_with_placeholder("Has dishwasher?", ["Yes", "No"], key=f"{prefix}_dish_has")
            if st.session_state[f"{prefix}_dish_has"] == "Yes":
                st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles")
                st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L")

        # F) Usage assumptions (moved here; per scenario)
        with st.expander("F) Usage assumptions (affects water + hot water energy)", expanded=False):
            st.number_input("Hot water demand (L/person/day)", min_value=0.0, max_value=300.0, step=1.0, key=f"{prefix}_hotWater_L_ppd")
            st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
            st.number_input("Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")

            st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
            st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
            st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
            st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

    # -------------------- Baseline --------------------
    with col_b:
        scenario_inputs("b", "Baseline")
        st.divider()
        if st.button("Copy Baseline → Option", use_container_width=True):
            copy_baseline_to_option()
            st.rerun()

    # -------------------- Option --------------------
    with col_o:
        scenario_inputs("o", "Option")

    # -------------------- Results (always at bottom) --------------------
    st.divider()

    baseline_now = get_scenario("b")
    option_now = get_scenario("o")

    missing_b = validate_scenario(baseline_now)
    missing_o = validate_scenario(option_now)

    if missing_b:
        st.info("Baseline incomplete. Missing: " + ", ".join(missing_b))
        st.stop()

    # Tariffs + factors immediately before KPI
    with st.expander("Tariffs & factors (affects carbon + opex)", expanded=True):
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.number_input(
                "Electricity tariff (NZD/kWh)",
                min_value=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["min"]),
                max_value=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["max"]),
                step=float(ASSUMPTIONS["ELECTRICITY_TARIFF"]["step"]),
                key="coef_elec_tariff",
            )
        with c2:
            st.number_input(
                "Water tariff (NZD/m³)",
                min_value=float(ASSUMPTIONS["WATER_TARIFF"]["min"]),
                max_value=float(ASSUMPTIONS["WATER_TARIFF"]["max"]),
                step=float(ASSUMPTIONS["WATER_TARIFF"]["step"]),
                key="coef_water_tariff",
            )
        with c3:
            st.number_input(
                "Grid emission factor (kgCO₂e/kWh)",
                min_value=float(ASSUMPTIONS["GRID_EMISSION_FACTOR"]["min"]),
                max_value=float(ASSUMPTIONS["GRID_EMISSION_FACTOR"]["max"]),
                step=float(ASSUMPTIONS["GRID_EMISSION_FACTOR"]["step"]),
                key="coef_grid_ef",
            )
        with c4:
            st.number_input(
                "Water emission factor (kgCO₂e/m³)",
                min_value=float(ASSUMPTIONS["WATER_EMISSION_FACTOR"]["min"]),
                max_value=float(ASSUMPTIONS["WATER_EMISSION_FACTOR"]["max"]),
                step=float(ASSUMPTIONS["WATER_EMISSION_FACTOR"]["step"]),
                key="coef_water_ef",
            )

    coeffs = get_coeffs()

    base_r = calculate_scenario(baseline_now, coeffs)
    opt_r = None if missing_o else calculate_scenario(option_now, coeffs)

    capex = None
    if opt_r is not None:
        capex = calculate_incremental_capex(baseline_now, option_now)

    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "coefficients": coeffs,
        "baseline": {"inputs": baseline_now, "results": base_r, "missing": []},
        "option": {"inputs": option_now, "results": opt_r, "missing": missing_o},
        "capex": capex,
        "notes": {
            "scope": "Early-stage decision support; not certification; not simulation.",
            "energy_boundary": "Energy excludes appliances/plug loads; includes space heating + water heating + lighting.",
            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
            "capex_boundary": "Incremental capex uses scenario-specific unit costs (placeholder or user-supplied). Not investment-grade.",
        },
    }

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
    else:
        # Charts: show all together, 2 per line
        st.divider()
        st.markdown("### Charts (Baseline vs Option)")

        df_kpi = pd.DataFrame([
            {"Metric": "Energy (kWh/y)", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
            {"Metric": "Energy Intensity (kWh/m²/y)", "Baseline": base_r["energyIntensity_kwh_m2_y"], "Option": opt_r["energyIntensity_kwh_m2_y"]},
            {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
            {"Metric": "Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
            {"Metric": "Opex (NZD/y)", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
        ])

        df_energy = pd.DataFrame([
            {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
            {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
            {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
            {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
            {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
            {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_total_kwh_y"]},
        ])

        b_w = base_r["waterConsumption"]["breakdown_m3_y"]
        o_w = opt_r["waterConsumption"]["breakdown_m3_y"]
        df_water = pd.DataFrame(
            [{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b_w.items()] +
            [{"Scenario": "Option", "Component": k, "Value": v} for k, v in o_w.items()]
        )

        df_carbon = pd.DataFrame([
            {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
            {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
            {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity_kg_y"]},
            {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water_kg_y"]},
        ])

        df_opex = pd.DataFrame([
            {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
            {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
            {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["opex"]["opex_electricity_nzd_y"]},
            {"Scenario": "Option", "Component": "Water", "Value": opt_r["opex"]["opex_water_nzd_y"]},
        ])

        row1 = st.columns(2, gap="large")
        with row1[0]:
            st.pyplot(fig_grouped_barh(df_kpi, "KPIs: Baseline vs Option"))
        with row1[1]:
            st.pyplot(fig_stacked_bar(df_energy, "Energy breakdown (excl. plug loads)", "kWh/year"))

        row2 = st.columns(2, gap="large")
        with row2[0]:
            st.pyplot(fig_stacked_bar(df_water, "Indoor water breakdown", "m³/year"))
        with row2[1]:
            st.pyplot(fig_stacked_bar(df_carbon, "Operational carbon breakdown", "kgCO₂e/year"))

        row3 = st.columns(2, gap="large")
        with row3[0]:
            st.pyplot(fig_stacked_bar(df_opex, "Opex breakdown", "NZD/year"))
        with row3[1]:
            st.pyplot(fig_capex_breakdown(capex["breakdown_nzd"]))

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
        "This prototype is simplified and indicative. No embodied carbon. No behavioural modelling. "
        "No ventilation/infiltration modelling. Many coefficients remain placeholders until replaced with sourced NZ values."
    )

# -----------------------------------------------------------------------------
# TAB 2: Assumptions (Auditable provenance table)
# -----------------------------------------------------------------------------
with tabs[1]:
    st.subheader("Assumptions / Provenance (Auditable Registry)")
    st.write(
        "This table documents default parameter values, provenance, where each parameter is used, "
        "and the exact UI location where overrides are allowed."
    )
    st.dataframe(assumptions_dataframe(), use_container_width=True, hide_index=True)

# -----------------------------------------------------------------------------
# TAB 3: Calculations (Formulas)
# -----------------------------------------------------------------------------
with tabs[2]:
    st.subheader("Calculations (Transparent Equations)")
    st.markdown(
        r"""
**Important:** This is a transparent, early-stage comparative model. It is not ECCHO and does not replicate Homestar.

### 1) Space Heating (steady-state heat loss + HDD)
- Heat loss coefficient:
  - \(H = A_{roof}U_{roof} + A_{wall}U_{wall} + A_{floor}U_{floor} + A_{win}U_{win}\)
- Annual delivered heat (kWh/y):
  - \(Q_{del} = (H \times HDD \times 24) / 1000\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

### 2) Water Heating (volume + temperature rise)
- Annual hot water volume:
  - \(V_y = n \times L_{ppd} \times 365\)
- Delivered thermal energy:
  - \(Q_{del} = (V_y \times \Delta T \times C_p) / 3600\)
- Purchased electricity:
  - \(Q_{purch} = Q_{del} / COP\)

### 3) Lighting Electricity (no plug loads)
- \(Q_{light} = (N_{lights} \times W_{light} \times h_{day} \times 365)/1000\)

### 4) Indoor Water Consumption (fixtures + appliances)
- Toilets:
  - \(V_{toilet} = n \times flushes \times L_{flush} \times 365\)
- Showers:
  - \(V_{shower} = n \times showers \times min_{shower} \times L/min \times 365\)
- Taps:
  - \(V_{tap} = n \times min_{tap} \times L/min \times 365\)
- Appliances (water only):
  - \(V_{wash} = cycles/wk \times L/cycle \times 52\)
  - \(V_{dish} = cycles/wk \times L/cycle \times 52\)

### 5) Operational Carbon (average factors)
- \(CO2 = kWh \times EF_{grid} + m^3 \times EF_{water}\)

### 6) Opex (average tariffs)
- \(Cost = kWh \times tariff_e + m^3 \times tariff_w\)

### 7) Incremental Capex (transparent unit-cost accounting)
- Scenario element costs are computed using user-selected or user-entered unit costs.
- Incremental capex is:
  - \(Capex_{\Delta} = Capex_{option} - Capex_{baseline}\)
        """
    )

# -----------------------------------------------------------------------------
# TAB 4: Indicators (tight boundaries)
# -----------------------------------------------------------------------------
with tabs[3]:
    st.subheader("Indicators (Definitions and Boundaries)")
    st.markdown(
        """
### Energy KPI (kWh/year)
**Includes:** Space heating electricity + hot water heating electricity + lighting electricity.  
**Excludes:** Appliances/plug loads (e.g., dishwasher energy, washing machine energy, cooking).  
**Why:** This boundary is deliberately narrow and defensible for early-stage comparison, aligned with common rating-system operational energy framing.

### Water KPI (m³/year)
**Includes:** Toilets + showers + taps + dishwasher water + washing machine water.  
**Excludes:** Outdoor irrigation, leakage, seasonal effects, rainwater/greywater offsets (not implemented).

### Operational Carbon (kgCO₂e/year)
**Scope:** Electricity + supplied water only, using average factors.  
**Excludes:** Embodied carbon, marginal emissions, time-of-use effects.

### Operating Cost / Opex (NZD/year)
**Includes:** Electricity + water variable charges only.  
**Excludes:** Fixed charges, time-of-use pricing, demand charges, maintenance.

### What this tool is not
- Not a Homestar certification workflow.
- Not an ECCHO calculation engine.
- Not a building energy simulation model.
        """
    )
