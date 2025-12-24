# streamlit_app.py
import copy
import json
import math
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
# LOOKUP TABLES (Single Source of Truth)
# =============================================================================
LOOKUP = {
    "constants": {
        # Defaults (can be overridden per scenario in Usage block)
        "grid_emission_factor_kgco2e_per_kwh_default": 0.0729,  # MfE (2024) for 2023
        "water_emission_factor_kgco2e_per_m3_default": 0.0349,  # MfE (2024)

        "electricity_tariff_nzd_per_kwh_default": 0.312,  # placeholder
        "water_tariff_nzd_per_m3_default": 2.296,         # placeholder

        "ceiling_height_m_default": 2.4,
        "cp_kj_per_kgC": 4.186,
    },

    "thermal_envelope": {
        "floorR_m2K_per_W": {
            "Uninsulated": 0.6, "Basic": 1.5, "Code minimum": 2.0, "Good": 2.8, "Excellent": 3.5
        },
        "roofR_m2K_per_W": {
            "Uninsulated": 0.5, "Basic": 3.0, "Code minimum": 6.6, "Good": 8.0, "Excellent": 10.0
        },
        "wallR_m2K_per_W": {
            "Uninsulated": 0.5, "Basic": 1.5, "Code minimum": 2.0, "Good": 3.0, "Excellent": 4.0
        },
        "windowU_W_per_m2K": {
            "Single glazed": 5.8,
            "Standard double glazed": 3.0,
            "Low-E double glazed": 2.0,
            "High-performance triple glazed": 1.0,
        },
        "capex_per_m2": {
            "floor": {"Uninsulated": 0, "Basic": 20, "Code minimum": 40, "Good": 70, "Excellent": 110},
            "roof":  {"Uninsulated": 0, "Basic": 15, "Code minimum": 25, "Good": 35, "Excellent": 35},
            "wall":  {"Uninsulated": 0, "Basic": 25, "Code minimum": 45, "Good": 75, "Excellent": 120},
            "window": {
                "Single glazed": 300,
                "Standard double glazed": 600,
                "Low-E double glazed": 950,
                "High-performance triple glazed": 1400,
            },
        },
    },

    "climate": {
        "hdd_by_zone_base18": {
            "Climate Zone 1 – Warmest": 1200,
            "Climate Zone 2 – Warm": 1400,
            "Climate Zone 3 – Mild": 1800,
            "Climate Zone 4 – Cool": 2200,
            "Climate Zone 5 – Cold": 2400,
            "Climate Zone 6 – Coldest": 3000,
        },
        "zone_by_city": {
            "Auckland": "Climate Zone 1 – Warmest",
            "Whangarei": "Climate Zone 1 – Warmest",
            "Tauranga": "Climate Zone 1 – Warmest",
            "Hamilton": "Climate Zone 2 – Warm",
            "New Plymouth": "Climate Zone 2 – Warm",
            "Napier": "Climate Zone 2 – Warm",
            "Hastings": "Climate Zone 2 – Warm",
            "Gisborne": "Climate Zone 2 – Warm",
            "Wellington": "Climate Zone 3 – Mild",
            "Nelson": "Climate Zone 3 – Mild",
            "Blenheim": "Climate Zone 3 – Mild",
            "Rotorua": "Climate Zone 4 – Cool",
            "Taupo": "Climate Zone 4 – Cool",
            "Palmerston North": "Climate Zone 4 – Cool",
            "Westport": "Climate Zone 4 – Cool",
            "Christchurch": "Climate Zone 5 – Cold",
            "Dunedin": "Climate Zone 5 – Cold",
            "Timaru": "Climate Zone 5 – Cold",
            "Queenstown": "Climate Zone 6 – Coldest",
            "Invercargill": "Climate Zone 6 – Coldest",
            "Gore": "Climate Zone 6 – Coldest",
            "Alexandra": "Climate Zone 6 – Coldest",
        },
    },

    "systems": {
        "space_heating": {
            "cop": {
                "None": 0.0,
                "Electric resistance heater": 1.0,
                "Air-source Heat pump": 2.5,
                "High-efficiency heat pump": 3.5,
            },
            "install_cost_nzd": {
                "None": 0,
                "Electric resistance heater": 1500,
                "Air-source Heat pump": 4500,
                "High-efficiency heat pump": 7000,
            },
        },
        "water_heating": {
            "cop": {
                "None": 0.0,
                "Electric storage cylinder": 1.0,
                "Heat pump hot water": 2.0,
            },
            "install_cost_nzd": {
                "None": 0,
                "Electric storage cylinder": 3500,
                "Heat pump hot water": 6500,
            },
        },
    },

    "fixtures": {
        "toilet": {
            "l_per_flush": {
                "Single flush": 9,
                "Dual flush standard (avg 5 L)": 5,
                "Dual flush efficient (avg 4 L)": 4,
            },
            "install_cost_nzd": {
                "Single flush": 300,
                "Dual flush standard (avg 5 L)": 450,
                "Dual flush efficient (avg 4 L)": 650,
            },
        },
        "shower": {
            "l_per_min": {"Standard": 9, "Low flow": 7, "Efficient": 6},
            "install_cost_nzd": {"Standard": 50, "Low flow": 120, "Efficient": 220},
        },
        "tap": {
            "l_per_min": {"Standard": 8, "Efficient": 6, "Very efficient": 4},
            "install_cost_nzd": {"Standard": 70, "Efficient": 150, "Very efficient": 250},
        },
        "hot_water_fractions": {"shower": 0.9, "tap": 0.4, "laundry": 0.5, "dishwasher": 1.0},
    },

    "defaults": {
        "washing_machine": {"hasAppliance": False, "cyclesPerWeek": 4, "waterPerCycle_L": 60},
        "dishwasher": {"hasAppliance": False, "cyclesPerWeek": 4, "waterPerCycle_L": 12},
        "lighting": {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5},
        "usage": {
            "toiletFlushes_per_person_day": 5.0,
            "showers_per_person_day": 1.0,
            "minutes_per_shower": 6.21,
            "tapMinutes_per_person_day": 10.0,
            "hotWater_setpoint_C": 60.0,
            "coldWater_inlet_C": 15.0,
        },
    },
}

# =============================================================================
# UTIL
# =============================================================================
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

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _bucket_from_label(label: str) -> str:
    for b in ["Uninsulated", "Basic", "Code minimum", "Good", "Excellent"]:
        if label == b:
            return b
    return "Uninsulated"

def _yn_to_bool(v: str):
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)

def show_selected_line(name: str, perf: str | None = None, cost: str | None = None):
    parts = [f"Selected: **{name}**"]
    if perf:
        parts.append(f"Performance: **{perf}**")
    if cost:
        parts.append(f"Cost: **{cost}**")
    st.caption(" | ".join(parts))

# =============================================================================
# RESOLVERS
# =============================================================================
def resolve_from_lookup_or_custom(label: str, custom_key: str, lookup_dict: dict) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(lookup_dict[label])
    return float(st.session_state[custom_key])

def resolve_capex_envelope(element: str, label: str, custom_key: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        bucket = _bucket_from_label(label)
        return float(LOOKUP["thermal_envelope"]["capex_per_m2"][element][bucket])
    return float(st.session_state[custom_key])

def resolve_capex_window(label: str, custom_key: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["thermal_envelope"]["capex_per_m2"]["window"][label])
    return float(st.session_state[custom_key])

def resolve_cop(label: str, custom_key: str, sys_block: str) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(LOOKUP["systems"][sys_block]["cop"][label])
    return float(st.session_state[custom_key])

def resolve_install_cost(label: str, custom_key: str, sys_block: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["systems"][sys_block]["install_cost_nzd"][label])
    return float(st.session_state[custom_key])

def resolve_fixture_value(label: str, kind: str, custom_key: str) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        key = "l_per_flush" if kind == "toilet" else "l_per_min"
        return float(LOOKUP["fixtures"][kind][key][label])
    return float(st.session_state[custom_key])

def resolve_fixture_cost(label: str, kind: str, custom_key: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["fixtures"][kind]["install_cost_nzd"][label])
    return float(st.session_state[custom_key])

# =============================================================================
# CORE CALCS
# =============================================================================
def _geometry_areas(floor_area: float, ceiling_h: float, window_area: float) -> dict:
    roof_area = floor_area
    perimeter = 4.0 * math.sqrt(max(floor_area, 0.0))
    wall_area = max(perimeter * ceiling_h - window_area, 0.0)
    return {"roof": roof_area, "wall": wall_area, "floor": floor_area, "window": window_area}

def calculate_space_heating(s: dict) -> dict:
    HDD = s["HDD_base18"]
    areas = _geometry_areas(s["floorArea"], s["ceilingHeight"], s["windowArea"])

    roofU = 1.0 / s["roofRValue"]
    wallU = 1.0 / s["wallRValue"]
    floorU = 1.0 / s["floorRValue"]
    winU = s["windowUValue"]

    H_roof = areas["roof"] * roofU
    H_wall = areas["wall"] * wallU
    H_floor = areas["floor"] * floorU
    H_window = areas["window"] * winU
    H_total = H_roof + H_wall + H_floor + H_window

    delivered_kwh = (H_total * HDD * 24.0) / 1000.0
    cop = s["spaceHeatingCOP"]

    if cop is None or cop <= 0:
        purchased_kwh = 0.0
        warning = "Space heating COP is 0/None → purchased set to 0."
    else:
        purchased_kwh = delivered_kwh / cop
        warning = None

    return {
        "H_total_W_per_K": H_total,
        "Q_delivered_kwh_y": delivered_kwh,
        "Q_purchased_kwh_y": purchased_kwh,
        "warning": warning,
        "breakdown_W_per_K": {"H_roof": H_roof, "H_wall": H_wall, "H_floor": H_floor, "H_window": H_window},
    }

def calculate_water_enduse(s: dict) -> dict:
    n = s["householdSize"]
    u = s["usage"]

    toilet_Lpf = s["toilet_L_per_flush"]
    shower_Lpm = s["shower_L_per_min"]
    tap_Lpm = s["tap_L_per_min"]

    V_toilet_L_y = n * u["toiletFlushes_per_person_day"] * toilet_Lpf * 365.0
    V_shower_L_y = n * u["showers_per_person_day"] * u["minutes_per_shower"] * shower_Lpm * 365.0
    V_tap_L_y = n * u["tapMinutes_per_person_day"] * tap_Lpm * 365.0

    wash = s["washingMachine"]
    dish = s["dishwasher"]
    V_laundry_L_y = (wash["cyclesPerWeek"] * wash["waterPerCycle_L"] * 52.0) if wash["hasAppliance"] else 0.0
    V_dish_L_y = (dish["cyclesPerWeek"] * dish["waterPerCycle_L"] * 52.0) if dish["hasAppliance"] else 0.0

    total_m3_y = (V_toilet_L_y + V_shower_L_y + V_tap_L_y + V_laundry_L_y + V_dish_L_y) / 1000.0

    return {
        "enduse_L_y": {
            "toilet": V_toilet_L_y,
            "shower": V_shower_L_y,
            "tap": V_tap_L_y,
            "laundry": V_laundry_L_y,
            "dishwasher": V_dish_L_y,
        },
        "V_total_m3_y": total_m3_y,
        "breakdown_m3_y": {
            "Toilets": V_toilet_L_y / 1000.0,
            "Showers": V_shower_L_y / 1000.0,
            "Taps": V_tap_L_y / 1000.0,
            "Laundry": V_laundry_L_y / 1000.0,
            "Dishwasher": V_dish_L_y / 1000.0,
        },
    }

def calculate_water_heating_from_enduse(s: dict, enduse_L_y: dict) -> dict:
    fr = LOOKUP["fixtures"]["hot_water_fractions"]
    u = s["usage"]

    V_hot_L_y = (
        enduse_L_y["shower"] * fr["shower"]
        + enduse_L_y["tap"] * fr["tap"]
        + enduse_L_y["laundry"] * fr["laundry"]
        + enduse_L_y["dishwasher"] * fr["dishwasher"]
    )

    deltaT = float(u["hotWater_setpoint_C"]) - float(u["coldWater_inlet_C"])
    cp = float(LOOKUP["constants"]["cp_kj_per_kgC"])

    delivered_kwh = (V_hot_L_y * cp * deltaT) / 3600.0
    cop = s["waterHeatingCOP"]

    if cop is None or cop <= 0:
        purchased_kwh = 0.0
        warning = "Water heating COP is 0/None → purchased set to 0."
    else:
        purchased_kwh = delivered_kwh / cop
        warning = None

    return {
        "V_hot_L_y": V_hot_L_y,
        "deltaT_C": deltaT,
        "Q_delivered_kwh_y": delivered_kwh,
        "Q_purchased_kwh_y": purchased_kwh,
        "warning": warning,
    }

def calculate_lighting(s: dict) -> dict:
    L = s["lighting"]
    Q = (L["numberOfLights"] * L["wattsPerLight"] * L["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_total_kwh_y": Q}

def calculate_operational_carbon(total_kwh_y: float, total_m3_y: float, coeffs: dict) -> dict:
    CO2_e = total_kwh_y * coeffs["grid_ef"]
    CO2_w = total_m3_y * coeffs["water_ef"]
    return {"CO2_total_kg_y": CO2_e + CO2_w, "CO2_electricity_kg_y": CO2_e, "CO2_water_kg_y": CO2_w}

def calculate_opex(total_kwh_y: float, total_m3_y: float, coeffs: dict) -> dict:
    c_e = total_kwh_y * coeffs["elec_tariff"]
    c_w = total_m3_y * coeffs["water_tariff"]
    return {"opex_total_nzd_y": c_e + c_w, "opex_electricity_nzd_y": c_e, "opex_water_nzd_y": c_w}

def compute_capex_totals(s: dict) -> dict:
    areas = _geometry_areas(s["floorArea"], s["ceilingHeight"], s["windowArea"])
    cap = s["capex"]

    envelope = (
        cap["roof_nzd_per_m2"] * areas["roof"]
        + cap["wall_nzd_per_m2"] * areas["wall"]
        + cap["floor_nzd_per_m2"] * areas["floor"]
        + cap["window_nzd_per_m2_window"] * areas["window"]
    )
    systems = cap["space_heating_install_nzd"] + cap["water_heating_install_nzd"]
    fixtures = cap["toilet_install_nzd"] + cap["shower_install_nzd"] + cap["tap_install_nzd"]
    total = envelope + systems + fixtures

    return {"capex_total_nzd": total, "breakdown_nzd": {"Envelope": envelope, "Systems": systems, "Fixtures": fixtures}}

def compute_capex_breakdown_detailed(s: dict) -> dict:
    areas = _geometry_areas(s["floorArea"], s["ceilingHeight"], s["windowArea"])
    cap = s["capex"]
    return {
        "Roof insulation": cap["roof_nzd_per_m2"] * areas["roof"],
        "Wall insulation": cap["wall_nzd_per_m2"] * areas["wall"],
        "Floor insulation": cap["floor_nzd_per_m2"] * areas["floor"],
        "Windows": cap["window_nzd_per_m2_window"] * areas["window"],
        "Space heating system": cap["space_heating_install_nzd"],
        "Water heating system": cap["water_heating_install_nzd"],
        "Toilet install": cap["toilet_install_nzd"],
        "Shower install": cap["shower_install_nzd"],
        "Tap install": cap["tap_install_nzd"],
    }

def calculate_incremental_capex(base_s: dict, opt_s: dict) -> dict:
    base_total = compute_capex_totals(base_s)
    opt_total = compute_capex_totals(opt_s)
    inc = opt_total["capex_total_nzd"] - base_total["capex_total_nzd"]

    breakdown_base = compute_capex_breakdown_detailed(base_s)
    breakdown_opt = compute_capex_breakdown_detailed(opt_s)
    breakdown_inc = {k: breakdown_opt[k] - breakdown_base.get(k, 0.0) for k in breakdown_opt.keys()}

    return {
        "capex_incremental_nzd": inc,
        "breakdown_incremental_nzd": breakdown_inc,
        "baseline_total_nzd": base_total["capex_total_nzd"],
        "option_total_nzd": opt_total["capex_total_nzd"],
    }

def calculate_scenario(s: dict, coeffs: dict) -> dict:
    space = calculate_space_heating(s)
    water_use = calculate_water_enduse(s)
    water_heat = calculate_water_heating_from_enduse(s, water_use["enduse_L_y"])
    lighting = calculate_lighting(s)

    total_electricity_kwh_y = space["Q_purchased_kwh_y"] + water_heat["Q_purchased_kwh_y"] + lighting["Q_total_kwh_y"]
    carbon = calculate_operational_carbon(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    opex = calculate_opex(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    energy_intensity = (total_electricity_kwh_y / s["floorArea"]) if s["floorArea"] > 0 else 0.0

    cap_totals = compute_capex_totals(s)
    cap_detail = compute_capex_breakdown_detailed(s)

    return {
        "spaceHeating": space,
        "waterConsumption": water_use,
        "waterHeating": water_heat,
        "lighting": lighting,
        "totalElectricity_kwh_y": total_electricity_kwh_y,
        "energyIntensity_kwh_m2_y": energy_intensity,
        "carbon": carbon,
        "opex": opex,
        "capex": cap_totals,
        "capex_detail": cap_detail,
    }

# =============================================================================
# CHARTS (ALL VERTICAL BAR CHARTS)
# =============================================================================
def fig_bar_components_single(df: pd.DataFrame, title: str, y_label: str):
    # df columns: Component, Value
    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar(df["Component"], df["Value"])
    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.set_xlabel("")
    ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    return fig

def fig_bar_components_compare(df: pd.DataFrame, title: str, y_label: str):
    # df columns: Component, Baseline, Option
    components = df["Component"].tolist()
    b = df["Baseline"].tolist()
    o = df["Option"].tolist()

    x = list(range(len(components)))
    w = 0.4

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar([i - w/2 for i in x], b, width=w, label="Baseline")
    ax.bar([i + w/2 for i in x], o, width=w, label="Option")

    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.set_xlabel("")
    ax.set_xticks(x)
    ax.set_xticklabels(components, rotation=35, ha="right")
    ax.legend()
    fig.tight_layout()
    return fig

def fig_kpi_compare_vertical(df_kpi: pd.DataFrame, title: str):
    # df_kpi columns: Metric, Baseline, Option
    metrics = df_kpi["Metric"].tolist()
    b = df_kpi["Baseline"].tolist()
    o = df_kpi["Option"].tolist()

    x = list(range(len(metrics)))
    w = 0.4

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar([i - w/2 for i in x], b, width=w, label="Baseline")
    ax.bar([i + w/2 for i in x], o, width=w, label="Option")

    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_xticks(x)
    ax.set_xticklabels(metrics, rotation=35, ha="right")
    ax.legend()
    fig.tight_layout()
    return fig

# =============================================================================
# STATE / DEFAULTS
# =============================================================================
def init_defaults():
    st.session_state.setdefault("baseline_calculated", False)
    st.session_state.setdefault("option_calculated", False)
    st.session_state.setdefault("baseline_payload", None)
    st.session_state.setdefault("option_payload", None)

    # Scenario-specific defaults
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", float(LOOKUP["constants"]["ceiling_height_m_default"]))
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        st.session_state.setdefault(f"{p}_closestCity", PLACEHOLDER)
        st.session_state.setdefault(f"{p}_use_custom_hdd", False)
        st.session_state.setdefault(f"{p}_hdd_override_value", 2000.0)

        # Lighting defaults are fine
        st.session_state.setdefault(f"{p}_light_n", LOOKUP["defaults"]["lighting"]["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LOOKUP["defaults"]["lighting"]["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LOOKUP["defaults"]["lighting"]["hoursPerDay"])

        # Appliances: default to "No" (explicit choice is still visible)
        st.session_state.setdefault(f"{p}_wash_has", "No")
        st.session_state.setdefault(f"{p}_wash_cycles", LOOKUP["defaults"]["washing_machine"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", LOOKUP["defaults"]["washing_machine"]["waterPerCycle_L"])
        st.session_state.setdefault(f"{p}_dish_has", "No")
        st.session_state.setdefault(f"{p}_dish_cycles", LOOKUP["defaults"]["dishwasher"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", LOOKUP["defaults"]["dishwasher"]["waterPerCycle_L"])

        # IMPORTANT: All select labels default to PLACEHOLDER so fixtures are blank
        for k in [
            "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
            "spaceHeatingSystem", "waterHeatingSystem",
            "toiletType", "showerType", "tapType",
        ]:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

        # Custom perf + costs (only used if user chooses Custom)
        st.session_state.setdefault(f"{p}_roofR_custom", 6.6)
        st.session_state.setdefault(f"{p}_roofCost_custom", 25.0)
        st.session_state.setdefault(f"{p}_wallR_custom", 2.0)
        st.session_state.setdefault(f"{p}_wallCost_custom", 45.0)
        st.session_state.setdefault(f"{p}_floorR_custom", 2.0)
        st.session_state.setdefault(f"{p}_floorCost_custom", 40.0)

        st.session_state.setdefault(f"{p}_windowU_custom", 3.0)
        st.session_state.setdefault(f"{p}_windowCost_custom", 600.0)

        st.session_state.setdefault(f"{p}_spaceCOP_custom", 2.5)
        st.session_state.setdefault(f"{p}_spaceInstall_custom", 4500.0)
        st.session_state.setdefault(f"{p}_waterCOP_custom", 2.0)
        st.session_state.setdefault(f"{p}_waterInstall_custom", 6500.0)

        st.session_state.setdefault(f"{p}_toilet_value_custom", 5.0)
        st.session_state.setdefault(f"{p}_toilet_cost_custom", 450.0)
        st.session_state.setdefault(f"{p}_shower_value_custom", 7.0)
        st.session_state.setdefault(f"{p}_shower_cost_custom", 120.0)
        st.session_state.setdefault(f"{p}_tap_value_custom", 6.0)
        st.session_state.setdefault(f"{p}_tap_cost_custom", 150.0)

        du = LOOKUP["defaults"]["usage"]
        st.session_state.setdefault(f"{p}_hotWater_setpoint_C", float(du["hotWater_setpoint_C"]))
        st.session_state.setdefault(f"{p}_coldWater_inlet_C", float(du["coldWater_inlet_C"]))
        st.session_state.setdefault(f"{p}_toiletFlushes_ppd", float(du["toiletFlushes_per_person_day"]))
        st.session_state.setdefault(f"{p}_showers_ppd", float(du["showers_per_person_day"]))
        st.session_state.setdefault(f"{p}_minutes_per_shower", float(du["minutes_per_shower"]))
        st.session_state.setdefault(f"{p}_tapMinutes_ppd", float(du["tapMinutes_per_person_day"]))

        # Tariffs + factors per scenario
        st.session_state.setdefault(f"{p}_elec_tariff", float(LOOKUP["constants"]["electricity_tariff_nzd_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_water_tariff", float(LOOKUP["constants"]["water_tariff_nzd_per_m3_default"]))
        st.session_state.setdefault(f"{p}_grid_ef", float(LOOKUP["constants"]["grid_emission_factor_kgco2e_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_water_ef", float(LOOKUP["constants"]["water_emission_factor_kgco2e_per_m3_default"]))

def get_coeffs(prefix: str) -> dict:
    return {
        "grid_ef": float(st.session_state[f"{prefix}_grid_ef"]),
        "water_ef": float(st.session_state[f"{prefix}_water_ef"]),
        "elec_tariff": float(st.session_state[f"{prefix}_elec_tariff"]),
        "water_tariff": float(st.session_state[f"{prefix}_water_tariff"]),
    }

def resolve_hdd(prefix: str) -> float | None:
    city = st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER)
    if city == PLACEHOLDER:
        return None
    use_custom = bool(st.session_state.get(f"{prefix}_use_custom_hdd", False))
    if use_custom:
        return _clamp(float(st.session_state.get(f"{prefix}_hdd_override_value", 2000.0)), 0.0, 6000.0)
    zone = LOOKUP["climate"]["zone_by_city"].get(city, None)
    if zone is None:
        return None
    return float(LOOKUP["climate"]["hdd_by_zone_base18"][zone])

def copy_baseline_to_option():
    keys = [k for k in st.session_state.keys() if k.startswith("b_")]
    for k in keys:
        st.session_state["o_" + k[2:]] = copy.deepcopy(st.session_state[k])
    st.session_state["option_calculated"] = False
    st.session_state["option_payload"] = None

# =============================================================================
# SCENARIO BUILD / VALIDATION
# =============================================================================
def get_scenario(prefix: str) -> dict:
    city = st.session_state[f"{prefix}_closestCity"]
    closest_city = None if city == PLACEHOLDER else city
    HDD = resolve_hdd(prefix)

    roof_label = st.session_state[f"{prefix}_roofRLabel"]
    wall_label = st.session_state[f"{prefix}_wallRLabel"]
    floor_label = st.session_state[f"{prefix}_floorRLabel"]
    win_label = st.session_state[f"{prefix}_windowULabel"]

    space_sys = st.session_state[f"{prefix}_spaceHeatingSystem"]
    water_sys = st.session_state[f"{prefix}_waterHeatingSystem"]

    toilet = st.session_state[f"{prefix}_toiletType"]
    shower = st.session_state[f"{prefix}_showerType"]
    tap = st.session_state[f"{prefix}_tapType"]

    wash_has = _yn_to_bool(st.session_state[f"{prefix}_wash_has"])
    dish_has = _yn_to_bool(st.session_state[f"{prefix}_dish_has"])

    scenario = {
        "closestCity": closest_city,
        "HDD_base18": HDD,

        "floorArea": float(st.session_state[f"{prefix}_floorArea"]),
        "ceilingHeight": float(st.session_state[f"{prefix}_ceilingHeight"]),
        "householdSize": int(st.session_state[f"{prefix}_householdSize"]),
        "windowArea": float(st.session_state[f"{prefix}_windowArea"]),

        "roofRValue": resolve_from_lookup_or_custom(roof_label, f"{prefix}_roofR_custom", LOOKUP["thermal_envelope"]["roofR_m2K_per_W"]),
        "wallRValue": resolve_from_lookup_or_custom(wall_label, f"{prefix}_wallR_custom", LOOKUP["thermal_envelope"]["wallR_m2K_per_W"]),
        "floorRValue": resolve_from_lookup_or_custom(floor_label, f"{prefix}_floorR_custom", LOOKUP["thermal_envelope"]["floorR_m2K_per_W"]),
        "windowUValue": resolve_from_lookup_or_custom(win_label, f"{prefix}_windowU_custom", LOOKUP["thermal_envelope"]["windowU_W_per_m2K"]),

        "spaceHeatingCOP": resolve_cop(space_sys, f"{prefix}_spaceCOP_custom", "space_heating"),
        "waterHeatingCOP": resolve_cop(water_sys, f"{prefix}_waterCOP_custom", "water_heating"),

        "toilet_L_per_flush": resolve_fixture_value(toilet, "toilet", f"{prefix}_toilet_value_custom"),
        "shower_L_per_min": resolve_fixture_value(shower, "shower", f"{prefix}_shower_value_custom"),
        "tap_L_per_min": resolve_fixture_value(tap, "tap", f"{prefix}_tap_value_custom"),

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
            "hotWater_setpoint_C": float(st.session_state[f"{prefix}_hotWater_setpoint_C"]),
            "coldWater_inlet_C": float(st.session_state[f"{prefix}_coldWater_inlet_C"]),
            "toiletFlushes_per_person_day": float(st.session_state[f"{prefix}_toiletFlushes_ppd"]),
            "showers_per_person_day": float(st.session_state[f"{prefix}_showers_ppd"]),
            "minutes_per_shower": float(st.session_state[f"{prefix}_minutes_per_shower"]),
            "tapMinutes_per_person_day": float(st.session_state[f"{prefix}_tapMinutes_ppd"]),
        },

        "capex": {
            "roof_nzd_per_m2": resolve_capex_envelope("roof", roof_label, f"{prefix}_roofCost_custom"),
            "wall_nzd_per_m2": resolve_capex_envelope("wall", wall_label, f"{prefix}_wallCost_custom"),
            "floor_nzd_per_m2": resolve_capex_envelope("floor", floor_label, f"{prefix}_floorCost_custom"),
            "window_nzd_per_m2_window": resolve_capex_window(win_label, f"{prefix}_windowCost_custom"),

            "space_heating_install_nzd": resolve_install_cost(space_sys, f"{prefix}_spaceInstall_custom", "space_heating"),
            "water_heating_install_nzd": resolve_install_cost(water_sys, f"{prefix}_waterInstall_custom", "water_heating"),

            "toilet_install_nzd": resolve_fixture_cost(toilet, "toilet", f"{prefix}_toilet_cost_custom"),
            "shower_install_nzd": resolve_fixture_cost(shower, "shower", f"{prefix}_shower_cost_custom"),
            "tap_install_nzd": resolve_fixture_cost(tap, "tap", f"{prefix}_tap_cost_custom"),
        },

        "_labels": {
            "roof": roof_label, "wall": wall_label, "floor": floor_label, "window": win_label,
            "spaceHeatingSystem": space_sys, "waterHeatingSystem": water_sys,
            "toilet": toilet, "shower": shower, "tap": tap,
            "use_custom_hdd": bool(st.session_state.get(f"{prefix}_use_custom_hdd", False)),
        }
    }
    return scenario

def validate_scenario(s: dict) -> list:
    missing = []
    if s["closestCity"] is None:
        missing.append("Closest city")
    if s["HDD_base18"] is None:
        missing.append("HDD")

    for k, label in [
        ("roofRValue", "Roof insulation (R-value)"),
        ("wallRValue", "Wall insulation (R-value)"),
        ("floorRValue", "Floor insulation (R-value)"),
        ("windowUValue", "Window type (U-value)"),
        ("spaceHeatingCOP", "Space heating system (COP)"),
        ("waterHeatingCOP", "Water heating system (COP)"),
        ("toilet_L_per_flush", "Toilet type (L/flush)"),
        ("shower_L_per_min", "Shower type (L/min)"),
        ("tap_L_per_min", "Tap type (L/min)"),
    ]:
        if s[k] is None:
            missing.append(label)

    if s["washingMachine"]["hasAppliance"] is None:
        missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None:
        missing.append("Dishwasher (Yes/No)")
    return missing

# =============================================================================
# INPUT UI (SINGLE PAGE 3×2 GRID)
# =============================================================================
CITIES = sorted(list(LOOKUP["climate"]["zone_by_city"].keys()))
ROOF_OPTS = list(LOOKUP["thermal_envelope"]["roofR_m2K_per_W"].keys()) + ["Custom"]
WALL_OPTS = list(LOOKUP["thermal_envelope"]["wallR_m2K_per_W"].keys()) + ["Custom"]
FLOOR_OPTS = list(LOOKUP["thermal_envelope"]["floorR_m2K_per_W"].keys()) + ["Custom"]
WIN_OPTS = list(LOOKUP["thermal_envelope"]["windowU_W_per_m2K"].keys()) + ["Custom"]

SPACE_SYS_OPTS = list(LOOKUP["systems"]["space_heating"]["cop"].keys()) + ["Custom"]
WATER_SYS_OPTS = list(LOOKUP["systems"]["water_heating"]["cop"].keys()) + ["Custom"]

TOILET_OPTS = list(LOOKUP["fixtures"]["toilet"]["l_per_flush"].keys()) + ["Custom"]
SHOWER_OPTS = list(LOOKUP["fixtures"]["shower"]["l_per_min"].keys()) + ["Custom"]
TAP_OPTS = list(LOOKUP["fixtures"]["tap"]["l_per_min"].keys()) + ["Custom"]

def core_inputs_block(prefix: str):
    st.markdown("### Core")
    select_with_placeholder("Closest city", CITIES, key=f"{prefix}_closestCity")

    city = st.session_state[f"{prefix}_closestCity"]
    if city != PLACEHOLDER:
        z = LOOKUP["climate"]["zone_by_city"][city]
        h_default = LOOKUP["climate"]["hdd_by_zone_base18"][z]
        st.caption(f"Climate zone: **{z}** | Default HDD (base 18°C): **{h_default}**")

        st.checkbox("Use custom HDD input", key=f"{prefix}_use_custom_hdd")
        if st.session_state[f"{prefix}_use_custom_hdd"]:
            st.number_input("Custom HDD (base 18°C)", min_value=0.0, max_value=6000.0, step=50.0, key=f"{prefix}_hdd_override_value")

    st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea")
    st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight")
    st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize")
    st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea")

def envelope_block(prefix: str):
    st.markdown("### Envelope")

    def _r_item(name, label_key, options, perf_lookup, perf_custom_key, cost_custom_key, cap_element):
        select_with_placeholder(name, options, key=label_key)
        label = st.session_state[label_key]

        if label == "Custom":
            st.number_input("Custom performance", min_value=0.1, max_value=20.0, step=0.1, key=perf_custom_key)
            st.number_input("Custom cost (NZD/m²)", min_value=0.0, max_value=5000.0, step=10.0, key=cost_custom_key)

        if label != PLACEHOLDER:
            perf = resolve_from_lookup_or_custom(label, perf_custom_key, perf_lookup)
            if cap_element == "window":
                cost = resolve_capex_window(label, cost_custom_key)
                show_selected_line(label, perf=f"U = {fmt_num(perf,2)} W/m²K", cost=f"{fmt_num(cost,0)} NZD/m²")
            else:
                cost = resolve_capex_envelope(cap_element, label, cost_custom_key)
                show_selected_line(label, perf=f"R = {fmt_num(perf,2)} m²K/W", cost=f"{fmt_num(cost,0)} NZD/m²")

    _r_item("Roof insulation (R-value)", f"{prefix}_roofRLabel", ROOF_OPTS,
            LOOKUP["thermal_envelope"]["roofR_m2K_per_W"], f"{prefix}_roofR_custom", f"{prefix}_roofCost_custom", "roof")
    _r_item("Wall insulation (R-value)", f"{prefix}_wallRLabel", WALL_OPTS,
            LOOKUP["thermal_envelope"]["wallR_m2K_per_W"], f"{prefix}_wallR_custom", f"{prefix}_wallCost_custom", "wall")
    _r_item("Floor insulation (R-value)", f"{prefix}_floorRLabel", FLOOR_OPTS,
            LOOKUP["thermal_envelope"]["floorR_m2K_per_W"], f"{prefix}_floorR_custom", f"{prefix}_floorCost_custom", "floor")
    _r_item("Window type (U-value)", f"{prefix}_windowULabel", WIN_OPTS,
            LOOKUP["thermal_envelope"]["windowU_W_per_m2K"], f"{prefix}_windowU_custom", f"{prefix}_windowCost_custom", "window")

def systems_block(prefix: str):
    st.markdown("### Systems")

    def _sys_item(title, label_key, options, sys_block, cop_custom_key, cost_custom_key):
        select_with_placeholder(title, options, key=label_key)
        label = st.session_state[label_key]

        if label == "Custom":
            st.number_input("Custom COP", min_value=0.0, max_value=10.0, step=0.1, key=cop_custom_key)
            st.number_input("Custom install cost (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=cost_custom_key)

        if label != PLACEHOLDER:
            cop = resolve_cop(label, cop_custom_key, sys_block)
            cost = resolve_install_cost(label, cost_custom_key, sys_block)
            show_selected_line(label, perf=f"COP = {fmt_num(cop,2)}", cost=f"{fmt_num(cost,0)} NZD")

    _sys_item("Space heating system", f"{prefix}_spaceHeatingSystem", SPACE_SYS_OPTS, "space_heating",
              f"{prefix}_spaceCOP_custom", f"{prefix}_spaceInstall_custom")
    _sys_item("Water heating system", f"{prefix}_waterHeatingSystem", WATER_SYS_OPTS, "water_heating",
              f"{prefix}_waterCOP_custom", f"{prefix}_waterInstall_custom")

def fixtures_block(prefix: str):
    st.markdown("### Fixtures")

    def _fix_item(title, label_key, options, kind, val_custom_key, cost_custom_key, unit_label):
        select_with_placeholder(title, options, key=label_key)
        label = st.session_state[label_key]

        if label == "Custom":
            st.number_input(f"Custom {unit_label}", min_value=1.0, max_value=30.0, step=0.5, key=val_custom_key)
            st.number_input("Custom install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=cost_custom_key)

        if label != PLACEHOLDER:
            v = resolve_fixture_value(label, kind, val_custom_key)
            c = resolve_fixture_cost(label, kind, cost_custom_key)
            show_selected_line(label, perf=f"{fmt_num(v,1)} {unit_label}", cost=f"{fmt_num(c,0)} NZD")

    _fix_item("Toilet type", f"{prefix}_toiletType", TOILET_OPTS, "toilet",
              f"{prefix}_toilet_value_custom", f"{prefix}_toilet_cost_custom", "L/flush")
    _fix_item("Shower type", f"{prefix}_showerType", SHOWER_OPTS, "shower",
              f"{prefix}_shower_value_custom", f"{prefix}_shower_cost_custom", "L/min")
    _fix_item("Tap type", f"{prefix}_tapType", TAP_OPTS, "tap",
              f"{prefix}_tap_value_custom", f"{prefix}_tap_cost_custom", "L/min")

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

def lighting_block(prefix: str):
    st.markdown("### Lighting")
    st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n")
    st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts")
    st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours")

def usage_and_tariffs_block(prefix: str):
    st.markdown("### Usage + Tariffs/Facts")

    st.markdown("**Usage assumptions**")
    st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
    st.number_input("Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")
    st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
    st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
    st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
    st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

    st.markdown("**Tariffs + emission factors (scenario-specific)**")
    st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_elec_tariff")
    st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_water_tariff")
    st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_grid_ef")
    st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_water_ef")

def scenario_inputs_grid(prefix: str, title: str):
    st.subheader(title)

    r1c1, r1c2, r1c3 = st.columns(3, gap="large")
    r2c1, r2c2, r2c3 = st.columns(3, gap="large")

    with r1c1:
        core_inputs_block(prefix)
    with r1c2:
        envelope_block(prefix)
    with r1c3:
        systems_block(prefix)

    with r2c1:
        fixtures_block(prefix)
    with r2c2:
        lighting_block(prefix)
    with r2c3:
        usage_and_tariffs_block(prefix)

# =============================================================================
# KPI TABLES
# =============================================================================
def kpi_table_baseline(base_r: dict) -> pd.DataFrame:
    rows = [
        ("Total Energy (excl. plug loads)", base_r["totalElectricity_kwh_y"], "kWh/year", 1),
        ("Energy Intensity", base_r["energyIntensity_kwh_m2_y"], "kWh/m²/year", 2),
        ("Water Consumption", base_r["waterConsumption"]["V_total_m3_y"], "m³/year", 2),
        ("Operational Carbon", base_r["carbon"]["CO2_total_kg_y"], "kgCO₂e/year", 1),
        ("Annual Operating Cost (Opex)", base_r["opex"]["opex_total_nzd_y"], "NZD/year", 0),
        ("Total Capex (scenario)", base_r["capex"]["capex_total_nzd"], "NZD", 0),
    ]
    out = []
    for m, v, u, d in rows:
        out.append({"Metric": m, "Value": fmt_num(v, d), "Unit": u})
    return pd.DataFrame(out)

def kpi_table_compare(base_r: dict, opt_r: dict, capex_inc: dict | None) -> pd.DataFrame:
    rows = [
        ("Total Energy (excl. plug loads)", base_r["totalElectricity_kwh_y"], opt_r["totalElectricity_kwh_y"], "kWh/year", 1),
        ("Energy Intensity", base_r["energyIntensity_kwh_m2_y"], opt_r["energyIntensity_kwh_m2_y"], "kWh/m²/year", 2),
        ("Water Consumption", base_r["waterConsumption"]["V_total_m3_y"], opt_r["waterConsumption"]["V_total_m3_y"], "m³/year", 2),
        ("Operational Carbon", base_r["carbon"]["CO2_total_kg_y"], opt_r["carbon"]["CO2_total_kg_y"], "kgCO₂e/year", 1),
        ("Annual Operating Cost (Opex)", base_r["opex"]["opex_total_nzd_y"], opt_r["opex"]["opex_total_nzd_y"], "NZD/year", 0),
        ("Total Capex (scenario)", base_r["capex"]["capex_total_nzd"], opt_r["capex"]["capex_total_nzd"], "NZD", 0),
    ]

    out = []
    for m, b, o, u, d in rows:
        delta = o - b
        out.append({
            "Metric": m,
            "Baseline": fmt_num(b, d),
            "Option": fmt_num(o, d),
            "Δ (Option−Base)": fmt_num(delta, d),
            "Dir": direction_arrow(delta),
            "Unit": u,
        })

    # Payback row (still uses incremental capex)
    if capex_inc is not None:
        savings = base_r["opex"]["opex_total_nzd_y"] - opt_r["opex"]["opex_total_nzd_y"]
        inc = capex_inc["capex_incremental_nzd"]
        if inc <= 0:
            pb = 0.0
            note = "No additional capex"
        elif savings <= 0:
            pb = None
            note = "No payback (savings ≤ 0)"
        else:
            pb = inc / savings
            note = ""

        out.append({
            "Metric": "Simple Payback",
            "Baseline": "—",
            "Option": "—" if pb is None else fmt_num(pb, 1),
            "Δ (Option−Base)": "—",
            "Dir": "—",
            "Unit": "years",
        })
        if note:
            out.append({
                "Metric": "Payback note",
                "Baseline": note,
                "Option": "",
                "Δ (Option−Base)": "",
                "Dir": "",
                "Unit": "",
            })

    return pd.DataFrame(out)

# =============================================================================
# APP
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.caption("Early-stage comparison tool. Simplified, indicative, non-certification.")

# ---- BASELINE (Step 1)
st.divider()
st.markdown("## Step 1 — Baseline")
scenario_inputs_grid("b", "Baseline inputs")

baseline_now = get_scenario("b")
missing_b = validate_scenario(baseline_now)

b_actions = st.columns([1, 1, 3])
with b_actions[0]:
    calc_b = st.button("Calculate Baseline", type="primary", use_container_width=True)
with b_actions[1]:
    reset_all = st.button("Reset Calculations", use_container_width=True)

if reset_all:
    st.session_state["baseline_calculated"] = False
    st.session_state["option_calculated"] = False
    st.session_state["baseline_payload"] = None
    st.session_state["option_payload"] = None
    st.rerun()

if calc_b:
    if missing_b:
        st.error("Baseline incomplete. Missing: " + ", ".join(missing_b))
    else:
        coeffs_b = get_coeffs("b")
        base_r = calculate_scenario(baseline_now, coeffs_b)
        st.session_state["baseline_calculated"] = True
        st.session_state["baseline_payload"] = {
            "inputs": baseline_now,
            "coeffs": coeffs_b,
            "results": base_r,
            "missing": [],
        }
        # Recalculate option after baseline changes
        st.session_state["option_calculated"] = False
        st.session_state["option_payload"] = None
        st.rerun()

# Show baseline results only after calculate
if st.session_state["baseline_calculated"]:
    base_payload = st.session_state["baseline_payload"]
    base_r = base_payload["results"]

    st.markdown("### Baseline results")
    st.dataframe(kpi_table_baseline(base_r), use_container_width=True, hide_index=True)

    # Baseline charts (vertical bars)
    df_energy_b = pd.DataFrame([
        {"Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
        {"Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
        {"Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
    ])
    df_water_b = pd.DataFrame([{"Component": k, "Value": v} for k, v in base_r["waterConsumption"]["breakdown_m3_y"].items()])
    df_carbon_b = pd.DataFrame([
        {"Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
        {"Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
    ])
    df_opex_b = pd.DataFrame([
        {"Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
        {"Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
    ])
    df_capex_b = pd.DataFrame([{"Component": k, "Value": v} for k, v in base_r["capex_detail"].items()])

    row1 = st.columns(2, gap="large")
    with row1[0]:
        st.pyplot(fig_bar_components_single(df_energy_b, "Baseline energy breakdown", "kWh/year"))
    with row1[1]:
        st.pyplot(fig_bar_components_single(df_water_b, "Baseline indoor water breakdown", "m³/year"))

    row2 = st.columns(2, gap="large")
    with row2[0]:
        st.pyplot(fig_bar_components_single(df_carbon_b, "Baseline operational carbon breakdown", "kgCO₂e/year"))
    with row2[1]:
        st.pyplot(fig_bar_components_single(df_opex_b, "Baseline opex breakdown", "NZD/year"))

    st.pyplot(fig_bar_components_single(df_capex_b, "Baseline capex breakdown (detailed)", "NZD"))

# ---- OPTION (Step 2) unlocked only after baseline calculated
st.divider()
st.markdown("## Step 2 — Option")
if not st.session_state["baseline_calculated"]:
    st.info("Calculate **Baseline** first to unlock Option inputs and comparison.")
    st.stop()

opt_actions = st.columns([1, 1, 3])
with opt_actions[0]:
    if st.button("Copy Baseline → Option", use_container_width=True):
        copy_baseline_to_option()
        st.rerun()

scenario_inputs_grid("o", "Option inputs")

option_now = get_scenario("o")
missing_o = validate_scenario(option_now)

opt_actions2 = st.columns([1, 3])
with opt_actions2[0]:
    calc_o = st.button("Calculate Option & Compare", type="primary", use_container_width=True)

if calc_o:
    if missing_o:
        st.error("Option incomplete. Missing: " + ", ".join(missing_o))
    else:
        base_payload = st.session_state["baseline_payload"]
        base_inputs = base_payload["inputs"]
        base_r = base_payload["results"]

        coeffs_o = get_coeffs("o")
        opt_r = calculate_scenario(option_now, coeffs_o)

        capex_inc = calculate_incremental_capex(base_inputs, option_now)

        st.session_state["option_calculated"] = True
        st.session_state["option_payload"] = {
            "inputs": option_now,
            "coeffs": coeffs_o,
            "results": opt_r,
            "missing": [],
            "capex_inc": capex_inc,
        }
        st.rerun()

# Show comparison only after option calculated
if st.session_state["option_calculated"]:
    base_inputs = st.session_state["baseline_payload"]["inputs"]
    base_r = st.session_state["baseline_payload"]["results"]
    coeffs_b = st.session_state["baseline_payload"]["coeffs"]

    opt_payload = st.session_state["option_payload"]
    opt_inputs = opt_payload["inputs"]
    opt_r = opt_payload["results"]
    coeffs_o = opt_payload["coeffs"]
    capex_inc = opt_payload["capex_inc"]

    st.markdown("### Comparison (Baseline vs Option)")
    st.dataframe(kpi_table_compare(base_r, opt_r, capex_inc), use_container_width=True, hide_index=True)

    # KPI compare chart (vertical)
    df_kpi = pd.DataFrame([
        {"Metric": "Energy (kWh/y)", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
        {"Metric": "Intensity (kWh/m²/y)", "Baseline": base_r["energyIntensity_kwh_m2_y"], "Option": opt_r["energyIntensity_kwh_m2_y"]},
        {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
        {"Metric": "Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
        {"Metric": "Opex (NZD/y)", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
        {"Metric": "Capex (NZD)", "Baseline": base_r["capex"]["capex_total_nzd"], "Option": opt_r["capex"]["capex_total_nzd"]},
    ])

    # Component compare charts (vertical)
    df_energy = pd.DataFrame([
        {"Component": "Space Heating", "Baseline": base_r["spaceHeating"]["Q_purchased_kwh_y"], "Option": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
        {"Component": "Water Heating", "Baseline": base_r["waterHeating"]["Q_purchased_kwh_y"], "Option": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
        {"Component": "Lighting", "Baseline": base_r["lighting"]["Q_total_kwh_y"], "Option": opt_r["lighting"]["Q_total_kwh_y"]},
    ])

    # Preserve consistent ordering for water breakdown
    water_components = list(base_r["waterConsumption"]["breakdown_m3_y"].keys())
    df_water = pd.DataFrame([
        {"Component": k,
         "Baseline": base_r["waterConsumption"]["breakdown_m3_y"][k],
         "Option": opt_r["waterConsumption"]["breakdown_m3_y"].get(k, 0.0)}
        for k in water_components
    ])

    df_carbon = pd.DataFrame([
        {"Component": "Electricity", "Baseline": base_r["carbon"]["CO2_electricity_kg_y"], "Option": opt_r["carbon"]["CO2_electricity_kg_y"]},
        {"Component": "Water", "Baseline": base_r["carbon"]["CO2_water_kg_y"], "Option": opt_r["carbon"]["CO2_water_kg_y"]},
    ])

    df_opex = pd.DataFrame([
        {"Component": "Electricity", "Baseline": base_r["opex"]["opex_electricity_nzd_y"], "Option": opt_r["opex"]["opex_electricity_nzd_y"]},
        {"Component": "Water", "Baseline": base_r["opex"]["opex_water_nzd_y"], "Option": opt_r["opex"]["opex_water_nzd_y"]},
    ])

    # Capex compare (NOT incremental): baseline vs option across all aspects
    cap_components = list(base_r["capex_detail"].keys())
    df_capex = pd.DataFrame([
        {"Component": k,
         "Baseline": base_r["capex_detail"][k],
         "Option": opt_r["capex_detail"].get(k, 0.0)}
        for k in cap_components
    ])

    row1 = st.columns(2, gap="large")
    with row1[0]:
        st.pyplot(fig_kpi_compare_vertical(df_kpi, "KPIs: Baseline vs Option"))
    with row1[1]:
        st.pyplot(fig_bar_components_compare(df_energy, "Energy breakdown (Baseline vs Option)", "kWh/year"))

    row2 = st.columns(2, gap="large")
    with row2[0]:
        st.pyplot(fig_bar_components_compare(df_water, "Indoor water breakdown (Baseline vs Option)", "m³/year"))
    with row2[1]:
        st.pyplot(fig_bar_components_compare(df_carbon, "Operational carbon breakdown (Baseline vs Option)", "kgCO₂e/year"))

    row3 = st.columns(2, gap="large")
    with row3[0]:
        st.pyplot(fig_bar_components_compare(df_opex, "Opex breakdown (Baseline vs Option)", "NZD/year"))
    with row3[1]:
        st.pyplot(fig_bar_components_compare(df_capex, "Capex breakdown (Baseline vs Option)", "NZD"))

    # Download JSON
    payload = {
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "baseline": {"inputs": base_inputs, "coefficients": coeffs_b, "results": base_r},
        "option": {"inputs": opt_inputs, "coefficients": coeffs_o, "results": opt_r},
        "capex_incremental": capex_inc,
        "notes": {
            "scope": "Early-stage decision support; not certification; not simulation.",
            "energy_boundary": "Space heating + water heating + lighting (excludes plug loads/appliances).",
            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
            "capex_boundary": "Transparent unit-cost accounting. Not investment-grade.",
            "hot_water_model": "Hot water derived from end-use volumes using hot water fractions (toilet excluded).",
            "scenario_specific_tariffs_factors": "Tariffs and emission factors are stored per scenario.",
        },
    }

    st.divider()
    st.download_button(
        "Download results (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"housing-sustainability-comparison-{int(datetime.utcnow().timestamp())}.json",
        mime="application/json",
        use_container_width=True,
    )
else:
    st.info("Fill Option inputs, then click **Calculate Option & Compare** to see the comparison.")
