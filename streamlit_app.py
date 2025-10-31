import streamlit as st
import pandas as pd

# ------------------------------------------------------------
# App Title & Intro
# ------------------------------------------------------------
st.title("House Sustainability Calculator")

st.markdown("""
This tool provides a simplified sustainability assessment for residential buildings.  
It evaluates three dimensions — **Efficiency**, **Health & Comfort**, and **Liveability** — 
based on basic building characteristics.
""")

# ------------------------------------------------------------
# 1. Efficient Use of Resources
# ------------------------------------------------------------
st.header("1. Efficient Use of Resources")

col1, col2 = st.columns(2)

with col1:
    st.subheader("Energy Efficiency")
    area = st.number_input("Building floor area (m²)", min_value=0.0, step=1.0)
    insulation = st.selectbox(
        "Wall/Roof insulation type", 
        ["None", "Standard", "High-performance"], 
        help="Higher insulation performance reduces heating and cooling demand."
    )
    solar = st.radio("Solar PV system installed?", ["Yes", "No"])

with col2:
    st.subheader("Water Efficiency")
    rainwater = st.radio("Rainwater harvesting system?", ["Yes", "No"])
    dual_flush = st.radio("Dual flush toilet?", ["Yes", "No"])

# ------------------------------------------------------------
# 2. Health & Comfort
# ------------------------------------------------------------
st.header("2. Health & Comfort")

col3, col4 = st.columns(2)

with col3:
    double_glazing = st.radio("Double-glazed windows?", ["Yes", "No"])
    ventilation = st.selectbox(
        "Ventilation type", 
        ["Natural", "Mechanical", "Heat Recovery Ventilation (HRV)"],
        help="HRV systems improve indoor air quality and heat recovery."
    )

with col4:
    natural_light = st.slider(
        "Natural daylight coverage (%)", 
        0, 100, 50, 
        help="Estimate the percentage of living spaces with good daylight access."
    )

# ------------------------------------------------------------
# 3. Liveability
# ------------------------------------------------------------
st.header("3. Liveability")

col5, col6 = st.columns(2)

with col5:
    wheelchair_access = st.radio("Wheelchair access (ramp/wide doors)?", ["Yes", "No"])
    waste_sorting = st.radio("Recycling or composting facilities available?", ["Yes", "No"])

with col6:
    distance_transport = st.number_input(
        "Distance to nearest public transport (m)", 
        min_value=0, step=10,
        help="Approximate walking distance to the nearest bus/train stop."
    )

# ------------------------------------------------------------
# Scoring & Calculation
# ------------------------------------------------------------
if st.button("Calculate Score"):

    ef_score, hc_score, lv_score = 0, 0, 0

    # Efficiency Scoring
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

    # Health & Comfort Scoring
    if double_glazing == "Yes":
        hc_score += 6
    if ventilation == "Heat Recovery Ventilation (HRV)":
        hc_score += 6
    elif ventilation == "Mechanical":
        hc_score += 3
    hc_score += (natural_light / 100) * 6
    hc_score = min(hc_score, 30)

    # Liveability Scoring
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

    # Rating Interpretation
    if total_score >= 80:
        rating = "Platinum"
        description = "Outstanding performance with strong sustainability measures."
    elif total_score >= 60:
        rating = "Gold"
        description = "Above average performance with potential for improvement."
    elif total_score >= 40:
        rating = "Silver"
        description = "Moderate performance, several areas could be improved."
    else:
        rating = "Bronze"
        description = "Basic level, consider additional sustainability features."

    # ------------------------------------------------------------
    # Results Display
    # ------------------------------------------------------------
    st.success("Calculation complete")

    col_r1, col_r2, col_r3 = st.columns(3)
    with col_r1:
        st.metric("Efficiency", f"{ef_score:.1f}/40")
    with col_r2:
        st.metric("Health & Comfort", f"{hc_score:.1f}/30")
    with col_r3:
        st.metric("Liveability", f"{lv_score:.1f}/20")

    st.markdown(f"### Total Score: **{total_score:.1f}/100** ({rating})")
    st.write(description)

    # ------------------------------------------------------------
    # Visualization
    # ------------------------------------------------------------
    st.subheader("Category Comparison")
    df_chart = pd.DataFrame({
        'Category': ['Efficiency', 'Health & Comfort', 'Liveability'],
        'Score': [ef_score, hc_score, lv_score],
        'Max': [40, 30, 20]
    })
    df_chart['Percentage'] = df_chart['Score'] / df_chart['Max'] * 100
    st.bar_chart(df_chart.set_index('Category')['Percentage'])

    # ------------------------------------------------------------
    # Transparency Table
    # ------------------------------------------------------------
    st.subheader("How Scores Are Calculated")
    st.markdown("""
    | Category | Key Criteria | Maximum Points |
    |-----------|--------------|----------------|
    | Efficiency | Insulation, solar PV, water use | 40 |
    | Health & Comfort | Glazing, ventilation, daylight | 30 |
    | Liveability | Accessibility, waste, transport | 20 |
    | **Total** |  | **100** |
    """)
    
    # ------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------
    st.subheader("Suggestions for Improvement")
    suggestions = []
    if solar == "No":
        suggestions.append("Install a solar PV system to reduce energy use.")
    if rainwater == "No":
        suggestions.append("Add a rainwater harvesting system to save water.")
    if ventilation == "Natural":
        suggestions.append("Consider mechanical or HRV ventilation to improve air quality.")
    if natural_light < 40:
        suggestions.append("Increase natural light by enlarging or repositioning windows.")
    if distance_transport > 800:
        suggestions.append("Enhance accessibility to nearby public transport.")
    if not suggestions:
        st.write("Your building performs well across all assessed categories.")
    else:
        for s in suggestions:
            st.write(f"- {s}")

# ------------------------------------------------------------
# Footer
# ------------------------------------------------------------
st.write("---")
st.caption("Prototype v2.0 — House Sustainability Calculator | For demonstration purposes only")
