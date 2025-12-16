import streamlit as st
import json
import gspread
from PIL import Image
from io import BytesIO
import base64
import requests
import pandas as pd
from datetime import datetime
import re
import uuid
from twilio.rest import Client as TwilioClient

# -------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------
st.set_page_config(page_title="JobBot+ | Manager Mode", layout="wide")

# -------------------------------------------------------
# LOGO + TITLE
# -------------------------------------------------------
def load_logo_base64():
    try:
        logo = Image.open("vt_logo.png")
        buf = BytesIO()
        logo.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

logo_b64 = load_logo_base64()
if logo_b64:
    st.markdown(
        f"<div style='text-align:center;'><img src='data:image/png;base64,{logo_b64}' width='240'></div>",
        unsafe_allow_html=True
    )

st.markdown(
    "<h1 style='text-align:center;'>JobBot+ — Senior Analytics Manager Mode</h1>",
    unsafe_allow_html=True
)

# -------------------------------------------------------
# GOOGLE SHEET
# -------------------------------------------------------
@st.cache_resource
def google_sheet():
    creds = json.loads(st.secrets["google"]["service_account"])
    gc = gspread.service_account_from_dict(creds)
    sh = gc.open_by_url(st.secrets["google"]["sheet_url"])
    return sh.sheet1

worksheet = google_sheet()

# -------------------------------------------------------
# UTILITIES
# -------------------------------------------------------
def uid():
    return uuid.uuid4().hex[:8]

def detect_emails(text):
    return list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")))

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

# -------------------------------------------------------
# MANAGER-LEVEL SKILLS (SCORING ONLY)
# -------------------------------------------------------
USER_SKILLS = [
    "forecasting",
    "planning",
    "capacity planning",
    "scenario modeling",
    "kpi",
    "performance analytics",
    "decision analytics",
    "python",
    "sql",
    "power bi",
    "automation"
]

def skill_match_score(text):
    t = (text or "").lower()
    hits = [s for s in USER_SKILLS if s in t]
    score = int(len(hits) / len(USER_SKILLS) * 100)
    return score, hits

# -------------------------------------------------------
# ROLE CLASSIFICATION (MANAGER-ONLY)
# -------------------------------------------------------
CLASS_KEYWORDS = {
    "manager": [
        "senior analytics manager",
        "analytics manager",
        "decision analytics",
        "planning",
        "forecasting",
        "capacity planning",
        "performance analytics",
        "kpi framework",
        "business analytics manager"
    ],
    "reject_ic": [
        "data scientist",
        "machine learning",
        "deep learning",
        "nlp",
        "classification",
        "model development",
        "ml engineer"
    ]
}

def classify_job(text):
    t = (text or "").lower()
    if any(k in t for k in CLASS_KEYWORDS["reject_ic"]):
        return "reject"
    if any(k in t for k in CLASS_KEYWORDS["manager"]):
        return "manager"
    return "reject"

# -------------------------------------------------------
# JOB SCORING
# -------------------------------------------------------
def compute_job_score(job):
    text = f"{job['title']} {job['description']}"
    skill_score, hits = skill_match_score(text)
    salary_lpa = parse_salary_to_lpa(job.get("salary_text"))
    sal_score = min(100, int((salary_lpa / 30) * 100))
    final = int(skill_score * 0.4 + sal_score * 0.6)
    return final, skill_score, salary_lpa, hits

# -------------------------------------------------------
# RESUME SNIPPET (MANAGER SIGNAL)
# -------------------------------------------------------
def generate_resume_snippet(company):
    return (
        f"• Led forecasting, planning, and performance analytics initiatives "
        f"supporting leadership decision-making at {company}.\n"
        "• Built KPI frameworks and automated analytics workflows to improve "
        "planning accuracy and decision turnaround."
    )

# -------------------------------------------------------
# INTERVIEW ANSWERS (MANAGER)
# -------------------------------------------------------
def interview_answers(job_title):
    return {
        "Tell me about yourself":
            "I lead decision analytics, forecasting, and planning initiatives "
            "that support leadership decisions in operations-heavy environments.",

        "Why hire you":
            "I bring ownership across forecasting, KPI frameworks, and decision support, "
            "not isolated model building.",

        "Core strengths":
            "Forecasting, scenario modeling, KPI design, and analytics automation.",

        "Role fit":
            f"This role aligns with my experience in senior analytics and decision planning."
    }

# -------------------------------------------------------
# -------------------------------------------------------
# RAPIDAPI FETCH (DEBUG VERSION)
# -------------------------------------------------------
def fetch_jobs(query, location, pages):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": st.secrets["rapidapi"]["key"],
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {
        "query": f"{query} {location}",
        "num_pages": pages
    }

    r = requests.get(url, headers=headers, params=params)

    # DEBUG OUTPUT
    st.write("Status Code:", r.status_code)
    st.write("Raw Response (first 500 chars):", r.text[:500])

    if r.status_code != 200:
        st.error("RapidAPI call failed")
        return []

    try:
        data = r.json().get("data", [])
    except Exception as e:
        st.error(f"JSON parse error: {e}")
        return []

    jobs = []
    for j in data:
        jobs.append({
            "title": j.get("job_title"),
            "company": j.get("employer_name"),
            "location": j.get("job_city") or j.get("job_country"),
            "salary_text": j.get("job_salary"),
            "description": j.get("job_description"),
            "apply_link": j.get("job_apply_link")
        })

    return jobs


# -------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------
st.sidebar.header("Manager-Only Filters")

q = st.sidebar.text_input(
    "Job keyword",
    "Senior Analytics Manager OR Analytics Manager OR Decision Analytics"
)

location = st.sidebar.text_input("Location", "India")
min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0)
pages = st.sidebar.slider("Pages", 1, 3, 1)

# -------------------------------------------------------
# FETCH JOBS
# -------------------------------------------------------
if st.sidebar.button("Fetch Jobs"):
    jobs = fetch_jobs(q, location, pages)
    filtered = []

    for job in jobs:
        role = classify_job(job["title"] + job["description"])
        if role == "reject":
            continue

        score, skill, sal, hits = compute_job_score(job)
        if sal < min_salary:
            continue

        filtered.append({
            **job,
            "score": score,
            "salary_lpa": sal
        })

    st.session_state["jobs"] = filtered
    st.success(f"{len(filtered)} senior analytics roles loaded")

# -------------------------------------------------------
# DISPLAY RESULTS
# -------------------------------------------------------
jobs = st.session_state.get("jobs", [])

if jobs:
    df = pd.DataFrame(jobs).sort_values("score", ascending=False)
    st.dataframe(df[["title","company","location","salary_lpa","score"]], use_container_width=True)

    idx = st.number_input("Select job index", 0, len(jobs)-1, 0)
    job = jobs[idx]

    st.markdown(f"## {job['title']} — {job['company']}")
    st.write(job["description"])
    st.write("Apply:", job["apply_link"])

    st.markdown("### Resume Snippet")
    st.code(generate_resume_snippet(job["company"]))

    st.markdown("### Interview Prep")
    for q,a in interview_answers(job["title"]).items():
        st.write(f"**{q}**")
        st.write(a)

st.caption("JobBot+ v2 — Senior Analytics Manager Mode")

