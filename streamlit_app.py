# streamlit_app.py
import copy
import json
import math
from datetime import datetime

import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt  # (kept; not used right now)
import streamlit.components.v1 as components  # (kept; not used right now)
import altair as alt

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="NZ Housing Sustainability Calculator (Prototype)", layout="wide")
PLACEHOLDER = "— Select —"

# =============================================================================
# HELPERS (DO NOT reference LOOKUP here)
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


def inject_card_css():
    # IMPORTANT: must be injected on every rerun (Streamlit rebuilds DOM).
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
        unsafe_allow_html=True,
    )


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
        # Source: MBIE (2023); BRANZ (2023)
        "windowU_W_per_m2K": {
            "Single glazed": 5.8,
            "Standard double glazed": 3.0,
            "Low-E double glazed": 2.0,
            "High-performance triple glazed": 1.0,
        },
        # Source: PRD Appendix (market benchmark schedule)
        "capex_per_m2": {
            "floor": {"Uninsulated": 0, "Basic": 20, "Code minimum": 40, "Good": 70, "Excellent": 110},
            "roof": {"Uninsulated": 0, "Basic": 15, "Code minimum": 25, "Good": 35, "Excellent": 35},
            "wall": {"Uninsulated": 0, "Basic": 25, "Code minimum": 45, "Good": 75, "Excellent": 120},
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
# HELP TEXTS (safe: built AFTER LOOKUP exists)
# =============================================================================
def build_help(LOOKUP):
    return {
        "closest_city": help_default_source(
            what="Closest major city used to infer Climate Zone and Heating Degree Days (HDD, base 18°C).",
            default="—",
            source="InfraComfort (n.d.); MSD (2006) bands; city→zone mapping embedded in this tool",
            notes="Pick the closest major city. If you have a confirmed HDD, you can override it.",
        ),
        "use_custom_hdd": help_default_source(
            what="Override the default HDD for your selected city/zone.",
            default=False,
            source="User override",
            notes="HDD is annual degree-days (base 18°C). Higher = colder climate.",
        ),
        "hdd_value": help_default_source(
            what="Annual Heating Degree Days (base 18°C).",
            default=2000.0,
            units="degree-days/year",
            source="User override (otherwise from climate zone defaults)",
        ),
        "floor_area": help_default_source(
            what="Conditioned floor area used in heat-loss geometry and intensity metrics.",
            default=float(LOOKUP["defaults"]["core"]["floorArea"]),
            units="m²",
            source="Model default (editable)",
        ),
        "ceiling_height": help_default_source(
            what="Average ceiling height used to approximate wall area.",
            default=float(LOOKUP["defaults"]["core"]["ceilingHeight"]),
            units="m",
            source="Model default (editable)",
        ),
        "household_size": help_default_source(
            what="Number of occupants used for per-person water end-uses.",
            default=int(LOOKUP["defaults"]["core"]["householdSize"]),
            units="people",
            source="Model default (editable)",
        ),
        "window_area": help_default_source(
            what="Total window area for glazing heat-loss.",
            default=float(LOOKUP["defaults"]["core"]["windowArea"]),
            units="m²",
            source="Model default (editable)",
        ),
        "light_n": help_default_source(
            what="Total number of light fixtures.",
            default=int(LOOKUP["defaults"]["lighting"]["numberOfLights"]),
            source="Model default (editable)",
        ),
        "light_watts": help_default_source(
            what="Average wattage per light. Typical LED is often ~6–12W.",
            default=float(LOOKUP["defaults"]["lighting"]["wattsPerLight"]),
            units="W",
            source="Model default (editable)",
        ),
        "light_hours": help_default_source(
            what="Average daily lighting usage time.",
            default=float(LOOKUP["defaults"]["lighting"]["hoursPerDay"]),
            units="hours/day",
            source="Model default (editable)",
        ),
        "r_value": help_default_source(
            what="R-value (m²K/W): higher is better insulation (lower heat loss).",
            source="MBIE (2023); BRANZ (2023) banded defaults embedded in this tool",
            notes="If you select Custom, enter your own R-value and capex rate.",
        ),
        "u_value": help_default_source(
            what="U-value (W/m²K): lower is better glazing performance (less heat loss).",
            source="MBIE/BRANZ typical glazing defaults embedded in this tool",
            notes="If you select Custom, enter your own U-value and window capex rate.",
        ),
        "cop": help_default_source(
            what="COP (Coefficient of Performance): higher means less purchased electricity for the same delivered heat.",
            source="BRANZ (2023) typical systems embedded in this tool",
        ),
        "fixture": help_default_source(
            what="Select fixture type to set water use rate and install capex.",
            source="BRANZ (2023) typical fixtures embedded in this tool",
            notes="Custom lets you enter your own litres/flush or L/min and capex.",
        ),
        "wash_has": help_default_source(
            what="Include washing machine water use.",
            default=bool(LOOKUP["defaults"]["washing_machine"]["hasAppliance"]),
            source="Model default (editable)",
        ),
        "dish_has": help_default_source(
            what="Include dishwasher water use.",
            default=bool(LOOKUP["defaults"]["dishwasher"]["hasAppliance"]),
            source="Model default (editable)",
        ),
        "usage_general": help_default_source(
            what="Behavioural assumptions for indoor water end-uses (per person).",
            source="Model defaults (editable)",
            notes="Use if you want to tailor the model to your household behaviour.",
        ),
        "hw_frac": help_default_source(
            what="Hot water fraction (0–1) for each end-use. Toilets are always treated as cold water.",
            default="Shower 0.9; Tap 0.4; Laundry 0.5; Dishwasher 1.0",
            source="BRANZ (2023) placeholders + user override",
        ),
        "tariffs": help_default_source(
            what="Retail tariffs vary by region/provider; set to match your bill.",
            default=f"Electricity {LOOKUP['constants']['electricity_tariff_nzd_per_kwh_default']} NZD/kWh; Water {LOOKUP['constants']['water_tariff_nzd_per_m3_default']} NZD/m³",
            source="Electricity Authority (2024); Auckland Council (2025)",
        ),
        "efs": help_default_source(
            what="Emission factors for operational carbon.",
            default=f"Grid {LOOKUP['constants']['grid_emission_factor_kgco2e_per_kwh']} kgCO₂e/kWh; Water {LOOKUP['constants']['water_emission_factor_kgco2e_per_m3']} kgCO₂e/m³",
            source="MfE (2024)",
            notes="Adjust only if you have a justified factor for your reporting boundary.",
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


# =============================================================================
# INTERACTIVE CHART HELPERS (Altair)
# =============================================================================
def _mk_long_df_for_breakdown(baseline: dict, option: dict | None, value_key: str, order: list[str] | None = None):
    rows = []
    for k, v in baseline.items():
        rows.append({"Scenario": "Baseline", "Component": k, value_key: float(v)})
    if option is not None:
        for k, v in option.items():
            rows.append({"Scenario": "Option", "Component": k, value_key: float(v)})

    df = pd.DataFrame(rows)
    if df.empty:
        return df

    if order:
        df["Component"] = pd.Categorical(df["Component"], categories=order, ordered=True)
        df = df.sort_values(["Component", "Scenario"])
    return df


def interactive_grouped_bar(df: pd.DataFrame, value_col: str, title: str, y_label: str):
    if df is None or df.empty:
        st.info("No data to chart yet.")
        return

    chart = (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X("Component:N", sort=None, title=None),
            xOffset=alt.XOffset("Scenario:N"),
            y=alt.Y(f"{value_col}:Q", title=y_label),
            color=alt.Color("Scenario:N", legend=alt.Legend(orient="top")),
            tooltip=[
                "Scenario:N",
                "Component:N",
                alt.Tooltip(f"{value_col}:Q", format=",.2f"),
            ],
        )
        .properties(height=280, title=title)
        .interactive()
    )

    st.altair_chart(chart, use_container_width=True)


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
# STATE + FLOW
# =============================================================================
COPY_KEYS = [
    "closestCity",
    "use_custom_hdd",
    "hdd_override_value",
    "floorArea",
    "ceilingHeight",
    "householdSize",
    "windowArea",
    "roofRLabel",
    "roofR_custom",
    "roofCost_custom",
    "wallRLabel",
    "wallR_custom",
    "wallCost_custom",
    "floorRLabel",
    "floorR_custom",
    "floorCost_custom",
    "windowULabel",
    "windowU_custom",
    "windowCost_custom",
    "spaceHeatingSystem",
    "spaceCOP_custom",
    "spaceInstall_custom",
    "waterHeatingSystem",
    "waterCOP_custom",
    "waterInstall_custom",
    "toiletType",
    "toilet_value_custom",
    "toilet_cost_custom",
    "showerType",
    "shower_value_custom",
    "shower_cost_custom",
    "tapType",
    "tap_value_custom",
    "tap_cost_custom",
    "wash_has",
    "wash_cycles",
    "wash_L",
    "dish_has",
    "dish_cycles",
    "dish_L",
    "light_n",
    "light_watts",
    "light_hours",
    "hotWater_setpoint_C",
    "coldWater_inlet_C",
    "toiletFlushes_ppd",
    "showers_ppd",
    "minutes_per_shower",
    "tapMinutes_ppd",
    "hw_frac_shower",
    "hw_frac_tap",
    "hw_frac_laundry",
    "hw_frac_dishwasher",
    "coef_grid_ef",
    "coef_water_ef",
    "coef_elec_tariff",
    "coef_water_tariff",
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

    # categorical defaults
    cat_keys = [
        "roofRLabel",
        "wallRLabel",
        "floorRLabel",
        "windowULabel",
        "spaceHeatingSystem",
        "waterHeatingSystem",
        "toiletType",
        "showerType",
        "tapType",
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
    if label in (PLACEHOLDER, None):
        return
    if label == "Custom":
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
    if label in (PLACEHOLDER, None):
        return
    if label == "Custom":
        return
    cop = LOOKUP["systems"][sys_block]["cop"][label]
    cost = LOOKUP["systems"][sys_block]["install_cost_nzd"][label]
    st.caption(f"Performance: **COP={cop:g}** · Install capex: **{fmt_money(cost)}**")


def show_fixture_caption(kind: str, label: str):
    if label in (PLACEHOLDER, None):
        return
    if label == "Custom":
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
# INPUT PANELS (Reset REMOVED)
# =============================================================================
def scenario_panel(prefix: str, title: str):
    st.subheader(title)

    if st.button(f"Use Code Minimum ({title})", key=f"{prefix}_btn_code_min", use_container_width=True):
        apply_code_minimum(prefix)
        st.rerun()

    # 1) Core + Climate + Lighting
    with st.expander("Core climate + lighting", expanded=True):
        cc1, cc2 = st.columns(2, gap="small")

        with cc1:
            select_with_placeholder("Closest city", CITIES, key=f"{prefix}_closestCity", help_text=HELP["closest_city"])
            show_city_caption(prefix)

            st.checkbox("Use custom HDD", key=f"{prefix}_use_custom_hdd", help=HELP["use_custom_hdd"])
            if st.session_state[f"{prefix}_use_custom_hdd"]:
                st.number_input(
                    "Custom HDD (base 18°C)",
                    min_value=0.0,
                    max_value=6000.0,
                    step=50.0,
                    key=f"{prefix}_hdd_override_value",
                    help=HELP["hdd_value"],
                )
                st.caption(f"Using custom HDD: **{float(st.session_state[f'{prefix}_hdd_override_value']):g}**")

            st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key=f"{prefix}_floorArea", help=HELP["floor_area"])
            st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key=f"{prefix}_ceilingHeight", help=HELP["ceiling_height"])
            st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key=f"{prefix}_householdSize", help=HELP["household_size"])
            st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key=f"{prefix}_windowArea", help=HELP["window_area"])

        with cc2:
            st.markdown("**Lighting**")
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n", help=HELP["light_n"])
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts", help=HELP["light_watts"])
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours", help=HELP["light_hours"])
            st.caption("Formula: count × watts × hours/day × 365 ÷ 1000")

    # 2) Envelope + Systems + Water
    with st.expander("Envelope + systems + water", expanded=False):
        ec1, ec2 = st.columns(2, gap="small")

        with ec1:
            with st.expander("Thermal envelope", expanded=True):
                select_with_placeholder("Roof insulation", ROOF_OPTS, key=f"{prefix}_roofRLabel", help_text=HELP["r_value"])
                show_envelope_caption("roof", st.session_state[f"{prefix}_roofRLabel"])
                if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                    st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom", help=HELP["r_value"])
                    st.number_input("Roof capex (NZD/m² roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom")

                select_with_placeholder("Wall insulation", WALL_OPTS, key=f"{prefix}_wallRLabel", help_text=HELP["r_value"])
                show_envelope_caption("wall", st.session_state[f"{prefix}_wallRLabel"])
                if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                    st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom", help=HELP["r_value"])
                    st.number_input("Wall capex (NZD/m² wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom")

                select_with_placeholder("Floor insulation", FLOOR_OPTS, key=f"{prefix}_floorRLabel", help_text=HELP["r_value"])
                show_envelope_caption("floor", st.session_state[f"{prefix}_floorRLabel"])
                if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                    st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom", help=HELP["r_value"])
                    st.number_input("Floor capex (NZD/m² floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom")

                select_with_placeholder("Window type", WIN_OPTS, key=f"{prefix}_windowULabel", help_text=HELP["u_value"])
                show_envelope_caption("window", st.session_state[f"{prefix}_windowULabel"])
                if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                    st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom", help=HELP["u_value"])
                    st.number_input("Windows capex (NZD/m² window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom")

        with ec2:
            with st.expander("Systems", expanded=True):
                select_with_placeholder("Space heating system", SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help_text=HELP["cop"])
                show_system_caption("space_heating", st.session_state[f"{prefix}_spaceHeatingSystem"])
                if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                    st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_spaceCOP_custom", help=HELP["cop"])
                    st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom")

                select_with_placeholder("Water heating system", WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help_text=HELP["cop"])
                show_system_caption("water_heating", st.session_state[f"{prefix}_waterHeatingSystem"])
                if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                    st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_waterCOP_custom", help=HELP["cop"])
                    st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_waterInstall_custom")

            with st.expander("Water fixtures + appliances", expanded=True):
                select_with_placeholder("Toilet type", TOILET_OPTS, key=f"{prefix}_toiletType", help_text=HELP["fixture"])
                show_fixture_caption("toilet", st.session_state[f"{prefix}_toiletType"])
                if st.session_state[f"{prefix}_toiletType"] == "Custom":
                    st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toilet_value_custom", help=HELP["fixture"])
                    st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom")

                select_with_placeholder("Shower type", SHOWER_OPTS, key=f"{prefix}_showerType", help_text=HELP["fixture"])
                show_fixture_caption("shower", st.session_state[f"{prefix}_showerType"])
                if st.session_state[f"{prefix}_showerType"] == "Custom":
                    st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_shower_value_custom", help=HELP["fixture"])
                    st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_shower_cost_custom")

                select_with_placeholder("Tap type", TAP_OPTS, key=f"{prefix}_tapType", help_text=HELP["fixture"])
                show_fixture_caption("tap", st.session_state[f"{prefix}_tapType"])
                if st.session_state[f"{prefix}_tapType"] == "Custom":
                    st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tap_value_custom", help=HELP["fixture"])
                    st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tap_cost_custom")

                st.divider()
                st.selectbox("Has washing machine?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_wash_has", help=HELP["wash_has"])
                if st.session_state[f"{prefix}_wash_has"] == "Yes":
                    st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles")
                    st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L")

                st.selectbox("Has dishwasher?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_dish_has", help=HELP["dish_has"])
                if st.session_state[f"{prefix}_dish_has"] == "Yes":
                    st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles")
                    st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L")

    # 3) Optional
    with st.expander("Optional: usage + fractions + tariffs + emissions", expanded=False):
        st.caption("Use this section only if you want to tailor behaviour assumptions or local pricing/factors.")
        oc1, oc2 = st.columns(2, gap="small")

        with oc1:
            with st.expander("Usage assumptions", expanded=True):
                st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C", help=HELP["usage_general"])
                st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C", help=HELP["usage_general"])
                st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd", help=HELP["usage_general"])
                st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd", help=HELP["usage_general"])
                st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower", help=HELP["usage_general"])
                st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd", help=HELP["usage_general"])

        with oc2:
            with st.expander("Hot water fractions", expanded=True):
                st.caption(HELP["hw_frac"])
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
# CARDS RENDERING (2 columns x 3 rows)
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
        unsafe_allow_html=True,
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
        unsafe_allow_html=True,
    )


def metric_vals(b_val: float | None, o_val: float | None, dec: int):
    b_s = fmt_num(b_val, dec) if b_val is not None else "—"
    o_s = fmt_num(o_val, dec) if o_val is not None else "—"
    if (b_val is None) or (o_val is None):
        return b_s, o_s, "—", "—"
    d = o_val - b_val
    return b_s, o_s, fmt_num(d, dec), direction_arrow(d)


# =============================================================================
# APP START
# =============================================================================
init_defaults()

# Seed option once baseline is calculated + unlocked
if st.session_state.get("baseline_ready", False) and st.session_state.get("option_unlocked", False) and not st.session_state.get("option_seeded", False):
    seed_option_from_baseline_once()

# Build option lists AFTER LOOKUP is defined
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
    left, right = st.columns([1.45, 1.0], gap="large")

    INPUT_H = 820
    RESULTS_H = 820

    # -------------------------
    # LEFT: inputs
    # -------------------------
    with left:
        try:
            input_box = st.container(height=INPUT_H, border=True)
        except TypeError:
            input_box = st.container()

        with input_box:
            scenario_panel("b", "Baseline")

            b_now = get_scenario("b")
            missing_b = validate_scenario(b_now)

            st.divider()
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
                st.success("Baseline calculated. You can now unlock and compare Option.")

            if st.session_state.get("option_unlocked", False):
                st.divider()
                scenario_panel("o", "Option")

                o_now = get_scenario("o")
                missing_o = validate_scenario(o_now)

                st.divider()
                if not st.session_state.get("compare_ready", False):
                    if missing_o:
                        st.info("Option incomplete. Missing: " + ", ".join(missing_o))
                    if st.button("Calculate & Compare", use_container_width=True, disabled=bool(missing_o)):
                        st.session_state["compare_ready"] = True
                        st.rerun()
                else:
                    st.success("Comparison activated. Editing inputs will update results live.")

    # -------------------------
    # RIGHT: results
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
                st.info("Fill Baseline inputs and click **Calculate Baseline**.")
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
                # Values
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

                # Payback
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

                # Layout 2 cols x 3 rows
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

                # -------------------------
                # INTERACTIVE CHARTS (safe placement: only here, at same indent level)
                # -------------------------
                st.divider()
                st.markdown("### Interactive charts")

                # Energy breakdown (purchased kWh/year)
                b_energy_breakdown = {
                    "Space heating": b_res["spaceHeating"]["Q_purchased_kwh_y"],
                    "Water heating": b_res["waterHeating"]["Q_purchased_kwh_y"],
                    "Lighting": b_res["lighting"]["Q_total_kwh_y"],
                }
                o_energy_breakdown = None
                if o_res is not None:
                    o_energy_breakdown = {
                        "Space heating": o_res["spaceHeating"]["Q_purchased_kwh_y"],
                        "Water heating": o_res["waterHeating"]["Q_purchased_kwh_y"],
                        "Lighting": o_res["lighting"]["Q_total_kwh_y"],
                    }

                df_energy = _mk_long_df_for_breakdown(
                    baseline=b_energy_breakdown,
                    option=o_energy_breakdown,
                    value_key="kWh_per_year",
                    order=["Space heating", "Water heating", "Lighting"],
                )
                interactive_grouped_bar(df_energy, "kWh_per_year", "Energy breakdown (purchased electricity)", "kWh/year")

                # Water end-use breakdown (m³/year)
                b_water_breakdown = b_res["waterConsumption"]["breakdown_m3_y"]
                o_water_breakdown = o_res["waterConsumption"]["breakdown_m3_y"] if o_res is not None else None

                df_water = _mk_long_df_for_breakdown(
                    baseline=b_water_breakdown,
                    option=o_water_breakdown,
                    value_key="m3_per_year",
                    order=["Toilets", "Showers", "Taps", "Laundry", "Dishwasher"],
                )
                interactive_grouped_bar(df_water, "m3_per_year", "Water end-use breakdown", "m³/year")

                # Optional JSON export only when compare is ready
                if o_res is not None:
                    payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "baseline": {"coefficients": get_coeffs("b"), "inputs": b_now, "results": b_res},
                        "option": {"coefficients": get_coeffs("o"), "inputs": o_now, "results": o_res},
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
# TAB 2/3 placeholders
# =============================================================================
with tab_formulas:
    st.header("Formulas")
    st.caption("Use your existing formulas tab content here (unchanged).")

with tab_sources:
    st.header("Data sources")
    st.caption("Use your existing data sources tab content here (unchanged).")
