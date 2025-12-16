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

# -------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------
st.set_page_config(
    page_title="JobBot+ | Senior Analytics Radar",
    layout="wide"
)

# -------------------------------------------------------
# LOGO + HEADER (CLEAN, NOT LOUD)
# -------------------------------------------------------
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
        f"""
        <div style="text-align:center; margin-bottom:6px;">
            <img src="data:image/png;base64,{logo_b64}" width="160">
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown(
    "<h2 style='text-align:center; margin-top:0;'>JobBot+ — Senior Analytics / Group Manager Radar</h2>",
    unsafe_allow_html=True
)

st.caption(
    "JSearch is used only as a radar. All actions are driven via LinkedIn verification and human judgment."
)

st.markdown("---")

# -------------------------------------------------------
# UTILITIES
# -------------------------------------------------------
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


def verification_status(apply_link):
    if not apply_link:
        return "Needs verification"
    link = apply_link.lower()
    if "careers" in link or "jobs." in link:
        return "Career page found"
    return "Needs verification"


def decide_action(score, verification):
    if score >= 80 and verification == "Career page found":
        return "Apply"
    if score >= 70:
        return "Recruiter outreach"
    return "Ignore"


def linkedin_search_link(title, company):
    query = f"{title} {company}"
    encoded = urllib.parse.quote(query)
    return f"https://www.linkedin.com/jobs/search/?keywords={encoded}"

# -------------------------------------------------------
# ROLE FILTERING (STRICT, SENIOR-SAFE)
# -------------------------------------------------------
REJECT_KEYWORDS = [
    "data scientist",
    "machine learning",
    "deep learning",
    "nlp",
    "ml engineer"
]

MANAGER_KEYWORDS = [
    "analytics manager",
    "group manager",
    "analytics lead",
    "decision analytics",
    "performance analytics",
    "business analytics manager",
    "risk analytics manager"
]

def classify_job(text):
    t = (text or "").lower()
    if any(k in t for k in REJECT_KEYWORDS):
        return "reject"
    if any(k in t for k in MANAGER_KEYWORDS):
        return "manager"
    return "reject"

# -------------------------------------------------------
# SCORING (RADAR-GRADE, NOT ATS)
# -------------------------------------------------------
KEY_SKILLS = [
    "forecasting",
    "planning",
    "kpi",
    "performance",
    "decision",
    "stakeholder",
    "automation",
    "sql",
    "power bi"
]

def compute_score(job):
    text = f"{job['title']} {job['description']}".lower()
    hits = sum(1 for s in KEY_SKILLS if s in text)
    skill_score = int((hits / len(KEY_SKILLS)) * 100)
    salary_lpa = parse_salary_to_lpa(job.get("salary_text"))
    salary_score = min(100, int((salary_lpa / 30) * 100))
    final_score = int(skill_score * 0.5 + salary_score * 0.5)
    return final_score, salary_lpa

# -------------------------------------------------------
# JSEARCH FETCH — RADAR ONLY
# -------------------------------------------------------
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
        st.error("JSearch call failed")
        return []

    data = r.json().get("data", [])
    jobs = []

    for j in data:
        jobs.append({
            "title": j.get("job_title"),
            "company": j.get("employer_name"),
            "location": j.get("job_city") or j.get("job_country"),
            "salary_text": j.get("job_salary"),
            "description": j.get("job_description") or "",
            "apply_link": j.get("job_apply_link"),
            "posted_at": j.get("job_posted_at_datetime_utc")
        })

    return jobs

# -------------------------------------------------------
# SIDEBAR — SEARCH CONTROLS
# -------------------------------------------------------
st.sidebar.header("Search Controls")

query = st.sidebar.text_input("Job keyword", "analytics manager")

time_window = st.sidebar.radio(
    "Posted within",
    ["Last 24 hours", "Last 3 days", "Last 7 days"],
    index=2
)

WINDOW_MAP = {
    "Last 24 hours": 1,
    "Last 3 days": 3,
    "Last 7 days": 7
}
max_days = WINDOW_MAP[time_window]

locations = st.sidebar.multiselect(
    "Locations",
    ["India", "Mumbai", "Bengaluru", "Pune", "Hyderabad", "Chennai", "Remote"],
    default=["India"]
)
location_query = " OR ".join(locations)

min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0)
pages = st.sidebar.slider("Pages", 1, 3, 1)

# -------------------------------------------------------
# FETCH + PROCESS
# -------------------------------------------------------
if st.sidebar.button("Fetch Jobs"):
    raw_jobs = fetch_jobs(query, location_query, pages)
    final_jobs = []

    for job in raw_jobs:
        age = job_age_days(job.get("posted_at"))
        if age > max_days:
            continue

        if classify_job(job["title"] + job["description"]) == "reject":
            continue

        score, salary_lpa = compute_score(job)
        if salary_lpa > 0 and salary_lpa < min_salary:
            continue

        verification = verification_status(job.get("apply_link"))
        action = decide_action(score, verification)

        final_jobs.append({
            "Title": job["title"],
            "Company": job["company"],
            "Location": job["location"],
            "Posted_Date": job.get("posted_at") or "Unknown",
            "Verification_Status": verification,
            "Action": action,
            "Salary_LPA": salary_lpa,
            "Score": score,
            "Apply_Link": job.get("apply_link"),
            "LinkedIn_Search": linkedin_search_link(job["title"], job["company"])
        })

    st.session_state["jobs"] = final_jobs
    st.success(f"{len(final_jobs)} senior analytics leads identified")

# -------------------------------------------------------
# DISPLAY — DECISION FIRST
# -------------------------------------------------------
jobs = st.session_state.get("jobs", [])

if jobs:
    df = pd.DataFrame(jobs).sort_values("Score", ascending=False)

    st.dataframe(
        df[
            [
                "Title",
                "Company",
                "Location",
                "Posted_Date",
                "Verification_Status",
                "Action",
                "Salary_LPA",
                "Score",
                "LinkedIn_Search"
            ]
        ],
        use_container_width=True
    )

    st.markdown("### Job Details")
    idx = st.number_input("Select row", 0, len(df) - 1, 0)
    selected = df.iloc[idx]

    st.write("**Title:**", selected["Title"])
    st.write("**Company:**", selected["Company"])
    st.write("**Location:**", selected["Location"])
    st.write("**Posted Date (raw):**", selected["Posted_Date"])
    st.write("**Verification Status:**", selected["Verification_Status"])
    st.write("**Recommended Action:**", selected["Action"])
    st.write("🔗 **LinkedIn Search:**", selected["LinkedIn_Search"])
    st.write("Apply Link:", selected["Apply_Link"])

st.caption("JobBot+ — Radar first. LinkedIn second. Apply last.")
