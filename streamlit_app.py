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

def fmt_money(x: float, decimals: int = 0) -> str:
    if x is None:
        return "—"
    return f"${x:,.{decimals}f}"

def direction_arrow(delta: float) -> str:
    if delta is None:
        return "—"
    if delta < 0:
        return "▼"
    if delta > 0:
        return "▲"
    return "—"

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

def select_with_placeholder_fmt(label: str, options: list, key: str, format_func, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0

    def _fmt(x):
        if x == PLACEHOLDER:
            return PLACEHOLDER
        return format_func(x)

    return st.selectbox(label, full, index=idx, key=key, help=help_text, format_func=_fmt)

# =============================================================================
# FORMATTERS (UI labels that show performance + price)
# =============================================================================
def fmt_r(label: str, r_lookup: dict, capex_per_m2: dict, suffix: str):
    if label == "Custom":
        return "Custom (enter R & $)"
    r = float(r_lookup[label])
    bucket = _bucket_from_label(label)
    cost = float(capex_per_m2[bucket])
    return f"{label} (R={r:g}; {fmt_money(cost)} {suffix})"

def fmt_u_window(label: str, u_lookup: dict, win_cost_lookup: dict, suffix: str):
    if label == "Custom":
        return "Custom (enter U & $)"
    u = float(u_lookup[label])
    cost = float(win_cost_lookup[label])
    return f"{label} (U={u:g}; {fmt_money(cost)} {suffix})"

def fmt_system(label: str, cop_lookup: dict, install_lookup: dict):
    if label == "Custom":
        return "Custom (enter COP & $)"
    cop = float(cop_lookup[label])
    cost = float(install_lookup[label])
    return f"{label} (COP={cop:g}; {fmt_money(cost)} install)"

def fmt_toilet(label: str, lpf_lookup: dict, install_lookup: dict):
    if label == "Custom":
        return "Custom (enter L/flush & $)"
    lpf = float(lpf_lookup[label])
    cost = float(install_lookup[label])
    return f"{label} ({lpf:g} L/flush; {fmt_money(cost)} install)"

def fmt_flow_fixture(label: str, lpm_lookup: dict, install_lookup: dict):
    if label == "Custom":
        return "Custom (enter L/min & $)"
    lpm = float(lpm_lookup[label])
    cost = float(install_lookup[label])
    return f"{label} ({lpm:g} L/min; {fmt_money(cost)} install)"

def fmt_city(city: str):
    z = LOOKUP["climate"]["zone_by_city"].get(city, None)
    if z is None:
        return city
    hdd = LOOKUP["climate"]["hdd_by_zone_base18"][z]
    return f"{city} ({z.split('–')[0].strip()}; HDD={hdd:g})"

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
        return float(LOOKUP["fixtures"][kind]["l_per_flush" if kind == "toilet" else "l_per_min"][label])
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
        }
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
# CHARTS (ALL VERTICAL BARS)
# =============================================================================
def fig_grouped_bar_vertical(df: pd.DataFrame, title: str, y_label: str):
    """
    df columns: Metric, Baseline, Option
    """
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
    """
    df columns: Scenario, Component, Value
    """
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
    """
    Grouped vertical bar chart comparing baseline vs option capex by category.
    """
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
# DEFAULTS / STATE
# =============================================================================
def init_defaults():
    # calc state
    st.session_state.setdefault("baseline_calculated", False)
    st.session_state.setdefault("option_calculated", False)
    st.session_state.setdefault("baseline_inputs_snapshot", None)
    st.session_state.setdefault("option_inputs_snapshot", None)
    st.session_state.setdefault("baseline_results", None)
    st.session_state.setdefault("option_results", None)

    # per-scenario coefficients (tariffs + factors)
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_coef_grid_ef", float(LOOKUP["constants"]["grid_emission_factor_kgco2e_per_kwh"]))
        st.session_state.setdefault(f"{p}_coef_water_ef", float(LOOKUP["constants"]["water_emission_factor_kgco2e_per_m3"]))
        st.session_state.setdefault(f"{p}_coef_elec_tariff", float(LOOKUP["constants"]["electricity_tariff_nzd_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_coef_water_tariff", float(LOOKUP["constants"]["water_tariff_nzd_per_m3_default"]))

        # Core geometry defaults
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

    # categorical defaults (UNSELECTED) — per your request, do NOT prefill fixtures
    cat_keys = [
        "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "spaceHeatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

def invalidate_results():
    # if user changes inputs, they should re-calc
    st.session_state["baseline_calculated"] = False
    st.session_state["option_calculated"] = False
    st.session_state["baseline_inputs_snapshot"] = None
    st.session_state["option_inputs_snapshot"] = None
    st.session_state["baseline_results"] = None
    st.session_state["option_results"] = None

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

def copy_baseline_to_option():
    keys = [k for k in st.session_state.keys() if k.startswith("b_")]
    for k in keys:
        st.session_state["o_" + k[2:]] = copy.deepcopy(st.session_state[k])
    # copying inputs invalidates previous results
    invalidate_results()

def apply_code_minimum(prefix: str):
    # envelope
    st.session_state[f"{prefix}_roofRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_wallRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_floorRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_windowULabel"] = "Standard double glazed"

    # systems (reasonable early-stage defaults)
    st.session_state[f"{prefix}_spaceHeatingSystem"] = "Air-source Heat pump"
    st.session_state[f"{prefix}_waterHeatingSystem"] = "Electric storage cylinder"

    # fixtures remain unselected by design (per your request)
    st.session_state[f"{prefix}_toiletType"] = PLACEHOLDER
    st.session_state[f"{prefix}_showerType"] = PLACEHOLDER
    st.session_state[f"{prefix}_tapType"] = PLACEHOLDER

    invalidate_results()

# =============================================================================
# HELP TEXTS
# =============================================================================
HELP = {
    "closest_city": "Used to infer Climate Zone and HDD (Heating Degree Days, base 18°C). Default HDD uses a zone-average benchmark (InfraComfort; MSD).",
    "hdd_custom": "Override HDD if you have a local/confirmed value. HDD is annual total degree-days (base 18°C).",
    "r_value": "R-value (m²K/W): higher is better insulation (lower heat loss).",
    "u_value": "U-value (W/m²K): lower is better (less heat loss).",
    "cop": "COP: coefficient of performance. Higher means less purchased electricity per delivered heat.",
    "lighting": "Lighting electricity = count × watts × hours/day × 365. Early-stage placeholder; not a full lighting design.",
    "tariffs": "Tariffs/factors are scenario-specific (region/provider dependent). Adjust to your local bill/region.",
    "efs": "Defaults from MfE (2024) guidance (grid-average; water supply/wastewater factor).",
}

# =============================================================================
# APP START
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.caption("Early-stage comparison tool. Simplified, indicative, non-certification. Results appear in the right column after you click Calculate.")

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

# -----------------------------------------------------------------------------
# Layout: Left (inputs) + Right (results)
# Left uses "segments" (2 columns x 3 rows feel) via nested columns and expanders
# -----------------------------------------------------------------------------
left, right = st.columns([1.35, 1.0], gap="large")

# =============================================================================
# INPUT PANELS
# =============================================================================
def scenario_panel(prefix: str, title: str):
    st.subheader(title)

    # Presets + copy controls
    cA, cB = st.columns([1, 1])
    with cA:
        if st.button(f"Use Code Minimum preset ({title})", use_container_width=True, key=f"{prefix}_preset_code"):
            apply_code_minimum(prefix)
            st.rerun()
    with cB:
        if prefix == "o":
            if st.button("Copy Baseline → Option", use_container_width=True, key="btn_copy_b_to_o"):
                copy_baseline_to_option()
                st.rerun()

    # 3x2 feel: each row has 2 compact expanders
    r1c1, r1c2 = st.columns(2, gap="small")
    r2c1, r2c2 = st.columns(2, gap="small")
    r3c1, r3c2 = st.columns(2, gap="small")

    # Row 1
    with r1c1:
        with st.expander("Core inputs", expanded=True):
            select_with_placeholder_fmt(
                "Closest city",
                CITIES,
                key=f"{prefix}_closestCity",
                help_text=HELP["closest_city"],
                format_func=fmt_city,
            )
            city = st.session_state[f"{prefix}_closestCity"]
            if city != PLACEHOLDER:
                z = LOOKUP["climate"]["zone_by_city"][city]
                h_default = LOOKUP["climate"]["hdd_by_zone_base18"][z]
                st.caption(f"Default HDD (base 18°C): **{h_default:g}**")

                st.checkbox("Use custom HDD", key=f"{prefix}_use_custom_hdd", help=HELP["hdd_custom"])
                if st.session_state[f"{prefix}_use_custom_hdd"]:
                    st.number_input(
                        "Custom HDD (base 18°C)",
                        min_value=0.0, max_value=6000.0, step=50.0,
                        key=f"{prefix}_hdd_override_value",
                    )

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea", on_change=invalidate_results)
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight", on_change=invalidate_results)
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize", on_change=invalidate_results)
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea", on_change=invalidate_results)

    with r1c2:
        with st.expander("Thermal envelope", expanded=False):
            # Roof
            select_with_placeholder_fmt(
                "Roof insulation",
                ROOF_OPTS,
                key=f"{prefix}_roofRLabel",
                help_text=HELP["r_value"],
                format_func=lambda x: fmt_r(
                    x,
                    LOOKUP["thermal_envelope"]["roofR_m2K_per_W"],
                    LOOKUP["thermal_envelope"]["capex_per_m2"]["roof"],
                    "/m² roof",
                ),
            )
            if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom", on_change=invalidate_results)
                st.number_input("Roof capex (NZD/m² roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom", on_change=invalidate_results)

            # Wall
            select_with_placeholder_fmt(
                "Wall insulation",
                WALL_OPTS,
                key=f"{prefix}_wallRLabel",
                help_text=HELP["r_value"],
                format_func=lambda x: fmt_r(
                    x,
                    LOOKUP["thermal_envelope"]["wallR_m2K_per_W"],
                    LOOKUP["thermal_envelope"]["capex_per_m2"]["wall"],
                    "/m² wall",
                ),
            )
            if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom", on_change=invalidate_results)
                st.number_input("Wall capex (NZD/m² wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom", on_change=invalidate_results)

            # Floor
            select_with_placeholder_fmt(
                "Floor insulation",
                FLOOR_OPTS,
                key=f"{prefix}_floorRLabel",
                help_text=HELP["r_value"],
                format_func=lambda x: fmt_r(
                    x,
                    LOOKUP["thermal_envelope"]["floorR_m2K_per_W"],
                    LOOKUP["thermal_envelope"]["capex_per_m2"]["floor"],
                    "/m² floor",
                ),
            )
            if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom", on_change=invalidate_results)
                st.number_input("Floor capex (NZD/m² floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom", on_change=invalidate_results)

            # Windows
            select_with_placeholder_fmt(
                "Window type",
                WIN_OPTS,
                key=f"{prefix}_windowULabel",
                help_text=HELP["u_value"],
                format_func=lambda x: fmt_u_window(
                    x,
                    LOOKUP["thermal_envelope"]["windowU_W_per_m2K"],
                    LOOKUP["thermal_envelope"]["capex_per_m2"]["window"],
                    "/m² window",
                ),
            )
            if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom", on_change=invalidate_results)
                st.number_input("Windows capex (NZD/m² window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom", on_change=invalidate_results)

    # Row 2
    with r2c1:
        with st.expander("Systems", expanded=False):
            select_with_placeholder_fmt(
                "Space heating system",
                SPACE_SYS_OPTS,
                key=f"{prefix}_spaceHeatingSystem",
                help_text=HELP["cop"],
                format_func=lambda x: fmt_system(x, LOOKUP["systems"]["space_heating"]["cop"], LOOKUP["systems"]["space_heating"]["install_cost_nzd"]),
            )
            if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_spaceCOP_custom", on_change=invalidate_results)
                st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom", on_change=invalidate_results)

            select_with_placeholder_fmt(
                "Water heating system",
                WATER_SYS_OPTS,
                key=f"{prefix}_waterHeatingSystem",
                help_text=HELP["cop"],
                format_func=lambda x: fmt_system(x, LOOKUP["systems"]["water_heating"]["cop"], LOOKUP["systems"]["water_heating"]["install_cost_nzd"]),
            )
            if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_waterCOP_custom", on_change=invalidate_results)
                st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_waterInstall_custom", on_change=invalidate_results)

    with r2c2:
        with st.expander("Fixtures + appliance water", expanded=False):
            select_with_placeholder_fmt(
                "Toilet type",
                TOILET_OPTS,
                key=f"{prefix}_toiletType",
                format_func=lambda x: fmt_toilet(x, LOOKUP["fixtures"]["toilet"]["l_per_flush"], LOOKUP["fixtures"]["toilet"]["install_cost_nzd"]),
            )
            if st.session_state[f"{prefix}_toiletType"] == "Custom":
                st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toilet_value_custom", on_change=invalidate_results)
                st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom", on_change=invalidate_results)

            select_with_placeholder_fmt(
                "Shower type",
                SHOWER_OPTS,
                key=f"{prefix}_showerType",
                format_func=lambda x: fmt_flow_fixture(x, LOOKUP["fixtures"]["shower"]["l_per_min"], LOOKUP["fixtures"]["shower"]["install_cost_nzd"]),
            )
            if st.session_state[f"{prefix}_showerType"] == "Custom":
                st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_shower_value_custom", on_change=invalidate_results)
                st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_shower_cost_custom", on_change=invalidate_results)

            select_with_placeholder_fmt(
                "Tap type",
                TAP_OPTS,
                key=f"{prefix}_tapType",
                format_func=lambda x: fmt_flow_fixture(x, LOOKUP["fixtures"]["tap"]["l_per_min"], LOOKUP["fixtures"]["tap"]["install_cost_nzd"]),
            )
            if st.session_state[f"{prefix}_tapType"] == "Custom":
                st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tap_value_custom", on_change=invalidate_results)
                st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tap_cost_custom", on_change=invalidate_results)

            st.markdown("**Washing machine (water only)**")
            st.selectbox("Has washing machine?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_wash_has", on_change=invalidate_results)
            if st.session_state[f"{prefix}_wash_has"] == "Yes":
                st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles", on_change=invalidate_results)
                st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L", on_change=invalidate_results)

            st.markdown("**Dishwasher (water only)**")
            st.selectbox("Has dishwasher?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_dish_has", on_change=invalidate_results)
            if st.session_state[f"{prefix}_dish_has"] == "Yes":
                st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles", on_change=invalidate_results)
                st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L", on_change=invalidate_results)

    # Row 3
    with r3c1:
        with st.expander("Lighting", expanded=False):
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n", help=HELP["lighting"], on_change=invalidate_results)
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts", help=HELP["lighting"], on_change=invalidate_results)
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours", help=HELP["lighting"], on_change=invalidate_results)

    with r3c2:
        with st.expander("Usage + Tariffs + Emission factors", expanded=False):
            st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C", on_change=invalidate_results)
            st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C", on_change=invalidate_results)

            st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd", on_change=invalidate_results)
            st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd", on_change=invalidate_results)
            st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower", on_change=invalidate_results)
            st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd", on_change=invalidate_results)

            st.markdown("---")
            st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"], on_change=invalidate_results)
            st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"], on_change=invalidate_results)
            st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", help=HELP["efs"], on_change=invalidate_results)
            st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef", help=HELP["efs"], on_change=invalidate_results)

# =============================================================================
# LEFT COLUMN: Inputs for baseline, then option (gated by baseline calculation)
# =============================================================================
with left:
    scenario_panel("b", "Baseline")

    st.divider()
    base_now = get_scenario("b")
    missing_b = validate_scenario(base_now)

    calc_base_disabled = len(missing_b) > 0
    if calc_base_disabled:
        st.info("Baseline incomplete. Missing: " + ", ".join(missing_b))

    if st.button("Calculate Baseline", use_container_width=True, disabled=calc_base_disabled):
        base_coeffs = get_coeffs("b")
        st.session_state["baseline_inputs_snapshot"] = copy.deepcopy(base_now)
        st.session_state["baseline_results"] = calculate_scenario(base_now, base_coeffs)
        st.session_state["baseline_calculated"] = True
        st.session_state["option_calculated"] = False  # reset option calc
        st.session_state["option_results"] = None
        st.rerun()

    st.divider()

    # Option panel enabled only after baseline calculated
    if not st.session_state["baseline_calculated"]:
        st.warning("Calculate Baseline first to unlock Option.")
    else:
        scenario_panel("o", "Option")
        st.divider()

        opt_now = get_scenario("o")
        missing_o = validate_scenario(opt_now)
        calc_opt_disabled = len(missing_o) > 0

        if calc_opt_disabled:
            st.info("Option incomplete. Missing: " + ", ".join(missing_o))

        if st.button("Calculate Option + Compare", use_container_width=True, disabled=calc_opt_disabled):
            opt_coeffs = get_coeffs("o")
            st.session_state["option_inputs_snapshot"] = copy.deepcopy(opt_now)
            st.session_state["option_results"] = calculate_scenario(opt_now, opt_coeffs)
            st.session_state["option_calculated"] = True
            st.rerun()

# =============================================================================
# RIGHT COLUMN: Results (baseline first, then comparison)
# =============================================================================
with right:
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
            kpi_base.assign(Value=lambda d: d["Value"].map(lambda x: float(x))).assign(
                ValueFmt=lambda d: d["Value"].map(lambda x: fmt_num(x, 1))
            )[["Metric", "ValueFmt", "Unit"]].rename(columns={"ValueFmt": "Value"}),
            hide_index=True,
            use_container_width=True
        )

        st.divider()

        if not st.session_state["option_calculated"]:
            st.info("Fill Option inputs on the left, then click **Calculate Option + Compare**.")
        else:
            opt_r = st.session_state["option_results"]

            # KPI comparison table
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
                    "Unit": unit
                })
            st.markdown("### Comparison KPIs")
            st.dataframe(pd.DataFrame(out), hide_index=True, use_container_width=True)

            # Simple payback (based on total capex delta vs opex savings)
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
            st.markdown("### Charts (all vertical bars)")

            # KPI grouped bar
            df_kpi = pd.DataFrame([
                {"Metric": "Energy", "Baseline": base_r["totalElectricity_kwh_y"], "Option": opt_r["totalElectricity_kwh_y"]},
                {"Metric": "Water", "Baseline": base_r["waterConsumption"]["V_total_m3_y"], "Option": opt_r["waterConsumption"]["V_total_m3_y"]},
                {"Metric": "Carbon", "Baseline": base_r["carbon"]["CO2_total_kg_y"], "Option": opt_r["carbon"]["CO2_total_kg_y"]},
                {"Metric": "Opex", "Baseline": base_r["opex"]["opex_total_nzd_y"], "Option": opt_r["opex"]["opex_total_nzd_y"]},
            ])
            st.pyplot(fig_grouped_bar_vertical(df_kpi, "KPIs: Baseline vs Option", "Value"))

            # Energy stacked
            df_energy = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Baseline", "Component": "Lighting", "Value": base_r["lighting"]["Q_total_kwh_y"]},
                {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased_kwh_y"]},
                {"Scenario": "Option", "Component": "Lighting", "Value": opt_r["lighting"]["Q_total_kwh_y"]},
            ])
            st.pyplot(fig_stacked_bar_vertical(df_energy, "Energy breakdown (excl. plug loads)", "kWh/y"))

            # Water stacked
            b_w = base_r["waterConsumption"]["breakdown_m3_y"]
            o_w = opt_r["waterConsumption"]["breakdown_m3_y"]
            df_water = pd.DataFrame(
                [{"Scenario": "Baseline", "Component": k, "Value": v} for k, v in b_w.items()] +
                [{"Scenario": "Option", "Component": k, "Value": v} for k, v in o_w.items()]
            )
            st.pyplot(fig_stacked_bar_vertical(df_water, "Indoor water breakdown", "m³/y"))

            # Carbon stacked
            df_carbon = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity_kg_y"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water_kg_y"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity_kg_y"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water_kg_y"]},
            ])
            st.pyplot(fig_stacked_bar_vertical(df_carbon, "Operational carbon breakdown", "kgCO₂e/y"))

            # Opex stacked
            df_opex = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["opex"]["opex_electricity_nzd_y"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["opex"]["opex_water_nzd_y"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["opex"]["opex_electricity_nzd_y"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["opex"]["opex_water_nzd_y"]},
            ])
            st.pyplot(fig_stacked_bar_vertical(df_opex, "Opex breakdown", "NZD/y"))

            # Capex compare (NOT incremental)
            st.pyplot(fig_capex_compare(base_r["capex"]["detail_breakdown_nzd"], opt_r["capex"]["detail_breakdown_nzd"]))

            st.divider()

            # Download JSON
            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "baseline": {
                    "coefficients": get_coeffs("b"),
                    "inputs": st.session_state["baseline_inputs_snapshot"],
                    "results": base_r,
                },
                "option": {
                    "coefficients": get_coeffs("o"),
                    "inputs": st.session_state["option_inputs_snapshot"],
                    "results": opt_r,
                },
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
