# app.py
# Streamlit version with:
# - Results hidden until user clicks "Calculate / Update Results"
# - NO default selection for ALL categorical inputs (dropdowns start blank)
# - NO default selection for dishwasher / washing machine (checkboxes start OFF)
# - Numeric fields still have defaults

import json
import math
from copy import deepcopy
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# =============================================================================
# DUMMY COEFFICIENTS (PLACEHOLDERS)
# =============================================================================

HDD_LOOKUP_BASE18 = {
    "Zone 1 (Warmest - e.g., Northland)": 1200,
    "Zone 2 (Warm - e.g., Auckland)": 1600,
    "Zone 3 (Mild - e.g., Wellington)": 2000,
    "Zone 4 (Cool - e.g., Christchurch)": 2400,
    "Zone 5 (Cold - e.g., Queenstown)": 2800,
    "Zone 6 (Coldest - e.g., Central Otago)": 3200,
}

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

HEATING_SYSTEMS = {
    "None": 0,
    "Electric resistance": 1.0,
    "Heat pump (COP 3.0)": 3.0,
    "Heat pump (COP 4.0)": 4.0,
}

WATER_HEATING_SYSTEMS = {
    "Electric storage cylinder": 1.0,
    "Heat pump hot water (COP 2.5)": 2.5,
    "Heat pump hot water (COP 3.0)": 3.0,
}

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

WASHING_MACHINE_DEFAULTS = {"cyclesPerWeek": 4, "energyPerCycle": 0.8, "waterPerCycle": 60}
DISHWASHER_DEFAULTS = {"cyclesPerWeek": 4, "energyPerCycle": 1.0, "waterPerCycle": 12}
COOKING_DEFAULTS = {"mealsPerWeek": 14, "energyPerMeal": 0.5}
LIGHTING_DEFAULTS = {"numberOfLights": 15, "wattsPerLight": 10, "hoursPerDay": 5}

GRID_EMISSION_FACTOR = 0.10      # kgCO2/kWh  - DUMMY
ELECTRICITY_TARIFF = 0.30        # NZD/kWh    - DUMMY
WATER_TARIFF = 2.50              # NZD/m³     - DUMMY
WATER_EMISSION_FACTOR = 0.63     # kgCO2/m³   - DUMMY

# =============================================================================
# CALCULATION FUNCTIONS
# =============================================================================

def calculate_space_heating(inputs: dict) -> dict:
    HDD = float(HDD_LOOKUP_BASE18[inputs["climateZone"]])

    floor_area = float(inputs["floorArea"])
    ceiling_height = float(inputs["ceilingHeight"])
    window_area = float(inputs["windowArea"])

    roof_r = float(inputs["roofRValue"])
    wall_r = float(inputs["wallRValue"])
    floor_r = float(inputs["floorRValue"])
    window_u = float(inputs["windowUValue"])

    roof_u = 1.0 / roof_r
    wall_u = 1.0 / wall_r
    floor_u = 1.0 / floor_r

    roof_area = floor_area
    perimeter = 4.0 * math.sqrt(max(floor_area, 0.0))
    wall_area = max(perimeter * ceiling_height - window_area, 0.0)

    H_roof = roof_area * roof_u
    H_wall = wall_area * wall_u
    H_floor = floor_area * floor_u
    H_window = window_area * window_u
    H_total = H_roof + H_wall + H_floor + H_window

    Q_delivered = (H_total * HDD * 24.0) / 1000.0  # kWh/year

    system_eff = float(HEATING_SYSTEMS[inputs["heatingSystem"]])
    Q_purchased = (Q_delivered / system_eff) if system_eff > 0 else 0.0

    return {
        "Q_delivered": Q_delivered,
        "Q_purchased": Q_purchased,
        "H_total": H_total,
        "breakdown": {"H_roof": H_roof, "H_wall": H_wall, "H_floor": H_floor, "H_window": H_window},
    }

def calculate_water_heating(inputs: dict, advanced: dict) -> dict:
    household_size = int(inputs["householdSize"])
    system_eff = float(WATER_HEATING_SYSTEMS[inputs["waterHeatingSystem"]])

    V_annual = household_size * float(advanced["hotWaterPerPersonPerDay"]) * 365.0  # L/year
    deltaT = max(float(advanced["hotWaterTemp"]) - float(advanced["coldWaterTemp"]), 0.0)

    specific_heat = 4.186  # kJ/kg·°C
    Q_delivered = (V_annual * deltaT * specific_heat) / 3600.0  # kWh/year
    Q_purchased = (Q_delivered / system_eff) if system_eff > 0 else Q_delivered

    return {"Q_delivered": Q_delivered, "Q_purchased": Q_purchased, "V_annual": V_annual}

def calculate_lighting_and_appliances(inputs: dict) -> dict:
    lighting = inputs["lighting"]
    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]
    cooking = inputs["cooking"]

    Q_lighting = (lighting["numberOfLights"] * lighting["wattsPerLight"] * lighting["hoursPerDay"] * 365.0) / 1000.0
    Q_wash = (washing["cyclesPerWeek"] * washing["energyPerCycle"] * 52.0) if washing["hasAppliance"] else 0.0
    Q_dish = (dish["cyclesPerWeek"] * dish["energyPerCycle"] * 52.0) if dish["hasAppliance"] else 0.0
    Q_cook = cooking["mealsPerWeek"] * cooking["energyPerMeal"] * 52.0

    Q_total = Q_lighting + Q_wash + Q_dish + Q_cook
    return {"Q_total": Q_total, "breakdown": {"Q_lighting": Q_lighting, "Q_wash": Q_wash, "Q_dish": Q_dish, "Q_cook": Q_cook}}

def calculate_water_consumption(inputs: dict, advanced: dict) -> dict:
    household_size = int(inputs["householdSize"])

    toilet_L = float(TOILET_TYPES[inputs["toiletType"]])
    shower_flow = float(SHOWER_TYPES[inputs["showerType"]])
    tap_flow = float(TAP_TYPES[inputs["tapType"]])

    toilet_flushes = float(advanced["toiletFlushesPerDay"])
    showers_per_day = float(advanced["showersPerDay"])
    shower_minutes = float(advanced["showerMinutes"])
    tap_minutes = float(advanced["tapMinutesPerDay"])

    V_toilet_L = household_size * toilet_flushes * toilet_L * 365.0
    V_shower_L = household_size * showers_per_day * shower_minutes * shower_flow * 365.0
    V_taps_L = household_size * tap_minutes * tap_flow * 365.0

    washing = inputs["washingMachine"]
    dish = inputs["dishwasher"]

    V_laundry_L = (washing["cyclesPerWeek"] * washing["waterPerCycle"] * 52.0) if washing["hasAppliance"] else 0.0
    V_dish_L = (dish["cyclesPerWeek"] * dish["waterPerCycle"] * 52.0) if dish["hasAppliance"] else 0.0

    V_total_m3 = (V_toilet_L + V_shower_L + V_taps_L + V_laundry_L + V_dish_L) / 1000.0
    return {
        "V_total": V_total_m3,
        "breakdown": {
            "V_toilet": V_toilet_L / 1000.0,
            "V_shower": V_shower_L / 1000.0,
            "V_taps": V_taps_L / 1000.0,
            "V_laundry": V_laundry_L / 1000.0,
            "V_dishwasher": V_dish_L / 1000.0,
        },
    }

def calculate_operational_carbon(total_electricity_kWh: float, total_water_m3: float) -> dict:
    CO2_elec = total_electricity_kWh * GRID_EMISSION_FACTOR
    CO2_water = total_water_m3 * WATER_EMISSION_FACTOR
    return {"CO2_total": CO2_elec + CO2_water, "CO2_electricity": CO2_elec, "CO2_water": CO2_water}

def calculate_costs(total_electricity_kWh: float, total_water_m3: float) -> dict:
    cost_e = total_electricity_kWh * ELECTRICITY_TARIFF
    cost_w = total_water_m3 * WATER_TARIFF
    return {"cost_total": cost_e + cost_w, "cost_electricity": cost_e, "cost_water": cost_w}

def calculate_scenario(inputs: dict, advanced: dict) -> dict:
    space = calculate_space_heating(inputs)
    water_heat = calculate_water_heating(inputs, advanced)
    lighting_apps = calculate_lighting_and_appliances(inputs)

    total_electricity = space["Q_purchased"] + water_heat["Q_purchased"] + lighting_apps["Q_total"]
    water = calculate_water_consumption(inputs, advanced)
    carbon = calculate_operational_carbon(total_electricity, water["V_total"])
    costs = calculate_costs(total_electricity, water["V_total"])

    floor_area = max(float(inputs["floorArea"]), 1e-9)
    energy_intensity = total_electricity / floor_area

    return {
        "spaceHeating": space,
        "waterHeating": water_heat,
        "lightingAppliances": lighting_apps,
        "totalElectricity": total_electricity,
        "waterConsumption": water,
        "carbon": carbon,
        "costs": costs,
        "energyIntensity": energy_intensity,
    }

# =============================================================================
# STATE HELPERS
# =============================================================================

def create_default_scenario_blank_choices() -> dict:
    # Numeric defaults exist; categorical choices start BLANK (None)
    return {
        "climateZone": None,
        "floorArea": 120.0,
        "ceilingHeight": 2.4,
        "householdSize": 3,

        "roofRValueLabel": None,
        "roofRValue": None,
        "wallRValueLabel": None,
        "wallRValue": None,
        "floorRValueLabel": None,
        "floorRValue": None,

        "windowUValueLabel": None,
        "windowUValue": None,
        "windowArea": 30.0,

        "heatingSystem": None,
        "waterHeatingSystem": None,

        "toiletType": None,
        "showerType": None,
        "tapType": None,

        "lighting": {
            "numberOfLights": LIGHTING_DEFAULTS["numberOfLights"],
            "wattsPerLight": LIGHTING_DEFAULTS["wattsPerLight"],
            "hoursPerDay": LIGHTING_DEFAULTS["hoursPerDay"],
        },

        # Appliances default NOT selected
        "washingMachine": {
            "hasAppliance": False,
            "cyclesPerWeek": WASHING_MACHINE_DEFAULTS["cyclesPerWeek"],
            "energyPerCycle": WASHING_MACHINE_DEFAULTS["energyPerCycle"],
            "waterPerCycle": WASHING_MACHINE_DEFAULTS["waterPerCycle"],
        },
        "dishwasher": {
            "hasAppliance": False,
            "cyclesPerWeek": DISHWASHER_DEFAULTS["cyclesPerWeek"],
            "energyPerCycle": DISHWASHER_DEFAULTS["energyPerCycle"],
            "waterPerCycle": DISHWASHER_DEFAULTS["waterPerCycle"],
        },
        "cooking": {
            "mealsPerWeek": COOKING_DEFAULTS["mealsPerWeek"],
            "energyPerMeal": COOKING_DEFAULTS["energyPerMeal"],
        },
    }

def scenario_ready(s: dict) -> bool:
    required = [
        "climateZone",
        "roofRValue", "wallRValue", "floorRValue", "windowUValue",
        "heatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    return all(s.get(k) is not None for k in required)

def stable_hash(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)

def _pct(base: float, opt: float) -> float:
    return 0.0 if abs(base) < 1e-12 else ((base - opt) / base) * 100.0

def _trend_arrow(opt: float, base: float) -> str:
    d = opt - base
    if abs(d) < 1e-9:
        return "→"
    return "↓" if d < 0 else "↑"

def fmt(val: float, decimals: int = 1) -> str:
    return f"{val:,.{decimals}f}"

def fmt0(val: float) -> str:
    return f"{val:,.0f}"

# =============================================================================
# STREAMLIT SETUP
# =============================================================================

st.set_page_config(page_title="NZ Housing Sustainability Calculator (Streamlit)", layout="wide")

if "advanced" not in st.session_state:
    st.session_state.advanced = {
        "hotWaterPerPersonPerDay": 50.0,  # DUMMY
        "hotWaterTemp": 60.0,             # DUMMY
        "coldWaterTemp": 15.0,            # DUMMY
        "toiletFlushesPerDay": 5.0,       # DUMMY
        "showersPerDay": 1.0,             # DUMMY
        "showerMinutes": 8.0,             # DUMMY
        "tapMinutesPerDay": 10.0,         # DUMMY
    }

if "baseline" not in st.session_state:
    st.session_state.baseline = create_default_scenario_blank_choices()

if "option_enabled" not in st.session_state:
    st.session_state.option_enabled = True  # keep comparison layout, but option can be left incomplete

if "option" not in st.session_state:
    st.session_state.option = create_default_scenario_blank_choices()

if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False

if "has_calculated" not in st.session_state:
    st.session_state.has_calculated = False

if "last_calc_hash" not in st.session_state:
    st.session_state.last_calc_hash = None

if "last_payload" not in st.session_state:
    st.session_state.last_payload = None

# =============================================================================
# UI: HEADER
# =============================================================================

st.title("NZ Housing Sustainability Calculator (Streamlit)")
st.write("Early-stage decision support tool for comparing housing scenarios. **Not a certification tool.**")
st.caption("All coefficients in this prototype are DUMMY placeholders (as per your React).")

top = st.columns([1.0, 1.0, 2.5], gap="medium")
with top[0]:
    st.session_state.show_advanced = st.toggle("Show Advanced Settings", value=st.session_state.show_advanced)
with top[1]:
    if st.button("Reset Option", use_container_width=True):
        st.session_state.option = create_default_scenario_blank_choices()
        st.session_state.has_calculated = False
with top[2]:
    st.info(
        f"Assumptions (DUMMY): Grid EF={GRID_EMISSION_FACTOR} kgCO₂/kWh | Water EF={WATER_EMISSION_FACTOR} kgCO₂/m³ | "
        f"Tariffs: {ELECTRICITY_TARIFF} NZD/kWh, {WATER_TARIFF} NZD/m³"
    )

if st.session_state.show_advanced:
    with st.expander("Advanced Settings (DUMMY values - editable)", expanded=True):
        adv = deepcopy(st.session_state.advanced)
        adv["hotWaterPerPersonPerDay"] = st.number_input("Hot water (L/person/day)", 0.0, 300.0, float(adv["hotWaterPerPersonPerDay"]), 5.0)
        adv["hotWaterTemp"] = st.number_input("Hot water temp (°C)", 30.0, 70.0, float(adv["hotWaterTemp"]), 1.0)
        adv["coldWaterTemp"] = st.number_input("Cold water temp (°C)", 0.0, 30.0, float(adv["coldWaterTemp"]), 1.0)
        adv["toiletFlushesPerDay"] = st.number_input("Toilet flushes/person/day", 0.0, 20.0, float(adv["toiletFlushesPerDay"]), 0.5)
        adv["showersPerDay"] = st.number_input("Showers/person/day", 0.0, 5.0, float(adv["showersPerDay"]), 0.1)
        adv["showerMinutes"] = st.number_input("Shower minutes", 0.0, 60.0, float(adv["showerMinutes"]), 1.0)
        adv["tapMinutesPerDay"] = st.number_input("Tap minutes/person/day", 0.0, 60.0, float(adv["tapMinutesPerDay"]), 1.0)
        st.session_state.advanced = adv

# =============================================================================
# INPUT UI HELPERS
# =============================================================================

def select_or_blank(label, options, key, value, placeholder="Select..."):
    if value is None:
        return st.selectbox(label, options=options, index=None, placeholder=placeholder, key=key)
    idx = options.index(value) if value in options else None
    return st.selectbox(label, options=options, index=idx, key=key)

def scenario_inputs_ui(title: str, prefix: str, scenario: dict) -> dict:
    st.subheader(title)

    with st.expander("1. Basic Information", expanded=True):
        cz_options = list(HDD_LOOKUP_BASE18.keys())
        cz = select_or_blank("Climate Zone (DUMMY HDD lookup)", cz_options, f"{prefix}_climateZone", scenario.get("climateZone"))
        st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[cz]}** (DUMMY)" if cz else "HDD (base 18°C): —")

        floor_area = st.number_input("Floor Area (m²)", 20.0, 500.0, float(scenario["floorArea"]), 5.0, key=f"{prefix}_floorArea")
        ceiling_height = st.number_input("Ceiling Height (m)", 2.0, 4.0, float(scenario["ceilingHeight"]), 0.1, key=f"{prefix}_ceilingHeight")
        hh = st.number_input("Household Size", 1, 10, int(scenario["householdSize"]), 1, key=f"{prefix}_householdSize")

    with st.expander("1.1 Thermal Envelope", expanded=False):
        roof_labels = list(R_VALUES_ROOF.keys())
        wall_labels = list(R_VALUES_WALLS.keys())
        floor_labels = list(R_VALUES_FLOOR.keys())
        win_labels = list(U_VALUES_WINDOWS.keys())

        roof_label = select_or_blank("Roof Insulation (R-value)", roof_labels, f"{prefix}_roofRValueLabel", scenario.get("roofRValueLabel"))
        roof_r = float(R_VALUES_ROOF[roof_label]) if roof_label else None
        st.caption(f"R = {roof_r:.1f}, U = {1/roof_r:.2f} W/m²K (DUMMY)" if roof_r else "R/U: —")

        wall_label = select_or_blank("Wall Insulation (R-value)", wall_labels, f"{prefix}_wallRValueLabel", scenario.get("wallRValueLabel"))
        wall_r = float(R_VALUES_WALLS[wall_label]) if wall_label else None
        st.caption(f"R = {wall_r:.1f}, U = {1/wall_r:.2f} W/m²K (DUMMY)" if wall_r else "R/U: —")

        floor_label = select_or_blank("Floor Insulation (R-value)", floor_labels, f"{prefix}_floorRValueLabel", scenario.get("floorRValueLabel"))
        floor_r = float(R_VALUES_FLOOR[floor_label]) if floor_label else None
        st.caption(f"R = {floor_r:.1f}, U = {1/floor_r:.2f} W/m²K (DUMMY)" if floor_r else "R/U: —")

        win_label = select_or_blank("Window Type (U-value)", win_labels, f"{prefix}_windowUValueLabel", scenario.get("windowUValueLabel"))
        win_u = float(U_VALUES_WINDOWS[win_label]) if win_label else None
        st.caption(f"U = {win_u:.1f} W/m²K (DUMMY)" if win_u else "U: —")

        window_area = st.number_input("Total Window Area (m²)", 5.0, 100.0, float(scenario["windowArea"]), 5.0, key=f"{prefix}_windowArea")
        st.caption(f"~{(window_area / float(floor_area) * 100.0):.0f}% of floor area" if float(floor_area) > 0 else "")

    with st.expander("1.1.4 Space Heating System", expanded=False):
        hs_options = list(HEATING_SYSTEMS.keys())
        hs = select_or_blank("Heating System Type (efficiency/COP)", hs_options, f"{prefix}_heatingSystem", scenario.get("heatingSystem"))
        st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[hs]}** (DUMMY)" if hs else "Efficiency/COP: —")

    with st.expander("1.2 Water Heating System", expanded=False):
        whs_options = list(WATER_HEATING_SYSTEMS.keys())
        whs = select_or_blank("Water Heating Type (efficiency/COP)", whs_options, f"{prefix}_waterHeatingSystem", scenario.get("waterHeatingSystem"))
        st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[whs]}** (DUMMY)" if whs else "Efficiency/COP: —")

    with st.expander("1.3 Lighting & Appliances", expanded=False):
        n_lights = st.number_input("# Lights", 0, 200, int(scenario["lighting"]["numberOfLights"]), 1, key=f"{prefix}_lighting_numberOfLights")
        watts_per_light = st.number_input("Watts per light", 0.0, 200.0, float(scenario["lighting"]["wattsPerLight"]), 1.0, key=f"{prefix}_lighting_wattsPerLight")
        hours_per_day = st.number_input("Lighting hours/day", 0.0, 24.0, float(scenario["lighting"]["hoursPerDay"]), 0.5, key=f"{prefix}_lighting_hoursPerDay")

        st.markdown("**Washing Machine**")
        has_washer = st.checkbox("Has washing machine", value=bool(scenario["washingMachine"]["hasAppliance"]), key=f"{prefix}_washing_hasAppliance")
        if has_washer:
            wash_cycles = st.number_input("Cycles/week (washing)", 0.0, 30.0, float(scenario["washingMachine"]["cyclesPerWeek"]), 1.0, key=f"{prefix}_washing_cyclesPerWeek")
            wash_kwh = st.number_input("kWh/cycle (washing)", 0.0, 10.0, float(scenario["washingMachine"]["energyPerCycle"]), 0.1, key=f"{prefix}_washing_energyPerCycle")
            wash_L = st.number_input("L/cycle (washing)", 0.0, 300.0, float(scenario["washingMachine"]["waterPerCycle"]), 5.0, key=f"{prefix}_washing_waterPerCycle")
        else:
            wash_cycles, wash_kwh, wash_L = 0.0, 0.0, 0.0

        st.markdown("**Dishwasher**")
        has_dish = st.checkbox("Has dishwasher", value=bool(scenario["dishwasher"]["hasAppliance"]), key=f"{prefix}_dish_hasAppliance")
        if has_dish:
            dish_cycles = st.number_input("Cycles/week (dishwasher)", 0.0, 30.0, float(scenario["dishwasher"]["cyclesPerWeek"]), 1.0, key=f"{prefix}_dish_cyclesPerWeek")
            dish_kwh = st.number_input("kWh/cycle (dishwasher)", 0.0, 10.0, float(scenario["dishwasher"]["energyPerCycle"]), 0.1, key=f"{prefix}_dish_energyPerCycle")
            dish_L = st.number_input("L/cycle (dishwasher)", 0.0, 200.0, float(scenario["dishwasher"]["waterPerCycle"]), 1.0, key=f"{prefix}_dish_waterPerCycle")
        else:
            dish_cycles, dish_kwh, dish_L = 0.0, 0.0, 0.0

        st.markdown("**Cooking**")
        meals_wk = st.number_input("Meals/week", 0.0, 100.0, float(scenario["cooking"]["mealsPerWeek"]), 1.0, key=f"{prefix}_cooking_mealsPerWeek")
        kwh_meal = st.number_input("kWh/meal", 0.0, 10.0, float(scenario["cooking"]["energyPerMeal"]), 0.1, key=f"{prefix}_cooking_energyPerMeal")

    with st.expander("2. Water Fixtures", expanded=False):
        toilet_options = list(TOILET_TYPES.keys())
        shower_options = list(SHOWER_TYPES.keys())
        tap_options = list(TAP_TYPES.keys())

        toilet_type = select_or_blank("Toilet Type (L/flush)", toilet_options, f"{prefix}_toiletType", scenario.get("toiletType"))
        st.caption(f"{TOILET_TYPES[toilet_type]} L/flush (DUMMY)" if toilet_type else "L/flush: —")

        shower_type = select_or_blank("Shower Type (L/min)", shower_options, f"{prefix}_showerType", scenario.get("showerType"))
        st.caption(f"{SHOWER_TYPES[shower_type]} L/min (DUMMY)" if shower_type else "L/min: —")

        tap_type = select_or_blank("Tap Type (L/min)", tap_options, f"{prefix}_tapType", scenario.get("tapType"))
        st.caption(f"{TAP_TYPES[tap_type]} L/min (DUMMY)" if tap_type else "L/min: —")

    return {
        "climateZone": cz,
        "floorArea": float(floor_area),
        "ceilingHeight": float(ceiling_height),
        "householdSize": int(hh),

        "roofRValueLabel": roof_label,
        "roofRValue": float(roof_r) if roof_r is not None else None,
        "wallRValueLabel": wall_label,
        "wallRValue": float(wall_r) if wall_r is not None else None,
        "floorRValueLabel": floor_label,
        "floorRValue": float(floor_r) if floor_r is not None else None,

        "windowUValueLabel": win_label,
        "windowUValue": float(win_u) if win_u is not None else None,
        "windowArea": float(window_area),

        "heatingSystem": hs,
        "waterHeatingSystem": whs,

        "toiletType": toilet_type,
        "showerType": shower_type,
        "tapType": tap_type,

        "lighting": {"numberOfLights": int(n_lights), "wattsPerLight": float(watts_per_light), "hoursPerDay": float(hours_per_day)},
        "washingMachine": {"hasAppliance": bool(has_washer), "cyclesPerWeek": float(wash_cycles), "energyPerCycle": float(wash_kwh), "waterPerCycle": float(wash_L)},
        "dishwasher": {"hasAppliance": bool(has_dish), "cyclesPerWeek": float(dish_cycles), "energyPerCycle": float(dish_kwh), "waterPerCycle": float(dish_L)},
        "cooking": {"mealsPerWeek": float(meals_wk), "energyPerMeal": float(kwh_meal)},
    }

# =============================================================================
# LAYOUT: Baseline | Option | Results
# =============================================================================

col_base, col_opt, col_res = st.columns([1.05, 1.05, 1.45], gap="large")

with col_base:
    st.session_state.baseline = scenario_inputs_ui("Baseline Scenario", "BASE", st.session_state.baseline)

with col_opt:
    opt_top = st.columns([1.2, 1.2], gap="small")
    with opt_top[0]:
        if st.button("Copy Baseline → Option", use_container_width=True):
            st.session_state.option = deepcopy(st.session_state.baseline)
            st.session_state.has_calculated = False
    with opt_top[1]:
        st.caption("Option dropdowns also start blank by default.")
    st.session_state.option = scenario_inputs_ui("Option Scenario", "OPT", st.session_state.option)

# =============================================================================
# CALCULATE BUTTON / RESULTS
# =============================================================================

current_inputs_snapshot = {
    "advanced": st.session_state.advanced,
    "baseline": st.session_state.baseline,
    "option": st.session_state.option,
}
current_hash = stable_hash(current_inputs_snapshot)

with col_res:
    st.subheader("Results")

    action_row = st.columns([1.2, 1.0, 2.0], gap="small")
    with action_row[0]:
        calc_clicked = st.button("Calculate / Update Results", use_container_width=True)
    with action_row[1]:
        if st.button("Hide Results", use_container_width=True):
            st.session_state.has_calculated = False
            st.session_state.last_payload = None
            st.session_state.last_calc_hash = None
    with action_row[2]:
        st.caption("Results are shown only after you calculate. If you change inputs, calculate again.")

    if calc_clicked:
        if not scenario_ready(st.session_state.baseline):
            st.error("Baseline scenario belum lengkap. Semua dropdown utama harus dipilih dulu sebelum kalkulasi.")
        else:
            baseline_results = calculate_scenario(st.session_state.baseline, st.session_state.advanced)

            option_results = None
            if scenario_ready(st.session_state.option):
                option_results = calculate_scenario(st.session_state.option, st.session_state.advanced)

            savings = None
            if option_results is not None:
                savings = {
                    "electricity": baseline_results["totalElectricity"] - option_results["totalElectricity"],
                    "electricityPct": _pct(baseline_results["totalElectricity"], option_results["totalElectricity"]),
                    "water": baseline_results["waterConsumption"]["V_total"] - option_results["waterConsumption"]["V_total"],
                    "waterPct": _pct(baseline_results["waterConsumption"]["V_total"], option_results["waterConsumption"]["V_total"]),
                    "carbon": baseline_results["carbon"]["CO2_total"] - option_results["carbon"]["CO2_total"],
                    "carbonPct": _pct(baseline_results["carbon"]["CO2_total"], option_results["carbon"]["CO2_total"]),
                    "cost": baseline_results["costs"]["cost_total"] - option_results["costs"]["cost_total"],
                    "costPct": _pct(baseline_results["costs"]["cost_total"], option_results["costs"]["cost_total"]),
                }

            payload = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "advancedSettings": st.session_state.advanced,
                "baseline": {"inputs": st.session_state.baseline, "results": baseline_results},
                "option": {"inputs": st.session_state.option, "results": option_results},
                "savings": savings,
                "assumptions": {
                    "GRID_EMISSION_FACTOR": GRID_EMISSION_FACTOR,
                    "WATER_EMISSION_FACTOR": WATER_EMISSION_FACTOR,
                    "ELECTRICITY_TARIFF": ELECTRICITY_TARIFF,
                    "WATER_TARIFF": WATER_TARIFF,
                },
                "notes": "All coefficients are DUMMY placeholders. Model is early-stage comparative, not certification.",
            }

            st.session_state.last_payload = payload
            st.session_state.last_calc_hash = current_hash
            st.session_state.has_calculated = True

    if st.session_state.has_calculated and st.session_state.last_calc_hash != current_hash:
        st.warning("Inputs sudah berubah sejak kalkulasi terakhir. Klik **Calculate / Update Results** untuk refresh.")

    if not st.session_state.has_calculated or st.session_state.last_payload is None:
        st.info("Pilih input dulu (dropdown tidak ada default), lalu klik **Calculate / Update Results**.")
    else:
        payload = st.session_state.last_payload
        base_r = payload["baseline"]["results"]
        opt_r = payload["option"]["results"]
        savings = payload["savings"]

        if opt_r is None:
            st.markdown("**Baseline Results (Option belum lengkap, jadi tidak dihitung)**")
            rows = [
                {"Metric": "Total Energy Consumption", "Value": fmt(base_r["totalElectricity"], 1), "Unit": "kWh/year"},
                {"Metric": "Energy Intensity", "Value": fmt(base_r["energyIntensity"], 2), "Unit": "kWh/m²/year"},
                {"Metric": "Water Consumption", "Value": fmt(base_r["waterConsumption"]["V_total"], 2), "Unit": "m³/year"},
                {"Metric": "Operational Carbon", "Value": fmt(base_r["carbon"]["CO2_total"], 1), "Unit": "kgCO₂e/year"},
                {"Metric": "Annual Operating Cost", "Value": fmt0(base_r["costs"]["cost_total"]), "Unit": "NZD/year"},
            ]
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
        else:
            st.markdown("**Comparison (Baseline vs Option)**")
            kpis = [
                ("Total Energy Consumption", base_r["totalElectricity"], opt_r["totalElectricity"], "kWh/year", 1),
                ("Energy Intensity", base_r["energyIntensity"], opt_r["energyIntensity"], "kWh/m²/year", 2),
                ("Water Consumption", base_r["waterConsumption"]["V_total"], opt_r["waterConsumption"]["V_total"], "m³/year", 2),
                ("Operational Carbon", base_r["carbon"]["CO2_total"], opt_r["carbon"]["CO2_total"], "kgCO₂e/year", 1),
                ("Annual Operating Cost", base_r["costs"]["cost_total"], opt_r["costs"]["cost_total"], "NZD/year", 0),
            ]

            rows = []
            for label, base, opt, unit, dec in kpis:
                arrow = _trend_arrow(opt, base)
                rows.append({
                    "Metric": label,
                    "Baseline": fmt(base, dec) if dec > 0 else fmt0(base),
                    "Option": f"{(fmt(opt, dec) if dec > 0 else fmt0(opt))} {arrow}",
                    "Unit": unit,
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            with st.expander("Annual Savings Summary (Option vs Baseline)", expanded=True):
                def savings_line(name, value, pct, unit, decimals=1, currency=False):
                    sign = "−" if value > 0 else "+"
                    v = abs(value)
                    v_str = fmt0(v) if currency else fmt(v, decimals)
                    st.write(f"**{name}:** {sign}{v_str} {unit} ({pct:.1f}%)")

                savings_line("Energy", savings["electricity"], savings["electricityPct"], "kWh", decimals=1)
                savings_line("Water", savings["water"], savings["waterPct"], "m³", decimals=2)
                savings_line("Carbon", savings["carbon"], savings["carbonPct"], "kgCO₂e", decimals=1)
                savings_line("Cost", savings["cost"], savings["costPct"], "NZD", currency=True)

        st.download_button(
            label="Download Results (JSON)",
            data=json.dumps(payload, indent=2),
            file_name=f"housing-sustainability-comparison-{int(datetime.now().timestamp())}.json",
            mime="application/json",
            use_container_width=True,
        )
