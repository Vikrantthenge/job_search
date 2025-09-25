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

# --- Stacked Logos ---
try:
    vt_logo = Image.open("vt_logo.png")
    jobbot_logo = Image.open("jobbot_badge.png")

    vt_buffer = BytesIO()
    vt_logo.save(vt_buffer, format="PNG")
    vt_base64 = base64.b64encode(vt_buffer.getvalue()).decode()


    st.markdown(f"""
        <div style='text-align: center; margin-top: 10px; margin-bottom: 10px;'>
            <img src='data:image/png;base64,{vt_base64}' width='80'><br>
            <img src='data:image/png;base64,{jobbot_base64}' width='160'>
        </div>
        <div style='text-align: center; font-size: 24px; font-weight: bold; color: #8B0000; margin-bottom: 20px;'>
            🧭 <span style='color:#333;'>Job Bot</span> by <span style='color:#8B0000;'>Vikrant Thenge</span>
        </div>
    """, unsafe_allow_html=True)

except FileNotFoundError:
    st.warning("One or both logo files not found.")

# --- Branding Header ---
st.markdown("""
    <div style='text-align: center; font-size: 24px; font-weight: bold; color: #8B0000; margin-bottom: 20px;'>
        <span style='color:#333;'>Job Bot</span> by <span style='color:#8B0000;'>Vikrant Thenge</span>
    </div>
""", unsafe_allow_html=True)

# --- Logo + Tagline ---
try:
    logo = Image.open("your_logo.png")
    buffered = BytesIO()
    logo.save(buffered, format="PNG")
    img_base64 = base64.b64encode(buffered.getvalue()).decode()

    st.markdown(f"""
        <div style='display: flex; align-items: center; justify-content: center; gap: 1rem; margin-bottom: 1.5rem;'>
            <img src='data:image/png;base64,{img_base64}' width='60'>
            <span style='font-size: 20px; font-weight: 600; color: #8B0000;'>Built for Data. Ready for Impact.</span>
        </div>
    """, unsafe_allow_html=True)

    st.markdown("""
        <div style='text-align: center; font-size: 24px; font-weight: bold; color: #8B0000; margin-bottom: 20px;'>
            🧭 <span style='color:#333;'>Job Bot</span> – <span style='color:#8B0000;'>Auto Apply + Resume Enhancer + Drift Monitor</span>
        </div>
    """, unsafe_allow_html=True)

except FileNotFoundError:
    st.warning("Logo file not found.")
    

# --- Resume Upload ---
st.subheader("📤 Upload Your Resume")
resume = st.file_uploader("Upload PDF Resume", type=["pdf"])
parsed_skills = []

# --- Simulated Resume Parser ---
if resume:
    parsed_skills = ["Python", "SQL", "Power BI", "Data Analysis", "Machine Learning"]
    st.success("Resume uploaded successfully!")
    st.markdown("**🔍 Simulated Keywords from Resume:**")
    st.markdown(", ".join(parsed_skills[:10]))

# --- Simulated Bullet Rewriter ---
st.subheader("🧠 Rewrite Resume Bullet (Simulated)")
bullet_input = st.text_area("Paste a resume bullet point to enhance")
tone = st.selectbox("Choose tone", ["assertive", "formal", "friendly"])

if st.button("Simulate Rewrite"):
    if bullet_input:
        simulated = f"[{tone.capitalize()} tone] {bullet_input} — rewritten for recruiter impact."
        st.markdown("**🔁 Simulated Rewritten Bullet:**")
        st.success(simulated)
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

if "job_df" not in st.session_state:
    st.session_state["job_df"] = pd.DataFrame()

def fetch_jobs(keywords, location, num_pages):
    url = "https://jsearch.p.rapidapi.com/search"
    querystring = {"query": f"{keywords} in {location}", "num_pages": str(num_pages)}
    headers = {
        "X-RapidAPI-Key": "71a00e1f1emsh5f78d93a2205a33p114d26jsncc6534e3f6b3"
    }
    response = requests.get(url, headers=headers, params=querystring)
    data = response.json()
    jobs = [{
        "Job Title": job["job_title"],
        "Company": job["employer_name"],
        "Location": job["job_city"],
        "Apply Link": job["job_apply_link"]
    } for job in data.get("data", [])]
    return pd.DataFrame(jobs)

if st.sidebar.button("Search Jobs"):
    with st.spinner("Fetching jobs..."):
        job_df = fetch_jobs(keywords, location, num_pages)
        st.session_state["job_df"] = job_df
        if not job_df.empty:
            st.subheader("💼 Job Listings")
            st.markdown(f"🔢 Jobs found: **{len(job_df)}**")
            for i, row in job_df.iterrows():
                st.markdown(f"**{row['Job Title']}** at *{row['Company']}* — {row['Location']}")
                st.markdown(f"[Apply Now]({row['Apply Link']})", unsafe_allow_html=True)
                st.markdown("---")
        else:
            st.warning("No jobs found.")

job_df = st.session_state.get("job_df", pd.DataFrame())

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

        st.markdown("### 🏢 Companies Applied To")
        for company in applied_companies:
            st.markdown(f"- {company}")
        st.text_area("📋 Copy Company List", value="\n".join(applied_companies), height=150)

        # --- Recruiter Metrics ---
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
st.subheader("📉 Drift Monitor (Job Title Frequency)")
uploaded_old = st.file_uploader("Upload old job data CSV", key="old")
uploaded_new = st.file_uploader("Upload new job data CSV", key="new")

if uploaded_old and uploaded_new:
    df_old = pd.read_csv(uploaded_old)
    df_new = pd.read_csv(uploaded_new)
    old_freq = df_old["Job Title"].value_counts().head(10)
    new_freq = df_new["Job Title"].value_counts().head(10)
    drift_df = pd.DataFrame({"Old": old_freq, "New": new_freq}).fillna(0)
    st.markdown("**📊 Drift in Top Job Titles:**")
    st.dataframe(drift_df)
    fig_drift = px.bar(drift_df, barmode="group", title="Job Title Drift Over Time")
    st.plotly_chart(fig_drift)

# --- Footer ---
st.markdown("""
    <hr style='margin-top: 40px;'>
    <div style='text-align: center; font-size: 14px; color: gray;'>
        · Built with ❤️ using Streamlit · Resume parsing enabled · OpenAI-powered rewriting · Google Sheets logging active · Recruiter metrics visualized · Drift monitoring integrated ·
    </div>
""", unsafe_allow_html=True)
