### ————————————————————————————————————————————
### JOBBOT+ FULL PATCHED EDITION (VIKRANT)
### ————————————————————————————————————————————

import streamlit as st
import pandas as pd
import requests, json, time, hashlib, re
from datetime import datetime
from bs4 import BeautifulSoup
from io import BytesIO, StringIO
from PIL import Image
import base64
import gspread
import plotly.express as px

### ————————————————————————————————————————————
### SECTION 1 — CONFIG
### ————————————————————————————————————————————

st.set_page_config(page_title="JobBot", layout="wide")

def load_logo_base64():
    try:
        logo = Image.open("vt_logo.png")
        buf = BytesIO()
        logo.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

RAPIDAPI_KEY = st.secrets.get("rapidapi", {}).get("key", "")

@st.cache_resource
def google_sheet():
    try:
        creds = json.loads(st.secrets["google"]["service_account"])
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_url(st.secrets["google"]["sheet_url"])
        return sh.sheet1
    except Exception as e:
        st.error(f"Google Sheets Error: {e}")
        return None


### ————————————————————————————————————————————
### SECTION 2 — FETCH JOBS
### ————————————————————————————————————————————

HEADERS = {"User-Agent": "Mozilla/5.0 (JobBot/1.0)"}

def fetch_jobs_rapidapi(query, pages=1):
    out = []
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }

    for _ in range(pages):
        try:
            resp = requests.get(url, headers=headers, params={"query": query, "num_pages": "1"}, timeout=10)
            data = resp.json().get("data", [])
        except:
            continue

        for job in data:
            out.append({
                "title": job.get("job_title"),
                "company": job.get("employer_name"),
                "location": job.get("job_city") or job.get("job_country"),
                "salary_max": job.get("job_salary_max") or 0,
                "currency": job.get("job_salary_currency") or "",
                "date_posted": job.get("job_posted_at_datetime_utc") or "",
                "apply_link": job.get("job_apply_link"),
                "source": "RapidAPI"
            })
    return out


def fetch_jobs_indeed(query, location, pages=1):
    results = []
    for p in range(pages):
        try:
            url = f"https://www.indeed.co.in/jobs?q={query}&l={location}&start={p*10}"
            r = requests.get(url, headers=HEADERS, timeout=10)
            soup = BeautifulSoup(r.text, "html.parser")
        except:
            continue

        cards = soup.select("a.tapItem")
        for c in cards:
            title = c.select_one("h2")
            company = c.select_one(".companyName")
            loc = c.select_one(".companyLocation")

            results.append({
                "title": title.get_text(strip=True) if title else None,
                "company": company.get_text(strip=True) if company else None,
                "location": loc.get_text(strip=True) if loc else None,
                "salary_max": 0,
                "currency": "",
                "date_posted": "",
                "apply_link": "https://www.indeed.co.in" + c.get("href", ""),
                "source": "Indeed"
            })
    return results


def aggregate_jobs(query, location, pages, use_indeed):
    jobs = fetch_jobs_rapidapi(f"{query} in {location}", pages)
    if use_indeed:
        jobs += fetch_jobs_indeed(query, location, pages)
    return jobs


### ————————————————————————————————————————————
### SECTION 3 — SCORING
### ————————————————————————————————————————————

def normalize(s): return (s or "").lower().strip()

def title_score(title, target_titles):
    t = normalize(title)
    for target in target_titles:
        if target.lower() in t:
            return 30
    if any(x in t for x in ["data scientist","ml","ai","analytics"]):
        return 20
    return 0

def skills_score(text, skills):
    text = normalize(text)
    per = 30 / len(skills)
    score = sum(per for s in skills if s.lower() in text)
    return min(30, score)

def salary_score(s, min_salary):
    try:
        s = float(s)
    except:
        s = 0
    if s >= min_salary: return 15
    if s == 0: return 7.5
    return max(0, 15 * (s / min_salary))

def location_score(loc, prefs):
    l = normalize(loc)
    for p in prefs:
        if p.lower() in l:
            return 10
    if "remote" in l:
        return 8
    return 0

def recency_score(dt):
    if not dt: return 5
    try:
        posted = datetime.fromisoformat(dt.replace("Z",""))
        days = (datetime.utcnow() - posted).days
        if days <= 3: return 10
        if days <= 7: return 7
        if days <= 30: return 4
        return 1
    except:
        return 5


### ————————————————————————————————————————————
### PATCHED compute_score (NO CRASHES)
### ————————————————————————————————————————————

def compute_score(job, skills, target_titles, min_salary, prefs):
    try:
        if not job:
            return 0.0

        # support dict/Series/other
        def safe_get(obj, key, default=""):
            try:
                if hasattr(obj, "get"):
                    v = obj.get(key, default)
                elif isinstance(obj, dict):
                    v = obj[key] if key in obj else default
                else:
                    return default
                return v if v is not None else default
            except:
                return default

        title = str(safe_get(job, "title", ""))
        company = str(safe_get(job, "company", ""))
        location = str(safe_get(job, "location", ""))
        salary = safe_get(job, "salary_max", 0)
        date_posted = safe_get(job, "date_posted", "")

        combo = f"{title} {company} {location}"

        score = 0
        score += title_score(title, target_titles)
        score += skills_score(combo, skills)
        score += salary_score(salary, min_salary)
        score += location_score(location, prefs)
        score += recency_score(date_posted)

        return round(min(score, 100), 1)

    except:
        return 0.0


### ————————————————————————————————————————————
### SECTION 4 — IMPACT RANK
### ————————————————————————————————————————————

IMPACT_KEYWORDS = {
    "ml": ["machine learning","ml","deep learning","pytorch","tensorflow","llm","transformer","mlops"],
    "ds": ["data science","analysis","forecast","classification","regression","feature engineering","modeling"],
    "ai": ["llm","gpt","nlp","gen ai","computer vision","transformer"],
    "eng": ["data engineer","analytics engineer","etl","pipeline","dbt","airflow","spark","sql"]
}

def impact_rank(text):
    t = normalize(text)
    scores = {k:0 for k in IMPACT_KEYWORDS}
    for area, keys in IMPACT_KEYWORDS.items():
        for kw in keys:
            if kw in t:
                scores[area]+=1
    total = sum(scores.values()) or 1
    for k in scores:
        scores[k] = round(100*scores[k]/total,1)
    primary = max(scores, key=lambda x: scores[x])
    return primary, scores


### ————————————————————————————————————————————
### SECTION 5 — RECRUITER EMAIL DETECTOR
### ————————————————————————————————————————————

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

def detect_emails_from_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code != 200:
            return []
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ")
        return list(set(EMAIL_RE.findall(text)))
    except:
        return []


### ————————————————————————————————————————————
### SECTION 6 — RESUME SNIPPETS
### ————————————————————————————————————————————

def generate_snippets(jt):
    t = normalize(jt)
    techs = [k for k in ["python","sql","power bi","aws","nlp","scikit-learn","streamlit"] if k in t]
    techs = ", ".join(techs[:4]) or "Python, SQL"

    return [
        f"Built ML pipelines using {techs}, improving planning accuracy by 20-25%.",
        f"Developed forecasting and classification models to enhance operational decision-making.",
        f"Delivered end-to-end automation using Streamlit/AWS to reduce manual reporting."
    ]


### ————————————————————————————————————————————
### SECTION 7 — MINI PROJECT SUGGESTIONS
### ————————————————————————————————————————————

PROJECTS = {
    "forecast": "Time-Series Forecasting Engine with ARIMA/Prophet",
    "nlp": "Customer Feedback NLP + Sentiment Classifier",
    "mlops": "Dockerized ML Model + CI Pipeline"
}

def suggest_projects(text):
    t = normalize(text)
    out = [v for k,v in PROJECTS.items() if k in t]
    if not out:
        out = ["Time-Series Forecasting Engine", "NLP Sentiment Classifier"]
    return out


### ————————————————————————————————————————————
### SECTION 8 — INTERVIEW ANSWERS
### ————————————————————————————————————————————

def interview_tell():
    return "I’m Vikrant, an Applied Data Scientist & Analytics Engineer working across Python, SQL, ML pipelines and forecasting."

def interview_exp():
    return "My predictive maintenance model used engineered features + ROC-AUC selection and deployed via Streamlit."

def interview_hire():
    return "Hire me because I deliver end-to-end DS/ML systems that directly reduce manual effort and improve planning."


### ————————————————————————————————————————————
### SECTION 9 — UI
### ————————————————————————————————————————————

logo = load_logo_base64()
if logo:
    st.markdown(f"<div style='text-align:center'><img src='data:image/png;base64,{logo}' width='250'></div>", unsafe_allow_html=True)

st.title("JobBot (Data Scientist & Analytics)")


### OPTIONS
st.sidebar.header("Filters")
keywords = st.sidebar.text_input("Job Title", "Applied Data Scientist")
location = st.sidebar.text_input("Location", "Mumbai, Pune, Remote")
pages = st.sidebar.slider("Pages to search", 1, 5, 1)
min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0)
min_inr = int(min_salary * 100000)

use_indeed = st.sidebar.checkbox("Include Indeed", False)

skills_list = ["python","sql","power bi","forecasting","nlp","streamlit"]
target_titles = ["Data Scientist", "Applied Data Scientist", "ML Engineer", "Analytics Engineer"]
prefs = [x.strip() for x in location.split(",")]


### FETCH BUTTON
if st.sidebar.button("Fetch Jobs"):
    jobs = aggregate_jobs(keywords, location, pages, use_indeed)

    cleaned = []
    for j in jobs:
        if not j:
            continue
        job = dict(j) if isinstance(j, dict) else j

        job["job_id"] = hashlib.md5((str(job.get("title","")) + str(job.get("company",""))).encode()).hexdigest()[:8]
        combo = f"{job.get('title','')} {job.get('company','')} {job.get('location','')}"
        job["score"] = compute_score(job, skills_list, target_titles, min_inr, prefs)
        job["impact_primary"], job["impact_scores"] = impact_rank(combo)

        cleaned.append(job)

    if cleaned:
        df = pd.DataFrame(cleaned).sort_values("score", ascending=False)
        st.session_state["jobs"] = df
        st.success(f"Found {len(df)} jobs.")
    else:
        st.error("No jobs found.")


### DISPLAY JOBS
df = st.session_state.get("jobs")
if df is not None and not df.empty:
    st.subheader("Top Matches")
    st.dataframe(df.head(50), height=350)

    for _, row in df.head(20).iterrows():
        st.markdown(f"## {row['title']} — {row['company']}")
        st.write(f"Score: {row['score']} | Impact: {row['impact_primary']}")
        st.write(f"Location: {row['location']} | Salary: {row['salary_max']}")
        st.write(f"[Apply Link]({row['apply_link']})")

        c1, c2, c3, c4, c5 = st.columns(5)

        if c1.button("Emails", key=f"em{row['job_id']}"):
            st.write(detect_emails_from_url(row["apply_link"]))

        if c2.button("Snippets", key=f"sn{row['job_id']}"):
            st.write(generate_snippets(row["title"]))

        if c3.button("Projects", key=f"pj{row['job_id']}"):
            st.write(suggest_projects(row["title"]))

        if c4.button("Interview", key=f"in{row['job_id']}"):
            st.write(interview_tell())
            st.write(interview_exp())
            st.write(interview_hire())

        if c5.button("Log", key=f"gs{row['job_id']}"):
            sh = google_sheet()
            if sh:
                sh.append_row([
                    row["job_id"],
                    datetime.utcnow().isoformat(),
                    row["title"],
                    row["company"],
                    row["location"],
                    row["score"],
                    row["impact_primary"],
                    row["apply_link"]
                ])
                st.success("Saved to Google Sheet")
            else:
                st.error("Google Sheet not configured.")

        st.markdown("---")


### FOOTER
st.markdown("<hr><center>JobBot+ Full Edition — Built for Vikrant</center>", unsafe_allow_html=True)


