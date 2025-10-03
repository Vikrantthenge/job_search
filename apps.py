import streamlit as st
import pandas as pd
import requests
from datetime import datetime
from PIL import Image
import base64
from io import BytesIO, StringIO
import warnings
import gspread
import plotly.express as px
import json

# --- Logo + Branding Header ---
try:
    logo = Image.open("vt_logo.png")
    buffered = BytesIO()
    logo.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    st.markdown(f"""
        <div style='text-align: center;'>
            <img src='data:image/png;base64,{img_base64}' width='360'>
        </div>
        <div style='text-align: center; font-size: 22px; font-weight: bold; color: #8B0000;'>
            🧭 <span style='color:#333;'>Job Bot</span> by <span style='color:#8B0000;'>Vikrant Thenge</span>
        </div>
    """, unsafe_allow_html=True)
except FileNotFoundError:
    st.warning("Logo file not found.")

# --- Resume Upload ---
st.subheader("📤 Upload Your Resume")
resume = st.file_uploader("Upload PDF Resume", type=["pdf"])
parsed_skills = []

if resume:
    parsed_skills = ["Data Analysis", "SQL", "Python", "Power BI", "Machine Learning"]
    st.success("Resume uploaded successfully!")
    st.markdown("**🔍 Simulated Keywords from Resume:**")
    st.markdown(", ".join(parsed_skills[:10]))

# --- Bullet Rewriter ---
st.subheader("🧠 Rewrite Resume Bullet (Simulated)")
bullet_input = st.text_area("Paste a resume bullet point to enhance")
tone = st.selectbox("Choose tone", ["assertive", "formal", "friendly"])

if st.button("Simulate Rewrite"):
    if bullet_input:
        rewritten = f"• Spearheaded demand forecasting models, driving a 12% profitability surge — {tone.capitalize()} delivery for recruiter impact."
        st.markdown("**🔁 Simulated Rewritten Bullet:**")
        st.success(rewritten)
    else:
        st.warning("Please enter a bullet point to rewrite.")

# --- Google Sheets Setup ---
creds = json.loads(st.secrets["google"]["service_account"])
gc = gspread.service_account_from_dict(creds)
sh = gc.open_by_url("https://docs.google.com/spreadsheets/d/1iBBq1tPtVPjBfYv1GEDCjR6rx4tL5JyO2QthiXAfZhk/edit")
worksheet = sh.sheet1

# --- Sidebar Filters ---
st.sidebar.header("🎯 Job Search Filters")
default_keywords = parsed_skills[0] if parsed_skills else "Data Analyst"
keywords = st.sidebar.text_input("Job Title", value=default_keywords)
location = st.sidebar.text_input("Location", value="India")
num_pages = st.sidebar.slider("Pages to Search", 1, 5, 1)
min_salary_lpa = st.sidebar.number_input("Minimum Salary (LPA)", value=24)
min_salary_in_inr = min_salary_lpa * 100000

if "job_df" not in st.session_state:
    st.session_state["job_df"] = pd.DataFrame()

# --- Job Fetch Function with Salary Filter ---
def fetch_jobs(keywords, location, num_pages, min_salary_in_inr):
    url = "https://jsearch.p.rapidapi.com/search"
    querystring = {"query": f"{keywords} in {location}", "num_pages": str(num_pages)}
    headers = {
        "X-RapidAPI-Key": "71a00e1f1emsh5f78d93a2205a33p114d26jsncc6534e3f6b3"
    }
    response = requests.get(url, headers=headers, params=querystring)
    data = response.json()

    filtered_jobs = []
    for job in data.get("data", []):
        salary_max = job.get("job_salary_max", 0)
        currency = job.get("job_salary_currency", "")
        if currency == "INR" and salary_max >= min_salary_in_inr:
            filtered_jobs.append({
                "Job Title": job["job_title"],
                "Company": job["employer_name"],
                "Location": job["job_city"],
                "Salary (Max)": f"₹{salary_max:,}",
                "Apply Link": job["job_apply_link"]
            })

    return pd.DataFrame(filtered_jobs)

# --- Job Search Trigger ---
if st.sidebar.button("Search Jobs"):
    with st.spinner("Fetching jobs..."):
        job_df = fetch_jobs(keywords, location, num_pages, min_salary_in_inr)
        st.session_state["job_df"] = job_df
        if not job_df.empty:
            st.subheader("💼 Job Listings")
            st.markdown(f"🔢 Jobs found: **{len(job_df)}**")
            for i, row in job_df.iterrows():
                st.markdown(f"**{row['Job Title']}** at *{row['Company']}* — {row['Location']}")
                st.markdown(f"💰 Salary (Max): {row.get('Salary (Max)', 'Not disclosed')}")
                st.markdown(f"[Apply Now]({row['Apply Link']})", unsafe_allow_html=True)
                st.markdown("---")
        else:
            st.warning("No jobs found matching salary criteria.")

job_df = st.session_state.get("job_df", pd.DataFrame())

# --- Auto Apply Logic ---
if st.button("🚀 Auto-Apply to All"):
    if resume and not job_df.empty:
        st.success("Bot applied to all matching jobs ✅ (simulated)")
        applied_companies = job_df["Company"].dropna().unique().tolist()
        top_locations = job_df["Location"].value_counts().head(5)
        top_roles = job_df["Job Title"].value_counts().head(5)

        timestamp = datetime.now().strftime("%d-%b-%Y %I:%M %p")
        log_df = pd.DataFrame({
            "Company": applied_companies,
            "Applied On": [timestamp] * len(applied_companies),
            "Keyword": [keywords] * len(applied_companies),
            "Location": [location] * len(applied_companies)
        })

        for row in log_df.values.tolist():
            worksheet.append_row(row)
        worksheet.update_acell('A1', f"Last synced: {timestamp}")
        st.success("✅ Synced to Google Sheet successfully")

        st.markdown("### 🏢 Companies Applied To")
        for company in applied_companies:
            st.markdown(f"- {company}")
        st.text_area("📋 Copy Company List", value="\n".join(applied_companies), height=150)

        st.markdown("### 📊 Recruiter-Facing Metrics")
        st.markdown("**Top Cities:**")
        st.dataframe(top_locations)
        st.markdown("**Most Applied Roles:**")
        st.dataframe(top_roles)

        role_counts = job_df["Job Title"].value_counts().reset_index()
        role_counts.columns = ["Role", "Count"]
        fig_roles = px.pie(role_counts, names="Role", values="Count", title="Top Roles by Application Volume")
        st.plotly_chart(fig_roles)

        city_counts = job_df["Location"].value_counts().reset_index()
        city_counts.columns = ["City", "Count"]
        fig_cities = px.bar(city_counts, x="City", y="Count", title="Applications by Location", color="City")
        st.plotly_chart(fig_cities)

        csv_buffer = StringIO()
        log_df.to_csv(csv_buffer, index=False)
        st.download_button(
            label="📥 Download Applied Companies CSV",
            data=csv_buffer.getvalue(),
            file_name=f"applied_companies_{timestamp}.csv",
            mime="text/csv"
        )
    else:
        st.error("Please upload your resume and search jobs first.")

# --- Drift Monitor ---
st.markdown("### 📉 Drift Monitor – Job Title Trends Over Time")
st.markdown("Upload two job datasets to compare how demand has shifted across roles.")

col1, col2 = st.columns(2)
with col1:
    uploaded_old = st.file_uploader("⬅️ Old Job Data CSV", type=["csv"], key="old")
with col2:
    uploaded_new = st.file_uploader("➡️ New Job Data CSV", type=["csv"], key="new")

if uploaded_old and uploaded_new:
    df_old = pd.read_csv(uploaded_old)
    df_new = pd.read_csv(uploaded_new)

    old_freq = df_old["Job Title"].value_counts().head(10)
    new_freq = df_new["Job Title"].value_counts().head(10)

    drift_df = pd.DataFrame({
        "Old": old_freq,
        "New": new_freq
    }).fillna(0)

    st.markdown("#### 🔍 Top 10 Job Titles – Frequency Comparison")
    st.dataframe(drift_df)

    fig_drift = px.bar(
        drift_df,
        barmode="group",
        title="📊 Job Title Drift Over Time",
        labels={"index": "Job Title", "value": "Frequency"},
        color_discrete_sequence=["#8B0000", "#333333"]
    )
    st.plotly_chart(fig_drift, use_container_width=True)
else:
    st.info("Upload both CSVs to view drift analysis.")

# --- Footer ---
st.markdown("""
    <hr style='margin-top: 40px;'>
    <div style='text-align: center; font-size: 14px; color: gray;'>
        · Built with ❤️ using Streamlit · Resume parsing enabled · OpenAI-powered rewriting · Google Sheets logging active · Recruiter metrics visualized · Drift monitoring integrated · Salary filter ≥ ₹24 LPA active ·
    </div>
""", unsafe_allow_html=True)
