# =============================================================================
# HELPERS: tooltip builder (consistent, includes default + source)
# =============================================================================
def help_default_source(what: str, default=None, source: str | None = None, notes: str | None = None, units: str | None = None) -> str:
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

# =============================================================================
# HELP TEXTS (expanded; include defaults + provenance-like short refs)
# =============================================================================
HELP = {
    # Core + climate
    "closest_city": help_default_source(
        what="Used to infer Climate Zone and HDD (Heating Degree Days, base 18°C).",
        default="—",
        source="InfraComfort (n.d.); MSD (2006) bands; city→zone mapping in LOOKUP",
        notes="Pick the closest major city. You can override HDD if you have a confirmed local value."
    ),
    "use_custom_hdd": help_default_source(
        what="Override the default HDD for the selected city/zone.",
        default=False,
        source="User-provided override",
        notes="HDD is annual total degree-days (base 18°C). Keep within a plausible NZ range.",
    ),
    "hdd_value": help_default_source(
        what="Annual Heating Degree Days (base 18°C). Higher means colder climate and more heating demand.",
        default=2000.0,
        units="degree-days/year",
        source="User override (otherwise zone defaults)",
        notes="Only affects the simplified space-heating model."
    ),
    "floor_area": help_default_source(
        what="Conditioned floor area used for geometry + intensity calculations.",
        default=float(LOOKUP["defaults"]["core"]["floorArea"]),
        units="m²",
        source="Model default (editable)",
        notes="Used to estimate roof= floor area and approximate wall area from perimeter."
    ),
    "ceiling_height": help_default_source(
        what="Average ceiling height used for wall area approximation.",
        default=float(LOOKUP["defaults"]["core"]["ceilingHeight"]),
        units="m",
        source="Model default (editable)",
        notes="Impacts wall area and therefore heating losses."
    ),
    "household_size": help_default_source(
        what="Number of people used for per-person water end-use assumptions.",
        default=int(LOOKUP["defaults"]["core"]["householdSize"]),
        units="people",
        source="Model default (editable)",
        notes="Impacts toilet/shower/tap hot water + total water consumption."
    ),
    "window_area": help_default_source(
        what="Total window area used for heat loss through glazing.",
        default=float(LOOKUP["defaults"]["core"]["windowArea"]),
        units="m²",
        source="Model default (editable)",
        notes="Used directly in H_total calculation."
    ),

    # Lighting
    "light_n": help_default_source(
        what="Total number of light fixtures assumed in the home.",
        default=int(LOOKUP["defaults"]["lighting"]["numberOfLights"]),
        source="Model default (editable)",
    ),
    "light_watts": help_default_source(
        what="Average wattage per light (LED typically 6–12W).",
        default=float(LOOKUP["defaults"]["lighting"]["wattsPerLight"]),
        units="W",
        source="Model default (editable)",
    ),
    "light_hours": help_default_source(
        what="Average daily hours of lighting use.",
        default=float(LOOKUP["defaults"]["lighting"]["hoursPerDay"]),
        units="hours/day",
        source="Model default (editable)",
    ),

    # Envelope + systems explanation
    "r_value": help_default_source(
        what="R-value (m²K/W): higher means better insulation (lower heat loss).",
        source="MBIE (2023); BRANZ (2023) bands in LOOKUP",
        notes="If you select Custom, enter your own R-value and cost rate."
    ),
    "u_value": help_default_source(
        what="U-value (W/m²K): lower means better glazing performance (less heat loss).",
        source="MBIE/BRANZ typical glazing bands in LOOKUP",
        notes="If you select Custom, enter your own U-value and window cost rate."
    ),
    "cop": help_default_source(
        what="COP (Coefficient of Performance): higher means less purchased electricity per delivered heat.",
        source="BRANZ (2023) typical systems in LOOKUP",
        notes="If COP is 0/None, purchased energy is set to 0 (tool will warn)."
    ),

    # Fixtures + appliances
    "fixture_general": help_default_source(
        what="Select the fixture performance and cost. Custom allows manual entry.",
        source="BRANZ (2023) typical fixtures in LOOKUP",
    ),
    "wash_has": help_default_source(
        what="Include washing machine indoor water use.",
        default=LOOKUP["defaults"]["washing_machine"]["hasAppliance"],
        source="Model default (editable)",
        notes="If Yes, cycles/week and L/cycle will be included."
    ),
    "dish_has": help_default_source(
        what="Include dishwasher indoor water use.",
        default=LOOKUP["defaults"]["dishwasher"]["hasAppliance"],
        source="Model default (editable)",
        notes="If Yes, cycles/week and L/cycle will be included."
    ),

    # Usage + fractions
    "usage_general": help_default_source(
        what="Behavioural assumptions for indoor water end-uses.",
        source="Model defaults (Homestar-like placeholder for shower duration; user-editable)",
        notes="These defaults are indicative; adjust based on occupant behaviour."
    ),
    "hw_frac": help_default_source(
        what="Fraction (0–1) of end-use water assumed to be hot water (toilets excluded).",
        source="BRANZ (2023) typical assumptions (placeholders) + user override",
        notes="Used to estimate hot water volume for water heating energy."
    ),

    # Coefficients
    "tariffs": help_default_source(
        what="Retail tariffs vary by region/provider. Set these if you want cost outputs to reflect local bills.",
        default="Electricity 0.312 NZD/kWh; Water 2.296 NZD/m³",
        source="Electricity Authority NZ (2024) representative; Auckland Council (2025) representative",
        notes="Keep in Baseline and Option to avoid confusion (scenario-specific)."
    ),
    "efs": help_default_source(
        what="Operational emission factors for electricity and water supply.",
        default="Grid EF 0.0729 kgCO₂e/kWh; Water EF 0.0349 kgCO₂e/m³",
        source="MfE (2024) measuring emissions guide (2023 grid-average and water factors)",
        notes="Change only if you have a different factor set you need to use."
    ),
}

# =============================================================================
# INPUT PANELS (3 main expanders; nested expanders inside)
# =============================================================================
def scenario_panel(prefix: str, title: str, show_compare_controls: bool):
    st.subheader(title)

    # Controls row
    c1, c2 = st.columns([1, 1], gap="small")
    with c1:
        if st.button(f"Use Code Minimum ({title})", key=f"{prefix}_btn_code_min", use_container_width=True):
            apply_code_minimum(prefix)
            st.rerun()
    with c2:
        if st.button(f"Reset ({title})", key=f"{prefix}_btn_reset", use_container_width=True):
            reset_scenario(prefix)
            st.rerun()

    # -------------------------------------------------------------------------
    # ROW 1: Core + Climate + Lighting
    # -------------------------------------------------------------------------
    with st.expander("Core + Climate + Lighting", expanded=True):
        cc1, cc2 = st.columns(2, gap="small")

        with cc1:
            with st.expander("Core + Climate", expanded=True):
                select_with_placeholder(
                    "Closest city",
                    CITIES,
                    key=f"{prefix}_closestCity",
                    help_text=HELP["closest_city"],
                )
                show_city_caption(prefix)

                st.checkbox(
                    "Use custom HDD",
                    key=f"{prefix}_use_custom_hdd",
                    help=HELP["use_custom_hdd"],
                )
                if st.session_state[f"{prefix}_use_custom_hdd"]:
                    st.number_input(
                        "Custom HDD (base 18°C)",
                        min_value=0.0, max_value=6000.0, step=50.0,
                        key=f"{prefix}_hdd_override_value",
                        help=HELP["hdd_value"],
                    )
                    st.caption(f"Using custom HDD: **{float(st.session_state[f'{prefix}_hdd_override_value']):g}**")

                st.number_input(
                    "Floor area (m²)",
                    min_value=20.0, max_value=500.0, step=5.0,
                    key=f"{prefix}_floorArea",
                    help=HELP["floor_area"],
                )
                st.number_input(
                    "Ceiling height (m)",
                    min_value=2.0, max_value=4.0, step=0.1,
                    key=f"{prefix}_ceilingHeight",
                    help=HELP["ceiling_height"],
                )
                st.number_input(
                    "Household size (people)",
                    min_value=1, max_value=12, step=1,
                    key=f"{prefix}_householdSize",
                    help=HELP["household_size"],
                )
                st.number_input(
                    "Total window area (m²)",
                    min_value=0.0, max_value=200.0, step=5.0,
                    key=f"{prefix}_windowArea",
                    help=HELP["window_area"],
                )

        with cc2:
            with st.expander("Lighting", expanded=True):
                st.number_input(
                    "Number of lights",
                    min_value=0, max_value=200, step=1,
                    key=f"{prefix}_light_n",
                    help=HELP["light_n"],
                )
                st.number_input(
                    "Watts per light",
                    min_value=0.0, max_value=200.0, step=1.0,
                    key=f"{prefix}_light_watts",
                    help=HELP["light_watts"],
                )
                st.number_input(
                    "Lighting hours/day",
                    min_value=0.0, max_value=24.0, step=0.5,
                    key=f"{prefix}_light_hours",
                    help=HELP["light_hours"],
                )
                st.caption("Formula: count × watts × hours/day × 365 ÷ 1000")

    # -------------------------------------------------------------------------
    # ROW 2: Envelope + Systems + Water
    # -------------------------------------------------------------------------
    with st.expander("Envelope + Systems + Water", expanded=False):
        ec1, ec2 = st.columns(2, gap="small")

        # Left column: Envelope (nested)
        with ec1:
            with st.expander("Thermal envelope", expanded=True):
                select_with_placeholder("Roof insulation", ROOF_OPTS, key=f"{prefix}_roofRLabel", help_text=HELP["r_value"])
                show_envelope_caption("roof", st.session_state[f"{prefix}_roofRLabel"])
                if st.session_state[f"{prefix}_roofRLabel"] == "Custom":
                    st.number_input("Roof R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_roofR_custom", help=HELP["r_value"])
                    st.number_input("Roof capex (NZD/m² roof)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_roofCost_custom")
                    st.caption(f"Custom: R={float(st.session_state[f'{prefix}_roofR_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_roofCost_custom']))}/m²")

                select_with_placeholder("Wall insulation", WALL_OPTS, key=f"{prefix}_wallRLabel", help_text=HELP["r_value"])
                show_envelope_caption("wall", st.session_state[f"{prefix}_wallRLabel"])
                if st.session_state[f"{prefix}_wallRLabel"] == "Custom":
                    st.number_input("Wall R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_wallR_custom", help=HELP["r_value"])
                    st.number_input("Wall capex (NZD/m² wall)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_wallCost_custom")
                    st.caption(f"Custom: R={float(st.session_state[f'{prefix}_wallR_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_wallCost_custom']))}/m²")

                select_with_placeholder("Floor insulation", FLOOR_OPTS, key=f"{prefix}_floorRLabel", help_text=HELP["r_value"])
                show_envelope_caption("floor", st.session_state[f"{prefix}_floorRLabel"])
                if st.session_state[f"{prefix}_floorRLabel"] == "Custom":
                    st.number_input("Floor R-value (m²K/W)", min_value=0.1, max_value=20.0, step=0.1, key=f"{prefix}_floorR_custom", help=HELP["r_value"])
                    st.number_input("Floor capex (NZD/m² floor)", min_value=0.0, max_value=2000.0, step=10.0, key=f"{prefix}_floorCost_custom")
                    st.caption(f"Custom: R={float(st.session_state[f'{prefix}_floorR_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_floorCost_custom']))}/m²")

                select_with_placeholder("Window type", WIN_OPTS, key=f"{prefix}_windowULabel", help_text=HELP["u_value"])
                show_envelope_caption("window", st.session_state[f"{prefix}_windowULabel"])
                if st.session_state[f"{prefix}_windowULabel"] == "Custom":
                    st.number_input("Window U-value (W/m²K)", min_value=0.1, max_value=10.0, step=0.1, key=f"{prefix}_windowU_custom", help=HELP["u_value"])
                    st.number_input("Windows capex (NZD/m² window)", min_value=0.0, max_value=5000.0, step=25.0, key=f"{prefix}_windowCost_custom")
                    st.caption(f"Custom: U={float(st.session_state[f'{prefix}_windowU_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_windowCost_custom']))}/m²")

        # Right column: Systems + Water fixtures (nested)
        with ec2:
            with st.expander("Systems", expanded=True):
                select_with_placeholder("Space heating system", SPACE_SYS_OPTS, key=f"{prefix}_spaceHeatingSystem", help_text=HELP["cop"])
                show_system_caption("space_heating", st.session_state[f"{prefix}_spaceHeatingSystem"])
                if st.session_state[f"{prefix}_spaceHeatingSystem"] == "Custom":
                    st.number_input("Space heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_spaceCOP_custom", help=HELP["cop"])
                    st.number_input("Space heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_spaceInstall_custom")
                    st.caption(f"Custom: COP={float(st.session_state[f'{prefix}_spaceCOP_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_spaceInstall_custom']))}")

                select_with_placeholder("Water heating system", WATER_SYS_OPTS, key=f"{prefix}_waterHeatingSystem", help_text=HELP["cop"])
                show_system_caption("water_heating", st.session_state[f"{prefix}_waterHeatingSystem"])
                if st.session_state[f"{prefix}_waterHeatingSystem"] == "Custom":
                    st.number_input("Water heating COP", min_value=0.0, max_value=10.0, step=0.1, key=f"{prefix}_waterCOP_custom", help=HELP["cop"])
                    st.number_input("Water heating install capex (NZD)", min_value=0.0, max_value=50000.0, step=100.0, key=f"{prefix}_waterInstall_custom")
                    st.caption(f"Custom: COP={float(st.session_state[f'{prefix}_waterCOP_custom']):g} · {fmt_money(float(st.session_state[f'{prefix}_waterInstall_custom']))}")

            with st.expander("Water fixtures + appliances", expanded=True):
                select_with_placeholder("Toilet type", TOILET_OPTS, key=f"{prefix}_toiletType", help_text=HELP["fixture_general"])
                show_fixture_caption("toilet", st.session_state[f"{prefix}_toiletType"])
                if st.session_state[f"{prefix}_toiletType"] == "Custom":
                    st.number_input("Toilet litres/flush", min_value=1.0, max_value=20.0, step=0.5, key=f"{prefix}_toilet_value_custom")
                    st.number_input("Toilet install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_toilet_cost_custom")
                    st.caption(f"Custom: {float(st.session_state[f'{prefix}_toilet_value_custom']):g} L/flush · {fmt_money(float(st.session_state[f'{prefix}_toilet_cost_custom']))}")

                select_with_placeholder("Shower type", SHOWER_OPTS, key=f"{prefix}_showerType", help_text=HELP["fixture_general"])
                show_fixture_caption("shower", st.session_state[f"{prefix}_showerType"])
                if st.session_state[f"{prefix}_showerType"] == "Custom":
                    st.number_input("Shower flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_shower_value_custom")
                    st.number_input("Shower install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_shower_cost_custom")
                    st.caption(f"Custom: {float(st.session_state[f'{prefix}_shower_value_custom']):g} L/min · {fmt_money(float(st.session_state[f'{prefix}_shower_cost_custom']))}")

                select_with_placeholder("Tap type", TAP_OPTS, key=f"{prefix}_tapType", help_text=HELP["fixture_general"])
                show_fixture_caption("tap", st.session_state[f"{prefix}_tapType"])
                if st.session_state[f"{prefix}_tapType"] == "Custom":
                    st.number_input("Tap flow (L/min)", min_value=1.0, max_value=30.0, step=0.5, key=f"{prefix}_tap_value_custom")
                    st.number_input("Tap install capex (NZD)", min_value=0.0, max_value=20000.0, step=50.0, key=f"{prefix}_tap_cost_custom")
                    st.caption(f"Custom: {float(st.session_state[f'{prefix}_tap_value_custom']):g} L/min · {fmt_money(float(st.session_state[f'{prefix}_tap_cost_custom']))}")

                st.markdown("---")
                st.selectbox("Has washing machine?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_wash_has", help=HELP["wash_has"])
                if st.session_state[f"{prefix}_wash_has"] == "Yes":
                    st.number_input("Cycles/week (washing)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_wash_cycles")
                    st.number_input("L/cycle (washing)", min_value=0.0, max_value=300.0, step=5.0, key=f"{prefix}_wash_L")

                st.selectbox("Has dishwasher?", [PLACEHOLDER, "Yes", "No"], key=f"{prefix}_dish_has", help=HELP["dish_has"])
                if st.session_state[f"{prefix}_dish_has"] == "Yes":
                    st.number_input("Cycles/week (dishwasher)", min_value=0.0, max_value=50.0, step=1.0, key=f"{prefix}_dish_cycles")
                    st.number_input("L/cycle (dishwasher)", min_value=0.0, max_value=100.0, step=1.0, key=f"{prefix}_dish_L")

    # -------------------------------------------------------------------------
    # ROW 3: Usage + Fractions + Tariffs + Emissions (optional/advanced)
    # -------------------------------------------------------------------------
    with st.expander("Usage + Hot-water fractions + Tariffs + Emissions (Optional)", expanded=False):
        wc1, wc2 = st.columns(2, gap="small")

        with wc1:
            with st.expander("Usage assumptions (behaviour)", expanded=True):
                st.caption(HELP["usage_general"])
                st.number_input("Hot water setpoint (°C)", min_value=30.0, max_value=80.0, step=1.0, key=f"{prefix}_hotWater_setpoint_C")
                st.number_input("Cold water inlet (°C)", min_value=0.0, max_value=30.0, step=1.0, key=f"{prefix}_coldWater_inlet_C")
                st.number_input("Toilet flushes/person/day", min_value=0.0, max_value=20.0, step=0.5, key=f"{prefix}_toiletFlushes_ppd")
                st.number_input("Showers/person/day", min_value=0.0, max_value=5.0, step=0.1, key=f"{prefix}_showers_ppd")
                st.number_input("Minutes/shower", min_value=0.0, max_value=60.0, step=0.1, key=f"{prefix}_minutes_per_shower")
                st.number_input("Tap minutes/person/day", min_value=0.0, max_value=120.0, step=0.5, key=f"{prefix}_tapMinutes_ppd")

        with wc2:
            with st.expander("Hot-water fractions (advanced)", expanded=True):
                st.caption(HELP["hw_frac"])
                st.slider("Shower hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_shower")
                st.slider("Tap hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_tap")
                st.slider("Laundry hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_laundry")
                st.slider("Dishwasher hot water fraction", 0.0, 1.0, step=0.05, key=f"{prefix}_hw_frac_dishwasher")

            with st.expander("Tariffs + emission factors (advanced)", expanded=False):
                st.caption(HELP["tariffs"])
                st.number_input("Electricity tariff (NZD/kWh)", min_value=0.0, max_value=2.0, step=0.01, key=f"{prefix}_coef_elec_tariff")
                st.number_input("Water tariff (NZD/m³)", min_value=0.0, max_value=20.0, step=0.1, key=f"{prefix}_coef_water_tariff")

                st.caption(HELP["efs"])
                st.number_input("Grid emission factor (kgCO₂e/kWh)", min_value=0.0, max_value=1.0, step=0.0001, key=f"{prefix}_coef_grid_ef")
                st.number_input("Water emission factor (kgCO₂e/m³)", min_value=0.0, max_value=5.0, step=0.0001, key=f"{prefix}_coef_water_ef")
