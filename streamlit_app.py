# streamlit_app.py
import copy
import json
import math
from datetime import datetime
from typing import Any, Callable

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="NZ Housing Sustainability Calculator (Prototype)", layout="wide")
PLACEHOLDER = "— Select —"

# Build stamp
st.caption("BUILD: 2025-12-25 vREFACTORED+UXWRITING")

# =============================================================================
# MINIMAL CSS (cards + sticky action bar)
# =============================================================================
def inject_min_css() -> None:
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

        .sec-h{
          font-weight: 900;
          font-size: 1.05rem;
          margin: 2px 0 8px 0;
        }

        .fixed-bar{
          position: sticky;
          bottom: 0;
          z-index: 999;
          background: var(--background-color, white);
          padding-top: 8px;
          padding-bottom: 8px;
          border-top: 1px solid rgba(49, 51, 63, 0.18);
        }

        .status-pill{
          display:inline-block;
          padding: 2px 8px;
          border-radius: 999px;
          border: 1px solid rgba(49, 51, 63, 0.18);
          font-size: 0.82rem;
          font-weight: 700;
          opacity: 0.95;
          margin-right: 6px;
          margin-bottom: 6px;
          white-space: nowrap;
        }
        .pill-ok{ background: rgba(0, 128, 0, 0.06); }
        .pill-warn{ background: rgba(255, 165, 0, 0.08); }
        .muted{ opacity: 0.75; }
        </style>
        """,
        unsafe_allow_html=True,
    )


inject_min_css()

# =============================================================================
# LOOKUP TABLES (Single Source of Truth)
# =============================================================================
LOOKUP: dict[str, Any] = {
    "constants": {
        "grid_emission_factor_kgco2e_per_kwh": 0.0729,  # MfE (2024) 2023 factor
        "water_emission_factor_kgco2e_per_m3": 0.0349,  # MfE (2024)
        "electricity_tariff_nzd_per_kwh_default": 0.312,  # Electricity Authority (2024)
        "water_tariff_nzd_per_m3_default": 2.296,  # Auckland Council (2025)
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
            "cop": {"None": 0.0, "Electric storage cylinder": 1.0, "Heat pump hot water": 2.0},
            "install_cost_nzd": {"None": 0, "Electric storage cylinder": 3500, "Heat pump hot water": 6500},
        },
    },
    "fixtures": {
        "toilet": {
            "l_per_flush": {"Single flush": 9, "Dual flush standard (avg 5 L)": 5, "Dual flush efficient (avg 4 L)": 4},
            "install_cost_nzd": {"Single flush": 300, "Dual flush standard (avg 5 L)": 450, "Dual flush efficient (avg 4 L)": 650},
        },
        "shower": {"l_per_min": {"Standard": 9, "Low flow": 7, "Efficient": 6}, "install_cost_nzd": {"Standard": 50, "Low flow": 120, "Efficient": 220}},
        "tap": {"l_per_min": {"Standard": 8, "Efficient": 6, "Very efficient": 4}, "install_cost_nzd": {"Standard": 70, "Efficient": 150, "Very efficient": 250}},
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
# HELPERS (tooltips)
# =============================================================================
def help_default_source(
    what: str,
    default: Any = None,
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
        parts.append(f"Basis: {source}.")
    if notes:
        parts.append(notes)
    return " ".join(parts)


def _path_get(dct: dict[str, Any], path: tuple[str, ...]) -> Any:
    cur: Any = dct
    for k in path:
        cur = cur[k]
    return cur


def build_help(lookup: dict[str, Any]) -> dict[str, str]:
    specs: dict[str, dict[str, Any]] = {
        "closest_city": dict(
            what="Used to infer Climate Zone and Heating Degree Days (HDD, base 18°C) for space heating.",
            source="HDD bands aligned with common NZ early-stage modelling references (e.g., MSD/BRANZ-style climate severity bands).",
            notes="Pick the closest major city. If you already have an HDD value, turn on Custom HDD.",
        ),
        "use_custom_hdd": dict(
            what="Override the default HDD for your selected city/zone.",
            default=False,
            source="User override",
            notes="HDD is annual degree-days (base 18°C). Higher = colder climate = more space heating.",
        ),
        "hdd_value": dict(
            what="Annual Heating Degree Days (base 18°C).",
            default=2000.0,
            units="degree-days/year",
            source="User override (otherwise from climate zone defaults)",
        ),
        "floor_area": dict(
            what="Conditioned floor area used in heat-loss geometry and intensity metrics.",
            default_path=("defaults", "core", "floorArea"),
            units="m²",
            source="Model default (editable)",
        ),
        "ceiling_height": dict(
            what="Average ceiling height used to approximate wall area.",
            default_path=("defaults", "core", "ceilingHeight"),
            units="m",
            source="Model default (editable)",
        ),
        "household_size": dict(
            what="Number of occupants used for per-person water end-uses.",
            default_path=("defaults", "core", "householdSize"),
            units="people",
            source="Model default (editable)",
        ),
        "window_area": dict(
            what="Total window area for glazing heat loss.",
            default_path=("defaults", "core", "windowArea"),
            units="m²",
            source="Model default (editable)",
        ),
        "r_value": dict(
            what="R-value (m²K/W): higher is better insulation (lower heat loss).",
            source="NZ early-stage envelope benchmarking (MBIE/NZBC H1 style bands + BRANZ typical values).",
            notes="Custom lets you enter your own R-value and capex rate.",
        ),
        "u_value": dict(
            what="U-value (W/m²K): lower is better glazing (less heat loss).",
            source="BRANZ-style typical glazing U-values used in early-stage assessments.",
            notes="Custom lets you enter your own U-value and window capex rate.",
        ),
        "cop": dict(
            what="COP: higher means less purchased electricity for the same delivered heat.",
            source="Typical NZ system performance ranges used in early-stage modelling.",
        ),
        "fixture": dict(
            what="Sets indoor water use rate and install capex for that fixture.",
            source="BRANZ-style typical fixture rates; editable.",
            notes="Custom lets you enter litres/flush or L/min and capex.",
        ),
        "tariffs": dict(
            what="Retail tariffs vary by region/provider; adjust to match your bill.",
            default=(
                f"Electricity {lookup['constants']['electricity_tariff_nzd_per_kwh_default']} NZD/kWh; "
                f"Water {lookup['constants']['water_tariff_nzd_per_m3_default']} NZD/m³"
            ),
            source="Public NZ tariff benchmarks (editable).",
        ),
        "efs": dict(
            what="Emission factors used for operational carbon.",
            default=(
                f"Grid {lookup['constants']['grid_emission_factor_kgco2e_per_kwh']} kgCO₂e/kWh; "
                f"Water {lookup['constants']['water_emission_factor_kgco2e_per_m3']} kgCO₂e/m³"
            ),
            source="MfE emission factor guidance (editable).",
        ),
        "hw_frac": dict(
            what="Hot water fraction (0–1) per end-use. Toilets are always treated as cold water.",
            default="Shower 0.9; Tap 0.4; Laundry 0.5; Dishwasher 1.0",
            source="Early-stage behavioural assumptions; editable.",
        ),
        "wash_has": dict(what="Include washing machine water use.", default=False, source="Model default (editable)"),
        "dish_has": dict(what="Include dishwasher water use.", default=False, source="Model default (editable)"),
    }

    out: dict[str, str] = {}
    for k, spec in specs.items():
        default = spec.get("default", None)
        if "default_path" in spec:
            default = _path_get(lookup, spec["default_path"])
        out[k] = help_default_source(
            what=spec["what"],
            default=default,
            source=spec.get("source"),
            notes=spec.get("notes"),
            units=spec.get("units"),
        )
    return out


HELP = build_help(LOOKUP)

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


def _yn_to_bool(v: str) -> bool | None:
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


BUCKETS = {"Uninsulated", "Basic", "Code minimum", "Good", "Excellent"}


def _bucket_from_label(label: str) -> str:
    return label if label in BUCKETS else "Uninsulated"


def select_with_placeholder(label: str, options: list[str], key: str, help_text: str | None = None) -> str:
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)


# =============================================================================
# GENERIC RESOLVERS
# =============================================================================
def resolve_choice(
    label: str,
    *,
    lookup_map: dict[str, Any] | None = None,
    custom_key: str | None = None,
    placeholder_returns_none: bool = True,
    placeholder_value: float = 0.0,
    custom_label: str = "Custom",
    cast: Callable[[Any], Any] = float,
) -> Any:
    if label == PLACEHOLDER:
        return None if placeholder_returns_none else cast(placeholder_value)
    if label != custom_label:
        if lookup_map is None:
            raise ValueError("lookup_map is required when label is not Custom.")
        return cast(lookup_map[label])
    if custom_key is None:
        raise ValueError("custom_key is required when label is Custom.")
    return cast(st.session_state[custom_key])


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


def resolve_install_cost(label: str, custom_key: str, sys_block: str) -> float:
    if label == PLACEHOLDER:
        return 0.0
    if label != "Custom":
        return float(LOOKUP["systems"][sys_block]["install_cost_nzd"][label])
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
def _geometry_areas(floor_area: float, ceiling_h: float, window_area: float) -> dict[str, float]:
    roof_area = floor_area
    perimeter = 4.0 * math.sqrt(max(floor_area, 0.0))
    wall_area = max(perimeter * ceiling_h - window_area, 0.0)
    return {"roof": roof_area, "wall": wall_area, "floor": floor_area, "window": window_area}


def calculate_space_heating(s: dict[str, Any]) -> dict[str, Any]:
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


def calculate_water_enduse(s: dict[str, Any]) -> dict[str, Any]:
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


def calculate_water_heating_from_enduse(s: dict[str, Any], enduse_L_y: dict[str, float]) -> dict[str, Any]:
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

    return {"V_hot_L_y": V_hot_L_y, "deltaT_C": deltaT, "Q_delivered_kwh_y": delivered_kwh, "Q_purchased_kwh_y": purchased_kwh, "warning": warning, "fractions_used": fr}


def calculate_lighting(s: dict[str, Any]) -> dict[str, float]:
    L = s["lighting"]
    Q = (L["numberOfLights"] * L["wattsPerLight"] * L["hoursPerDay"] * 365.0) / 1000.0
    return {"Q_total_kwh_y": Q}


def calculate_operational_carbon(total_kwh_y: float, total_m3_y: float, coeffs: dict[str, float]) -> dict[str, float]:
    CO2_e = total_kwh_y * coeffs["grid_ef"]
    CO2_w = total_m3_y * coeffs["water_ef"]
    return {"CO2_total_kg_y": CO2_e + CO2_w, "CO2_electricity_kg_y": CO2_e, "CO2_water_kg_y": CO2_w}


def calculate_opex(total_kwh_y: float, total_m3_y: float, coeffs: dict[str, float]) -> dict[str, float]:
    c_e = total_kwh_y * coeffs["elec_tariff"]
    c_w = total_m3_y * coeffs["water_tariff"]
    return {"opex_total_nzd_y": c_e + c_w, "opex_electricity_nzd_y": c_e, "opex_water_nzd_y": c_w}


def compute_capex_total(s: dict[str, Any]) -> dict[str, Any]:
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


def calculate_scenario(s: dict[str, Any], coeffs: dict[str, float]) -> dict[str, Any]:
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
STATE_FLAGS_DEFAULTS = {"base_ready": False, "improve_unlocked": False, "improve_seeded": False, "compare_ready": False}

BASE_DEFAULTS: dict[str, Any] = {
    "coef_grid_ef": ("constants", "grid_emission_factor_kgco2e_per_kwh"),
    "coef_water_ef": ("constants", "water_emission_factor_kgco2e_per_m3"),
    "coef_elec_tariff": ("constants", "electricity_tariff_nzd_per_kwh_default"),
    "coef_water_tariff": ("constants", "water_tariff_nzd_per_m3_default"),
    "floorArea": ("defaults", "core", "floorArea"),
    "ceilingHeight": ("defaults", "core", "ceilingHeight"),
    "householdSize": ("defaults", "core", "householdSize"),
    "windowArea": ("defaults", "core", "windowArea"),
    "light_n": ("defaults", "lighting", "numberOfLights"),
    "light_watts": ("defaults", "lighting", "wattsPerLight"),
    "light_hours": ("defaults", "lighting", "hoursPerDay"),
    "wash_has": "No",
    "wash_cycles": ("defaults", "washing_machine", "cyclesPerWeek"),
    "wash_L": ("defaults", "washing_machine", "waterPerCycle_L"),
    "dish_has": "No",
    "dish_cycles": ("defaults", "dishwasher", "cyclesPerWeek"),
    "dish_L": ("defaults", "dishwasher", "waterPerCycle_L"),
    "closestCity": PLACEHOLDER,
    "use_custom_hdd": False,
    "hdd_override_value": 2000.0,
    "roofR_custom": 6.6,
    "roofCost_custom": 25.0,
    "wallR_custom": 2.0,
    "wallCost_custom": 45.0,
    "floorR_custom": 2.0,
    "floorCost_custom": 40.0,
    "windowU_custom": 3.0,
    "windowCost_custom": 600.0,
    "spaceCOP_custom": 2.5,
    "spaceInstall_custom": 4500.0,
    "waterCOP_custom": 2.0,
    "waterInstall_custom": 6500.0,
    "toilet_value_custom": 5.0,
    "toilet_cost_custom": 450.0,
    "shower_value_custom": 7.0,
    "shower_cost_custom": 120.0,
    "tap_value_custom": 6.0,
    "tap_cost_custom": 150.0,
    "hotWater_setpoint_C": ("defaults", "usage", "hotWater_setpoint_C"),
    "coldWater_inlet_C": ("defaults", "usage", "coldWater_inlet_C"),
    "toiletFlushes_ppd": ("defaults", "usage", "toiletFlushes_per_person_day"),
    "showers_ppd": ("defaults", "usage", "showers_per_person_day"),
    "minutes_per_shower": ("defaults", "usage", "minutes_per_shower"),
    "tapMinutes_ppd": ("defaults", "usage", "tapMinutes_per_person_day"),
    "hw_frac_shower": ("defaults", "usage", "hot_water_fractions", "shower"),
    "hw_frac_tap": ("defaults", "usage", "hot_water_fractions", "tap"),
    "hw_frac_laundry": ("defaults", "usage", "hot_water_fractions", "laundry"),
    "hw_frac_dishwasher": ("defaults", "usage", "hot_water_fractions", "dishwasher"),
}

CAT_KEYS = ["roofRLabel", "wallRLabel", "floorRLabel", "windowULabel", "spaceHeatingSystem", "waterHeatingSystem", "toiletType", "showerType", "tapType"]


def init_defaults() -> None:
    for k, v in STATE_FLAGS_DEFAULTS.items():
        st.session_state.setdefault(k, v)

    for p in ["b", "i"]:
        for suffix, spec in BASE_DEFAULTS.items():
            key = f"{p}_{suffix}"
            if isinstance(spec, tuple):
                st.session_state.setdefault(key, _path_get(LOOKUP, spec))
            else:
                st.session_state.setdefault(key, spec)

        for k in CAT_KEYS:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)


def seed_improve_from_base_once() -> None:
    for k, v in list(st.session_state.items()):
        if k.startswith("b_"):
            st.session_state["i_" + k[2:]] = copy.deepcopy(v)
    st.session_state["improve_seeded"] = True


def apply_code_minimum(prefix: str) -> None:
    st.session_state[f"{prefix}_roofRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_wallRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_floorRLabel"] = "Code minimum"
    st.session_state[f"{prefix}_windowULabel"] = "Standard double glazed"
    st.session_state[f"{prefix}_spaceHeatingSystem"] = "Electric resistance heater"
    st.session_state[f"{prefix}_waterHeatingSystem"] = "Electric storage cylinder"
    st.session_state[f"{prefix}_toiletType"] = "Dual flush standard (avg 5 L)"
    st.session_state[f"{prefix}_showerType"] = "Standard"
    st.session_state[f"{prefix}_tapType"] = "Standard"


def get_coeffs(prefix: str) -> dict[str, float]:
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
def get_scenario(prefix: str) -> dict[str, Any]:
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
        "roofRValue": resolve_choice(roof_label, lookup_map=LOOKUP["thermal_envelope"]["roofR_m2K_per_W"], custom_key=f"{prefix}_roofR_custom", placeholder_returns_none=True),
        "wallRValue": resolve_choice(wall_label, lookup_map=LOOKUP["thermal_envelope"]["wallR_m2K_per_W"], custom_key=f"{prefix}_wallR_custom", placeholder_returns_none=True),
        "floorRValue": resolve_choice(floor_label, lookup_map=LOOKUP["thermal_envelope"]["floorR_m2K_per_W"], custom_key=f"{prefix}_floorR_custom", placeholder_returns_none=True),
        "windowUValue": resolve_choice(win_label, lookup_map=LOOKUP["thermal_envelope"]["windowU_W_per_m2K"], custom_key=f"{prefix}_windowU_custom", placeholder_returns_none=True),
        "spaceHeatingCOP": resolve_choice(space_sys, lookup_map=LOOKUP["systems"]["space_heating"]["cop"], custom_key=f"{prefix}_spaceCOP_custom", placeholder_returns_none=True),
        "waterHeatingCOP": resolve_choice(water_sys, lookup_map=LOOKUP["systems"]["water_heating"]["cop"], custom_key=f"{prefix}_waterCOP_custom", placeholder_returns_none=True),
        "toilet_L_per_flush": resolve_choice(toilet, lookup_map=LOOKUP["fixtures"]["toilet"]["l_per_flush"], custom_key=f"{prefix}_toilet_value_custom", placeholder_returns_none=True),
        "shower_L_per_min": resolve_choice(shower, lookup_map=LOOKUP["fixtures"]["shower"]["l_per_min"], custom_key=f"{prefix}_shower_value_custom", placeholder_returns_none=True),
        "tap_L_per_min": resolve_choice(tap, lookup_map=LOOKUP["fixtures"]["tap"]["l_per_min"], custom_key=f"{prefix}_tap_value_custom", placeholder_returns_none=True),
        "lighting": {
            "numberOfLights": int(st.session_state[f"{prefix}_light_n"]),
            "wattsPerLight": float(st.session_state[f"{prefix}_light_watts"]),
            "hoursPerDay": float(st.session_state[f"{prefix}_light_hours"]),
        },
        "washingMachine": {"hasAppliance": wash_has, "cyclesPerWeek": float(st.session_state[f"{prefix}_wash_cycles"]), "waterPerCycle_L": float(st.session_state[f"{prefix}_wash_L"])},
        "dishwasher": {"hasAppliance": dish_has, "cyclesPerWeek": float(st.session_state[f"{prefix}_dish_cycles"]), "waterPerCycle_L": float(st.session_state[f"{prefix}_dish_L"])},
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


def validate_scenario(s: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    if s["closestCity"] is None:
        missing.append("Closest city")
    if s["HDD_base18"] is None:
        missing.append("HDD (derived from city/zone or custom)")

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
# UX STATUS HELPERS
# =============================================================================
def status_pill(text: str, ok: bool) -> str:
    cls = "pill-ok" if ok else "pill-warn"
    label = f"✓ {text}" if ok else f"• {text}"
    return f'<span class="status-pill {cls}">{label}</span>'


def section_completion(prefix: str) -> dict[str, Any]:
    """
    Returns completion for three sections + overall:
      - core_climate_lighting
      - envelope_systems_water
      - optional_assumptions
    Completion is based on whether required fields have been selected.
    """
    # required picks for main modelling (space heating + water + lighting + capex):
    core_required = [
        f"{prefix}_closestCity",
        f"{prefix}_floorArea",
        f"{prefix}_ceilingHeight",
        f"{prefix}_householdSize",
        f"{prefix}_windowArea",
        f"{prefix}_light_n",
        f"{prefix}_light_watts",
        f"{prefix}_light_hours",
    ]

    picks_required = [
        f"{prefix}_roofRLabel",
        f"{prefix}_wallRLabel",
        f"{prefix}_floorRLabel",
        f"{prefix}_windowULabel",
        f"{prefix}_spaceHeatingSystem",
        f"{prefix}_waterHeatingSystem",
        f"{prefix}_toiletType",
        f"{prefix}_showerType",
        f"{prefix}_tapType",
        f"{prefix}_wash_has",
        f"{prefix}_dish_has",
    ]

    def _is_filled(key: str) -> bool:
        v = st.session_state.get(key, None)
        if v is None:
            return False
        if isinstance(v, str) and v.strip() == "":
            return False
        if v == PLACEHOLDER:
            return False
        return True

    core_ok = all(_is_filled(k) for k in core_required) and (st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER) != PLACEHOLDER)
    pick_ok = all(_is_filled(k) for k in picks_required)

    # optional is “nice to fill”, but not required
    optional_keys = [
        f"{prefix}_coef_elec_tariff",
        f"{prefix}_coef_water_tariff",
        f"{prefix}_coef_grid_ef",
        f"{prefix}_coef_water_ef",
        f"{prefix}_hotWater_setpoint_C",
        f"{prefix}_coldWater_inlet_C",
    ]
    optional_ok = all(_is_filled(k) for k in optional_keys)

    overall_ok = core_ok and pick_ok
    return {"core": core_ok, "picks": pick_ok, "optional": optional_ok, "overall": overall_ok}


def expander_label(title: str, ok: bool, required: bool = True) -> str:
    if required:
        return f"{title}  ({'✓ complete' if ok else '• incomplete'})"
    return f"{title}  ({'✓ set' if ok else '• optional'})"


def user_stage_text() -> str:
    if not st.session_state.get("base_ready", False):
        return "Stage: Fill the Base scenario → then calculate."
    if st.session_state.get("base_ready", False) and not st.session_state.get("compare_ready", False):
        return "Stage: Base is calculated → adjust the Improve scenario → then compare."
    return "Stage: Comparing results → you can now play around; results update as you edit."


# =============================================================================
# UI captions (performance + capex)
# =============================================================================
def show_city_caption(prefix: str) -> None:
    city = st.session_state.get(f"{prefix}_closestCity", PLACEHOLDER)
    if city == PLACEHOLDER:
        return
    z = LOOKUP["climate"]["zone_by_city"].get(city)
    if z:
        hdd = LOOKUP["climate"]["hdd_by_zone_base18"][z]
        st.caption(f"Climate zone: **{z}** · Default HDD (base 18°C): **{hdd:g}**")


def show_envelope_caption(element: str, label: str) -> None:
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


def show_system_caption(sys_block: str, label: str) -> None:
    if label in (PLACEHOLDER, None, "Custom"):
        return
    cop = LOOKUP["systems"][sys_block]["cop"][label]
    cost = LOOKUP["systems"][sys_block]["install_cost_nzd"][label]
    st.caption(f"Performance: **COP={cop:g}** · Install capex: **{fmt_money(cost)}**")


def show_fixture_caption(kind: str, label: str) -> None:
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
# INPUT PANELS (with completion signals in expander names)
# =============================================================================
def scenario_panel(prefix: str, title: str) -> None:
    st.subheader(title)

    comp = section_completion(prefix)

    # top local status pills
    st.markdown(
        f"""
        {status_pill("Core climate + lighting", comp["core"])}
        {status_pill("Envelope + systems + water", comp["picks"])}
        {status_pill("Optional assumptions", comp["optional"])}
        """,
        unsafe_allow_html=True,
    )
    st.caption("Tip: You only need the first two sections to calculate. The optional section improves realism and transparency.")

    if st.button(f"Use Code Minimum ({title})", key=f"{prefix}_btn_code_min", use_container_width=True):
        apply_code_minimum(prefix)
        st.rerun()

    # 1) Core + Climate + Lighting
    with st.expander(expander_label("Core climate + lighting", comp["core"], required=True), expanded=True):
        c1, c2 = st.columns(2, gap="large")

        with c1:
            st.markdown('<div class="sec-h">Building + climate</div>', unsafe_allow_html=True)

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

        with c2:
            st.markdown('<div class="sec-h">Lighting</div>', unsafe_allow_html=True)
            st.number_input("Number of lights", min_value=0, max_value=200, step=1, key=f"{prefix}_light_n")
            st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key=f"{prefix}_light_watts")
            st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key=f"{prefix}_light_hours")
            st.caption("Lighting model: count × watts × hours/day × 365 ÷ 1000")

    # 2) Envelope + Systems + Water
    with st.expander(expander_label("Envelope + systems + water", comp["picks"], required=True), expanded=False):
        ec1, ec2 = st.columns(2, gap="large")

        ENVELOPE_FIELDS = [
            dict(element="roof", label="Roof insulation", opts=ROOF_OPTS, label_key="roofRLabel", val_key="roofR_custom", cost_key="roofCost_custom", help_key="r_value",
                 perf_label="Roof R-value (m²K/W)", cost_label="Roof capex (NZD/m² roof)", perf_min=0.1, perf_max=20.0, perf_step=0.1, cost_min=0.0, cost_max=2000.0, cost_step=10.0),
            dict(element="wall", label="Wall insulation", opts=WALL_OPTS, label_key="wallRLabel", val_key="wallR_custom", cost_key="wallCost_custom", help_key="r_value",
                 perf_label="Wall R-value (m²K/W)", cost_label="Wall capex (NZD/m² wall)", perf_min=0.1, perf_max=20.0, perf_step=0.1, cost_min=0.0, cost_max=2000.0, cost_step=10.0),
            dict(element="floor", label="Floor insulation", opts=FLOOR_OPTS, label_key="floorRLabel", val_key="floorR_custom", cost_key="floorCost_custom", help_key="r_value",
                 perf_label="Floor R-value (m²K/W)", cost_label="Floor capex (NZD/m² floor)", perf_min=0.1, perf_max=20.0, perf_step=0.1, cost_min=0.0, cost_max=2000.0, cost_step=10.0),
            dict(element="window", label="Window type", opts=WIN_OPTS, label_key="windowULabel", val_key="windowU_custom", cost_key="windowCost_custom", help_key="u_value",
                 perf_label="Window U-value (W/m²K)", cost_label="Windows capex (NZD/m² window)", perf_min=0.1, perf_max=10.0, perf_step=0.1, cost_min=0.0, cost_max=5000.0, cost_step=25.0),
        ]

        SYSTEM_FIELDS = [
            dict(sys_block="space_heating", label="Space heating system", opts=SPACE_SYS_OPTS, label_key="spaceHeatingSystem", cop_key="spaceCOP_custom", cost_key="spaceInstall_custom",
                 cop_label="Space heating COP", cost_label="Space heating install capex (NZD)"),
            dict(sys_block="water_heating", label="Water heating system", opts=WATER_SYS_OPTS, label_key="waterHeatingSystem", cop_key="waterCOP_custom", cost_key="waterInstall_custom",
                 cop_label="Water heating COP", cost_label="Water heating install capex (NZD)"),
        ]

        FIXTURE_FIELDS = [
            dict(kind="toilet", label="Toilet type", opts=TOILET_OPTS, label_key="toiletType", val_key="toilet_value_custom", cost_key="toilet_cost_custom",
                 val_label="Toilet litres/flush", cost_label="Toilet install capex (NZD)", val_min=1.0, val_max=20.0, val_step=0.5),
            dict(kind="shower", label="Shower type", opts=SHOWER_OPTS, label_key="showerType", val_key="shower_value_custom", cost_key="shower_cost_custom",
                 val_label="Shower flow (L/min)", cost_label="Shower install capex (NZD)", val_min=1.0, val_max=30.0, val_step=0.5),
            dict(kind="tap", label="Tap type", opts=TAP_OPTS, label_key="tapType", val_key="tap_value_custom", cost_key="tap_cost_custom",
                 val_label="Tap flow (L/min)", cost_label="Tap install capex (NZD)", val_min=1.0, val_max=30.0, val_step=0.5),
        ]

        with ec1:
            st.markdown('<div class="sec-h">Thermal envelope</div>', unsafe_allow_html=True)
            for f in ENVELOPE_FIELDS:
                select_with_placeholder(f["label"], f["opts"], key=f"{prefix}_{f['label_key']}", help_text=HELP[f["help_key"]])
                show_envelope_caption(f["element"], st.session_state[f"{prefix}_{f['label_key']}"])
                if st.session_state[f"{prefix}_{f['label_key']}"] == "Custom":
                    st.number_input(f["perf_label"], min_value=f["perf_min"], max_value=f["perf_max"], step=f["perf_step"], key=f"{prefix}_{f['val_key']}", help=HELP[f["help_key"]])
                    st.number_input(f["cost_label"], min_value=f["cost_min"], max_value=f["cost_max"], step=f["cost_step"], key=f"{prefix}_{f['cost_key']}")

        with ec2:
            st.markdown('<div class="sec-h">Systems</div>', unsafe_allow_html=True)
            for f in SYSTEM_FIELDS:
                select_with_placeholder(f["label"], f["opts"], key=f"{prefix}_{f['label_key']}", help_text=HELP["cop"])
                show_system_caption(f["sys_block"], st.session_state[f"{prefix}_{f['label_key']}"])
                if st.session_state[f"{prefix}_{f['label_key']}"] == "Custom":
                    st.number_input(f["cop_label"], min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_{f['cop_key']}", help=HELP["cop"])
                    st.number_input(f["cost_label"], min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_{f['cost_key']}")

            st.markdown('<div class="sec-h" style="margin-top:12px;">Water fixtures + appliances</div>', unsafe_allow_html=True)
            for f in FIXTURE_FIELDS:
                select_with_placeholder(f["label"], f["opts"], key=f"{prefix}_{f['label_key']}", help_text=HELP["fixture"])
                show_fixture_caption(f["kind"], st.session_state[f"{prefix}_{f['label_key']}"])
                if st.session_state[f"{prefix}_{f['label_key']}"] == "Custom":
                    st.number_input(f["val_label"], min_value=f["val_min"], max_value=f["val_max"], step=f["val_step"], key=f"{prefix}_{f['val_key']}", help=HELP["fixture"])
                    st.number_input(f["cost_label"], min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_{f['cost_key']}")

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
    with st.expander(expander_label("Optional: usage + fractions + tariffs + emissions", comp["optional"], required=False), expanded=False):
        oc1, oc2 = st.columns(2, gap="large")

        with oc1:
            st.markdown('<div class="sec-h">Usage assumptions</div>', unsafe_allow_html=True)
            st.caption("These assumptions affect water volumes and water-heating energy. Adjust if your household behaviour differs from the defaults.")
            st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
            st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")
            st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
            st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
            st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
            st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

        with oc2:
            st.markdown('<div class="sec-h">Hot water fractions</div>', unsafe_allow_html=True)
            st.caption(HELP["hw_frac"])
            st.slider("Shower hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_shower")
            st.slider("Tap hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_tap")
            st.slider("Laundry hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_laundry")
            st.slider("Dishwasher hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_dishwasher")

            st.divider()
            st.markdown('<div class="sec-h">Tariffs + emission factors</div>', unsafe_allow_html=True)
            st.caption("Set these to match your location/provider (tariffs) and your reporting boundary (emission factors).")
            st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff", help=HELP["tariffs"])
            st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff", help=HELP["tariffs"])
            st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef", help=HELP["efs"])
            st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef", help=HELP["efs"])


# =============================================================================
# CARDS + DIFF SUMMARY
# =============================================================================
def render_metric_card(title: str, unit: str, base_val: str, improve_val: str, delta_val: str, delta_dir: str) -> None:
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">{title}</div>
          <div class="kpi-sub">{unit}</div>
          <div class="kpi-row"><div class="kpi-label">Base scenario</div><div class="kpi-val">{base_val}</div></div>
          <div class="kpi-row"><div class="kpi-label">Improve scenario</div><div class="kpi-val">{improve_val}</div></div>
          <div class="kpi-row"><div class="kpi-label">Δ (Improve − Base)</div><div class="kpi-val">{delta_dir} {delta_val}</div></div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_payback_card(pb_years: str, note: str | None = None) -> None:
    note_html = f'<div class="kpi-note">{note}</div>' if note else ""
    st.markdown(
        f"""
        <div class="kpi-card">
          <div class="kpi-title">Simple payback</div>
          <div class="kpi-sub">years</div>
          <div class="kpi-row"><div class="kpi-label">Payback</div><div class="kpi-val">{pb_years}</div></div>
          {note_html}
        </div>
        """,
        unsafe_allow_html=True,
    )


def metric_vals(base_val: float | None, improve_val: float | None, dec: int) -> tuple[str, str, str, str]:
    b_s = fmt_num(base_val, dec) if base_val is not None else "—"
    i_s = fmt_num(improve_val, dec) if improve_val is not None else "—"
    if (base_val is None) or (improve_val is None):
        return b_s, i_s, "—", "—"
    d = improve_val - base_val
    return b_s, i_s, fmt_num(d, dec), direction_arrow(d)


def scenario_changes_table(base_s: dict[str, Any], improve_s: dict[str, Any]) -> pd.DataFrame:
    def _cap(label: str) -> str:
        if label == PLACEHOLDER:
            return "—"
        return str(label)

    rows = []
    # high-salience choices
    rows.append(["Closest city", _cap(base_s["closestCity"] or "—"), _cap(improve_s["closestCity"] or "—")])
    rows.append(["Roof insulation", _cap(st.session_state.get("b_roofRLabel", "—")), _cap(st.session_state.get("i_roofRLabel", "—"))])
    rows.append(["Wall insulation", _cap(st.session_state.get("b_wallRLabel", "—")), _cap(st.session_state.get("i_wallRLabel", "—"))])
    rows.append(["Floor insulation", _cap(st.session_state.get("b_floorRLabel", "—")), _cap(st.session_state.get("i_floorRLabel", "—"))])
    rows.append(["Windows", _cap(st.session_state.get("b_windowULabel", "—")), _cap(st.session_state.get("i_windowULabel", "—"))])
    rows.append(["Space heating system", _cap(st.session_state.get("b_spaceHeatingSystem", "—")), _cap(st.session_state.get("i_spaceHeatingSystem", "—"))])
    rows.append(["Water heating system", _cap(st.session_state.get("b_waterHeatingSystem", "—")), _cap(st.session_state.get("i_waterHeatingSystem", "—"))])
    rows.append(["Toilet", _cap(st.session_state.get("b_toiletType", "—")), _cap(st.session_state.get("i_toiletType", "—"))])
    rows.append(["Shower", _cap(st.session_state.get("b_showerType", "—")), _cap(st.session_state.get("i_showerType", "—"))])
    rows.append(["Tap", _cap(st.session_state.get("b_tapType", "—")), _cap(st.session_state.get("i_tapType", "—"))])
    rows.append(["Washing machine", _cap(st.session_state.get("b_wash_has", "—")), _cap(st.session_state.get("i_wash_has", "—"))])
    rows.append(["Dishwasher", _cap(st.session_state.get("b_dish_has", "—")), _cap(st.session_state.get("i_dish_has", "—"))])

    df = pd.DataFrame(rows, columns=["What changed", "Base scenario", "Improve scenario"])
    # keep only true differences (except city, always show)
    mask = (df["Base scenario"] != df["Improve scenario"]) | (df["What changed"] == "Closest city")
    return df[mask].reset_index(drop=True)


# =============================================================================
# CHARTS
# =============================================================================
def plot_breakdown_stacked(title: str, y_title: str, categories: list[str], b_vals: list[float], i_vals: list[float] | None) -> None:
    x = ["Base scenario"] + (["Improve scenario"] if i_vals is not None else [])
    fig = go.Figure()
    for idx, cat in enumerate(categories):
        y = [b_vals[idx]] + ([i_vals[idx]] if i_vals is not None else [])
        fig.add_trace(go.Bar(name=cat, x=x, y=y))
    fig.update_layout(title=title, barmode="stack", height=360, margin=dict(l=20, r=20, t=60, b=50), yaxis_title=y_title, legend_title_text="")
    st.plotly_chart(fig, use_container_width=True)


CHART_SPECS = [
    dict(
        title="Electricity composition (Base vs Improve)",
        y="kWh/year",
        cats=["Space heating", "Water heating", "Lighting"],
        get=lambda r: [r["spaceHeating"]["Q_purchased_kwh_y"], r["waterHeating"]["Q_purchased_kwh_y"], r["lighting"]["Q_total_kwh_y"]],
    ),
    dict(title="Water composition (Base vs Improve)", y="m³/year", cats=None, get=lambda r: r["waterConsumption"]["breakdown_m3_y"]),
    dict(title="Operational carbon composition (Base vs Improve)", y="kgCO₂e/year", cats=["Electricity emissions", "Water emissions"], get=lambda r: [r["carbon"]["CO2_electricity_kg_y"], r["carbon"]["CO2_water_kg_y"]]),
    dict(title="Opex composition (Base vs Improve)", y="NZD/year", cats=["Electricity cost", "Water cost"], get=lambda r: [r["opex"]["opex_electricity_nzd_y"], r["opex"]["opex_water_nzd_y"]]),
    dict(title="Capex composition (Base vs Improve)", y="NZD", cats=["Envelope", "Systems", "Fixtures"], get=lambda r: [r["capex"]["breakdown_nzd"]["Envelope"], r["capex"]["breakdown_nzd"]["Systems"], r["capex"]["breakdown_nzd"]["Fixtures"]]),
]


def plot_from_spec(spec: dict[str, Any], b_res: dict[str, Any], i_res: dict[str, Any] | None) -> None:
    b_get = spec["get"](b_res)
    if isinstance(b_get, dict):
        cats = list(b_get.keys())
        b_vals = [float(b_get[c]) for c in cats]
        i_vals = None
        if i_res is not None:
            i_get = spec["get"](i_res)
            i_vals = [float(i_get.get(c, 0.0)) for c in cats]
        plot_breakdown_stacked(spec["title"], spec["y"], cats, b_vals, i_vals)
        return

    cats = spec["cats"]
    b_vals = [float(x) for x in b_get]
    i_vals = None
    if i_res is not None:
        i_vals = [float(x) for x in spec["get"](i_res)]
    plot_breakdown_stacked(spec["title"], spec["y"], cats, b_vals, i_vals)


# =============================================================================
# APP START
# =============================================================================
init_defaults()

# Auto-seed Improve scenario once Base is ready and improve is unlocked
if st.session_state.get("base_ready", False) and st.session_state.get("improve_unlocked", False) and not st.session_state.get("improve_seeded", False):
    seed_improve_from_base_once()

# Options lists
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

# Human-friendly tool explanation (top)
with st.expander("How this tool works (quick guide)", expanded=True):
    st.markdown(
        """
**What this tool does**  
This prototype estimates operational performance and simple economics for a NZ home under two scenarios:
- **Base scenario**: your “as-is” or starting point.
- **Improve scenario**: a proposed upgrade package (insulation, glazing, systems, fixtures), copied from Base as a starting point.

**What gets calculated (high level)**  
- **Space heating energy**: a simplified *heat loss coefficient* style approach (HLC / H_total) × climate severity (**HDD**) to estimate annual heating demand, then divided by heating system efficiency (**COP**).  
- **Water consumption**: indoor end-use volumes (toilet, shower, taps, optional appliances).  
- **Water heating energy**: hot water volume × temperature lift (ΔT) × heat capacity, then divided by water-heating COP.  
- **Lighting**: fixture count × wattage × hours/day.  
- **Operational carbon**: electricity + water multiplied by emission factors.  
- **Costs**:
  - **Opex**: electricity tariff + water tariff.
  - **Capex**: transparent “unit cost × quantity” accounting for envelope, systems, and fixtures.

**Where to find details**  
- **Calculator tab**: fill forms, calculate, compare, and explore charts.  
- **Formulas tab**: the exact equations and boundaries.  
- **Data sources tab**: a provenance table for defaults and references.

**How to use (step-by-step)**  
1) Fill **Base scenario** (at minimum: the first two sections).  
2) Click **Calculate Base scenario**.  
3) The tool unlocks **Improve scenario** and copies Base inputs.  
4) Change only what you want to upgrade, then click **Compare scenarios**.  
5) After comparison is activated, results update automatically as you adjust inputs.
        """
    )

st.markdown(f"<div class='muted'>{user_stage_text()}</div>", unsafe_allow_html=True)

tab_calc, tab_formulas, tab_sources = st.tabs(["Calculator", "Formulas", "Data sources"])

# =============================================================================
# TAB 1: CALCULATOR
# =============================================================================
KPI_SPECS = [
    dict(title="Total energy use", unit="kWh/year", dec=1, get=lambda r: r["totalElectricity_kwh_y"]),
    dict(title="Total water use", unit="m³/year", dec=2, get=lambda r: r["waterConsumption"]["V_total_m3_y"]),
    dict(title="Operational carbon", unit="kgCO₂e/year", dec=1, get=lambda r: r["carbon"]["CO2_total_kg_y"]),
    dict(title="Operational expenditure", unit="NZD/year", dec=0, get=lambda r: r["opex"]["opex_total_nzd_y"]),
    dict(title="Capital expenditure", unit="NZD", dec=0, get=lambda r: r["capex"]["capex_total_nzd"]),
]

with tab_calc:
    left, right = st.columns([1, 1], gap="large")

    INPUT_H = 640
    RESULTS_H = 720

    with left:
        try:
            input_box = st.container(height=INPUT_H, border=True)
        except TypeError:
            input_box = st.container()

        with input_box:
            scenario_panel("b", "Base scenario")

            if st.session_state.get("improve_unlocked", False):
                st.divider()
                scenario_panel("i", "Improve scenario")

        # Sticky action bar
        st.markdown('<div class="fixed-bar">', unsafe_allow_html=True)

        base_now = get_scenario("b")
        base_missing = validate_scenario(base_now)

        # action copy: clearer guidance
        if not st.session_state["base_ready"]:
            if base_missing:
                st.markdown("<span class='muted'>To calculate Base scenario, complete the required sections (Core climate + lighting, and Envelope + systems + water).</span>", unsafe_allow_html=True)
                with st.expander("See what is missing in Base scenario", expanded=False):
                    st.write(base_missing)

            disabled = bool(base_missing)
            if st.button("Calculate Base scenario", use_container_width=True, disabled=disabled, key="btn_calc_base"):
                st.session_state["base_ready"] = True
                st.session_state["improve_unlocked"] = True
                if not st.session_state.get("improve_seeded", False):
                    seed_improve_from_base_once()
                st.rerun()
        else:
            st.success("Base scenario is calculated. Improve scenario is now unlocked (copied from Base).")

        # Compare
        if st.session_state.get("improve_unlocked", False):
            improve_now = get_scenario("i")
            improve_missing = validate_scenario(improve_now)

            if not st.session_state.get("compare_ready", False):
                if improve_missing:
                    st.markdown("<span class='muted'>To compare, complete the Improve scenario form (same required sections as Base).</span>", unsafe_allow_html=True)
                    with st.expander("See what is missing in Improve scenario", expanded=False):
                        st.write(improve_missing)

                disabled = bool(improve_missing)
                if st.button("Compare scenarios", use_container_width=True, disabled=disabled, key="btn_calc_compare"):
                    st.session_state["compare_ready"] = True
                    st.rerun()
            else:
                st.success("Comparison is active. As you edit inputs, results update automatically.")

        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        try:
            results_box = st.container(height=RESULTS_H, border=True)
        except TypeError:
            results_box = st.container()

        with results_box:
            st.subheader("Results")

            b_res: dict[str, Any] | None = None
            i_res: dict[str, Any] | None = None

            if not st.session_state.get("base_ready", False):
                st.caption("Fill the Base scenario form on the left and click **Calculate Base scenario**.")
            else:
                if base_missing:
                    st.caption("Base scenario is incomplete.")
                else:
                    b_res = calculate_scenario(base_now, get_coeffs("b"))

            if st.session_state.get("compare_ready", False):
                improve_now = get_scenario("i")
                improve_missing = validate_scenario(improve_now)
                if improve_missing:
                    st.caption("Complete the Improve scenario form to compare two results.")
                else:
                    i_res = calculate_scenario(improve_now, get_coeffs("i"))

            # What changed (human-readable)
            if b_res is not None and st.session_state.get("improve_unlocked", False):
                st.markdown("### What is different between scenarios?")
                if i_res is None:
                    st.caption("Improve scenario is unlocked and copied from Base. Change the items you want to upgrade, then compare.")
                else:
                    df_changes = scenario_changes_table(base_now, improve_now)
                    if len(df_changes) == 0:
                        st.caption("No input differences detected. Change a selection in Improve scenario to see impact.")
                    else:
                        st.dataframe(df_changes, use_container_width=True, hide_index=True)

            # KPI cards + charts
            if b_res is not None:
                kpi_render_data = []
                for spec in KPI_SPECS:
                    b_val = float(spec["get"](b_res))
                    i_val = float(spec["get"](i_res)) if i_res is not None else None
                    b_s, i_s, d_s, d_dir = metric_vals(b_val, i_val, spec["dec"])
                    kpi_render_data.append((spec, b_s, i_s, d_s, d_dir))

                # Payback
                pb_years = "—"
                pb_note = None
                if i_res is not None:
                    base_capex = float(KPI_SPECS[4]["get"](b_res))
                    imp_capex = float(KPI_SPECS[4]["get"](i_res))
                    base_opex = float(KPI_SPECS[3]["get"](b_res))
                    imp_opex = float(KPI_SPECS[3]["get"](i_res))

                    inc_capex = imp_capex - base_capex
                    savings = base_opex - imp_opex

                    if inc_capex <= 0:
                        pb_years = "0.0"
                        pb_note = "No additional capex (Improve ≤ Base capex)."
                    elif savings <= 0:
                        pb_years = "—"
                        pb_note = "No payback (annual opex savings ≤ 0)."
                    else:
                        pb_years = fmt_num(inc_capex / savings, 1)
                        pb_note = "Payback = (Capex increase) ÷ (Annual opex savings)."

                st.divider()
                st.markdown("### KPI comparison (headline)")

                # 2 columns layout
                rows = [(kpi_render_data[0], kpi_render_data[1]), (kpi_render_data[2], kpi_render_data[3]), (kpi_render_data[4], None)]
                for left_kpi, right_kpi in rows:
                    c1, c2 = st.columns(2, gap="small")
                    with c1:
                        spec, b_s, i_s, d_s, d_dir = left_kpi
                        render_metric_card(spec["title"], spec["unit"], b_s, i_s, d_s, d_dir)
                    with c2:
                        if right_kpi is not None:
                            spec, b_s, i_s, d_s, d_dir = right_kpi
                            render_metric_card(spec["title"], spec["unit"], b_s, i_s, d_s, d_dir)
                        else:
                            render_payback_card(pb_years, pb_note)

                st.divider()
                st.markdown("### Charts (composition, not just totals)")

                ch1, ch2 = st.columns(2, gap="small")
                with ch1:
                    plot_from_spec(CHART_SPECS[0], b_res, i_res)
                with ch2:
                    plot_from_spec(CHART_SPECS[1], b_res, i_res)

                ch3, ch4 = st.columns(2, gap="small")
                with ch3:
                    plot_from_spec(CHART_SPECS[2], b_res, i_res)
                with ch4:
                    plot_from_spec(CHART_SPECS[3], b_res, i_res)

                plot_from_spec(CHART_SPECS[4], b_res, i_res)

                if i_res is not None:
                    payload = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "base_scenario": {"coefficients": get_coeffs("b"), "inputs": base_now, "results": b_res},
                        "improve_scenario": {"coefficients": get_coeffs("i"), "inputs": improve_now, "results": i_res},
                        "notes": {
                            "scope": "Early-stage decision support; not certification; not a dynamic simulation.",
                            "energy_boundary": "Space heating + water heating + lighting (excludes plug loads/appliances electricity).",
                            "water_boundary": "Indoor water includes toilets, showers, taps, plus optional dishwasher/washing machine water.",
                            "capex_boundary": "Transparent unit-cost accounting; not investment-grade pricing.",
                            "hot_water_model": "Hot water derived from end-use volumes using hot water fractions (toilets excluded).",
                        },
                    }
                    st.download_button(
                        "Download results (JSON)",
                        data=json.dumps(payload, indent=2),
                        file_name=f"housing-sustainability-compare-{int(datetime.utcnow().timestamp())}.json",
                        mime="application/json",
                        use_container_width=True,
                    )

# =============================================================================
# TAB 2: FORMULAS
# =============================================================================
with tab_formulas:
    st.header("Formulas")
    st.markdown(
        """
This tab documents the equations used in the Calculator. The intent is transparency: you can audit the logic and assumptions.

### Space heating electricity (early-stage HLC approach)

**Heat loss coefficient**
- \(H_{total} = H_{roof} + H_{wall} + H_{floor} + H_{window}\)
- \(H_x = Area_x \times U_x\)
- \(U = 1/R\) (for insulated elements)

**Annual delivered heating energy**
- \(Q_{delivered} = (H_{total} \times HDD \times 24) / 1000\)

**Purchased electricity**
- \(Q_{purchased} = Q_{delivered} / COP\)

This is a simplified steady-state method suitable for early-stage comparison and aligns with common NZ practice for early modelling (HLC-style), rather than a full dynamic simulation.

### Water consumption

Sum of indoor end uses:
- Toilets (flushes × litres/flush)
- Showers (showers × minutes × litres/min)
- Taps (minutes × litres/min)
- Optional appliances (cycles × litres/cycle)

### Water heating electricity

Hot water volume is estimated using **hot water fractions** applied to end-use volumes (toilets excluded).
- \(Q_{delivered} = (V_{hot} \times C_p \times \Delta T) / 3600\)
- \(Q_{purchased} = Q_{delivered} / COP\)

### Lighting electricity

- \(Q = (N_{lights} \times W_{per\ light} \times hours/day \times 365) / 1000\)

### Carbon + cost

- Electricity emissions = electricity × grid EF  
- Water emissions = water × water EF  
- Opex = (electricity × tariff) + (water × tariff)  
- Simple payback = (capex increase) ÷ (annual opex savings)
        """
    )

# =============================================================================
# TAB 3: DATA SOURCES
# =============================================================================
with tab_sources:
    st.header("Data sources")
    st.markdown(
        """
This tab provides a provenance view: which values are calculated vs. default vs. user input, and what the reference basis is for defaults.
If you want to make this “audit-grade”, treat every default as editable and record your project-specific sources.
        """
    )

    rows = [
        [1, "Energy", "Space heating electricity", "Calculated", "(H_total × HDD × 24 / 1000) ÷ COP", "Early-stage HLC-style method; aligns with NZ early modelling practice"],
        [2, "Energy", "HDD (base 18°C)", "Lookup/User", "City → zone → HDD band; or custom", "Climate severity bands used for early-stage estimates"],
        [3, "Envelope", "R-values (roof/wall/floor)", "Default/User", "Banded options + custom", "NZBC H1 / MBIE-style bands; BRANZ typical values"],
        [4, "Envelope", "Window U-values", "Default/User", "Glazing options + custom", "BRANZ typical glazing performance ranges"],
        [5, "Systems", "COP (space/water heating)", "Default/User", "System options + custom", "Typical NZ system performance ranges"],
        [6, "Water", "Fixtures (L/flush, L/min)", "Default/User", "Fixture options + custom", "BRANZ typical indoor water rates"],
        [7, "Lighting", "Lighting model inputs", "User", "Count, watts, hours/day", "User-defined; defaults are placeholders"],
        [8, "Carbon", "Grid + water emission factors", "Default/User", "Electricity × EF; Water × EF", "MfE-style emission factor guidance (editable)"],
        [9, "Cost", "Tariffs", "Default/User", "Electricity × tariff; Water × tariff", "Public benchmarks (editable to bill)"],
        [10, "Cost", "Capex (unit cost accounting)", "Default/User", "Unit cost × quantity", "Market benchmark placeholders; replace with quotes if needed"],
    ]
    df = pd.DataFrame(rows, columns=["Order", "Module", "Item", "Type", "How it is used", "Reference basis / notes"])
    st.dataframe(df, use_container_width=True, hide_index=True)
