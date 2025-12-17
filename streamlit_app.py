# app.py
import copy
import json
import math
import hashlib
from datetime import datetime

import pandas as pd
import streamlit as st
import plotly.express as px

# =============================================================================
# CONFIG
# =============================================================================
st.set_page_config(page_title="NZ Housing Sustainability Calculator (Prototype)", layout="wide")

PLACEHOLDER = "— Select —"

# =============================================================================
# DUMMY COEFFICIENTS (PLACEHOLDERS)
# =============================================================================

# DUMMY: NZ Climate Zones Heating Degree Days (base 18°C)
HDD_LOOKUP_BASE18 = {
    "Zone 1 (Warmest - e.g., Northland)": 1200,
    "Zone 2 (Warm - e.g., Auckland)": 1600,
    "Zone 3 (Mild - e.g., Wellington)": 2000,
    "Zone 4 (Cool - e.g., Christchurch)": 2400,
    "Zone 5 (Cold - e.g., Queenstown)": 2800,
    "Zone 6 (Coldest - e.g., Central Otago)": 3200,
}

# DUMMY: Default R-values and U-values
R_VALUES_ROOF = {
    "Uninsulated": 0.5,
    "Basic (R2.0)": 2.0,
    "Code minimum (R3.3)": 3.3,
    "Good (R4.6)": 4.6,
    "Excellent (R6.0)": 6.0,
}

R_VALUES_WALLS = {
    "Uninsulated": 0.5,
    "Basic (R1.5)": 1.5,
    "Code minimum (R2.0)": 2.0,
    "Good (R2.8)": 2.8,
    "Excellent (R4.0)": 4.0,
}

R_VALUES_FLOOR = {
    "Uninsulated": 0.5,
    "Basic (R1.3)": 1.3,
    "Code minimum (R2.0)": 2.0,
    "Good (R3.0)": 3.0,
    "Excellent (R4.0)": 4.0,
}

U_VALUES_WINDOWS = {
    "Single glazed": 5.8,
    "Standard double glazed": 3.0,
    "Low-E double glazed": 2.0,
    "High performance triple": 1.0,
}

# DUMMY: Heating system efficiencies
HEATING_SYSTEMS = {
    "None": 0,
    "Electric resistance": 1.0,
    "Heat pump (COP 3.0)": 3.0,
    "Heat pump (COP 4.0)": 4.0,
}

# DUMMY: Hot water system efficiencies
WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder": 1.0,
    "Heat pump hot water (COP 2.5)": 2.5,
    "Heat pump hot water (COP 3.0)": 3.0,
}

# DUMMY: Water fixtures
TOILET_TYPES = {
    "Single flush (9L)": 9.0,
    "Dual flush standard (6/3L avg 5L)": 5.0,
    "Dual flush efficient (4.5/3L avg 4L)": 4.0,
}

SHOWER_TYPES = {
    "Standard (9 L/min)": 9.0,
    "Low-flow (7 L/min)": 7.0,
    "Efficient (6 L/min)": 6.0,
}

TAP_TYPES = {
    "Standard (8 L/min)": 8.0,
    "Efficient (6 L/min)": 6.0,
    "Very efficient (4 L/min)": 4.0,
}

# DUMMY: Appliance defaults (numeric defaults are OK)
WASHING_MACHINE_DEFAULTS = {"cyclesPerWeek": 4, "energyPerCycle": 0.8, "waterPerCycle": 60}
DISHWASHER_DEFAULTS = {"cyclesPerWeek": 4, "energyPerCycle": 1.0, "waterPerCycle": 12}
COOKING_DEFAULTS = {"mealsPerWeek": 14, "energyPerMeal": 0.5}
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}

# DUMMY: Grid emission factor and tariff
GRID_EMISSION_FACTOR = 0.10  # kgCO2/kWh - DUMMY
ELECTRICITY_TARIFF = 0.30    # NZD/kWh - DUMMY
WATER_TARIFF = 2.50          # NZD/m³ - DUMMY
WATER_EMISSION_FACTOR = 0.63 # kgCO2/m³ - DUMMY

# =============================================================================
# CALCULATION FUNCTIONS (per spec)
# =============================================================================

def calculate_space_heating(inputs: dict) -> dict:
    """
    Spec 1.1: Steady-state heat loss + HDD conversion.
    """
    HDD = HDD_LOOKUP_BASE18[inputs["climateZone"]]

    # Convert R to U
    roofU = 1.0 / inputs["roofRValue"]
    wallU = 1.0 / inputs["wallRValue"]
    floorU = 1.0 / inputs["floorRValue"]

    # Areas (simplified square footprint)
    floorArea = inputs["floorArea"]
    ceilingHeight = inputs["ceilingHeight"]
    windowArea = inputs["windowArea"]
    roofArea = floorArea
    perimeter = 4.0 * math.sqrt(floorArea)
    wallArea = perimeter * ceilingHeight - windowArea
    floorAreaCalc = floorArea

    # Heat loss coefficient H (W/K)
    H_roof = roofArea * roofU
    H_wall = wallArea * wallU
    H_floor = floorAreaCalc * floorU
    H_window = windowArea * inputs["windowUValue"]
    H_total = H_roof + H_wall + H_floor + H_window

    # Annual heating demand (delivered), kWh/year
    Q_delivered = (H_total * HDD * 24.0) / 1000.0

    # Purchased energy (adjust for COP/efficiency)
    eff = inputs["heatingSystemEfficiency"]
    Q_purchased = (Q_delivered / eff) if eff and eff > 0 else 0.0

    return {
        "Q_delivered": Q_delivered,
        "Q_purchased": Q_purchased,
        "H_total": H_total,
        "breakdown": {"H_roof": H_roof, "H_wall": H_wall, "H_floor": H_floor, "H_window": H_window},
    }

def calculate_water_heating(inputs: dict, advanced: dict) -> dict:
    """
    Spec 1.2: Volume × ΔT × cp.
    """
    householdSize = inputs["householdSize"]
    L_per_person_day = advanced["hotWaterPerPersonPerDay"]
    T_hot = advanced["hotWaterTemp"]
    T_cold = advanced["coldWaterTemp"]

    V_annual = householdSize * L_per_person_day * 365.0  # L/year
    deltaT = T_hot - T_cold

    specificHeat = 4.186  # kJ/kg·°C
    Q_delivered = (V_annual * deltaT * specificHeat) / 3600.0  # kWh/year

    eff = inputs["waterHeatingEfficiency"]
    Q_purchased = (Q_delivered / eff) if eff and eff > 0 else Q_delivered

    return {"Q_delivered": Q_delivered, "Q_purchased": Q_purchased, "V_annual": V_annual}

def calculate_lighting_and_appliances(inputs: dict) -> dict:
    """
    Spec 1.3: usage × intensity
    """
    lighting = inputs["lighting"]
    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]
    cooking = inputs["cooking"]

    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0

    Q_wash = washing["cyclesPerWeek"] * washing["energyPerCycle"] * 52.0 if washing["hasAppliance"] else 0.0
    Q_dish = dish["cyclesPerWeek"] * dish["energyPerCycle"] * 52.0 if dish["hasAppliance"] else 0.0
    Q_cook = cooking["mealsPerWeek"] * cooking["energyPerMeal"] * 52.0

    Q_total = Q_lighting + Q_wash + Q_dish + Q_cook

    return {
        "Q_total": Q_total,
        "breakdown": {"Q_lighting": Q_lighting, "Q_wash": Q_wash, "Q_dish": Q_dish, "Q_cook": Q_cook},
    }

def calculate_water_consumption(inputs: dict, advanced: dict) -> dict:
    """
    Spec 2: end-use breakdown (m³/year)
    """
    n = inputs["householdSize"]

    toiletLPerFlush = TOILET_TYPES[inputs["toiletType"]]
    showerFlowRate = SHOWER_TYPES[inputs["showerType"]]
    tapFlowRate = TAP_TYPES[inputs["tapType"]]

    toiletFlushesPerDay = advanced["toiletFlushesPerDay"]
    showersPerDay = advanced["showersPerDay"]
    showerMinutes = advanced["showerMinutes"]
    tapMinutesPerDay = advanced["tapMinutesPerDay"]

    V_toilet_L = n * toiletFlushesPerDay * toiletLPerFlush * 365.0
    V_shower_L = n * showersPerDay * showerMinutes * showerFlowRate * 365.0
    V_taps_L = n * tapMinutesPerDay * tapFlowRate * 365.0

    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]

    V_laundry_L = washing["cyclesPerWeek"] * washing["waterPerCycle"] * 52.0 if washing["hasAppliance"] else 0.0
    V_dishwasher_L = dish["cyclesPerWeek"] * dish["waterPerCycle"] * 52.0 if dish["hasAppliance"] else 0.0

    V_total_m3 = (V_toilet_L + V_shower_L + V_taps_L + V_laundry_L + V_dishwasher_L) / 1000.0

    return {
        "V_total": V_total_m3,
        "breakdown": {
            "V_toilet": V_toilet_L / 1000.0,
            "V_shower": V_shower_L / 1000.0,
            "V_taps": V_taps_L / 1000.0,
            "V_laundry": V_laundry_L / 1000.0,
            "V_dishwasher": V_dishwasher_L / 1000.0,
        },
    }

def calculate_operational_carbon(total_electricity_kwh: float, total_water_m3: float) -> dict:
    """
    Spec 3: activity × EF
    """
    CO2_electricity = total_electricity_kwh * GRID_EMISSION_FACTOR
    CO2_water = total_water_m3 * WATER_EMISSION_FACTOR
    return {"CO2_total": CO2_electricity + CO2_water, "CO2_electricity": CO2_electricity, "CO2_water": CO2_water}

def calculate_costs(total_electricity_kwh: float, total_water_m3: float) -> dict:
    """
    Spec 4.2: operating costs
    """
    cost_electricity = total_electricity_kwh * ELECTRICITY_TARIFF
    cost_water = total_water_m3 * WATER_TARIFF
    return {"cost_total": cost_electricity + cost_water, "cost_electricity": cost_electricity, "cost_water": cost_water}

def calculate_scenario(inputs: dict, advanced: dict) -> dict:
    space = calculate_space_heating(inputs)
    water_heat = calculate_water_heating(inputs, advanced)
    other = calculate_lighting_and_appliances(inputs)
    water_use = calculate_water_consumption(inputs, advanced)

    total_electricity = space["Q_purchased"] + water_heat["Q_purchased"] + other["Q_total"]
    carbon = calculate_operational_carbon(total_electricity, water_use["V_total"])
    costs = calculate_costs(total_electricity, water_use["V_total"])

    energy_intensity = (total_electricity / inputs["floorArea"]) if inputs["floorArea"] > 0 else 0.0

    return {
        "spaceHeating": space,
        "waterHeating": water_heat,
        "lightingAppliances": other,
        "waterConsumption": water_use,
        "totalElectricity": total_electricity,
        "carbon": carbon,
        "costs": costs,
        "energyIntensity": energy_intensity,
    }

# =============================================================================
# STATE / UTIL
# =============================================================================

def _stable_hash(obj: dict) -> str:
    s = json.dumps(obj, sort_keys=True, default=str)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()

def init_defaults():
    # Advanced (numeric defaults OK)
    st.session_state.setdefault("adv_hotWaterPerPersonPerDay", 50.0)
    st.session_state.setdefault("adv_hotWaterTemp", 60.0)
    st.session_state.setdefault("adv_coldWaterTemp", 15.0)
    st.session_state.setdefault("adv_toiletFlushesPerDay", 5.0)
    st.session_state.setdefault("adv_showersPerDay", 1.0)
    st.session_state.setdefault("adv_showerMinutes", 8.0)
    st.session_state.setdefault("adv_tapMinutesPerDay", 10.0)

    # Scenario numeric defaults OK
    for p in ["b", "o"]:
        st.session_state.setdefault(f"{p}_floorArea", 120.0)
        st.session_state.setdefault(f"{p}_ceilingHeight", 2.4)
        st.session_state.setdefault(f"{p}_householdSize", 3)

        st.session_state.setdefault(f"{p}_windowArea", 30.0)

        st.session_state.setdefault(f"{p}_light_n", LIGHTING_DEFAULTS["numberOfLights"])
        st.session_state.setdefault(f"{p}_light_watts", LIGHTING_DEFAULTS["wattsPerLight"])
        st.session_state.setdefault(f"{p}_light_hours", LIGHTING_DEFAULTS["hoursPerDay"])

        st.session_state.setdefault(f"{p}_wash_cycles", WASHING_MACHINE_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_wash_kwh", WASHING_MACHINE_DEFAULTS["energyPerCycle"])
        st.session_state.setdefault(f"{p}_wash_L", WASHING_MACHINE_DEFAULTS["waterPerCycle"])

        st.session_state.setdefault(f"{p}_dish_cycles", DISHWASHER_DEFAULTS["cyclesPerWeek"])
        st.session_state.setdefault(f"{p}_dish_kwh", DISHWASHER_DEFAULTS["energyPerCycle"])
        st.session_state.setdefault(f"{p}_dish_L", DISHWASHER_DEFAULTS["waterPerCycle"])

        st.session_state.setdefault(f"{p}_cook_meals", COOKING_DEFAULTS["mealsPerWeek"])
        st.session_state.setdefault(f"{p}_cook_kwh", COOKING_DEFAULTS["energyPerMeal"])

    # Scenario categorical defaults MUST be unselected
    cat_keys = [
        "climateZone",
        "roofRLabel",
        "wallRLabel",
        "floorRLabel",
        "windowULabel",
        "heatingSystem",
        "waterHeatingSystem",
        "toiletType",
        "showerType",
        "tapType",
        "wash_has",
        "dish_has",
    ]
    for p in ["b", "o"]:
        for k in cat_keys:
            st.session_state.setdefault(f"{p}_{k}", PLACEHOLDER)

    # Result caching
    st.session_state.setdefault("has_calculated", False)
    st.session_state.setdefault("last_payload", None)     # snapshot (inputs + results)
    st.session_state.setdefault("last_signature", None)   # hash(signature)
    st.session_state.setdefault("show_advanced", False)

def get_advanced_settings() -> dict:
    return {
        "hotWaterPerPersonPerDay": float(st.session_state["adv_hotWaterPerPersonPerDay"]),
        "hotWaterTemp": float(st.session_state["adv_hotWaterTemp"]),
        "coldWaterTemp": float(st.session_state["adv_coldWaterTemp"]),
        "toiletFlushesPerDay": float(st.session_state["adv_toiletFlushesPerDay"]),
        "showersPerDay": float(st.session_state["adv_showersPerDay"]),
        "showerMinutes": float(st.session_state["adv_showerMinutes"]),
        "tapMinutesPerDay": float(st.session_state["adv_tapMinutesPerDay"]),
    }

def _yn_to_bool(v: str):
    if v == "Yes":
        return True
    if v == "No":
        return False
    return None

def get_scenario(prefix: str) -> dict:
    """
    Read a scenario from session_state, mapping labels -> numeric coefficients.
    If any required categorical input is PLACEHOLDER, store None in the scenario and let validation handle it.
    """
    climateZone = st.session_state[f"{prefix}_climateZone"]
    roof_label = st.session_state[f"{prefix}_roofRLabel"]
    wall_label = st.session_state[f"{prefix}_wallRLabel"]
    floor_label = st.session_state[f"{prefix}_floorRLabel"]
    win_label = st.session_state[f"{prefix}_windowULabel"]
    heat_sys = st.session_state[f"{prefix}_heatingSystem"]
    hw_sys = st.session_state[f"{prefix}_waterHeatingSystem"]
    toilet = st.session_state[f"{prefix}_toiletType"]
    shower = st.session_state[f"{prefix}_showerType"]
    tap = st.session_state[f"{prefix}_tapType"]

    wash_has = _yn_to_bool(st.session_state[f"{prefix}_wash_has"])
    dish_has = _yn_to_bool(st.session_state[f"{prefix}_dish_has"])

    # Map labels to values when selected
    def map_r(label, lookup):
        if label == PLACEHOLDER:
            return None
        return float(lookup[label])

    def map_u(label, lookup):
        if label == PLACEHOLDER:
            return None
        return float(lookup[label])

    def map_eff(label, lookup):
        if label == PLACEHOLDER:
            return None
        return float(lookup[label])

    scenario = {
        "climateZone": None if climateZone == PLACEHOLDER else climateZone,
        "floorArea": float(st.session_state[f"{prefix}_floorArea"]),
        "ceilingHeight": float(st.session_state[f"{prefix}_ceilingHeight"]),
        "householdSize": int(st.session_state[f"{prefix}_householdSize"]),

        "roofRValue": map_r(roof_label, R_VALUES_ROOF),
        "wallRValue": map_r(wall_label, R_VALUES_WALLS),
        "floorRValue": map_r(floor_label, R_VALUES_FLOOR),
        "windowUValue": map_u(win_label, U_VALUES_WINDOWS),

        "windowArea": float(st.session_state[f"{prefix}_windowArea"]),

        "heatingSystemEfficiency": map_eff(heat_sys, HEATING_SYSTEMS),
        "waterHeatingEfficiency": map_eff(hw_sys, WATER_HEATING_SYSTEMS),

        "toiletType": None if toilet == PLACEHOLDER else toilet,
        "showerType": None if shower == PLACEHOLDER else shower,
        "tapType": None if tap == PLACEHOLDER else tap,

        "lighting": {
            "numberOfLights": int(st.session_state[f"{prefix}_light_n"]),
            "wattsPerLight": float(st.session_state[f"{prefix}_light_watts"]),
            "hoursPerDay": float(st.session_state[f"{prefix}_light_hours"]),
        },
        "washingMachine": {
            "hasAppliance": wash_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_wash_cycles"]),
            "energyPerCycle": float(st.session_state[f"{prefix}_wash_kwh"]),
            "waterPerCycle": float(st.session_state[f"{prefix}_wash_L"]),
        },
        "dishwasher": {
            "hasAppliance": dish_has,
            "cyclesPerWeek": float(st.session_state[f"{prefix}_dish_cycles"]),
            "energyPerCycle": float(st.session_state[f"{prefix}_dish_kwh"]),
            "waterPerCycle": float(st.session_state[f"{prefix}_dish_L"]),
        },
        "cooking": {
            "mealsPerWeek": float(st.session_state[f"{prefix}_cook_meals"]),
            "energyPerMeal": float(st.session_state[f"{prefix}_cook_kwh"]),
        },
        # Keep original labels too (for debugging / transparency)
        "_labels": {
            "roofRLabel": roof_label,
            "wallRLabel": wall_label,
            "floorRLabel": floor_label,
            "windowULabel": win_label,
            "heatingSystem": heat_sys,
            "waterHeatingSystem": hw_sys,
            "wash_has": st.session_state[f"{prefix}_wash_has"],
            "dish_has": st.session_state[f"{prefix}_dish_has"],
        },
    }
    return scenario

def validate_scenario(s: dict) -> list:
    """
    Returns list of missing fields (human-readable).
    """
    missing = []
    if s["climateZone"] is None:
        missing.append("Climate zone")
    if s["roofRValue"] is None:
        missing.append("Roof insulation (R-value)")
    if s["wallRValue"] is None:
        missing.append("Wall insulation (R-value)")
    if s["floorRValue"] is None:
        missing.append("Floor insulation (R-value)")
    if s["windowUValue"] is None:
        missing.append("Window type (U-value)")
    if s["heatingSystemEfficiency"] is None:
        missing.append("Space heating system")
    if s["waterHeatingEfficiency"] is None:
        missing.append("Water heating system")
    if s["toiletType"] is None:
        missing.append("Toilet type")
    if s["showerType"] is None:
        missing.append("Shower type")
    if s["tapType"] is None:
        missing.append("Tap type")

    if s["washingMachine"]["hasAppliance"] is None:
        missing.append("Washing machine (Yes/No)")
    if s["dishwasher"]["hasAppliance"] is None:
        missing.append("Dishwasher (Yes/No)")

    return missing

def copy_baseline_to_option():
    """
    Copy ALL baseline widgets to option widgets (full copy).
    """
    mappings = [
        # categorical
        ("b_climateZone", "o_climateZone"),
        ("b_roofRLabel", "o_roofRLabel"),
        ("b_wallRLabel", "o_wallRLabel"),
        ("b_floorRLabel", "o_floorRLabel"),
        ("b_windowULabel", "o_windowULabel"),
        ("b_heatingSystem", "o_heatingSystem"),
        ("b_waterHeatingSystem", "o_waterHeatingSystem"),
        ("b_toiletType", "o_toiletType"),
        ("b_showerType", "o_showerType"),
        ("b_tapType", "o_tapType"),
        ("b_wash_has", "o_wash_has"),
        ("b_dish_has", "o_dish_has"),

        # numeric / inputs
        ("b_floorArea", "o_floorArea"),
        ("b_ceilingHeight", "o_ceilingHeight"),
        ("b_householdSize", "o_householdSize"),
        ("b_windowArea", "o_windowArea"),

        # lighting
        ("b_light_n", "o_light_n"),
        ("b_light_watts", "o_light_watts"),
        ("b_light_hours", "o_light_hours"),

        # washing machine
        ("b_wash_cycles", "o_wash_cycles"),
        ("b_wash_kwh", "o_wash_kwh"),
        ("b_wash_L", "o_wash_L"),

        # dishwasher
        ("b_dish_cycles", "o_dish_cycles"),
        ("b_dish_kwh", "o_dish_kwh"),
        ("b_dish_L", "o_dish_L"),

        # cooking
        ("b_cook_meals", "o_cook_meals"),
        ("b_cook_kwh", "o_cook_kwh"),
    ]
    for src, dst in mappings:
        st.session_state[dst] = copy.deepcopy(st.session_state[src])

    # Force recalculation requirement
    st.session_state["has_calculated"] = False
    st.session_state["last_payload"] = None
    st.session_state["last_signature"] = None

# =============================================================================
# UI HELPERS
# =============================================================================

def select_with_placeholder(label: str, options: list, key: str, help_text: str | None = None):
    full = [PLACEHOLDER] + options
    current = st.session_state.get(key, PLACEHOLDER)
    idx = full.index(current) if current in full else 0
    return st.selectbox(label, full, index=idx, key=key, help=help_text)

def direction_arrow(delta: float) -> str:
    if delta < 0:
        return "▼"  # option lower than baseline
    if delta > 0:
        return "▲"
    return "—"

def fmt_num(x: float, decimals: int = 1):
    if x is None:
        return "—"
    return f"{x:,.{decimals}f}"

# =============================================================================
# APP
# =============================================================================
init_defaults()

st.title("NZ Housing Sustainability Calculator (Prototype)")
st.write(
    "Early-stage decision support for comparing housing scenarios. "
    "**Not a certification tool.** Values and coefficients are placeholders unless you replace them."
)

# ---- Advanced settings (top; not inside scenario columns) ----
with st.expander("Advanced settings (DUMMY defaults; optional overrides)", expanded=st.session_state["show_advanced"]):
    st.session_state["show_advanced"] = True
    st.number_input("Hot water demand (L/person/day)", min_value=0.0, max_value=300.0, step=1.0, key="adv_hotWaterPerPersonPerDay")
    st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key="adv_hotWaterTemp")
    st.number_input("Cold water inlet temperature (°C)", min_value=0.0, max_value=30.0, step=1.0, key="adv_coldWaterTemp")
    st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key="adv_toiletFlushesPerDay")
    st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key="adv_showersPerDay")
    st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.5, key="adv_showerMinutes")
    st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key="adv_tapMinutesPerDay")

adv = get_advanced_settings()

# ---- Layout ----
col_b, col_o, col_r = st.columns([1.05, 1.05, 1.30], gap="large")

# =============================================================================
# BASELINE COLUMN
# =============================================================================
with col_b:
    st.subheader("Baseline")

    with st.expander("1) Basic information", expanded=True):
        select_with_placeholder(
            "Climate zone",
            list(HDD_LOOKUP_BASE18.keys()),
            key="b_climateZone",
            help_text="HDD base 18°C shown only after you select a zone.",
        )
        if st.session_state["b_climateZone"] != PLACEHOLDER:
            st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['b_climateZone']]}** (DUMMY)")

        st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="b_floorArea")
        st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="b_ceilingHeight")
        st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="b_householdSize")

    with st.expander("1.1) Thermal envelope", expanded=False):
        select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key="b_roofRLabel")
        if st.session_state["b_roofRLabel"] != PLACEHOLDER:
            r = R_VALUES_ROOF[st.session_state["b_roofRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key="b_wallRLabel")
        if st.session_state["b_wallRLabel"] != PLACEHOLDER:
            r = R_VALUES_WALLS[st.session_state["b_wallRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key="b_floorRLabel")
        if st.session_state["b_floorRLabel"] != PLACEHOLDER:
            r = R_VALUES_FLOOR[st.session_state["b_floorRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key="b_windowULabel")
        if st.session_state["b_windowULabel"] != PLACEHOLDER:
            u = U_VALUES_WINDOWS[st.session_state["b_windowULabel"]]
            st.caption(f"U={u:.1f} W/m²K")

        st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="b_windowArea")

    with st.expander("1.1.4) Space heating system", expanded=False):
        select_with_placeholder("Heating system", list(HEATING_SYSTEMS.keys()), key="b_heatingSystem")
        if st.session_state["b_heatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[st.session_state['b_heatingSystem']]}** (DUMMY)")

    with st.expander("1.2) Water heating system", expanded=False):
        select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="b_waterHeatingSystem")
        if st.session_state["b_waterHeatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[st.session_state['b_waterHeatingSystem']]}** (DUMMY)")

    with st.expander("1.3) Lighting & appliances", expanded=False):
        st.markdown("**Lighting**")
        st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="b_light_n")
        st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="b_light_watts")
        st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="b_light_hours")

        st.markdown("**Washing machine**")
        select_with_placeholder("Has washing machine?", ["Yes", "No"], key="b_wash_has")
        if st.session_state["b_wash_has"] == "Yes":
            st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="b_wash_cycles")
            st.number_input("kWh/cycle (washing)", min_value=0.0, max_value=10.0, step=0.1, key="b_wash_kwh")
            st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key="b_wash_L")

        st.markdown("**Dishwasher**")
        select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="b_dish_has")
        if st.session_state["b_dish_has"] == "Yes":
            st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="b_dish_cycles")
            st.number_input("kWh/cycle (dishwasher)", min_value=0.0, max_value=10.0, step=0.1, key="b_dish_kwh")
            st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key="b_dish_L")

        st.markdown("**Cooking**")
        st.number_input("Meals/week", min_value=0.0, max_value=100.0, step=1.0, key="b_cook_meals")
        st.number_input("kWh/meal", min_value=0.0, max_value=10.0, step=0.1, key="b_cook_kwh")

    with st.expander("2) Water fixtures", expanded=False):
        select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="b_toiletType")
        if st.session_state["b_toiletType"] != PLACEHOLDER:
            st.caption(f"{TOILET_TYPES[st.session_state['b_toiletType']]} L/flush (DUMMY)")

        select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="b_showerType")
        if st.session_state["b_showerType"] != PLACEHOLDER:
            st.caption(f"{SHOWER_TYPES[st.session_state['b_showerType']]} L/min (DUMMY)")

        select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="b_tapType")
        if st.session_state["b_tapType"] != PLACEHOLDER:
            st.caption(f"{TAP_TYPES[st.session_state['b_tapType']]} L/min (DUMMY)")

    # COPY BUTTON AT BOTTOM (as requested)
    st.divider()
    if st.button("Copy Baseline → Option", use_container_width=True):
        copy_baseline_to_option()
        st.rerun()

# =============================================================================
# OPTION COLUMN
# =============================================================================
with col_o:
    st.subheader("Option")

    with st.expander("1) Basic information", expanded=True):
        select_with_placeholder("Climate zone", list(HDD_LOOKUP_BASE18.keys()), key="o_climateZone")
        if st.session_state["o_climateZone"] != PLACEHOLDER:
            st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[st.session_state['o_climateZone']]}** (DUMMY)")

        st.number_input("Floor area (m²)", min_value=20.0, max_value=500.0, step=5.0, key="o_floorArea")
        st.number_input("Ceiling height (m)", min_value=2.0, max_value=4.0, step=0.1, key="o_ceilingHeight")
        st.number_input("Household size (people)", min_value=1, max_value=12, step=1, key="o_householdSize")

    with st.expander("1.1) Thermal envelope", expanded=False):
        select_with_placeholder("Roof insulation (R-value)", list(R_VALUES_ROOF.keys()), key="o_roofRLabel")
        if st.session_state["o_roofRLabel"] != PLACEHOLDER:
            r = R_VALUES_ROOF[st.session_state["o_roofRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Wall insulation (R-value)", list(R_VALUES_WALLS.keys()), key="o_wallRLabel")
        if st.session_state["o_wallRLabel"] != PLACEHOLDER:
            r = R_VALUES_WALLS[st.session_state["o_wallRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Floor insulation (R-value)", list(R_VALUES_FLOOR.keys()), key="o_floorRLabel")
        if st.session_state["o_floorRLabel"] != PLACEHOLDER:
            r = R_VALUES_FLOOR[st.session_state["o_floorRLabel"]]
            st.caption(f"R={r:.1f}, U={1/r:.2f} W/m²K")

        select_with_placeholder("Window type (U-value)", list(U_VALUES_WINDOWS.keys()), key="o_windowULabel")
        if st.session_state["o_windowULabel"] != PLACEHOLDER:
            u = U_VALUES_WINDOWS[st.session_state["o_windowULabel"]]
            st.caption(f"U={u:.1f} W/m²K")

        st.number_input("Total window area (m²)", min_value=0.0, max_value=200.0, step=5.0, key="o_windowArea")

    with st.expander("1.1.4) Space heating system", expanded=False):
        select_with_placeholder("Heating system", list(HEATING_SYSTEMS.keys()), key="o_heatingSystem")
        if st.session_state["o_heatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[st.session_state['o_heatingSystem']]}** (DUMMY)")

    with st.expander("1.2) Water heating system", expanded=False):
        select_with_placeholder("Water heating system", list(WATER_HEATING_SYSTEMS.keys()), key="o_waterHeatingSystem")
        if st.session_state["o_waterHeatingSystem"] != PLACEHOLDER:
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[st.session_state['o_waterHeatingSystem']]}** (DUMMY)")

    with st.expander("1.3) Lighting & appliances", expanded=False):
        st.markdown("**Lighting**")
        st.number_input("Number of lights", min_value=0, max_value=200, step=1, key="o_light_n")
        st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, key="o_light_watts")
        st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, key="o_light_hours")

        st.markdown("**Washing machine**")
        select_with_placeholder("Has washing machine?", ["Yes", "No"], key="o_wash_has")
        if st.session_state["o_wash_has"] == "Yes":
            st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key="o_wash_cycles")
            st.number_input("kWh/cycle (washing)", min_value=0.0, max_value=10.0, step=0.1, key="o_wash_kwh")
            st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key="o_wash_L")

        st.markdown("**Dishwasher**")
        select_with_placeholder("Has dishwasher?", ["Yes", "No"], key="o_dish_has")
        if st.session_state["o_dish_has"] == "Yes":
            st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key="o_dish_cycles")
            st.number_input("kWh/cycle (dishwasher)", min_value=0.0, max_value=10.0, step=0.1, key="o_dish_kwh")
            st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key="o_dish_L")

        st.markdown("**Cooking**")
        st.number_input("Meals/week", min_value=0.0, max_value=100.0, step=1.0, key="o_cook_meals")
        st.number_input("kWh/meal", min_value=0.0, max_value=10.0, step=0.1, key="o_cook_kwh")

    with st.expander("2) Water fixtures", expanded=False):
        select_with_placeholder("Toilet type", list(TOILET_TYPES.keys()), key="o_toiletType")
        if st.session_state["o_toiletType"] != PLACEHOLDER:
            st.caption(f"{TOILET_TYPES[st.session_state['o_toiletType']]} L/flush (DUMMY)")

        select_with_placeholder("Shower type", list(SHOWER_TYPES.keys()), key="o_showerType")
        if st.session_state["o_showerType"] != PLACEHOLDER:
            st.caption(f"{SHOWER_TYPES[st.session_state['o_showerType']]} L/min (DUMMY)")

        select_with_placeholder("Tap type", list(TAP_TYPES.keys()), key="o_tapType")
        if st.session_state["o_tapType"] != PLACEHOLDER:
            st.caption(f"{TAP_TYPES[st.session_state['o_tapType']]} L/min (DUMMY)")

# =============================================================================
# RESULTS COLUMN
# =============================================================================
with col_r:
    st.subheader("Results")

    # Current inputs snapshot (for dirty check)
    baseline_now = get_scenario("b")
    option_now = get_scenario("o")
    signature_now = _stable_hash({"advanced": adv, "baseline": baseline_now, "option": option_now})

    # Calculate button (results are NOT live)
    c1, c2 = st.columns([1, 1])
    with c1:
        do_calc = st.button("Calculate results", type="primary", use_container_width=True)
    with c2:
        show_charts = st.toggle("Show charts", value=True)

    if do_calc:
        missing_b = validate_scenario(baseline_now)
        if missing_b:
            st.error("Baseline is incomplete. Missing: " + ", ".join(missing_b))
            st.session_state["has_calculated"] = False
            st.session_state["last_payload"] = None
            st.session_state["last_signature"] = None
        else:
            # Baseline always calculated (once baseline complete)
            base_r = calculate_scenario(baseline_now, adv)

            # Option only if complete
            missing_o = validate_scenario(option_now)
            opt_r = None if missing_o else calculate_scenario(option_now, adv)

            payload = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "advancedSettings": adv,
                "baseline": {"inputs": baseline_now, "results": base_r},
                "option": {"inputs": option_now, "results": opt_r, "missing": missing_o},
                "notes": {
                    "coefficients": "DUMMY placeholders unless replaced.",
                    "tool_scope": "Early-stage decision support; not certification; not predictive modelling.",
                },
            }

            st.session_state["has_calculated"] = True
            st.session_state["last_payload"] = payload
            st.session_state["last_signature"] = signature_now

    # Display last results snapshot only
    if not st.session_state["has_calculated"] or st.session_state["last_payload"] is None:
        st.info("Press **Calculate results** to generate outputs. Results do not update live.")
        st.stop()

    # Dirty check
    if st.session_state["last_signature"] != signature_now:
        st.warning("Inputs have changed since the last calculation. Press **Calculate results** to refresh outputs.")

    payload = st.session_state["last_payload"]
    base_r = payload["baseline"]["results"]
    opt_r = payload["option"]["results"]
    opt_missing = payload["option"]["missing"]

    # Download snapshot
    st.download_button(
        "Download results (JSON)",
        data=json.dumps(payload, indent=2),
        file_name=f"housing-sustainability-comparison-{int(datetime.utcnow().timestamp())}.json",
        mime="application/json",
        use_container_width=True,
    )

    st.divider()

    # KPI table (Baseline vs Option with arrow)
    def kpi_rows():
        rows = [
            ("Total Energy Consumption", base_r["totalElectricity"], None if opt_r is None else opt_r["totalElectricity"], "kWh/year", 1),
            ("Energy Intensity", base_r["energyIntensity"], None if opt_r is None else opt_r["energyIntensity"], "kWh/m²/year", 2),
            ("Water Consumption", base_r["waterConsumption"]["V_total"], None if opt_r is None else opt_r["waterConsumption"]["V_total"], "m³/year", 2),
            ("Operational Carbon", base_r["carbon"]["CO2_total"], None if opt_r is None else opt_r["carbon"]["CO2_total"], "kgCO₂e/year", 1),
            ("Annual Operating Cost", base_r["costs"]["cost_total"], None if opt_r is None else opt_r["costs"]["cost_total"], "NZD/year", 0),
        ]
        out = []
        for name, b, o, unit, dec in rows:
            if o is None:
                out.append({"Metric": name, "Baseline": fmt_num(b, dec), "Option": "—", "Δ (Option−Base)": "—", "Dir": "—", "Unit": unit})
            else:
                d = o - b
                out.append({"Metric": name, "Baseline": fmt_num(b, dec), "Option": fmt_num(o, dec), "Δ (Option−Base)": fmt_num(d, dec), "Dir": direction_arrow(d), "Unit": unit})
        return out

    st.markdown("**Key Performance Indicators**")
    st.dataframe(pd.DataFrame(kpi_rows()), use_container_width=True, hide_index=True)

    if opt_r is None:
        st.info("Option is incomplete. Complete Option inputs (or use **Copy Baseline → Option**) and recalculate to see comparison and charts.")
        st.stop()

    # Savings (Option vs Baseline; positive = improvement)
    savings = {
        "electricity": base_r["totalElectricity"] - opt_r["totalElectricity"],
        "water": base_r["waterConsumption"]["V_total"] - opt_r["waterConsumption"]["V_total"],
        "carbon": base_r["carbon"]["CO2_total"] - opt_r["carbon"]["CO2_total"],
        "cost": base_r["costs"]["cost_total"] - opt_r["costs"]["cost_total"],
    }

    def pct(saved, base):
        return (saved / base * 100.0) if base and base > 0 else 0.0

    st.markdown("**Annual Savings (Option vs Baseline)**")
    st.write(
        f"- Energy: **{savings['electricity']:,.1f} kWh** ({pct(savings['electricity'], base_r['totalElectricity']):.1f}%)\n"
        f"- Water: **{savings['water']:,.2f} m³** ({pct(savings['water'], base_r['waterConsumption']['V_total']):.1f}%)\n"
        f"- Carbon: **{savings['carbon']:,.1f} kgCO₂e** ({pct(savings['carbon'], base_r['carbon']['CO2_total']):.1f}%)\n"
        f"- Cost: **{savings['cost']:,.0f} NZD** ({pct(savings['cost'], base_r['costs']['cost_total']):.1f}%)"
    )

    # Charts (tabs)
    if show_charts:
        st.divider()
        tabs = st.tabs(["KPIs", "Energy", "Water", "Carbon", "Cost"])

        with tabs[0]:
            df_kpi = pd.DataFrame([
                {"Metric": "Total Energy (kWh/y)", "Baseline": base_r["totalElectricity"], "Option": opt_r["totalElectricity"]},
                {"Metric": "Energy Intensity (kWh/m²/y)", "Baseline": base_r["energyIntensity"], "Option": opt_r["energyIntensity"]},
                {"Metric": "Water (m³/y)", "Baseline": base_r["waterConsumption"]["V_total"], "Option": opt_r["waterConsumption"]["V_total"]},
                {"Metric": "Operational Carbon (kgCO₂e/y)", "Baseline": base_r["carbon"]["CO2_total"], "Option": opt_r["carbon"]["CO2_total"]},
                {"Metric": "Cost (NZD/y)", "Baseline": base_r["costs"]["cost_total"], "Option": opt_r["costs"]["cost_total"]},
            ])
            dfm = df_kpi.melt(id_vars=["Metric"], var_name="Scenario", value_name="Value")
            fig = px.bar(dfm, y="Metric", x="Value", color="Scenario", barmode="group", orientation="h")
            st.plotly_chart(fig, use_container_width=True)

        with tabs[1]:
            df_energy = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Space Heating", "Value": base_r["spaceHeating"]["Q_purchased"]},
                {"Scenario": "Baseline", "Component": "Water Heating", "Value": base_r["waterHeating"]["Q_purchased"]},
                {"Scenario": "Baseline", "Component": "Lighting & Appliances", "Value": base_r["lightingAppliances"]["Q_total"]},
                {"Scenario": "Option", "Component": "Space Heating", "Value": opt_r["spaceHeating"]["Q_purchased"]},
                {"Scenario": "Option", "Component": "Water Heating", "Value": opt_r["waterHeating"]["Q_purchased"]},
                {"Scenario": "Option", "Component": "Lighting & Appliances", "Value": opt_r["lightingAppliances"]["Q_total"]},
            ])
            fig = px.bar(df_energy, x="Scenario", y="Value", color="Component", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

        with tabs[2]:
            b = base_r["waterConsumption"]["breakdown"]
            o = opt_r["waterConsumption"]["breakdown"]
            df_water = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Toilets", "Value": b["V_toilet"]},
                {"Scenario": "Baseline", "Component": "Showers", "Value": b["V_shower"]},
                {"Scenario": "Baseline", "Component": "Taps", "Value": b["V_taps"]},
                {"Scenario": "Baseline", "Component": "Laundry", "Value": b["V_laundry"]},
                {"Scenario": "Baseline", "Component": "Dishwasher", "Value": b["V_dishwasher"]},
                {"Scenario": "Option", "Component": "Toilets", "Value": o["V_toilet"]},
                {"Scenario": "Option", "Component": "Showers", "Value": o["V_shower"]},
                {"Scenario": "Option", "Component": "Taps", "Value": o["V_taps"]},
                {"Scenario": "Option", "Component": "Laundry", "Value": o["V_laundry"]},
                {"Scenario": "Option", "Component": "Dishwasher", "Value": o["V_dishwasher"]},
            ])
            fig = px.bar(df_water, x="Scenario", y="Value", color="Component", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

        with tabs[3]:
            df_carbon = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["carbon"]["CO2_electricity"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["carbon"]["CO2_water"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["carbon"]["CO2_electricity"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["carbon"]["CO2_water"]},
            ])
            fig = px.bar(df_carbon, x="Scenario", y="Value", color="Component", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

        with tabs[4]:
            df_cost = pd.DataFrame([
                {"Scenario": "Baseline", "Component": "Electricity", "Value": base_r["costs"]["cost_electricity"]},
                {"Scenario": "Baseline", "Component": "Water", "Value": base_r["costs"]["cost_water"]},
                {"Scenario": "Option", "Component": "Electricity", "Value": opt_r["costs"]["cost_electricity"]},
                {"Scenario": "Option", "Component": "Water", "Value": opt_r["costs"]["cost_water"]},
            ])
            fig = px.bar(df_cost, x="Scenario", y="Value", color="Component", barmode="stack")
            st.plotly_chart(fig, use_container_width=True)

st.caption(
    "Notes: Results are simplified and indicative. This prototype uses placeholder coefficients unless you replace them. "
    "No embodied carbon, no detailed simulation, no behavioural modelling, no time-of-use pricing."
)
