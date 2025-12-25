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
        "grid_emission_factor_kgco2e_per_kwh": 0.0729,  # MfE (2024) 2023 grid-average
        "water_emission_factor_kgco2e_per_m3": 0.0349,  # MfE (2024)
        "electricity_tariff_nzd_per_kwh_default": 0.312,  # Elec Authority (2024) representative
        "water_tariff_nzd_per_m3_default": 2.296,  # Auckland Council (2025) representative
        "ceiling_height_m_default": 2.4,
        "cp_kj_per_kgC": 4.186,
    },

    "thermal_envelope": {
        "floorR_m2K_per_W": {"Uninsulated": 0.6, "Basic": 1.5, "Code minimum": 2.0, "Good": 2.8, "Excellent": 3.5},
        "roofR_m2K_per_W": {"Uninsulated": 0.5, "Basic": 3.0, "Code minimum": 6.6, "Good": 8.0, "Excellent": 10.0},
        "wallR_m2K_per_W": {"Uninsulated": 0.5, "Basic": 1.5, "Code minimum": 2.0, "Good": 3.0, "Excellent": 4.0},
        "windowU_W_per_m2K": {
            "Single glazed": 5.8,
            "Standard double glazed": 3.0,
            "Low-E double glazed": 2.0,
            "High-performance triple glazed": 1.0,
        },
        # Capex schedules (early-stage)
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
            "l_per_flush": {"Single flush": 9, "Dual flush standard (avg 5 L)": 5, "Dual flush efficient (avg 4 L)": 4},
            "install_cost_nzd": {"Single flush": 300, "Dual flush standard (avg 5 L)": 450, "Dual flush efficient (avg 4 L)": 650},
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
def fmt_num(x: float | None, decimals: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}"

def fmt_money(x: float | None, decimals: int = 0) -> str:
    if x is None:
        return "—"
    return f"${x:,.{decimals}f}"

def direction_arrow(delta: float | None) -> str:
    if delta is None:
        return "—"
    if delta < 0:
        return "▼"
    if delta > 0:
        return "▲"
    return "—"

def _yn_to_bool(v: str | None):
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None

def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

def _bucket_from_label(label: str) -> str:
    for b in ["Uninsulated", "Basic", "Code minimum", "Good", "Excellent"]:
        if label == b:
            return b
    return "Uninsulated"

# =============================================================================
# CALCS
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
        "breakdown_W_per_K": {"Roof": H_roof, "Walls": H_wall, "Floor": H_floor, "Windows": H_window},
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
            "Toilets": V_toilet_L_y,
            "Showers": V_shower_L_y,
            "Taps": V_tap_L_y,
            "Laundry": V_laundry_L_y,
            "Dishwasher": V_dish_L_y,
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
        enduse_L_y["Showers"] * fr["shower"]
        + enduse_L_y["Taps"] * fr["tap"]
        + enduse_L_y["Laundry"] * fr["laundry"]
        + enduse_L_y["Dishwasher"] * fr["dishwasher"]
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

def compute_capex_total(s: dict) -> dict:
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

    return {
        "capex_total_nzd": total,
        "breakdown_nzd": {"Envelope": envelope, "Systems": systems, "Fixtures": fixtures},
        "detail_breakdown_nzd": {
            "Roof insulation": cap["roof_nzd_per_m2"] * areas["roof"],
            "Wall insulation": cap["wall_nzd_per_m2"] * areas["wall"],
            "Floor insulation": cap["floor_nzd_per_m2"] * areas["floor"],
            "Windows": cap["window_nzd_per_m2_window"] * areas["window"],
            "Space heating system": cap["space_heating_install_nzd"],
            "Water heating system": cap["water_heating_install_nzd"],
            "Toilet install": cap["toilet_install_nzd"],
            "Shower install": cap["shower_install_nzd"],
            "Tap install": cap["tap_install_nzd"],
        },
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
    capex = compute_capex_total(s)

    return {
        "spaceHeating": space,
        "waterConsumption": water_use,
        "waterHeating": water_heat,
        "lighting": lighting,
        "totalElectricity_kwh_y": total_electricity_kwh_y,
        "energyIntensity_kwh_m2_y": energy_intensity,
        "carbon": carbon,
        "opex": opex,
        "capex": capex,
    }

# =============================================================================
# CHARTS
# =============================================================================
def fig_grouped_bar_vertical(df: pd.DataFrame, title: str, y_label: str):
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    x = range(len(df))
    w = 0.38
    ax.bar([i - w/2 for i in x], df["Baseline"].values, width=w, label="Baseline")
    ax.bar([i + w/2 for i in x], df["Option"].values, width=w, label="Option")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["Metric"].tolist(), rotation=20, ha="right")
    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.legend()
    fig.tight_layout()
    return fig

def fig_stacked_bar_vertical(df: pd.DataFrame, title: str, y_label: str):
    pivot = df.pivot_table(index="Scenario", columns="Component", values="Value", aggfunc="sum").fillna(0)
    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    pivot.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(y_label)
    ax.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return fig

def fig_capex_compare(detail_b: dict, detail_o: dict):
    cats = list(detail_b.keys())
    b_vals = [detail_b[c] for c in cats]
    o_vals = [detail_o.get(c, 0.0) for c in cats]
    df = pd.DataFrame({"Category": cats, "Baseline": b_vals, "Option": o_vals})

    fig, ax = plt.subplots(figsize=(7.4, 4.2))
    x = range(len(df))
    w = 0.38
    ax.bar([i - w/2 for i in x], df["Baseline"].values, width=w, label="Baseline")
    ax.bar([i + w/2 for i in x], df["Option"].values, width=w, label="Option")
    ax.set_xticks(list(x))
    ax.set_xticklabels(df["Category"].tolist(), rotation=25, ha="right")
    ax.set_title("Capex breakdown comparison")
    ax.set_ylabel("NZD")
    ax.legend()
    fig.tight_layout()
    return fig

# =============================================================================
# STATE + INVALIDATION (fixes “option resets”)
# =============================================================================
def invalidate_baseline_only():
    st.session_state["baseline_calculated"] = False
    st.session_state["baseline_inputs_snapshot"] = None
    st.session_state["baseline_results"] = None
    # baseline change invalidates comparison
    st.session_state["option_calculated"] = False
    st.session_state["option_inputs_snapshot"] = None
    st.session_state["option_results"] = None

def invalidate_option_only():
    st.session_state["option_calculated"] = False
    st.session_state["option_inputs_snapshot"] = None
    st.session_state["option_results"] = None

def init_defaults():
    st.session_state.setdefault("baseline_calculated", False)
    st.session_state.setdefault("option_calculated", False)
    st.session_state.setdefault("baseline_inputs_snapshot", None)
    st.session_state.setdefault("option_inputs_snapshot", None)
    st.session_state.setdefault("baseline_results", None)
    st.session_state.setdefault("option_results", None)

    # per-scenario coefficients and inputs
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_coef_grid_ef", float(LOOKUP["constants"]["grid_emission_factor_kgco2e_per_kwh"]))
        st.session_state.setdefault(f"{p}_coef_water_ef", float(LOOKUP["constants"]["water_emission_factor_kgco2e_per_m3"]))
        st.session_state.setdefault(f"{p}_coef_elec_tariff", float(LOOKUP["constants"]["electricity_tariff_nzd_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_coef_water_tariff", float(LOOKUP["constants"]["water_tariff_nzd_per_m3_default"]))

        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", float(LOOKUP["constants"]["ceiling_height_m_default"]))
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        # lighting
        st.session_state.setdefault(f"{p}_light_n", LOOKUP["defaults"]["lighting"]["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LOOKUP["defaults"]["lighting"]["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LOOKUP["defaults"]["lighting"]["hoursPerDay"])

        # appliances default = No
        st.session_state.setdefault(f"{p}_wash_has", "No")
        st.session_state.setdefault(f"{p}_wash_cycles", LOOKUP["defaults"]["washing_machine"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", LOOKUP["defaults"]["washing_machine"]["waterPerCycle_L"])
        st.session_state.setdefault(f"{p}_dish_has", "No")
        st.session_state.setdefault(f"{p}_dish_cycles", LOOKUP["defaults"]["dishwasher"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", LOOKUP["defaults"]["dishwasher"]["waterPerCycle_L"])

        # climate
        st.session_state.setdefault(f"{p}_closestCity", PLACEHOLDER)
        st.session_state.setdefault(f"{p}_use_custom_hdd", False)
        st.session_state.setdefault(f"{p}_hdd_override_value", 2000.0)

        # custom performance + costs
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

        # usage assumptions
        du = LOOKUP["defaults"]["usage"]
        st.session_state.setdefault(f"{p}_hotWater_setpoint_C", float(du["hotWater_setpoint_C"]))
        st.session_state.setdefault(f"{p}_coldWater_inlet_C", float(du["coldWater_inlet_C"]))
        st.session_state.setdefault(f"{p}_toiletFlushes_ppd", float(du["toiletFlushes_per_person_day"]))
        st.session_state.setdefault(f"{p}_showers_ppd", float(du["showers_per_person_day"]))
        st.session_state.setdefault(f"{p}_minutes_per_shower", float(du["minutes_per_shower"]))
        st.session_state.setdefault(f"{p}_tapMinutes_ppd", float(du["tapMinutes_per_person_day"]))

    # categorical defaults
    cat_keys = [
        "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "spaceHeatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

init_defaults()

def get_coeffs(prefix: str) -> dict:
    return {
        "grid_ef": float(st.session_state[f"{prefix}_coef_grid_ef"]),
        "water_ef": float(st.session_state[f"{prefix}_coef_water_ef"]),
        "elec_tariff": float(st.session_state[f"{prefix}_coef_elec_tariff"]),
        "water_tariff": float(st.session_state[f"{prefix}_coef_water_tariff"]),
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

# =============================================================================
# RESOLVERS (no perf/price in dropdown; show captions under selection)
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
        if kind == "toilet":
            return float(LOOKUP["fixtures"][kind]["l_per_flush"][label])
        return float(LOOKUP["fixtures"][kind]["l_per_min"][label])
    return float(st.session_state[custom_key])

def resolve_fixture_cost(label: str, kind: str, custom_key: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["fixtures"][kind]["install_cost_nzd"][label])
    return float(st.session_state[custom_key])

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

    return {
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
        },
    }

def validate_scenario(s: dict) -> list:
    missing = []
    if s["closestCity"] is None:
        missing.append("Closest city")
    if s["HDD_base18"] is None:
        missing.append("HDD")
    for k, label in [
        ("roofRValue", "Roof insulation"),
        ("wallRValue", "Wall insulation"),
        ("floorRValue", "Floor insulation"),
        ("windowUValue", "Window type"),
        ("spaceHeatingCOP", "Space heating system"),
        ("waterHeatingCOP", "Water heating system"),
        ("toilet_L_per_flush", "Toilet type"),
        ("shower_L_per_min", "Shower type"),
        ("tap_L_per_min", "Tap type"),
    ]:
        if s[k] is None:
            missing.append(label)
    if s["washingMachine"]["hasAppliance"] is None:
        missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None:
        missing.append("Dishwasher (Yes/No)")
    return missing

# =============================================================================
# CALLBACKS (fixes the StreamlitAPIException on Copy / Presets)
# =============================================================================
def _scenario_keys(prefix: str) -> list[str]:
    return [k for k in st.session_state.keys() if k.startswith(prefix + "_")]

def copy_baseline_to_option_cb():
    # Only copy "b_" widget keys into "o_" keys inside callback (safe)
    for k in _scenario_keys("b"):
        st.session_state["o_" + k[2:]] = copy.deepcopy(st.session_state[k])
    invalidate_option_only()

def apply_code_minimum_cb(prefix: str):
    # Code minimum envelope + BASIC heaters + ALSO fill fixtures (per your new request)
    st.session_state[f"{prefix}_closestCity"] = "Auckland"  # “any location” but must pass validation
    st.session_state[f"{prefix}_use_custom_hdd"] = False

    st.session_state[f"{prefix}_roofRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_wallRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_floorRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_windowULabel"] = "Standard double glazed"

    # BASIC heaters (as requested)
    st.session_state[f"{prefix}_spaceHeatingSystem"] = "Electric resistance heater"
    st.session_state[f"{prefix}_waterHeatingSystem"] = "Electric storage cylinder"

    # Fixtures filled (previously left blank)
    st.session_state[f"{prefix}_toiletType"] = "Dual flush standard (avg 5 L)"
    st.session_state[f"{prefix}_showerType"] = "Standard"
    st.session_state[f"{prefix}_tapType"] = "Standard"

    # Appliances default No
    st.session_state[f"{prefix}_wash_has"] = "No"
    st.session_state[f"{prefix}_dish_has"] = "No"

    if prefix == "b":
        invalidate_baseline_only()
    else:
        invalidate_option_only()

def reset_scenario_cb(prefix: str):
    # Reset scenario keys back to init defaults (without wiping other scenario)
    # Strategy: pop keys then re-run init_defaults
    keep = {}
    for k, v in st.session_state.items():
        keep[k] = v

    # Remove scenario keys
    for k in list(st.session_state.keys()):
        if k.startswith(prefix + "_"):
            del st.session_state[k]

    # Re-init missing defaults
    init_defaults()

    if prefix == "b":
        invalidate_baseline_only()
    else:
        invalidate_option_only()

def reset_all_cb():
    st.session_state.clear()
    st.rerun()

# =============================================================================
# UI HELP (tooltips)
# =============================================================================
HELP = {
    "closest_city": "Used to infer Climate Zone and HDD (Heating Degree Days, base 18°C).",
    "hdd_custom": "Override HDD if you have a local/confirmed value (base 18°C).",
    "r_value": "R-value (m²K/W): higher = better insulation (lower heat loss).",
    "u_value": "U-value (W/m²K): lower = better glazing performance (lower heat loss).",
    "cop": "COP: higher = less purchased electricity per delivered heat.",
    "lighting": "Lighting electricity = count × watts × hours/day × 365.",
    "tariffs": "Tariffs/factors vary by provider/location. Set to your bill/assumption.",
}

# =============================================================================
# TABS
# =============================================================================
st.title("NZ Housing Sustainability Calculator (Prototype)")
tabs = st.tabs(["Calculator", "Formulas", "Data sources"])

# =============================================================================
# TAB 2: FORMULAS
# =============================================================================
with tabs[1]:
    st.subheader("Formulas (model logic)")
    st.markdown(
        """
**Energy**
- Total electricity (kWh/y) = Space heating purchased + Water heating purchased + Lighting
- Space heating delivered (kWh/y) = (H_total × HDD × 24) / 1000  
- Space heating purchased (kWh/y) = Delivered / COP  
- H_total (W/K) = H_roof + H_wall + H_floor + H_window  
- H_component (W/K) = Area × U, where U = 1/R (except windows use U directly)

**Water**
- End-use volumes (L/y) = (people × frequency × intensity × 365) with appliance cycles per week × 52
- Total water (m³/y) = Sum(end uses) / 1000

**Water heating**
- Hot water volume (L/y) = Σ(end-use volume × hot-water fraction) (toilets excluded)
- Delivered DHW energy (kWh/y) = (V_hot × Cp × ΔT) / 3600  
  where Cp = 4.186 kJ/kg°C, ΔT = setpoint − inlet
- Purchased DHW electricity (kWh/y) = Delivered / COP

**Carbon**
- Electricity CO₂ (kg/y) = kWh × grid EF
- Water CO₂ (kg/y) = m³ × water EF

**Cost**
- Opex (NZD/y) = (kWh × elec tariff) + (m³ × water tariff)
- Capex total (NZD) = Envelope (Σ unit cost × area) + Systems (install) + Fixtures (install)
- Simple payback (years) = (Option capex − Baseline capex) / (Baseline opex − Option opex)
        """
    )

# =============================================================================
# TAB 3: DATA SOURCES TABLE
# =============================================================================
with tabs[2]:
    st.subheader("Data sources (full)")
    # You pasted the table in the prompt; we render it as-is.
    # If you later want to edit in-app, we can store it as a CSV/JSON.
    rows = [
        [1,"Energy","Total Energy","Total annual household energy use","Calculated","Space heating + water heating + lighting","Derived","Primary output"],
        [2,"Energy","Space Heating Energy","Electricity for space heating","Calculated","(H_total × HDD × 24 / 1000) ÷ COP","MBIE (2023)","Steady-state early-stage method"],
        [3,"Energy","Heating Degree Days (HDD)","Climate severity (base 18 °C)","Lookup / User","Zone 1=1200; Zone 2=1400; Zone 3=1800; Zone 4=2200; Zone 5=2400; Zone 6=3000; Custom","InfraComfort (n.d.); MSD (2006)","City → climate zone"],
        [4,"Energy","Heating System COP","Seasonal heating efficiency","Assumption / User","None=0; Electric resistance=1.0; Heat pump=2.5; High-eff HP=3.5; Custom","BRANZ (2023)","Typical NZ systems"],
        [5,"Envelope","Floor R-value","Floor thermal resistance","Assumption / User","Uninsulated=0.6; Basic=1.5; Code=2.0; Good=2.8; Excellent=3.5; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [6,"Envelope","Roof R-value","Roof thermal resistance","Assumption / User","Uninsulated=0.5; Basic=3.0; Code=6.6; Good=8.0; Excellent=10.0; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [7,"Envelope","Wall R-value","Wall thermal resistance","Assumption / User","Uninsulated=0.5; Basic=1.5; Code=2.0; Good=3.0; Excellent=4.0; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [8,"Envelope","Window U-value","Glazing heat transfer","Assumption / User","Single=5.8; Double=3.0; Low-E=2.0; Triple=1.0; Custom","BRANZ (2023)","Typical NZ glazing"],
        [9,"Envelope","Envelope Areas","Floor, roof, wall, window areas","User Input","User input (m²)","User-defined","Simplified geometry"],
        [10,"Water Heating","Delivered Hot Water Energy","Energy to heat water","Calculated","(V × ΔT × Cp) ÷ 3600","Engineering standard","Physics-based"],
        [11,"Water Heating","Heat Capacity (Cp)","Thermal constant","Constant","4.186 kJ/kg °C","Engineering standard","Universal"],
        [12,"Water Heating","Hot Water Fraction – Shower","Portion of shower water heated","Assumption / User","Default=0.9","BRANZ (2023)","Overrideable"],
        [13,"Water Heating","Hot Water Fraction – Tap","Portion of tap water heated","Assumption / User","Default=0.4","BRANZ (2023)","Overrideable"],
        [14,"Water Heating","Hot Water Fraction – Laundry","Portion of laundry water heated","Assumption / User","Default=0.5","BRANZ (2023)","Overrideable"],
        [15,"Water Heating","Hot Water Fraction – Dishwasher","Portion of dishwasher water heated","Assumption / User","Default=1.0","BRANZ (2023)","Overrideable"],
        [16,"Water Heating","Water Heating COP","Hot water system efficiency","Assumption / User","None=0; Electric cylinder=1.0; HPHW=2.0; Custom","BRANZ (2023)","Simplified"],
        [17,"Lighting","Lighting Energy","Annual lighting electricity","Calculated","(Lights × W × h × 365) ÷ 1000","Derived","Standard load"],
        [18,"Lighting","Number of Lights","Installed fixtures","User Input","User input","User-defined","No default"],
        [19,"Lighting","Wattage per Light","Lamp power","User Input","User input (W)","User-defined","LED–incandescent"],
        [20,"Lighting","Daily Usage Hours","Average daily use","User Input","User input (h/day)","User-defined","Early-stage"],
        [21,"Water","Total Water Use","Annual indoor water use","Calculated","Sum of end uses","Derived","m³/year"],
        [22,"Water","Toilet Flush Volume","Water per flush","Assumption / User","Single=9; Dual std=5; Dual eff=4; Custom","BRANZ (2023)","NZ fixtures"],
        [23,"Water","Shower Flow Rate","Shower water flow","Assumption / User","Standard=9; Low-flow=7; Efficient=6; Custom","BRANZ (2023)","L/min"],
        [24,"Water","Tap Flow Rate","Tap water flow","Assumption / User","Standard=8; Efficient=6; Very efficient=4; Custom","BRANZ (2023)","L/min"],
        [25,"Water","Laundry Water per Cycle","Washing machine demand","Assumption / User","User input (L/cycle)","BRANZ (2023)",""],
        [26,"Water","Dishwasher Water per Cycle","Dishwasher demand","Assumption / User","User input (L/cycle)","BRANZ (2023)",""],
        [27,"Carbon","Electricity Emissions","CO₂ from electricity use","Calculated","Energy × factor","MfE (2024)","2023 value"],
        [28,"Carbon","Grid Emission Factor","Carbon intensity of grid","Constant","0.0729 kgCO₂e/kWh","MfE (2024)","Location-based"],
        [29,"Carbon","Water Emissions","CO₂ from water supply","Calculated","Water × factor","MfE (2024)",""],
        [30,"Carbon","Water Emission Factor","Carbon per m³ water","Constant","0.0349 kgCO₂e/m³","MfE (2024)",""],
        [31,"Cost (Opex)","Electricity Tariff","Retail electricity price","Default / User","Default=0.312 NZD/kWh","Electricity Authority (2024)","Editable"],
        [32,"Cost (Opex)","Water Tariff","Residential water price","Default / User","Default=2.296 NZD/m³","Auckland Council (2025)","Editable"],
        [33,"Cost (Opex)","Annual Operating Cost","Total operating cost","Calculated","Energy + water","Derived",""],
        [34,"Cost (Capex)","Floor Insulation Cost","Installed floor insulation","Assumption / User","0/20/40/70/110 NZD/m²","Market benchmark","Early-stage"],
        [35,"Cost (Capex)","Roof Insulation Cost","Installed roof insulation","Assumption / User","0/15/25/35/35 NZD/m²","Market benchmark",""],
        [36,"Cost (Capex)","Wall Insulation Cost","Installed wall insulation","Assumption / User","0/25/45/75/120 NZD/m²","Market benchmark",""],
        [37,"Cost (Capex)","Window Cost","Installed glazing","Assumption / User","300/600/950/1400 NZD/m²","Market benchmark",""],
        [38,"Cost (Capex)","Space Heating System Cost","Installed heating system","Assumption / User","0/1500/4500/7000 NZD","Market benchmark",""],
        [39,"Cost (Capex)","Water Heating System Cost","Installed DHW system","Assumption / User","0/3500/6500 NZD","Market benchmark",""],
        [40,"Cost (Capex)","Water Fixture Costs","Toilet, shower, tap upgrades","Assumption / User","As specified","Market benchmark",""],
        [41,"Metrics","Annual Savings","Opex reduction","Calculated","Baseline − option","Derived",""],
        [42,"Metrics","Payback Period","Investment recovery time","Calculated","Capex ÷ savings","Derived","Years"],
    ]
    df_sources = pd.DataFrame(rows, columns=[
        "Order","Module","Variable / Indicator","Description & Role in Model","Data Type",
        "Selection Options & Default Values","Source / Reference","Notes"
    ])
    st.dataframe(df_sources, use_container_width=True, hide_index=True)

# =============================================================================
# TAB 1: CALCULATOR
# =============================================================================
with tabs[0]:
    st.caption("Early-stage comparison tool. Simplified, indicative, non-certification. Use fixed containers so inputs and results scroll independently.")

    # Options
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

    # -------------------------------------------------------------------------
    # Layout: fixed-height containers to create independent scroll (requested)
    # -------------------------------------------------------------------------
    left, right = st.columns([1.35, 1.0], gap="large")

    def _caption_envelope(prefix: str):
        labels = {
            "roof": st.session_state[f"{prefix}_roofRLabel"],
            "wall": st.session_state[f"{prefix}_wallRLabel"],
            "floor": st.session_state[f"{prefix}_floorRLabel"],
            "window": st.session_state[f"{prefix}_windowULabel"],
        }

        if labels["roof"] != PLACEHOLDER:
            if labels["roof"] == "Custom":
                r = float(st.session_state[f"{prefix}_roofR_custom"])
                c = float(st.session_state[f"{prefix}_roofCost_custom"])
            else:
                r = float(LOOKUP["thermal_envelope"]["roofR_m2K_per_W"][labels["roof"]])
                c = float(LOOKUP["thermal_envelope"]["capex_per_m2"]["roof"][_bucket_from_label(labels["roof"])])
            st.caption(f"Roof: R={fmt_num(r,1)}; capex={fmt_money(c)} /m² roof")

        if labels["wall"] != PLACEHOLDER:
            if labels["wall"] == "Custom":
                r = float(st.session_state[f"{prefix}_wallR_custom"])
                c = float(st.session_state[f"{prefix}_wallCost_custom"])
            else:
                r = float(LOOKUP["thermal_envelope"]["wallR_m2K_per_W"][labels["wall"]])
                c = float(LOOKUP["thermal_envelope"]["capex_per_m2"]["wall"][_bucket_from_label(labels["wall"])])
            st.caption(f"Walls: R={fmt_num(r,1)}; capex={fmt_money(c)} /m² wall")

        if labels["floor"] != PLACEHOLDER:
            if labels["floor"] == "Custom":
                r = float(st.session_state[f"{prefix}_floorR_custom"])
                c = float(st.session_state[f"{prefix}_floorCost_custom"])
            else:
                r = float(LOOKUP["thermal_envelope"]["floorR_m2K_per_W"][labels["floor"]])
                c = float(LOOKUP["thermal_envelope"]["capex_per_m2"]["floor"][_bucket_from_label(labels["floor"])])
            st.caption(f"Floor: R={fmt_num(r,1)}; capex={fmt_money(c)} /m² floor")

        if labels["window"] != PLACEHOLDER:
            if labels["window"] == "Custom":
                u = float(st.session_state[f"{prefix}_windowU_custom"])
                c = float(st.session_state[f"{prefix}_windowCost_custom"])
            else:
                u = float(LOOKUP["thermal_envelope"]["windowU_W_per_m2K"][labels["window"]])
                c = float(LOOKUP["thermal_envelope"]["capex_per_m2"]["window"][labels["window"]])
            st.caption(f"Windows: U={fmt_num(u,1)}; capex={fmt_money(c)} /m² window")

    def _caption_systems(prefix: str):
        s = st.session_state[f"{prefix}_spaceHeatingSystem"]
        w = st.session_state[f"{prefix}_waterHeatingSystem"]

        if s != PLACEHOLDER:
            if s == "Custom":
                cop = float(st.session_state[f"{prefix}_spaceCOP_custom"])
                cost = float(st.session_state[f"{prefix}_spaceInstall_custom"])
            else:
                cop = float(LOOKUP["systems"]["space_heating"]["cop"][s])
                cost = float(LOOKUP["systems"]["space_heating"]["install_cost_nzd"][s])
            st.caption(f"Space heating: COP={fmt_num(cop,2)}; install capex={fmt_money(cost)}")

        if w != PLACEHOLDER:
            if w == "Custom":
                cop = float(st.session_state[f"{prefix}_waterCOP_custom"])
                cost = float(st.session_state[f"{prefix}_waterInstall_custom"])
            else:
                cop = float(LOOKUP["systems"]["water_heating"]["cop"][w])
                cost = float(LOOKUP["systems"]["water_heating"]["install_cost_nzd"][w])
            st.caption(f"Water heating: COP={fmt_num(cop,2)}; install capex={fmt_money(cost)}")

    def _caption_fixtures(prefix: str):
        t = st.session_state[f"{prefix}_toiletType"]
        s = st.session_state[f"{prefix}_showerType"]
        a = st.session_state[f"{prefix}_tapType"]

        if t != PLACEHOLDER:
            if t == "Custom":
                v = float(st.session_state[f"{prefix}_toilet_value_custom"])
                c = float(st.session_state[f"{prefix}_toilet_cost_custom"])
            else:
                v = float(LOOKUP["fixtures"]["toilet"]["l_per_flush"][t])
                c = float(LOOKUP["fixtures"]["toilet"]["install_cost_nzd"][t])
            st.caption(f"Toilet: {fmt_num(v,1)} L/flush; install capex={fmt_money(c)}")

        if s != PLACEHOLDER:
            if s == "Custom":
                v = float(st.session_state[f"{prefix}_shower_value_custom"])
                c = float(st.session_state[f"{prefix}_shower_cost_custom"])
            else:
                v = float(LOOKUP["fixtures"]["shower"]["l_per_min"][s])
                c = float(LOOKUP["fixtures"]["shower"]["install_cost_nzd"][s])
            st.caption(f"Shower: {fmt_num(v,1)} L/min; install capex={fmt_money(c)}")

        if a != PLACEHOLDER:
            if a == "Custom":
                v = float(st.session_state[f"{prefix}_tap_value_custom"])
                c = float(st.session_state[f"{prefix}_tap_cost_custom"])
            else:
                v = float(LOOKUP["fixtures"]["tap"]["l_per_min"][a])
                c = float(LOOKUP["fixtures"]["tap"]["install_cost_nzd"][a])
            st.caption(f"Tap: {fmt_num(v,1)} L/min; install capex={fmt_money(c)}")

    def scenario_panel(prefix: str, title: str, on_change_fn):
        st.subheader(title)

        # Presets / copy / reset
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            st.button(
                f"Use Code Minimum ({title})",
                use_container_width=True,
                key=f"{prefix}_btn_code_min",
                on_click=apply_code_minimum_cb,
                args=(prefix,),
            )
        with c2:
            if prefix == "o":
                st.button(
                    "Copy Baseline → Option",
                    use_container_width=True,
                    key="btn_copy_b_to_o",
                    on_click=copy_baseline_to_option_cb,
                )
            else:
                st.button(
                    "Reset ALL (app)",
                    use_container_width=True,
                    key="btn_reset_all",
                    on_click=reset_all_cb,
                )
        with c3:
            st.button(
                f"Reset ({title})",
                use_container_width=True,
                key=f"{prefix}_btn_reset",
                on_click=reset_scenario_cb,
                args=(prefix,),
            )

        # 3 expanders total (requested), each with 2 columns inside
        with st.expander("Row 1 — Core + Climate", expanded=True):
            a, b = st.columns(2, gap="small")
            with a:
                st.number_input("Floor area (m²)", 20.0, 500.0, step=5.0, key=f"{prefix}_floorArea", on_change=on_change_fn)
                st.number_input("Ceiling height (m)", 2.0, 4.0, step=0.1, key=f"{prefix}_ceilingHeight", on_change=on_change_fn)
                st.number_input("Household size (people)", 1, 12, step=1, key=f"{prefix}_householdSize", on_change=on_change_fn)
                st.number_input("Total window area (m²)", 0.0, 200.0, step=5.0, key=f"{prefix}_windowArea", on_change=on_change_fn)

            with b:
                st.selectbox("Closest city", [PLACEHOLDER] + CITIES, key=f"{prefix}_closestCity", help=HELP["closest_city"], on_change=on_change_fn)
                city = st.session_state[f"{prefix}_closestCity"]
                if city != PLACEHOLDER:
                    z = LOOKUP["climate"]["zone_by_city"][city]
                    h_default = LOOKUP["climate"]["hdd_by_zone_base18"][z]
                    st.caption(f"Climate zone: {z.split('–')[0].strip()} • Default HDD (base 18°C): {h_default:g}")

                st.checkbox("Use custom HDD", key=f"{prefix}_use_custom_hdd", help=HELP["hdd_custom"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_use_custom_hdd"]:
                    st.number_input("Custom HDD (base 18°C)", 0.0, 6000.0, step=50.0, key=f"{prefix}_hdd_override_value", on_change=on_change_fn)
                    st.caption(f"Using custom HDD: {fmt_num(float(st.session_state[f'{prefix}_hdd_override_value']),0)}")

        with st.expander("Row 2 — Envelope + Lighting", expanded=False):
            a, b = st.columns(2, gap="small")
            with a:
                st.selectbox("Roof insulation", [PLACEHOLDER] + ROOF_OPTS, key=f"{prefix}_roofRLabel", help=HELP["r_value"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                    st.number_input("Roof R-value (m²K/W)", 0.1, 20.0, step=0.1, key=f"{prefix}_roofR_custom", on_change=on_change_fn)
                    st.number_input("Roof capex (NZD/m² roof)", 0.0, 2000.0, step=10.0, key=f"{prefix}_roofCost_custom", on_change=on_change_fn)
                _caption_envelope(prefix)

                st.selectbox("Wall insulation", [PLACEHOLDER] + WALL_OPTS, key=f"{prefix}_wallRLabel", help=HELP["r_value"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                    st.number_input("Wall R-value (m²K/W)", 0.1, 20.0, step=0.1, key=f"{prefix}_wallR_custom", on_change=on_change_fn)
                    st.number_input("Wall capex (NZD/m² wall)", 0.0, 2000.0, step=10.0, key=f"{prefix}_wallCost_custom", on_change=on_change_fn)
                _caption_envelope(prefix)

                st.selectbox("Floor insulation", [PLACEHOLDER] + FLOOR_OPTS, key=f"{prefix}_floorRLabel", help=HELP["r_value"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                    st.number_input("Floor R-value (m²K/W)", 0.1, 20.0, step=0.1, key=f"{prefix}_floorR_custom", on_change=on_change_fn)
                    st.number_input("Floor capex (NZD/m² floor)", 0.0, 2000.0, step=10.0, key=f"{prefix}_floorCost_custom", on_change=on_change_fn)
                _caption_envelope(prefix)

                st.selectbox("Window type", [PLACEHOLDER] + WIN_OPTS, key=f"{prefix}_windowULabel", help=HELP["u_value"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                    st.number_input("Window U-value (W/m²K)", 0.1, 10.0, step=0.1, key=f"{prefix}_windowU_custom", on_change=on_change_fn)
                    st.number_input("Windows capex (NZD/m² window)", 0.0, 5000.0, step=25.0, key=f"{prefix}_windowCost_custom", on_change=on_change_fn)
                _caption_envelope(prefix)

            with b:
                st.number_input("Number of lights", 0, 200, step=1, key=f"{prefix}_light_n", help=HELP["lighting"], on_change=on_change_fn)
                st.number_input("Watts per light", 0.0, 200.0, step=1.0, key=f"{prefix}_light_watts", help=HELP["lighting"], on_change=on_change_fn)
                st.number_input("Lighting hours/day", 0.0, 24.0, step=0.5, key=f"{prefix}_light_hours", help=HELP["lighting"], on_change=on_change_fn)
                st.caption(
                    f"Lighting calc uses: n={int(st.session_state[f'{prefix}_light_n'])}, "
                    f"W={fmt_num(float(st.session_state[f'{prefix}_light_watts']),0)}, "
                    f"h/day={fmt_num(float(st.session_state[f'{prefix}_light_hours']),1)}"
                )

        with st.expander("Row 3 — Systems + Water/Fixtures + Assumptions/Tariffs", expanded=False):
            a, b = st.columns(2, gap="small")
            with a:
                st.selectbox("Space heating system", [PLACEHOLDER] + SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help=HELP["cop"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                    st.number_input("Space heating COP", 0.0, 10.0, step=0.1, key=f"{prefix}_spaceCOP_custom", on_change=on_change_fn)
                    st.number_input("Space heating install capex (NZD)", 0.0, 50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom", on_change=on_change_fn)
                _caption_systems(prefix)

                st.selectbox("Water heating system", [PLACEHOLDER] + WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help=HELP["cop"], on_change=on_change_fn)
                if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                    st.number_input("Water heating COP", 0.0, 10.0, step=0.1, key=f"{prefix}_waterCOP_custom", on_change=on_change_fn)
                    st.number_input("Water heating install capex (NZD)", 0.0, 50000.0, step=100.0, key=f"{prefix}_waterInstall_custom", on_change=on_change_fn)
                _caption_systems(prefix)

                st.markdown("---")
                st.number_input("Electricity tariff (NZD/kWh)", 0.0, 2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"], on_change=on_change_fn)
                st.caption(f"Electricity tariff: {fmt_num(float(st.session_state[f'{prefix}_coef_elec_tariff']),3)} NZD/kWh")
                st.number_input("Water tariff (NZD/m³)", 0.0, 20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"], on_change=on_change_fn)
                st.caption(f"Water tariff: {fmt_num(float(st.session_state[f'{prefix}_coef_water_tariff']),3)} NZD/m³")
                st.number_input("Grid emission factor (kgCO₂e/kWh)", 0.0, 1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", on_change=on_change_fn)
                st.caption(f"Grid EF: {fmt_num(float(st.session_state[f'{prefix}_coef_grid_ef']),4)} kgCO₂e/kWh")
                st.number_input("Water emission factor (kgCO₂e/m³)", 0.0, 5.0, step=0.0001, key=f"{prefix}_coef_water_ef", on_change=on_change_fn)
                st.caption(f"Water EF: {fmt_num(float(st.session_state[f'{prefix}_coef_water_ef']),4)} kgCO₂e/m³")

            with b:
                st.selectbox("Toilet type", [PLACEHOLDER] + TOILET_OPTS, key=f"{prefix}_toiletType", on_change=on_change_fn)
                if st.session_state[f"{prefix}_toiletType"] == "Custom":
                    st.number_input("Toilet litres/flush", 1.0, 20.0, step=0.5, key=f"{prefix}_toilet_value_custom", on_change=on_change_fn)
                    st.number_input("Toilet install capex (NZD)", 0.0, 20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom", on_change=on_change_fn)
                _caption_fixtures(prefix)

                st.selectbox("Shower type", [PLACEHOLDER] + SHOWER_OPTS, key=f"{prefix}_showerType", on_change=on_change_fn)
                if st.session_state[f"{prefix}_showerType"] == "Custom":
                    st.number_input("Shower flow (L/min)", 1.0, 30.0, step=0.5, key=f"{prefix}_shower_value_custom", on_change=on_change_fn)
                    st.number_input("Shower install capex (NZD)", 0.0, 20000.0, step=50.0, key=f"{prefix}_shower_cost_custom", on_change=on_change_fn)
                _caption_fixtures(prefix)

                st.selectbox("Tap type", [PLACEHOLDER] + TAP_OPTS, key=f"{prefix}_tapType", on_change=on_change_fn)
                if st.session_state[f"{prefix}_tapType"] == "Custom":
                    st.number_input("Tap flow (L/min)", 1.0, 30.0, step=0.5, key=f"{prefix}_tap_value_custom", on_change=on_change_fn)
                    st.number_input("Tap install capex (NZD)", 0.0, 20000.0, step=50.0, key=f"{prefix}_tap_cost_custom", on_change=on_change_fn)
                _caption_fixtures(prefix)

                st.markdown("---")
                st.selectbox("Has washing machine?", ["Yes", "No"], key=f"{prefix}_wash_has", on_change=on_change_fn)
                st.caption(f"Washing machine: {st.session_state[f'{prefix}_wash_has']}")
                if st.session_state[f"{prefix}_wash_has"] == "Yes":
                    st.number_input("Cycles/week (washing)", 0.0, 50.0, step=1.0, key=f"{prefix}_wash_cycles", on_change=on_change_fn)
                    st.number_input("L/cycle (washing)", 0.0, 300.0, step=5.0, key=f"{prefix}_wash_L", on_change=on_change_fn)

                st.selectbox("Has dishwasher?", ["Yes", "No"], key=f"{prefix}_dish_has", on_change=on_change_fn)
                st.caption(f"Dishwasher: {st.session_state[f'{prefix}_dish_has']}")
                if st.session_state[f"{prefix}_dish_has"] == "Yes":
                    st.number_input("Cycles/week (dishwasher)", 0.0, 50.0, step=1.0, key=f"{prefix}_dish_cycles", on_change=on_change_fn)
                    st.number_input("L/cycle (dishwasher)", 0.0, 100.0, step=1.0, key=f"{prefix}_dish_L", on_change=on_change_fn)

                st.markdown("---")
                st.number_input("Hot water setpoint (°C)", 30.0, 80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C", on_change=on_change_fn)
                st.caption(f"Hot water setpoint: {fmt_num(float(st.session_state[f'{prefix}_hotWater_setpoint_C']),0)} °C")
                st.number_input("Cold water inlet (°C)", 0.0, 30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C", on_change=on_change_fn)
                st.caption(f"Cold inlet: {fmt_num(float(st.session_state[f'{prefix}_coldWater_inlet_C']),0)} °C")

                st.number_input("Toilet flushes/person/day", 0.0, 20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd", on_change=on_change_fn)
                st.number_input("Showers/person/day", 0.0, 5.0, step=0.1, key=f"{prefix}_showers_ppd", on_change=on_change_fn)
                st.number_input("Minutes/shower", 0.0, 60.0, step=0.1, key=f"{prefix}_minutes_per_shower", on_change=on_change_fn)
                st.number_input("Tap minutes/person/day", 0.0, 120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd", on_change=on_change_fn)

    # Fixed height scroll containers
    with left:
        left_box = st.container(height=900, border=True)
        with left_box:
            scenario_panel("b", "Baseline", on_change_fn=invalidate_baseline_only)
            st.divider()

            base_now = get_scenario("b")
            missing_b = validate_scenario(base_now)
            if missing_b:
                st.info("Baseline incomplete. Missing: " + ", ".join(missing_b))

            disabled_b = len(missing_b) > 0
            if st.button("Calculate Baseline", use_container_width=True, disabled=disabled_b, key="btn_calc_baseline"):
                base_coeffs = get_coeffs("b")
                st.session_state["baseline_inputs_snapshot"] = copy.deepcopy(base_now)
                st.session_state["baseline_results"] = calculate_scenario(base_now, base_coeffs)
                st.session_state["baseline_calculated"] = True
                # baseline recalc invalidates option comparison
                invalidate_option_only()

            st.divider()

            if not st.session_state["baseline_calculated"]:
                st.warning("Calculate Baseline first to unlock Option.")
            else:
                scenario_panel("o", "Option", on_change_fn=invalidate_option_only)
                st.divider()

                opt_now = get_scenario("o")
                missing_o = validate_scenario(opt_now)
                if missing_o:
                    st.info("Option incomplete. Missing: " + ", ".join(missing_o))

                disabled_o = len(missing_o) > 0
                if st.button("Calculate Option + Compare", use_container_width=True, disabled=disabled_o, key="btn_calc_option"):
                    opt_coeffs = get_coeffs("o")
                    st.session_state["option_inputs_snapshot"] = copy.deepcopy(opt_now)
                    st.session_state["option_results"] = calculate_scenario(opt_now, opt_coeffs)
                    st.session_state["option_calculated"] = True

    with right:
        right_box = st.container(height=900, border=True)
        with right_box:
            st.subheader("Results")

            if not st.session_state["baseline_calculated"]:
                st.info("Results will appear here after you click **Calculate Baseline**.")
            else:
                base_r = st.session_state["baseline_results"]
                st.markdown("### Baseline KPI summary")

                kpi_base = pd.DataFrame([
                    {"Metric": "Total Energy (kWh/y)", "Value": base_r["totalElectricity_kwh_y"], "Unit": "kWh/y"},
                    {"Metric": "Energy Intensity (kWh/m²/y)", "Value": base_r["energyIntensity_kwh_m2_y"], "Unit": "kWh/m²/y"},
                    {"Metric": "Water Consumption (m³/y)", "Value": base_r["waterConsumption"]["V_total_m3_y"], "Unit": "m³/y"},
                    {"Metric": "Operational Carbon (kgCO₂e/y)", "Value": base_r["carbon"]["CO2_total_kg_y"], "Unit": "kgCO₂e/y"},
                    {"Metric": "Annual Opex (NZD/y)", "Value": base_r["opex"]["opex_total_nzd_y"], "Unit": "NZD/y"},
                    {"Metric": "Total Capex (NZD)", "Value": base_r["capex"]["capex_total_nzd"], "Unit": "NZD"},
                ])
                st.dataframe(
                    kpi_base.assign(ValueFmt=lambda d: d["Value"].map(lambda x: fmt_num(float(x), 1)))[["Metric", "ValueFmt", "Unit"]]
                    .rename(columns={"ValueFmt": "Value"}),
                    hide_index=True,
                    use_container_width=True,
                )

                st.divider()

                if not st.session_state["option_calculated"]:
                    st.info("Fill Option inputs on the left, then click **Calculate Option + Compare**.")
                else:
                    opt_r = st.session_state["option_results"]

                    rows = [
                        ("Total Energy (kWh/y)", base_r["totalElectricity_kwh_y"], opt_r["totalElectricity_kwh_y"], 1, "kWh/y"),
                        ("Energy Intensity (kWh/m²/y)", base_r["energyIntensity_kwh_m2_y"], opt_r["energyIntensity_kwh_m2_y"], 2, "kWh/m²/y"),
                        ("Water (m³/y)", base_r["waterConsumption"]["V_total_m3_y"], opt_r["waterConsumption"]["V_total_m3_y"], 2, "m³/y"),
                        ("Carbon (kgCO₂e/y)", base_r["carbon"]["CO2_total_kg_y"], opt_r["carbon"]["CO2_total_kg_y"], 1, "kgCO₂e/y"),
                        ("Opex (NZD/y)", base_r["opex"]["opex_total_nzd_y"], opt_r["opex"]["opex_total_nzd_y"], 0, "NZD/y"),
                        ("Capex total (NZD)", base_r["capex"]["capex_total_nzd"], opt_r["capex"]["capex_total_nzd"], 0, "NZD"),
                    ]
                    out = []
                    for name, b, o, dec, unit in rows:
                        d = o - b
                        out.append({
                            "Metric": name,
                            "Baseline": fmt_num(b, dec),
                            "Option": fmt_num(o, dec),
                            "Δ (Option−Base)": fmt_num(d, dec),
                            "Dir": direction_arrow(d),
                            "Unit": unit,
                        })
                    st.markdown("### Comparison KPIs")
                    st.dataframe(pd.DataFrame(out), hide_index=True, use_container_width=True)

                    inc_capex = opt_r["capex"]["capex_total_nzd"] - base_r["capex"]["capex_total_nzd"]
                    savings = base_r["opex"]["opex_total_nzd_y"] - opt_r["opex"]["opex_total_nzd_y"]
                    if inc_capex <= 0:
                        pb = 0.0
                        pb_note = "No additional capex (option ≤ baseline capex)."
                    elif savings <= 0:
                        pb = None
                        pb_note = "No payback (opex savings ≤ 0)."
                    else:
                        pb = inc_capex / savings
                        pb_note = ""

                    st.caption(f"Simple payback: **{fmt_num(pb, 1) if pb is not None else '—'} years** {('— ' + pb_note) if pb_note else ''}")

                    st.divider()
                    st.markdown("### Charts (vertical bars)")

                    df_kpi = pd.DataFrame([
                        {"Metric": "Energy", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
                        {"Metric": "Water", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
                        {"Metric": "Carbon", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
                        {"Metric": "Opex", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
                    ])
                    st.pyplot(fig_grouped_bar_vertical(df_kpi, "KPIs: Baseline vs Option", "Value"))

                    df_energy = pd.DataFrame([
                        {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
                        {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
                        {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
                        {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
                        {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
                        {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_total_kwh_y"]},
                    ])
                    st.pyplot(fig_stacked_bar_vertical(df_energy, "Energy breakdown (excl. plug loads)", "kWh/y"))

                    b_w = base_r["waterConsumption"]["breakdown_m3_y"]
                    o_w = opt_r["waterConsumption"]["breakdown_m3_y"]
                    df_water = pd.DataFrame(
                        [{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b_w.items()] +
                        [{"Scenario": "Option", "Component": k, "Value": v} for k, v in o_w.items()]
                    )
                    st.pyplot(fig_stacked_bar_vertical(df_water, "Indoor water breakdown", "m³/y"))

                    df_carbon = pd.DataFrame([
                        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
                        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
                        {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity_kg_y"]},
                        {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water_kg_y"]},
                    ])
                    st.pyplot(fig_stacked_bar_vertical(df_carbon, "Operational carbon breakdown", "kgCO₂e/y"))

                    df_opex = pd.DataFrame([
                        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
                        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
                        {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["opex"]["opex_electricity_nzd_y"]},
                        {"Scenario": "Option", "Component": "Water", "Value": opt_r["opex"]["opex_water_nzd_y"]},
                    ])
                    st.pyplot(fig_stacked_bar_vertical(df_opex, "Opex breakdown", "NZD/y"))

                    st.pyplot(fig_capex_compare(base_r["capex"]["detail_breakdown_nzd"], opt_r["capex"]["detail_breakdown_nzd"]))

                    st.divider()
                    payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "baseline": {"coefficients": get_coeffs("b"), "inputs": st.session_state["baseline_inputs_snapshot"], "results": base_r},
                        "option": {"coefficients": get_coeffs("o"), "inputs": st.session_state["option_inputs_snapshot"], "results": opt_r},
                        "notes": {
                            "scope": "Early-stage decision support; not certification; not simulation.",
                            "energy_boundary": "Space heating + water heating + lighting (excludes plug loads/appliances).",
                            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
                            "capex_boundary": "Transparent unit-cost accounting. Not investment-grade.",
                            "hot_water_model": "Hot water derived from end-use volumes using hot water fractions (toilet excluded).",
                        },
                    }
                    st.download_button(
                        "Download results (JSON)",
                        data=json.dumps(payload, indent=2),
                        file_name=f"housing-sustainability-comparison-{int(datetime.utcnow().timestamp())}.json",
                        mime="application/json",
                        use_container_width=True,
                    )
