import streamlit as st

# --- App Title ---
st.title("House Sustainability Calculator")

st.write("Fill in a few details about your house to get an overview of its sustainability performance.")

# --- SECTION 1: Efficient Use of Resources ---
st.header("1. Efficient Use of Resources")

st.subheader("Energy Efficiency")
area = st.number_input("Building floor area (m²)", min_value=0.0, step=1.0)
insulation = st.selectbox("Wall/Roof insulation type", ["None", "Standard", "High-performance"])
solar = st.radio("Is there a solar PV system installed?", ["Yes", "No"])

st.subheader("Water Efficiency")
rainwater = st.radio("Does the house have a rainwater harvesting system?", ["Yes", "No"])
dual_flush = st.radio("Does the toilet use a dual flush system?", ["Yes", "No"])

# --- SECTION 2: Health & Comfort ---
st.header("2. Health & Comfort")

double_glazing = st.radio("Are windows double-glazed?", ["Yes", "No"])
ventilation = st.selectbox("Ventilation type", ["Natural", "Mechanical", "Heat Recovery Ventilation (HRV)"])
natural_light = st.slider("Percentage of floor area with natural daylight (%)", 0, 100, 50)

# --- SECTION 3: Liveability ---
st.header("3. Liveability")

wheelchair_access = st.radio("Does the house provide wheelchair access (ramp/wide doors)?", ["Yes", "No"])
waste_sorting = st.radio("Are there recycling or composting facilities available?", ["Yes", "No"])
distance_transport = st.number_input("Distance to the nearest public transport stop (meters)", min_value=0, step=10)

# --- SUBMIT SECTION ---
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
    ef_score = min(ef_score, 40)  # Cap at 40

    # Health & Comfort scoring
    if double_glazing == "Yes":
        hc_score += 6
    if ventilation == "Heat Recovery Ventilation (HRV)":
        hc_score += 6
    elif ventilation == "Mechanical":
        hc_score += 3
    hc_score += (natural_light / 100) * 6  # up to 6 points for daylight
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

    # --- Total ---
    total_score = ef_score + hc_score + lv_score

    # --- Rating Level ---
    if total_score >= 80:
        rating = "Platinum"
    elif total_score >= 60:
        rating = "Gold"
    elif total_score >= 40:
        rating = "Silver"
    else:
        rating = "Bronze"

    # --- Display Results ---
    st.success("Calculation complete!")
    st.subheader("📊 Summary:")
    st.write(f"**Efficiency:** {ef_score:.1f}/40")
    st.write(f"**Health & Comfort:** {hc_score:.1f}/30")
    st.write(f"**Liveability:** {lv_score:.1f}/20")
    st.markdown(f"### 🏅 Total Score: **{total_score:.1f}/100** ({rating} Rating)")

    # --- Insights ---
    st.subheader("💡 Suggestions for Improvement")
    suggestions = []
    if solar == "No":
        suggestions.append("Consider installing a solar PV system to reduce energy use.")
    if rainwater == "No":
        suggestions.append("Add a rainwater harvesting system for water efficiency.")
    if ventilation == "Natural":
        suggestions.append("Mechanical or HRV ventilation can improve indoor comfort.")
    if natural_light < 40:
        suggestions.append("Increase natural lighting with larger or better-placed windows.")
    if distance_transport > 800:
        suggestions.append("Consider improving transport accessibility for residents.")

    if suggestions:
        for s in suggestions:
            st.write(f"- {s}")
    else:
        st.write("Your house performs very well across all categories!")

# --- Footer ---
st.write("---")
st.caption("Prototype v1.0 — Sustainability Calculator (Demo Version)")
