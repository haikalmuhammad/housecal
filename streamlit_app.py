# streamlit_app.py
import copy
import json
import math
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
# THEME / CSS OVERRIDES (green palette + select highlights + tabs)
# =============================================================================
def inject_theme_css():
    st.markdown(
        """
        <style>
        /* --------- Global accent to green-ish --------- */
        :root{
          --accent: #16a34a;      /* green-600 */
          --accent-2: #22c55e;    /* green-500 */
          --accent-soft: rgba(34,197,94,0.12);
          --border-soft: rgba(49,51,63,0.18);
        }

        /* Tabs (BaseWeb) */
        div[data-baseweb="tab-list"] button[aria-selected="true"]{
          color: var(--accent) !important;
          border-bottom: 2px solid var(--accent) !important;
        }
        div[data-baseweb="tab-list"] button:hover{
          color: var(--accent-2) !important;
        }

        /* Buttons */
        .stButton > button {
          border-color: var(--border-soft);
        }
        .stButton > button:focus,
        .stButton > button:active {
          outline: none !important;
          box-shadow: 0 0 0 0.2rem var(--accent-soft) !important;
          border-color: var(--accent) !important;
        }

        /* Select / input focus border (BaseWeb) */
        div[data-baseweb="select"] > div:focus-within{
          box-shadow: 0 0 0 0.2rem var(--accent-soft) !important;
          border-color: var(--accent) !important;
        }
        input:focus, textarea:focus{
          box-shadow: 0 0 0 0.2rem var(--accent-soft) !important;
          border-color: var(--accent) !important;
        }

        /* Slider accent */
        div[data-baseweb="slider"] div[role="slider"]{
          box-shadow: 0 0 0 0.2rem var(--accent-soft) !important;
          border-color: var(--accent) !important;
        }

        /* Small status pill */
        .pill{
          display:inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          font-size: 0.78rem;
          font-weight: 700;
          border: 1px solid var(--border-soft);
          margin-bottom: 6px;
        }
        .pill.ok{
          color: var(--accent);
          border-color: rgba(22,163,74,0.35);
          background: rgba(22,163,74,0.10);
        }
        .pill.bad{
          opacity: 0.7;
          background: rgba(255,255,255,0.03);
        }

        /* Action bar */
        .actionbar{
          position: sticky;
          bottom: 0;
          z-index: 20;
          padding: 10px 10px;
          border: 1px solid var(--border-soft);
          border-radius: 12px;
          background: rgba(255,255,255,0.04);
          backdrop-filter: blur(8px);
          margin-top: 10px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )

def inject_card_css():
    st.markdown(
        """
        <style>
        .kpi-card{
          border: 1px solid rgba(49, 51, 63, 0.18);
          border-radius: 12px;
          padding: 12px 12px;
          background: rgba(255,255,255,0.02);
          margin-bottom: 10px;
        }
        .kpi-title{
          font-weight: 800;
          font-size: 0.95rem;
          margin-bottom: 2px;
          line-height: 1.2;
        }
        .kpi-sub{
          font-weight: 600;
          opacity: 0.70;
          font-size: 0.82rem;
          margin-bottom: 8px;
        }
        .kpi-row{
          display:flex;
          justify-content: space-between;
          gap: 12px;
          padding: 2px 0;
          font-size: 0.92rem;
        }
        .kpi-label{ opacity: 0.75; }
        .kpi-val{ font-weight: 800; }
        .kpi-note{ opacity: 0.70; font-size: 0.82rem; margin-top: 6px; }
        </style>
        """,
        unsafe_allow_html=True
    )

inject_theme_css()

# =============================================================================
# HELPERS
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

# =============================================================================
# LOOKUP TABLES (Single Source of Truth)
# =============================================================================
LOOKUP = {
    "constants": {
        "grid_emission_factor_kgco2e_per_kwh": 0.0729,  # MfE (2024) – 2023
        "water_emission_factor_kgco2e_per_m3": 0.0349,  # MfE (2024)
        "electricity_tariff_nzd_per_kwh_default": 0.312,  # Electricity Authority (2024)
        "water_tariff_nzd_per_m3_default": 2.296,         # Auckland Council (2025)
        "ceiling_height_m_default": 2.4,
        "cp_kj_per_kgC": 4.186,                           # engineering constant
    },

    "thermal_envelope": {
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
# FIXED COLOR MAP (semantic consistency across Baseline vs Option)
# =============================================================================
ENDUSE_COLORS = {
    "Space heating": "#1f77b4",
    "Water heating": "#ff7f0e",
    "Lighting": "#2ca02c",

    "Toilets": "#9467bd",
    "Showers": "#17becf",
    "Taps": "#8c564b",
    "Laundry": "#e377c2",
    "Dishwasher": "#7f7f7f",

    "Electricity": "#1f77b4",
    "Water": "#17becf",

    "Envelope": "#1f77b4",
    "Systems": "#ff7f0e",
    "Fixtures": "#2ca02c",
}

# =============================================================================
# HELP TEXTS (built after LOOKUP)
# =============================================================================
def build_help(LOOKUP):
    return {
        "closest_city": help_default_source(
            what="Closest major city used to infer Climate Zone and Heating Degree Days (HDD, base 18°C).",
            source="InfraComfort (n.d.); MSD (2006) bands; city→zone mapping embedded in this tool",
            notes="Pick the closest major city. If you have a confirmed HDD, you can override it."
        ),
        "use_custom_hdd": help_default_source(
            what="Override the default HDD for your selected city/zone.",
            default=False,
            source="User override",
            notes="HDD is annual degree-days (base 18°C). Higher = colder climate."
        ),
        "hdd_value": help_default_source(
            what="Annual Heating Degree Days (base 18°C).",
            default=2000.0,
            units="degree-days/year",
            source="User override (otherwise from climate zone defaults)"
        ),
        "floor_area": help_default_source(
            what="Conditioned floor area used in simplified heat-loss geometry and intensity metrics.",
            default=float(LOOKUP["defaults"]["core"]["floorArea"]),
            units="m²",
            source="Model default (editable)"
        ),
        "ceiling_height": help_default_source(
            what="Average ceiling height used to approximate external wall area.",
            default=float(LOOKUP["defaults"]["core"]["ceilingHeight"]),
            units="m",
            source="Model default (editable)"
        ),
        "household_size": help_default_source(
            what="Number of occupants used for per-person indoor water end-uses.",
            default=int(LOOKUP["defaults"]["core"]["householdSize"]),
            units="people",
            source="Model default (editable)"
        ),
        "window_area": help_default_source(
            what="Total window area used in glazing heat-loss component.",
            default=float(LOOKUP["defaults"]["core"]["windowArea"]),
            units="m²",
            source="Model default (editable)"
        ),
        "r_value": help_default_source(
            what="R-value (m²K/W): higher is better insulation (lower heat loss).",
            source="MBIE (2023); BRANZ (2023) – banded defaults embedded in this tool",
            notes="If you select Custom, enter your own R-value and capex rate."
        ),
        "u_value": help_default_source(
            what="U-value (W/m²K): lower is better glazing performance (less heat loss).",
            source="BRANZ (2023) – typical glazing defaults embedded in this tool",
            notes="If you select Custom, enter your own U-value and window capex rate."
        ),
        "cop": help_default_source(
            what="COP (Coefficient of Performance): higher means less purchased electricity for the same delivered heat.",
            source="BRANZ (2023) – typical NZ system COPs embedded in this tool"
        ),
        "fixture": help_default_source(
            what="Select fixture type to set water use rate and install capex.",
            source="BRANZ (2023) – typical fixture performance embedded in this tool",
            notes="Custom lets you enter your own litres/flush or L/min and capex."
        ),
        "tariffs": help_default_source(
            what="Retail tariffs vary by region/provider; set to match your bill if known.",
            default=f"Electricity {LOOKUP['constants']['electricity_tariff_nzd_per_kwh_default']} NZD/kWh; Water {LOOKUP['constants']['water_tariff_nzd_per_m3_default']} NZD/m³",
            source="Electricity Authority (2024); Auckland Council (2025)"
        ),
        "efs": help_default_source(
            what="Emission factors for operational carbon (location-based).",
            default=f"Grid {LOOKUP['constants']['grid_emission_factor_kgco2e_per_kwh']} kgCO₂e/kWh; Water {LOOKUP['constants']['water_emission_factor_kgco2e_per_m3']} kgCO₂e/m³",
            source="MfE (2024)"
        ),
    }

HELP = build_help(LOOKUP)

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

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)

def pill(ok: bool, text_ok="Complete", text_bad="Incomplete"):
    klass = "ok" if ok else "bad"
    txt = text_ok if ok else text_bad
    st.markdown(f'<span class="pill {klass}">{txt}</span>', unsafe_allow_html=True)

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
    """
    Simplified geometry:
    - roof area ~ floor area
    - wall area ~ perimeter * height - window area
      where perimeter ~ 4 * sqrt(floor_area) (square footprint assumption)
    """
    roof_area = floor_area
    perimeter = 4.0 * math.sqrt(max(floor_area, 0.0))
    wall_area = max(perimeter * ceiling_h - window_area, 0.0)
    return {"roof": roof_area, "wall": wall_area, "floor": floor_area, "window": window_area}

def calculate_space_heating(s: dict) -> dict:
    """
    Space Heating Electricity (kWh/y) = (H_total × HDD × 24 / 1000) ÷ COP
    where:
      H_total (W/K) = sum(area_i * U_i)
      U for floor/roof/wall derived from R: U=1/R
      windows uses U directly
    """
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

    # Delivered heat demand proxy (kWh/y): W/K * degree-days * hours/day -> Wh -> kWh
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

    # Delivered DHW energy (kWh/y) = (L * kJ/kgC * C) / 3600; 1 L ~ 1 kg
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
    st.session_state.setdefault("baseline_ready", False)
    st.session_state.setdefault("option_unlocked", False)
    st.session_state.setdefault("option_seeded", False)
    st.session_state.setdefault("compare_ready", False)
    st.session_state.setdefault("baseline_results", None)
    st.session_state.setdefault("option_results", None)

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

def seed_option_from_baseline_once():
    for suffix in COPY_KEYS:
        b_key = f"b_{suffix}"
        o_key = f"o_{suffix}"
        if b_key in st.session_state:
            st.session_state[o_key] = copy.deepcopy(st.session_state[b_key])
    st.session_state["option_seeded"] = True

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
# UI captions (performance + capex)
# =============================================================================
def show_city_caption(prefix: str):
    city = st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER)
    if city == PLACEHOLDER:
        return
    z = LOOKUP["climate"]["zone_by_city"].get(city)
    if z:
        hdd = LOOKUP["climate"]["hdd_by_zone_base18"][z]
        st.caption(f"Climate zone: **{z}** · Default HDD (base 18°C): **{hdd:g}**")

def show_envelope_caption(element: str, label: str):
    if label in (PLACEHOLDER, None, "Custom"):
        return
    if element in ("roof", "wall", "floor"):
        r = LOOKUP["thermal_envelope"][f"{element}R_m2K_per_W"][label]
        bucket = _bucket_from_label(label)
        cost = LOOKUP["thermal_envelope"]["capex_per_m2"][element][bucket]
        st.caption(f"Performance: **R={r:g} m²K/W** · Capex: **{fmt_money(cost)} /m²**")
    if element == "window":
        u = LOOKUP["thermal_envelope"]["windowU_W_per_m2K"][label]
        cost = LOOKUP["thermal_envelope"]["capex_per_m2"]["window"][label]
        st.caption(f"Performance: **U={u:g} W/m²K** · Capex: **{fmt_money(cost)} /m² window**")

def show_system_caption(sys_block: str, label: str):
    if label in (PLACEHOLDER, None, "Custom"):
        return
    cop = LOOKUP["systems"][sys_block]["cop"][label]
    cost = LOOKUP["systems"][sys_block]["install_cost_nzd"][label]
    st.caption(f"Performance: **COP={cop:g}** · Install capex: **{fmt_money(cost)}**")

def show_fixture_caption(kind: str, label: str):
    if label in (PLACEHOLDER, None, "Custom"):
        return
    if kind == "toilet":
        v = LOOKUP["fixtures"]["toilet"]["l_per_flush"][label]
        c = LOOKUP["fixtures"]["toilet"]["install_cost_nzd"][label]
        st.caption(f"Water: **{v:g} L/flush** · Install capex: **{fmt_money(c)}**")
    else:
        v = LOOKUP["fixtures"][kind]["l_per_min"][label]
        c = LOOKUP["fixtures"][kind]["install_cost_nzd"][label]
        st.caption(f"Water: **{v:g} L/min** · Install capex: **{fmt_money(c)}**")

# =============================================================================
# SECTION COMPLETENESS (for the green “complete” cues)
# =============================================================================
def section_complete_core(prefix: str) -> bool:
    city = st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER)
    if city == PLACEHOLDER:
        return False
    if resolve_hdd(prefix) is None:
        return False
    # Basic building info present by defaults (floor area etc) – we treat valid if >0
    if float(st.session_state.get(f"{prefix}_floorArea", 0)) <= 0:
        return False
    if float(st.session_state.get(f"{prefix}_ceilingHeight", 0)) <= 0:
        return False
    if int(st.session_state.get(f"{prefix}_householdSize", 0)) <= 0:
        return False
    if float(st.session_state.get(f"{prefix}_windowArea", -1)) < 0:
        return False
    # lighting inputs have defaults; accept >=0
    if int(st.session_state.get(f"{prefix}_light_n", -1)) < 0:
        return False
    return True

def section_complete_envelope_systems_water(prefix: str) -> bool:
    s = get_scenario(prefix)
    missing = validate_scenario(s)
    # This section covers envelope + systems + fixtures (not optional tariffs/usage)
    # We consider it complete if the “main” required selection fields are not missing.
    required_labels = {
        "Roof insulation", "Wall insulation", "Floor insulation", "Window type",
        "Space heating system", "Water heating system",
        "Toilet type", "Shower type", "Tap type",
        "Washing machine (Yes/No)", "Dishwasher (Yes/No)",
    }
    return all(m not in required_labels for m in missing)

# =============================================================================
# INPUT PANELS
# =============================================================================
def scenario_panel(prefix: str, title: str):
    st.subheader(title)

    if st.button(f"Use Code Minimum ({title})", key=f"{prefix}_btn_code_min", use_container_width=True):
        apply_code_minimum(prefix)
        st.rerun()

    # 1) Core + Climate + Lighting (now with heading “Building info”)
    ok_core = section_complete_core(prefix)
    pill(ok_core, text_ok="Core complete", text_bad="Core incomplete")

    with st.expander("Core climate + lighting", expanded=True):
        st.markdown("#### Building info")
        cc1, cc2 = st.columns(2, gap="small")

        with cc1:
            select_with_placeholder("Closest city", CITIES, key=f"{prefix}_closestCity", help_text=HELP["closest_city"])
            show_city_caption(prefix)

            st.checkbox("Use custom HDD", key=f"{prefix}_use_custom_hdd", help=HELP["use_custom_hdd"])
            if st.session_state[f"{prefix}_use_custom_hdd"]:
                st.number_input(
                    "Custom HDD (base 18°C)",
                    min_value=0.0, max_value=6000.0, step=50.0,
                    key=f"{prefix}_hdd_override_value",
                    help=HELP["hdd_value"],
                )
                st.caption(f"Using custom HDD: **{float(st.session_state[f'{prefix}_hdd_override_value']):g}**")

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea", help=HELP["floor_area"])
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight", help=HELP["ceiling_height"])
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize", help=HELP["household_size"])
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea", help=HELP["window_area"])

        with cc2:
            st.markdown("#### Lighting")
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n")
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts")
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours")
            st.caption("Lighting kWh/y = (Lights × W × hours/day × 365) ÷ 1000")

    # 2) Envelope + Systems + Water
    ok_esw = section_complete_envelope_systems_water(prefix)
    pill(ok_esw, text_ok="Envelope/systems/water complete", text_bad="Envelope/systems/water incomplete")

    with st.expander("Envelope + systems + water", expanded=False):
        ec1, ec2 = st.columns(2, gap="small")

        with ec1:
            with st.expander("Thermal envelope", expanded=True):
                select_with_placeholder("Roof insulation", ROOF_OPTS, key=f"{prefix}_roofRLabel", help_text=HELP["r_value"])
                show_envelope_caption("roof", st.session_state[f"{prefix}_roofRLabel"])
                if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                    st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom")
                    st.number_input("Roof capex (NZD/m² roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom")

                select_with_placeholder("Wall insulation", WALL_OPTS, key=f"{prefix}_wallRLabel", help_text=HELP["r_value"])
                show_envelope_caption("wall", st.session_state[f"{prefix}_wallRLabel"])
                if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                    st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom")
                    st.number_input("Wall capex (NZD/m² wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom")

                select_with_placeholder("Floor insulation", FLOOR_OPTS, key=f"{prefix}_floorRLabel", help_text=HELP["r_value"])
                show_envelope_caption("floor", st.session_state[f"{prefix}_floorRLabel"])
                if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                    st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom")
                    st.number_input("Floor capex (NZD/m² floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom")

                select_with_placeholder("Window type", WIN_OPTS, key=f"{prefix}_windowULabel", help_text=HELP["u_value"])
                show_envelope_caption("window", st.session_state[f"{prefix}_windowULabel"])
                if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                    st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom")
                    st.number_input("Windows capex (NZD/m² window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom")

        with ec2:
            with st.expander("Systems", expanded=True):
                select_with_placeholder("Space heating system", SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help_text=HELP["cop"])
                show_system_caption("space_heating", st.session_state[f"{prefix}_spaceHeatingSystem"])
                if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                    st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_spaceCOP_custom")
                    st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom")

                select_with_placeholder("Water heating system", WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help_text=HELP["cop"])
                show_system_caption("water_heating", st.session_state[f"{prefix}_waterHeatingSystem"])
                if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                    st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_waterCOP_custom")
                    st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_waterInstall_custom")

            with st.expander("Water fixtures + appliances", expanded=True):
                select_with_placeholder("Toilet type", TOILET_OPTS, key=f"{prefix}_toiletType", help_text=HELP["fixture"])
                show_fixture_caption("toilet", st.session_state[f"{prefix}_toiletType"])
                if st.session_state[f"{prefix}_toiletType"] == "Custom":
                    st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toilet_value_custom")
                    st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom")

                select_with_placeholder("Shower type", SHOWER_OPTS, key=f"{prefix}_showerType", help_text=HELP["fixture"])
                show_fixture_caption("shower", st.session_state[f"{prefix}_showerType"])
                if st.session_state[f"{prefix}_showerType"] == "Custom":
                    st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_shower_value_custom")
                    st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_shower_cost_custom")

                select_with_placeholder("Tap type", TAP_OPTS, key=f"{prefix}_tapType", help_text=HELP["fixture"])
                show_fixture_caption("tap", st.session_state[f"{prefix}_tapType"])
                if st.session_state[f"{prefix}_tapType"] == "Custom":
                    st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tap_value_custom")
                    st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tap_cost_custom")

                st.divider()
                st.selectbox("Has washing machine?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_wash_has")
                if st.session_state[f"{prefix}_wash_has"] == "Yes":
                    st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles")
                    st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L")

                st.selectbox("Has dishwasher?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_dish_has")
                if st.session_state[f"{prefix}_dish_has"] == "Yes":
                    st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles")
                    st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L")

    # 3) Optional
    with st.expander("Optional: usage + fractions + tariffs + emissions", expanded=False):
        st.caption("Use this section only if you want to tailor behaviour assumptions or local pricing/factors.")
        oc1, oc2 = st.columns(2, gap="small")

        with oc1:
            with st.expander("Usage assumptions", expanded=True):
                st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
                st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")
                st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
                st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
                st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
                st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

        with oc2:
            with st.expander("Hot water fractions", expanded=True):
                st.caption("Fractions (0–1). Toilets are always treated as cold water.")
                st.slider("Shower hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_shower")
                st.slider("Tap hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_tap")
                st.slider("Laundry hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_laundry")
                st.slider("Dishwasher hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_dishwasher")

            with st.expander("Tariffs + emission factors", expanded=True):
                st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"])
                st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"])
                st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", help=HELP["efs"])
                st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef", help=HELP["efs"])

# =============================================================================
# CARDS
# =============================================================================
def render_metric_card(title: str, unit: str, base_val: str, opt_val: str, delta_val: str, delta_dir: str):
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">{title}</div>
          <div class="kpi-sub">{unit}</div>
          <div class="kpi-row"><div class="kpi-label">Baseline</div><div class="kpi-val">{base_val}</div></div>
          <div class="kpi-row"><div class="kpi-label">Option</div><div class="kpi-val">{opt_val}</div></div>
          <div class="kpi-row"><div class="kpi-label">Δ (Option − Base)</div><div class="kpi-val">{delta_dir} {delta_val}</div></div>
        </div>
        """,
        unsafe_allow_html=True
    )

def render_payback_card(pb_years: str, note: str | None = None):
    note_html = f'<div class="kpi-note">{note}</div>' if note else ""
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">Simple payback years</div>
          <div class="kpi-sub">years</div>
          <div class="kpi-row"><div class="kpi-label">Payback</div><div class="kpi-val">{pb_years}</div></div>
          {note_html}
        </div>
        """,
        unsafe_allow_html=True
    )

def metric_vals(b_val: float | None, o_val: float | None, dec: int):
    b_s = fmt_num(b_val, dec) if b_val is not None else "—"
    o_s = fmt_num(o_val, dec) if o_val is not None else "—"
    if (b_val is None) or (o_val is None):
        return b_s, o_s, "—", "—"
    d = o_val - b_val
    return b_s, o_s, fmt_num(d, dec), direction_arrow(d)

# =============================================================================
# CHARTS (your requested 5 breakdown charts; fixed semantic colors)
# =============================================================================
def plot_breakdown_stacked(title: str, ytitle: str, categories: list, base_vals: list, opt_vals: list | None):
    fig = go.Figure()

    for cat, val in zip(categories, base_vals):
        fig.add_trace(go.Bar(
            name=cat,
            x=["Baseline"],
            y=[val],
            marker_color=ENDUSE_COLORS.get(cat),
            legendgroup=cat,
        ))

    if opt_vals is not None:
        for cat, val in zip(categories, opt_vals):
            fig.add_trace(go.Bar(
                name=cat,
                x=["Option"],
                y=[val],
                marker_color=ENDUSE_COLORS.get(cat),
                legendgroup=cat,
                showlegend=False,
            ))

    fig.update_layout(
        title=title,
        barmode="stack",
        height=360,
        margin=dict(l=20, r=20, t=60, b=50),
        yaxis_title=ytitle,
    )
    st.plotly_chart(fig, use_container_width=True)

def chart_electricity_breakdown(b_res: dict, o_res: dict | None):
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
    plot_breakdown_stacked(
        "Electricity breakdown (Baseline vs Option)",
        "kWh/year",
        cats, b_vals, o_vals
    )

def chart_water_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Toilets", "Showers", "Taps", "Laundry", "Dishwasher"]
    b = b_res["waterConsumption"]["breakdown_m3_y"]
    b_vals = [b.get(c, 0.0) for c in cats]
    o_vals = None
    if o_res:
        o = o_res["waterConsumption"]["breakdown_m3_y"]
        o_vals = [o.get(c, 0.0) for c in cats]
    plot_breakdown_stacked(
        "Water breakdown (Baseline vs Option)",
        "m³/year",
        cats, b_vals, o_vals
    )

def chart_operational_carbon_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Electricity", "Water"]
    b_vals = [b_res["carbon"]["CO2_electricity_kg_y"], b_res["carbon"]["CO2_water_kg_y"]]
    o_vals = None
    if o_res:
        o_vals = [o_res["carbon"]["CO2_electricity_kg_y"], o_res["carbon"]["CO2_water_kg_y"]]
    plot_breakdown_stacked(
        "Operational carbon breakdown (Baseline vs Option)",
        "kgCO₂e/year",
        cats, b_vals, o_vals
    )

def chart_opex_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Electricity", "Water"]
    b_vals = [b_res["opex"]["opex_electricity_nzd_y"], b_res["opex"]["opex_water_nzd_y"]]
    o_vals = None
    if o_res:
        o_vals = [o_res["opex"]["opex_electricity_nzd_y"], o_res["opex"]["opex_water_nzd_y"]]
    plot_breakdown_stacked(
        "Operational expenditure breakdown (Baseline vs Option)",
        "NZD/year",
        cats, b_vals, o_vals
    )

def chart_capex_breakdown(b_res: dict, o_res: dict | None):
    cats = ["Envelope", "Systems", "Fixtures"]
    b = b_res["capex"]["breakdown_nzd"]
    b_vals = [b[c] for c in cats]
    o_vals = None
    if o_res:
        o = o_res["capex"]["breakdown_nzd"]
        o_vals = [o[c] for c in cats]
    plot_breakdown_stacked(
        "Capital expenditure breakdown (Baseline vs Option)",
        "NZD",
        cats, b_vals, o_vals
    )

# =============================================================================
# APP START
# =============================================================================
init_defaults()

# Seed option once baseline is calculated
if st.session_state.get("baseline_ready", False) and st.session_state.get("option_unlocked", False) and not st.session_state.get("option_seeded", False):
    seed_option_from_baseline_once()

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
st.caption("Baseline → unlock Option → Compare. After activation, results update automatically as you edit inputs.")

tab_calc, tab_formulas, tab_sources = st.tabs(["Calculator", "Formulas", "Data sources"])

# =============================================================================
# TAB 1: CALCULATOR
# =============================================================================
with tab_calc:
    left, right = st.columns([1, 1], gap="large")

    INPUT_H = 820
    RESULTS_H = 860

    # -------------------------
    # LEFT: inputs (scroll box) + ALWAYS-VISIBLE action bar below (sticky)
    # -------------------------
    with left:
        try:
            input_box = st.container(height=INPUT_H, border=True)
        except TypeError:
            input_box = st.container()

        with input_box:
            scenario_panel("b", "Baseline")

            if st.session_state.get("option_unlocked", False):
                st.divider()
                scenario_panel("o", "Option")

        # Always-visible action bar (outside scroll container)
        st.markdown('<div class="actionbar">', unsafe_allow_html=True)

        # Baseline button always visible
        b_now = get_scenario("b")
        missing_b = validate_scenario(b_now)
        if not st.session_state["baseline_ready"]:
            if missing_b:
                st.info("Baseline incomplete. Missing: " + ", ".join(missing_b))
            if st.button("Calculate Baseline", use_container_width=True, disabled=bool(missing_b)):
                st.session_state["baseline_ready"] = True
                st.session_state["option_unlocked"] = True
                if not st.session_state.get("option_seeded", False):
                    seed_option_from_baseline_once()
                st.rerun()
        else:
            st.success("Baseline calculated.")

        # Compare button always visible once option exists
        if st.session_state.get("option_unlocked", False):
            o_now = get_scenario("o")
            missing_o = validate_scenario(o_now)
            if not st.session_state.get("compare_ready", False):
                if missing_o:
                    st.info("Option incomplete. Missing: " + ", ".join(missing_o))
                if st.button("Calculate & Compare", use_container_width=True, disabled=bool(missing_o)):
                    st.session_state["compare_ready"] = True
                    st.rerun()
            else:
                st.success("Comparison activated. Editing inputs updates results live.")

        st.markdown("</div>", unsafe_allow_html=True)

    # -------------------------
    # RIGHT: results (cards + charts)
    # -------------------------
    with right:
        try:
            results_box = st.container(height=RESULTS_H, border=True)
        except TypeError:
            results_box = st.container()

        with results_box:
            st.subheader("Results")
            inject_card_css()

            b_res = None
            o_res = None

            if not st.session_state.get("baseline_ready", False):
                st.info("Fill Baseline inputs and click **Calculate Baseline** (button is always visible at the bottom).")
            else:
                b_now = get_scenario("b")
                missing_b = validate_scenario(b_now)
                if missing_b:
                    st.warning("Baseline incomplete. Missing: " + ", ".join(missing_b))
                else:
                    b_res = calculate_scenario(b_now, get_coeffs("b"))
                    st.session_state["baseline_results"] = b_res

            if st.session_state.get("compare_ready", False):
                o_now = get_scenario("o")
                missing_o = validate_scenario(o_now)
                if missing_o:
                    st.warning("Option incomplete. Missing: " + ", ".join(missing_o))
                else:
                    o_res = calculate_scenario(o_now, get_coeffs("o"))
                    st.session_state["option_results"] = o_res

            if b_res is not None:
                base_energy = b_res["totalElectricity_kwh_y"]
                base_water = b_res["waterConsumption"]["V_total_m3_y"]
                base_carbon = b_res["carbon"]["CO2_total_kg_y"]
                base_opex = b_res["opex"]["opex_total_nzd_y"]
                base_capex = b_res["capex"]["capex_total_nzd"]

                opt_energy = o_res["totalElectricity_kwh_y"] if o_res else None
                opt_water = o_res["waterConsumption"]["V_total_m3_y"] if o_res else None
                opt_carbon = o_res["carbon"]["CO2_total_kg_y"] if o_res else None
                opt_opex = o_res["opex"]["opex_total_nzd_y"] if o_res else None
                opt_capex = o_res["capex"]["capex_total_nzd"] if o_res else None

                b_s, o_s, d_s, d_dir = metric_vals(base_energy, opt_energy, 1)
                b_w, o_w, d_w, d_dir_w = metric_vals(base_water, opt_water, 2)
                b_c, o_c, d_c, d_dir_c = metric_vals(base_carbon, opt_carbon, 1)
                b_op, o_op, d_op, d_dir_op = metric_vals(base_opex, opt_opex, 0)
                b_cap, o_cap, d_cap, d_dir_cap = metric_vals(base_capex, opt_capex, 0)

                pb_years = "—"
                pb_note = None
                if o_res is not None:
                    inc_capex = opt_capex - base_capex
                    savings = base_opex - opt_opex
                    if inc_capex <= 0:
                        pb_years = "0.0"
                        pb_note = "No additional capex (option ≤ baseline capex)."
                    elif savings <= 0:
                        pb_years = "—"
                        pb_note = "No payback (opex savings ≤ 0)."
                    else:
                        pb_years = fmt_num(inc_capex / savings, 1)
                        pb_note = "Payback = (Capex increase) ÷ (Annual opex savings)."

                c1, c2 = st.columns(2, gap="small")
                with c1:
                    render_metric_card("Total energy use", "kWh/year", b_s, o_s, d_s, d_dir)
                with c2:
                    render_metric_card("Total water use", "m³/year", b_w, o_w, d_w, d_dir_w)

                c1, c2 = st.columns(2, gap="small")
                with c1:
                    render_metric_card("Operational carbon", "kgCO₂e/year", b_c, o_c, d_c, d_dir_c)
                with c2:
                    render_metric_card("Operational expenditure", "NZD/year", b_op, o_op, d_op, d_dir_op)

                c1, c2 = st.columns(2, gap="small")
                with c1:
                    render_metric_card("Capital expenditure", "NZD", b_cap, o_cap, d_cap, d_dir_cap)
                with c2:
                    render_payback_card(pb_years, pb_note)

                st.divider()
                st.markdown("### Charts (breakdown-focused)")

                # Your requested 5 charts (each compares baseline vs option; consistent colors)
                ch1, ch2 = st.columns(2, gap="small")
                with ch1:
                    chart_electricity_breakdown(b_res, o_res)
                with ch2:
                    chart_water_breakdown(b_res, o_res)

                ch3, ch4 = st.columns(2, gap="small")
                with ch3:
                    chart_operational_carbon_breakdown(b_res, o_res)
                with ch4:
                    chart_opex_breakdown(b_res, o_res)

                chart_capex_breakdown(b_res, o_res)

                # Export
                if o_res is not None:
                    payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "baseline": {"coefficients": get_coeffs("b"), "inputs": b_now, "results": b_res},
                        "option": {"coefficients": get_coeffs("o"), "inputs": o_now, "results": o_res},
                        "notes": {
                            "scope": "Early-stage decision support; not certification; not dynamic simulation.",
                            "energy_boundary": "Space heating + water heating + lighting (excludes plug loads/appliances).",
                            "water_boundary": "Indoor water includes toilets, showers, taps, plus dishwasher/washing machine water.",
                            "capex_boundary": "Transparent unit-cost accounting; early-stage benchmark schedule.",
                            "heat_loss_method": "Space heating uses steady-state heat-loss coefficient H_total × HDD × 24 / 1000, then divides by COP.",
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
# TAB 2: FORMULAS (filled from your text; concise + explicit)
# =============================================================================
with tab_formulas:
    st.header("Formulas (model logic)")

    st.markdown(
        """
### 1) Energy consumption

**1.1 Total energy**
- Total Energy (kWh/year) = Space Heating + Water Heating + Lighting

**1.2 Space heating electricity (steady-state heat loss)**
- Space Heating Electricity (kWh/year) = (H_total × HDD × 24 / 1000) ÷ Heating System COP

Where:
- H_total (W/K) = H_floor + H_roof + H_wall + H_window
- HDD = Heating Degree Days (base 18°C), degree-days/year
- 24 converts degree-days to degree-hours per day
- /1000 converts Wh to kWh (since W × hours = Wh)

**1.2.1 Heat-loss components**
- H_floor (W/K) = floorArea × floorU, with floorU = 1 / floorR
- H_roof (W/K) = roofArea × roofU, with roofU = 1 / roofR
- H_wall (W/K) = wallArea × wallU, with wallU = 1 / wallR
- H_window (W/K) = windowArea × windowU

**Geometry (simplified)**
- roofArea (m²) = floorArea
- wallArea (m²) = (4 × sqrt(floorArea) × ceilingHeight) − windowArea

**1.2.2 HDD climate input**
- User selects Closest City → mapped to climate zone → HDD default (base 18°C)
- Custom HDD allowed.

**1.2.3 Heating COP**
- Purchased electricity = Delivered heating ÷ COP
- If COP ≤ 0, purchased is set to 0 (guardrail).

**1.3 Water heating electricity**
- Water Heating Electricity (kWh/year) = Water Heating Delivered ÷ Water Heating COP

Delivered hot water energy:
- Water Heating Delivered (kWh/year) = (V_hot_annual × ΔT × Cp) ÷ 3600

Where:
- Cp = 4.186 kJ/kg·°C
- 3600 converts kJ → kWh (1 kWh = 3600 kJ)
- 1 L ≈ 1 kg (density assumption)

Hot water volume:
- V_hot_annual (L/year) =
  (V_shower × hot_share_shower) +
  (V_tap × hot_share_tap) +
  (V_laundry × hot_share_laundry) +
  (V_dishwasher × hot_share_dishwasher)

Note: Toilets excluded from hot water.

Temperature difference:
- ΔT (°C) = hotWater_setpoint − coldWater_inlet

**1.4 Lighting electricity**
- Lighting (kWh/year) = (numberOfLights × wattsPerLight × hoursPerDay × 365) ÷ 1000

---

### 2) Water consumption
- Water (m³/year) = (V_toilet + V_shower + V_tap + V_laundry + V_dishwasher) ÷ 1000

End uses:
- Toilet (L/year) = householdSize × flushes/person/day × L/flush × 365
- Shower (L/year) = householdSize × showers/person/day × minutes/shower × L/min × 365
- Tap (L/year) = householdSize × tapMinutes/person/day × L/min × 365
- Laundry (L/year) = cycles/week × L/cycle × 52 (if present)
- Dishwasher (L/year) = cycles/week × L/cycle × 52 (if present)

---

### 3) Operational carbon
- Operational Carbon (kgCO₂e/year) = CO₂_electricity + CO₂_water

Where:
- CO₂_electricity = Total Energy × grid emission factor (kgCO₂e/kWh)
- CO₂_water = Water (m³) × water emission factor (kgCO₂e/m³)

---

### 4) Financials
**4.1 Operating cost (Opex)**
- Opex (NZD/year) = (Total Energy × electricity tariff) + (Water × water tariff)

**4.2 Capex (installed)**
- Capex total (NZD) = Envelope + Systems + Fixtures

Envelope:
- Roof = roof capex/m² × roofArea
- Wall = wall capex/m² × wallArea
- Floor = floor capex/m² × floorArea
- Windows = window capex/m² × windowArea

Systems:
- Space heating install + Water heating install

Fixtures:
- Toilet install + Shower install + Tap install

**4.3 Metrics**
- Annual savings (NZD/year) = Opex_baseline − Opex_option
- Payback (years) = (Capex_option − Capex_baseline) ÷ Annual savings
        """
    )

# =============================================================================
# TAB 3: DATA SOURCES (single big table)
# =============================================================================
with tab_sources:
    st.header("Data sources (provenance table)")
    st.caption("This table documents each variable, its role, defaults/options, and source references (as used in the model).")

    rows = [
        [1,"Energy","Total Energy","Total annual household energy use","Calculated","Space heating + water heating + lighting","Derived","Primary output"],
        [2,"Energy","Space Heating Energy","Electricity for space heating","Calculated","(H_total × HDD × 24 / 1000) ÷ COP","MBIE (2023)","Steady-state early-stage method"],
        [3,"Energy","Heating Degree Days (HDD)","Climate severity (base 18 °C)","Lookup / User","Zone1=1200; Zone2=1400; Zone3=1800; Zone4=2200; Zone5=2400; Zone6=3000; Custom","InfraComfort (n.d.); MSD (2006)","City → climate zone"],
        [4,"Energy","Heating System COP","Seasonal heating efficiency","Assumption / User","None=0; Electric resistance=1.0; Heat pump=2.5; High-efficiency HP=3.5; Custom","BRANZ (2023)","Typical NZ systems"],
        [5,"Envelope","Floor R-value","Floor thermal resistance","Assumption / User","Uninsulated=0.6; Basic=1.5; Code=2.0; Good=2.8; Excellent=3.5; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [6,"Envelope","Roof R-value","Roof thermal resistance","Assumption / User","Uninsulated=0.5; Basic=3.0; Code=6.6; Good=8.0; Excellent=10.0; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [7,"Envelope","Wall R-value","Wall thermal resistance","Assumption / User","Uninsulated=0.5; Basic=1.5; Code=2.0; Good=3.0; Excellent=4.0; Custom","MBIE (2023); BRANZ (2023)","NZBC H1 aligned"],
        [8,"Envelope","Window U-value","Glazing heat transfer","Assumption / User","Single=5.8; Double=3.0; Low-E=2.0; Triple=1.0; Custom","BRANZ (2023)","Typical NZ glazing"],
        [9,"Envelope","Envelope Areas","Floor, roof, wall, window areas","User Input","User input (m²)","User-defined","Simplified geometry"],
        [10,"Water Heating","Delivered Hot Water Energy","Energy to heat water","Calculated","(V × ΔT × Cp) ÷ 3600","Engineering standard","Physics-based"],
        [11,"Water Heating","Heat Capacity (Cp)","Thermal constant","Constant","4.186 kJ/kg·°C","Engineering standard","Universal"],
        [12,"Water Heating","Hot Water Fraction – Shower","Portion of shower water heated","Assumption / User","Default=0.9","BRANZ (2023)","Overrideable"],
        [13,"Water Heating","Hot Water Fraction – Tap","Portion of tap water heated","Assumption / User","Default=0.4","BRANZ (2023)","Overrideable"],
        [14,"Water Heating","Hot Water Fraction – Laundry","Portion of laundry water heated","Assumption / User","Default=0.5","BRANZ (2023)","Overrideable"],
        [15,"Water Heating","Hot Water Fraction – Dishwasher","Portion of dishwasher water heated","Assumption / User","Default=1.0","BRANZ (2023)","Overrideable"],
        [16,"Water Heating","Water Heating COP","Hot water system efficiency","Assumption / User","None=0; Electric cylinder=1.0; HPHW=2.0; Custom","BRANZ (2023)","Simplified"],
        [17,"Lighting","Lighting Energy","Annual lighting electricity","Calculated","(Lights × W × h × 365) ÷ 1000","Derived","Standard load"],
        [18,"Lighting","Number of Lights","Installed fixtures","User Input","User input","User-defined","No default required"],
        [19,"Lighting","Wattage per Light","Lamp power","User Input","User input (W)","User-defined","LED–incandescent range"],
        [20,"Lighting","Daily Usage Hours","Average daily use","User Input","User input (h/day)","User-defined","Early-stage"],
        [21,"Water","Total Water Use","Annual indoor water use","Calculated","Sum of end uses","Derived","m³/year"],
        [22,"Water","Toilet Flush Volume","Water per flush","Assumption / User","Single=9; Dual std=5; Dual eff=4; Custom","BRANZ (2023)","NZ fixtures"],
        [23,"Water","Shower Flow Rate","Shower water flow","Assumption / User","Standard=9; Low-flow=7; Efficient=6; Custom","BRANZ (2023)","L/min"],
        [24,"Water","Tap Flow Rate","Tap water flow","Assumption / User","Standard=8; Efficient=6; Very efficient=4; Custom","BRANZ (2023)","L/min"],
        [25,"Water","Laundry Water per Cycle","Washing machine demand","Assumption / User","User input (L/cycle)","BRANZ (2023)","Appliance-dependent"],
        [26,"Water","Dishwasher Water per Cycle","Dishwasher demand","Assumption / User","User input (L/cycle)","BRANZ (2023)","Appliance-dependent"],
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
    df = pd.DataFrame(rows, columns=[
        "Order","Module","Variable / Indicator","Description & Role in Model",
        "Data Type","Selection Options & Default Values","Source / Reference","Notes"
    ])
    st.dataframe(df, use_container_width=True, hide_index=True)
