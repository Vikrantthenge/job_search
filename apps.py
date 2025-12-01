### ————————————————————————————————————————————
### JOBBOT+ FULL EDITION — SINGLE FILE (VIKRANT)
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
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

### ————————————————————————————————————————————
### SECTION 1 — CONFIG AND HELPERS
### ————————————————————————————————————————————

st.set_page_config(page_title="JobBot+ — Vikrant", layout="wide")

def load_logo_base64(path="vt_logo.png"):
    try:
        logo = Image.open(path)
        buf = BytesIO()
        logo.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

RAPIDAPI_KEY = st.secrets.get("rapidapi", {}).get("key", "")
SMTP_USER = st.secrets.get("smtp", {}).get("user", "")
SMTP_PASS = st.secrets.get("smtp", {}).get("pass", "")

@st.cache_resource
def google_sheet():
    try:
        creds = json.loads(st.secrets["google"]["service_account"])
        gc = gspread.service_account_from_dict(creds)
        sh = gc.open_by_url(st.secrets["google"]["sheet_url"])
        return sh.sheet1
    except:
        return None


### ————————————————————————————————————————————
### SECTION 2 — FETCH JOBS (RapidAPI + Optional Indeed)
### ————————————————————————————————————————————

HEADERS = {"User-Agent": "Mozilla/5.0 (JobBot/1.0)"}

def fetch_jobs_rapidapi(query, pages=1):
    url = "https://jsearch.p.rapidapi.com/search"
    out = []
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    for i in range(pages):
        params = {"query": query, "num_pages": "1"}
        resp = requests.get(url, headers=headers, params=params, timeout=12)
        if resp.status_code != 200:
            continue
        data = resp.json().get("data", [])
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
        url = f"https://www.indeed.co.in/jobs?q={query}&l={location}&start={p*10}"
        r = requests.get(url, headers=HEADERS)
        if r.status_code != 200:
            break
        soup = BeautifulSoup(r.text, "html.parser")
        cards = soup.select("a.tapItem")
        for c in cards:
            title = c.select_one("h2")
            title = title.get_text(strip=True) if title else None
            company = c.select_one(".companyName")
            company = company.get_text(strip=True) if company else None
            loc = c.select_one(".companyLocation")
            loc = loc.get_text(strip=True) if loc else None
            link = "https://www.indeed.co.in" + c.get("href", "")
            results.append({
                "title": title,
                "company": company,
                "location": loc,
                "salary_max": 0,
                "currency": "",
                "date_posted": "",
                "apply_link": link,
                "source": "Indeed"
            })
    return results

def aggregate_jobs(query, location, pages=1, use_indeed=False):
    out = fetch_jobs_rapidapi(f"{query} in {location}", pages)
    if use_indeed:
        out += fetch_jobs_indeed(query, location, pages)
    return out


### ————————————————————————————————————————————
### SECTION 3 — SCORING & IMPACT RANKING
### ————————————————————————————————————————————

def normalize(s): return (s or "").lower()

def title_score(title, target_titles):
    t = normalize(title)
    for target in target_titles:
        if target.lower() in t:
            return 30
    if any(x in t for x in ["data scientist","ml engineer","ai","analytics"]):
        return 20
    return 0

def skills_score(text, skills):
    text = normalize(text)
    per = 30/len(skills)
    score = sum(per for s in skills if s.lower() in text)
    return min(30, score)

def salary_score(s, min_salary):
    if s >= min_salary:
        return 15
    if s == 0:
        return 7.5
    return max(0, 15*(s/min_salary))

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
        days = (datetime.utcnow()-posted).days
        if days<=3: return 10
        if days<=7: return 7
        if days<=30: return 4
        return 1
    except:
        return 5

def compute_score(job, skills, target_titles, min_salary, prefs):
    """
    Defensive scoring function: accepts dict-like or pandas Series or None.
    Returns 0 if job is invalid. Otherwise computes same weighted score.
    """
    try:
        if not job:
            return 0.0

        # Support dicts and pandas Series (both have .get). For numpy/other types, coerce safely.
        # Use .get where possible but fallback to indexing or attribute access.
        def safe_get(obj, key, default=""):
            try:
                # dict-like
                if hasattr(obj, "get"):
                    val = obj.get(key, default)
                else:
                    # try dictionary-style indexing
                    val = obj[key] if key in obj else default
                # coerce None to default and ensure string where needed
                return val if val is not None else default
            except Exception:
                return default

        title = str(safe_get(job, "title", "") or "")
        company = str(safe_get(job, "company", "") or "")
        location = str(safe_get(job, "location", "") or "")
        salary_val = safe_get(job, "salary_max", 0) or 0
        date_posted = safe_get(job, "date_posted", "")

        combo = " ".join([title, company, location])

        s = 0.0
        s += title_score(title, target_titles)
        s += skills_score(combo, skills)
        try:
            # ensure salary_val is numeric
            salary_num = float(salary_val)
        except Exception:
            salary_num = 0.0
        s += salary_score(salary_num, min_salary)
        s += location_score(location, prefs)
        s += recency_score(date_posted)
        return round(min(100.0, s), 1)
    except Exception:
        # In case of any unexpected error, return 0 to avoid app crash.
        return 0.0


IMPACT_KEYWORDS = {
    "ml": ["ml","machine learning","model","deep learning","pytorch","tensorflow","llm","bert","transformer","mlops"],
    "ds": ["data scientist","analysis","forecast","arima","prophet","classification","regression","feature engineering"],
    "ai": ["llm","gpt","transformer","deep learning","cv","nlp","gen ai"],
    "eng": ["analytics engineer","data engineer","etl","pipeline","dbt","airflow","spark","databricks","sql"]
}

def impact_rank(text):
    t = normalize(text)
    scores = {"ml":0,"ds":0,"ai":0,"eng":0}
    for area, keys in IMPACT_KEYWORDS.items():
        for k in keys:
            if k in t:
                scores[area]+=1
    total = sum(scores.values()) or 1
    for a in scores:
        scores[a] = round(100*scores[a]/total,1)
    primary = max(scores, key=lambda x:scores[x])
    return primary, scores


### ————————————————————————————————————————————
### SECTION 4 — RECRUITER EMAIL DETECTOR
### ————————————————————————————————————————————

EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")

def detect_emails_from_url(url):
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code!=200: return []
        soup = BeautifulSoup(r.text, "html.parser")
        text = soup.get_text(" ")
        emails = set(EMAIL_RE.findall(text))
        return list(emails)
    except:
        return []


### ————————————————————————————————————————————
### SECTION 5 — RESUME SNIPPET GENERATOR
### ————————————————————————————————————————————

def generate_snippets(job_text):
    text = normalize(job_text)
    techs = [k for k in ["python","sql","power bi","streamlit","aws","prophet","arima","nlp","scikit-learn"] if k in text][:4]
    probs = [k for k in ["forecast","maintenance","classification","nlp","sentiment","staffing","optimization","delay"] if k in text]

    techs = ", ".join(techs) or "Python, SQL"
    prob = probs[0] if probs else "operational inefficiencies"

    return [
        f"Built end-to-end {prob} pipelines using {techs}, improving planning accuracy by 20-25%.",
        f"Developed forecasting models and deployed them via Streamlit/AWS to reduce manual workload.",
        f"Applied feature engineering + SHAP explainability to highlight key drivers for business decisions."
    ]


### ————————————————————————————————————————————
### SECTION 6 — SKILL-GAP MINI-PROJECT SUGGESTIONS
### ————————————————————————————————————————————

PROJECTS = {
    "forecast": "Time-Series Forecasting Engine (Prophet/ARIMA + Power BI)",
    "nlp": "Sentiment Analysis Pipeline (TF-IDF + Logistic Regression + Streamlit)",
    "mlops": "Dockerized ML Model with CI Tests + Streamlit Deployment",
}

def suggest_projects(job_text):
    t = normalize(job_text)
    out = []
    for k,v in PROJECTS.items():
        if k in t:
            out.append(v)
    if not out:
        out = [
            PROJECTS["forecast"],
            PROJECTS["nlp"]
        ]
    return out


### ————————————————————————————————————————————
### SECTION 7 — INTERVIEW ANSWER GENERATOR
### ————————————————————————————————————————————

def interview_tell_me_about():
    return (
        "I’m Vikrant, an Applied Data Scientist & Analytics Engineer. I work across Python, SQL, "
        "ML pipelines, forecasting models and automation. Recently I built a forecasting engine that "
        "reduced manual scheduling and improved planning accuracy by 20-25%. I enjoy end-to-end delivery "
        "from data cleaning to deployment, and I’m available immediately."
    )

def interview_project_explain():
    return (
        "In my predictive maintenance project, the challenge was identifying early signs of failure. "
        "I gathered historical logs, engineered features, tested multiple models, and selected the best "
        "classifier using ROC-AUC. I deployed the model with Streamlit, enabling real-time insights. "
        "The model supported proactive planning and reduced operational risk."
    )

def interview_why_hire():
    return (
        "You should hire me because I deliver practical ML systems that improve forecasting, automate "
        "manual workflows, and directly support business decisions. My background blends analytics, "
        "modeling, and deployment — so I don’t stop at analysis; I deliver usable tools."
    )


### ————————————————————————————————————————————
### SECTION 8 — WHATSAPP ALERTS (TWILIO)
### ————————————————————————————————————————————

def send_whatsapp_alert(body):
    # OPTIONAL — only if Twilio secrets added
    sid = st.secrets.get("twilio",{}).get("sid","")
    tok = st.secrets.get("twilio",{}).get("token","")
    from_no = st.secrets.get("twilio",{}).get("from_whatsapp","")
    to_no = st.secrets.get("twilio",{}).get("to_whatsapp","")

    if not sid or not tok or not from_no or not to_no:
        return "Twilio not configured."

    try:
        from twilio.rest import Client
        client = Client(sid, tok)
        msg = client.messages.create(body=body, from_=f"whatsapp:{from_no}", to=f"whatsapp:{to_no}")
        return f"WhatsApp sent: {msg.sid}"
    except Exception as e:
        return f"Failed: {e}"


### ————————————————————————————————————————————
### SECTION 9 — UI START
### ————————————————————————————————————————————

logo = load_logo_base64()
if logo:
    st.markdown(f"<div style='text-align:center'><img src='data:image/png;base64,{logo}' width='280'></div>", unsafe_allow_html=True)

st.title("JobBot+ — Applied Data Scientist & Analytics Engineer (Vikrant)")


### ————————————————————————————————————————————
### JOB SEARCH PANEL
### ————————————————————————————————————————————

st.sidebar.header("Search Filters")
keywords = st.sidebar.text_input("Job Title", "Applied Data Scientist")
location = st.sidebar.text_input("Location", "Mumbai, Pune, Remote")
pages = st.sidebar.slider("Pages", 1, 5, 1)
min_salary = st.sidebar.number_input("Min Salary (LPA)", 24.0, step=0.5)
min_inr = int(min_salary * 100000)

use_indeed = st.sidebar.checkbox("Include Indeed", False)

skills_list = ["python","sql","power bi","forecasting","nlp","streamlit"]
target_titles = ["Data Scientist","Applied Data Scientist","ML Engineer","Analytics Engineer"]
prefs = [loc.strip() for loc in location.split(",")]


### ————————————————————————————————————————————
### FETCH BUTTON
### ————————————————————————————————————————————

if st.sidebar.button("Fetch Jobs"):
    with st.spinner("Fetching jobs…"):
        raw = aggregate_jobs(keywords, location, pages, use_indeed)
        for j in raw:
            j["job_id"] = hashlib.md5((j.get("title","")+j.get("company","")).encode()).hexdigest()[:8]
            text = " ".join([j["title"] or "", j["company"] or "", j["location"] or ""])
            j["score"] = compute_score(j, skills_list, target_titles, min_inr, prefs)
            j["impact_primary"], j["impact_scores"] = impact_rank(text)
        df = pd.DataFrame(raw)
        df = df.sort_values("score", ascending=False)
        st.session_state["jobs"] = df
    st.success(f"Found {len(df)} jobs.")


### ————————————————————————————————————————————
### JOB RESULTS
### ————————————————————————————————————————————

df = st.session_state.get("jobs")
if df is not None and not df.empty:
    st.subheader("Matched Jobs (Sorted by Score)")
    show = df.copy()
    show["salary_display"] = show["salary_max"].apply(lambda x: f"₹{int(x):,}" if x>0 else "Not disclosed")
    st.dataframe(show[["score","impact_primary","title","company","location","salary_display","apply_link","source"]].head(50))

    # Loop through top 20 jobs
    for idx, row in show.head(20).iterrows():
        st.markdown(f"## {row['title']} — *{row['company']}*")
        st.markdown(f"Score: **{row['score']}** | Impact: **{row['impact_primary']}**")
        st.markdown(f"Location: {row['location']} | Salary: {row['salary_display']} | Source: {row['source']}")
        st.markdown(f"[Open Apply Page]({row['apply_link']})")

        c1, c2, c3, c4, c5 = st.columns(5)

        if c1.button("Recruiter Emails", key=f"emails_{row['job_id']}"):
            emails = detect_emails_from_url(row["apply_link"])
            st.write("Emails found:", emails if emails else "No emails detected.")

        if c2.button("Resume Snippets", key=f"snip_{row['job_id']}"):
            snips = generate_snippets(row["title"] + " " + row["company"])
            st.text_area("Snippets", "\n".join(snips), height=140)

        if c3.button("Skill Gap Projects", key=f"proj_{row['job_id']}"):
            pro = suggest_projects(row["title"] + " " + row["company"])
            st.write(pro)

        if c4.button("Interview Answers", key=f"int_{row['job_id']}"):
            st.write("Tell me about yourself:", interview_tell_me_about())
            st.write("Explain a project:", interview_project_explain())
            st.write("Why hire you:", interview_why_hire())

        if c5.button("Log to Sheet", key=f"log_{row['job_id']}"):
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
                    row["apply_link"],
                    "Logged"
                ])
                st.success("Logged to Google Sheet")
            else:
                st.error("Google Sheet not configured.")

        # WhatsApp alert if score >= 80
        if row["score"] >= 80:
            msg = f"High-match job: {row['title']} at {row['company']} (Score: {row['score']})"
            out = send_whatsapp_alert(msg)
            st.info(out)

        st.markdown("---")


### ————————————————————————————————————————————
### FOOTER
### ————————————————————————————————————————————

st.markdown("""
<br><hr>
<div style='text-align:center'>
Built for <b>Vikrant</b> — JobBot+ Full Edition.<br>
Search • Score • Impact Rank • Snippets • Skill Gap • Interview Coaching • WhatsApp Alerts • Recruiter Email Detection
</div>
""", unsafe_allow_html=True)

