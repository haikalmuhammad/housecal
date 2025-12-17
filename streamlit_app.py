# app.py
import math
import pandas as pd
import streamlit as st

# =========================================================
# 0. GLOBAL DEFAULTS (Backend coefficients, V1 placeholders)
# =========================================================

# --- Space heating: HDD lookup (PLACEHOLDER TABLE) ---
# Replace with your actual NZ climate zone -> HDD (base 18°C) lookup.
HDD_LOOKUP_BASE18 = {
    "Zone 1": 1200,
    "Zone 2": 1600,
    "Zone 3": 2000,
    "Zone 4": 2400,
    "Zone 5": 2800,
    "Zone 6": 3200,
}

DEFAULTS_SPACE = {
    "ceiling_height_m": 2.4,
    "R_roof_m2K_W": 3.6,
    "R_wall_m2K_W": 2.0,
    "R_floor_m2K_W": 1.3,
    "U_window_W_m2K": 2.8,
    "heat_pump_COP": 3.0,
    "hdd_manual": 2000,
}

# --- Water heating defaults (Backend coefficients, V1) ---
DEFAULTS_WATER_HEATING = {
    "L_per_person_day": 50.0,  # placeholder default
    "T_hot_C": 55.0,
    "T_cold_C": 15.0,
    "COP_heat_pump_hw": 2.5,
    "eta_electric_storage": 1.0,
}
CP_WATER_KJ_PER_KG_C = 4.186
KWH_PER_KJ = 1.0 / 3600.0  # 1 kWh = 3600 kJ

# --- Lighting & appliances defaults (Backend coefficients, V1) ---
DEFAULTS_OTHER = {
    "lighting_hours_per_day": 3.0,
    "lamp_watt_by_type": {
        "LED": 9.0,
        "Mixed": 15.0,
        "Halogen/Incandescent": 40.0,
    },
    "wash_kwh_per_cycle": 0.7,
    "dish_kwh_per_cycle": 1.0,
    "cook_kwh_per_meal": 0.7,
    "cook_power_kW": 2.0,
}

# --- Water consumption defaults (Backend coefficients, V1) ---
DEFAULTS_WATER = {
    "flushes_per_person_day": 5.0,
    "L_per_flush": {
        "Standard": 6.0,
        "Dual flush": 4.5,
    },
    "showers_per_person_day": 1.0,
    "minutes_per_shower": 8.0,
    "shower_flow_L_min": {
        "Standard": 9.0,
        "Low-flow": 6.0,
    },
    "taps_L_per_person_day": {
        "Standard": 30.0,
        "Efficient": 20.0,
    },
    "wash_L_per_cycle": 70.0,
    "dish_L_per_cycle": 15.0,
}

# --- Operational carbon defaults (PLACEHOLDER FACTORS) ---
DEFAULTS_CARBON = {
    "grid_kgCO2e_per_kWh": 0.10,      # placeholder
    "water_kgCO2e_per_m3": 0.30,      # placeholder
}

# --- Operating cost defaults (PLACEHOLDER TARIFFS) ---
DEFAULTS_TARIFFS = {
    "electricity_NZD_per_kWh": 0.30,  # placeholder
    "water_NZD_per_m3": 2.50,         # placeholder
}

# --- Upgrade cost defaults (PLACEHOLDER INCREMENTAL COSTS) ---
DEFAULTS_UPGRADE_COSTS = {
    "d_cost_roof_per_m2": 60.0,
    "d_cost_wall_per_m2": 80.0,
    "d_cost_floor_per_m2": 70.0,
    "d_cost_window_per_m2": 350.0,
    "d_cost_heatpump_vs_electric": 5000.0,
    "d_cost_dual_flush_each": 300.0,
    "d_cost_lowflow_shower_each": 150.0,
    "d_cost_aerator_each": 20.0,
}


# =========================================================
# 1. CALCULATION FUNCTIONS (Map 1:1 to master specification)
# =========================================================

def _clamp_nonneg(x: float) -> float:
    return max(float(x), 0.0)

def _safe_div(n: float, d: float, default: float = 0.0) -> float:
    return n / d if d not in (0, 0.0) else default


# -------------------------
# 1.1 Space Heating
# -------------------------

def space_heating_geometry(
    floor_area_m2: float,
    ceiling_height_m: float,
    windows_df: pd.DataFrame,
) -> dict:
    """
    Spec 1.1.3 Step 2: Estimate element areas (system-calculated)

    - Roof area ≈ floor area
    - Wall area ≈ derived from floor area and ceiling height (simplified rectangular footprint)
    - Window area = Σ (width × height × count)

    Implementation: square footprint assumption (rectangular, aspect ratio = 1).
    """
    A_floor = _clamp_nonneg(floor_area_m2)
    h = _clamp_nonneg(ceiling_height_m)

    # Roof & floor
    A_roof = A_floor
    A_floor_area = A_floor

    # Wall area: assume square footprint => side = sqrt(A), perimeter = 4*side
    side = math.sqrt(A_floor) if A_floor > 0 else 0.0
    perimeter = 4.0 * side
    A_wall_gross = perimeter * h

    # Window area from typologies table
    A_window = 0.0
    if windows_df is not None and len(windows_df) > 0:
        for _, r in windows_df.iterrows():
            w = _clamp_nonneg(r.get("width_m", 0.0))
            hh = _clamp_nonneg(r.get("height_m", 0.0))
            c = _clamp_nonneg(r.get("count", 0.0))
            A_window += w * hh * c

    # Opaque wall area avoids double counting
    A_wall_opaque = max(A_wall_gross - A_window, 0.0)

    return {
        "A_roof_m2": A_roof,
        "A_wall_gross_m2": A_wall_gross,
        "A_wall_opaque_m2": A_wall_opaque,
        "A_floor_m2": A_floor_area,
        "A_window_m2": A_window,
    }


def space_heating_kwh_per_year(
    floor_area_m2: float,
    ceiling_height_m: float,
    windows_df: pd.DataFrame,
    R_roof_m2K_W: float,
    R_wall_m2K_W: float,
    R_floor_m2K_W: float,
    U_window_W_m2K: float,
    HDD_base18: float,
    heating_system_type: str,  # "Electric resistance" or "Heat pump"
    heat_pump_COP: float,
) -> dict:
    """
    Spec 1.1.3 Calculation Steps

    1) Convert R-values to U-values: U = 1/R
    2) Estimate element areas
    3) Heat loss coefficient: H = Σ(Area × U) [W/K]
    4) Delivered heating: Q_delivered = H × HDD × 24 / 1000 [kWh/year]
    5) Purchased: Q_purchased = Q_delivered / system_efficiency (COP or 1.0)
    """
    geom = space_heating_geometry(floor_area_m2, ceiling_height_m, windows_df)

    # Step 1: U-values for opaque elements
    U_roof = _safe_div(1.0, _clamp_nonneg(R_roof_m2K_W), default=0.0)
    U_wall = _safe_div(1.0, _clamp_nonneg(R_wall_m2K_W), default=0.0)
    U_floor = _safe_div(1.0, _clamp_nonneg(R_floor_m2K_W), default=0.0)

    U_window = _clamp_nonneg(U_window_W_m2K)

    # Step 3: H = Σ(Area × U)
    H_roof = geom["A_roof_m2"] * U_roof
    H_wall = geom["A_wall_opaque_m2"] * U_wall
    H_floor = geom["A_floor_m2"] * U_floor
    H_window = geom["A_window_m2"] * U_window

    H_total_W_per_K = H_roof + H_wall + H_floor + H_window

    # Step 4: Delivered energy
    HDD = _clamp_nonneg(HDD_base18)
    Q_delivered_kWh_per_year = H_total_W_per_K * HDD * 24.0 / 1000.0

    # Step 5: Purchased energy
    if heating_system_type == "Heat pump":
        system_eff = max(_clamp_nonneg(heat_pump_COP), 0.1)
    else:
        system_eff = 1.0

    Q_purchased_kWh_per_year = Q_delivered_kWh_per_year / system_eff

    return {
        "space_geom": geom,
        "U_roof": U_roof,
        "U_wall": U_wall,
        "U_floor": U_floor,
        "U_window": U_window,
        "H_W_per_K": H_total_W_per_K,
        "Q_space_delivered_kWh_yr": Q_delivered_kWh_per_year,
        "Q_space_purchased_kWh_yr": Q_purchased_kWh_per_year,
    }


# -------------------------
# 1.2 Water Heating
# -------------------------

def water_heating_kwh_per_year(
    occupants: int,
    L_per_person_day: float,
    T_hot_C: float,
    T_cold_C: float,
    hot_water_system_type: str,  # "Electric storage" or "Heat pump hot water"
    COP_hw: float,
) -> dict:
    """
    Spec 1.2.4 Calculation Steps

    1) V_annual = occupants × L/person/day × 365  [L/year]
    2) Q_delivered = (V_annual × ΔT × 4.186) / 3600  [kWh/year]
       (1 L ≈ 1 kg, Cp = 4.186 kJ/kg°C, 1 kWh = 3600 kJ)
    3) Q_purchased = Q_delivered / system_eff (η or COP)
    """
    n = int(max(occupants, 0))
    Lpd = _clamp_nonneg(L_per_person_day)

    V_annual_L = n * Lpd * 365.0

    dT = max(float(T_hot_C) - float(T_cold_C), 0.0)

    # Q_delivered in kWh
    # (L * °C * kJ/kg°C) => kJ, then /3600 => kWh
    Q_delivered_kWh_yr = (V_annual_L * dT * CP_WATER_KJ_PER_KG_C) * KWH_PER_KJ

    if hot_water_system_type == "Heat pump hot water":
        eff = max(_clamp_nonneg(COP_hw), 0.1)
    else:
        eff = 1.0  # electric storage η≈1.0 in spec defaults

    Q_purchased_kWh_yr = Q_delivered_kWh_yr / eff

    return {
        "V_hotwater_annual_L_yr": V_annual_L,
        "dT_C": dT,
        "Q_hw_delivered_kWh_yr": Q_delivered_kWh_yr,
        "Q_hw_purchased_kWh_yr": Q_purchased_kWh_yr,
    }


# -------------------------
# 1.3 Lighting & Appliances
# -------------------------

def lighting_appliances_kwh_per_year(
    # Lighting
    n_lights: int,
    lighting_type: str,
    lighting_hours_per_day: float,
    lamp_watt_override: float | None,
    # Washing machine
    has_washer: bool,
    wash_cycles_per_week: float,
    wash_kwh_per_cycle: float,
    # Dishwasher
    has_dishwasher: bool,
    dish_cycles_per_week: float,
    dish_kwh_per_cycle: float,
    # Cooking
    cooking_method: str,  # "Meals/week" or "Hours/day"
    meals_per_week: float,
    cook_kwh_per_meal: float,
    cook_power_kW: float,
    cook_hours_per_day: float,
) -> dict:
    """
    Spec 1.3.4 Calculation Logic
    Lighting:
      Q_lighting = (n × W × hours/day × 365) / 1000
    Washing:
      Q_wash = cycles/week × kWh/cycle × 52
    Dishwasher:
      Q_dish = cycles/week × kWh/cycle × 52
    Cooking (two UI methods allowed by spec):
      Meals/week: Q_cook = meals/week × kWh/meal × 52
      Hours/day:  Q_cook = power(kW) × hours/day × 365
    Total:
      Q_other = Q_lighting + Q_wash + Q_dish + Q_cook
    """
    n = int(max(n_lights, 0))
    hrs = _clamp_nonneg(lighting_hours_per_day)

    if lamp_watt_override is None:
        watt = _clamp_nonneg(DEFAULTS_OTHER["lamp_watt_by_type"].get(lighting_type, 9.0))
    else:
        watt = _clamp_nonneg(lamp_watt_override)

    Q_lighting = (n * watt * hrs * 365.0) / 1000.0

    Q_wash = 0.0
    if has_washer:
        Q_wash = _clamp_nonneg(wash_cycles_per_week) * _clamp_nonneg(wash_kwh_per_cycle) * 52.0

    Q_dish = 0.0
    if has_dishwasher:
        Q_dish = _clamp_nonneg(dish_cycles_per_week) * _clamp_nonneg(dish_kwh_per_cycle) * 52.0

    if cooking_method == "Hours/day":
        Q_cook = _clamp_nonneg(cook_power_kW) * _clamp_nonneg(cook_hours_per_day) * 365.0
    else:
        Q_cook = _clamp_nonneg(meals_per_week) * _clamp_nonneg(cook_kwh_per_meal) * 52.0

    Q_other = Q_lighting + Q_wash + Q_dish + Q_cook

    return {
        "Q_lighting_kWh_yr": Q_lighting,
        "Q_wash_kWh_yr": Q_wash,
        "Q_dish_kWh_yr": Q_dish,
        "Q_cook_kWh_yr": Q_cook,
        "Q_other_kWh_yr": Q_other,
        "lamp_watt_used_W": watt,
    }


# -------------------------
# 2. Water Consumption
# -------------------------

def water_consumption_L_per_year(
    occupants: int,
    # Toilets
    toilet_type: str,  # "Standard" or "Dual flush"
    flushes_per_person_day: float,
    L_per_flush_override: float | None,
    # Showers
    shower_type: str,  # "Standard" or "Low-flow"
    showers_per_person_day: float,
    minutes_per_shower: float,
    shower_flow_override_L_min: float | None,
    # Taps
    tap_efficiency: str,  # "Standard" or "Efficient"
    taps_L_per_person_day_override: float | None,
    # Washing machine
    has_washer: bool,
    wash_cycles_per_week: float,
    wash_L_per_cycle: float,
    # Dishwasher
    has_dishwasher: bool,
    dish_cycles_per_week: float,
    dish_L_per_cycle: float,
) -> dict:
    """
    Spec 2.3 Calculation Logic
    V_toilet     = occupants × flushes/day × L/flush × 365
    V_shower     = occupants × showers/day × minutes × flow rate × 365
    V_taps       = occupants × L/person/day × 365
    V_laundry    = cycles/week × L/cycle × 52
    V_dishwasher = cycles/week × L/cycle × 52
    V_total = sum(...)
    """
    n = int(max(occupants, 0))

    # Toilet
    if L_per_flush_override is None:
        L_flush = DEFAULTS_WATER["L_per_flush"].get(toilet_type, 6.0)
    else:
        L_flush = L_per_flush_override
    V_toilet = n * _clamp_nonneg(flushes_per_person_day) * _clamp_nonneg(L_flush) * 365.0

    # Shower
    if shower_flow_override_L_min is None:
        flow = DEFAULTS_WATER["shower_flow_L_min"].get(shower_type, 9.0)
    else:
        flow = shower_flow_override_L_min
    V_shower = n * _clamp_nonneg(showers_per_person_day) * _clamp_nonneg(minutes_per_shower) * _clamp_nonneg(flow) * 365.0

    # Taps
    if taps_L_per_person_day_override is None:
        taps_Lpd = DEFAULTS_WATER["taps_L_per_person_day"].get(tap_efficiency, 30.0)
    else:
        taps_Lpd = taps_L_per_person_day_override
    V_taps = n * _clamp_nonneg(taps_Lpd) * 365.0

    # Laundry
    V_laundry = 0.0
    if has_washer:
        V_laundry = _clamp_nonneg(wash_cycles_per_week) * _clamp_nonneg(wash_L_per_cycle) * 52.0

    # Dishwasher
    V_dishwasher = 0.0
    if has_dishwasher:
        V_dishwasher = _clamp_nonneg(dish_cycles_per_week) * _clamp_nonneg(dish_L_per_cycle) * 52.0

    V_total = V_toilet + V_shower + V_taps + V_laundry + V_dishwasher

    return {
        "V_toilet_L_yr": V_toilet,
        "V_shower_L_yr": V_shower,
        "V_taps_L_yr": V_taps,
        "V_laundry_L_yr": V_laundry,
        "V_dishwasher_L_yr": V_dishwasher,
        "V_total_L_yr": V_total,
        "L_flush_used": _clamp_nonneg(L_flush),
        "shower_flow_used_L_min": _clamp_nonneg(flow),
        "taps_Lpd_used": _clamp_nonneg(taps_Lpd),
    }


# -------------------------
# 3. Operational Carbon
# -------------------------

def operational_carbon_kgCO2e_per_year(
    electricity_kWh_yr: float,
    water_L_yr: float,
    grid_kgCO2e_per_kWh: float,
    water_kgCO2e_per_m3: float,
) -> dict:
    """
    Spec 3.2 Calculation Logic
    CO2_electricity = kWh × EF_grid
    CO2_water       = (L/1000) × EF_water  (since 1000 L = 1 m³)
    CO2_operational = sum
    """
    E = _clamp_nonneg(electricity_kWh_yr)
    V_m3 = _clamp_nonneg(water_L_yr) / 1000.0

    CO2_el = E * _clamp_nonneg(grid_kgCO2e_per_kWh)
    CO2_w  = V_m3 * _clamp_nonneg(water_kgCO2e_per_m3)
    CO2_total = CO2_el + CO2_w

    return {
        "CO2_electricity_kg_yr": CO2_el,
        "CO2_water_kg_yr": CO2_w,
        "CO2_operational_kg_yr": CO2_total,
    }


# -------------------------
# 4. Costs
# -------------------------

def operating_costs_NZD_per_year(
    electricity_kWh_yr: float,
    water_L_yr: float,
    electricity_tariff_NZD_per_kWh: float,
    water_tariff_NZD_per_m3: float,
) -> dict:
    """
    Spec 4.2 Operating Costs
    Cost_electricity = kWh × tariff
    Cost_water       = (L/1000) × tariff(m³)
    Cost_operating   = sum
    """
    E = _clamp_nonneg(electricity_kWh_yr)
    V_m3 = _clamp_nonneg(water_L_yr) / 1000.0

    cost_el = E * _clamp_nonneg(electricity_tariff_NZD_per_kWh)
    cost_w  = V_m3 * _clamp_nonneg(water_tariff_NZD_per_m3)
    cost_total = cost_el + cost_w

    return {
        "Cost_electricity_NZD_yr": cost_el,
        "Cost_water_NZD_yr": cost_w,
        "Cost_operating_NZD_yr": cost_total,
    }


def upgrade_costs_incremental_NZD(
    # areas come from the same geometry used in space heating
    roof_area_m2: float,
    wall_area_m2: float,
    floor_area_m2: float,
    window_area_m2: float,
    # scenario deltas
    baseline: dict,
    option: dict,
    # incremental cost coefficients (Δcost...)
    d_cost_roof_per_m2: float,
    d_cost_wall_per_m2: float,
    d_cost_floor_per_m2: float,
    d_cost_window_per_m2: float,
    d_cost_heatpump_vs_electric: float,
    # fixture counts + deltas
    n_toilets: int,
    d_cost_dual_flush_each: float,
    n_showers: int,
    d_cost_lowflow_shower_each: float,
    n_taps: int,
    d_cost_aerator_each: float,
) -> dict:
    """
    Spec 4.3 Upgrade Costs (Incremental)

    Insulation:
      Cost_roof  = roof area × Δcost_roof/m²
      Cost_wall  = wall area × Δcost_wall/m²
      Cost_floor = floor area × Δcost_floor/m²

    Windows:
      Cost_windows = window area × Δcost_window/m²

    Heating system:
      Cost_heating = Δcost_heatpump_vs_electric  (only applies when moving electric->heat pump)

    Water fixtures:
      Cost_toilets = number × Δcost_dual_flush
      Cost_showers = number × Δcost_lowflow_shower
      Cost_taps    = number × Δcost_aerator

    Important: this function applies costs ONLY when the Option differs from the Baseline
    in the relevant selection (incremental vs baseline framing).
    """
    # Envelope change detection (minimal + transparent)
    roof_changed = float(option["R_roof"]) != float(baseline["R_roof"])
    wall_changed = float(option["R_wall"]) != float(baseline["R_wall"])
    floor_changed = float(option["R_floor"]) != float(baseline["R_floor"])
    window_changed = (float(option["U_window"]) != float(baseline["U_window"])) or (float(option["A_window"]) != float(baseline["A_window"]))

    cost_roof = _clamp_nonneg(roof_area_m2) * _clamp_nonneg(d_cost_roof_per_m2) if roof_changed else 0.0
    cost_wall = _clamp_nonneg(wall_area_m2) * _clamp_nonneg(d_cost_wall_per_m2) if wall_changed else 0.0
    cost_floor = _clamp_nonneg(floor_area_m2) * _clamp_nonneg(d_cost_floor_per_m2) if floor_changed else 0.0
    cost_windows = _clamp_nonneg(window_area_m2) * _clamp_nonneg(d_cost_window_per_m2) if window_changed else 0.0

    # Heating system incremental: only for electric resistance -> heat pump
    baseline_heat = baseline["heating_system"]
    option_heat = option["heating_system"]
    cost_heating = _clamp_nonneg(d_cost_heatpump_vs_electric) if (baseline_heat == "Electric resistance" and option_heat == "Heat pump") else 0.0

    # Fixture incremental: only when the option selects the more efficient type
    cost_toilets = 0.0
    if baseline["toilet_type"] != "Dual flush" and option["toilet_type"] == "Dual flush":
        cost_toilets = int(max(n_toilets, 0)) * _clamp_nonneg(d_cost_dual_flush_each)

    cost_showers = 0.0
    if baseline["shower_type"] != "Low-flow" and option["shower_type"] == "Low-flow":
        cost_showers = int(max(n_showers, 0)) * _clamp_nonneg(d_cost_lowflow_shower_each)

    cost_taps = 0.0
    if baseline["tap_efficiency"] != "Efficient" and option["tap_efficiency"] == "Efficient":
        cost_taps = int(max(n_taps, 0)) * _clamp_nonneg(d_cost_aerator_each)

    total = cost_roof + cost_wall + cost_floor + cost_windows + cost_heating + cost_toilets + cost_showers + cost_taps

    return {
        "Cost_roof_NZD": cost_roof,
        "Cost_wall_NZD": cost_wall,
        "Cost_floor_NZD": cost_floor,
        "Cost_windows_NZD": cost_windows,
        "Cost_heating_NZD": cost_heating,
        "Cost_toilets_NZD": cost_toilets,
        "Cost_showers_NZD": cost_showers,
        "Cost_taps_NZD": cost_taps,
        "Cost_upgrade_total_NZD": total,
    }


# =========================================================
# 2. SCENARIO WRAPPER (Compute all KPIs)
# =========================================================

def compute_scenario(inputs: dict) -> dict:
    # --- 1.1 Space heating ---
    sh = space_heating_kwh_per_year(
        floor_area_m2=inputs["floor_area_m2"],
        ceiling_height_m=inputs["ceiling_height_m"],
        windows_df=inputs["windows_df"],
        R_roof_m2K_W=inputs["R_roof"],
        R_wall_m2K_W=inputs["R_wall"],
        R_floor_m2K_W=inputs["R_floor"],
        U_window_W_m2K=inputs["U_window"],
        HDD_base18=inputs["HDD"],
        heating_system_type=inputs["heating_system"],
        heat_pump_COP=inputs["heat_pump_COP"],
    )

    # --- 1.2 Water heating ---
    wh = water_heating_kwh_per_year(
        occupants=inputs["occupants"],
        L_per_person_day=inputs["L_hotwater_per_person_day"],
        T_hot_C=inputs["T_hot_C"],
        T_cold_C=inputs["T_cold_C"],
        hot_water_system_type=inputs["hot_water_system"],
        COP_hw=inputs["COP_hw"],
    )

    # --- 1.3 Lighting & appliances ---
    other = lighting_appliances_kwh_per_year(
        n_lights=inputs["n_lights"],
        lighting_type=inputs["lighting_type"],
        lighting_hours_per_day=inputs["lighting_hours_per_day"],
        lamp_watt_override=inputs["lamp_watt_override"],
        has_washer=inputs["has_washer"],
        wash_cycles_per_week=inputs["wash_cycles_per_week"],
        wash_kwh_per_cycle=inputs["wash_kwh_per_cycle"],
        has_dishwasher=inputs["has_dishwasher"],
        dish_cycles_per_week=inputs["dish_cycles_per_week"],
        dish_kwh_per_cycle=inputs["dish_kwh_per_cycle"],
        cooking_method=inputs["cooking_method"],
        meals_per_week=inputs["meals_per_week"],
        cook_kwh_per_meal=inputs["cook_kwh_per_meal"],
        cook_power_kW=inputs["cook_power_kW"],
        cook_hours_per_day=inputs["cook_hours_per_day"],
    )

    # --- Total energy (Spec 1) ---
    E_space = sh["Q_space_purchased_kWh_yr"]
    E_hw = wh["Q_hw_purchased_kWh_yr"]
    E_other = other["Q_other_kWh_yr"]
    E_total = E_space + E_hw + E_other

    # --- 2 Water consumption ---
    water = water_consumption_L_per_year(
        occupants=inputs["occupants"],
        toilet_type=inputs["toilet_type"],
        flushes_per_person_day=inputs["flushes_per_person_day"],
        L_per_flush_override=inputs["L_per_flush_override"],
        shower_type=inputs["shower_type"],
        showers_per_person_day=inputs["showers_per_person_day"],
        minutes_per_shower=inputs["minutes_per_shower"],
        shower_flow_override_L_min=inputs["shower_flow_override_L_min"],
        tap_efficiency=inputs["tap_efficiency"],
        taps_L_per_person_day_override=inputs["taps_L_per_person_day_override"],
        has_washer=inputs["has_washer"],
        wash_cycles_per_week=inputs["wash_cycles_per_week"],
        wash_L_per_cycle=inputs["wash_L_per_cycle"],
        has_dishwasher=inputs["has_dishwasher"],
        dish_cycles_per_week=inputs["dish_cycles_per_week"],
        dish_L_per_cycle=inputs["dish_L_per_cycle"],
    )

    # --- 3 Operational carbon ---
    carbon = operational_carbon_kgCO2e_per_year(
        electricity_kWh_yr=E_total,
        water_L_yr=water["V_total_L_yr"],
        grid_kgCO2e_per_kWh=inputs["EF_grid"],
        water_kgCO2e_per_m3=inputs["EF_water"],
    )

    # --- 4 Operating costs ---
    opex = operating_costs_NZD_per_year(
        electricity_kWh_yr=E_total,
        water_L_yr=water["V_total_L_yr"],
        electricity_tariff_NZD_per_kWh=inputs["tariff_el"],
        water_tariff_NZD_per_m3=inputs["tariff_water"],
    )

    return {
        "space_heating": sh,
        "water_heating": wh,
        "other_loads": other,
        "energy_total_kWh_yr": E_total,
        "energy_breakdown_kWh_yr": {
            "space_heating_purchased": E_space,
            "water_heating_purchased": E_hw,
            "lighting_and_appliances": E_other,
        },
        "water": water,
        "carbon": carbon,
        "opex": opex,
    }


# =========================================================
# 3. UI (Baseline vs Option, defaults first, optional overrides)
# =========================================================

st.set_page_config(page_title="NZ Housing Sustainability Calculator (PoC)", layout="wide")

st.title("Homestar-Inspired Early-Stage Housing Sustainability Calculator (PoC)")
st.write(
    """
This is a **conceptual + computational model** for **relative comparison** of design choices.
It is **not** a certified assessment, compliance tool, or detailed simulation.
"""
)

def _default_windows_df():
    return pd.DataFrame(
        [
            {"label": "Typical window", "width_m": 1.2, "height_m": 1.0, "count": 8},
        ]
    )

def scenario_ui(prefix: str) -> dict:
    # -------------------------
    # Section A: Core inputs
    # -------------------------
    with st.expander(f"{prefix} — 1) Space heating (inputs)", expanded=True):
        colA, colB = st.columns(2)

        with colA:
            floor_area_m2 = st.number_input(
                "Floor area (m²)",
                min_value=20.0, max_value=600.0, value=120.0, step=5.0,
                key=f"{prefix}_floor_area_m2",
            )
            ceiling_height_m = st.number_input(
                "Ceiling height (m)",
                min_value=2.0, max_value=4.0, value=DEFAULTS_SPACE["ceiling_height_m"], step=0.1,
                key=f"{prefix}_ceiling_height_m",
            )

            hdd_mode = st.radio(
                "Heating Degree Days (HDD, base 18°C)",
                ["Use climate zone lookup", "Enter HDD manually"],
                index=0,
                key=f"{prefix}_hdd_mode",
            )

            if hdd_mode == "Use climate zone lookup":
                cz = st.selectbox(
                    "NZ climate zone (for HDD lookup)",
                    list(HDD_LOOKUP_BASE18.keys()),
                    index=2 if "Zone 3" in HDD_LOOKUP_BASE18 else 0,
                    key=f"{prefix}_climate_zone",
                )
                HDD = float(HDD_LOOKUP_BASE18[cz])
                st.caption(f"HDD used (base 18°C): **{HDD:,.0f}** (lookup placeholder table)")
            else:
                HDD = st.number_input(
                    "HDD (base 18°C)",
                    min_value=0.0, max_value=6000.0, value=float(DEFAULTS_SPACE["hdd_manual"]), step=50.0,
                    key=f"{prefix}_HDD_manual",
                )

        with colB:
            st.markdown("**Window typologies (derived window area)**")
            windows_df = st.data_editor(
                _default_windows_df(),
                num_rows="dynamic",
                use_container_width=True,
                key=f"{prefix}_windows_df",
            )
            st.caption("Window area is computed as Σ(width × height × count).")

            U_window = st.number_input(
                "Window U-value (W/m²·K)",
                min_value=0.5, max_value=6.0, value=DEFAULTS_SPACE["U_window_W_m2K"], step=0.1,
                key=f"{prefix}_U_window",
            )

    with st.expander(f"{prefix} — 1) Space heating (envelope + system)", expanded=False):
        col1, col2 = st.columns(2)
        with col1:
            R_roof = st.number_input(
                "Roof R-value (m²·K/W)",
                min_value=0.1, max_value=10.0, value=DEFAULTS_SPACE["R_roof_m2K_W"], step=0.1,
                key=f"{prefix}_R_roof",
            )
            R_wall = st.number_input(
                "Wall R-value (m²·K/W)",
                min_value=0.1, max_value=10.0, value=DEFAULTS_SPACE["R_wall_m2K_W"], step=0.1,
                key=f"{prefix}_R_wall",
            )
            R_floor = st.number_input(
                "Floor R-value (m²·K/W)",
                min_value=0.1, max_value=10.0, value=DEFAULTS_SPACE["R_floor_m2K_W"], step=0.1,
                key=f"{prefix}_R_floor",
            )

        with col2:
            heating_system = st.radio(
                "Heating system",
                ["Electric resistance", "Heat pump"],
                index=1,
                key=f"{prefix}_heating_system",
            )
            heat_pump_COP = DEFAULTS_SPACE["heat_pump_COP"]
            if heating_system == "Heat pump":
                heat_pump_COP = st.number_input(
                    "Heat pump COP",
                    min_value=1.0, max_value=6.0, value=DEFAULTS_SPACE["heat_pump_COP"], step=0.1,
                    key=f"{prefix}_heat_pump_COP",
                )
            else:
                st.caption("Electric resistance uses system efficiency η = 1.0 (no adjustment).")

    # -------------------------
    # Section B: Water heating
    # -------------------------
    with st.expander(f"{prefix} — 1.2 Water heating", expanded=False):
        occupants = st.number_input(
            "Household size (occupants)",
            min_value=1, max_value=10, value=3, step=1,
            key=f"{prefix}_occupants",
        )

        hot_water_system = st.radio(
            "Hot water system type",
            ["Electric storage", "Heat pump hot water"],
            index=0,
            key=f"{prefix}_hot_water_system",
        )

        with st.expander("Advanced (optional overrides)", expanded=False):
            L_hotwater_per_person_day = st.number_input(
                "Hot water demand (L/person/day)",
                min_value=0.0, max_value=300.0, value=DEFAULTS_WATER_HEATING["L_per_person_day"], step=5.0,
                key=f"{prefix}_L_hotwater_ppd",
            )
            T_hot_C = st.number_input(
                "Hot water setpoint (°C)",
                min_value=30.0, max_value=70.0, value=DEFAULTS_WATER_HEATING["T_hot_C"], step=1.0,
                key=f"{prefix}_T_hot",
            )
            T_cold_C = st.number_input(
                "Cold water inlet temperature (°C)",
                min_value=0.0, max_value=30.0, value=DEFAULTS_WATER_HEATING["T_cold_C"], step=1.0,
                key=f"{prefix}_T_cold",
            )
            COP_hw = DEFAULTS_WATER_HEATING["COP_heat_pump_hw"]
            if hot_water_system == "Heat pump hot water":
                COP_hw = st.number_input(
                    "Heat pump hot water COP",
                    min_value=1.0, max_value=6.0, value=DEFAULTS_WATER_HEATING["COP_heat_pump_hw"], step=0.1,
                    key=f"{prefix}_COP_hw",
                )
            else:
                COP_hw = 1.0

        # If user does not open advanced, still use defaults
        if f"{prefix}_L_hotwater_ppd" not in st.session_state:
            L_hotwater_per_person_day = DEFAULTS_WATER_HEATING["L_per_person_day"]
            T_hot_C = DEFAULTS_WATER_HEATING["T_hot_C"]
            T_cold_C = DEFAULTS_WATER_HEATING["T_cold_C"]
            COP_hw = DEFAULTS_WATER_HEATING["COP_heat_pump_hw"] if hot_water_system == "Heat pump hot water" else 1.0

    # -------------------------
    # Section C: Lighting & Appliances
    # -------------------------
    with st.expander(f"{prefix} — 1.3 Lighting & appliances", expanded=False):
        st.markdown("**Lighting**")
        colL1, colL2, colL3 = st.columns(3)
        with colL1:
            n_lights = st.number_input(
                "Number of lights",
                min_value=0, max_value=200, value=20, step=1,
                key=f"{prefix}_n_lights",
            )
        with colL2:
            lighting_type = st.selectbox(
                "Lighting type",
                list(DEFAULTS_OTHER["lamp_watt_by_type"].keys()),
                index=0,
                key=f"{prefix}_lighting_type",
            )
        with colL3:
            lighting_hours_per_day = st.number_input(
                "Average lighting hours/day",
                min_value=0.0, max_value=24.0, value=DEFAULTS_OTHER["lighting_hours_per_day"], step=0.5,
                key=f"{prefix}_lighting_hours",
            )

        with st.expander("Advanced (optional lamp watt override)", expanded=False):
            lamp_watt_override = st.number_input(
                "Lamp wattage (W per light) — override",
                min_value=0.0, max_value=200.0,
                value=float(DEFAULTS_OTHER["lamp_watt_by_type"][lighting_type]),
                step=1.0,
                key=f"{prefix}_lamp_watt_override",
            )

        # Washer
        st.markdown("**Washing machine**")
        has_washer = st.checkbox("Has washing machine", value=True, key=f"{prefix}_has_washer")
        colW1, colW2 = st.columns(2)
        with colW1:
            wash_cycles_per_week = st.number_input(
                "Cycles per week",
                min_value=0.0, max_value=30.0, value=4.0, step=1.0,
                key=f"{prefix}_wash_cycles",
            )
        with colW2:
            wash_kwh_per_cycle = st.number_input(
                "Energy per cycle (kWh/cycle)",
                min_value=0.0, max_value=10.0, value=DEFAULTS_OTHER["wash_kwh_per_cycle"], step=0.1,
                key=f"{prefix}_wash_kwh_cycle",
            )

        # Dishwasher
        st.markdown("**Dishwasher**")
        has_dishwasher = st.checkbox("Has dishwasher", value=False, key=f"{prefix}_has_dishwasher")
        colD1, colD2 = st.columns(2)
        with colD1:
            dish_cycles_per_week = st.number_input(
                "Cycles per week",
                min_value=0.0, max_value=30.0, value=3.0, step=1.0,
                key=f"{prefix}_dish_cycles",
            )
        with colD2:
            dish_kwh_per_cycle = st.number_input(
                "Energy per cycle (kWh/cycle)",
                min_value=0.0, max_value=10.0, value=DEFAULTS_OTHER["dish_kwh_per_cycle"], step=0.1,
                key=f"{prefix}_dish_kwh_cycle",
            )

        # Cooking
        st.markdown("**Cooking (electric)**")
        cooking_method = st.radio(
            "Cooking input method",
            ["Meals/week", "Hours/day"],
            index=0,
            key=f"{prefix}_cooking_method",
        )
        colC1, colC2 = st.columns(2)
        if cooking_method == "Meals/week":
            with colC1:
                meals_per_week = st.number_input(
                    "Meals per week",
                    min_value=0.0, max_value=100.0, value=14.0, step=1.0,
                    key=f"{prefix}_meals_week",
                )
            with colC2:
                cook_kwh_per_meal = st.number_input(
                    "Energy per meal (kWh/meal)",
                    min_value=0.0, max_value=10.0, value=DEFAULTS_OTHER["cook_kwh_per_meal"], step=0.1,
                    key=f"{prefix}_cook_kwh_meal",
                )
            cook_power_kW = DEFAULTS_OTHER["cook_power_kW"]
            cook_hours_per_day = 0.0
        else:
            with colC1:
                cook_power_kW = st.number_input(
                    "Cooking power rating (kW)",
                    min_value=0.0, max_value=10.0, value=DEFAULTS_OTHER["cook_power_kW"], step=0.1,
                    key=f"{prefix}_cook_power",
                )
            with colC2:
                cook_hours_per_day = st.number_input(
                    "Cooking hours per day",
                    min_value=0.0, max_value=6.0, value=1.0, step=0.1,
                    key=f"{prefix}_cook_hours",
                )
            meals_per_week = 0.0
            cook_kwh_per_meal = DEFAULTS_OTHER["cook_kwh_per_meal"]

    # -------------------------
    # Section D: Water consumption (L/year)
    # -------------------------
    with st.expander(f"{prefix} — 2) Water consumption", expanded=False):
        st.markdown("**Toilets**")
        toilet_type = st.selectbox("Toilet type", ["Standard", "Dual flush"], index=1, key=f"{prefix}_toilet_type")
        flushes_per_person_day = st.number_input(
            "Flushes per person per day",
            min_value=0.0, max_value=20.0, value=DEFAULTS_WATER["flushes_per_person_day"], step=0.5,
            key=f"{prefix}_flushes_ppd",
        )
        with st.expander("Advanced (optional overrides)", expanded=False):
            L_per_flush_override = st.number_input(
                "Litres per flush — override",
                min_value=0.0, max_value=20.0, value=float(DEFAULTS_WATER["L_per_flush"][toilet_type]), step=0.5,
                key=f"{prefix}_L_per_flush_override",
            )

        st.markdown("**Showers**")
        shower_type = st.selectbox("Shower type", ["Standard", "Low-flow"], index=0, key=f"{prefix}_shower_type")
        colS1, colS2 = st.columns(2)
        with colS1:
            showers_per_person_day = st.number_input(
                "Showers per person per day",
                min_value=0.0, max_value=5.0, value=DEFAULTS_WATER["showers_per_person_day"], step=0.1,
                key=f"{prefix}_showers_ppd",
            )
        with colS2:
            minutes_per_shower = st.number_input(
                "Minutes per shower",
                min_value=0.0, max_value=60.0, value=DEFAULTS_WATER["minutes_per_shower"], step=1.0,
                key=f"{prefix}_minutes_shower",
            )
        with st.expander("Advanced (optional overrides)", expanded=False):
            shower_flow_override_L_min = st.number_input(
                "Shower flow rate (L/min) — override",
                min_value=0.0, max_value=30.0, value=float(DEFAULTS_WATER["shower_flow_L_min"][shower_type]), step=0.5,
                key=f"{prefix}_shower_flow_override",
            )

        st.markdown("**Taps**")
        tap_efficiency = st.selectbox("Tap efficiency", ["Standard", "Efficient"], index=0, key=f"{prefix}_tap_eff")
        with st.expander("Advanced (optional overrides)", expanded=False):
            taps_L_per_person_day_override = st.number_input(
                "Taps water use (L/person/day) — override",
                min_value=0.0, max_value=200.0, value=float(DEFAULTS_WATER["taps_L_per_person_day"][tap_efficiency]), step=1.0,
                key=f"{prefix}_taps_Lpd_override",
            )

        st.markdown("**Washing machine water**")
        wash_L_per_cycle = st.number_input(
            "Water per wash cycle (L/cycle)",
            min_value=0.0, max_value=300.0, value=DEFAULTS_WATER["wash_L_per_cycle"], step=5.0,
            key=f"{prefix}_wash_L_cycle",
        )

        st.markdown("**Dishwasher water**")
        dish_L_per_cycle = st.number_input(
            "Water per dishwasher cycle (L/cycle)",
            min_value=0.0, max_value=100.0, value=DEFAULTS_WATER["dish_L_per_cycle"], step=1.0,
            key=f"{prefix}_dish_L_cycle",
        )

    # -------------------------
    # Section E: Carbon + tariffs (defaults first)
    # -------------------------
    with st.expander(f"{prefix} — 3 & 4) Carbon factors and tariffs", expanded=False):
        with st.expander("Advanced (optional overrides)", expanded=False):
            EF_grid = st.number_input(
                "Grid emission factor (kgCO₂e/kWh)",
                min_value=0.0, max_value=1.0, value=DEFAULTS_CARBON["grid_kgCO2e_per_kWh"], step=0.01,
                key=f"{prefix}_EF_grid",
            )
            EF_water = st.number_input(
                "Water emission factor (kgCO₂e/m³)",
                min_value=0.0, max_value=5.0, value=DEFAULTS_CARBON["water_kgCO2e_per_m3"], step=0.05,
                key=f"{prefix}_EF_water",
            )
            tariff_el = st.number_input(
                "Electricity tariff (NZD/kWh)",
                min_value=0.0, max_value=2.0, value=DEFAULTS_TARIFFS["electricity_NZD_per_kWh"], step=0.01,
                key=f"{prefix}_tariff_el",
            )
            tariff_water = st.number_input(
                "Water tariff (NZD/m³)",
                min_value=0.0, max_value=20.0, value=DEFAULTS_TARIFFS["water_NZD_per_m3"], step=0.10,
                key=f"{prefix}_tariff_water",
            )

        # If user doesn't open advanced, still use defaults
        if f"{prefix}_EF_grid" not in st.session_state:
            EF_grid = DEFAULTS_CARBON["grid_kgCO2e_per_kWh"]
            EF_water = DEFAULTS_CARBON["water_kgCO2e_per_m3"]
            tariff_el = DEFAULTS_TARIFFS["electricity_NZD_per_kWh"]
            tariff_water = DEFAULTS_TARIFFS["water_NZD_per_m3"]

    # Build input dict (only what model needs)
    return {
        # Space heating
        "floor_area_m2": float(floor_area_m2),
        "ceiling_height_m": float(ceiling_height_m),
        "windows_df": windows_df,
        "R_roof": float(R_roof),
        "R_wall": float(R_wall),
        "R_floor": float(R_floor),
        "U_window": float(U_window),
        "HDD": float(HDD),
        "heating_system": heating_system,
        "heat_pump_COP": float(heat_pump_COP),
        # Water heating
        "occupants": int(occupants),
        "hot_water_system": hot_water_system,
        "L_hotwater_per_person_day": float(L_hotwater_per_person_day),
        "T_hot_C": float(T_hot_C),
        "T_cold_C": float(T_cold_C),
        "COP_hw": float(COP_hw),
        # Lighting & appliances
        "n_lights": int(n_lights),
        "lighting_type": lighting_type,
        "lighting_hours_per_day": float(lighting_hours_per_day),
        "lamp_watt_override": float(lamp_watt_override) if f"{prefix}_lamp_watt_override" in st.session_state else None,
        "has_washer": bool(has_washer),
        "wash_cycles_per_week": float(wash_cycles_per_week),
        "wash_kwh_per_cycle": float(wash_kwh_per_cycle),
        "has_dishwasher": bool(has_dishwasher),
        "dish_cycles_per_week": float(dish_cycles_per_week),
        "dish_kwh_per_cycle": float(dish_kwh_per_cycle),
        "cooking_method": cooking_method,
        "meals_per_week": float(meals_per_week),
        "cook_kwh_per_meal": float(cook_kwh_per_meal),
        "cook_power_kW": float(cook_power_kW),
        "cook_hours_per_day": float(cook_hours_per_day),
        # Water consumption
        "toilet_type": toilet_type,
        "flushes_per_person_day": float(flushes_per_person_day),
        "L_per_flush_override": float(L_per_flush_override) if f"{prefix}_L_per_flush_override" in st.session_state else None,
        "shower_type": shower_type,
        "showers_per_person_day": float(showers_per_person_day),
        "minutes_per_shower": float(minutes_per_shower),
        "shower_flow_override_L_min": float(shower_flow_override_L_min) if f"{prefix}_shower_flow_override" in st.session_state else None,
        "tap_efficiency": tap_efficiency,
        "taps_L_per_person_day_override": float(taps_L_per_person_day_override) if f"{prefix}_taps_Lpd_override" in st.session_state else None,
        "wash_L_per_cycle": float(wash_L_per_cycle),
        "dish_L_per_cycle": float(dish_L_per_cycle),
        # Carbon + tariffs
        "EF_grid": float(EF_grid),
        "EF_water": float(EF_water),
        "tariff_el": float(tariff_el),
        "tariff_water": float(tariff_water),
    }


# =========================================================
# 4. APP LAYOUT: Baseline vs Option + Results
# =========================================================

col1, col2, col3 = st.columns([1.05, 1.05, 1.25])

with col1:
    st.header("Baseline")
    baseline_inputs = scenario_ui("Baseline")

with col2:
    st.header("Option")
    option_inputs = scenario_ui("Option")

baseline = compute_scenario(baseline_inputs)
option = compute_scenario(option_inputs)

# -------------------------
# Upgrade costs (incremental) + payback
# -------------------------
with col3:
    st.header("Results")

    # Key headline KPIs
    E_base = baseline["energy_total_kWh_yr"]
    E_opt = option["energy_total_kWh_yr"]
    V_base = baseline["water"]["V_total_L_yr"]
    V_opt = option["water"]["V_total_L_yr"]
    CO2_base = baseline["carbon"]["CO2_operational_kg_yr"]
    CO2_opt = option["carbon"]["CO2_operational_kg_yr"]
    Cost_base = baseline["opex"]["Cost_operating_NZD_yr"]
    Cost_opt = option["opex"]["Cost_operating_NZD_yr"]

    st.subheader("Key KPIs (Option with delta vs Baseline)")
    st.metric("Total energy (kWh/year)", f"{E_opt:,.0f}", f"{E_opt - E_base:,.0f}", delta_color="inverse")
    st.metric("Water use (L/year)", f"{V_opt:,.0f}", f"{V_opt - V_base:,.0f}", delta_color="inverse")
    st.metric("Operational carbon (kgCO₂e/year)", f"{CO2_opt:,.0f}", f"{CO2_opt - CO2_base:,.0f}", delta_color="inverse")
    st.metric("Operating cost (NZD/year)", f"{Cost_opt:,.0f}", f"{Cost_opt - Cost_base:,.0f}", delta_color="inverse")

    st.subheader("Energy breakdown (purchased kWh/year)")
    bd = pd.DataFrame(
        {
            "Baseline": baseline["energy_breakdown_kWh_yr"],
            "Option": option["energy_breakdown_kWh_yr"],
        }
    )
    st.dataframe(bd, use_container_width=True)

    with st.expander("Space heating details"):
        shb = baseline["space_heating"]
        sho = option["space_heating"]
        st.write(f"H (W/K): {shb['H_W_per_K']:.1f} → {sho['H_W_per_K']:.1f}")
        st.write(f"Delivered (kWh/yr): {shb['Q_space_delivered_kWh_yr']:.0f} → {sho['Q_space_delivered_kWh_yr']:.0f}")
        st.write(f"Purchased (kWh/yr): {shb['Q_space_purchased_kWh_yr']:.0f} → {sho['Q_space_purchased_kWh_yr']:.0f}")
        g = shb["space_geom"]
        st.write(
            f"Areas (m²): roof {g['A_roof_m2']:.1f}, wall gross {g['A_wall_gross_m2']:.1f}, "
            f"wall opaque {g['A_wall_opaque_m2']:.1f}, window {g['A_window_m2']:.1f}"
        )

    with st.expander("Water heating details"):
        whb = baseline["water_heating"]
        who = option["water_heating"]
        st.write(f"Annual hot water volume (L/yr): {whb['V_hotwater_annual_L_yr']:.0f} → {who['V_hotwater_annual_L_yr']:.0f}")
        st.write(f"ΔT (°C): {whb['dT_C']:.1f} → {who['dT_C']:.1f}")
        st.write(f"Delivered (kWh/yr): {whb['Q_hw_delivered_kWh_yr']:.0f} → {who['Q_hw_delivered_kWh_yr']:.0f}")
        st.write(f"Purchased (kWh/yr): {whb['Q_hw_purchased_kWh_yr']:.0f} → {who['Q_hw_purchased_kWh_yr']:.0f}")

    with st.expander("Water breakdown (L/year)"):
        wb = pd.DataFrame(
            {
                "Baseline": {k: v for k, v in baseline["water"].items() if k.endswith("_L_yr")},
                "Option": {k: v for k, v in option["water"].items() if k.endswith("_L_yr")},
            }
        )
        st.dataframe(wb, use_container_width=True)

    # Upgrade costs (incremental) & payback
    st.subheader("Upgrade costs (incremental vs Baseline) + simple payback")

    with st.expander("Upgrade cost assumptions (Δcost inputs)", expanded=False):
        colC1, colC2 = st.columns(2)
        with colC1:
            d_cost_roof_per_m2 = st.number_input("Δcost roof insulation (NZD/m²)", 0.0, 500.0, DEFAULTS_UPGRADE_COSTS["d_cost_roof_per_m2"], 5.0)
            d_cost_wall_per_m2 = st.number_input("Δcost wall insulation (NZD/m²)", 0.0, 500.0, DEFAULTS_UPGRADE_COSTS["d_cost_wall_per_m2"], 5.0)
            d_cost_floor_per_m2 = st.number_input("Δcost floor insulation (NZD/m²)", 0.0, 500.0, DEFAULTS_UPGRADE_COSTS["d_cost_floor_per_m2"], 5.0)
            d_cost_window_per_m2 = st.number_input("Δcost windows (NZD/m²)", 0.0, 1500.0, DEFAULTS_UPGRADE_COSTS["d_cost_window_per_m2"], 10.0)
        with colC2:
            d_cost_heatpump_vs_electric = st.number_input("Δcost heat pump vs electric (NZD)", 0.0, 30000.0, DEFAULTS_UPGRADE_COSTS["d_cost_heatpump_vs_electric"], 250.0)

            n_toilets = st.number_input("Number of toilets", 0, 10, 2, 1)
            d_cost_dual_flush_each = st.number_input("Δcost dual flush toilet (NZD each)", 0.0, 2000.0, DEFAULTS_UPGRADE_COSTS["d_cost_dual_flush_each"], 25.0)

            n_showers = st.number_input("Number of showers", 0, 10, 1, 1)
            d_cost_lowflow_shower_each = st.number_input("Δcost low-flow shower (NZD each)", 0.0, 2000.0, DEFAULTS_UPGRADE_COSTS["d_cost_lowflow_shower_each"], 25.0)

            n_taps = st.number_input("Number of taps", 0, 30, 6, 1)
            d_cost_aerator_each = st.number_input("Δcost tap aerator (NZD each)", 0.0, 200.0, DEFAULTS_UPGRADE_COSTS["d_cost_aerator_each"], 5.0)

    # Areas from baseline geometry (consistent reference for incremental costs)
    geom_base = baseline["space_heating"]["space_geom"]
    roof_area = geom_base["A_roof_m2"]
    wall_area = geom_base["A_wall_opaque_m2"]
    floor_area = geom_base["A_floor_m2"]
    window_area = geom_base["A_window_m2"]

    baseline_cost_context = {
        "R_roof": baseline_inputs["R_roof"],
        "R_wall": baseline_inputs["R_wall"],
        "R_floor": baseline_inputs["R_floor"],
        "U_window": baseline_inputs["U_window"],
        "A_window": float(geom_base["A_window_m2"]),
        "heating_system": baseline_inputs["heating_system"],
        "toilet_type": baseline_inputs["toilet_type"],
        "shower_type": baseline_inputs["shower_type"],
        "tap_efficiency": baseline_inputs["tap_efficiency"],
    }
    geom_opt = option["space_heating"]["space_geom"]
    option_cost_context = {
        "R_roof": option_inputs["R_roof"],
        "R_wall": option_inputs["R_wall"],
        "R_floor": option_inputs["R_floor"],
        "U_window": option_inputs["U_window"],
        "A_window": float(geom_opt["A_window_m2"]),
        "heating_system": option_inputs["heating_system"],
        "toilet_type": option_inputs["toilet_type"],
        "shower_type": option_inputs["shower_type"],
        "tap_efficiency": option_inputs["tap_efficiency"],
    }

    capex = upgrade_costs_incremental_NZD(
        roof_area_m2=roof_area,
        wall_area_m2=wall_area,
        floor_area_m2=floor_area,
        window_area_m2=window_area,
        baseline=baseline_cost_context,
        option=option_cost_context,
        d_cost_roof_per_m2=d_cost_roof_per_m2,
        d_cost_wall_per_m2=d_cost_wall_per_m2,
        d_cost_floor_per_m2=d_cost_floor_per_m2,
        d_cost_window_per_m2=d_cost_window_per_m2,
        d_cost_heatpump_vs_electric=d_cost_heatpump_vs_electric,
        n_toilets=n_toilets,
        d_cost_dual_flush_each=d_cost_dual_flush_each,
        n_showers=n_showers,
        d_cost_lowflow_shower_each=d_cost_lowflow_shower_each,
        n_taps=n_taps,
        d_cost_aerator_each=d_cost_aerator_each,
    )

    st.write(f"Incremental upgrade cost (NZD): **{capex['Cost_upgrade_total_NZD']:,.0f}**")

    annual_savings = max(Cost_base - Cost_opt, 0.0)
    if capex["Cost_upgrade_total_NZD"] > 0 and annual_savings > 0:
        payback_years = capex["Cost_upgrade_total_NZD"] / annual_savings
        st.write(f"Simple payback (years) = upgrade cost / annual operating savings: **{payback_years:.1f}**")
    else:
        st.write("Simple payback: **N/A** (requires upgrade cost > 0 and annual savings > 0)")

    with st.expander("Upgrade cost breakdown"):
        st.json(capex)

st.info(
    "All outputs are indicative and intended for early-stage comparison only. "
    "Defaults and lookup coefficients are designed to be transparent and editable."
)
