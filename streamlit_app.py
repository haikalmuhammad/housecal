import streamlit as st

# --- App Title ---
st.title("House Sustainability Calculator")

st.write("Fill in the details below to get an overview of your house's sustainability performance.")

# ============================================================
# 1. Efficient Use of Resources
# ============================================================
st.header("1. Efficient Use of Resources")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Energy Efficiency")
    area = st.number_input("Building floor area (m²)", min_value=0.0, step=1.0)
    insulation = st.selectbox("Wall/Roof insulation type", ["None", "Standard", "High-performance"])
    solar = st.radio("Solar PV system installed?", ["Yes", "No"])

with col2:
    st.subheader("Water Efficiency")
    rainwater = st.radio("Rainwater harvesting system?", ["Yes", "No"])
    dual_flush = st.radio("Dual flush toilet?", ["Yes", "No"])

# ============================================================
# 2. Health & Comfort
# ============================================================
st.header("2. Health & Comfort")

col3, col4 = st.columns(2)

with col3:
    double_glazing = st.radio("Double-glazed windows?", ["Yes", "No"])
    ventilation = st.selectbox("Ventilation type", ["Natural", "Mechanical", "Heat Recovery Ventilation (HRV)"])

with col4:
    natural_light = st.slider("Natural daylight coverage (%)", 0, 100, 50)

# ============================================================
# 3. Liveability
# ============================================================
st.header("3. Liveability")

col5, col6 = st.columns(2)

with col5:
    wheelchair_access = st.radio("Wheelchair access (ramp/wide doors)?", ["Yes", "No"])
    waste_sorting = st.radio("Recycling or composting facilities available?", ["Yes", "No"])

with col6:
    distance_transport = st.number_input("Distance to nearest public transport (m)", min_value=0, step=10)

# ============================================================
# Calculation
# ============================================================
if st.button("Calculate Score"):

    # --- Scoring System ---
    ef_score = 0
    hc_score = 0
    lv_score = 0

    # Efficient scoring
    if insulation == "High-performance":
        ef_score += 8
    elif insulation == "Standard":
        ef_score += 4
    if solar == "Yes":
        ef_score += 8
    if rainwater == "Yes":
        ef_score += 4
    if dual_flush == "Yes":
        ef_score += 4
    ef_score = min(ef_score, 40)

    # Health & Comfort scoring
    if double_glazing == "Yes":
        hc_score += 6
    if ventilation == "Heat Recovery Ventilation (HRV)":
        hc_score += 6
    elif ventilation == "Mechanical":
        hc_score += 3
    hc_score += (natural_light / 100) * 6
    hc_score = min(hc_score, 30)

    # Liveability scoring
    if wheelchair_access == "Yes":
        lv_score += 5
    if waste_sorting == "Yes":
        lv_score += 5
    if distance_transport <= 400:
        lv_score += 10
    elif distance_transport <= 800:
        lv_score += 6
    else:
        lv_score += 2
    lv_score = min(lv_score, 20)

    total_score = ef_score + hc_score + lv_score

    # --- Rating ---
    if total_score >= 80:
        rating = "Platinum"
    elif total_score >= 60:
        rating = "Gold"
    elif total_score >= 40:
        rating = "Silver"
    else:
        rating = "Bronze"

    # ============================================================
    # Results
    # ============================================================
    st.success("Calculation complete")

    c1, c2, c3 = st.columns(3)
    with c1:
        st.metric("Efficiency", f"{ef_score:.1f}/40")
    with c2:
        st.metric("Health & Comfort", f"{hc_score:.1f}/30")
    with c3:
        st.metric("Liveability", f"{lv_score:.1f}/20")

    st.markdown(f"### Total Score: **{total_score:.1f}/100** ({rating} Rating)")

    # ============================================================
    # Recommendations
    # ============================================================
    st.subheader("Suggestions for Improvement")

    suggestions = []
    if solar == "No":
        suggestions.append("Install a solar PV system to reduce energy use.")
    if rainwater == "No":
        suggestions.append("Add a rainwater harvesting system for better water efficiency.")
    if ventilation == "Natural":
        suggestions.append("Consider mechanical or HRV ventilation for improved indoor air quality.")
    if natural_light < 40:
        suggestions.append("Increase natural lighting with larger or better-positioned windows.")
    if distance_transport > 800:
        suggestions.append("Improve accessibility to public transport for residents.")

    if suggestions:
        for s in suggestions:
            st.write(f"- {s}")
    else:
        st.write("Your house performs well across all categories.")

# ============================================================
# Footer
# ============================================================
st.write("---")
st.caption("Prototype v1.1 — Sustainability Calculator (Demo Version)")
