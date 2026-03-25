import streamlit as st
import requests
import pandas as pd
from datetime import datetime, timezone
from dateutil import parser
import re
import urllib.parse

# -------------------------------------------------------
# CONFIG
# -------------------------------------------------------
st.set_page_config(
    page_title="JobBot+ | Ops & Performance Radar",
    layout="wide"
)

# session state
if "jobs" not in st.session_state:
    st.session_state["jobs"] = pd.DataFrame()

# -------------------------------------------------------
# HEADER
# -------------------------------------------------------
st.title("JobBot+ — Operations / Performance / Analytics Radar")
st.caption("Focus: Operations + KPI + Workforce + Efficiency roles")

# -------------------------------------------------------
# HELPERS
# -------------------------------------------------------
def parse_salary_to_lpa(text):
    if not text:
        return 0.0
    s = text.lower().replace(",", "")
    m = re.search(r"(\d+(\.\d+)?)\s*(lpa|lakh)", s)
    if m:
        return float(m.group(1))
    return 0.0


def classify_job(text):
    t = (text or "").lower()

    reject = ["ml engineer", "data engineer", "deep learning", "nlp"]
    if any(k in t for k in reject):
        return False

    target = [
        "operations",
        "performance",
        "analytics",
        "supply chain",
        "control tower",
        "network"
    ]

    return any(k in t for k in target)


def compute_score(text, salary):
    signals = [
        "kpi", "performance", "operations",
        "planning", "forecasting", "efficiency",
        "cost", "process", "productivity"
    ]

    hits = sum(1 for s in signals if s in text.lower())
    skill_score = int((hits / len(signals)) * 100)

    salary_score = min(100, int((salary / 30) * 100))

    return int(0.7 * skill_score + 0.3 * salary_score)


def fetch_jobs(query, location):
    url = "https://jsearch.p.rapidapi.com/search"

    headers = {
        "X-RapidAPI-Key": st.secrets["rapidapi"]["key"],
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    params = {
        "query": f"{query} in {location}",
        "num_pages": 1
    }

    r = requests.get(url, headers=headers, params=params)

    if r.status_code != 200:
        return []

    return r.json().get("data", [])

# -------------------------------------------------------
# SIDEBAR
# -------------------------------------------------------
st.sidebar.header("Controls")

query = st.sidebar.text_input(
    "Search",
    "operations manager OR operations analytics OR performance manager OR supply chain analytics"
)

location = st.sidebar.selectbox(
    "Location",
    ["India", "Mumbai", "Bangalore", "Remote"]
)

min_salary = st.sidebar.slider("Min Salary (LPA)", 0, 50, 20)

# -------------------------------------------------------
# FETCH BUTTON
# -------------------------------------------------------
if st.sidebar.button("Fetch Jobs"):

    raw_jobs = fetch_jobs(query, location)

    results = []

    for j in raw_jobs:

        text = f"{j.get('job_title','')} {j.get('job_description','')}"

        if not classify_job(text):
            continue

        salary = parse_salary_to_lpa(j.get("job_salary"))

        if salary and salary < min_salary:
            continue

        score = compute_score(text, salary)

        results.append({
            "Title": j.get("job_title"),
            "Company": j.get("employer_name"),
            "Location": j.get("job_city"),
            "Score": score,
            "Salary": salary,
            "Apply": j.get("job_apply_link")
        })

    df = pd.DataFrame(results)

    if not df.empty:
        df = df.sort_values("Score", ascending=False)
        st.session_state["jobs"] = df
        st.success(f"{len(df)} jobs found")
    else:
        st.session_state["jobs"] = pd.DataFrame()
        st.warning("No jobs found. Try relaxing filters.")

# -------------------------------------------------------
# DISPLAY
# -------------------------------------------------------
df = st.session_state["jobs"]

if not df.empty:

    st.dataframe(df, use_container_width=True)

    idx = st.number_input("Select job", 0, len(df)-1, 0)

    row = df.iloc[idx]

    st.markdown("### Job Details")
    st.write("Title:", row["Title"])
    st.write("Company:", row["Company"])
    st.write("Score:", row["Score"])

    if row["Apply"]:
        st.markdown(f"[Apply Here]({row['Apply']})")

else:
    st.info("Click 'Fetch Jobs' to begin")
