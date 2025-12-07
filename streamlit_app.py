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


def scenario_input_ui(label_prefix: str = "Scenario") -> dict:
    """Builds Streamlit inputs and returns a dict of scenario inputs."""
    st.subheader(label_prefix)

    # --- Location / climate band ---
    location = st.selectbox(
        f"{label_prefix} – Where do you live?",
        list(LOCATION_TO_CLIMATE.keys()),
        index=1,
        help=(
            "Choose the region that best matches your home. "
            "The tool will map this to a winter climate band (mild / temperate / cold) "
            "based on Infracomfort's New Zealand winter climate zones."
        ),
    )
    climate_band = LOCATION_TO_CLIMATE[location]

    dwelling_type = st.selectbox(
        f"{label_prefix} – Dwelling type",
        list(K_FACADE.keys()),
        help="Freestanding houses usually have more exposed walls than apartments, "
             "so they lose more heat for the same floor area.",
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
        )
    with col_b:
        n_occ = st.number_input(
            f"{label_prefix} – Number of occupants",
            min_value=1,
            max_value=8,
            value=3,
            step=1,
            help="How many people usually live in the home?",
        )

    # --- Envelope (windows & walls) ---
    window_area_cat = st.selectbox(
        f"{label_prefix} – Window area on external walls",
        list(WWR.keys()),
        index=1,
        help=(
            "Roughly how much glass do you have on outside walls (window-to-wall ratio)? "
            "Low ≈ 15% of wall area, Medium ≈ 25%, High ≈ 40% or more."
        ),
    )

    wall_perf = st.selectbox(
        f"{label_prefix} – Wall insulation level",
        list(U_WALL.keys()),
        index=1,
        help=(
            "Very poor / uninsulated: older walls with little or no insulation. "
            "Typical NZ Code-like: current H1-level wall (around R1.6). "
            "Improved insulation: higher-performance wall (around R2.5 or better)."
        ),
    )

    glazing_type = st.selectbox(
        f"{label_prefix} – Window type",
        list(U_WINDOW.keys()),
        index=1,
        help=(
            "Mostly single glazing: older, less efficient windows. "
            "Standard double glazing: current typical new-build windows. "
            "High-performance: double glazing with low-E / better frames."
        ),
    )

    # --- Heating and hot water ---
    st.markdown("**Heating and hot water**")

    heating_system = st.selectbox(
        f"{label_prefix} – Main space heating system",
        list(COP_HEAT.keys()),
        index=3,  # default heat pump
        help=(
            "Portable / panel heaters use electricity directly (COP ≈ 1). "
            "Heat pumps move heat and typically deliver ~3 units of heat per unit of electricity."
        ),
    )

    heating_coverage = st.selectbox(
        f"{label_prefix} – Which spaces do you usually heat in winter?",
        list(F_COVERAGE.keys()),
        index=1,
        help=(
            "This controls how much of the floor area is assumed to be heated. "
            "If you're not sure, leave the default (living room + some bedrooms)."
        ),
    )

    water_heating_system = st.selectbox(
        f"{label_prefix} – Water heating system",
        list(COP_HW.keys()),
        index=0,
        help=(
            "Electric cylinders are common but less efficient. "
            "Heat pump water heaters use less electricity for the same hot water."
        ),
    )

    # --- Fixtures and water use ---
    st.markdown("**Water fixtures and taps**")

    col1, col2 = st.columns(2)
    with col1:
        toilet_type = st.selectbox(
            f"{label_prefix} – Toilet type",
            list(V_TOILET.keys()),
            index=1,
            help=(
                "Single flush represents older cisterns (~11 L/flush). "
                "Standard dual flush ~6 L/flush on average. "
                "Efficient dual flush ~4 L/flush."
            ),
        )
        basin_tap_type = st.selectbox(
            f"{label_prefix} – Basin tap type",
            list(V_BASIN.keys()),
            index=0,
            help="Standard taps ~6 L/min; efficient taps ~4 L/min.",
        )
    with col2:
        shower_type = st.selectbox(
            f"{label_prefix} – Shower head type",
            list(V_SHOWER.keys()),
            index=0,
            help="Standard shower heads ~9 L/min; efficient heads ~6 L/min.",
        )
        kitchen_tap_type = st.selectbox(
            f"{label_prefix} – Kitchen tap type",
            list(V_KITCHEN.keys()),
            index=0,
            help="Standard kitchen taps ~8 L/min; efficient taps ~6 L/min.",
        )

    # --- Laundry and dishwasher ---
    st.markdown("**Laundry and dishwasher**")

    laundry_use = st.selectbox(
        f"{label_prefix} – Do you wash clothes at home?",
        ["Yes", "No"],
        index=0,
        help="If most laundry is done elsewhere (e.g. laundromat), choose No.",
    )

    if laundry_use == "Yes":
        col_l1, col_l2 = st.columns(2)
        with col_l1:
            laundry_type = st.selectbox(
                f"{label_prefix} – Washing machine type",
                list(LAUNDRY_L_PER_LOAD.keys()),
                index=1,
                help=(
                    "Standard machine ≈ top-loader (~135 L per load). "
                    "Efficient machine ≈ front-loader (~64 L per load). "
                    "Hand wash for small bucket / tub washing."
                ),
            )
        with col_l2:
            laundry_freq = st.selectbox(
                f"{label_prefix} – Laundry frequency",
                list(LAUNDRY_LOADS_PER_WEEK.keys()),
                index=1,
                help="Approximate number of loads per week for the whole household.",
            )
    else:
        laundry_type = "Standard machine"
        laundry_freq = "Low (1–2 loads/week)"

    dishwasher_use = st.selectbox(
        f"{label_prefix} – Do you use a dishwasher regularly?",
        ["Yes", "No"],
        index=1,
        help="Choose No if you mainly wash dishes by hand.",
    )

    if dishwasher_use == "Yes":
        dishwasher_freq = st.selectbox(
            f"{label_prefix} – Dishwasher frequency",
            list(DW_CYCLES_PER_WEEK.keys()),
            index=1,
            help="Low ≈ 1–2 cycles/week, Medium ≈ 3–5, High ≈ 6 or more.",
        )
    else:
        dishwasher_freq = "Low"

    # --- Materials (embodied carbon) ---
    st.markdown("**Main materials (for embodied carbon)**")

    col_m1, col_m2 = st.columns(2)
    with col_m1:
        structure_opt = st.selectbox(
            f"{label_prefix} – Structure option",
            list(EC_STRUCTURE.keys()),
            index=0,
            help=(
                "Conventional timber: standard light timber framing. "
                "Engineered timber: LVL/CLT-type systems. "
                "Higher-carbon: more concrete/steel content."
            ),
        )
        wall_opt = st.selectbox(
            f"{label_prefix} – Walls / cladding option",
            list(EC_WALLS.keys()),
            index=0,
            help=(
                "Standard cladding mix: e.g. brick + fibre-cement. "
                "Lower-carbon cladding: timber or other lighter options."
            ),
        )
    with col_m2:
        floor_opt = st.selectbox(
            f"{label_prefix} – Floor / slab option",
            list(EC_FLOOR.keys()),
            index=0,
            help=(
                "Standard slab: conventional concrete slab-on-ground. "
                "Low-cement: mixes with reduced clinker content. "
                "Timber floor: suspended timber system."
            ),
        )
        roof_opt = st.selectbox(
            f"{label_prefix} – Roof option",
            list(EC_ROOF.keys()),
            index=0,
            help=(
                "Standard metal roof vs lower-carbon roof options "
                "(e.g. lighter materials or lower-impact coatings)."
            ),
        )

    # Simple CAPEX field (Option only; Baseline assumed 0 incremental CAPEX)
    if "Option" in label_prefix:
        capex_extra = st.number_input(
            f"{label_prefix} – Extra upgrade cost vs baseline (NZD, optional)",
            min_value=0.0,
            value=0.0,
            step=500.0,
            help="If you enter the extra cost of upgrades, the tool will estimate a simple payback time.",
        )
    else:
        capex_extra = 0.0

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
        "capex_extra": capex_extra,
    }

    return scenario_inputs



# =========================
# STREAMLIT APP
# =========================

st.title("Early-stage NZ Housing Sustainability Prototype")
st.write(
    """
This is a **prototype** calculator for New Zealand homes.  
On the left, describe your **Baseline** home and an **Option** (improved) scenario.  
On the right, the results update in real time.

This is **not** a Homestar or EDGE rating tool – it is only inspired by some of their ideas.
"""
)

# Layout: left = inputs, right = results
col_left, col_right = st.columns([3, 2])

# -------- LEFT: INPUTS --------
with col_left:
    st.markdown("### Describe your two scenarios")

    with st.expander("Baseline scenario (current / typical home)", expanded=True):
        baseline_inputs = scenario_input_ui("Baseline scenario")

    with st.expander("Option scenario (improved / upgraded home)", expanded=True):
        option_inputs = scenario_input_ui("Option scenario")

# Hitung setelah kedua skenario diisi
baseline_outputs = compute_scenario(baseline_inputs)
option_outputs = compute_scenario(option_inputs)

# Savings vs baseline
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

# Simple payback
capex_baseline = baseline_inputs.get("capex_extra", 0.0)
capex_option = option_inputs.get("capex_extra", 0.0)
capex_incremental = max(capex_option - capex_baseline, 0.0)

if capex_incremental > 0 and cost_savings > 0:
    payback_years = capex_incremental / cost_savings
    payback_text = f"{payback_years:.1f} years"
else:
    payback_text = "N/A (no positive savings or CAPEX entered)"

# -------- RIGHT: RESULTS --------
with col_right:
    st.markdown("### Summary results")

    col_b, col_o = st.columns(2)

    with col_b:
        st.markdown("**Baseline**")
        st.metric("Final energy use (kWh/year)", f"{baseline_outputs['E_total']:.0f}")
        st.metric("Energy intensity (kWh/m²/year)", f"{baseline_outputs['E_total_intensity']:.1f}")
        st.metric("Space heating demand (kWh/m²/year)", f"{baseline_outputs['q_heat']:.1f}")
        st.metric("Indoor water use (m³/year)", f"{baseline_outputs['V_total']:.1f}")
        st.metric("Operational CO₂ (kgCO₂/year)", f"{baseline_outputs['C_operational']:.0f}")
        st.metric("Energy cost (NZD/year)", f"{baseline_outputs['Cost_energy']:.0f}")
        st.metric("Total embodied carbon (kgCO₂e)", f"{baseline_outputs['C_embodied']:.0f}")

    with col_o:
        st.markdown("**Option**")
        st.metric("Final energy use (kWh/year)", f"{option_outputs['E_total']:.0f}")
        st.metric("Energy intensity (kWh/m²/year)", f"{option_outputs['E_total_intensity']:.1f}")
        st.metric("Space heating demand (kWh/m²/year)", f"{option_outputs['q_heat']:.1f}")
        st.metric("Indoor water use (m³/year)", f"{option_outputs['V_total']:.1f}")
        st.metric("Operational CO₂ (kgCO₂/year)", f"{option_outputs['C_operational']:.0f}")
        st.metric("Energy cost (NZD/year)", f"{option_outputs['Cost_energy']:.0f}")
        st.metric("Total embodied carbon (kgCO₂e)", f"{option_outputs['C_embodied']:.0f}")

    st.markdown("### Savings of Option vs Baseline")

    col_s1, col_s2 = st.columns(2)
    with col_s1:
        st.metric("Energy savings (kWh/year)", f"{energy_savings:.0f}")
        st.metric("Energy savings (%)", f"{energy_savings_pct:.1f}")
        st.metric("Water savings (m³/year)", f"{water_savings:.1f}")
        st.metric("Water savings (%)", f"{water_savings_pct:.1f}")
    with col_s2:
        st.metric("Operational CO₂ savings (kgCO₂/year)", f"{co2_savings:.0f}")
        st.metric("CO₂ savings (%)", f"{co2_savings_pct:.1f}")
        st.metric("Bill savings (NZD/year)", f"{cost_savings:.0f}")
        st.metric("Bill savings (%)", f"{cost_savings_pct:.1f}")

    st.markdown("### Simple payback (if you entered extra cost)")

    st.write(f"Incremental upgrade cost (Option vs Baseline): **{capex_incremental:,.0f} NZD**")
    st.write(f"Simple payback period: **{payback_text}**")

    # Detail per domain (mini-results per subsection)
    with st.expander("Energy & heating details"):
        st.write("**Baseline vs Option – annual energy breakdown**")
        st.write(f"- Space heating: {baseline_outputs['E_space_heating']:.0f} → {option_outputs['E_space_heating']:.0f} kWh/yr")
        st.write(f"- Hot water: {baseline_outputs['E_water_heating']:.0f} → {option_outputs['E_water_heating']:.0f} kWh/yr")
        st.write(f"- Other loads: {baseline_outputs['E_other']:.0f} → {option_outputs['E_other']:.0f} kWh/yr")

    with st.expander("Water & hot water details"):
        st.write("**Baseline vs Option – indoor water**")
        st.write(f"- Total indoor water: {baseline_outputs['V_total']:.1f} → {option_outputs['V_total']:.1f} m³/yr")
        st.write(f"- Hot water volume: {baseline_outputs['V_hot']:.1f} → {option_outputs['V_hot']:.1f} m³/yr")

    with st.expander("Embodied carbon details"):
        st.write("**Embodied carbon intensity per m² floor area**")
        st.write(f"- Baseline: {baseline_outputs['EC_total_intensity']:.0f} kgCO₂e/m²")
        st.write(f"- Option: {option_outputs['EC_total_intensity']:.0f} kgCO₂e/m²")

    st.info(
        "All numbers currently use **simplified NZ-based assumptions** for illustration. "
        "For the thesis, the focus is on relative changes between Baseline and Option, not precise compliance numbers."
    )

