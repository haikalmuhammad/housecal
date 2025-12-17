# app.py
# BSNS580 — Early-stage NZ Housing Sustainability Calculator (Prototype)
# Faithful implementation of the provided master specification (V1).
#
# Run:
#   streamlit run app.py

import math
from dataclasses import dataclass
from typing import Dict, Any, Tuple, Optional

import pandas as pd
import streamlit as st

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(page_title="NZ Housing Sustainability Prototype", layout="wide")

# =========================================================
# BACKEND DEFAULTS (V1) — EDIT THESE LATER IF NEEDED
# =========================================================

# --- Space heating defaults ---
DEFAULTS_SPACE = {
    "ceiling_height_m": 2.4,
    "R_roof_m2K_W": 3.6,
    "R_wall_m2K_W": 2.0,
    "R_floor_m2K_W": 1.8,
    "U_window_W_m2K": 2.8,
    "heat_pump_COP": 3.0,
    "hdd_manual": 1800.0,
}

# HDD lookup (base 18°C) — placeholder values for V1 (editable by you later)
HDD_LOOKUP_BASE18 = {
    "Zone 1 (very warm)": 900.0,
    "Zone 2 (warm)": 1200.0,
    "Zone 3 (mild)": 1600.0,
    "Zone 4 (cool)": 2100.0,
    "Zone 5 (cold)": 2700.0,
    "Zone 6 (very cold)": 3300.0,
}

# --- Water heating defaults (Backend defaults, V1) ---
DEFAULTS_WATER_HEATING = {
    "L_per_person_day": 50.0,
    "T_hot_C": 55.0,
    "T_cold_C": 15.0,
    "COP_heat_pump_hw": 2.5,
}

# Physical constants
CP_WATER_KJ_PER_KG_C = 4.186
KJ_PER_KWH = 3600.0  # 1 kWh = 3600 kJ
L_TO_KG = 1.0        # 1 L water ≈ 1 kg

# --- Lighting & appliances defaults ---
DEFAULTS_OTHER = {
    "lighting_hours_per_day": 3.0,
    "lamp_watt_by_type": {
        "LED": 8.0,
        "Mixed": 12.0,
        "Halogen / incandescent": 40.0,
    },
    "wash_kwh_per_cycle": 0.7,
    "dish_kwh_per_cycle": 0.9,
    "cook_kwh_per_meal": 0.5,
    "cook_power_kW": 2.0,
}

# --- Water consumption defaults ---
DEFAULTS_WATER = {
    "flushes_per_person_day": 5.0,
    "L_per_flush": {
        "Standard": 9.0,
        "Dual flush": 4.5,  # average
    },
    "showers_per_person_day": 1.0,
    "minutes_per_shower": 8.0,
    "shower_flow_L_min": {
        "Standard": 9.0,
        "Low-flow": 6.0,
    },
    "taps_L_per_person_day": {
        "Standard": 40.0,
        "Efficient": 25.0,
    },
    "wash_L_per_cycle": 70.0,
    "dish_L_per_cycle": 15.0,
}

# --- Operational carbon + tariffs defaults (global) ---
DEFAULTS_CARBON = {
    "grid_kgCO2e_per_kWh": 0.10,
    "water_kgCO2e_per_m3": 0.30,
}
DEFAULTS_TARIFFS = {
    "electricity_NZD_per_kWh": 0.30,
    "water_NZD_per_m3": 2.50,
}

# --- Upgrade cost coefficients (global, incremental vs baseline) ---
DEFAULTS_UPGRADE_COSTS = {
    # Insulation (area-based)
    "d_roof_NZD_per_m2": 20.0,
    "d_wall_NZD_per_m2": 30.0,
    "d_floor_NZD_per_m2": 25.0,
    # Windows (area-based)
    "d_window_NZD_per_m2": 300.0,
    # Systems (one-off)
    "d_heatpump_vs_electric_NZD": 3500.0,
    "d_hw_heatpump_vs_electric_NZD": 2500.0,
    # Water fixtures (per unit)
    "d_dual_flush_toilet_NZD_each": 300.0,
    "d_lowflow_shower_NZD_each": 150.0,
    "d_tap_aerator_NZD_each": 20.0,
}

# =========================================================
# HELPERS — WINDOW TABLE, FORMATTING, ARROWS
# =========================================================

def default_windows_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "width_m": [1.2, 0.9],
            "height_m": [1.2, 0.6],
            "count": [6, 2],
        }
    )

def safe_float(x, default=0.0) -> float:
    try:
        v = float(x)
        if math.isnan(v) or math.isinf(v):
            return default
        return v
    except Exception:
        return default

def window_area_m2(windows_df: pd.DataFrame) -> float:
    if windows_df is None or len(windows_df) == 0:
        return 0.0
    df = windows_df.copy()
    for c in ["width_m", "height_m", "count"]:
        if c not in df.columns:
            return 0.0
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
    df["area_m2"] = (df["width_m"].clip(lower=0.0) * df["height_m"].clip(lower=0.0) * df["count"].clip(lower=0.0))
    return float(df["area_m2"].sum())

def _fmt(x: float, decimals: int = 0) -> str:
    return f"{x:,.{decimals}f}"

def _arrow(delta: float) -> str:
    if abs(delta) < 1e-12:
        return "→"
    return "↑" if delta > 0 else "↓"

def opt_cell(opt: float, base: float, decimals: int = 0) -> str:
    return f"{_fmt(opt, decimals)} {_arrow(opt - base)}"

# =========================================================
# CORE CALCULATION FUNCTIONS — 1:1 WITH MASTER SPEC
# =========================================================

def r_to_u(R: float) -> float:
    # U = 1 / R
    R = max(R, 1e-9)
    return 1.0 / R

def estimate_areas(floor_area_m2: float, ceiling_height_m: float, A_window_m2: float) -> Dict[str, float]:
    """
    System-calculated areas (simplified):
    - Roof area ≈ floor area
    - Floor area = floor area
    - Wall area derived from floor area + ceiling height using simplified rectangular footprint assumption.
      Here: assume square footprint => side = sqrt(A), perimeter = 4*sqrt(A), wall_gross = perimeter*height
    - Opaque wall area = max(wall_gross - window_area, 0) to avoid double counting.
    """
    A_floor = max(floor_area_m2, 0.0)
    A_roof = A_floor

    side = math.sqrt(max(A_floor, 0.0))
    perimeter = 4.0 * side
    A_wall_gross = perimeter * max(ceiling_height_m, 0.0)

    A_window = max(A_window_m2, 0.0)
    A_wall_opaque = max(A_wall_gross - A_window, 0.0)

    return {
        "A_floor_m2": A_floor,
        "A_roof_m2": A_roof,
        "A_wall_gross_m2": A_wall_gross,
        "A_wall_opaque_m2": A_wall_opaque,
        "A_window_m2": A_window,
    }

def compute_space_heating(inputs: Dict[str, Any]) -> Dict[str, float]:
    """
    Space heating (steady-state heat loss approach)

    1) Convert R-values to U-values: U = 1/R
    2) Compute areas (roof, floor, wall opaque, window)
    3) Heat loss coefficient: H = Σ(Area × U) [W/K]
    4) Annual delivered heating energy:
       Q_delivered (kWh/yr) = H × HDD × 24 / 1000
    5) Purchased energy:
       Q_purchased = Q_delivered / system_efficiency
       - Electric resistance: η = 1.0
       - Heat pump: efficiency = COP
    """
    floor_area_m2 = safe_float(inputs["floor_area_m2"])
    ceiling_height_m = safe_float(inputs["ceiling_height_m"])
    HDD = safe_float(inputs["HDD"])
    R_roof = safe_float(inputs["R_roof"])
    R_wall = safe_float(inputs["R_wall"])
    R_floor = safe_float(inputs["R_floor"])
    U_window = safe_float(inputs["U_window"])
    windows_df = inputs["windows_df"]

    A_window_m2 = window_area_m2(windows_df)
    areas = estimate_areas(floor_area_m2, ceiling_height_m, A_window_m2)

    U_roof = r_to_u(R_roof)
    U_wall = r_to_u(R_wall)
    U_floor = r_to_u(R_floor)

    # H = Σ(Area × U)
    H_roof = areas["A_roof_m2"] * U_roof
    H_wall = areas["A_wall_opaque_m2"] * U_wall
    H_floor = areas["A_floor_m2"] * U_floor
    H_window = areas["A_window_m2"] * max(U_window, 0.0)

    H_total_W_per_K = H_roof + H_wall + H_floor + H_window

    # Q_delivered = H * HDD * 24 / 1000
    Q_delivered_kWh_yr = H_total_W_per_K * max(HDD, 0.0) * 24.0 / 1000.0

    # System efficiency
    heating_system = inputs["heating_system"]
    if heating_system == "Heat pump":
        eff = max(safe_float(inputs["heat_pump_COP"]), 1e-6)
    else:
        eff = 1.0

    Q_purchased_kWh_yr = Q_delivered_kWh_yr / eff

    return {
        "A_window_m2": areas["A_window_m2"],
        "A_wall_opaque_m2": areas["A_wall_opaque_m2"],
        "A_wall_gross_m2": areas["A_wall_gross_m2"],
        "A_roof_m2": areas["A_roof_m2"],
        "A_floor_m2": areas["A_floor_m2"],
        "U_roof": U_roof,
        "U_wall": U_wall,
        "U_floor": U_floor,
        "U_window": max(U_window, 0.0),
        "H_W_per_K": H_total_W_per_K,
        "Q_space_delivered_kWh_yr": Q_delivered_kWh_yr,
        "Q_space_purchased_kWh_yr": Q_purchased_kWh_yr,
        "H_roof": H_roof,
        "H_wall": H_wall,
        "H_floor": H_floor,
        "H_window": H_window,
    }

def compute_water_heating(inputs: Dict[str, Any]) -> Dict[str, float]:
    """
    Water heating

    1) Annual hot water volume:
       V_annual (L/yr) = occupants × L/person/day × 365
    2) Delivered thermal energy:
       Q_delivered (kWh/yr) = (V_annual × ΔT × 4.186) / 3600
       where ΔT = T_hot - T_cold
    3) Purchased energy:
       Q_purchased = Q_delivered / system_efficiency
       - Electric storage: η = 1.0
       - Heat pump hot water: COP ≈ 2.5 (default)
    """
    occupants = int(inputs["occupants"])
    L_ppd = safe_float(inputs["L_hotwater_per_person_day"])
    T_hot = safe_float(inputs["T_hot_C"])
    T_cold = safe_float(inputs["T_cold_C"])
    dT = T_hot - T_cold

    V_annual_L_yr = max(occupants, 0) * max(L_ppd, 0.0) * 365.0

    Q_delivered_kWh_yr = (V_annual_L_yr * max(dT, 0.0) * CP_WATER_KJ_PER_KG_C * L_TO_KG) / KJ_PER_KWH

    system = inputs["hot_water_system"]
    if system == "Heat pump hot water":
        eff = max(safe_float(inputs["COP_hw"]), 1e-6)
    else:
        eff = 1.0

    Q_purchased_kWh_yr = Q_delivered_kWh_yr / eff

    return {
        "V_hotwater_annual_L_yr": V_annual_L_yr,
        "dT_C": dT,
        "Q_hw_delivered_kWh_yr": Q_delivered_kWh_yr,
        "Q_hw_purchased_kWh_yr": Q_purchased_kWh_yr,
        "hw_efficiency": eff,
    }

def compute_lighting_and_appliances(inputs: Dict[str, Any]) -> Dict[str, float]:
    """
    Lighting & appliances (usage × intensity)

    Lighting:
      Q_lighting = (n_lights × watt × hours/day × 365)/1000

    Washing machine:
      Q_wash = cycles/week × kWh/cycle × 52   (if owned)

    Dishwasher:
      Q_dish = cycles/week × kWh/cycle × 52  (if owned)

    Cooking:
      - If meals/week method:
          Q_cook = meals/week × kWh/meal × 52
      - If hours/day method (UI-selected):
          Q_cook = power_kW × hours/day × 365
    """
    # Lighting
    n_lights = int(inputs["n_lights"])
    lighting_type = inputs["lighting_type"]
    hours_per_day = safe_float(inputs["lighting_hours_per_day"])
    lamp_watt = DEFAULTS_OTHER["lamp_watt_by_type"].get(lighting_type, 10.0)
    if inputs["lamp_watt_override"] is not None:
        lamp_watt = max(safe_float(inputs["lamp_watt_override"]), 0.0)

    Q_lighting_kWh_yr = (max(n_lights, 0) * max(lamp_watt, 0.0) * max(hours_per_day, 0.0) * 365.0) / 1000.0

    # Washing machine
    if inputs["has_washer"]:
        cycles_w = safe_float(inputs["wash_cycles_per_week"])
        kwh_cycle = safe_float(inputs["wash_kwh_per_cycle"])
        Q_wash_kWh_yr = max(cycles_w, 0.0) * max(kwh_cycle, 0.0) * 52.0
    else:
        Q_wash_kWh_yr = 0.0

    # Dishwasher
    if inputs["has_dishwasher"]:
        cycles_d = safe_float(inputs["dish_cycles_per_week"])
        kwh_cycle_d = safe_float(inputs["dish_kwh_per_cycle"])
        Q_dish_kWh_yr = max(cycles_d, 0.0) * max(kwh_cycle_d, 0.0) * 52.0
    else:
        Q_dish_kWh_yr = 0.0

    # Cooking
    method = inputs["cooking_method"]
    if method == "Meals/week":
        meals_w = safe_float(inputs["meals_per_week"])
        kwh_meal = safe_float(inputs["cook_kwh_per_meal"])
        Q_cook_kWh_yr = max(meals_w, 0.0) * max(kwh_meal, 0.0) * 52.0
    else:
        power_kW = safe_float(inputs["cook_power_kW"])
        hours_d = safe_float(inputs["cook_hours_per_day"])
        Q_cook_kWh_yr = max(power_kW, 0.0) * max(hours_d, 0.0) * 365.0

    Q_other_kWh_yr = Q_lighting_kWh_yr + Q_wash_kWh_yr + Q_dish_kWh_yr + Q_cook_kWh_yr

    return {
        "Q_lighting_kWh_yr": Q_lighting_kWh_yr,
        "Q_wash_kWh_yr": Q_wash_kWh_yr,
        "Q_dish_kWh_yr": Q_dish_kWh_yr,
        "Q_cook_kWh_yr": Q_cook_kWh_yr,
        "Q_other_kWh_yr": Q_other_kWh_yr,
    }

def compute_water_consumption(inputs: Dict[str, Any]) -> Dict[str, float]:
    """
    Water consumption (L/yr)

    V_toilet     = occupants × flushes/day × L/flush × 365
    V_shower     = occupants × showers/day × minutes × flow_rate × 365
    V_taps       = occupants × L/person/day × 365
    V_laundry    = cycles/week × L/cycle × 52   (if owned)
    V_dishwasher = cycles/week × L/cycle × 52   (if owned)

    V_total = sum
    """
    occ = int(inputs["occupants"])

    # Toilet
    toilet_type = inputs["toilet_type"]
    flushes = safe_float(inputs["flushes_per_person_day"])
    L_flush = DEFAULTS_WATER["L_per_flush"][toilet_type]
    if inputs["L_per_flush_override"] is not None:
        L_flush = max(safe_float(inputs["L_per_flush_override"]), 0.0)

    V_toilet_L_yr = max(occ, 0) * max(flushes, 0.0) * max(L_flush, 0.0) * 365.0

    # Shower
    shower_type = inputs["shower_type"]
    showers = safe_float(inputs["showers_per_person_day"])
    minutes = safe_float(inputs["minutes_per_shower"])
    flow = DEFAULTS_WATER["shower_flow_L_min"][shower_type]
    if inputs["shower_flow_override_L_min"] is not None:
        flow = max(safe_float(inputs["shower_flow_override_L_min"]), 0.0)

    V_shower_L_yr = max(occ, 0) * max(showers, 0.0) * max(minutes, 0.0) * max(flow, 0.0) * 365.0

    # Taps
    tap_eff = inputs["tap_efficiency"]
    taps_Lpd = DEFAULTS_WATER["taps_L_per_person_day"][tap_eff]
    if inputs["taps_L_per_person_day_override"] is not None:
        taps_Lpd = max(safe_float(inputs["taps_L_per_person_day_override"]), 0.0)

    V_taps_L_yr = max(occ, 0) * max(taps_Lpd, 0.0) * 365.0

    # Laundry (water)
    if inputs["has_washer"]:
        cycles_w = safe_float(inputs["wash_cycles_per_week"])
        L_cycle = safe_float(inputs["wash_L_per_cycle"])
        V_laundry_L_yr = max(cycles_w, 0.0) * max(L_cycle, 0.0) * 52.0
    else:
        V_laundry_L_yr = 0.0

    # Dishwasher (water)
    if inputs["has_dishwasher"]:
        cycles_d = safe_float(inputs["dish_cycles_per_week"])
        L_cycle_d = safe_float(inputs["dish_L_per_cycle"])
        V_dish_L_yr = max(cycles_d, 0.0) * max(L_cycle_d, 0.0) * 52.0
    else:
        V_dish_L_yr = 0.0

    V_total_L_yr = V_toilet_L_yr + V_shower_L_yr + V_taps_L_yr + V_laundry_L_yr + V_dish_L_yr

    return {
        "V_toilet_L_yr": V_toilet_L_yr,
        "V_shower_L_yr": V_shower_L_yr,
        "V_taps_L_yr": V_taps_L_yr,
        "V_laundry_L_yr": V_laundry_L_yr,
        "V_dishwasher_L_yr": V_dish_L_yr,
        "V_total_L_yr": V_total_L_yr,
    }

def compute_operational_carbon(total_electricity_kWh_yr: float, water_L_yr: float, EF_grid: float, EF_water: float) -> Dict[str, float]:
    """
    CO2_electricity = kWh * EF_grid
    CO2_water       = (L/1000) * EF_water   [since EF_water is per m³]
    CO2_operational = sum
    """
    CO2_el = max(total_electricity_kWh_yr, 0.0) * max(EF_grid, 0.0)
    CO2_w = (max(water_L_yr, 0.0) / 1000.0) * max(EF_water, 0.0)
    return {
        "CO2_electricity_kg_yr": CO2_el,
        "CO2_water_kg_yr": CO2_w,
        "CO2_operational_kg_yr": CO2_el + CO2_w,
    }

def compute_operating_costs(total_electricity_kWh_yr: float, water_L_yr: float, tariff_el: float, tariff_water: float) -> Dict[str, float]:
    """
    Cost_electricity = kWh * tariff_el
    Cost_water       = (L/1000) * tariff_water
    Cost_operating   = sum
    """
    cost_el = max(total_electricity_kWh_yr, 0.0) * max(tariff_el, 0.0)
    cost_w = (max(water_L_yr, 0.0) / 1000.0) * max(tariff_water, 0.0)
    return {
        "Cost_electricity_NZD_yr": cost_el,
        "Cost_water_NZD_yr": cost_w,
        "Cost_operating_NZD_yr": cost_el + cost_w,
    }

def compute_upgrade_costs(
    areas: Dict[str, float],
    scenario_flags: Dict[str, bool],
    heating_system: str,
    hot_water_system: str,
    toilet_type: str,
    shower_type: str,
    taps_efficiency: str,
    n_toilets: int,
    n_showers: int,
    n_taps: int,
    cost_coeff: Dict[str, float],
) -> Dict[str, float]:
    """
    Upgrade costs (incremental, one-off)

    Insulation (area-based):
      Cost_roof  = roof area × Δcost_roof/m²
      Cost_wall  = wall area × Δcost_wall/m²
      Cost_floor = floor area × Δcost_floor/m²

    Windows:
      Cost_windows = window area × Δcost_window/m²

    Heating system:
      Cost_heating = Δcost_heatpump_vs_electric (if heat pump selected)

    Water fixtures:
      Cost_toilets = number × Δcost_dual_flush (if dual flush selected)
      Cost_showers = number × Δcost_lowflow_shower (if low-flow selected)
      Cost_taps    = number × Δcost_aerator (if efficient taps selected)
    """
    A_roof = areas["A_roof_m2"]
    A_wall = areas["A_wall_opaque_m2"]
    A_floor = areas["A_floor_m2"]
    A_window = areas["A_window_m2"]

    c_roof = (A_roof * cost_coeff["d_roof_NZD_per_m2"]) if scenario_flags.get("roof", False) else 0.0
    c_wall = (A_wall * cost_coeff["d_wall_NZD_per_m2"]) if scenario_flags.get("wall", False) else 0.0
    c_floor = (A_floor * cost_coeff["d_floor_NZD_per_m2"]) if scenario_flags.get("floor", False) else 0.0
    c_windows = (A_window * cost_coeff["d_window_NZD_per_m2"]) if scenario_flags.get("windows", False) else 0.0

    c_heating = cost_coeff["d_heatpump_vs_electric_NZD"] if heating_system == "Heat pump" else 0.0
    c_hw = cost_coeff["d_hw_heatpump_vs_electric_NZD"] if hot_water_system == "Heat pump hot water" else 0.0

    c_toilet = (n_toilets * cost_coeff["d_dual_flush_toilet_NZD_each"]) if toilet_type == "Dual flush" else 0.0
    c_shower = (n_showers * cost_coeff["d_lowflow_shower_NZD_each"]) if shower_type == "Low-flow" else 0.0
    c_taps = (n_taps * cost_coeff["d_tap_aerator_NZD_each"]) if taps_efficiency == "Efficient" else 0.0

    total = c_roof + c_wall + c_floor + c_windows + c_heating + c_hw + c_toilet + c_shower + c_taps

    return {
        "Cost_roof_NZD": c_roof,
        "Cost_wall_NZD": c_wall,
        "Cost_floor_NZD": c_floor,
        "Cost_windows_NZD": c_windows,
        "Cost_heating_NZD": c_heating,
        "Cost_hotwater_system_NZD": c_hw,
        "Cost_toilets_NZD": c_toilet,
        "Cost_showers_NZD": c_shower,
        "Cost_taps_NZD": c_taps,
        "Cost_upgrade_total_NZD": total,
    }

# =========================================================
# UI — GLOBAL ASSUMPTIONS (SIDEBAR)
# =========================================================
st.title("Early-stage NZ Housing Sustainability Calculator (Prototype)")
st.write(
    """
Conceptual + computational model for **relative comparison** (not certification, not prediction).

- Transparency > precision
- Simple physics + lookup coefficients
- Defaults first, optional overrides
- No embodied carbon, no detailed simulation, no behavioural modelling, no time-of-use pricing
"""
)

with st.sidebar:
    st.header("Global assumptions")
    EF_grid = st.number_input(
        "Grid emission factor (kgCO₂e/kWh)",
        min_value=0.0, max_value=1.0,
        value=DEFAULTS_CARBON["grid_kgCO2e_per_kWh"], step=0.01,
    )
    EF_water = st.number_input(
        "Water emission factor (kgCO₂e/m³)",
        min_value=0.0, max_value=5.0,
        value=DEFAULTS_CARBON["water_kgCO2e_per_m3"], step=0.05,
    )
    tariff_el = st.number_input(
        "Electricity tariff (NZD/kWh)",
        min_value=0.0, max_value=2.0,
        value=DEFAULTS_TARIFFS["electricity_NZD_per_kWh"], step=0.01,
    )
    tariff_water = st.number_input(
        "Water tariff (NZD/m³)",
        min_value=0.0, max_value=20.0,
        value=DEFAULTS_TARIFFS["water_NZD_per_m3"], step=0.10,
    )

    st.divider()
    st.header("Upgrade cost coefficients (V1)")
    st.caption("These are incremental coefficients used by the Upgrade Cost module.")
    cost_coeff = {}
    for k, v in DEFAULTS_UPGRADE_COSTS.items():
        label = k.replace("_", " ")
        cost_coeff[k] = st.number_input(label, min_value=0.0, value=float(v), step=10.0 if "per_m2" in k else 50.0)

# =========================================================
# UI — SCENARIO INPUT (NO NESTED COLUMNS)
# =========================================================

def scenario_ui(prefix: str, defaults_for_cost_flags: Dict[str, bool]) -> Dict[str, Any]:
    tabs = st.tabs(["Space heating", "Water heating", "Lighting & appliances", "Water consumption", "Costs (upgrade flags)"])

    # ---------- TAB 1: Space heating ----------
    with tabs[0]:
        floor_area_m2 = st.number_input(
            "Floor area (m²)", min_value=20.0, max_value=600.0,
            value=120.0, step=5.0, key=f"{prefix}_floor_area_m2"
        )
        ceiling_height_m = st.number_input(
            "Ceiling height (m)", min_value=2.0, max_value=4.0,
            value=DEFAULTS_SPACE["ceiling_height_m"], step=0.1, key=f"{prefix}_ceiling_height_m"
        )

        hdd_mode = st.radio(
            "Heating Degree Days (HDD, base 18°C)",
            ["Use climate zone lookup", "Enter HDD manually"],
            index=0, horizontal=True, key=f"{prefix}_hdd_mode",
        )
        if hdd_mode == "Use climate zone lookup":
            cz = st.selectbox(
                "NZ climate zone (for HDD lookup)",
                list(HDD_LOOKUP_BASE18.keys()),
                index=2 if "Zone 3 (mild)" in HDD_LOOKUP_BASE18 else 0,
                key=f"{prefix}_climate_zone",
            )
            HDD = float(HDD_LOOKUP_BASE18[cz])
            st.caption(f"HDD used: **{HDD:,.0f}** (base 18°C)")
        else:
            HDD = st.number_input(
                "HDD (base 18°C)", min_value=0.0, max_value=6000.0,
                value=float(DEFAULTS_SPACE["hdd_manual"]), step=50.0, key=f"{prefix}_HDD_manual"
            )

        st.markdown("**Window typologies (derived window area)**")
        windows_df = st.data_editor(
            default_windows_df(),
            num_rows="dynamic",
            use_container_width=True,
            key=f"{prefix}_windows_df",
        )
        st.caption("Window area = Σ(width × height × count).")

        U_window = st.number_input(
            "Window U-value (W/m²·K)", min_value=0.5, max_value=6.0,
            value=DEFAULTS_SPACE["U_window_W_m2K"], step=0.1, key=f"{prefix}_U_window"
        )

        st.divider()
        st.markdown("**Thermal envelope (R-values)**")
        R_roof = st.number_input(
            "Roof R-value (m²·K/W)", min_value=0.1, max_value=10.0,
            value=DEFAULTS_SPACE["R_roof_m2K_W"], step=0.1, key=f"{prefix}_R_roof"
        )
        R_wall = st.number_input(
            "Wall R-value (m²·K/W)", min_value=0.1, max_value=10.0,
            value=DEFAULTS_SPACE["R_wall_m2K_W"], step=0.1, key=f"{prefix}_R_wall"
        )
        R_floor = st.number_input(
            "Floor R-value (m²·K/W)", min_value=0.1, max_value=10.0,
            value=DEFAULTS_SPACE["R_floor_m2K_W"], step=0.1, key=f"{prefix}_R_floor"
        )

        st.divider()
        st.markdown("**Heating system**")
        heating_system = st.radio(
            "Type",
            ["Electric resistance", "Heat pump"],
            index=1,
            horizontal=True,
            key=f"{prefix}_heating_system",
        )
        heat_pump_COP = DEFAULTS_SPACE["heat_pump_COP"]
        if heating_system == "Heat pump":
            heat_pump_COP = st.number_input(
                "Heat pump COP", min_value=1.0, max_value=6.0,
                value=DEFAULTS_SPACE["heat_pump_COP"], step=0.1, key=f"{prefix}_heat_pump_COP"
            )

    # ---------- TAB 2: Water heating ----------
    with tabs[1]:
        occupants = st.number_input(
            "Household size (occupants)", min_value=1, max_value=10,
            value=3, step=1, key=f"{prefix}_occupants"
        )

        hot_water_system = st.radio(
            "Hot water system type",
            ["Electric storage", "Heat pump hot water"],
            index=0,
            horizontal=True,
            key=f"{prefix}_hot_water_system",
        )

        override_hw = st.toggle("Override water heating defaults", value=False, key=f"{prefix}_override_hw")
        if override_hw:
            L_ppd = st.number_input(
                "Hot water demand (L/person/day)", min_value=0.0, max_value=300.0,
                value=DEFAULTS_WATER_HEATING["L_per_person_day"], step=5.0, key=f"{prefix}_L_ppd"
            )
            T_hot = st.number_input(
                "Hot water setpoint (°C)", min_value=30.0, max_value=70.0,
                value=DEFAULTS_WATER_HEATING["T_hot_C"], step=1.0, key=f"{prefix}_T_hot"
            )
            T_cold = st.number_input(
                "Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0,
                value=DEFAULTS_WATER_HEATING["T_cold_C"], step=1.0, key=f"{prefix}_T_cold"
            )
        else:
            L_ppd = DEFAULTS_WATER_HEATING["L_per_person_day"]
            T_hot = DEFAULTS_WATER_HEATING["T_hot_C"]
            T_cold = DEFAULTS_WATER_HEATING["T_cold_C"]

        if hot_water_system == "Heat pump hot water":
            COP_hw = st.number_input(
                "Heat pump hot water COP", min_value=1.0, max_value=6.0,
                value=DEFAULTS_WATER_HEATING["COP_heat_pump_hw"], step=0.1, key=f"{prefix}_COP_hw"
            )
        else:
            COP_hw = 1.0

    # ---------- TAB 3: Lighting & appliances ----------
    with tabs[2]:
        st.markdown("**Lighting**")
        n_lights = st.number_input("Number of lights", min_value=0, max_value=300, value=20, step=1, key=f"{prefix}_n_lights")
        lighting_type = st.selectbox(
            "Lighting type",
            list(DEFAULTS_OTHER["lamp_watt_by_type"].keys()),
            index=0,
            key=f"{prefix}_lighting_type",
        )
        lighting_hours = st.number_input(
            "Average lighting hours/day", min_value=0.0, max_value=24.0,
            value=DEFAULTS_OTHER["lighting_hours_per_day"], step=0.5, key=f"{prefix}_lighting_hours"
        )
        override_lamp = st.toggle("Override lamp wattage", value=False, key=f"{prefix}_override_lamp")
        lamp_watt_override = None
        if override_lamp:
            lamp_watt_override = st.number_input(
                "Lamp wattage (W per light)", min_value=0.0, max_value=200.0,
                value=float(DEFAULTS_OTHER["lamp_watt_by_type"][lighting_type]), step=1.0, key=f"{prefix}_lamp_watt_override"
            )

        st.divider()
        st.markdown("**Washing machine**")
        has_washer = st.checkbox("Has washing machine", value=True, key=f"{prefix}_has_washer")
        wash_cycles = st.number_input("Cycles per week", min_value=0.0, max_value=30.0, value=4.0, step=1.0, key=f"{prefix}_wash_cycles")
        wash_kwh_cycle = st.number_input(
            "Energy per cycle (kWh/cycle)", min_value=0.0, max_value=10.0,
            value=DEFAULTS_OTHER["wash_kwh_per_cycle"], step=0.1, key=f"{prefix}_wash_kwh_cycle"
        )

        st.divider()
        st.markdown("**Dishwasher**")
        has_dishwasher = st.checkbox("Has dishwasher", value=False, key=f"{prefix}_has_dishwasher")
        dish_cycles = st.number_input("Cycles per week", min_value=0.0, max_value=30.0, value=3.0, step=1.0, key=f"{prefix}_dish_cycles")
        dish_kwh_cycle = st.number_input(
            "Energy per cycle (kWh/cycle)", min_value=0.0, max_value=10.0,
            value=DEFAULTS_OTHER["dish_kwh_per_cycle"], step=0.1, key=f"{prefix}_dish_kwh_cycle"
        )

        st.divider()
        st.markdown("**Cooking (electric)**")
        cooking_method = st.radio(
            "Cooking input method",
            ["Meals/week", "Hours/day"],
            index=0,
            horizontal=True,
            key=f"{prefix}_cooking_method",
        )
        if cooking_method == "Meals/week":
            meals_per_week = st.number_input("Meals per week", min_value=0.0, max_value=100.0, value=14.0, step=1.0, key=f"{prefix}_meals_week")
            cook_kwh_meal = st.number_input(
                "Energy per meal (kWh/meal)", min_value=0.0, max_value=10.0,
                value=DEFAULTS_OTHER["cook_kwh_per_meal"], step=0.1, key=f"{prefix}_cook_kwh_meal"
            )
            cook_power_kW = DEFAULTS_OTHER["cook_power_kW"]
            cook_hours_day = 0.0
        else:
            cook_power_kW = st.number_input(
                "Cooking power rating (kW)", min_value=0.0, max_value=10.0,
                value=DEFAULTS_OTHER["cook_power_kW"], step=0.1, key=f"{prefix}_cook_power"
            )
            cook_hours_day = st.number_input(
                "Cooking hours per day", min_value=0.0, max_value=6.0,
                value=1.0, step=0.1, key=f"{prefix}_cook_hours_day"
            )
            meals_per_week = 0.0
            cook_kwh_meal = DEFAULTS_OTHER["cook_kwh_per_meal"]

    # ---------- TAB 4: Water consumption ----------
    with tabs[3]:
        # Keep occupants consistent (already entered in tab 2)
        toilet_type = st.selectbox("Toilet type", ["Standard", "Dual flush"], index=1, key=f"{prefix}_toilet_type")
        flushes = st.number_input(
            "Flushes per person per day", min_value=0.0, max_value=20.0,
            value=DEFAULTS_WATER["flushes_per_person_day"], step=0.5, key=f"{prefix}_flushes_ppd"
        )
        override_flush = st.toggle("Override litres per flush", value=False, key=f"{prefix}_override_flush")
        L_flush_override = None
        if override_flush:
            L_flush_override = st.number_input(
                "Litres per flush", min_value=0.0, max_value=20.0,
                value=float(DEFAULTS_WATER["L_per_flush"][toilet_type]), step=0.5, key=f"{prefix}_L_flush_override"
            )

        st.divider()
        shower_type = st.selectbox("Shower type", ["Standard", "Low-flow"], index=0, key=f"{prefix}_shower_type")
        showers = st.number_input(
            "Showers per person per day", min_value=0.0, max_value=5.0,
            value=DEFAULTS_WATER["showers_per_person_day"], step=0.1, key=f"{prefix}_showers_ppd"
        )
        minutes = st.number_input(
            "Minutes per shower", min_value=0.0, max_value=60.0,
            value=DEFAULTS_WATER["minutes_per_shower"], step=1.0, key=f"{prefix}_minutes_shower"
        )
        override_flow = st.toggle("Override shower flow rate", value=False, key=f"{prefix}_override_flow")
        shower_flow_override = None
        if override_flow:
            shower_flow_override = st.number_input(
                "Shower flow rate (L/min)", min_value=0.0, max_value=30.0,
                value=float(DEFAULTS_WATER["shower_flow_L_min"][shower_type]), step=0.5, key=f"{prefix}_shower_flow_override"
            )

        st.divider()
        tap_eff = st.selectbox("Tap efficiency", ["Standard", "Efficient"], index=0, key=f"{prefix}_tap_eff")
        override_taps = st.toggle("Override taps water per person/day", value=False, key=f"{prefix}_override_taps")
        taps_Lpd_override = None
        if override_taps:
            taps_Lpd_override = st.number_input(
                "Taps water use (L/person/day)", min_value=0.0, max_value=200.0,
                value=float(DEFAULTS_WATER["taps_L_per_person_day"][tap_eff]), step=1.0, key=f"{prefix}_taps_Lpd_override"
            )

        st.divider()
        st.markdown("**Laundry + dishwasher water**")
        wash_L_cycle = st.number_input(
            "Water per wash cycle (L/cycle)", min_value=0.0, max_value=300.0,
            value=DEFAULTS_WATER["wash_L_per_cycle"], step=5.0, key=f"{prefix}_wash_L_cycle"
        )
        dish_L_cycle = st.number_input(
            "Water per dishwasher cycle (L/cycle)", min_value=0.0, max_value=100.0,
            value=DEFAULTS_WATER["dish_L_per_cycle"], step=1.0, key=f"{prefix}_dish_L_cycle"
        )

    # ---------- TAB 5: Costs (upgrade flags) ----------
    with tabs[4]:
        st.markdown("**Envelope upgrade flags (controls which area-based Δcosts are applied)**")
        flag_roof = st.checkbox("Include roof insulation upgrade cost", value=defaults_for_cost_flags.get("roof", False), key=f"{prefix}_flag_roof")
        flag_wall = st.checkbox("Include wall insulation upgrade cost", value=defaults_for_cost_flags.get("wall", False), key=f"{prefix}_flag_wall")
        flag_floor = st.checkbox("Include floor insulation upgrade cost", value=defaults_for_cost_flags.get("floor", False), key=f"{prefix}_flag_floor")
        flag_windows = st.checkbox("Include window upgrade cost", value=defaults_for_cost_flags.get("windows", False), key=f"{prefix}_flag_windows")

        st.divider()
        st.markdown("**Fixture counts (for incremental fixture costs)**")
        n_toilets = st.number_input("Number of toilets", min_value=0, max_value=10, value=1, step=1, key=f"{prefix}_n_toilets")
        n_showers = st.number_input("Number of showers", min_value=0, max_value=10, value=1, step=1, key=f"{prefix}_n_showers")
        n_taps = st.number_input("Number of taps (for aerators)", min_value=0, max_value=30, value=4, step=1, key=f"{prefix}_n_taps")

    return {
        # Space heating
        "floor_area_m2": float(floor_area_m2),
        "ceiling_height_m": float(ceiling_height_m),
        "HDD": float(HDD),
        "windows_df": windows_df,
        "U_window": float(U_window),
        "R_roof": float(R_roof),
        "R_wall": float(R_wall),
        "R_floor": float(R_floor),
        "heating_system": heating_system,
        "heat_pump_COP": float(heat_pump_COP),

        # Water heating / household
        "occupants": int(occupants),
        "hot_water_system": hot_water_system,
        "L_hotwater_per_person_day": float(L_ppd),
        "T_hot_C": float(T_hot),
        "T_cold_C": float(T_cold),
        "COP_hw": float(COP_hw),

        # Lighting & appliances
        "n_lights": int(n_lights),
        "lighting_type": lighting_type,
        "lighting_hours_per_day": float(lighting_hours),
        "lamp_watt_override": float(lamp_watt_override) if lamp_watt_override is not None else None,
        "has_washer": bool(has_washer),
        "wash_cycles_per_week": float(wash_cycles),
        "wash_kwh_per_cycle": float(wash_kwh_cycle),
        "has_dishwasher": bool(has_dishwasher),
        "dish_cycles_per_week": float(dish_cycles),
        "dish_kwh_per_cycle": float(dish_kwh_cycle),
        "cooking_method": cooking_method,
        "meals_per_week": float(meals_per_week),
        "cook_kwh_per_meal": float(cook_kwh_meal),
        "cook_power_kW": float(cook_power_kW),
        "cook_hours_per_day": float(cook_hours_day),

        # Water consumption inputs (reuses washer/dish cycles + ownership)
        "toilet_type": toilet_type,
        "flushes_per_person_day": float(flushes),
        "L_per_flush_override": float(L_flush_override) if L_flush_override is not None else None,
        "shower_type": shower_type,
        "showers_per_person_day": float(showers),
        "minutes_per_shower": float(minutes),
        "shower_flow_override_L_min": float(shower_flow_override) if shower_flow_override is not None else None,
        "tap_efficiency": tap_eff,
        "taps_L_per_person_day_override": float(taps_Lpd_override) if taps_Lpd_override is not None else None,
        "wash_L_per_cycle": float(wash_L_cycle),
        "dish_L_per_cycle": float(dish_L_cycle),

        # Upgrade flags + counts
        "upgrade_flags": {
            "roof": bool(flag_roof),
            "wall": bool(flag_wall),
            "floor": bool(flag_floor),
            "windows": bool(flag_windows),
        },
        "n_toilets": int(n_toilets),
        "n_showers": int(n_showers),
        "n_taps": int(n_taps),
    }

# =========================================================
# LAYOUT — BASELINE / OPTION / RESULTS
# =========================================================

col1, col2, col3 = st.columns([1.15, 1.15, 1.35])

with col1:
    st.header("Baseline")
    baseline_inputs = scenario_ui("BASE", defaults_for_cost_flags={"roof": False, "wall": False, "floor": False, "windows": False})

with col2:
    st.header("Option")
    option_inputs = scenario_ui("OPT", defaults_for_cost_flags={"roof": True, "wall": True, "floor": False, "windows": True})

# =========================================================
# COMPUTE — BASELINE + OPTION
# =========================================================

def compute_all(inputs: Dict[str, Any]) -> Dict[str, Any]:
    space = compute_space_heating(inputs)
    water_heat = compute_water_heating(inputs)
    other = compute_lighting_and_appliances(inputs)
    water = compute_water_consumption(inputs)

    # Total energy consumption = space heating (purchased) + water heating (purchased) + lighting & appliances
    total_electricity_kWh_yr = (
        space["Q_space_purchased_kWh_yr"]
        + water_heat["Q_hw_purchased_kWh_yr"]
        + other["Q_other_kWh_yr"]
    )

    carbon = compute_operational_carbon(
        total_electricity_kWh_yr=total_electricity_kWh_yr,
        water_L_yr=water["V_total_L_yr"],
        EF_grid=EF_grid,
        EF_water=EF_water,
    )

    opex = compute_operating_costs(
        total_electricity_kWh_yr=total_electricity_kWh_yr,
        water_L_yr=water["V_total_L_yr"],
        tariff_el=tariff_el,
        tariff_water=tariff_water,
    )

    upgrade = compute_upgrade_costs(
        areas={
            "A_roof_m2": space["A_roof_m2"],
            "A_wall_opaque_m2": space["A_wall_opaque_m2"],
            "A_floor_m2": space["A_floor_m2"],
            "A_window_m2": space["A_window_m2"],
        },
        scenario_flags=inputs["upgrade_flags"],
        heating_system=inputs["heating_system"],
        hot_water_system=inputs["hot_water_system"],
        toilet_type=inputs["toilet_type"],
        shower_type=inputs["shower_type"],
        taps_efficiency=inputs["tap_efficiency"],
        n_toilets=inputs["n_toilets"],
        n_showers=inputs["n_showers"],
        n_taps=inputs["n_taps"],
        cost_coeff=cost_coeff,
    )

    return {
        "space_heating": space,
        "water_heating": water_heat,
        "lighting_appliances": other,
        "water": water,
        "energy_total_kWh_yr": total_electricity_kWh_yr,
        "energy_breakdown_kWh_yr": {
            "space_heating_purchased": space["Q_space_purchased_kWh_yr"],
            "water_heating_purchased": water_heat["Q_hw_purchased_kWh_yr"],
            "lighting_and_appliances": other["Q_other_kWh_yr"],
        },
        "carbon": carbon,
        "opex": opex,
        "upgrade": upgrade,
    }

baseline = compute_all(baseline_inputs)
option = compute_all(option_inputs)

# Incremental upgrade cost (Option − Baseline), clamped at >= 0 for payback convention
upgrade_baseline = baseline["upgrade"]["Cost_upgrade_total_NZD"]
upgrade_option = option["upgrade"]["Cost_upgrade_total_NZD"]
upgrade_incremental = max(upgrade_option - upgrade_baseline, 0.0)

# Annual operating savings (Baseline − Option)
opex_savings = baseline["opex"]["Cost_operating_NZD_yr"] - option["opex"]["Cost_operating_NZD_yr"]

if upgrade_incremental > 0 and opex_savings > 0:
    payback_years = upgrade_incremental / opex_savings
else:
    payback_years = None

# =========================================================
# RESULTS — COMPACT TABLE (BASELINE | OPTION WITH ARROW)
# =========================================================
with col3:
    st.header("Results (compact)")

    summary = pd.DataFrame(
        {
            "Baseline": [
                _fmt(baseline["energy_total_kWh_yr"], 0),
                _fmt(baseline["energy_breakdown_kWh_yr"]["space_heating_purchased"], 0),
                _fmt(baseline["energy_breakdown_kWh_yr"]["water_heating_purchased"], 0),
                _fmt(baseline["energy_breakdown_kWh_yr"]["lighting_and_appliances"], 0),
                _fmt(baseline["water"]["V_total_L_yr"], 0),
                _fmt(baseline["carbon"]["CO2_operational_kg_yr"], 0),
                _fmt(baseline["opex"]["Cost_operating_NZD_yr"], 0),
                _fmt(baseline["upgrade"]["Cost_upgrade_total_NZD"], 0),
                "—",
            ],
            "Option": [
                opt_cell(option["energy_total_kWh_yr"], baseline["energy_total_kWh_yr"], 0),
                opt_cell(option["energy_breakdown_kWh_yr"]["space_heating_purchased"], baseline["energy_breakdown_kWh_yr"]["space_heating_purchased"], 0),
                opt_cell(option["energy_breakdown_kWh_yr"]["water_heating_purchased"], baseline["energy_breakdown_kWh_yr"]["water_heating_purchased"], 0),
                opt_cell(option["energy_breakdown_kWh_yr"]["lighting_and_appliances"], baseline["energy_breakdown_kWh_yr"]["lighting_and_appliances"], 0),
                opt_cell(option["water"]["V_total_L_yr"], baseline["water"]["V_total_L_yr"], 0),
                opt_cell(option["carbon"]["CO2_operational_kg_yr"], baseline["carbon"]["CO2_operational_kg_yr"], 0),
                opt_cell(option["opex"]["Cost_operating_NZD_yr"], baseline["opex"]["Cost_operating_NZD_yr"], 0),
                opt_cell(option["upgrade"]["Cost_upgrade_total_NZD"], baseline["upgrade"]["Cost_upgrade_total_NZD"], 0),
                (f"{payback_years:.1f}" if payback_years is not None else "N/A"),
            ],
        },
        index=[
            "Total energy (kWh/yr)",
            "Space heating (purchased, kWh/yr)",
            "Water heating (purchased, kWh/yr)",
            "Lighting & appliances (kWh/yr)",
            "Water consumption (L/yr)",
            "Operational carbon (kgCO₂e/yr)",
            "Operating cost (NZD/yr)",
            "Upgrade cost total (NZD, one-off)",
            "Simple payback (years)",
        ],
    )

    st.table(summary)
    st.caption("Arrow shows Option relative to Baseline (↑ higher, ↓ lower, → no change).")

    # Keep detail behind tabs/expanders to reduce vertical scroll
    detail_tabs = st.tabs(["Breakdowns", "Debug (intermediate values)"])

    with detail_tabs[0]:
        with st.expander("Energy breakdown details", expanded=False):
            eb = pd.DataFrame(
                {
                    "Baseline (kWh/yr)": baseline["energy_breakdown_kWh_yr"],
                    "Option (kWh/yr)": option["energy_breakdown_kWh_yr"],
                }
            )
            st.dataframe(eb, use_container_width=True)

        with st.expander("Water end-use breakdown (L/yr)", expanded=False):
            wb = pd.DataFrame(
                {
                    "Baseline (L/yr)": {
                        k: v for k, v in baseline["water"].items() if k.endswith("_L_yr")
                    },
                    "Option (L/yr)": {
                        k: v for k, v in option["water"].items() if k.endswith("_L_yr")
                    },
                }
            )
            st.dataframe(wb, use_container_width=True)

        with st.expander("Operational carbon breakdown (kgCO₂e/yr)", expanded=False):
            cb = pd.DataFrame(
                {
                    "Baseline": baseline["carbon"],
                    "Option": option["carbon"],
                }
            )
            st.dataframe(cb, use_container_width=True)

        with st.expander("Costs breakdown", expanded=False):
            costs = pd.DataFrame(
                {
                    "Baseline": {
                        **baseline["opex"],
                        **baseline["upgrade"],
                    },
                    "Option": {
                        **option["opex"],
                        **option["upgrade"],
                    },
                }
            )
            st.dataframe(costs, use_container_width=True)
            st.write(f"Incremental upgrade cost (Option − Baseline): **{_fmt(upgrade_incremental, 0)} NZD**")
            st.write(f"Annual operating savings (Baseline − Option): **{_fmt(opex_savings, 0)} NZD/yr**")

    with detail_tabs[1]:
        with st.expander("Space heating intermediate values", expanded=False):
            sb = baseline["space_heating"]
            so = option["space_heating"]

            df_dbg = pd.DataFrame(
                {
                    "Baseline": {
                        "A_roof_m2": sb["A_roof_m2"],
                        "A_floor_m2": sb["A_floor_m2"],
                        "A_wall_gross_m2": sb["A_wall_gross_m2"],
                        "A_wall_opaque_m2": sb["A_wall_opaque_m2"],
                        "A_window_m2": sb["A_window_m2"],
                        "U_roof": sb["U_roof"],
                        "U_wall": sb["U_wall"],
                        "U_floor": sb["U_floor"],
                        "U_window": sb["U_window"],
                        "H_W_per_K": sb["H_W_per_K"],
                        "Q_delivered_kWh_yr": sb["Q_space_delivered_kWh_yr"],
                        "Q_purchased_kWh_yr": sb["Q_space_purchased_kWh_yr"],
                    },
                    "Option": {
                        "A_roof_m2": so["A_roof_m2"],
                        "A_floor_m2": so["A_floor_m2"],
                        "A_wall_gross_m2": so["A_wall_gross_m2"],
                        "A_wall_opaque_m2": so["A_wall_opaque_m2"],
                        "A_window_m2": so["A_window_m2"],
                        "U_roof": so["U_roof"],
                        "U_wall": so["U_wall"],
                        "U_floor": so["U_floor"],
                        "U_window": so["U_window"],
                        "H_W_per_K": so["H_W_per_K"],
                        "Q_delivered_kWh_yr": so["Q_space_delivered_kWh_yr"],
                        "Q_purchased_kWh_yr": so["Q_space_purchased_kWh_yr"],
                    },
                }
            )
            st.dataframe(df_dbg, use_container_width=True)

st.info(
    "Model reminders: steady-state, early-stage comparison only. No ventilation/infiltration, gains, behaviour, detailed simulation, or certification claims."
)
