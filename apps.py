# app.py - JobBot+ Version C (Hybrid)

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
import tldextract
from dateutil import parser as dateparser

st.set_page_config(page_title="JobBot+", layout="wide")

# ---------------------------
# LOGO + MAIN TITLE (FINAL)
# ---------------------------
def load_logo_base64():
    try:
        logo = Image.open("vt_logo.png")  # keep this file in your repo root
        buf = BytesIO()
        logo.save(buf, format="PNG")
        return base64.b64encode(buf.getvalue()).decode()
    except:
        return None

# Display centered logo
logo_b64 = load_logo_base64()
if logo_b64:
    st.markdown(
        f"""
        <div style='text-align:center; margin-top:-20px; margin-bottom:10px;'>
            <img src='data:image/png;base64,{logo_b64}' width='260'>
        </div>
        """,
        unsafe_allow_html=True
    )
else:
    st.info("Logo not found — upload vt_logo.png to project root.")

# MAIN title — your ONLY title
st.markdown(
    "<h1 style='text-align:center; margin-top:-10px;'>JobBot+ — Job Search & Application Assistant</h1>",
    unsafe_allow_html=True
)


# ---------------------------
# GOOGLE SHEETS LOADER
# ---------------------------
@st.cache_resource
def google_sheet():
    try:
        creds = json.loads(st.secrets["google"]["service_account"])
        gc = gspread.service_account_from_dict(creds)
        sheet_url = st.secrets["google"]["sheet_url"]
        sh = gc.open_by_url(sheet_url)
        return sh.sheet1
    except Exception as e:
        st.error(f"Google Sheets Error: {e}")
        return None

worksheet = google_sheet()

# ---------------------------
# UTILS
# ---------------------------
def uid():
    return uuid.uuid4().hex[:8]

def detect_emails(text):
    return list(set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or "")))

def extract_company_domain(url_or_text):
    try:
        res = tldextract.extract(url_or_text)
        if res.domain:
            return f"{res.domain}.{res.suffix}"
    except:
        pass
    return None

def parse_salary_to_lpa(salary_text):
    if not salary_text:
        return 0.0
    s = salary_text.replace(",", "").lower()

    m = re.search(r"(\d+(\.\d+)?)\s*(lpa|lakh|lakhs|lac)", s)
    if m:
        return float(m.group(1))

    m2 = re.search(r"(\d+(\.\d+)?)\s*(inr|₹)", s)
    if m2:
        v = float(m2.group(1))
        if v > 10000:
            return round(v/100000, 1)
        return v

    m3 = re.search(r"(\d+(\.\d+)?)", s)
    if m3:
        v = float(m3.group(1))
        if v > 10000:
            return v/100000
        return v

    return 0.0

USER_SKILLS = [
    "python","sql","power bi","powerbi","pandas","numpy","scikit-learn",
    "prophet","arima","streamlit","aws","gcp","etl","forecasting","nlp","shap"
]

def skill_match_score(job_text, user_skills=USER_SKILLS):
    text = (job_text or "").lower()
    hits = [s for s in user_skills if s.lower() in text]
    score = int(len(hits) / max(1, len(user_skills)) * 100)
    return min(100, score), hits

CLASS_KEYWORDS = {
    "data_scientist": ["data scientist","ml engineer","machine learning","deep learning"],
    "data_engineer": ["spark","airflow","etl","pipeline","databricks"],
    "analytics_engineer": ["analytics engineer","dbt","data modeling"],
    "data_analyst": ["power bi","tableau","excel","dashboard","analyst"],
    "ml_engineer": ["mlops","docker","kubernetes","tensorflow"],
    "nlp_engineer": ["nlp","bert","transformer","text"]
}

def classify_job(text):
    t = (text or "").lower()
    scores = {role: sum(kw in t for kw in kws) for role, kws in CLASS_KEYWORDS.items()}
    return max(scores, key=scores.get), scores

def compute_job_score(job):
    text = " ".join([str(job.get(k,"")) for k in ("title","description","company")])
    skill_score, hits = skill_match_score(text)
    salary_lpa = parse_salary_to_lpa(job.get("salary_text") or "")

    sal_score = min(100, int((salary_lpa / 30.0) * 100))

    final = int(skill_score*0.6 + sal_score*0.4)
    return final, skill_score, salary_lpa, hits

def generate_resume_snippet(job_title, company, hits):
    if hits:
        return "• Worked end-to-end with " + ", ".join(hits[:4]) + f" to improve analytics impact at {company}.\n• Built ML & forecasting workflows reducing manual effort."
    return "• Delivered analytics & ML solutions using Python, SQL and Power BI."

def mini_project_suggestion(missing_skills):
    if not missing_skills:
        return "Convert one portfolio project into a deployed Streamlit + API service."
    ms = ", ".join(missing_skills[:3])
    return f"Mini-project: Build a small ML API covering {ms}, deploy on AWS, add Streamlit UI."

def interview_answers(job_title, job_desc):
    return {
        "tell_me_about_yourself": "I build data and ML systems end-to-end…",
        "why_hire_you": "I solve operational problems using analytics and automation…",
        "technical_strengths": "Forecasting, classification, feature engineering, SHAP…",
        "company_fit": f"This role fits my background in {job_title} work…"
    }

# ---------------------------
# RAPIDAPI
# ---------------------------
RAPIDAPI_KEY = st.secrets.get("rapidapi", {}).get("key", None)

def fetch_jobs_rapidapi(query, location="India", pages=1):
    if not RAPIDAPI_KEY:
        return []

    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {"query": f"{query} in {location}", "num_pages": pages}

    try:
        r = requests.get(url, headers=headers, params=params, timeout=12)
        data = r.json().get("data", [])
        jobs = []

        for it in data:
            jobs.append({
                "title": it.get("job_title"),
                "company": it.get("employer_name"),
                "location": it.get("job_city") or it.get("job_country"),
                "salary_text": it.get("job_salary"),
                "description": it.get("job_description"),
                "apply_link": it.get("job_apply_link"),
            })
        return jobs
    except:
        return []

# ---------------------------
# WhatsApp notifier
# ---------------------------
def send_whatsapp(msg):
    tw = st.secrets.get("twilio", {})
    sid = tw.get("account_sid")
    token = tw.get("auth_token")
    from_ = tw.get("from_whatsapp")
    to_ = tw.get("to_whatsapp")

    if not sid or not token:
        return False, "Twilio missing"

    try:
        client = TwilioClient(sid, token)
        m = client.messages.create(body=msg, from_=from_, to=to_)
        return True, m.sid
    except Exception as e:
        return False, str(e)

# ---------------------------
# SHEET LOGGER
# ---------------------------
def log_to_sheet(row):
    try:
        if worksheet:
            if not worksheet.row_values(1):
                worksheet.append_row(
                    ["UID","Applied On","Job Title","Company","Location","Salary (LPA)",
                     "Role Category","Apply Link","Source","Skill Match (%)","Score",
                     "Notes","Status"]
                )
            worksheet.append_row(row)
            return True, None
        return False, "No sheet"
    except Exception as e:
        return False, str(e)


st.sidebar.header("Filters")

q = st.sidebar.text_input("Job keyword", "Data Scientist")
location = st.sidebar.text_input("Location", "India")
min_salary = st.sidebar.number_input("Min LPA", 24.0)
pages = st.sidebar.slider("Pages", 1, 3, 1)

if st.sidebar.button("Fetch Jobs"):
    jobs = fetch_jobs_rapidapi(q, location, pages)
    st.session_state["jobs_list"] = jobs
    st.success(f"{len(jobs)} jobs loaded")

jobs_list = st.session_state.get("jobs_list", [])

# ---------------------------
# RESULTS
# ---------------------------
if jobs_list:
    rows = []
    for idx, job in enumerate(jobs_list):
        score, skill_score, sal_lpa, hits = compute_job_score(job)
        cls, _ = classify_job(job.get("title","") + job.get("description",""))
        rows.append({
            "idx": idx,
            "title": job["title"],
            "company": job["company"],
            "location": job["location"],
            "salary_lpa": sal_lpa,
            "score": score,
            "skill_match": skill_score,
            "category": cls,
            "apply_link": job["apply_link"]
        })

    df = pd.DataFrame(rows)
    st.subheader("Jobs (ranked)")
    st.dataframe(df.sort_values("score", ascending=False))

    st.markdown("---")
    idx = st.number_input("Select job index", 0, len(rows)-1, 0)

    job = jobs_list[int(idx)]

    st.markdown(f"### {job['title']} — {job['company']} — {job['location']}")
    st.write(job["description"])
    st.write("Apply:", job["apply_link"])

    emails = detect_emails(job["description"])
    st.write("Emails detected:", emails)

    score, skill_score, sal_lpa, hits = compute_job_score(job)

    st.markdown("### Tailored Resume Snippet")
    st.code(generate_resume_snippet(job["title"], job["company"], hits))

    st.markdown("### Interview Answers")
    ans = interview_answers(job["title"], job["description"])
    for k,v in ans.items():
        st.write(f"**{k.replace('_',' ').title()}**")
        st.write(v)

    st.markdown("### Skill Gap")
    missing = [s for s in ["nlp","fastapi","docker","kubernetes"] if s not in hits]
    st.write("Missing:", missing)
    st.write(mini_project_suggestion(missing))

    # BUTTONS
    st.markdown("---")
    if st.button("Log to Google Sheet"):
        row = [
            uid(),
            datetime.now().isoformat(),
            job["title"],
            job["company"],
            job["location"],
            sal_lpa,
            classify_job(job["title"])[0],
            job["apply_link"],
            "RapidAPI",
            skill_score,
            score,
            ";".join(emails),
            "Logged"
        ]
        ok, err = log_to_sheet(row)
        st.success("Logged" if ok else err)

    if st.button("Send WhatsApp Alert"):
        if score >= 80:
            ok, resp = send_whatsapp(
                f"High-match job: {job['title']} at {job['company']} — Score {score}"
            )
            st.success("Sent!" if ok else resp)
        else:
            st.info("Below 80 — Not sending")

st.caption("JobBot+ v1 — Hybrid Edition.")



