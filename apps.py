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
import smtplib
from email.mime.text import MIMEText

# -------------------------------------------------------
# PAGE CONFIG
# -------------------------------------------------------
st.set_page_config(
    page_title="JobBot+ | Operations & Performance Roles Radar",
    layout="wide"
)

if "jobs" not in st.session_state:
    st.session_state["jobs"] = []

# -------------------------------------------------------
# HEADER
# -------------------------------------------------------
st.markdown(
    "<h3 style='text-align:center;'>JobBot+ — Operations / Performance / Analytics Radar</h3>",
    unsafe_allow_html=True
)

st.caption(
    "Focus: Operations + Analytics + Performance + Workforce Planning roles"
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
    return "https://www.linkedin.com/jobs/search/?keywords=" + urllib.parse.quote(f"{title} {company}")


def naukri_search_link(title, company):
    return "https://www.naukri.com/" + urllib.parse.quote(f"{title} {company}") + "-jobs"

# -------------------------------------------------------
# ROLE FILTERING
# -------------------------------------------------------
REJECT_KEYWORDS = [
    "ml engineer",
    "data engineer",
    "deep learning engineer",
    "computer vision",
    "nlp engineer"
]

MANAGER_KEYWORDS = [
    "operations analytics manager",
    "operations performance manager",
    "operational excellence manager",
    "operations manager analytics",
    "supply chain analytics",
    "network operations manager",
    "control tower",
    "operations intelligence",
    "business operations manager",
    "program manager operations",
    "operations strategy",
    "performance manager",
    "ops analytics",
]

def classify_job(text):
    t = (text or "").lower()
    if any(k in t for k in REJECT_KEYWORDS):
        return "reject"
    if any(k in t for k in MANAGER_KEYWORDS):
        return "accept"
    return "reject"

# -------------------------------------------------------
# SCORING
# -------------------------------------------------------
KEY_SIGNALS = [
    "kpi",
    "performance",
    "operations",
    "workforce",
    "planning",
    "forecasting",
    "efficiency",
    "cost optimization",
    "process improvement",
    "control tower",
    "network",
    "utilization",
    "productivity"
]

def compute_score(job):
    text = f"{job.get('title','')} {job.get('description','')}".lower()
    hits = sum(1 for s in KEY_SIGNALS if s in text)
    skill_score = int((hits / len(KEY_SIGNALS)) * 100)

    salary_lpa = parse_salary_to_lpa(job.get("salary_text"))
    salary_score = min(100, int((salary_lpa / 30) * 100))

    final = int(skill_score * 0.7 + salary_score * 0.3)
    return final, salary_lpa

# -------------------------------------------------------
# TEXT OUTPUT
# -------------------------------------------------------
def why_this_fits():
    return (
        "Strong alignment with experience in improving operational performance through KPI systems, "
        "workforce planning, and cost optimization in complex operations."
    )


def recruiter_dm(title, company):
    return (
        f"Hi, I came across the {title} role at {company}. "
        f"I’ve worked on driving operational performance through KPI systems, workforce planning, "
        f"and identifying cost leakages in large-scale operations. Would be good to connect."
    )

# -------------------------------------------------------
# EMAIL ALERT (AUTO PIPELINE BASE)
# -------------------------------------------------------
def send_email_alert(df):
    if df.empty:
        return

    top_jobs = df.head(5)[["Title", "Company", "Score"]]

    body = "\n".join(
        [f"{row.Title} | {row.Company} | Score: {row.Score}" for _, row in top_jobs.iterrows()]
    )

    msg = MIMEText(body)
    msg["Subject"] = "JobBot Alert - Top Roles"
    msg["From"] = "your_email@gmail.com"
    msg["To"] = "your_email@gmail.com"

    try:
        with smtplib.SMTP("smtp.gmail.com", 587) as server:
            server.starttls()
            server.login("your_email@gmail.com", "your_app_password")
            server.send_message(msg)
    except:
        pass

# -------------------------------------------------------
# FETCH JOBS
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

    return r.json().get("data", [])

# -------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------
st.sidebar.header("Search Controls")

query = st.sidebar.text_input(
    "Job keyword",
    "operations analytics manager OR operations performance manager OR operational excellence manager OR supply chain analytics manager OR network operations manager OR control tower operations"
)

locations = st.sidebar.multiselect(
    "Locations",
    ["India", "Mumbai", "Bengaluru", "Pune", "Hyderabad", "Remote"],
    default=["India"]
)

min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0)

# -------------------------------------------------------
# FETCH BUTTON
# -------------------------------------------------------
if st.sidebar.button("Fetch Jobs"):

    raw = fetch_jobs(query, " OR ".join(locations), 1)
    final = []

    for j in raw:

        if classify_job(j.get("job_title","") + j.get("job_description","")) == "reject":
            continue

        score, salary = compute_score(j)

        if salary > 0 and salary < min_salary:
            continue

        final.append({
            "Title": j.get("job_title"),
            "Company": j.get("employer_name"),
            "Location": j.get("job_city"),
            "Score": score,
            "Salary_LPA": salary,
            "Why_Fit": why_this_fits(),
            "DM": recruiter_dm(j.get("job_title"), j.get("employer_name")),
            "Apply": j.get("job_apply_link")
        })

    df = pd.DataFrame(final).sort_values("Score", ascending=False)

    st.session_state["jobs"] = df

    st.success(f"{len(df)} relevant roles found")

    # 🔥 AUTO EMAIL ALERT
    send_email_alert(df)

# -------------------------------------------------------
# DISPLAY
# -------------------------------------------------------
df = st.session_state.get("jobs")

if isinstance(df, pd.DataFrame) and not df.empty:

    st.dataframe(df[["Title","Company","Location","Score","Salary_LPA"]])

    idx = st.number_input("Select job", 0, len(df)-1, 0)

    row = df.iloc[idx]

    st.write("### Details")
    st.write(row["Why_Fit"])
    st.code(row["DM"])

    if row["Apply"]:
        st.markdown(f"[Apply Here]({row['Apply']})")

else:
    st.info("No jobs yet. Click Fetch Jobs.")
    
