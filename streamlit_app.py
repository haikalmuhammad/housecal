import streamlit as st

# =========================
# PARAMETERS
# =========================

# Climate bands: baseline space heating demand (kWh/m²/year)
Q_HEAT_BASE = {
    "Mild": 30.0,
    "Temperate": 50.0,
    "Cold": 80.0,
}

# Map NZ towns/cities to simplified winter climate bands (stylised)
LOCATION_TO_CLIMATE = {
    # Northland & Auckland
    "Whangārei": "Mild",
    "Auckland": "Mild",

    # Upper / central North Island
    "Hamilton": "Temperate",
    "Tauranga": "Mild",
    "Rotorua": "Temperate",
    "Taupō": "Cold",
    "Gisborne": "Mild",
    "Napier / Hastings": "Temperate",
    "New Plymouth": "Temperate",
    "Palmerston North": "Temperate",

    # Lower North Island
    "Wellington": "Temperate",

    # Upper South Island
    "Nelson": "Temperate",
    "Blenheim": "Temperate",

    # West Coast & Canterbury
    "Greymouth": "Temperate",
    "Christchurch": "Temperate",
    "Timaru": "Temperate",

    # Otago & Southland
    "Queenstown": "Cold",
    "Dunedin": "Cold",
    "Invercargill": "Cold",

    # Fallbacks
    "Other North Island (warmer coastal)": "Mild",
    "Other North Island (cooler inland)": "Temperate",
    "Other South Island (coastal)": "Temperate",
    "Other South Island (inland / colder)": "Cold",
}

# Dwelling type -> facade area factor (A_facade ≈ k * A_floor)
K_FACADE = {
    "Freestanding house": 1.2,
    "Semi-detached / end unit": 0.9,
    "Mid-floor apartment": 0.6,
}

# Window area category -> window-to-wall ratio (WWR)
WWR = {
    "Low window area": 0.15,
    "Medium (typical)": 0.25,
    "High window area": 0.40,
}

# Wall performance -> U-value (W/m²K)
U_WALL = {
    "Very poor / uninsulated": 1.8,
    "Typical NZ Code-like": 0.8,
    "Improved insulation": 0.5,
}

# Window type -> U-value (W/m²K)
U_WINDOW = {
    "Mostly single glazing": 4.5,
    "Standard double glazing": 2.8,
    "High-performance double / Low-E": 1.8,
}

# Baseline geometry & U-values for HeatLoss_base (per m² floor) – "typical NZ new house"
BASELINE_DWELLING_TYPE = "Freestanding house"
BASELINE_WINDOW_AREA = "Medium (typical)"
BASELINE_WALL_PERF = "Typical NZ Code-like"
BASELINE_GLAZING = "Standard double glazing"

# Other loads baseline (lighting + plugs etc.)
Q_OTHER_BASE = 25.0  # kWh/m²/year

# Hot water energy per m³ (kWh/m³)
E_HW_BASE = 45.0

# Heating system COP
COP_HEAT = {
    "None": 0.0,
    "Portable electric heaters": 0.95,
    "Panel / convector heaters": 0.95,
    "Heat pump (split system)": 3.0,
}

# Water heating system COP / efficiency
COP_HW = {
    "Electric cylinder": 0.9,
    "Heat pump water heater": 2.5,
}

# Heating coverage -> fraction of floor area heated
F_COVERAGE = {
    "Only living room": 0.4,
    "Living + some bedrooms": 0.7,
    "Most of the house": 1.0,
}

# Grid emission factor & tariff (dummy NZ-wide)
EF_EL = 0.10  # kgCO2/kWh
P_EL = 0.30   # NZD/kWh

# Usage assumptions (per person per day, unless noted)
U_FIXTURES = {
    "toilet_flushes": 5.0,      # flush/person/day
    "shower_minutes": 8.0,      # min/person/day
    "basin_minutes": 4.0,       # min/person/day
    "kitchen_minutes": 5.0,     # min/person/day
}

# Flow/volume per use (litres) for fixtures
V_TOILET = {
    "Single flush": 9.0,
    "Dual flush (standard)": 5.0,
    "Dual flush (efficient)": 4.0,
}

V_SHOWER = {
    "Standard shower head": 9.0,   # L/min
    "Efficient shower head": 6.0,
}

V_BASIN = {
    "Standard basin tap": 6.0,     # L/min
    "Efficient basin tap": 4.0,
}

V_KITCHEN = {
    "Standard kitchen tap": 8.0,   # L/min
    "Efficient kitchen tap": 6.0,
}

# Hot water fractions
H_FIXTURES = {
    "toilet": 0.0,
    "shower": 0.8,
    "basin": 0.3,
    "kitchen": 0.7,
    "laundry": 0.3,
    "dishwasher": 0.9,
}

# Laundry assumptions
LAUNDRY_LOADS_PER_WEEK = {
    "Low (1–2 loads/week)": 2,
    "Medium (3–5 loads/week)": 4,
    "High (6+ loads/week)": 7,
}

LAUNDRY_L_PER_LOAD = {
    "Hand wash": 40.0,
    "Standard machine": 70.0,
    "Efficient machine": 50.0,
}

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

DW_L_PER_CYCLE = 15.0
DW_KWH_PER_CYCLE = 0.8

# Embodied carbon intensities (kgCO2e/m² floor area, over 50 years – dummy)
EC_STRUCTURE = {
    "Conventional timber": 150.0,
    "Engineered timber (LVL/CLT)": 100.0,
    "Higher-carbon structure": 200.0,
}

EC_FLOOR = {
    "Standard concrete slab": 120.0,
    "Low-cement concrete": 90.0,
    "Timber floor system": 70.0,
}

EC_WALLS = {
    "Standard cladding mix": 60.0,
    "Lower-carbon cladding": 40.0,
}

EC_ROOF = {
    "Standard metal roof": 50.0,
    "Lower-carbon roof": 35.0,
}

# =========================
# UPGRADE COST ASSUMPTIONS (STYLISED, DUMMY NZD)
# =========================

COST_WALL_PER_M2_FLOOR = {
    "Very poor / uninsulated": 0.0,
    "Typical NZ Code-like": 60.0,
    "Improved insulation": 120.0,
}

COST_WINDOW_PER_M2_WINDOW = {
    "Mostly single glazing": 0.0,
    "Standard double glazing": 350.0,
    "High-performance double / Low-E": 500.0,
}

COST_HEATING_SYSTEM = {
    "None": 0.0,
    "Portable electric heaters": 500.0,
    "Panel / convector heaters": 2_000.0,
    "Heat pump (split system)": 5_000.0,
}

COST_WATER_HEATING_SYSTEM = {
    "Electric cylinder": 2_500.0,
    "Heat pump water heater": 5_000.0,
}

COST_TOILET = {
    "Single flush": 0.0,
    "Dual flush (standard)": 300.0,
    "Dual flush (efficient)": 400.0,
}

COST_SHOWER = {
    "Standard shower head": 0.0,
    "Efficient shower head": 150.0,
}

COST_BASIN_TAP = {
    "Standard basin tap": 0.0,
    "Efficient basin tap": 100.0,
}

COST_KITCHEN_TAP = {
    "Standard kitchen tap": 0.0,
    "Efficient kitchen tap": 120.0,
}

COST_LAUNDRY_MACHINE = {
    "Hand wash": 0.0,
    "Standard machine": 800.0,
    "Efficient machine": 1_200.0,
}

COST_DISHWASHER = {
    "Has dishwasher": 1_000.0,
    "No dishwasher": 0.0,
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
    a_facade = kf * 1.0
    a_window = wwr * a_facade
    a_wall = a_facade - a_window
    return u_wall * a_wall + u_win * a_window


HEATLOSS_BASE_PER_M2 = heatloss_base_per_m2()


def compute_scenario(inputs: dict) -> dict:
    """Compute all KPIs for one scenario based on user inputs."""
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

    a_facade_per_m2 = kf * 1.0
    a_window_per_m2 = wwr * a_facade_per_m2
    a_wall_per_m2 = a_facade_per_m2 - a_window_per_m2
    heatloss_opt_per_m2 = u_wall * a_wall_per_m2 + u_win * a_window_per_m2

    ratio = heatloss_opt_per_m2 / HEATLOSS_BASE_PER_M2 if HEATLOSS_BASE_PER_M2 > 0 else 1.0
    q_heat = q_heat_base * ratio

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
    v_hot += v_toilet_m3 * H_FIXTURES["toilet"]

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
        e_water_heating = e_hw_theoretical
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

    if floor_area > 0:
        e_total_intensity = e_total / floor_area
    else:
        e_total_intensity = 0.0

    outputs = {
        "E_total": e_total,
        "E_total_intensity": e_total_intensity,
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


def compute_capex(inputs: dict) -> float:
    """
    Estimate a stylised upgrade CAPEX (NZD) for one scenario
    based on envelope, systems, and fixture choices.
    """
    floor_area = inputs["floor_area"]
    dwelling_type = inputs["dwelling_type"]
    window_area_cat = inputs["window_area_cat"]
    wall_perf = inputs["wall_perf"]
    glazing_type = inputs["glazing_type"]
    heating_system = inputs["heating_system"]
    water_heating_system = inputs["water_heating_system"]
    toilet_type = inputs["toilet_type"]
    shower_type = inputs["shower_type"]
    basin_tap_type = inputs["basin_tap_type"]
    kitchen_tap_type = inputs["kitchen_tap_type"]
    laundry_use = inputs["laundry_use"]
    laundry_type = inputs["laundry_type"]
    dishwasher_use = inputs["dishwasher_use"]

    kf = K_FACADE[dwelling_type]
    wwr = WWR[window_area_cat]
    a_facade_per_m2 = kf * 1.0
    a_window_per_m2 = wwr * a_facade_per_m2
    window_area_total = a_window_per_m2 * floor_area

    wall_cost = COST_WALL_PER_M2_FLOOR[wall_perf] * floor_area
    window_cost = COST_WINDOW_PER_M2_WINDOW[glazing_type] * window_area_total

    heating_cost = COST_HEATING_SYSTEM[heating_system]
    water_heating_cost = COST_WATER_HEATING_SYSTEM[water_heating_system]

    toilet_cost = COST_TOILET[toilet_type]
    shower_cost = COST_SHOWER[shower_type]
    basin_cost = COST_BASIN_TAP[basin_tap_type]
    kitchen_cost = COST_KITCHEN_TAP[kitchen_tap_type]

    if laundry_use == "Yes":
        laundry_cost = COST_LAUNDRY_MACHINE[laundry_type]
    else:
        laundry_cost = 0.0

    if dishwasher_use == "Yes":
        dishwasher_cost = COST_DISHWASHER["Has dishwasher"]
    else:
        dishwasher_cost = COST_DISHWASHER["No dishwasher"]

    total_capex = (
        wall_cost
        + window_cost
        + heating_cost
        + water_heating_cost
        + toilet_cost
        + shower_cost
        + basin_cost
        + kitchen_cost
        + laundry_cost
        + dishwasher_cost
    )

    return total_capex

# =========================
# INPUT UI – GENERIC SCENARIO
# =========================

def scenario_input_ui(label_prefix: str = "Scenario") -> dict:
    """Builds Streamlit inputs and returns a dict of scenario inputs."""
    st.subheader(label_prefix)

    # Location & climate
    location = st.selectbox(
        f"{label_prefix} – Closest town or city",
        list(LOCATION_TO_CLIMATE.keys()),
        index=list(LOCATION_TO_CLIMATE.keys()).index("Dunedin")
        if "Dunedin" in LOCATION_TO_CLIMATE else 0,
        help="Pick the town/city that best matches your home location.",
        key=f"{label_prefix}_location",
    )
    climate_band = LOCATION_TO_CLIMATE[location]
    st.caption(f"Internal climate band: **{climate_band}**")

    dwelling_type = st.selectbox(
        f"{label_prefix} – Dwelling type",
        list(K_FACADE.keys()),
        help="Freestanding houses usually have more exposed walls than apartments.",
        key=f"{label_prefix}_dwelling_type",
    )

    col_a, col_b = st.columns(2)
    with col_a:
        floor_area = st.number_input(
            f"{label_prefix} – Floor area (m²)",
            min_value=30.0,
            max_value=400.0,
            value=120.0,
            step=5.0,
            help="Approximate internal floor area of the home.",
            key=f"{label_prefix}_floor_area",
        )
    with col_b:
        n_occ = st.number_input(
            f"{label_prefix} – Number of occupants",
            min_value=1,
            max_value=8,
            value=3,
            step=1,
            help="How many people usually live in the home?",
            key=f"{label_prefix}_n_occ",
        )

    window_area_cat = st.selectbox(
        f"{label_prefix} – Window area on external walls",
        list(WWR.keys()),
        index=1,
        help="Low ≈ 15% glass, Medium ≈ 25%, High ≈ 40%+ of external wall area.",
        key=f"{label_prefix}_window_area",
    )

    wall_perf = st.selectbox(
        f"{label_prefix} – Wall insulation level",
        list(U_WALL.keys()),
        index=1,
        help="Very poor: little/no insulation. Code-like: typical Building Code. Improved: better than code.",
        key=f"{label_prefix}_wall_perf",
    )

    glazing_type = st.selectbox(
        f"{label_prefix} – Window type",
        list(U_WINDOW.keys()),
        index=1,
        help="Single glazing vs standard double vs high-performance double glazing.",
        key=f"{label_prefix}_glazing",
    )

    st.markdown("**Heating and hot water**")

    heating_system = st.selectbox(
        f"{label_prefix} – Main space heating system",
        list(COP_HEAT.keys()),
        index=3,
        help="Portable/panel heaters are resistive (COP ~1); heat pumps give more heat per kWh.",
        key=f"{label_prefix}_heating_system",
    )

    heating_coverage = st.selectbox(
        f"{label_prefix} – Which spaces are usually heated in winter?",
        list(F_COVERAGE.keys()),
        index=1,
        help="Controls how much of the floor area is assumed to be heated.",
        key=f"{label_prefix}_heating_cov",
    )

    water_heating_system = st.selectbox(
        f"{label_prefix} – Water heating system",
        list(COP_HW.keys()),
        index=0,
        help="Electric cylinders are common; heat pump water heaters use less electricity.",
        key=f"{label_prefix}_water_heating",
    )

    st.markdown("**Water fixtures and taps**")

    col1, col2 = st.columns(2)
    with col1:
        toilet_type = st.selectbox(
            f"{label_prefix} – Toilet type",
            list(V_TOILET.keys()),
            index=1,
            help="Single flush ≈ older cistern; dual flush options use less per flush.",
            key=f"{label_prefix}_toilet",
        )
        basin_tap_type = st.selectbox(
            f"{label_prefix} – Basin tap type",
            list(V_BASIN.keys()),
            index=0,
            help="Standard taps ≈ 6 L/min; efficient ≈ 4 L/min.",
            key=f"{label_prefix}_basin",
        )
    with col2:
        shower_type = st.selectbox(
            f"{label_prefix} – Shower head type",
            list(V_SHOWER.keys()),
            index=0,
            help="Standard heads ≈ 9 L/min; efficient ≈ 6 L/min.",
            key=f"{label_prefix}_shower",
        )
        kitchen_tap_type = st.selectbox(
            f"{label_prefix} – Kitchen tap type",
            list(V_KITCHEN.keys()),
            index=0,
            help="Standard ≈ 8 L/min; efficient ≈ 6 L/min.",
            key=f"{label_prefix}_kitchen",
        )

    st.markdown("**Laundry and dishwasher**")

    laundry_use = st.selectbox(
        f"{label_prefix} – Do you wash clothes at home?",
        ["Yes", "No"],
        index=0,
        help="Choose No if most laundry is done elsewhere.",
        key=f"{label_prefix}_laundry_use",
    )

    if laundry_use == "Yes":
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            laundry_type = st.selectbox(
                f"{label_prefix} – Washing machine type",
                list(LAUNDRY_L_PER_LOAD.keys()),
                index=1,
                help="Standard ≈ typical top-loader; efficient ≈ front-loader.",
                key=f"{label_prefix}_laundry_type",
            )
        with col_l2:
            laundry_freq = st.selectbox(
                f"{label_prefix} – Laundry frequency",
                list(LAUNDRY_LOADS_PER_WEEK.keys()),
                index=1,
                help="Approximate number of loads per week for the household.",
                key=f"{label_prefix}_laundry_freq",
            )
    else:
        laundry_type = "Standard machine"
        laundry_freq = "Low (1–2 loads/week)"

    dishwasher_use = st.selectbox(
        f"{label_prefix} – Do you use a dishwasher regularly?",
        ["Yes", "No"],
        index=1,
        help="Choose No if you mainly wash dishes by hand.",
        key=f"{label_prefix}_dw_use",
    )

    if dishwasher_use == "Yes":
        dishwasher_freq = st.selectbox(
            f"{label_prefix} – Dishwasher frequency",
            list(DW_CYCLES_PER_WEEK.keys()),
            index=1,
            help="Low ≈ 1–2 cycles/week, Medium ≈ 3–5, High ≈ 6+.",
            key=f"{label_prefix}_dw_freq",
        )
    else:
        dishwasher_freq = "Low"

    st.markdown("**Main materials (embodied carbon)**")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        structure_opt = st.selectbox(
            f"{label_prefix} – Structure option",
            list(EC_STRUCTURE.keys()),
            index=0,
            help="Conventional timber vs engineered timber vs higher-carbon structure.",
            key=f"{label_prefix}_structure",
        )
        wall_opt = st.selectbox(
            f"{label_prefix} – Walls / cladding option",
            list(EC_WALLS.keys()),
            index=0,
            help="Standard cladding mix vs lower-carbon alternatives.",
            key=f"{label_prefix}_wall_material",
        )
    with col_m2:
        floor_opt = st.selectbox(
            f"{label_prefix} – Floor / slab option",
            list(EC_FLOOR.keys()),
            index=0,
            help="Standard concrete slab vs lower-carbon or timber floor.",
            key=f"{label_prefix}_floor_material",
        )
        roof_opt = st.selectbox(
            f"{label_prefix} – Roof option",
            list(EC_ROOF.keys()),
            index=0,
            help="Standard metal roof vs lower-carbon roof.",
            key=f"{label_prefix}_roof_material",
        )

    scenario_inputs = {
        "location": location,
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

st.title("Early-stage NZ Housing Sustainability Prototype")

st.write(
    """
This is a **prototype** calculator for New Zealand homes.

- Column 1: describe a **Baseline** home (current / typical).  
- Column 2: describe an **Option** home (improved / alternative).  
- Column 3: see **results** and how the Option compares to the Baseline.

This is **not** a Homestar or EDGE rating tool – it is only inspired by some of their ideas.
"""
)

col1, col2, col3 = st.columns([1.1, 1.1, 1.2])

# -------- LEFT: BASELINE INPUTS --------
with col1:
    st.header("Baseline")
    baseline_inputs = scenario_input_ui("Baseline")

# -------- MIDDLE: OPTION INPUTS --------
with col2:
    st.header("Option")
    option_inputs = scenario_input_ui("Option")

# -------- RIGHT: RESULTS --------
baseline_outputs = compute_scenario(baseline_inputs)
option_outputs = compute_scenario(option_inputs)

# Savings vs baseline (Baseline – Option => positive = improvement)
energy_savings = baseline_outputs["E_total"] - option_outputs["E_total"]
water_savings = baseline_outputs["V_total"] - option_outputs["V_total"]
co2_savings = baseline_outputs["C_operational"] - option_outputs["C_operational"]
cost_savings = baseline_outputs["Cost_energy"] - option_outputs["Cost_energy"]
ec_savings = baseline_outputs["C_embodied"] - option_outputs["C_embodied"]

def pct_saving(abs_saving, baseline_value):
    if baseline_value <= 0:
        return 0.0
    return abs_saving / baseline_value * 100.0

energy_savings_pct = pct_saving(energy_savings, baseline_outputs["E_total"])
water_savings_pct = pct_saving(water_savings, baseline_outputs["V_total"])
co2_savings_pct = pct_saving(co2_savings, baseline_outputs["C_operational"])
cost_savings_pct = pct_saving(cost_savings, baseline_outputs["Cost_energy"])
ec_savings_pct = pct_saving(ec_savings, baseline_outputs["C_embodied"])

# CAPEX & payback
capex_baseline = compute_capex(baseline_inputs)
capex_option = compute_capex(option_inputs)
capex_incremental = max(capex_option - capex_baseline, 0.0)

if capex_incremental > 0 and cost_savings > 0:
    payback_years = capex_incremental / cost_savings
    payback_text = f"{payback_years:.1f} years"
else:
    payback_text = "N/A"

with col3:
    st.header("Results")

    st.subheader("Key KPIs (Option, with change vs Baseline)")
    # delta = Option - Baseline (negatif = perbaikan)
    st.metric(
        "Final energy use (kWh/yr)",
        f"{option_outputs['E_total']:.0f}",
        delta=f"{option_outputs['E_total'] - baseline_outputs['E_total']:.0f}",
    )
    st.metric(
        "Energy intensity (kWh/m²/yr)",
        f"{option_outputs['E_total_intensity']:.1f}",
        delta=f"{option_outputs['E_total_intensity'] - baseline_outputs['E_total_intensity']:.1f}",
    )
    st.metric(
        "Space heating demand (kWh/m²/yr)",
        f"{option_outputs['q_heat']:.1f}",
        delta=f"{option_outputs['q_heat'] - baseline_outputs['q_heat']:.1f}",
    )
    st.metric(
        "Indoor water use (m³/yr)",
        f"{option_outputs['V_total']:.1f}",
        delta=f"{option_outputs['V_total'] - baseline_outputs['V_total']:.1f}",
    )
    st.metric(
        "Operational CO₂ (kgCO₂/yr)",
        f"{option_outputs['C_operational']:.0f}",
        delta=f"{option_outputs['C_operational'] - baseline_outputs['C_operational']:.0f}",
    )
    st.metric(
        "Energy bill (NZD/yr)",
        f"{option_outputs['Cost_energy']:.0f}",
        delta=f"{option_outputs['Cost_energy'] - baseline_outputs['Cost_energy']:.0f}",
    )
    st.metric(
        "Total embodied carbon (kgCO₂e)",
        f"{option_outputs['C_embodied']:.0f}",
        delta=f"{option_outputs['C_embodied'] - baseline_outputs['C_embodied']:.0f}",
    )

    st.subheader("Savings of Option vs Baseline (positive = Option better)")
    st.write(f"- Energy savings: **{energy_savings:,.0f} kWh/yr** ({energy_savings_pct:.1f}%)")
    st.write(f"- Water savings: **{water_savings:,.1f} m³/yr** ({water_savings_pct:.1f}%)")
    st.write(f"- Operational CO₂ savings: **{co2_savings:,.0f} kgCO₂/yr** ({co2_savings_pct:.1f}%)")
    st.write(f"- Bill savings: **{cost_savings:,.0f} NZD/yr** ({cost_savings_pct:.1f}%)")
    st.write(f"- Embodied carbon savings: **{ec_savings:,.0f} kgCO₂e** ({ec_savings_pct:.1f}%)")

    st.subheader("Stylised upgrade cost & payback")
    st.write(f"- Estimated CAPEX – Baseline: **{capex_baseline:,.0f} NZD**")
    st.write(f"- Estimated CAPEX – Option: **{capex_option:,.0f} NZD**")
    st.write(f"- Incremental CAPEX (Option − Baseline): **{capex_incremental:,.0f} NZD**")
    st.write(f"- Simple payback: **{payback_text}**")

    with st.expander("Breakdown (energy & water)"):
        st.write(
            f"Space heating: {baseline_outputs['E_space_heating']:.0f} → "
            f"{option_outputs['E_space_heating']:.0f} kWh/yr"
        )
        st.write(
            f"Hot water: {baseline_outputs['E_water_heating']:.0f} → "
            f"{option_outputs['E_water_heating']:.0f} kWh/yr"
        )
        st.write(
            f"Other loads: {baseline_outputs['E_other']:.0f} → "
            f"{option_outputs['E_other']:.0f} kWh/yr"
        )
        st.write(
            f"Indoor water: {baseline_outputs['V_total']:.1f} → "
            f"{option_outputs['V_total']:.1f} m³/yr"
        )
        st.write(
            f"Hot water volume: {baseline_outputs['V_hot']:.1f} → "
            f"{option_outputs['V_hot']:.1f} m³/yr"
        )

    with st.expander("Embodied carbon breakdown"):
        st.write(
            f"Embodied intensity: {baseline_outputs['EC_total_intensity']:.0f} → "
            f"{option_outputs['EC_total_intensity']:.0f} kgCO₂e/m²"
        )
        st.write(
            f"Total embodied: {baseline_outputs['C_embodied']:.0f} → "
            f"{option_outputs['C_embodied']:.0f} kgCO₂e"
        )

st.info(
    "All numbers use **simplified assumptions and stylised upgrade costs**. "
    "The main purpose is to show how design choices change energy, water, carbon and bills, "
    "not to provide a detailed compliance assessment."
)
