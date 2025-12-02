# app.py - JobBot+ Version C (Hybrid)
import streamlit as st
import json
import gspread
import requests
import pandas as pd
from datetime import datetime
import re
import uuid
from twilio.rest import Client as TwilioClient
import tldextract
from dateutil import parser as dateparser

st.set_page_config(page_title="JobBot+ — Vikrant", layout="wide")

# ---------------------------
# Google Sheets helper
# ---------------------------
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

worksheet = google_sheet()

# ---------------------------
# Utility functions
# ---------------------------
def uid():
    return uuid.uuid4().hex[:8]

def detect_emails(text):
    # simple robust regex: returns unique emails
    emails = set(re.findall(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", text or ""))
    return list(emails)

def extract_company_domain(url_or_text):
    try:
        res = tldextract.extract(url_or_text)
        if res.domain:
            return f"{res.domain}.{res.suffix}"
    except:
        pass
    return None

def parse_salary_to_lpa(salary_text):
    # Very simple parsers - extend as needed
    if not salary_text: return 0.0
    s = salary_text.replace(",", "").lower()
    # handle yearly INR like "24 LPA" or "24 lakhs"
    m = re.search(r"(\d+(\.\d+)?)\s*(lakh|lpa|lakhs|lacs|lac|l)\b", s)
    if m:
        return float(m.group(1))
    m2 = re.search(r"(\d+(\.\d+)?)\s*(inr|₹)\s*", s)
    if m2:
        # assume absolute rupee, convert to LPA if large
        v = float(m2.group(1))
        if v > 10000:
            return round(v/100000, 1)
        return v
    # fallback: numbers present
    m3 = re.search(r"(\d+(\.\d+)?)", s)
    if m3:
        val = float(m3.group(1))
        if val > 1000: return round(val/100000, 1)
        return val
    return 0.0

# Simple skill list you have (edit this list)
USER_SKILLS = [
    "python","sql","power bi","powerbi","pandas","numpy","scikit-learn",
    "prophet","arima","streamlit","aws","gcp","etl","forecasting","nlp","shap"
]

def skill_match_score(job_text, user_skills=USER_SKILLS):
    text = (job_text or "").lower()
    hits = [s for s in user_skills if s.lower() in text]
    score = min(100, int(len(hits)/max(1,len(user_skills))*100))
    return score, hits

# Job classification keywords (simple)
CLASS_KEYWORDS = {
    "data_scientist": ["data scientist","ml engineer","machine learning","deep learning","model","classification","regression","neural network"],
    "data_engineer": ["spark","airflow","etl","pipeline","databricks","data engineering"],
    "analytics_engineer": ["analytics engineer","dbt","data modeling","star schema","dimensional"],
    "data_analyst": ["power bi","tableau","excel","dashboard","visualization","analyst"],
    "ml_engineer": ["mlops","model deployment","docker","kubernetes","fastapi","tensorflow","pytorch"],
    "nlp_engineer": ["nlp","natural language","bert","transformer","text classification"]
}

def classify_job(text):
    t = (text or "").lower()
    scores = {}
    for k, kws in CLASS_KEYWORDS.items():
        s = sum(1 for kw in kws if kw in t)
        scores[k] = s
    # choose top
    best = max(scores, key=lambda k: scores[k])
    return best, scores

def compute_job_score(job, user_skills=USER_SKILLS, salary_weight=0.4, skill_weight=0.6):
    # job: dict with title, description, salary_text
    text = " ".join([str(job.get(k,"")) for k in ("title","description","company")])
    skill_score, hits = skill_match_score(text, user_skills)
    salary_lpa = parse_salary_to_lpa(job.get("salary_text") or job.get("salary") or "")
    # normalize salary to 0-100 where 24 LPA = threshold
    sal_score = min(100, int((salary_lpa / 30.0) * 100))
    final = int(skill_score*skill_weight + sal_score*salary_weight)
    return final, skill_score, salary_lpa, hits

def generate_resume_snippet(job_title, company, hits):
    # short, recruiter-facing bullet
    bullets = []
    if hits:
        top = ", ".join(hits[:4])
        bullets.append(f"Spearheaded data & ML workflows leveraging {top} to deliver actionable forecasting and performance dashboards for operations.")
    else:
        bullets.append(f"Delivered end-to-end analytics solutions (Python, SQL, Power BI) to improve operational decision making.")
    bullets.append(f"Built productionized models and dashboards to support planning & reduce manual effort at scale.")
    return "\n".join(["• " + b for b in bullets])

def mini_project_suggestion(missing_skills):
    # simple heuristics: suggest one compact project
    if not missing_skills:
        return "Your skill set matches well. Suggested mini-project: Convert one of your portfolio projects to a deployed Streamlit app with CI and hosted inference."
    ms = ", ".join(missing_skills[:3])
    return (f"Mini-project: Build an end-to-end project that covers {ms}. Example: Build a text-classification API (FastAPI) trained with an LSTM/BERT model, "
            "host model on a small VM, add a Streamlit demo and CI. Deliverables: README, deployed demo, repo + short writeup.")

def interview_answers(job_title, job_desc):
    # simple template generator
    ans = {}
    ans["tell_me_about_yourself"] = (f"I am a data and analytics professional who builds end-to-end solutions — from data pipelines to forecasting and ML models — "
                                    f"using Python, SQL and Power BI. Recently I delivered forecasting and predictive maintenance projects that improved decision-making and reduced manual work.")
    ans["why_hire_you"] = ("I bridge domain operations and analytics: I translate operational problems into data solutions, deliver deployable models and dashboards, "
                          "and communicate impact to stakeholders.")
    ans["technical_strengths"] = ("I focus on forecasting, classification, feature engineering, and model explainability (SHAP). I also deploy models via Streamlit/AWS.")
    ans["company_fit"] = (f"I am excited about the role of {job_title} because my experience driving forecasting and automation aligns with the responsibilities described.")
    return ans

# ---------------------------
# RapidAPI job fetch (jsearch) - small wrapper
# ---------------------------
RAPIDAPI_KEY = st.secrets.get("rapidapi", {}).get("key", None)

def fetch_jobs_rapidapi(query, location="India", pages=1):
    if not RAPIDAPI_KEY:
        st.warning("RapidAPI key missing in secrets; simulated results will be used.")
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
                "salary": it.get("job_salary"),
                "salary_text": it.get("job_salary"),
                "description": it.get("job_description"),
                "apply_link": it.get("job_apply_link") or it.get("job_link"),
                "source": it.get("job_highlights", {}).get("skills", "")
            })
        return jobs
    except Exception as e:
        st.error(f"Job API error: {e}")
        return []

# ---------------------------
# Twilio WhatsApp notifier
# ---------------------------
def send_whatsapp(msg):
    tw = st.secrets.get("twilio", {})
    sid = tw.get("account_sid"); token = tw.get("auth_token")
    from_ = tw.get("from_whatsapp"); to_ = tw.get("to_whatsapp")
    if not sid or not token or not from_ or not to_:
        st.info("Twilio creds missing — cannot send WhatsApp.")
        return False, "Twilio not configured"
    try:
        client = TwilioClient(sid, token)
        message = client.messages.create(body=msg, from_=from_, to=to_)
        return True, message.sid
    except Exception as e:
        return False, str(e)

# ---------------------------
# Google Sheet logging
# ---------------------------
def log_to_sheet(row):
    try:
        if worksheet:
            # ensure header exists - create if empty
            header = worksheet.row_values(1)
            if not header:
                headers = ["UID","Applied On","Job Title","Company","Location","Salary (LPA)","Role Category","Apply Link","Source","Skill Match (%)","Score","Notes","Status"]
                worksheet.append_row(headers)
            worksheet.append_row(row)
            return True, None
        return False, "Worksheet not available"
    except Exception as e:
        return False, str(e)

# ---------------------------
# Streamlit UI
# ---------------------------
st.title("JobBot+ — Job Search & Application Assistant")
st.sidebar.header("JobBot Controls")

with st.sidebar.expander("Search & Filters", expanded=True):
    q = st.text_input("Job keyword", value="Data Scientist")
    location = st.text_input("Location (city or Remote)", value="India")
    min_salary = st.number_input("Min Salary (LPA)", value=24.0, step=0.5)
    pages = st.slider("Pages to fetch", 1, 3, 1)
    auto_whatsapp = st.checkbox("Enable WhatsApp alerts for high-match jobs", value=False)

st.sidebar.header("Profile")
uploaded_resume = st.file_uploader("Upload your Resume (PDF or TXT)", type=["pdf","txt"], key="resume_u")
user_skills_input = st.text_area("Your key skills (comma separated) — used for matching", value="Python, SQL, Power BI, Forecasting, ML, Streamlit")
if user_skills_input:
    USER_SKILLS = [s.strip().lower() for s in user_skills_input.split(",") if s.strip()]

st.sidebar.markdown("---")
if st.sidebar.button("Fetch Jobs"):
    with st.spinner("Fetching jobs..."):
        jobs = fetch_jobs_rapidapi(q, location, pages)
        if not jobs:
            st.warning("No jobs fetched — check RapidAPI key or network. Using simulated results.")
            # simulated example
            jobs = [
                {"title":"Data Scientist","company":"ZS Associates","location":"Mumbai","salary":"31.5 LPA","description":"Forecasting, Python, SQL, Prophet","apply_link":"https://remotefront.com"},
                {"title":"Decision Scientist","company":"Federal Express","location":"Mumbai","salary":"27.5 LPA","description":"ML, Python, feature engineering","apply_link":"https://fedex.example"}
            ]
        st.session_state["jobs_list"] = jobs
        st.success(f"{len(jobs)} jobs loaded")

jobs_list = st.session_state.get("jobs_list", [])

# Display job table with scoring
if jobs_list:
    df_rows = []
    for idx, job in enumerate(jobs_list):
        score, skill_score, sal_lpa, hits = compute_job_score(job)
        cls, _ = classify_job(" ".join([job.get("title",""), job.get("description","")]))
        df_rows.append({
            "idx": idx,
            "title": job.get("title"),
            "company": job.get("company"),
            "location": job.get("location"),
            "salary_lpa": sal_lpa,
            "skill_match": skill_score,
            "score": score,
            "category": cls,
            "apply_link": job.get("apply_link")
        })
    df = pd.DataFrame(df_rows)
    st.subheader("Jobs — ranked")
    st.dataframe(df.sort_values("score", ascending=False).reset_index(drop=True), use_container_width=True)

    st.markdown("---")
    st.subheader("Actions — select a job")
    sel = st.number_input("Select job index (from table)", min_value=0, max_value=len(df_rows)-1, value=0, step=1)

    job = jobs_list[int(sel)]
    st.markdown(f"### {job.get('title')} — {job.get('company')} — {job.get('location')}")
    st.write(job.get("description"))
    st.markdown(f"**Apply:** {job.get('apply_link')}")

    # detect emails
    emails = detect_emails(" ".join([job.get("title",""), job.get("description",""), job.get("apply_link","")]))
    st.write("Detected emails:", emails or "None found")

    # generate snippet
    score, skill_score, sal_lpa, hits = compute_job_score(job)
    st.markdown("### Resume Snippet (Tailored)")
    snippet = generate_resume_snippet(job.get("title"), job.get("company"), hits)
    st.code(snippet)

    st.markdown("### Interview Answer Generator")
    answers = interview_answers(job.get("title"), job.get("description"))
    for k,v in answers.items():
        st.write(f"**{k.replace('_',' ').title()}**")
        st.write(v)

    st.markdown("### Skill-gap & Mini-project")
    _, user_hits = skill_match_score(" ".join([job.get("title",""), job.get("description","")]), USER_SKILLS)
    missing = [s for s in ["nlp","fastapi","docker","kubernetes","lstm","pytorch","tensorflow"] if s not in user_hits]
    st.write("Missing skills detected:", missing[:5] or "None")
    st.write(mini_project_suggestion(missing))

    # buttons: log, auto-apply (simulated), whatsapp
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Log to Google Sheet"):
            row = [
                uid(),
                datetime.now().isoformat(),
                job.get("title"),
                job.get("company"),
                job.get("location"),
                sal_lpa,
                classify_job(job.get("title")+ " " + job.get("description"))[0],
                job.get("apply_link"),
                "RapidAPI",
                skill_score,
                score,
                "; ".join(emails),
                "Logged"
            ]
            ok, err = log_to_sheet(row)
            if ok:
                st.success("Logged to Google Sheet")
            else:
                st.error(f"Log failed: {err}")

    with col2:
        if st.button("Generate Resume bullet and Copy"):
            st.success("Snippet ready — copy it into your resume")

        if st.button("Simulate Auto-Apply"):
            # simulation: open link in a new tab (can't actually apply)
            st.info("Auto-apply simulated. Use manual apply link to complete application.")
            # log as applied
            row = [
                uid(),
                datetime.now().isoformat(),
                job.get("title"),
                job.get("company"),
                job.get("location"),
                sal_lpa,
                classify_job(job.get("title")+ " " + job.get("description"))[0],
                job.get("apply_link"),
                "RapidAPI",
                skill_score,
                score,
                "Auto-Apply-Simulated",
                "Applied"
            ]
            ok, err = log_to_sheet(row)
            if ok:
                st.success("Simulated apply logged")

    with col3:
        if st.button("Send WhatsApp Alert (if >=80)"):
            if score >= 80:
                msg = (f"High-match job!\n{job.get('title')} at {job.get('company')}\nSalary: {sal_lpa} LPA\nScore: {score}\nLink: {job.get('apply_link')}")
                ok, resp = send_whatsapp(msg)
                if ok:
                    st.success("WhatsApp sent")
                else:
                    st.error(f"WhatsApp failed: {resp}")
            else:
                st.info("Job score below threshold (80). No WhatsApp sent.")

st.markdown("---")
st.caption("JobBot+ v1 — Hybrid. Built for Vikrant. Extend with the Chrome 'Scan Job' extension by posting job JSON to your JobBot endpoint.")
