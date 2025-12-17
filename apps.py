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

if "jobs" not in st.session_state:
    st.session_state["jobs"] = []

# -------------------------------------------------------
# LOGO + HEADER
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
            <img src="data:image/png;base64,{logo_b64}" width="140">
        </div>
        """,
        unsafe_allow_html=True
    )

st.markdown(
    "<h3 style='text-align:center; margin-top:0;'>JobBot+ — Senior Analytics / Group Manager Radar</h3>",
    unsafe_allow_html=True
)

st.caption(
    "JSearch is used only as a radar. Final decisions happen via LinkedIn and career pages."
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


def linkedin_search_link(title, company):
    q = f"{title} {company}"
    return "https://www.linkedin.com/jobs/search/?keywords=" + urllib.parse.quote(q)


def verification_status(link):
    if not link:
        return "Needs verification"
    l = link.lower()
    if "career" in l or "jobs." in l:
        return "Career page found"
    return "Needs verification"

# -------------------------------------------------------
# ROLE & NOISE LOGIC
# -------------------------------------------------------
REJECT_KEYWORDS = [
    "data scientist", "machine learning", "deep learning",
    "nlp", "ml engineer", "computer vision"
]

MANAGER_KEYWORDS = [
    "analytics manager", "group manager", "analytics lead",
    "decision analytics", "performance analytics",
    "business analytics manager", "risk analytics manager"
]

NOISE_KEYWORDS = [
    "python developer", "data engineer", "spark", "airflow",
    "etl", "mlops", "deep learning"
]

def classify_job(text):
    t = (text or "").lower()
    if any(k in t for k in REJECT_KEYWORDS):
        return "reject"
    if any(k in t for k in MANAGER_KEYWORDS):
        return "manager"
    return "reject"


def noise_score(text):
    t = (text or "").lower()
    return sum(1 for k in NOISE_KEYWORDS if k in t)


def worth_messaging(score, noise):
    if score >= 75 and noise <= 1:
        return "Yes"
    return "No"

# -------------------------------------------------------
# SCORING
# -------------------------------------------------------
KEY_SIGNALS = [
    "forecasting", "planning", "kpi",
    "decision", "stakeholder",
    "performance", "governance"
]

def compute_score(job):
    text = f"{job.get('title','')} {job.get('description','')}".lower()
    signal_hits = sum(1 for s in KEY_SIGNALS if s in text)
    skill_score = int((signal_hits / len(KEY_SIGNALS)) * 100)

    salary_lpa = parse_salary_to_lpa(job.get("salary_text"))
    salary_score = min(100, int((salary_lpa / 30) * 100))

    final = int(skill_score * 0.6 + salary_score * 0.4)
    return final, salary_lpa

# -------------------------------------------------------
# JSEARCH FETCH (RADAR ONLY)
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
# SIDEBAR
# -------------------------------------------------------
st.sidebar.header("Search Controls")

query = st.sidebar.text_input("Job keyword", "analytics manager")

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

# -------------------------------------------------------
# FETCH + PROCESS
# -------------------------------------------------------
if st.sidebar.button("Fetch Jobs"):
    raw = fetch_jobs(query, location_query, pages)
    final = []

    for job in raw:
        if job_age_days(job.get("posted_at")) > max_days:
            continue

        if classify_job(job.get("title","") + job.get("description","")) == "reject":
            continue

        score, salary = compute_score(job)
        if salary > 0 and salary < min_salary:
            continue

        noise = noise_score(job.get("description"))
        worth = worth_messaging(score, noise)

        final.append({
            "Title": job.get("title"),
            "Company": job.get("company"),
            "Location": job.get("location"),
            "Posted": job.get("posted_at") or "Unknown",
            "Score": score,
            "Salary_LPA": salary,
            "Noise_Score": noise,
            "Worth_Messaging": worth,
            "Apply_Link": job.get("apply_link"),
            "LinkedIn_Search": linkedin_search_link(job.get("title"), job.get("company"))
        })

    st.session_state["jobs"] = final
    st.success(f"{len(final)} relevant senior analytics leads found")

# -------------------------------------------------------
# DISPLAY
# -------------------------------------------------------
jobs = st.session_state.get("jobs", [])

if jobs:
    df = pd.DataFrame(jobs).sort_values("Score", ascending=False)

    expected = [
        "Title", "Company", "Location", "Posted",
        "Score", "Salary_LPA", "Noise_Score", "Worth_Messaging"
    ]
    cols = [c for c in expected if c in df.columns]

    st.dataframe(df[cols], use_container_width=True)

    st.markdown("### Job Details")
    idx = st.number_input("Select row", 0, len(df) - 1, 0)
    sel = df.iloc[idx]

    st.write("**Title:**", sel.get("Title"))
    st.write("**Company:**", sel.get("Company"))
    st.write("**Location:**", sel.get("Location"))
    st.write("**Posted:**", sel.get("Posted"))
    st.write("**Score:**", sel.get("Score"))
    st.write("**Noise Score:**", sel.get("Noise_Score"))
    st.write("**Worth Messaging Recruiter:**", sel.get("Worth_Messaging"))

    if sel.get("LinkedIn_Search"):
        st.markdown(f"[🔍 Open LinkedIn Search]({sel['LinkedIn_Search']})")

    if sel.get("Apply_Link"):
        st.markdown(f"[🏢 Open Company Career Page]({sel['Apply_Link']})")

st.caption("JobBot+ — Radar first. LinkedIn second. Apply last.")

