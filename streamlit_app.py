import streamlit as st
import pandas as pd

# =========================
# ENERGY & CLIMATE (NZ-ANCHORED)
# =========================

# Climate bands: baseline space heating demand (kWh/m²/year)
# Back-calculated from ~7,000 kWh/yr per dwelling and HEEP end-use shares,
# then scaled for mild/temperate/cold zones :contentReference[oaicite:0]{index=0}
Q_HEAT_BASE = {
    "Mild": 15.0,       # e.g. northern coastal cities
    "Temperate": 25.0,  # around national average
    "Cold": 40.0,       # inland / southern colder zones
}

# Dwelling type -> facade area factor (A_facade ≈ k * A_floor)
# Stylised geometry (no single NZ source, just pattern: detached > semi > apartment)
K_FACADE = {
    "Freestanding house": 1.2,
    "Semi-detached / end unit": 0.9,
    "Mid-floor apartment": 0.6,
}

# Window area category -> window-to-wall ratio (WWR)
# Stylised low/typical/high categories (kept as simple buckets)
WWR = {
    "Low window area": 0.15,
    "Medium (typical)": 0.25,
    "High window area": 0.40,
}

# Wall performance -> U-value (W/m²K)
# Aligned loosely with H1 / NZ practice:
# - Uninsulated wall ~1.8
# - Code-like wall R~1.6 → U≈0.6
# - Better-than-code wall R~2.5 → U≈0.4 :contentReference[oaicite:1]{index=1}
U_WALL = {
    "Very poor / uninsulated": 1.8,
    "Typical NZ Code-like": 0.6,
    "Improved insulation": 0.4,
}

# Window type -> U-value (W/m²K)
# From NZ glazing suppliers: single ~5, standard double ~2.5, low-E+argon ~1.3–1.8 :contentReference[oaicite:2]{index=2}
U_WINDOW = {
    "Mostly single glazing": 5.0,
    "Standard double glazing": 2.5,
    "High-performance double / Low-E": 1.5,
}

# Baseline geometry & U-values for HeatLoss_base (per m² floor) – "typical NZ new house"
BASELINE_DWELLING_TYPE = "Freestanding house"
BASELINE_WINDOW_AREA = "Medium (typical)"
BASELINE_WALL_PERF = "Typical NZ Code-like"
BASELINE_GLAZING = "Standard double glazing"

# Other loads baseline (lighting + plugs etc.)
# Stylised: from HEEP, non-heating / non-hot-water uses ≈ half of electricity use → ~25 kWh/m²/yr for a 120m² home :contentReference[oaicite:3]{index=3}
Q_OTHER_BASE = 25.0  # kWh/m²/year

# Hot water energy per m³ (kWh/m³)
# Physics-based: E(kWh) ≈ Volume(L) * ΔT(°C) / 860; for ΔT≈40°C → ~46 kWh/m³ :contentReference[oaicite:4]{index=4}
E_HW_BASE = 46.0

# Heating system COP (stylised but within NZ ranges)
COP_HEAT = {
    "None": 0.0,
    "Portable electric heaters": 0.95,      # resistive
    "Panel / convector heaters": 0.95,      # resistive
    "Heat pump (split system)": 3.0,        # typical seasonal COP
}

# Water heating system COP / efficiency
# HW heat pumps around 3–4; cylinders ~0.9 :contentReference[oaicite:5]{index=5}
COP_HW = {
    "Electric cylinder": 0.9,
    "Heat pump water heater": 3.0,
}

# Heating coverage -> fraction of floor area heated (stylised)
F_COVERAGE = {
    "Only living room": 0.4,
    "Living + some bedrooms": 0.7,
    "Most of the house": 1.0,
}

# Grid emission factor & tariff (NZ)
# MfE grid factor around 0.12 kgCO2e/kWh in recent factor sets :contentReference[oaicite:6]{index=6}
EF_EL = 0.12  # kgCO2e/kWh

# Residential electricity prices ~33–35 c/kWh (MBIE, PowerCompare, Insurspy) :contentReference[oaicite:7]{index=7}
P_EL = 0.34   # NZD/kWh (incl. GST, national average order-of-magnitude)

# =========================
# WATER USE & FIXTURES (NZ-ANCHORED)
# =========================

# Usage assumptions (per person per day)
# Tuned so that total ≈ 160–230 L/person/day, consistent with BRANZ SR469 medians :contentReference[oaicite:8]{index=8}
U_FIXTURES = {
    "toilet_flushes": 5.0,      # flush/person/day
    "shower_minutes": 8.0,      # min/person/day
    "basin_minutes": 4.0,       # min/person/day
    "kitchen_minutes": 5.0,     # min/person/day
}

# Flow/volume per use (litres) for fixtures

# Toilet – volumes per flush; NZ dual-flush around 3/4.5 L half/full; old single flush higher :contentReference[oaicite:9]{index=9}
V_TOILET = {
    "Single flush": 11.0,               # older cistern
    "Dual flush (standard)": 6.0,       # typical mixed-use average
    "Dual flush (efficient)": 4.0,      # better-performing units
}

# Showers – EECA & BRANZ recommend ≤9 L/min for efficient heads; older heads 15–20 L/min :contentReference[oaicite:10]{index=10}
V_SHOWER = {
    "Standard shower head": 9.0,   # L/min (assume already better than very old 15–20 L/min)
    "Efficient shower head": 6.0,
}

V_BASIN = {
    "Standard basin tap": 6.0,     # L/min (typical)
    "Efficient basin tap": 4.0,
}

V_KITCHEN = {
    "Standard kitchen tap": 8.0,   # L/min
    "Efficient kitchen tap": 6.0,
}

# Hot water fractions (stylised but consistent with end-use breakdowns) :contentReference[oaicite:11]{index=11}
H_FIXTURES = {
    "toilet": 0.0,
    "shower": 0.8,
    "basin": 0.3,
    "kitchen": 0.7,
    "laundry": 0.3,
    "dishwasher": 0.9,
}

# Laundry assumptions

# Loads per week per household – stylised lifestyle categories
LAUNDRY_LOADS_PER_WEEK = {
    "Low (1–2 loads/week)": 2,
    "Medium (3–5 loads/week)": 4,
    "High (6+ loads/week)": 7,
}

# Water per load from Consumer NZ: 8.5kg top loader ≈135 L/3.5kg load; 8.5kg front loader ≈64 L :contentReference[oaicite:12]{index=12}
LAUNDRY_L_PER_LOAD = {
    "Hand wash": 40.0,             # still stylised
    "Standard machine": 135.0,     # treat as typical top loader
    "Efficient machine": 64.0,     # treat as front loader
}

# Energy per load – order-of-magnitude based on EECA/appliance data
LAUNDRY_KWH_PER_LOAD = {
    "Hand wash": 0.0,
    "Standard machine": 0.7,
    "Efficient machine": 0.4,
}

# Dishwasher assumptions
DW_CYCLES_PER_WEEK = {
    "Low": 2,
    "Medium": 4,
    "High": 7,
}

# Typical modern dishwasher Eco cycle ~10–12 L and ~0.8 kWh per wash :contentReference[oaicite:13]{index=13}
DW_L_PER_CYCLE = 12.0
DW_KWH_PER_CYCLE = 0.8

# =========================
# EMBODIED CARBON (NZ CONTEXT)
# =========================

# Embodied carbon intensities (kgCO2e/m² floor area, over 50 years – stylised)
# Anchored to ranges from NZGBC Embodied Carbon Methodology and BRANZ/LCAQuick examples :contentReference[oaicite:14]{index=14}
EC_STRUCTURE = {
    "Conventional timber": 120.0,
    "Engineered timber (LVL/CLT)": 90.0,
    "Higher-carbon structure": 200.0,   # e.g. heavy concrete/steel mix
}

EC_FLOOR = {
    "Standard concrete slab": 110.0,
    "Low-cement concrete": 80.0,
    "Timber floor system": 60.0,
}

EC_WALLS = {
    "Standard cladding mix": 50.0,
    "Lower-carbon cladding": 35.0,
}

EC_ROOF = {
    "Standard metal roof": 45.0,
    "Lower-carbon roof": 30.0,
}


# =========================
# HELPER FUNCTIONS
# =========================

def heatloss_base_per_m2():
    """Compute baseline HeatLoss per m² floor for ratio (typical house)."""
    kf = K_FACADE[BASELINE_DWELLING_TYPE]
    wwr = WWR[BASELINE_WINDOW_AREA]
    u_wall = U_WALL[BASELINE_WALL_PERF]
    u_win = U_WINDOW[BASELINE_GLAZING]
    # Per m² floor => A_facade = kf * 1; A_window = wwr * A_facade; A_wall = A_facade - A_window
    a_facade = kf * 1.0
    a_window = wwr * a_facade
    a_wall = a_facade - a_window
    return u_wall * a_wall + u_win * a_window


HEATLOSS_BASE_PER_M2 = heatloss_base_per_m2()


def compute_scenario(inputs: dict) -> dict:
    """Compute all KPIs for one scenario based on user inputs."""
    # Unpack inputs
    climate_band = inputs["climate_band"]
    dwelling_type = inputs["dwelling_type"]
    window_area_cat = inputs["window_area_cat"]
    wall_perf = inputs["wall_perf"]
    glazing_type = inputs["glazing_type"]
    floor_area = inputs["floor_area"]
    n_occ = inputs["n_occ"]
    heating_system = inputs["heating_system"]
    heating_coverage = inputs["heating_coverage"]
    water_heating_system = inputs["water_heating_system"]
    toilet_type = inputs["toilet_type"]
    shower_type = inputs["shower_type"]
    basin_tap_type = inputs["basin_tap_type"]
    kitchen_tap_type = inputs["kitchen_tap_type"]
    laundry_use = inputs["laundry_use"]
    laundry_type = inputs["laundry_type"]
    laundry_freq = inputs["laundry_freq"]
    dishwasher_use = inputs["dishwasher_use"]
    dishwasher_freq = inputs["dishwasher_freq"]
    structure_opt = inputs["structure_opt"]
    floor_opt = inputs["floor_opt"]
    wall_opt = inputs["wall_opt"]
    roof_opt = inputs["roof_opt"]

    # ---------- Space heating demand ----------
    q_heat_base = Q_HEAT_BASE[climate_band]
    kf = K_FACADE[dwelling_type]
    wwr = WWR[window_area_cat]
    u_wall = U_WALL[wall_perf]
    u_win = U_WINDOW[glazing_type]

    # Heat loss per m² floor for this scenario
    a_facade_per_m2 = kf * 1.0
    a_window_per_m2 = wwr * a_facade_per_m2
    a_wall_per_m2 = a_facade_per_m2 - a_window_per_m2
    heatloss_opt_per_m2 = u_wall * a_wall_per_m2 + u_win * a_window_per_m2

    # Scale q_heat
    ratio = heatloss_opt_per_m2 / HEATLOSS_BASE_PER_M2 if HEATLOSS_BASE_PER_M2 > 0 else 1.0
    q_heat = q_heat_base * ratio

    # Heating energy
    f_cov = F_COVERAGE[heating_coverage]
    a_heated = f_cov * floor_area
    cop_h = COP_HEAT[heating_system]
    if cop_h <= 0 or a_heated <= 0:
        e_space_heating = 0.0
    else:
        e_space_heating = q_heat * a_heated / cop_h

    # ---------- Water & hot water ----------
    days = 365.0
    v_total = 0.0
    v_hot = 0.0

    # Toilet
    v_toilet_l_year = (
        U_FIXTURES["toilet_flushes"]
        * n_occ
        * days
        * V_TOILET[toilet_type]
    )
    v_toilet_m3 = v_toilet_l_year / 1000.0
    v_total += v_toilet_m3
    v_hot += v_toilet_m3 * H_FIXTURES["toilet"]  # = 0

    # Shower
    v_shower_l_year = (
        U_FIXTURES["shower_minutes"]
        * n_occ
        * days
        * V_SHOWER[shower_type]
    )
    v_shower_m3 = v_shower_l_year / 1000.0
    v_total += v_shower_m3
    v_hot += v_shower_m3 * H_FIXTURES["shower"]

    # Basin
    v_basin_l_year = (
        U_FIXTURES["basin_minutes"]
        * n_occ
        * days
        * V_BASIN[basin_tap_type]
    )
    v_basin_m3 = v_basin_l_year / 1000.0
    v_total += v_basin_m3
    v_hot += v_basin_m3 * H_FIXTURES["basin"]

    # Kitchen
    v_kitchen_l_year = (
        U_FIXTURES["kitchen_minutes"]
        * n_occ
        * days
        * V_KITCHEN[kitchen_tap_type]
    )
    v_kitchen_m3 = v_kitchen_l_year / 1000.0
    v_total += v_kitchen_m3
    v_hot += v_kitchen_m3 * H_FIXTURES["kitchen"]

    # Laundry
    e_laundry = 0.0
    v_laundry_m3 = 0.0
    v_laundry_hot_m3 = 0.0
    if laundry_use == "Yes":
        loads_per_week = LAUNDRY_LOADS_PER_WEEK[laundry_freq]
        l_per_load = LAUNDRY_L_PER_LOAD[laundry_type]
        kwh_per_load = LAUNDRY_KWH_PER_LOAD[laundry_type]
        loads_per_year = loads_per_week * 52.0

        v_laundry_l_year = loads_per_year * l_per_load
        v_laundry_m3 = v_laundry_l_year / 1000.0
        e_laundry = loads_per_year * kwh_per_load
        v_laundry_hot_m3 = v_laundry_m3 * H_FIXTURES["laundry"]

        v_total += v_laundry_m3
        v_hot += v_laundry_hot_m3

    # Dishwasher
    e_dw = 0.0
    v_dw_m3 = 0.0
    v_dw_hot_m3 = 0.0
    if dishwasher_use == "Yes":
        cycles_per_week = DW_CYCLES_PER_WEEK[dishwasher_freq]
        cycles_per_year = cycles_per_week * 52.0
        v_dw_l_year = cycles_per_year * DW_L_PER_CYCLE
        v_dw_m3 = v_dw_l_year / 1000.0
        e_dw = cycles_per_year * DW_KWH_PER_CYCLE
        v_dw_hot_m3 = v_dw_m3 * H_FIXTURES["dishwasher"]

        v_total += v_dw_m3
        v_hot += v_dw_hot_m3

    # ---------- Hot water energy ----------
    e_hw_theoretical = v_hot * E_HW_BASE
    cop_hw = COP_HW[water_heating_system]
    if cop_hw <= 0:
        e_water_heating = e_hw_theoretical  # assume resistance
    else:
        e_water_heating = e_hw_theoretical / cop_hw

    # ---------- Other loads ----------
    e_other_base = Q_OTHER_BASE * floor_area
    e_other = e_other_base + e_laundry + e_dw

    # ---------- Total energy, carbon, cost ----------
    e_total = e_space_heating + e_water_heating + e_other
    c_operational = e_total * EF_EL
    cost_energy = e_total * P_EL

    # ---------- Embodied carbon ----------
    ec_total_intensity = (
        EC_STRUCTURE[structure_opt]
        + EC_FLOOR[floor_opt]
        + EC_WALLS[wall_opt]
        + EC_ROOF[roof_opt]
    )
    c_embodied = ec_total_intensity * floor_area

    outputs = {
        "E_total": e_total,
        "q_heat": q_heat,
        "E_space_heating": e_space_heating,
        "E_water_heating": e_water_heating,
        "E_other": e_other,
        "V_total": v_total,
        "V_hot": v_hot,
        "C_operational": c_operational,
        "Cost_energy": cost_energy,
        "EC_total_intensity": ec_total_intensity,
        "C_embodied": c_embodied,
    }
    return outputs


def scenario_input_ui(label_prefix: str = "Scenario") -> dict:
    """Builds Streamlit inputs and returns a dict of scenario inputs."""
    st.subheader(label_prefix)

    climate_band = st.selectbox(
        f"{label_prefix} – Climate band",
        list(Q_HEAT_BASE.keys()),
        index=1,
    )

    dwelling_type = st.selectbox(
        f"{label_prefix} – Dwelling type",
        list(K_FACADE.keys()),
    )

    col_a, col_b = st.columns(2)
    with col_a:
        floor_area = st.number_input(
            f"{label_prefix} – Floor area (m²)",
            min_value=30.0,
            max_value=400.0,
            value=120.0,
            step=5.0,
        )
    with col_b:
        n_occ = st.number_input(
            f"{label_prefix} – Number of occupants",
            min_value=1,
            max_value=8,
            value=3,
            step=1,
        )

    window_area_cat = st.selectbox(
        f"{label_prefix} – Window area category",
        list(WWR.keys()),
        index=1,
    )

    wall_perf = st.selectbox(
        f"{label_prefix} – Wall performance",
        list(U_WALL.keys()),
        index=1,
    )

    glazing_type = st.selectbox(
        f"{label_prefix} – Window type",
        list(U_WINDOW.keys()),
        index=1,
    )

    st.markdown("**Heating and hot water**")

    heating_system = st.selectbox(
        f"{label_prefix} – Main space heating system",
        list(COP_HEAT.keys()),
        index=3,  # default heat pump
    )

    heating_coverage = st.selectbox(
        f"{label_prefix} – Heating coverage",
        list(F_COVERAGE.keys()),
        index=1,
    )

    water_heating_system = st.selectbox(
        f"{label_prefix} – Water heating system",
        list(COP_HW.keys()),
        index=0,
    )

    st.markdown("** Fixtures and water use **")

    col1, col2 = st.columns(2)
    with col1:
        toilet_type = st.selectbox(
            f"{label_prefix} – Toilet type",
            list(V_TOILET.keys()),
            index=1,
        )
        basin_tap_type = st.selectbox(
            f"{label_prefix} – Basin tap type",
            list(V_BASIN.keys()),
            index=0,
        )
    with col2:
        shower_type = st.selectbox(
            f"{label_prefix} – Shower head type",
            list(V_SHOWER.keys()),
            index=0,
        )
        kitchen_tap_type = st.selectbox(
            f"{label_prefix} – Kitchen tap type",
            list(V_KITCHEN.keys()),
            index=0,
        )

    st.markdown("** Laundry and dishwasher **")

    laundry_use = st.selectbox(
        f"{label_prefix} – Do you wash clothes at home?",
        ["Yes", "No"],
        index=0,
    )

    if laundry_use == "Yes":
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            laundry_type = st.selectbox(
                f"{label_prefix} – Laundry type",
                list(LAUNDRY_L_PER_LOAD.keys()),
                index=1,
            )
        with col_l2:
            laundry_freq = st.selectbox(
                f"{label_prefix} – Laundry frequency",
                list(LAUNDRY_LOADS_PER_WEEK.keys()),
                index=1,
            )
    else:
        laundry_type = "Standard machine"
        laundry_freq = "Low (1–2 loads/week)"

    dishwasher_use = st.selectbox(
        f"{label_prefix} – Do you use a dishwasher?",
        ["Yes", "No"],
        index=1,
    )

    if dishwasher_use == "Yes":
        dishwasher_freq = st.selectbox(
            f"{label_prefix} – Dishwasher frequency",
            list(DW_CYCLES_PER_WEEK.keys()),
            index=1,
        )
    else:
        dishwasher_freq = "Low"

    st.markdown("** Materials (embodied carbon) **")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        structure_opt = st.selectbox(
            f"{label_prefix} – Structure option",
            list(EC_STRUCTURE.keys()),
            index=0,
        )
        wall_opt = st.selectbox(
            f"{label_prefix} – Walls / cladding option",
            list(EC_WALLS.keys()),
            index=0,
        )
    with col_m2:
        floor_opt = st.selectbox(
            f"{label_prefix} – Floor / slab option",
            list(EC_FLOOR.keys()),
            index=0,
        )
        roof_opt = st.selectbox(
            f"{label_prefix} – Roof option",
            list(EC_ROOF.keys()),
            index=0,
        )

    scenario_inputs = {
        "climate_band": climate_band,
        "dwelling_type": dwelling_type,
        "window_area_cat": window_area_cat,
        "wall_perf": wall_perf,
        "glazing_type": glazing_type,
        "floor_area": floor_area,
        "n_occ": n_occ,
        "heating_system": heating_system,
        "heating_coverage": heating_coverage,
        "water_heating_system": water_heating_system,
        "toilet_type": toilet_type,
        "shower_type": shower_type,
        "basin_tap_type": basin_tap_type,
        "kitchen_tap_type": kitchen_tap_type,
        "laundry_use": laundry_use,
        "laundry_type": laundry_type,
        "laundry_freq": laundry_freq,
        "dishwasher_use": dishwasher_use,
        "dishwasher_freq": dishwasher_freq,
        "structure_opt": structure_opt,
        "floor_opt": floor_opt,
        "wall_opt": wall_opt,
        "roof_opt": roof_opt,
    }

    return scenario_inputs


# =========================
# STREAMLIT APP
# =========================

st.title("Early-stage NZ Housing Sustainability Prototype (dummy model)")
st.write(
    """
This is a **prototype** calculator with dummy parameters.  
It compares a **Baseline** scenario with an **Option** scenario for energy, water, carbon, and cost.
"""
)

tab1, tab2 = st.tabs(["Inputs", "Results"])

with tab1:
    col_left, col_right = st.columns(2)

    with col_left:
        baseline_inputs = scenario_input_ui("Baseline scenario")

    with col_right:
        option_inputs = scenario_input_ui("Option scenario")

with tab2:
    # Compute both scenarios
    baseline_outputs = compute_scenario(baseline_inputs)
    option_outputs = compute_scenario(option_inputs)

    st.subheader("Key outputs per scenario")

    col_b, col_o = st.columns(2)

    with col_b:
        st.markdown("**Baseline scenario**")
        st.metric("Final energy use (kWh/year)", f"{baseline_outputs['E_total']:.0f}")
        st.metric("Space heating intensity (kWh/m²/yr)", f"{baseline_outputs['q_heat']:.1f}")
        st.metric("Potable water use (m³/year)", f"{baseline_outputs['V_total']:.1f}")
        st.metric("Operational CO₂ (kgCO₂/year)", f"{baseline_outputs['C_operational']:.0f}")
        st.metric("Energy cost (NZD/year)", f"{baseline_outputs['Cost_energy']:.0f}")
        st.metric("Embodied carbon intensity (kgCO₂e/m²)", f"{baseline_outputs['EC_total_intensity']:.0f}")
        st.metric("Total embodied carbon (kgCO₂e)", f"{baseline_outputs['C_embodied']:.0f}")

    with col_o:
        st.markdown("**Option scenario**")
        st.metric("Final energy use (kWh/year)", f"{option_outputs['E_total']:.0f}")
        st.metric("Space heating intensity (kWh/m²/yr)", f"{option_outputs['q_heat']:.1f}")
        st.metric("Potable water use (m³/year)", f"{option_outputs['V_total']:.1f}")
        st.metric("Operational CO₂ (kgCO₂/year)", f"{option_outputs['C_operational']:.0f}")
        st.metric("Energy cost (NZD/year)", f"{option_outputs['Cost_energy']:.0f}")
        st.metric("Embodied carbon intensity (kgCO₂e/m²)", f"{option_outputs['EC_total_intensity']:.0f}")
        st.metric("Total embodied carbon (kgCO₂e)", f"{option_outputs['C_embodied']:.0f}")

    st.subheader("Savings of Option vs Baseline")

    energy_savings = baseline_outputs["E_total"] - option_outputs["E_total"]
    water_savings = baseline_outputs["V_total"] - option_outputs["V_total"]
    co2_savings = baseline_outputs["C_operational"] - option_outputs["C_operational"]
    cost_savings = baseline_outputs["Cost_energy"] - option_outputs["Cost_energy"]
    ec_savings = baseline_outputs["C_embodied"] - option_outputs["C_embodied"]

    col_s1, col_s2, col_s3 = st.columns(3)
    with col_s1:
        st.metric("Energy savings (kWh/yr)", f"{energy_savings:.0f}")
        st.metric("Water savings (m³/yr)", f"{water_savings:.1f}")
    with col_s2:
        st.metric("Operational CO₂ savings (kgCO₂/yr)", f"{co2_savings:.0f}")
        st.metric("Energy bill savings (NZD/yr)", f"{cost_savings:.0f}")
    with col_s3:
        st.metric("Embodied carbon savings (kgCO₂e)", f"{ec_savings:.0f}")

    st.info(
        "All numbers use **dummy parameters** for illustration. "
        "For the thesis, you will replace them with NZ-based values from literature."
    )
