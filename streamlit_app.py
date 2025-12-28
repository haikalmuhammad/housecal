# streamlit_app.py
import copy
import json
import math
import inspect
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="NZ Housing Sustainability Calculator (Prototype)", layout="wide")
PLACEHOLDER = "— Select —"

# =============================================================================
# VERSION-SAFE UI HELPERS
# =============================================================================
def _supports_kw(fn, kw: str) -> bool:
    try:
        return kw in inspect.signature(fn).parameters
    except Exception:
        return False

SUPPORTS_METRIC_BORDER = _supports_kw(st.metric, "border")
SUPPORTS_CONTAINER_BORDER = _supports_kw(st.container, "border")

def container_box(height: int | None = None, border: bool = True):
    """Version-safe bordered container."""
    if SUPPORTS_CONTAINER_BORDER:
        if height is None:
            return st.container(border=border)
        return st.container(height=height, border=border)
    return st.container(height=height) if height is not None else st.container()

def metric_card(
    label: str,
    value: str,
    delta: str | None = None,
    delta_color: str = "normal",
    help_text: str | None = None,
):
    """Version-safe metric with optional border."""
    kwargs = dict(label=label, value=value, delta=delta, delta_color=delta_color, help=help_text)
    kwargs = {k: v for k, v in kwargs.items() if v is not None}
    if SUPPORTS_METRIC_BORDER:
        st.metric(**kwargs, border=True)
    else:
        st.metric(**kwargs)

# =============================================================================
# HELPERS (text + formatting)
# =============================================================================
def help_default_source(
    what: str,
    default=None,
    source: str | None = None,
    notes: str | None = None,
    units: str | None = None,
) -> str:
    parts = [what]
    if default is not None:
        d = default
        if isinstance(d, float):
            d = f"{d:g}"
        parts.append(f"Default: {d}{(' ' + units) if units else ''}.")
    if source:
        parts.append(f"Source: {source}.")
    if notes:
        parts.append(notes)
    return " ".join(parts)

def fmt_num(x: float | None, decimals: int = 1) -> str:
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}"

def fmt_money_nzd(x: float | None, decimals: int = 0) -> str:
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}"

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

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None, on_change=None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text, on_change=on_change)

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
        # Thermo for water heating
        "cp_kj_per_kgC": 4.186,
    },
    "thermal_envelope": {
        # Source: MBIE (2023); BRANZ (2023)
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
        # Source: BRANZ (2023)
        "windowU_W_per_m2K": {
            "Single glazed": 5.8,
            "Standard double glazed": 3.0,
            "Low-E double glazed": 2.0,
            "High-performance triple glazed": 1.0,
        },
        # Source: PRD Appendix (market benchmark schedule)
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
        # Source: InfraComfort (n.d.); MSD (2006) — HDD base 18°C magnitude bands
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
        # Source: BRANZ (2023)
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
        # Source: BRANZ (2023)
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
            "hot_water_fractions": {"shower": 0.9, "tap": 0.4, "laundry": 0.5, "dishwasher": 1.0},
        },
        "core": {"floorArea": 120.0, "ceilingHeight": 2.4, "householdSize": 3, "windowArea": 30.0},
    },
}

# =============================================================================
# HELP TEXTS
# =============================================================================
def build_help(LK):
    return {
        "closest_city": help_default_source(
            what="Pick the closest major city. This sets Climate Zone and Heating Degree Days (HDD, base 18°C).",
            default="—",
            source="InfraComfort (n.d.); MSD (2006) bands; city→zone mapping embedded",
            notes="If you already know your HDD (from a report or a model), you can override it.",
        ),
        "use_custom_hdd": help_default_source(
            what="Use your own annual HDD instead of the default for your selected city.",
            default=False,
            source="User override",
            notes="HDD is a climate severity indicator. Higher HDD generally means a colder location.",
        ),
        "hdd_value": help_default_source(
            what="Annual Heating Degree Days (base 18°C).",
            default=2000.0,
            units="degree-days/year",
            source="User override (otherwise from climate zone defaults)",
        ),
        "floor_area": help_default_source(
            what="Conditioned floor area (inside the thermal envelope).",
            default=float(LK["defaults"]["core"]["floorArea"]),
            units="m²",
            source="Model default (editable)",
        ),
        "ceiling_height": help_default_source(
            what="Average ceiling height. Used to approximate wall area (early-stage geometry).",
            default=float(LK["defaults"]["core"]["ceilingHeight"]),
            units="m",
            source="Model default (editable)",
        ),
        "household_size": help_default_source(
            what="Number of people living in the home. Used for per-person water use assumptions.",
            default=int(LK["defaults"]["core"]["householdSize"]),
            units="people",
            source="Model default (editable)",
        ),
        "window_area": help_default_source(
            what="Total window area. Used for glazing heat loss.",
            default=float(LK["defaults"]["core"]["windowArea"]),
            units="m²",
            source="Model default (editable)",
        ),
        "light_n": help_default_source(
            what="Total number of light fixtures.",
            default=int(LK["defaults"]["lighting"]["numberOfLights"]),
            source="Model default (editable)",
        ),
        "light_watts": help_default_source(
            what="Average wattage per light. Many LED bulbs are around 6–12W.",
            default=float(LK["defaults"]["lighting"]["wattsPerLight"]),
            units="W",
            source="Model default (editable)",
        ),
        "light_hours": help_default_source(
            what="Average time lights are on each day.",
            default=float(LK["defaults"]["lighting"]["hoursPerDay"]),
            units="hours/day",
            source="Model default (editable)",
        ),
        "r_value": help_default_source(
            what="R-value (m²K/W). Higher means better insulation (less heat loss).",
            source="MBIE (2023); BRANZ (2023) banded defaults embedded",
            notes="Choose a band or select Custom to enter your own R-value and capex rate.",
        ),
        "u_value": help_default_source(
            what="U-value (W/m²K). Lower means better glazing performance (less heat loss).",
            source="BRANZ (2023) typical glazing defaults embedded",
            notes="Choose a glazing type or select Custom to enter your own U-value and window capex rate.",
        ),
        "cop": help_default_source(
            what="COP (Coefficient of Performance). Higher COP means less purchased electricity for the same delivered heat.",
            source="BRANZ (2023) typical systems embedded",
        ),
        "fixture": help_default_source(
            what="Fixture type sets the flow/flush rate and an install cost estimate.",
            source="BRANZ (2023) typical fixtures embedded",
            notes="Select Custom to enter your own litres/flush or L/min and install cost.",
        ),
        "wash_has": help_default_source(
            what="Include washing machine water use in the indoor water total.",
            default=bool(LK["defaults"]["washing_machine"]["hasAppliance"]),
            source="Model default (editable)",
        ),
        "dish_has": help_default_source(
            what="Include dishwasher water use in the indoor water total.",
            default=bool(LK["defaults"]["dishwasher"]["hasAppliance"]),
            source="Model default (editable)",
        ),
        "usage_general": help_default_source(
            what="Behaviour assumptions for indoor water use (per person).",
            source="Model defaults (editable)",
            notes="If you are unsure, keep defaults. If you want a closer fit, adjust to match your household habits.",
        ),
        "hw_frac": help_default_source(
            what="Hot water fraction (0–1) for each end-use. Toilets are treated as cold water.",
            default="Shower 0.9; Tap 0.4; Laundry 0.5; Dishwasher 1.0",
            source="BRANZ (2023) placeholders + user override",
        ),
        "tariffs": help_default_source(
            what="Tariffs vary by region and provider. Adjust these to match your bill for better cost estimates.",
            default=f"Electricity {LK['constants']['electricity_tariff_nzd_per_kwh_default']} NZD/kWh; Water {LK['constants']['water_tariff_nzd_per_m3_default']} NZD/m³",
            source="Electricity Authority (2024); Auckland Council (2025)",
        ),
        "efs": help_default_source(
            what="Emission factors used to convert electricity and water into operational carbon (kgCO₂e).",
            default=f"Grid {LK['constants']['grid_emission_factor_kgco2e_per_kwh']} kgCO₂e/kWh; Water {LK['constants']['water_emission_factor_kgco2e_per_m3']} kgCO₂e/m³",
            source="MfE (2024)",
            notes="Adjust only if you have a justified factor for your reporting boundary.",
        ),
    }

HELP = build_help(LOOKUP)

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
    return {"roof": roof_area, "wall": wall_area, "floor": floor_area, "window": window_area, "perimeter": perimeter}

def calculate_space_heating(s: dict) -> dict:
    HDD = s["HDD_base18"]
    geom = _geometry_areas(s["floorArea"], s["ceilingHeight"], s["windowArea"])
    areas = {k: geom[k] for k in ["roof", "wall", "floor", "window"]}

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
        "areas_m2": areas,
        "U_values": {"Roof": roofU, "Walls": wallU, "Floor": floorU, "Windows": winU},
        "breakdown_W_per_K": {"Roof": H_roof, "Walls": H_wall, "Floor": H_floor, "Windows": H_window},
        "geometry": {"perimeter_m": geom["perimeter"]},
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
    fr = s["usage"]["hot_water_fractions"]
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
        "fractions_used": fr,
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
    geom = _geometry_areas(s["floorArea"], s["ceilingHeight"], s["windowArea"])
    areas = {k: geom[k] for k in ["roof", "wall", "floor", "window"]}
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
        "unit_rates": {
            "Roof NZD/m²": cap["roof_nzd_per_m2"],
            "Wall NZD/m²": cap["wall_nzd_per_m2"],
            "Floor NZD/m²": cap["floor_nzd_per_m2"],
            "Window NZD/m²": cap["window_nzd_per_m2_window"],
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
# STATE + FLOW
# =============================================================================
COPY_KEYS = [
    "closestCity","use_custom_hdd","hdd_override_value",
    "floorArea","ceilingHeight","householdSize","windowArea",
    "roofRLabel","roofR_custom","roofCost_custom",
    "wallRLabel","wallR_custom","wallCost_custom",
    "floorRLabel","floorR_custom","floorCost_custom",
    "windowULabel","windowU_custom","windowCost_custom",
    "spaceHeatingSystem","spaceCOP_custom","spaceInstall_custom",
    "waterHeatingSystem","waterCOP_custom","waterInstall_custom",
    "toiletType","toilet_value_custom","toilet_cost_custom",
    "showerType","shower_value_custom","shower_cost_custom",
    "tapType","tap_value_custom","tap_cost_custom",
    "wash_has","wash_cycles","wash_L",
    "dish_has","dish_cycles","dish_L",
    "light_n","light_watts","light_hours",
    "hotWater_setpoint_C","coldWater_inlet_C",
    "toiletFlushes_ppd","showers_ppd","minutes_per_shower","tapMinutes_ppd",
    "hw_frac_shower","hw_frac_tap","hw_frac_laundry","hw_frac_dishwasher",
    "coef_grid_ef","coef_water_ef","coef_elec_tariff","coef_water_tariff",
]

def init_defaults():
    st.session_state.setdefault("base_ready", False)
    st.session_state.setdefault("improve_unlocked", False)
    st.session_state.setdefault("improve_seeded", False)
    st.session_state.setdefault("compare_ready", False)
    st.session_state.setdefault("last_calc_error", None)

    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_coef_grid_ef", float(LOOKUP["constants"]["grid_emission_factor_kgco2e_per_kwh"]))
        st.session_state.setdefault(f"{p}_coef_water_ef", float(LOOKUP["constants"]["water_emission_factor_kgco2e_per_m3"]))
        st.session_state.setdefault(f"{p}_coef_elec_tariff", float(LOOKUP["constants"]["electricity_tariff_nzd_per_kwh_default"]))
        st.session_state.setdefault(f"{p}_coef_water_tariff", float(LOOKUP["constants"]["water_tariff_nzd_per_m3_default"]))

        st.session_state.setdefault(f"{p}_floorArea", float(LOOKUP["defaults"]["core"]["floorArea"]))
        st.session_state.setdefault(f"{p}_ceilingHeight", float(LOOKUP["defaults"]["core"]["ceilingHeight"]))
        st.session_state.setdefault(f"{p}_householdSize", int(LOOKUP["defaults"]["core"]["householdSize"]))
        st.session_state.setdefault(f"{p}_windowArea", float(LOOKUP["defaults"]["core"]["windowArea"]))

        st.session_state.setdefault(f"{p}_light_n", int(LOOKUP["defaults"]["lighting"]["numberOfLights"]))
        st.session_state.setdefault(f"{p}_light_watts", float(LOOKUP["defaults"]["lighting"]["wattsPerLight"]))
        st.session_state.setdefault(f"{p}_light_hours", float(LOOKUP["defaults"]["lighting"]["hoursPerDay"]))

        # default no appliances
        st.session_state.setdefault(f"{p}_wash_has", "No")
        st.session_state.setdefault(f"{p}_wash_cycles", float(LOOKUP["defaults"]["washing_machine"]["cyclesPerWeek"]))
        st.session_state.setdefault(f"{p}_wash_L", float(LOOKUP["defaults"]["washing_machine"]["waterPerCycle_L"]))
        st.session_state.setdefault(f"{p}_dish_has", "No")
        st.session_state.setdefault(f"{p}_dish_cycles", float(LOOKUP["defaults"]["dishwasher"]["cyclesPerWeek"]))
        st.session_state.setdefault(f"{p}_dish_L", float(LOOKUP["defaults"]["dishwasher"]["waterPerCycle_L"]))

        st.session_state.setdefault(f"{p}_closestCity", PLACEHOLDER)
        st.session_state.setdefault(f"{p}_use_custom_hdd", False)
        st.session_state.setdefault(f"{p}_hdd_override_value", 2000.0)

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

        hw = du["hot_water_fractions"]
        st.session_state.setdefault(f"{p}_hw_frac_shower", float(hw["shower"]))
        st.session_state.setdefault(f"{p}_hw_frac_tap", float(hw["tap"]))
        st.session_state.setdefault(f"{p}_hw_frac_laundry", float(hw["laundry"]))
        st.session_state.setdefault(f"{p}_hw_frac_dishwasher", float(hw["dishwasher"]))

    cat_keys = [
        "roofRLabel", "wallRLabel", "floorRLabel", "windowULabel",
        "spaceHeatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

def seed_improve_from_base_once():
    for suffix in COPY_KEYS:
        b_key = f"b_{suffix}"
        o_key = f"o_{suffix}"
        if b_key in st.session_state:
            st.session_state[o_key] = copy.deepcopy(st.session_state[b_key])
    st.session_state["improve_seeded"] = True

def apply_code_minimum(prefix: str):
    st.session_state[f"{prefix}_roofRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_wallRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_floorRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_windowULabel"] = "Standard double glazed"

    st.session_state[f"{prefix}_spaceHeatingSystem"] = "Electric resistance heater"
    st.session_state[f"{prefix}_waterHeatingSystem"] = "Electric storage cylinder"

    st.session_state[f"{prefix}_toiletType"] = "Dual flush standard (avg 5 L)"
    st.session_state[f"{prefix}_showerType"] = "Standard"
    st.session_state[f"{prefix}_tapType"] = "Standard"

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

def invalidate_compare():
    # Comparison stays active; Streamlit rerun will refresh results automatically.
    return

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
            "hot_water_fractions": {
                "shower": float(st.session_state[f"{prefix}_hw_frac_shower"]),
                "tap": float(st.session_state[f"{prefix}_hw_frac_tap"]),
                "laundry": float(st.session_state[f"{prefix}_hw_frac_laundry"]),
                "dishwasher": float(st.session_state[f"{prefix}_hw_frac_dishwasher"]),
            },
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
# INPUT PANELS
# =============================================================================
def show_city_caption(prefix: str):
    city = st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER)
    if city == PLACEHOLDER:
        return
    z = LOOKUP["climate"]["zone_by_city"].get(city)
    if z:
        hdd = LOOKUP["climate"]["hdd_by_zone_base18"][z]
        st.caption(f"Climate zone: **{z}** · Default HDD (base 18°C): **{hdd:g}**")

def _caption_perf_price_envelope(element: str, label: str, custom_val_key: str, custom_cost_key: str, unit_perf: str, unit_cost: str):
    if label == PLACEHOLDER:
        return
    if label == "Custom":
        perf = st.session_state.get(custom_val_key)
        cost = st.session_state.get(custom_cost_key)
        st.caption(f"Selected: **Custom** · Performance: **{fmt_num(perf, 2)} {unit_perf}** · Cost: **{fmt_money_nzd(cost)} {unit_cost}**")
        return
    if element == "window":
        perf = LOOKUP["thermal_envelope"]["windowU_W_per_m2K"][label]
        cost = LOOKUP["thermal_envelope"]["capex_per_m2"]["window"][label]
        st.caption(f"Selected: **{label}** · Performance: **{fmt_num(float(perf), 2)} {unit_perf}** · Cost: **{fmt_money_nzd(float(cost))} {unit_cost}**")
    else:
        perf = LOOKUP["thermal_envelope"][f"{element}R_m2K_per_W"][label]
        bucket = _bucket_from_label(label)
        cost = LOOKUP["thermal_envelope"]["capex_per_m2"][element][bucket]
        st.caption(f"Selected: **{label}** · Performance: **{fmt_num(float(perf), 2)} {unit_perf}** · Cost: **{fmt_money_nzd(float(cost))} {unit_cost}**")

def _caption_perf_price_system(sys_block: str, label: str, custom_cop_key: str, custom_cost_key: str):
    if label == PLACEHOLDER:
        return
    if label == "Custom":
        cop = st.session_state.get(custom_cop_key)
        cost = st.session_state.get(custom_cost_key)
        st.caption(f"Selected: **Custom** · Efficiency: **COP {fmt_num(cop, 2)}** · Install: **NZD {fmt_money_nzd(cost)}**")
        return
    cop = LOOKUP["systems"][sys_block]["cop"][label]
    cost = LOOKUP["systems"][sys_block]["install_cost_nzd"][label]
    st.caption(f"Selected: **{label}** · Efficiency: **COP {fmt_num(float(cop), 2)}** · Install: **NZD {fmt_money_nzd(float(cost))}**")

def _caption_perf_price_fixture(kind: str, label: str, custom_val_key: str, custom_cost_key: str):
    if label == PLACEHOLDER:
        return
    if label == "Custom":
        v = st.session_state.get(custom_val_key)
        c = st.session_state.get(custom_cost_key)
        u = "L/flush" if kind == "toilet" else "L/min"
        st.caption(f"Selected: **Custom** · Flow: **{fmt_num(v, 1)} {u}** · Install: **NZD {fmt_money_nzd(c)}**")
        return
    v = LOOKUP["fixtures"][kind]["l_per_flush" if kind == "toilet" else "l_per_min"][label]
    c = LOOKUP["fixtures"][kind]["install_cost_nzd"][label]
    u = "L/flush" if kind == "toilet" else "L/min"
    st.caption(f"Selected: **{label}** · Flow: **{fmt_num(float(v), 1)} {u}** · Install: **NZD {fmt_money_nzd(float(c))}**")

def scenario_panel(prefix: str, title: str):
    st.markdown(f"**{title}**")

    st.button(
        f"Use Code Minimum ({title})",
        key=f"{prefix}_btn_code_min",
        use_container_width=True,
        on_click=apply_code_minimum,
        args=(prefix,),
    )
    st.caption("Quick fill: this sets a typical Code Minimum baseline. You can then adjust item-by-item.")

    core_expanded = (prefix == "b")
    env_expanded = (prefix == "b")
    opt_expanded = False

    # 1) Core + Climate + Lighting
    with st.expander("Core climate + lighting", expanded=core_expanded):
        c1, c2 = st.columns(2, gap="large")

        with c1:
            st.markdown("**Building info**")
            select_with_placeholder("Closest city", CITIES, key=f"{prefix}_closestCity", help_text=HELP["closest_city"], on_change=invalidate_compare)
            show_city_caption(prefix)

            st.checkbox("Use custom HDD", key=f"{prefix}_use_custom_hdd", help=HELP["use_custom_hdd"], on_change=invalidate_compare)
            if st.session_state[f"{prefix}_use_custom_hdd"]:
                st.number_input(
                    "Custom HDD (base 18°C)",
                    min_value=0.0,
                    max_value=6000.0,
                    step=50.0,
                    key=f"{prefix}_hdd_override_value",
                    help=HELP["hdd_value"],
                    on_change=invalidate_compare,
                )

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0,
                            key=f"{prefix}_floorArea", help=HELP["floor_area"], on_change=invalidate_compare)
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1,
                            key=f"{prefix}_ceilingHeight", help=HELP["ceiling_height"], on_change=invalidate_compare)
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1,
                            key=f"{prefix}_householdSize", help=HELP["household_size"], on_change=invalidate_compare)
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0,
                            key=f"{prefix}_windowArea", help=HELP["window_area"], on_change=invalidate_compare)

        with c2:
            st.markdown("**Lighting**")
            st.number_input("Number of lights", min_value=0, max_value=200, step=1,
                            key=f"{prefix}_light_n", help=HELP["light_n"], on_change=invalidate_compare)
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0,
                            key=f"{prefix}_light_watts", help=HELP["light_watts"], on_change=invalidate_compare)
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5,
                            key=f"{prefix}_light_hours", help=HELP["light_hours"], on_change=invalidate_compare)
            st.caption("Lighting energy = count × watts × hours/day × 365 ÷ 1000")

    # 2) Envelope + Systems + Water
    with st.expander("Envelope + systems + water", expanded=env_expanded):
        ec1, ec2 = st.columns(2, gap="large")

        with ec1:
            st.markdown("**Thermal envelope**")
            select_with_placeholder("Roof insulation", ROOF_OPTS, key=f"{prefix}_roofRLabel", help_text=HELP["r_value"], on_change=invalidate_compare)
            _caption_perf_price_envelope("roof", st.session_state[f"{prefix}_roofRLabel"], f"{prefix}_roofR_custom", f"{prefix}_roofCost_custom", "m²K/W", "NZD/m² (roof)")
            if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1,
                                key=f"{prefix}_roofR_custom", help=HELP["r_value"], on_change=invalidate_compare)
                st.number_input("Roof capex (NZD/m² roof)", min_value=0.0, max_value=2000.0, step=10.0,
                                key=f"{prefix}_roofCost_custom", on_change=invalidate_compare)

            select_with_placeholder("Wall insulation", WALL_OPTS, key=f"{prefix}_wallRLabel", help_text=HELP["r_value"], on_change=invalidate_compare)
            _caption_perf_price_envelope("wall", st.session_state[f"{prefix}_wallRLabel"], f"{prefix}_wallR_custom", f"{prefix}_wallCost_custom", "m²K/W", "NZD/m² (wall)")
            if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1,
                                key=f"{prefix}_wallR_custom", help=HELP["r_value"], on_change=invalidate_compare)
                st.number_input("Wall capex (NZD/m² wall)", min_value=0.0, max_value=2000.0, step=10.0,
                                key=f"{prefix}_wallCost_custom", on_change=invalidate_compare)

            select_with_placeholder("Floor insulation", FLOOR_OPTS, key=f"{prefix}_floorRLabel", help_text=HELP["r_value"], on_change=invalidate_compare)
            _caption_perf_price_envelope("floor", st.session_state[f"{prefix}_floorRLabel"], f"{prefix}_floorR_custom", f"{prefix}_floorCost_custom", "m²K/W", "NZD/m² (floor)")
            if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1,
                                key=f"{prefix}_floorR_custom", help=HELP["r_value"], on_change=invalidate_compare)
                st.number_input("Floor capex (NZD/m² floor)", min_value=0.0, max_value=2000.0, step=10.0,
                                key=f"{prefix}_floorCost_custom", on_change=invalidate_compare)

            select_with_placeholder("Window type", WIN_OPTS, key=f"{prefix}_windowULabel", help_text=HELP["u_value"], on_change=invalidate_compare)
            _caption_perf_price_envelope("window", st.session_state[f"{prefix}_windowULabel"], f"{prefix}_windowU_custom", f"{prefix}_windowCost_custom", "W/m²K", "NZD/m² (window)")
            if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1,
                                key=f"{prefix}_windowU_custom", help=HELP["u_value"], on_change=invalidate_compare)
                st.number_input("Windows capex (NZD/m² window)", min_value=0.0, max_value=5000.0, step=25.0,
                                key=f"{prefix}_windowCost_custom", on_change=invalidate_compare)

        with ec2:
            st.markdown("**Systems**")
            select_with_placeholder("Space heating system", SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help_text=HELP["cop"], on_change=invalidate_compare)
            _caption_perf_price_system("space_heating", st.session_state[f"{prefix}_spaceHeatingSystem"], f"{prefix}_spaceCOP_custom", f"{prefix}_spaceInstall_custom")
            if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1,
                                key=f"{prefix}_spaceCOP_custom", help=HELP["cop"], on_change=invalidate_compare)
                st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0,
                                key=f"{prefix}_spaceInstall_custom", on_change=invalidate_compare)

            select_with_placeholder("Water heating system", WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help_text=HELP["cop"], on_change=invalidate_compare)
            _caption_perf_price_system("water_heating", st.session_state[f"{prefix}_waterHeatingSystem"], f"{prefix}_waterCOP_custom", f"{prefix}_waterInstall_custom")
            if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1,
                                key=f"{prefix}_waterCOP_custom", help=HELP["cop"], on_change=invalidate_compare)
                st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0,
                                key=f"{prefix}_waterInstall_custom", on_change=invalidate_compare)

            st.divider()
            st.markdown("**Water fixtures + appliances**")

            select_with_placeholder("Toilet type", TOILET_OPTS, key=f"{prefix}_toiletType", help_text=HELP["fixture"], on_change=invalidate_compare)
            _caption_perf_price_fixture("toilet", st.session_state[f"{prefix}_toiletType"], f"{prefix}_toilet_value_custom", f"{prefix}_toilet_cost_custom")
            if st.session_state[f"{prefix}_toiletType"] == "Custom":
                st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5,
                                key=f"{prefix}_toilet_value_custom", help=HELP["fixture"], on_change=invalidate_compare)
                st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0,
                                key=f"{prefix}_toilet_cost_custom", on_change=invalidate_compare)

            select_with_placeholder("Shower type", SHOWER_OPTS, key=f"{prefix}_showerType", help_text=HELP["fixture"], on_change=invalidate_compare)
            _caption_perf_price_fixture("shower", st.session_state[f"{prefix}_showerType"], f"{prefix}_shower_value_custom", f"{prefix}_shower_cost_custom")
            if st.session_state[f"{prefix}_showerType"] == "Custom":
                st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5,
                                key=f"{prefix}_shower_value_custom", help=HELP["fixture"], on_change=invalidate_compare)
                st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0,
                                key=f"{prefix}_shower_cost_custom", on_change=invalidate_compare)

            select_with_placeholder("Tap type", TAP_OPTS, key=f"{prefix}_tapType", help_text=HELP["fixture"], on_change=invalidate_compare)
            _caption_perf_price_fixture("tap", st.session_state[f"{prefix}_tapType"], f"{prefix}_tap_value_custom", f"{prefix}_tap_cost_custom")
            if st.session_state[f"{prefix}_tapType"] == "Custom":
                st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5,
                                key=f"{prefix}_tap_value_custom", help=HELP["fixture"], on_change=invalidate_compare)
                st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0,
                                key=f"{prefix}_tap_cost_custom", on_change=invalidate_compare)

            st.divider()
            st.selectbox("Has washing machine?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_wash_has", help=HELP["wash_has"], on_change=invalidate_compare)
            if st.session_state[f"{prefix}_wash_has"] == "Yes":
                st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles", on_change=invalidate_compare)
                st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L", on_change=invalidate_compare)

            st.selectbox("Has dishwasher?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_dish_has", help=HELP["dish_has"], on_change=invalidate_compare)
            if st.session_state[f"{prefix}_dish_has"] == "Yes":
                st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles", on_change=invalidate_compare)
                st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L", on_change=invalidate_compare)

    # 3) Optional
    with st.expander("Optional: usage + fractions + tariffs + emissions", expanded=opt_expanded):
        oc1, oc2 = st.columns(2, gap="large")

        with oc1:
            st.markdown("**Usage assumptions**")
            st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C", help=HELP["usage_general"], on_change=invalidate_compare)
            st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C", help=HELP["usage_general"], on_change=invalidate_compare)
            st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd", help=HELP["usage_general"], on_change=invalidate_compare)
            st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd", help=HELP["usage_general"], on_change=invalidate_compare)
            st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower", help=HELP["usage_general"], on_change=invalidate_compare)
            st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd", help=HELP["usage_general"], on_change=invalidate_compare)

        with oc2:
            st.markdown("**Hot water fractions**")
            st.caption(HELP["hw_frac"])
            st.slider("Shower hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_shower", on_change=invalidate_compare)
            st.slider("Tap hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_tap", on_change=invalidate_compare)
            st.slider("Laundry hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_laundry", on_change=invalidate_compare)
            st.slider("Dishwasher hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_dishwasher", on_change=invalidate_compare)

            st.divider()
            st.markdown("**Tariffs + emission factors**")
            st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"], on_change=invalidate_compare)
            st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"], on_change=invalidate_compare)
            st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", help=HELP["efs"], on_change=invalidate_compare)
            st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef", help=HELP["efs"], on_change=invalidate_compare)

# =============================================================================
# KPI RENDERING (SIDE-BY-SIDE BASE vs IMPROVE) — BOTH SIDES SHOW DELTA
# =============================================================================
def kpi_pair_row(title: str, unit: str, base: float, imp: float | None, decimals: int, lower_is_better: bool = True):
    with container_box(border=True):
        st.markdown(f"**{title} ({unit})**")

        col_b, col_o = st.columns(2, gap="small")
        with col_b:
            if imp is None:
                metric_card("Base scenario", f"{fmt_num(base, decimals)}")
            else:
                delta_b = base - imp
                dc = "inverse" if lower_is_better else "normal"
                metric_card("Base scenario", f"{fmt_num(base, decimals)}", delta=f"{fmt_num(delta_b, decimals)}", delta_color=dc)

        with col_o:
            if imp is None:
                metric_card("Improve scenario", "—")
            else:
                delta_o = imp - base
                dc = "inverse" if lower_is_better else "normal"
                metric_card("Improve scenario", f"{fmt_num(imp, decimals)}", delta=f"{fmt_num(delta_o, decimals)}", delta_color=dc)

def payback_box(pb_years: float | None, note: str | None):
    with container_box(border=True):
        st.markdown("**Simple payback (years)**")
        metric_card("Payback", "—" if pb_years is None else fmt_num(pb_years, 1))
        if note:
            st.caption(note)

# =============================================================================
# CHARTS
# =============================================================================
def plot_breakdown_stacked(title: str, y_title: str, categories: list[str], b_vals: list[float], o_vals: list[float] | None):
    x = ["Base"] + (["Improve"] if o_vals is not None else [])
    fig = go.Figure()
    for i, cat in enumerate(categories):
        y = [b_vals[i]] + ([o_vals[i]] if o_vals is not None else [])
        fig.add_trace(go.Bar(name=cat, x=x, y=y))

    fig.update_layout(
        title=title,
        barmode="stack",
        height=330,
        margin=dict(l=20, r=20, t=55, b=45),
        yaxis_title=y_title,
        legend_title_text="",
    )
    st.plotly_chart(fig, use_container_width=True)

def plot_electricity_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Space heating", "Water heating", "Lighting"]
    b_vals = [
        b_res["spaceHeating"]["Q_purchased_kwh_y"],
        b_res["waterHeating"]["Q_purchased_kwh_y"],
        b_res["lighting"]["Q_total_kwh_y"],
    ]
    o_vals = None
    if o_res:
        o_vals = [
            o_res["spaceHeating"]["Q_purchased_kwh_y"],
            o_res["waterHeating"]["Q_purchased_kwh_y"],
            o_res["lighting"]["Q_total_kwh_y"],
        ]
    plot_breakdown_stacked("1) Electricity breakdown (Base vs Improve)", "kWh/year", cats, b_vals, o_vals)

def plot_water_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Toilets", "Showers", "Taps", "Laundry", "Dishwasher"]
    b_br = b_res["waterConsumption"]["breakdown_m3_y"]
    b_vals = [b_br.get(c, 0.0) for c in cats]
    o_vals = None
    if o_res:
        o_br = o_res["waterConsumption"]["breakdown_m3_y"]
        o_vals = [o_br.get(c, 0.0) for c in cats]
    plot_breakdown_stacked("2) Water breakdown (Base vs Improve)", "m³/year", cats, b_vals, o_vals)

def plot_carbon_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Electricity emissions", "Water emissions"]
    b_vals = [b_res["carbon"]["CO2_electricity_kg_y"], b_res["carbon"]["CO2_water_kg_y"]]
    o_vals = None
    if o_res:
        o_vals = [o_res["carbon"]["CO2_electricity_kg_y"], o_res["carbon"]["CO2_water_kg_y"]]
    plot_breakdown_stacked("3) Operational carbon breakdown (Base vs Improve)", "kgCO₂e/year", cats, b_vals, o_vals)

def plot_opex_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Electricity cost", "Water cost"]
    b_vals = [b_res["opex"]["opex_electricity_nzd_y"], b_res["opex"]["opex_water_nzd_y"]]
    o_vals = None
    if o_res:
        o_vals = [o_res["opex"]["opex_electricity_nzd_y"], o_res["opex"]["opex_water_nzd_y"]]
    plot_breakdown_stacked("4) Operating cost breakdown (Base vs Improve)", "NZD/year", cats, b_vals, o_vals)

def plot_capex_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Envelope", "Systems", "Fixtures"]
    b = b_res["capex"]["breakdown_nzd"]
    b_vals = [b["Envelope"], b["Systems"], b["Fixtures"]]
    o_vals = None
    if o_res:
        o = o_res["capex"]["breakdown_nzd"]
        o_vals = [o["Envelope"], o["Systems"], o["Fixtures"]]
    plot_breakdown_stacked("5) Capital cost breakdown (Base vs Improve)", "NZD", cats, b_vals, o_vals)

# =============================================================================
# WHAT CHANGED TABLE
# =============================================================================
def scenario_changes_table() -> pd.DataFrame:
    rows = []

    def add(label: str, b_val, o_val):
        if b_val != o_val:
            rows.append([label, b_val, o_val])

    add("Closest city", st.session_state.get("b_closestCity"), st.session_state.get("o_closestCity"))
    add("Roof insulation", st.session_state.get("b_roofRLabel"), st.session_state.get("o_roofRLabel"))
    add("Wall insulation", st.session_state.get("b_wallRLabel"), st.session_state.get("o_wallRLabel"))
    add("Floor insulation", st.session_state.get("b_floorRLabel"), st.session_state.get("o_floorRLabel"))
    add("Window type", st.session_state.get("b_windowULabel"), st.session_state.get("o_windowULabel"))
    add("Space heating system", st.session_state.get("b_spaceHeatingSystem"), st.session_state.get("o_spaceHeatingSystem"))
    add("Water heating system", st.session_state.get("b_waterHeatingSystem"), st.session_state.get("o_waterHeatingSystem"))
    add("Toilet type", st.session_state.get("b_toiletType"), st.session_state.get("o_toiletType"))
    add("Shower type", st.session_state.get("b_showerType"), st.session_state.get("o_showerType"))
    add("Tap type", st.session_state.get("b_tapType"), st.session_state.get("o_tapType"))
    add("Has washing machine?", st.session_state.get("b_wash_has"), st.session_state.get("o_wash_has"))
    add("Has dishwasher?", st.session_state.get("b_dish_has"), st.session_state.get("o_dish_has"))

    return pd.DataFrame(rows, columns=["Changed item", "Base scenario", "Improve scenario"])

# =============================================================================
# TAB 2: CALCULATORS (TRANSPARENCY)
# =============================================================================
def build_transparency_tables(s: dict, res: dict, coeffs: dict) -> dict[str, pd.DataFrame]:
    """Return a dict of named tables (dataframes) for the Calculators tab."""
    space = res["spaceHeating"]
    water_use = res["waterConsumption"]
    water_heat = res["waterHeating"]
    lighting = res["lighting"]
    capex = res["capex"]
    opex = res["opex"]
    carbon = res["carbon"]

    # Scenario summary inputs
    df_inputs = pd.DataFrame(
        [
            ["Closest city", s["closestCity"]],
            ["HDD (base 18°C)", s["HDD_base18"]],
            ["Floor area (m²)", s["floorArea"]],
            ["Ceiling height (m)", s["ceilingHeight"]],
            ["Household size (people)", s["householdSize"]],
            ["Window area (m²)", s["windowArea"]],
        ],
        columns=["Item", "Value"],
    )

    # Envelope + geometry + HLC breakdown
    areas = space["areas_m2"]
    Uv = space["U_values"]
    Hk = space["breakdown_W_per_K"]

    df_hlc = pd.DataFrame(
        [
            ["Roof", areas["roof"], Uv["Roof"], Hk["Roof"]],
            ["Walls", areas["wall"], Uv["Walls"], Hk["Walls"]],
            ["Floor", areas["floor"], Uv["Floor"], Hk["Floor"]],
            ["Windows", areas["window"], Uv["Windows"], Hk["Windows"]],
            ["TOTAL (HLC)", None, None, space["H_total_W_per_K"]],
        ],
        columns=["Element", "Area (m²)", "U-value (W/m²K)", "Heat loss (W/K)"],
    )

    df_heat = pd.DataFrame(
        [
            ["Delivered space heating (kWh/yr)", space["Q_delivered_kwh_y"]],
            ["Space heating COP", s["spaceHeatingCOP"]],
            ["Purchased space heating (kWh/yr)", space["Q_purchased_kwh_y"]],
        ],
        columns=["Item", "Value"],
    )

    # Water end-uses
    df_water = pd.DataFrame(
        [[k, v] for k, v in water_use["enduse_L_y"].items()] + [["TOTAL indoor water (m³/yr)", water_use["V_total_m3_y"]]],
        columns=["End-use", "Volume"],
    )

    # Hot water energy
    df_hw = pd.DataFrame(
        [
            ["Hot water volume (L/yr)", water_heat["V_hot_L_y"]],
            ["ΔT (°C)", water_heat["deltaT_C"]],
            ["Delivered hot water energy (kWh/yr)", water_heat["Q_delivered_kwh_y"]],
            ["Water heating COP", s["waterHeatingCOP"]],
            ["Purchased hot water (kWh/yr)", water_heat["Q_purchased_kwh_y"]],
        ],
        columns=["Item", "Value"],
    )

    # Lighting
    L = s["lighting"]
    df_light = pd.DataFrame(
        [
            ["Number of lights", L["numberOfLights"]],
            ["Watts per light (W)", L["wattsPerLight"]],
            ["Hours/day", L["hoursPerDay"]],
            ["Lighting electricity (kWh/yr)", lighting["Q_total_kwh_y"]],
        ],
        columns=["Item", "Value"],
    )

    # Totals
    df_totals = pd.DataFrame(
        [
            ["Total electricity (kWh/yr)", res["totalElectricity_kwh_y"]],
            ["Energy intensity (kWh/m²/yr)", res["energyIntensity_kwh_m2_y"]],
            ["Total indoor water (m³/yr)", water_use["V_total_m3_y"]],
        ],
        columns=["Item", "Value"],
    )

    # Carbon + opex
    df_carbon = pd.DataFrame(
        [
            ["Grid EF (kgCO₂e/kWh)", coeffs["grid_ef"]],
            ["Water EF (kgCO₂e/m³)", coeffs["water_ef"]],
            ["Electricity emissions (kgCO₂e/yr)", carbon["CO2_electricity_kg_y"]],
            ["Water emissions (kgCO₂e/yr)", carbon["CO2_water_kg_y"]],
            ["TOTAL operational carbon (kgCO₂e/yr)", carbon["CO2_total_kg_y"]],
        ],
        columns=["Item", "Value"],
    )

    df_opex = pd.DataFrame(
        [
            ["Electricity tariff (NZD/kWh)", coeffs["elec_tariff"]],
            ["Water tariff (NZD/m³)", coeffs["water_tariff"]],
            ["Electricity cost (NZD/yr)", opex["opex_electricity_nzd_y"]],
            ["Water cost (NZD/yr)", opex["opex_water_nzd_y"]],
            ["TOTAL operating cost (NZD/yr)", opex["opex_total_nzd_y"]],
        ],
        columns=["Item", "Value"],
    )

    # Capex
    df_capex = pd.DataFrame(
        [
            ["Envelope capex (NZD)", capex["breakdown_nzd"]["Envelope"]],
            ["Systems capex (NZD)", capex["breakdown_nzd"]["Systems"]],
            ["Fixtures capex (NZD)", capex["breakdown_nzd"]["Fixtures"]],
            ["TOTAL capex (NZD)", capex["capex_total_nzd"]],
        ],
        columns=["Item", "Value"],
    )

    df_capex_rates = pd.DataFrame(
        [[k, v] for k, v in capex.get("unit_rates", {}).items()],
        columns=["Unit rate", "Value"],
    )

    return {
        "Scenario inputs": df_inputs,
        "Heat Loss Coefficient (HLC) breakdown": df_hlc,
        "Space heating energy": df_heat,
        "Indoor water end-uses": df_water,
        "Water heating energy": df_hw,
        "Lighting electricity": df_light,
        "Totals": df_totals,
        "Operational carbon": df_carbon,
        "Operating cost (Opex)": df_opex,
        "Capital cost (Capex)": df_capex,
        "Capex unit rates": df_capex_rates,
    }

# =============================================================================
# APP START
# =============================================================================
init_defaults()

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

st.title("NZ Housing Sustainability Calculator (Prototype)")

with st.expander("Quick start guide", expanded=False):
    st.markdown(
        """
**What this prototype does (early-stage):**
- Estimates annual **electricity** (space heating + hot water + lighting), **indoor water**, **operational carbon**, **operating cost**, and transparent **capex**.
- This is **decision support only** (not certification; not a full building simulation).

**How to use it:**
1. Fill **Base scenario** → press **Calculate**.
2. **Improve scenario** unlocks and copies Base values → adjust Improve → press **Calculate** again to compare.
3. Once comparison is active, results update when you press Calculate (you can also use it as a refresh button).

Tip: If you are unsure about an input, hover the help icon for plain-language guidance.
        """
    )

tab_scenarios, tab_calculators, tab_formulas, tab_sources = st.tabs(
    ["Scenarios", "Calculators", "Formulas", "Data sources"]
)

# =============================================================================
# TAB 1: SCENARIOS (MAIN UI)
# =============================================================================
with tab_scenarios:
    if not st.session_state.get("base_ready", False):
        st.info("Step 1: Fill the Base scenario, then press Calculate.")
    elif st.session_state.get("base_ready", False) and not st.session_state.get("compare_ready", False):
        st.info("Step 2: Improve scenario is unlocked. Update Improve, then press Calculate again to compare.")
    else:
        st.success("Step 3: Comparison is active.")

    left, right = st.columns([1, 1], gap="large")

    INPUT_H = 560
    RESULTS_H = 720

    def do_calculate():
        # Step 1 -> Step 2
        if not st.session_state.get("base_ready", False):
            b_now = get_scenario("b")
            missing_b = validate_scenario(b_now)
            if missing_b:
                st.session_state["last_calc_error"] = "To calculate, complete Base: " + ", ".join(missing_b)
                return
            st.session_state["base_ready"] = True
            st.session_state["improve_unlocked"] = True
            st.session_state["compare_ready"] = False
            st.session_state["last_calc_error"] = None

            if not st.session_state.get("improve_seeded", False):
                seed_improve_from_base_once()
            return

        # Step 2 -> Step 3
        if st.session_state.get("base_ready", False) and not st.session_state.get("compare_ready", False):
            o_now = get_scenario("o")
            missing_o = validate_scenario(o_now)
            if missing_o:
                st.session_state["last_calc_error"] = "To compare, complete Improve: " + ", ".join(missing_o)
                return
            st.session_state["compare_ready"] = True
            st.session_state["last_calc_error"] = None
            return

        # Step 3: refresh
        st.session_state["compare_ready"] = True
        st.session_state["last_calc_error"] = None

    def calc_label():
        if not st.session_state.get("base_ready", False):
            return "Calculate (unlock Improve scenario)"
        if st.session_state.get("base_ready", False) and not st.session_state.get("compare_ready", False):
            return "Calculate (compare scenarios)"
        return "Calculate (refresh comparison)"

    with left:
        with container_box(height=INPUT_H, border=False):
            scenario_panel("b", "Base scenario")

            if st.session_state.get("improve_unlocked", False):
                st.divider()
                scenario_panel("o", "Improve scenario")

        st.divider()
        st.button(calc_label(), use_container_width=True, key="btn_calculate_all", on_click=do_calculate)

        if st.session_state.get("last_calc_error"):
            st.warning(st.session_state["last_calc_error"])

    with right:
        with container_box(height=RESULTS_H, border=False):
            st.subheader("Results")

            b_res = None
            o_res = None
            b_now = None
            o_now = None

            if not st.session_state.get("base_ready", False):
                st.caption("Fill Base scenario inputs and press Calculate.")
            else:
                b_now = get_scenario("b")
                if validate_scenario(b_now):
                    st.caption("Base scenario is incomplete.")
                else:
                    b_res = calculate_scenario(b_now, get_coeffs("b"))

            if st.session_state.get("compare_ready", False):
                o_now = get_scenario("o")
                if validate_scenario(o_now):
                    st.caption("Improve scenario is incomplete.")
                else:
                    o_res = calculate_scenario(o_now, get_coeffs("o"))

            if b_res is not None:
                base_energy = b_res["totalElectricity_kwh_y"]
                base_water = b_res["waterConsumption"]["V_total_m3_y"]
                base_carbon = b_res["carbon"]["CO2_total_kg_y"]
                base_opex = b_res["opex"]["opex_total_nzd_y"]
                base_capex = b_res["capex"]["capex_total_nzd"]

                imp_energy = o_res["totalElectricity_kwh_y"] if o_res else None
                imp_water = o_res["waterConsumption"]["V_total_m3_y"] if o_res else None
                imp_carbon = o_res["carbon"]["CO2_total_kg_y"] if o_res else None
                imp_opex = o_res["opex"]["opex_total_nzd_y"] if o_res else None
                imp_capex = o_res["capex"]["capex_total_nzd"] if o_res else None

                # Payback
                pb_years = None
                pb_note = None
                if o_res is not None:
                    inc_capex = imp_capex - base_capex
                    savings = base_opex - imp_opex
                    if inc_capex <= 0:
                        pb_years = 0.0
                        pb_note = "No additional capex (Improve ≤ Base capex)."
                    elif savings <= 0:
                        pb_years = None
                        pb_note = "No payback (annual savings ≤ 0)."
                    else:
                        pb_years = inc_capex / savings
                        pb_note = "Payback = (Capex increase) ÷ (Annual opex savings)."

                # KPI rows (HLC intentionally NOT shown here)
                kpi_pair_row("Total energy use", "kWh/year", base_energy, imp_energy, decimals=1, lower_is_better=True)
                kpi_pair_row("Total water use", "m³/year", base_water, imp_water, decimals=2, lower_is_better=True)
                kpi_pair_row("Operational carbon", "kgCO₂e/year", base_carbon, imp_carbon, decimals=1, lower_is_better=True)
                kpi_pair_row("Operating cost", "NZD/year", base_opex, imp_opex, decimals=0, lower_is_better=True)
                kpi_pair_row("Capital cost", "NZD", base_capex, imp_capex, decimals=0, lower_is_better=True)

                payback_box(pb_years, pb_note)

                # What changed
                if st.session_state.get("compare_ready", False) and o_res is not None:
                    with container_box(border=True):
                        st.markdown("**What changed (Base → Improve)**")
                        df_changes = scenario_changes_table()
                        if df_changes.empty:
                            st.caption("No changes detected.")
                        else:
                            st.dataframe(df_changes, use_container_width=True, hide_index=True)

                st.divider()
                st.markdown("### Charts (Base vs Improve)")

                ch1, ch2 = st.columns(2, gap="small")
                with ch1:
                    plot_electricity_breakdown(b_res, o_res)
                with ch2:
                    plot_water_breakdown(b_res, o_res)

                ch3, ch4 = st.columns(2, gap="small")
                with ch3:
                    plot_carbon_breakdown(b_res, o_res)
                with ch4:
                    plot_opex_breakdown(b_res, o_res)

                plot_capex_breakdown(b_res, o_res)

                if o_res is not None:
                    payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "base": {"coefficients": get_coeffs("b"), "inputs": b_now, "results": b_res},
                        "improve": {"coefficients": get_coeffs("o"), "inputs": o_now, "results": o_res},
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

# =============================================================================
# TAB 2: CALCULATORS (TRANSPARENCY)
# =============================================================================
with tab_calculators:
    st.header("Calculators (transparency)")
    st.caption(
        "This tab shows the intermediate values used in the calculations. "
        "It is intended for transparency and reporting (early-stage, not a full simulation)."
    )

    if not st.session_state.get("base_ready", False):
        st.info("Calculate the Base scenario first to populate the intermediate values.")
    else:
        b_now = get_scenario("b")
        if validate_scenario(b_now):
            st.warning("Base scenario is incomplete.")
        else:
            b_res = calculate_scenario(b_now, get_coeffs("b"))
            b_tables = build_transparency_tables(b_now, b_res, get_coeffs("b"))

            o_now = None
            o_res = None
            o_tables = None
            if st.session_state.get("compare_ready", False):
                o_now = get_scenario("o")
                if not validate_scenario(o_now):
                    o_res = calculate_scenario(o_now, get_coeffs("o"))
                    o_tables = build_transparency_tables(o_now, o_res, get_coeffs("o"))

            colb, colo = st.columns(2, gap="large")
            with colb:
                st.subheader("Base scenario")
                for title, df in b_tables.items():
                    with st.expander(title, expanded=(title in ["Scenario inputs", "Heat Loss Coefficient (HLC) breakdown", "Totals"])):
                        st.dataframe(df, use_container_width=True, hide_index=True)

            with colo:
                st.subheader("Improve scenario")
                if o_tables is None:
                    st.caption("Improve intermediate values appear after you activate comparison (Step 3).")
                else:
                    for title, df in o_tables.items():
                        with st.expander(title, expanded=(title in ["Scenario inputs", "Heat Loss Coefficient (HLC) breakdown", "Totals"])):
                            st.dataframe(df, use_container_width=True, hide_index=True)

# =============================================================================
# TAB 3: FORMULAS
# =============================================================================
with tab_formulas:
    st.header("Formulas")
    st.markdown(
        """
### Notation
- **Area** in m²  
- **R-value** in m²·K/W  
- **U-value** in W/m²·K  (U = 1/R)  
- **HDD** in degree-days/year (base 18°C)  
- **COP** dimensionless  
- **HLC (H_total)** in W/K  

---

### 1) Heat Loss Coefficient (HLC)
**HLC (W/K) = Σ( Aᵢ × Uᵢ )**

Where:
- Roof: **H_roof = A_roof × (1 / R_roof)**
- Walls: **H_wall = A_wall × (1 / R_wall)**
- Floor: **H_floor = A_floor × (1 / R_floor)**
- Windows: **H_window = A_window × U_window**

So:
**HLC = H_roof + H_wall + H_floor + H_window**

**Geometry used (early-stage approximation):**
- **A_roof = floorArea**
- **Perimeter ≈ 4 × √(floorArea)**
- **A_wall ≈ (Perimeter × ceilingHeight) − windowArea**
- **A_floor = floorArea**
- **A_window = windowArea**

---

### 2) Annual Space Heating Electricity
Delivered annual space-heating energy (kWh/year):
**Q_delivered = (HLC × HDD × 24) / 1000**

Purchased electricity (kWh/year):
**Q_purchased = Q_delivered / COP**

---

### 3) Indoor Water Consumption
Annual volumes (L/year):
- **V_toilet = people × flushes/person/day × L/flush × 365**
- **V_shower = people × showers/person/day × minutes/shower × L/min × 365**
- **V_tap = people × tapMinutes/person/day × L/min × 365**
- **V_laundry = cycles/week × L/cycle × 52** (if included)
- **V_dishwasher = cycles/week × L/cycle × 52** (if included)

Total indoor water (m³/year):
**V_total_m3 = (V_toilet + V_shower + V_tap + V_laundry + V_dishwasher) / 1000**

---

### 4) Water Heating Electricity (derived from end-uses)
Hot-water volume (L/year):
**V_hot = V_shower×f_shower + V_tap×f_tap + V_laundry×f_laundry + V_dishwasher×f_dishwasher**

Temperature rise:
**ΔT = T_hot_setpoint − T_cold_inlet**

Delivered energy (kWh/year):
**Q_hot_delivered = (V_hot × Cp × ΔT) / 3600**

Where:
- Cp = 4.186 kJ/kg·°C (≈ kJ/L·°C for water)

Purchased electricity (kWh/year):
**Q_hot_purchased = Q_hot_delivered / COP**

---

### 5) Lighting Electricity
**Q_lighting = (numberOfLights × wattsPerLight × hoursPerDay × 365) / 1000**

---

### 6) Total Electricity (Operational)
**Q_total_electricity = Q_space_purchased + Q_hot_purchased + Q_lighting**

---

### 7) Operational Carbon
**CO2_total = (Q_total_electricity × EF_grid) + (V_total_m3 × EF_water)**

---

### 8) Operating Cost (Opex)
**Opex_total = (Q_total_electricity × tariff_elec) + (V_total_m3 × tariff_water)**

---

### 9) Capital Cost (Capex)
Envelope capex (NZD):
**Capex_env = (A_roof×c_roof) + (A_wall×c_wall) + (A_floor×c_floor) + (A_window×c_window)**

Systems + fixtures capex are added as lump sums:
**Capex_total = Capex_env + Capex_systems + Capex_fixtures**

---

### 10) Simple Payback (years)
Let:
- **ΔCapex = Capex_improve − Capex_base**
- **ΔOpex = Opex_base − Opex_improve** (savings)

Then:
- If ΔCapex ≤ 0 → Payback = 0 (no additional capex)
- If ΔOpex ≤ 0 → No payback
- Else **Payback = ΔCapex / ΔOpex**
        """
    )

# =============================================================================
# TAB 4: DATA SOURCES
# =============================================================================
with tab_sources:
    st.header("Data sources")
    rows = [
        [1,"Energy","Space Heating Energy","Electricity for space heating","Calculated","(HLC × HDD × 24 / 1000) ÷ COP","MBIE (2023)","Steady-state early-stage method"],
        [2,"Energy","Heating Degree Days (HDD)","Climate severity (base 18 °C)","Lookup / User","Zone bands + Custom","InfraComfort (n.d.); MSD (2006)","City → climate zone"],
        [3,"Energy","Heating System COP","Seasonal heating efficiency","Assumption / User","Systems list + Custom","BRANZ (2023)","Typical NZ systems"],
        [4,"Envelope","R-values (roof/wall/floor)","Thermal resistance bands","Assumption / User","Uninsulated → Excellent + Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned bands"],
        [5,"Envelope","Window U-value","Glazing heat transfer","Assumption / User","Single → Triple + Custom","BRANZ (2023)","Typical glazing"],
        [6,"Water","Fixture flow/flush rates","Indoor water end-use rates","Assumption / User","Toilet/shower/tap + Custom","BRANZ (2023)","Typical fixtures"],
        [7,"Carbon","Grid emission factor","kgCO₂e per kWh","Constant","0.0729","MfE (2024)","2023 value"],
        [8,"Carbon","Water emission factor","kgCO₂e per m³","Constant","0.0349","MfE (2024)","Water supply factor"],
        [9,"Cost (Opex)","Electricity tariff","NZD per kWh","Default / User","0.312","Electricity Authority (2024)","Editable"],
        [10,"Cost (Opex)","Water tariff","NZD per m³","Default / User","2.296","Auckland Council (2025)","Editable"],
        [11,"Cost (Capex)","Envelope/system/fixture costs","Installed capex estimates","Assumption / User","Benchmarks + Custom","Market benchmark schedule","Early-stage transparency"],
    ]
    df = pd.DataFrame(rows, columns=[
        "Order","Module","Variable / Indicator","Description & Role","Data Type",
        "Selection Options & Defaults","Source / Reference","Notes"
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)
