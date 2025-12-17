# app.py
# Streamlit version with:
# - "Calculate / Update Results" button (results hidden until calculated)
# - Optional Option Scenario (disabled by default)
# - Option dropdowns start blank (to avoid “default choice bias”)
# - Numeric inputs still have sensible defaults
#
# Run:
#   streamlit run app.py

import json
import math
from copy import deepcopy
from datetime import datetime, timezone

import pandas as pd
import streamlit as st

# =============================================================================
# DUMMY COEFFICIENTS (PLACEHOLDERS) — keep as-is for now
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
# CALCULATION FUNCTIONS (same as React logic)
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
    deltaT = float(advanced["hotWaterTemp"]) - float(advanced["coldWaterTemp"])
    deltaT = max(deltaT, 0.0)

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

def create_default_scenario() -> dict:
    return {
        "climateZone": "Zone 3 (Mild - e.g., Wellington)",
        "floorArea": 120.0,
        "ceilingHeight": 2.4,
        "householdSize": 3,
        "roofRValueLabel": "Code minimum (R3.3)",
        "roofRValue": R_VALUES_ROOF["Code minimum (R3.3)"],
        "wallRValueLabel": "Code minimum (R2.0)",
        "wallRValue": R_VALUES_WALLS["Code minimum (R2.0)"],
        "floorRValueLabel": "Code minimum (R2.0)",
        "floorRValue": R_VALUES_FLOOR["Code minimum (R2.0)"],
        "windowUValueLabel": "Standard double glazed",
        "windowUValue": U_VALUES_WINDOWS["Standard double glazed"],
        "windowArea": 30.0,
        "heatingSystem": "Heat pump (COP 3.0)",
        "waterHeatingSystem": "Electric storage cylinder",
        "toiletType": "Dual flush standard (6/3L avg 5L)",
        "showerType": "Standard (9 L/min)",
        "tapType": "Standard (8 L/min)",
        "lighting": {
            "numberOfLights": LIGHTING_DEFAULTS["numberOfLights"],
            "wattsPerLight": LIGHTING_DEFAULTS["wattsPerLight"],
            "hoursPerDay": LIGHTING_DEFAULTS["hoursPerDay"],
        },
        "washingMachine": {
            "hasAppliance": True,
            "cyclesPerWeek": WASHING_MACHINE_DEFAULTS["cyclesPerWeek"],
            "energyPerCycle": WASHING_MACHINE_DEFAULTS["energyPerCycle"],
            "waterPerCycle": WASHING_MACHINE_DEFAULTS["waterPerCycle"],
        },
        "dishwasher": {
            "hasAppliance": True,
            "cyclesPerWeek": DISHWASHER_DEFAULTS["cyclesPerWeek"],
            "energyPerCycle": DISHWASHER_DEFAULTS["energyPerCycle"],
            "waterPerCycle": DISHWASHER_DEFAULTS["waterPerCycle"],
        },
        "cooking": {
            "mealsPerWeek": COOKING_DEFAULTS["mealsPerWeek"],
            "energyPerMeal": COOKING_DEFAULTS["energyPerMeal"],
        },
    }

def create_blank_option_scenario() -> dict:
    # Numeric defaults exist; dropdown selections intentionally blank (None)
    s = create_default_scenario()
    s.update({
        "climateZone": None,
        "roofRValueLabel": None, "roofRValue": None,
        "wallRValueLabel": None, "wallRValue": None,
        "floorRValueLabel": None, "floorRValue": None,
        "windowUValueLabel": None, "windowUValue": None,
        "heatingSystem": None,
        "waterHeatingSystem": None,
        "toiletType": None,
        "showerType": None,
        "tapType": None,
    })
    return s

def scenario_ready(s: dict) -> bool:
    required = [
        "climateZone",
        "roofRValue", "wallRValue", "floorRValue", "windowUValue",
        "heatingSystem", "waterHeatingSystem",
        "toiletType", "showerType", "tapType",
    ]
    for k in required:
        if s.get(k) is None:
            return False
    return True

def stable_hash(obj) -> str:
    return json.dumps(obj, sort_keys=True, default=str)

def _pct(base: float, opt: float) -> float:
    if abs(base) < 1e-12:
        return 0.0
    return ((base - opt) / base) * 100.0

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
    st.session_state.baseline = create_default_scenario()

if "option_enabled" not in st.session_state:
    st.session_state.option_enabled = False

if "option" not in st.session_state:
    st.session_state.option = create_blank_option_scenario()

if "show_advanced" not in st.session_state:
    st.session_state.show_advanced = False

if "has_calculated" not in st.session_state:
    st.session_state.has_calculated = False

if "last_calc_hash" not in st.session_state:
    st.session_state.last_calc_hash = None

if "last_payload" not in st.session_state:
    st.session_state.last_payload = None

# =============================================================================
# UI: HEADER + ACTIONS
# =============================================================================

st.title("NZ Housing Sustainability Calculator (Streamlit)")
st.write("Early-stage decision support tool for comparing housing scenarios. **Not a certification tool.**")
st.caption("All coefficients in this prototype are DUMMY placeholders (as in your React).")

top = st.columns([1.0, 1.0, 1.0, 2.5], gap="medium")
with top[0]:
    st.session_state.show_advanced = st.toggle("Show Advanced Settings", value=st.session_state.show_advanced)
with top[1]:
    st.session_state.option_enabled = st.toggle("Enable Option Scenario", value=st.session_state.option_enabled)
with top[2]:
    if st.button("Reset Option", use_container_width=True):
        st.session_state.option = create_blank_option_scenario()
        st.session_state.has_calculated = False
with top[3]:
    st.info(
        f"Assumptions (DUMMY): Grid EF={GRID_EMISSION_FACTOR} kgCO₂/kWh | Water EF={WATER_EMISSION_FACTOR} kgCO₂/m³ | "
        f"Tariffs: {ELECTRICITY_TARIFF} NZD/kWh, {WATER_TARIFF} NZD/m³"
    )

# Advanced Settings Panel
if st.session_state.show_advanced:
    with st.expander("Advanced Settings (DUMMY values - editable)", expanded=True):
        adv = deepcopy(st.session_state.advanced)
        adv["hotWaterPerPersonPerDay"] = st.number_input("Hot water (L/person/day)", min_value=0.0, max_value=300.0, value=float(adv["hotWaterPerPersonPerDay"]), step=5.0)
        adv["hotWaterTemp"] = st.number_input("Hot water temp (°C)", min_value=30.0, max_value=70.0, value=float(adv["hotWaterTemp"]), step=1.0)
        adv["coldWaterTemp"] = st.number_input("Cold water temp (°C)", min_value=0.0, max_value=30.0, value=float(adv["coldWaterTemp"]), step=1.0)
        adv["toiletFlushesPerDay"] = st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, value=float(adv["toiletFlushesPerDay"]), step=0.5)
        adv["showersPerDay"] = st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, value=float(adv["showersPerDay"]), step=0.1)
        adv["showerMinutes"] = st.number_input("Shower minutes", min_value=0.0, max_value=60.0, value=float(adv["showerMinutes"]), step=1.0)
        adv["tapMinutesPerDay"] = st.number_input("Tap minutes/person/day", min_value=0.0, max_value=60.0, value=float(adv["tapMinutesPerDay"]), step=1.0)
        st.session_state.advanced = adv

# =============================================================================
# INPUT UI (baseline + option)
# =============================================================================

def select_or_blank(label, options, key, value, placeholder="Select..."):
    """
    Returns selected option or None.
    Uses index=None when value is None (blank default).
    """
    if value is None:
        return st.selectbox(label, options=options, index=None, placeholder=placeholder, key=key)
    else:
        idx = options.index(value) if value in options else None
        return st.selectbox(label, options=options, index=idx, key=key)

def scenario_inputs_ui(title: str, prefix: str, scenario: dict, allow_blanks: bool) -> dict:
    st.subheader(title)

    with st.expander("1. Basic Information", expanded=True):
        cz_options = list(HDD_LOOKUP_BASE18.keys())
        if allow_blanks:
            cz = select_or_blank("Climate Zone (DUMMY HDD lookup)", cz_options, f"{prefix}_climateZone", scenario.get("climateZone"))
            if cz is not None:
                st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[cz]}** (DUMMY)")
            else:
                st.caption("HDD (base 18°C): —")
        else:
            cz = st.selectbox(
                "Climate Zone (DUMMY HDD lookup)",
                options=cz_options,
                index=cz_options.index(scenario["climateZone"]),
                key=f"{prefix}_climateZone",
            )
            st.caption(f"HDD (base 18°C): **{HDD_LOOKUP_BASE18[cz]}** (DUMMY)")

        floor_area = st.number_input("Floor Area (m²)", min_value=20.0, max_value=500.0, step=5.0, value=float(scenario["floorArea"]), key=f"{prefix}_floorArea")
        ceiling_height = st.number_input("Ceiling Height (m)", min_value=2.0, max_value=4.0, step=0.1, value=float(scenario["ceilingHeight"]), key=f"{prefix}_ceilingHeight")
        hh = st.number_input("Household Size", min_value=1, max_value=10, step=1, value=int(scenario["householdSize"]), key=f"{prefix}_householdSize")

    with st.expander("1.1 Thermal Envelope", expanded=False):
        roof_labels = list(R_VALUES_ROOF.keys())
        wall_labels = list(R_VALUES_WALLS.keys())
        floor_labels = list(R_VALUES_FLOOR.keys())
        win_labels = list(U_VALUES_WINDOWS.keys())

        if allow_blanks:
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
        else:
            roof_label = st.selectbox("Roof Insulation (R-value)", roof_labels, index=roof_labels.index(scenario["roofRValueLabel"]), key=f"{prefix}_roofRValueLabel")
            roof_r = float(R_VALUES_ROOF[roof_label])
            st.caption(f"R = {roof_r:.1f}, U = {1/roof_r:.2f} W/m²K (DUMMY)")

            wall_label = st.selectbox("Wall Insulation (R-value)", wall_labels, index=wall_labels.index(scenario["wallRValueLabel"]), key=f"{prefix}_wallRValueLabel")
            wall_r = float(R_VALUES_WALLS[wall_label])
            st.caption(f"R = {wall_r:.1f}, U = {1/wall_r:.2f} W/m²K (DUMMY)")

            floor_label = st.selectbox("Floor Insulation (R-value)", floor_labels, index=floor_labels.index(scenario["floorRValueLabel"]), key=f"{prefix}_floorRValueLabel")
            floor_r = float(R_VALUES_FLOOR[floor_label])
            st.caption(f"R = {floor_r:.1f}, U = {1/floor_r:.2f} W/m²K (DUMMY)")

            win_label = st.selectbox("Window Type (U-value)", win_labels, index=win_labels.index(scenario["windowUValueLabel"]), key=f"{prefix}_windowUValueLabel")
            win_u = float(U_VALUES_WINDOWS[win_label])
            st.caption(f"U = {win_u:.1f} W/m²K (DUMMY)")

        window_area = st.number_input("Total Window Area (m²)", min_value=5.0, max_value=100.0, step=5.0, value=float(scenario["windowArea"]), key=f"{prefix}_windowArea")
        if float(floor_area) > 0:
            st.caption(f"~{(window_area / float(floor_area) * 100.0):.0f}% of floor area")

    with st.expander("1.1.4 Space Heating System", expanded=False):
        hs_options = list(HEATING_SYSTEMS.keys())
        if allow_blanks:
            hs = select_or_blank("Heating System Type (efficiency/COP)", hs_options, f"{prefix}_heatingSystem", scenario.get("heatingSystem"))
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[hs]}** (DUMMY)" if hs else "Efficiency/COP: —")
        else:
            hs = st.selectbox("Heating System Type (efficiency/COP)", hs_options, index=hs_options.index(scenario["heatingSystem"]), key=f"{prefix}_heatingSystem")
            st.caption(f"Efficiency/COP: **{HEATING_SYSTEMS[hs]}** (DUMMY)")

    with st.expander("1.2 Water Heating System", expanded=False):
        whs_options = list(WATER_HEATING_SYSTEMS.keys())
        if allow_blanks:
            whs = select_or_blank("Water Heating Type (efficiency/COP)", whs_options, f"{prefix}_waterHeatingSystem", scenario.get("waterHeatingSystem"))
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[whs]}** (DUMMY)" if whs else "Efficiency/COP: —")
        else:
            whs = st.selectbox("Water Heating Type (efficiency/COP)", whs_options, index=whs_options.index(scenario["waterHeatingSystem"]), key=f"{prefix}_waterHeatingSystem")
            st.caption(f"Efficiency/COP: **{WATER_HEATING_SYSTEMS[whs]}** (DUMMY)")

    with st.expander("1.3 Lighting & Appliances", expanded=False):
        n_lights = st.number_input("# Lights", min_value=0, max_value=200, step=1, value=int(scenario["lighting"]["numberOfLights"]), key=f"{prefix}_lighting_numberOfLights")
        watts_per_light = st.number_input("Watts per light", min_value=0.0, max_value=200.0, step=1.0, value=float(scenario["lighting"]["wattsPerLight"]), key=f"{prefix}_lighting_wattsPerLight")
        hours_per_day = st.number_input("Lighting hours/day", min_value=0.0, max_value=24.0, step=0.5, value=float(scenario["lighting"]["hoursPerDay"]), key=f"{prefix}_lighting_hoursPerDay")

        st.markdown("**Washing Machine**")
        has_washer = st.checkbox("Has washing machine", value=bool(scenario["washingMachine"]["hasAppliance"]), key=f"{prefix}_washing_hasAppliance")
        if has_washer:
            wash_cycles = st.number_input("Cycles/week (washing)", min_value=0.0, max_value=30.0, step=1.0, value=float(scenario["washingMachine"]["cyclesPerWeek"]), key=f"{prefix}_washing_cyclesPerWeek")
            wash_kwh = st.number_input("kWh/cycle (washing)", min_value=0.0, max_value=10.0, step=0.1, value=float(scenario["washingMachine"]["energyPerCycle"]), key=f"{prefix}_washing_energyPerCycle")
            wash_L = st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, value=float(scenario["washingMachine"]["waterPerCycle"]), key=f"{prefix}_washing_waterPerCycle")
        else:
            wash_cycles, wash_kwh, wash_L = 0.0, 0.0, 0.0

        st.markdown("**Dishwasher**")
        has_dish = st.checkbox("Has dishwasher", value=bool(scenario["dishwasher"]["hasAppliance"]), key=f"{prefix}_dish_hasAppliance")
        if has_dish:
            dish_cycles = st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=30.0, step=1.0, value=float(scenario["dishwasher"]["cyclesPerWeek"]), key=f"{prefix}_dish_cyclesPerWeek")
            dish_kwh = st.number_input("kWh/cycle (dishwasher)", min_value=0.0, max_value=10.0, step=0.1, value=float(scenario["dishwasher"]["energyPerCycle"]), key=f"{prefix}_dish_energyPerCycle")
            dish_L = st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=200.0, step=1.0, value=float(scenario["dishwasher"]["waterPerCycle"]), key=f"{prefix}_dish_waterPerCycle")
        else:
            dish_cycles, dish_kwh, dish_L = 0.0, 0.0, 0.0

        st.markdown("**Cooking**")
        meals_wk = st.number_input("Meals/week", min_value=0.0, max_value=100.0, step=1.0, value=float(scenario["cooking"]["mealsPerWeek"]), key=f"{prefix}_cooking_mealsPerWeek")
        kwh_meal = st.number_input("kWh/meal", min_value=0.0, max_value=10.0, step=0.1, value=float(scenario["cooking"]["energyPerMeal"]), key=f"{prefix}_cooking_energyPerMeal")

    with st.expander("2. Water Fixtures", expanded=False):
        toilet_options = list(TOILET_TYPES.keys())
        shower_options = list(SHOWER_TYPES.keys())
        tap_options = list(TAP_TYPES.keys())

        if allow_blanks:
            toilet_type = select_or_blank("Toilet Type (L/flush)", toilet_options, f"{prefix}_toiletType", scenario.get("toiletType"))
            st.caption(f"{TOILET_TYPES[toilet_type]} L/flush (DUMMY)" if toilet_type else "L/flush: —")

            shower_type = select_or_blank("Shower Type (L/min)", shower_options, f"{prefix}_showerType", scenario.get("showerType"))
            st.caption(f"{SHOWER_TYPES[shower_type]} L/min (DUMMY)" if shower_type else "L/min: —")

            tap_type = select_or_blank("Tap Type (L/min)", tap_options, f"{prefix}_tapType", scenario.get("tapType"))
            st.caption(f"{TAP_TYPES[tap_type]} L/min (DUMMY)" if tap_type else "L/min: —")
        else:
            toilet_type = st.selectbox("Toilet Type (L/flush)", toilet_options, index=toilet_options.index(scenario["toiletType"]), key=f"{prefix}_toiletType")
            st.caption(f"{TOILET_TYPES[toilet_type]} L/flush (DUMMY)")
            shower_type = st.selectbox("Shower Type (L/min)", shower_options, index=shower_options.index(scenario["showerType"]), key=f"{prefix}_showerType")
            st.caption(f"{SHOWER_TYPES[shower_type]} L/min (DUMMY)")
            tap_type = st.selectbox("Tap Type (L/min)", tap_options, index=tap_options.index(scenario["tapType"]), key=f"{prefix}_tapType")
            st.caption(f"{TAP_TYPES[tap_type]} L/min (DUMMY)")

    updated = {
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
    return updated

# =============================================================================
# LAYOUT: Baseline | Option | Results
# =============================================================================

col_base, col_opt, col_res = st.columns([1.05, 1.05, 1.45], gap="large")

with col_base:
    st.session_state.baseline = scenario_inputs_ui("Baseline Scenario", "BASE", st.session_state.baseline, allow_blanks=False)

with col_opt:
    if st.session_state.option_enabled:
        opt_top = st.columns([1.2, 1.2], gap="small")
        with opt_top[0]:
            if st.button("Copy Baseline → Option", use_container_width=True):
                # Copy baseline then force user to make explicit selections? (keep copied values)
                st.session_state.option = deepcopy(st.session_state.baseline)
                st.session_state.has_calculated = False
        with opt_top[1]:
            st.caption("Tip: if you want “blank dropdowns”, click Reset Option.")
        st.session_state.option = scenario_inputs_ui("Option Scenario", "OPT", st.session_state.option, allow_blanks=True)
    else:
        st.subheader("Option Scenario")
        st.info("Option scenario is disabled. Enable it above if you want to compare two scenarios.")

# =============================================================================
# CALCULATE BUTTON (results only appear after this)
# =============================================================================

current_inputs_snapshot = {
    "advanced": st.session_state.advanced,
    "baseline": st.session_state.baseline,
    "option_enabled": st.session_state.option_enabled,
    "option": st.session_state.option if st.session_state.option_enabled else None,
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
        # Baseline must always be ready
        if not scenario_ready(st.session_state.baseline):
            st.error("Baseline scenario is incomplete. Please complete required selections.")
        else:
            baseline_results = calculate_scenario(st.session_state.baseline, st.session_state.advanced)

            option_results = None
            if st.session_state.option_enabled:
                if scenario_ready(st.session_state.option):
                    option_results = calculate_scenario(st.session_state.option, st.session_state.advanced)
                else:
                    option_results = None

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
                "option_enabled": st.session_state.option_enabled,
                "option": {"inputs": st.session_state.option, "results": option_results} if st.session_state.option_enabled else None,
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

    # Show status if user changed inputs after last calc
    if st.session_state.has_calculated and st.session_state.last_calc_hash != current_hash:
        st.warning("Inputs have changed since the last calculation. Click **Calculate / Update Results** to refresh results.")

    # Render results (only if calculated)
    if not st.session_state.has_calculated or st.session_state.last_payload is None:
        st.info("Set your inputs, then click **Calculate / Update Results** to display results.")
    else:
        payload = st.session_state.last_payload
        base_r = payload["baseline"]["results"]
        opt_r = payload["option"]["results"] if payload["option_enabled"] and payload["option"] else None
        savings = payload["savings"]

        # KPI display
        if opt_r is None:
            st.markdown("**Baseline Results (Option not configured yet)**")

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

        # Breakdowns behind expanders
        with st.expander("Energy Breakdown", expanded=False):
            eb = pd.DataFrame([
                {"Component": "Space Heating", "Baseline": base_r["spaceHeating"]["Q_purchased"], "Option": (opt_r["spaceHeating"]["Q_purchased"] if opt_r else None)},
                {"Component": "Water Heating", "Baseline": base_r["waterHeating"]["Q_purchased"], "Option": (opt_r["waterHeating"]["Q_purchased"] if opt_r else None)},
                {"Component": "Lighting & Appliances", "Baseline": base_r["lightingAppliances"]["Q_total"], "Option": (opt_r["lightingAppliances"]["Q_total"] if opt_r else None)},
            ])
            st.dataframe(eb, use_container_width=True, hide_index=True)

        with st.expander("Water Breakdown", expanded=False):
            wb = pd.DataFrame([
                {"End-use": "Toilets", "Baseline": base_r["waterConsumption"]["breakdown"]["V_toilet"], "Option": (opt_r["waterConsumption"]["breakdown"]["V_toilet"] if opt_r else None)},
                {"End-use": "Showers", "Baseline": base_r["waterConsumption"]["breakdown"]["V_shower"], "Option": (opt_r["waterConsumption"]["breakdown"]["V_shower"] if opt_r else None)},
                {"End-use": "Taps", "Baseline": base_r["waterConsumption"]["breakdown"]["V_taps"], "Option": (opt_r["waterConsumption"]["breakdown"]["V_taps"] if opt_r else None)},
                {"End-use": "Washing Machine", "Baseline": base_r["waterConsumption"]["breakdown"]["V_laundry"], "Option": (opt_r["waterConsumption"]["breakdown"]["V_laundry"] if opt_r else None)},
                {"End-use": "Dishwasher", "Baseline": base_r["waterConsumption"]["breakdown"]["V_dishwasher"], "Option": (opt_r["waterConsumption"]["breakdown"]["V_dishwasher"] if opt_r else None)},
            ])
            st.dataframe(wb, use_container_width=True, hide_index=True)

        with st.expander("Carbon Breakdown", expanded=False):
            cb = pd.DataFrame([
                {"Source": "Electricity", "Baseline": base_r["carbon"]["CO2_electricity"], "Option": (opt_r["carbon"]["CO2_electricity"] if opt_r else None)},
                {"Source": "Water", "Baseline": base_r["carbon"]["CO2_water"], "Option": (opt_r["carbon"]["CO2_water"] if opt_r else None)},
            ])
            st.dataframe(cb, use_container_width=True, hide_index=True)

        with st.expander("Cost Breakdown", expanded=False):
            costb = pd.DataFrame([
                {"Source": "Electricity cost", "Baseline": base_r["costs"]["cost_electricity"], "Option": (opt_r["costs"]["cost_electricity"] if opt_r else None)},
                {"Source": "Water cost", "Baseline": base_r["costs"]["cost_water"], "Option": (opt_r["costs"]["cost_water"] if opt_r else None)},
            ])
            st.dataframe(costb, use_container_width=True, hide_index=True)

        # Download JSON
        st.download_button(
            label="Download Results (JSON)",
            data=json.dumps(payload, indent=2),
            file_name=f"housing-sustainability-comparison-{int(datetime.now().timestamp())}.json",
            mime="application/json",
            use_container_width=True,
        )
