import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from dateutil import parser
import re
import urllib.parse
from PIL import Image
from io import BytesIO
import base64

# =======================================================
# PAGE CONFIG
# =======================================================
st.set_page_config(
    page_title="JobBot+ | Senior Analytics Radar",
    layout="wide"
)

if "jobs" not in st.session_state:
    st.session_state["jobs"] = []

# =======================================================
# LOGO + HEADER
# =======================================================
def load_logo_base64(path="vt_logo.png"):
    try:
        img = Image.open(path)
        buf = BytesIO()
        img.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

logo_b64 = load_logo_base64()

if logo_b64:
    st.markdown(
        f"<div style='text-align:center;'><img src='data:image/png;base64,{logo_b64}' width='140'></div>",
        unsafe_allow_html=True
    )

st.markdown(
    "<h3 style='text-align:center;'>JobBot+ — Senior Analytics / Decision Radar</h3>",
    unsafe_allow_html=True
)

st.caption(
    "JSearch is used only as a radar. Decisions are driven by relevance, noise filtering, and recruiter judgment."
)

st.markdown("---")

# =======================================================
# UTILITIES
# =======================================================
def parse_salary_to_lpa(text):
    if not text:
        return 0.0
    s = text.lower().replace(",", "")
    m = re.search(r"(\d+(\.\d+)?)\s*(lpa|lakh|lakhs)", s)
    if m:
        return float(m.group(1))
    m2 = re.search(r"₹?\s*(\d{6,})", s)
    if m2:
        return round(float(m2.group(1)) / 100000, 1)
    return 0.0

def job_age_days(posted_at):
    if not posted_at:
        return 999
    try:
        posted = parser.parse(posted_at)
        return (datetime.now(timezone.utc) - posted).days
    except:
        return 999

def linkedin_search_link(title, company):
    q = urllib.parse.quote(f"{title} {company}")
    return f"https://www.linkedin.com/jobs/search/?keywords={q}"

# =======================================================
# NOISE + ROLE FILTERING
# =======================================================
REJECT_KEYWORDS = [
    "data scientist", "machine learning", "deep learning",
    "nlp", "ml engineer", "data engineer", "ai engineer"
]

MANAGER_KEYWORDS = [
    "analytics manager", "group manager", "analytics lead",
    "decision analytics", "performance analytics",
    "business analytics manager", "risk analytics manager",
    "planning manager", "forecasting manager"
]

def naukri_noise_score(text):
    t = text.lower()
    noise_hits = sum(1 for k in REJECT_KEYWORDS if k in t)
    return min(100, noise_hits * 25)

def is_manager_role(text):
    t = text.lower()
    return any(k in t for k in MANAGER_KEYWORDS)

# =======================================================
# SCORING (RECRUITER-FIRST)
# =======================================================
KEY_SKILLS = [
    "forecasting", "planning", "kpi",
    "decision", "stakeholder",
    "performance", "portfolio"
]

def compute_score(job):
    text = f"{job['title']} {job['description']}".lower()
    hits = sum(1 for s in KEY_SKILLS if s in text)
    skill_score = int((hits / len(KEY_SKILLS)) * 100)

    salary_lpa = parse_salary_to_lpa(job.get("salary_text"))
    salary_score = min(100, int((salary_lpa / 30) * 100))

    final = int(skill_score * 0.6 + salary_score * 0.4)
    return final, salary_lpa

def worth_messaging(score, noise):
    if noise >= 60:
        return "No"
    if score >= 70:
        return "Yes"
    return "No"

def recruiter_dm(job):
    return (
        f"Hi, I lead forecasting and decision analytics in operations-heavy environments. "
        f"This {job['Title']} role aligns with my experience in planning, KPI ownership, "
        f"and leadership-facing analytics. Open to a brief discussion?"
    )

# =======================================================
# JSEARCH FETCH (RADAR ONLY)
# =======================================================
def fetch_jobs(query, location_query, pages):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": st.secrets["rapidapi"]["key"],
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": f"{query} ({location_query})",
        "num_pages": pages
    }

    r = requests.get(url, headers=headers, params=params)
    if r.status_code != 200:
        st.error("JSearch failed")
        return []

    data = r.json().get("data", [])
    jobs = []

    for j in data:
        jobs.append({
            "title": j.get("job_title", ""),
            "company": j.get("employer_name", ""),
            "location": j.get("job_city") or j.get("job_country"),
            "salary_text": j.get("job_salary"),
            "description": j.get("job_description") or "",
            "apply_link": j.get("job_apply_link"),
            "posted_at": j.get("job_posted_at_datetime_utc")
        })

    return jobs

# =======================================================
# SIDEBAR
# =======================================================
st.sidebar.header("Recruiter-First Search")

query = st.sidebar.text_input("Role focus", "Senior Analytics Manager")

time_window = st.sidebar.radio(
    "Posted within",
    ["Last 24 hours", "Last 3 days", "Last 7 days"],
    index=2
)

WINDOW_MAP = {"Last 24 hours": 1, "Last 3 days": 3, "Last 7 days": 7}
max_days = WINDOW_MAP[time_window]

locations = st.sidebar.multiselect(
    "Locations",
    ["India", "Mumbai", "Bengaluru", "Pune", "Hyderabad", "Chennai", "Remote"],
    default=["India"]
)
location_query = " OR ".join(locations)

min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0)
pages = st.sidebar.slider("Pages", 1, 3, 1)

# =======================================================
# FETCH + PROCESS
# =======================================================
if st.sidebar.button("Scan Market"):
    raw = fetch_jobs(query, location_query, pages)
    final = []

    for job in raw:
        if job_age_days(job.get("posted_at")) > max_days:
            continue

        combined_text = job["title"] + " " + job["description"]

        if not is_manager_role(combined_text):
            continue

        noise = naukri_noise_score(combined_text)
        score, salary = compute_score(job)

        if salary > 0 and salary < min_salary:
            continue

        worth = worth_messaging(score, noise)

        final.append({
            "Title": job["title"],
            "Company": job["company"],
            "Location": job["location"],
            "Posted": job.get("posted_at") or "Unknown",
            "Score": score,
            "Noise_Score": noise,
            "Worth_Messaging": worth,
            "Salary_LPA": salary,
            "LinkedIn_Search": linkedin_search_link(job["title"], job["company"]),
            "Recruiter_DM": recruiter_dm({
                "Title": job["title"]
            }) if worth == "Yes" else ""
        })

    st.session_state["jobs"] = final
    st.success(f"{len(final)} recruiter-grade roles surfaced")

# =======================================================
# DISPLAY
# =======================================================
jobs = st.session_state.get("jobs", [])

if jobs:
    df = pd.DataFrame(jobs).sort_values("Score", ascending=False)

    expected_cols = [
        "Title",
        "Company",
        "Location",
        "Posted",
        "Score",
        "Noise_Score",
        "Worth_Messaging",
        "Salary_LPA"
    ]

    available_cols = [c for c in expected_cols if c in df.columns]

    st.dataframe(
        df[available_cols],
        use_container_width=True
    )
    st.markdown("### Selected Role")
    idx = st.number_input("Select row", 0, len(df) - 1, 0)
    sel = df.iloc[idx]

    st.write("**Title:**", sel["Title"])
    st.write("**Company:**", sel["Company"])
    st.write("**Worth Messaging Recruiter:**", sel["Worth_Messaging"])

    st.markdown(f"[🔍 Open LinkedIn Search]({sel['LinkedIn_Search']})")

    if sel["Worth_Messaging"] == "Yes":
        st.markdown("**Suggested Recruiter DM**")
        st.code(sel["Recruiter_DM"])

st.caption("JobBot+ — Signal first. Outreach second. Apply last.")

