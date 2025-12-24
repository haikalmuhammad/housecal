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
# UNIFIED LOOKUP TABLES (Single Source of Truth)
# =============================================================================
LOOKUP = {
    "constants": {
        # Source: MfE (2024) — NZ grid & water emission factors (2023)
        "grid_emission_factor_kgco2e_per_kwh": 0.0729,
        "water_emission_factor_kgco2e_per_m3": 0.0349,

        # Source: Electricity Authority NZ (2024) — representative retail tariff (default)
        "electricity_tariff_nzd_per_kwh_default": 0.312,
        # Source: Auckland Council (2025) — representative indoor residential tariff (default)
        "water_tariff_nzd_per_m3_default": 2.296,

        # Geometry
        "ceiling_height_m_default": 2.4,

        # Thermo for water heating
        "cp_kj_per_kgC": 4.186,
    },

    "thermal_envelope": {
        # Source: MBIE (2023); BRANZ (2023) — simplified early-stage bands aligned to NZBC H1 intent
        "floorR_m2K_per_W": {
            "Uninsulated": 0.6,
            "Basic": 1.5,
            "Code minimum": 2.0,
            "Good": 2.8,
            "Excellent": 3.5,
        },
        "roofR_m2K_per_W": {
            "Uninsulated": 0.5,
            "Basic": 3.0,
            "Code minimum": 6.6,
            "Good": 8.0,
            "Excellent": 10.0,
        },
        "wallR_m2K_per_W": {
            "Uninsulated": 0.5,
            "Basic": 1.5,
            "Code minimum": 2.0,
            "Good": 3.0,
            "Excellent": 4.0,
        },

        # Source: MBIE (2023); BRANZ (2023) — simplified glazing U-values
        "windowU_W_per_m2K": {
            "Single glazed": 5.8,
            "Standard double glazed": 3.0,
            "Low-E double glazed": 2.0,
            "High-performance triple glazed": 1.0,
        },

        # Source: PRD Appendix (user-specified cost schedule)
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
        # Source: InfraComfort (n.d.); Ministry of Social Development (2006) — benchmarked HDD magnitude bands (base 18°C)
        "hdd_by_zone_base18": {
            "Climate Zone 1 – Warmest": 1200,
            "Climate Zone 2 – Warm": 1400,
            "Climate Zone 3 – Mild": 1800,
            "Climate Zone 4 – Cool": 2200,
            "Climate Zone 5 – Cold": 2400,
            "Climate Zone 6 – Coldest": 3000,
        },
        # Source: PRD Appendix (city lists; adjust as needed)
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
        # Source: BRANZ (2023) — simplified seasonal COP bands for NZ conditions (early-stage)
        "space_heating": {
            "cop": {
                "None": 0.0,
                "Electric resistance heater": 1.0,
                "Air-source Heat pump": 2.5,
                "High-efficiency heat pump": 3.5,
            },
            # Source: PRD Appendix (user-specified install cost schedule)
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
        # Source: BRANZ (2023) — end-use accounting structure; PRD Appendix values
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

        # Source: BRANZ (2023) — simplified hot water fractions
        "hot_water_fractions": {"shower": 0.9, "tap": 0.4, "laundry": 0.5, "dishwasher": 1.0},
    },

    "defaults": {
        "washing_machine": {"hasAppliance": False, "cyclesPerWeek": 4, "waterPerCycle_L": 60},
        "dishwasher": {"hasAppliance": False, "cyclesPerWeek": 4, "waterPerCycle_L": 12},
        "lighting": {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5},
        "usage": {
            "toiletFlushes_per_person_day": 5.0,
            "showers_per_person_day": 1.0,
            "minutes_per_shower": 6.21,  # Source: Homestar Water Calculator default (fill exact doc/page later)
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

def _bucket_from_label(label: str) -> str:
    for b in ["Uninsulated", "Basic", "Code minimum", "Good", "Excellent"]:
        if label == b:
            return b
    return "Uninsulated"

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

def resolve_fixture_value(prefix: str, label: str, kind: str) -> float | None:
    if label == PLACEHOLDER:
        return None
    if label != "Custom":
        return float(LOOKUP["fixtures"][kind]["l_per_flush" if kind == "toilet" else "l_per_min"][label])
    return float(st.session_state[f"{prefix}_{kind}_value_custom"])

def resolve_fixture_cost(prefix: str, label: str, kind: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["fixtures"][kind]["install_cost_nzd"][label])
    return float(st.session_state[f"{prefix}_{kind}_cost_custom"])

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

    return {"capex_total_nzd": total, "breakdown_nzd": {"Envelope": envelope, "Systems": systems, "Fixtures": fixtures}}

def calculate_scenario(s: dict, coeffs: dict) -> dict:
    space = calculate_space_heating(s)
    water_use = calculate_water_enduse(s)
    water_heat = calculate_water_heating_from_enduse(s, water_use["enduse_L_y"])
    lighting = calculate_lighting(s)

    total_electricity_kwh_y = space["Q_purchased_kwh_y"] + water_heat["Q_purchased_kwh_y"] + lighting["Q_total_kwh_y"]
    carbon = calculate_operational_carbon(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    opex = calculate_opex(total_electricity_kwh_y, water_use["V_total_m3_y"], coeffs)
    energy_intensity = (total_electricity_kwh_y / s["floorArea"]) if s["floorArea"] > 0 else 0.0

    return {
        "spaceHeating": space,
        "waterConsumption": water_use,
        "waterHeating": water_heat,
        "lighting": lighting,
        "totalElectricity_kwh_y": total_electricity_kwh_y,
        "energyIntensity_kwh_m2_y": energy_intensity,
        "carbon": carbon,
        "opex": opex,
    }

# =============================================================================
# CHARTS (VERTICAL)
# =============================================================================
def fig_grouped_bar(df: pd.DataFrame, title: str, y_label: str):
    # df columns: Metric, Baseline, Option
    metrics = df["Metric"].tolist()
    baseline_vals = df["Baseline"].tolist()
    option_vals = df["Option"].tolist()

    x = list(range(len(metrics)))
    w = 0.38

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    ax.bar([xx - w/2 for xx in x], baseline_vals, width=w, label="Baseline")
    ax.bar([xx + w/2 for xx in x], option_vals, width=w, label="Option")

    ax.set_xticks(x)
    ax.set_xticklabels(metrics, rotation=20, ha="right")
    ax.set_title(title)
    ax.set_ylabel(y_label)
    ax.legend(loc="upper right")
    fig.tight_layout()
    return fig

def fig_stacked_bar_vertical(df: pd.DataFrame, title: str, y_label: str):
    # df columns: Scenario, Component, Value
    pivot = df.pivot_table(index="Scenario", columns="Component", values="Value", aggfunc="sum").fillna(0)

    fig, ax = plt.subplots(figsize=(7.2, 4.2))
    pivot.plot(kind="bar", stacked=True, ax=ax)
    ax.set_title(title)
    ax.set_xlabel("")
    ax.set_ylabel(y_label)
    ax.legend(title="Component", bbox_to_anchor=(1.02, 1), loc="upper left")
    fig.tight_layout()
    return fig

def fig_capex_compare(base_capex: dict, opt_capex: dict):
    # base_capex / opt_capex from compute_capex_total(...)
    cats = ["Envelope", "Systems", "Fixtures", "Total"]
    b_vals = [
        base_capex["breakdown_nzd"]["Envelope"],
        base_capex["breakdown_nzd"]["Systems"],
        base_capex["breakdown_nzd"]["Fixtures"],
        base_capex["capex_total_nzd"],
    ]
    o_vals = [
        opt_capex["breakdown_nzd"]["Envelope"],
        opt_capex["breakdown_nzd"]["Systems"],
        opt_capex["breakdown_nzd"]["Fixtures"],
        opt_capex["capex_total_nzd"],
    ]
    df = pd.DataFrame({"Metric": cats, "Baseline": b_vals, "Option": o_vals})
    return fig_grouped_bar(df, "Capex comparison (absolute)", "NZD")

# =============================================================================
# DEFAULTS / STATE
# =============================================================================
HELP = {
    "closest_city": "Used to infer Climate Zone and HDD (Heating Degree Days, base 18°C). Default HDD uses a zone-average benchmark.",
    "hdd_custom": "Override HDD if you have a local/confirmed value. HDD is annual total degree-days (base 18°C).",
    "r_value": "R-value (m²K/W): higher is better insulation (lower heat loss).",
    "u_value": "U-value (W/m²K): lower is better (less heat loss).",
    "capex_env": "Unit capex schedule (NZD/m²) is a transparent early-stage placeholder (PRD Appendix).",
    "cop": "COP: coefficient of performance. Higher means less purchased electricity per delivered heat.",
    "install_cost": "Install cost is a transparent early-stage placeholder (PRD Appendix).",
    "flow": "Fixture flow/volume affects indoor water demand (BRANZ structure; values per PRD Appendix).",
    "appliance_toggle": "If Yes, dishwasher/washing machine water is included (water-only; no electricity for appliances yet).",
    "lighting": "Lighting electricity = count × watts × hours/day × 365. Early-stage placeholder; not a full lighting design.",
    "tariffs": "Tariffs can differ by location/provider. Set per scenario to avoid confusion.",
    "efs": "Emission factors: MfE (2024) guidance; adjust if you have a different factor boundary.",
}

def init_defaults():
    C = LOOKUP["constants"]
    du = LOOKUP["defaults"]["usage"]

    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", float(C["ceiling_height_m_default"]))
        st.session_state.setdefault(f"{p}_householdSize", 3)
        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        # climate
        st.session_state.setdefault(f"{p}_closestCity", PLACEHOLDER)
        st.session_state.setdefault(f"{p}_use_custom_hdd", False)
        st.session_state.setdefault(f"{p}_hdd_override_value", 2000.0)

        # envelope labels
        for k in ["roofRLabel", "wallRLabel", "floorRLabel", "windowULabel"]:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

        # systems labels
        for k in ["spaceHeatingSystem", "waterHeatingSystem"]:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

        # fixtures labels (IMPORTANT: default = placeholder, not prefilled)
        for k in ["toiletType", "showerType", "tapType"]:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

        # lighting
        st.session_state.setdefault(f"{p}_light_n", LOOKUP["defaults"]["lighting"]["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LOOKUP["defaults"]["lighting"]["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LOOKUP["defaults"]["lighting"]["hoursPerDay"])

        # appliances default = No (explicit)
        st.session_state.setdefault(f"{p}_wash_has", "No")
        st.session_state.setdefault(f"{p}_wash_cycles", LOOKUP["defaults"]["washing_machine"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_L", LOOKUP["defaults"]["washing_machine"]["waterPerCycle_L"])
        st.session_state.setdefault(f"{p}_dish_has", "No")
        st.session_state.setdefault(f"{p}_dish_cycles", LOOKUP["defaults"]["dishwasher"]["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_L", LOOKUP["defaults"]["dishwasher"]["waterPerCycle_L"])

        # custom performance + costs (defaults only used if user selects Custom)
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
        st.session_state.setdefault(f"{p}_hotWater_setpoint_C", float(du["hotWater_setpoint_C"]))
        st.session_state.setdefault(f"{p}_coldWater_inlet_C", float(du["coldWater_inlet_C"]))
        st.session_state.setdefault(f"{p}_toiletFlushes_ppd", float(du["toiletFlushes_per_person_day"]))
        st.session_state.setdefault(f"{p}_showers_ppd", float(du["showers_per_person_day"]))
        st.session_state.setdefault(f"{p}_minutes_per_shower", float(du["minutes_per_shower"]))
        st.session_state.setdefault(f"{p}_tapMinutes_ppd", float(du["tapMinutes_per_person_day"]))

        # tariffs + factors PER scenario (important change)
        st.session_state.setdefault(f"{p}_coef_elec_tariff", float(C["electricity_tariff_nzd_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_coef_water_tariff", float(C["water_tariff_nzd_per_m3_default"]))
        st.session_state.setdefault(f"{p}_coef_grid_ef", float(C["grid_emission_factor_kgco2e_per_kwh"]))
        st.session_state.setdefault(f"{p}_coef_water_ef", float(C["water_emission_factor_kgco2e_per_m3"]))

    # results state
    st.session_state.setdefault("baseline_result", None)
    st.session_state.setdefault("option_result", None)
    st.session_state.setdefault("baseline_inputs", None)
    st.session_state.setdefault("option_inputs", None)
    st.session_state.setdefault("option_seeded", False)

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

        "toilet_L_per_flush": resolve_fixture_value(prefix, toilet, "toilet"),
        "shower_L_per_min": resolve_fixture_value(prefix, shower, "shower"),
        "tap_L_per_min": resolve_fixture_value(prefix, tap, "tap"),

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

            "toilet_install_nzd": resolve_fixture_cost(prefix, toilet, "toilet"),
            "shower_install_nzd": resolve_fixture_cost(prefix, shower, "shower"),
            "tap_install_nzd": resolve_fixture_cost(prefix, tap, "tap"),
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

    # envelope + systems
    for k, label in [
        ("roofRValue", "Roof insulation (R-value)"),
        ("wallRValue", "Wall insulation (R-value)"),
        ("floorRValue", "Floor insulation (R-value)"),
        ("windowUValue", "Window type (U-value)"),
        ("spaceHeatingCOP", "Space heating system (COP)"),
        ("waterHeatingCOP", "Water heating system (COP)"),
    ]:
        if s[k] is None:
            missing.append(label)

    # fixtures
    for k, label in [
        ("toilet_L_per_flush", "Toilet type (L/flush)"),
        ("shower_L_per_min", "Shower type (L/min)"),
        ("tap_L_per_min", "Tap type (L/min)"),
    ]:
        if s[k] is None:
            missing.append(label)

    # appliances
    if s["washingMachine"]["hasAppliance"] is None:
        missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None:
        missing.append("Dishwasher (Yes/No)")
    return missing

def copy_baseline_to_option():
    keys = [k for k in st.session_state.keys() if k.startswith("b_")]
    for k in keys:
        st.session_state["o_" + k[2:]] = copy.deepcopy(st.session_state[k])

# =============================================================================
# UI BLOCKS (SIMPLIFIED)
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

def _value_line(label: str, perf: str, cost: str):
    st.caption(f"Selected: **{label}** | Performance: **{perf}** | Cost: **{cost}**")

def core_inputs_block(prefix: str):
    st.markdown("**Core inputs**")
    select_with_placeholder("Closest city", CITIES, key=f"{prefix}_closestCity", help_text=HELP["closest_city"])

    city = st.session_state[f"{prefix}_closestCity"]
    if city != PLACEHOLDER:
        z = LOOKUP["climate"]["zone_by_city"][city]
        h_default = LOOKUP["climate"]["hdd_by_zone_base18"][z]
        st.caption(f"Climate zone: **{z}** | Default HDD (base 18°C): **{h_default}**")

        st.checkbox("Use custom HDD input", key=f"{prefix}_use_custom_hdd", help=HELP["hdd_custom"])
        if st.session_state[f"{prefix}_use_custom_hdd"]:
            st.number_input(
                "Custom HDD (base 18°C)",
                min_value=0.0, max_value=6000.0, step=50.0,
                key=f"{prefix}_hdd_override_value",
                help=HELP["hdd_custom"],
            )

    st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea")
    st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight")
    st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize")
    st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea")

def envelope_block(prefix: str):
    st.markdown("**Thermal envelope**")

    # Roof
    select_with_placeholder("Roof insulation (R-value)", ROOF_OPTS, key=f"{prefix}_roofRLabel", help_text=HELP["r_value"])
    roof_label = st.session_state[f"{prefix}_roofRLabel"]
    if roof_label == "Custom":
        st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom")
        st.number_input("Roof capex (NZD/m² of roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom")
    if roof_label != PLACEHOLDER:
        R = resolve_from_lookup_or_custom(roof_label, f"{prefix}_roofR_custom", LOOKUP["thermal_envelope"]["roofR_m2K_per_W"])
        cost = resolve_capex_envelope("roof", roof_label, f"{prefix}_roofCost_custom")
        _value_line(roof_label, f"R = {fmt_num(R, 2)}", f"{fmt_num(cost, 0)} NZD/m²")

    # Wall
    select_with_placeholder("Wall insulation (R-value)", WALL_OPTS, key=f"{prefix}_wallRLabel", help_text=HELP["r_value"])
    wall_label = st.session_state[f"{prefix}_wallRLabel"]
    if wall_label == "Custom":
        st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom")
        st.number_input("Wall capex (NZD/m² of wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom")
    if wall_label != PLACEHOLDER:
        R = resolve_from_lookup_or_custom(wall_label, f"{prefix}_wallR_custom", LOOKUP["thermal_envelope"]["wallR_m2K_per_W"])
        cost = resolve_capex_envelope("wall", wall_label, f"{prefix}_wallCost_custom")
        _value_line(wall_label, f"R = {fmt_num(R, 2)}", f"{fmt_num(cost, 0)} NZD/m²")

    # Floor
    select_with_placeholder("Floor insulation (R-value)", FLOOR_OPTS, key=f"{prefix}_floorRLabel", help_text=HELP["r_value"])
    floor_label = st.session_state[f"{prefix}_floorRLabel"]
    if floor_label == "Custom":
        st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom")
        st.number_input("Floor capex (NZD/m² of floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom")
    if floor_label != PLACEHOLDER:
        R = resolve_from_lookup_or_custom(floor_label, f"{prefix}_floorR_custom", LOOKUP["thermal_envelope"]["floorR_m2K_per_W"])
        cost = resolve_capex_envelope("floor", floor_label, f"{prefix}_floorCost_custom")
        _value_line(floor_label, f"R = {fmt_num(R, 2)}", f"{fmt_num(cost, 0)} NZD/m²")

    # Windows
    select_with_placeholder("Window type (U-value)", WIN_OPTS, key=f"{prefix}_windowULabel", help_text=HELP["u_value"])
    win_label = st.session_state[f"{prefix}_windowULabel"]
    if win_label == "Custom":
        st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom")
        st.number_input("Windows capex (NZD/m² of window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom")
    if win_label != PLACEHOLDER:
        U = resolve_from_lookup_or_custom(win_label, f"{prefix}_windowU_custom", LOOKUP["thermal_envelope"]["windowU_W_per_m2K"])
        cost = resolve_capex_window(win_label, f"{prefix}_windowCost_custom")
        _value_line(win_label, f"U = {fmt_num(U, 2)}", f"{fmt_num(cost, 0)} NZD/m² (window)")

def systems_block(prefix: str):
    st.markdown("**Systems**")

    select_with_placeholder("Space heating system", SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help_text=HELP["cop"])
    space_sys = st.session_state[f"{prefix}_spaceHeatingSystem"]
    if space_sys == "Custom":
        st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_spaceCOP_custom")
        st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom")
    if space_sys != PLACEHOLDER:
        cop = resolve_cop(space_sys, f"{prefix}_spaceCOP_custom", "space_heating")
        cost = resolve_install_cost(space_sys, f"{prefix}_spaceInstall_custom", "space_heating")
        _value_line(space_sys, f"COP = {fmt_num(cop, 2)}", f"{fmt_num(cost, 0)} NZD")

    select_with_placeholder("Water heating system", WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help_text=HELP["cop"])
    water_sys = st.session_state[f"{prefix}_waterHeatingSystem"]
    if water_sys == "Custom":
        st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_waterCOP_custom")
        st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_waterInstall_custom")
    if water_sys != PLACEHOLDER:
        cop = resolve_cop(water_sys, f"{prefix}_waterCOP_custom", "water_heating")
        cost = resolve_install_cost(water_sys, f"{prefix}_waterInstall_custom", "water_heating")
        _value_line(water_sys, f"COP = {fmt_num(cop, 2)}", f"{fmt_num(cost, 0)} NZD")

def fixtures_block(prefix: str):
    st.markdown("**Fixtures + appliance water**")

    select_with_placeholder("Toilet type", TOILET_OPTS, key=f"{prefix}_toiletType", help_text=HELP["flow"])
    toilet_label = st.session_state[f"{prefix}_toiletType"]
    if toilet_label == "Custom":
        st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toilet_value_custom")
        st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom")
    if toilet_label != PLACEHOLDER:
        v = resolve_fixture_value(prefix, toilet_label, "toilet")
        c = resolve_fixture_cost(prefix, toilet_label, "toilet")
        _value_line(toilet_label, f"{fmt_num(v, 1)} L/flush", f"{fmt_num(c, 0)} NZD")

    select_with_placeholder("Shower type", SHOWER_OPTS, key=f"{prefix}_showerType", help_text=HELP["flow"])
    shower_label = st.session_state[f"{prefix}_showerType"]
    if shower_label == "Custom":
        st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_shower_value_custom")
        st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_shower_cost_custom")
    if shower_label != PLACEHOLDER:
        v = resolve_fixture_value(prefix, shower_label, "shower")
        c = resolve_fixture_cost(prefix, shower_label, "shower")
        _value_line(shower_label, f"{fmt_num(v, 1)} L/min", f"{fmt_num(c, 0)} NZD")

    select_with_placeholder("Tap type", TAP_OPTS, key=f"{prefix}_tapType", help_text=HELP["flow"])
    tap_label = st.session_state[f"{prefix}_tapType"]
    if tap_label == "Custom":
        st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tap_value_custom")
        st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tap_cost_custom")
    if tap_label != PLACEHOLDER:
        v = resolve_fixture_value(prefix, tap_label, "tap")
        c = resolve_fixture_cost(prefix, tap_label, "tap")
        _value_line(tap_label, f"{fmt_num(v, 1)} L/min", f"{fmt_num(c, 0)} NZD")

    st.markdown("**Washing machine (water only)**")
    select_with_placeholder("Has washing machine?", ["Yes", "No"], key=f"{prefix}_wash_has", help_text=HELP["appliance_toggle"])
    if st.session_state[f"{prefix}_wash_has"] == "Yes":
        st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles")
        st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L")

    st.markdown("**Dishwasher (water only)**")
    select_with_placeholder("Has dishwasher?", ["Yes", "No"], key=f"{prefix}_dish_has", help_text=HELP["appliance_toggle"])
    if st.session_state[f"{prefix}_dish_has"] == "Yes":
        st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles")
        st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L")

def lighting_block(prefix: str):
    st.markdown("**Lighting**")
    st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n", help=HELP["lighting"])
    st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts", help=HELP["lighting"])
    st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours", help=HELP["lighting"])

def usage_and_tariffs_block(prefix: str):
    st.markdown("**Usage assumptions + tariffs/factors**")

    st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
    st.number_input("Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")
    st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
    st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
    st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
    st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

    st.divider()
    st.caption("Tariffs (opex) and factors (carbon) — set per scenario to support different locations/providers.")
    st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"])
    st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"])
    st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", help=HELP["efs"])
    st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef", help=HELP["efs"])

def scenario_inputs_grid(prefix: str, title: str):
    st.subheader(title)

    with st.expander("Core, Envelope, Systems", expanded=True):
        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            core_inputs_block(prefix)
        with c2:
            envelope_block(prefix)
        with c3:
            systems_block(prefix)

    with st.expander("Fixtures, Lighting, Usage + Tariffs/Facts", expanded=False):
        c1, c2, c3 = st.columns(3, gap="large")
        with c1:
            fixtures_block(prefix)
        with c2:
            lighting_block(prefix)
        with c3:
            usage_and_tariffs_block(prefix)

# =============================================================================
# RESULTS RENDER
# =============================================================================
def kpi_table(base_r: dict, opt_r: dict | None):
    rows = [
        ("Total Energy (excl. plug loads)", "kWh/year", 1,
         base_r["totalElectricity_kwh_y"], None if opt_r is None else opt_r["totalElectricity_kwh_y"]),
        ("Energy Intensity", "kWh/m²/year", 2,
         base_r["energyIntensity_kwh_m2_y"], None if opt_r is None else opt_r["energyIntensity_kwh_m2_y"]),
        ("Water Consumption", "m³/year", 2,
         base_r["waterConsumption"]["V_total_m3_y"], None if opt_r is None else opt_r["waterConsumption"]["V_total_m3_y"]),
        ("Operational Carbon", "kgCO₂e/year", 1,
         base_r["carbon"]["CO2_total_kg_y"], None if opt_r is None else opt_r["carbon"]["CO2_total_kg_y"]),
        ("Annual Operating Cost (Opex)", "NZD/year", 0,
         base_r["opex"]["opex_total_nzd_y"], None if opt_r is None else opt_r["opex"]["opex_total_nzd_y"]),
    ]

    out = []
    for metric, unit, dec, b, o in rows:
        d = None if (o is None) else (o - b)
        out.append({
            "Metric": metric,
            "Baseline": fmt_num(b, dec),
            "Option": fmt_num(o, dec) if o is not None else "—",
            "Δ (Option−Base)": fmt_num(d, dec) if d is not None else "—",
            "Dir": direction_arrow(d) if d is not None else "—",
            "Unit": unit,
        })
    return pd.DataFrame(out)

def render_baseline_only(base_inputs: dict, base_r: dict):
    st.markdown("### Baseline results")

    st.dataframe(kpi_table(base_r, None), use_container_width=True, hide_index=True)

    df_energy = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
    ])

    b_w = base_r["waterConsumption"]["breakdown_m3_y"]
    df_water = pd.DataFrame([{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b_w.items()])

    df_carbon = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
    ])

    df_opex = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
    ])

    st.pyplot(fig_stacked_bar_vertical(df_energy, "Energy breakdown (Baseline)", "kWh/year"))
    st.pyplot(fig_stacked_bar_vertical(df_water, "Indoor water breakdown (Baseline)", "m³/year"))
    st.pyplot(fig_stacked_bar_vertical(df_carbon, "Operational carbon breakdown (Baseline)", "kgCO₂e/year"))
    st.pyplot(fig_stacked_bar_vertical(df_opex, "Opex breakdown (Baseline)", "NZD/year"))

def render_comparison(base_inputs: dict, base_r: dict, opt_inputs: dict, opt_r: dict):
    st.markdown("### Baseline vs Option")

    st.dataframe(kpi_table(base_r, opt_r), use_container_width=True, hide_index=True)

    df_kpi = pd.DataFrame([
        {"Metric": "Energy (kWh/y)", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
        {"Metric": "Energy Intensity", "Baseline": base_r["energyIntensity_kwh_m2_y"], "Option": opt_r["energyIntensity_kwh_m2_y"]},
        {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
        {"Metric": "Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
        {"Metric": "Opex (NZD/y)", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
    ])
    st.pyplot(fig_grouped_bar(df_kpi, "KPI comparison", "Value"))

    df_energy = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
        {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
        {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_total_kwh_y"]},
    ])
    st.pyplot(fig_stacked_bar_vertical(df_energy, "Energy breakdown (Baseline vs Option)", "kWh/year"))

    b_w = base_r["waterConsumption"]["breakdown_m3_y"]
    o_w = opt_r["waterConsumption"]["breakdown_m3_y"]
    df_water = pd.DataFrame(
        [{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b_w.items()] +
        [{"Scenario": "Option", "Component": k, "Value": v} for k, v in o_w.items()]
    )
    st.pyplot(fig_stacked_bar_vertical(df_water, "Indoor water breakdown (Baseline vs Option)", "m³/year"))

    df_carbon = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
        {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity_kg_y"]},
        {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water_kg_y"]},
    ])
    st.pyplot(fig_stacked_bar_vertical(df_carbon, "Operational carbon breakdown (Baseline vs Option)", "kgCO₂e/year"))

    df_opex = pd.DataFrame([
        {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
        {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
        {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["opex"]["opex_electricity_nzd_y"]},
        {"Scenario": "Option", "Component": "Water", "Value": opt_r["opex"]["opex_water_nzd_y"]},
    ])
    st.pyplot(fig_stacked_bar_vertical(df_opex, "Opex breakdown (Baseline vs Option)", "NZD/year"))

    base_cap = compute_capex_total(base_inputs)
    opt_cap = compute_capex_total(opt_inputs)
    st.pyplot(fig_capex_compare(base_cap, opt_cap))

# =============================================================================
# APP START
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.caption("Early-stage comparison tool. Simplified, indicative, non-certification. Calculations run only when you click Calculate.")

left, right = st.columns([1.8, 1.0], gap="large")

with left:
    st.subheader("Inputs")

    with st.expander("Step 1 — Baseline", expanded=True):
        scenario_inputs_grid("b", "Baseline")
        b1, b2 = st.columns([1.2, 0.8], gap="large")
        with b1:
            if st.button("Calculate Baseline", use_container_width=True, key="btn_calc_b"):
                b_s = get_scenario("b")
                missing = validate_scenario(b_s)
                if missing:
                    st.warning("Baseline incomplete: " + ", ".join(missing))
                else:
                    coeffs_b = get_coeffs("b")
                    st.session_state["baseline_inputs"] = b_s
                    st.session_state["baseline_result"] = calculate_scenario(b_s, coeffs_b)

                    # seed option once (auto-copy)
                    if not st.session_state.get("option_seeded", False):
                        copy_baseline_to_option()
                        st.session_state["option_seeded"] = True

                    st.success("Baseline calculated. See results on the right.")
        with b2:
            if st.button("Reset results", use_container_width=True, key="btn_reset_results"):
                st.session_state["baseline_result"] = None
                st.session_state["option_result"] = None
                st.session_state["baseline_inputs"] = None
                st.session_state["option_inputs"] = None

    with st.expander("Step 2 — Option (Upgrades)", expanded=bool(st.session_state.get("baseline_result"))):
        scenario_inputs_grid("o", "Option")

        c1, c2 = st.columns(2, gap="large")
        with c1:
            if st.button("Copy Baseline → Option", use_container_width=True, key="btn_copy_bo"):
                copy_baseline_to_option()
                st.session_state["option_seeded"] = True
                st.success("Option copied from Baseline.")
        with c2:
            if st.button("Calculate Option", use_container_width=True, key="btn_calc_o"):
                if not st.session_state.get("baseline_result"):
                    st.warning("Please calculate Baseline first.")
                else:
                    o_s = get_scenario("o")
                    missing = validate_scenario(o_s)
                    if missing:
                        st.warning("Option incomplete: " + ", ".join(missing))
                    else:
                        coeffs_o = get_coeffs("o")
                        st.session_state["option_inputs"] = o_s
                        st.session_state["option_result"] = calculate_scenario(o_s, coeffs_o)
                        st.success("Option calculated. Comparison is shown on the right.")

with right:
    st.subheader("Results")

    base_r = st.session_state.get("baseline_result")
    opt_r = st.session_state.get("option_result")
    base_inputs = st.session_state.get("baseline_inputs")
    opt_inputs = st.session_state.get("option_inputs")

    if not base_r:
        st.info("Fill Baseline inputs and click Calculate Baseline. Results will appear here.")
    else:
        render_baseline_only(base_inputs, base_r)

        if opt_r:
            st.divider()
            render_comparison(base_inputs, base_r, opt_inputs, opt_r)
        else:
            st.info("Now fill Option (or copy Baseline) and click Calculate Option to compare.")

    # Download JSON (only if baseline exists)
    if base_r:
        payload = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "baseline": {
                "coefficients": get_coeffs("b"),
                "inputs": base_inputs,
                "results": base_r,
            },
            "option": None if not opt_r else {
                "coefficients": get_coeffs("o"),
                "inputs": opt_inputs,
                "results": opt_r,
            },
            "notes": {
                "scope": "Early-stage decision support; not certification; not simulation.",
                "energy_boundary": "Space heating + water heating + lighting (excludes plug loads/appliances).",
                "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
                "capex_boundary": "Transparent unit-cost accounting. Not investment-grade.",
                "hot_water_model": "Hot water derived from end-use volumes using hot water fractions (toilet excluded).",
                "tariffs_and_factors": "Per-scenario (baseline vs option) to support different locations/providers.",
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
