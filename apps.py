# streamlit_app.py
# Integrated Job Bot (safe) - Fetch, Score, Generate Messages, Track, Email Alerts (no auto-apply)
# Requirements: streamlit, pandas, requests, beautifulsoup4, plotly, gspread, oauth2client, Pillow

import streamlit as st
import pandas as pd
import requests, json, time, hashlib
from bs4 import BeautifulSoup
from datetime import datetime
from io import StringIO, BytesIO
from PIL import Image
import base64
import plotly.express as px
import gspread
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import smtplib

# ---------------------
# Helper: load logo
# ---------------------
@st.cache_resource
def load_logo_base64(path="vt_logo.png"):
    try:
        logo = Image.open(path)
        buffered = BytesIO()
        logo.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception:
        return None

# ---------------------
# Secrets check
# ---------------------
# Put these keys in Streamlit secrets: rapidapi.key, google.service_account (JSON), smtp.user, smtp.pass
if "rapidapi" not in st.secrets:
    st.warning("Set RapidAPI key in st.secrets['rapidapi']['key'] for best results.")
RAPIDAPI_KEY = st.secrets.get("rapidapi", {}).get("key", "")

# ---------------------
# Google Sheet setup
# ---------------------
@st.cache_resource
def get_gsheet(sheet_url=None):
    try:
        creds = json.loads(st.secrets["google"]["service_account"])
        gc = gspread.service_account_from_dict(creds)
        if sheet_url:
            sh = gc.open_by_url(sheet_url)
            return sh.sheet1
        return None
    except Exception as e:
        return None

# ---------------------
# Job source: RapidAPI JSearch
# ---------------------
def fetch_jobs_rapidapi(query, num_pages=1, rapidapi_key=""):
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": rapidapi_key,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com"
    }
    params = {"query": query, "num_pages": str(num_pages)}
    resp = requests.get(url, headers=headers, params=params, timeout=15)
    resp.raise_for_status()
    data = resp.json().get("data", [])
    out = []
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

# ---------------------
# Job source: simple Indeed scrape (fragile, optional)
# ---------------------
HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; JobBot/1.0)"}
def fetch_jobs_indeed(query, location, pages=1):
    results = []
    for p in range(pages):
        url = f"https://www.indeed.co.in/jobs?q={requests.utils.quote(query)}&l={requests.utils.quote(location)}&start={p*10}"
        r = requests.get(url, headers=HEADERS, timeout=10)
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
            link = "https://www.indeed.co.in" + (c.get("href") or "")
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
        time.sleep(1.2)
    return results

# ---------------------
# Aggregator
# ---------------------
def aggregate_jobs(query, location="India", pages=1, rapidapi_key="", use_indeed=False):
    out = []
    if rapidapi_key:
        try:
            out += fetch_jobs_rapidapi(f"{query} in {location}", num_pages=pages, rapidapi_key=rapidapi_key)
        except Exception as e:
            st.warning("RapidAPI fetch failed: " + str(e))
    if use_indeed:
        try:
            out += fetch_jobs_indeed(query, location, pages=pages)
        except Exception as e:
            st.warning("Indeed fetch failed: " + str(e))
    return out

# ---------------------
# Scoring utilities
# ---------------------
def normalize_text(s): return (s or "").lower()
def title_score(job_title, target_titles):
    jt = normalize_text(job_title)
    for t in target_titles:
        if t.lower() in jt:
            return 30
    if any(x in jt for x in ["data scientist","ml engineer","analytics engineer","machine learning","applied data"]):
        return 20
    return 0

def skills_score(text, candidate_skills):
    text = normalize_text(text)
    score = 0
    per_skill = 30 / max(1, len(candidate_skills))
    for sk in candidate_skills:
        if sk.lower() in text:
            score += per_skill
    return min(30, score)

def salary_score(salary_max, min_salary_inr):
    if not salary_max or salary_max == 0:
        return 7.5
    if salary_max >= min_salary_inr:
        return 15
    return max(0, 15 * (salary_max / min_salary_inr))

def location_score(job_loc, desired_locations):
    j = normalize_text(job_loc)
    for loc in desired_locations:
        if loc.lower() in j:
            return 10
    if "remote" in j or "work from home" in j:
        return 8
    return 0

def recency_score(posted_at_iso):
    if not posted_at_iso:
        return 5
    try:
        posted = datetime.fromisoformat(posted_at_iso.replace("Z",""))
    except:
        return 5
    days = (datetime.utcnow() - posted).days
    if days <= 3: return 10
    if days <= 7: return 7
    if days <= 30: return 4
    return 1

def overall_score(job, candidate_skills, target_titles, min_salary_inr, desired_locations):
    s = 0
    s += title_score(job.get("title",""), target_titles)
    s += skills_score(job.get("title","") + " " + (job.get("company","") or "") + " " + (job.get("location","") or ""), candidate_skills)
    s += salary_score(job.get("salary_max", 0), min_salary_inr)
    s += location_score(job.get("location",""), desired_locations)
    s += recency_score(job.get("date_posted",""))
    return round(min(100, s), 2)

# ---------------------
# Templates (messages)
# ---------------------
def gen_linkedin_message(candidate_name, role, company, key_skills, one_liner_project):
    return f"""Hi {company} Talent / Hiring Team,

I’m {candidate_name}, an Applied Data Scientist & Analytics Engineer with experience in {', '.join(key_skills[:5])}. I build end-to-end ML pipelines (forecasting, classification, NLP) and deploy production-ready models. Recently I delivered {one_liner_project}.

I’m interested in the {role} role at {company}. If this aligns, I’d appreciate the chance to discuss how I can contribute.

Regards,
{candidate_name}"""

def gen_email_cover(candidate_name, role, company, top_impact, contact_point="Hiring Team"):
    return f"""Subject: Application for {role} — {candidate_name}

Hello {contact_point},

I’m {candidate_name}, an Applied Data Scientist and Analytics Engineer. I specialize in building forecasting models, deploying ML pipelines, and automating reporting workflows. In my recent project I {top_impact}.

I’m attaching my resume and would welcome the chance to discuss this opportunity.

Regards,
{candidate_name}"""

# ---------------------
# Job ID helper
# ---------------------
def job_id(job):
    raw = (job.get("title","") + job.get("company","") + (job.get("apply_link") or "")).encode("utf-8")
    return hashlib.md5(raw).hexdigest()[:8]

# ---------------------
# Email send (Gmail / SMTP)
# ---------------------
def send_email_smtp(smtp_host, smtp_port, smtp_user, smtp_pass, to_email, subject, html_body):
    msg = MIMEMultipart()
    msg["From"] = smtp_user
    msg["To"] = to_email
    msg["Subject"] = subject
    msg.attach(MIMEText(html_body, "html"))
    server = smtplib.SMTP(smtp_host, smtp_port)
    server.starttls()
    server.login(smtp_user, smtp_pass)
    server.send_message(msg)
    server.quit()

# ---------------------
# Streamlit UI
# ---------------------
st.set_page_config(page_title="Job Bot — Vikrant", layout="wide")
logo_b64 = load_logo_base64()
if logo_b64:
    st.markdown(f"<div style='text-align:center'><img src='data:image/png;base64,{logo_b64}' width='300'/></div>", unsafe_allow_html=True)

st.title("Job Bot — Applied Data Scientist / Analytics Engineer")

# left inputs / right stats
col1, col2 = st.columns([2,1])

with col1:
    st.subheader("Search / Fetch Jobs")
    keywords = st.text_input("Job Title / Keywords", value="Applied Data Scientist")
    location = st.text_input("Location", value="Mumbai, Pune, Remote")
    pages = st.number_input("Pages to search (RapidAPI)", min_value=1, max_value=5, value=1)
    use_indeed = st.checkbox("Include Indeed (optional, fragile)", value=False)
    min_salary_lpa = st.number_input("Minimum salary (LPA)", value=24.0, step=0.5)
    include_unspecified = st.checkbox("Include jobs with unspecified salary", value=True)
    desired_locations = [x.strip() for x in location.split(",")]
    candidate_skills = st.text_input("Candidate skills (comma separated)", value="Python, SQL, Power BI, Forecasting, NLP, Streamlit")
    candidate_skills = [s.strip() for s in candidate_skills.split(",") if s.strip()]
    target_titles = ["Data Scientist","Applied Data Scientist","Analytics Engineer","ML Engineer","Decision Scientist"]
    min_salary_inr = int(min_salary_lpa * 100000)

    if st.button("Fetch & Score Jobs"):
        with st.spinner("Fetching jobs..."):
            raw = aggregate_jobs(keywords, location=location, pages=pages, rapidapi_key=RAPIDAPI_KEY, use_indeed=use_indeed)
            for j in raw:
                j["job_id"] = job_id(j)
                j["score"] = overall_score(j, candidate_skills, target_titles, min_salary_inr, desired_locations)
            jobs_df = pd.DataFrame(raw)
            if jobs_df.empty:
                st.warning("No jobs found. Try enabling unspecified salary or broaden keywords.")
            else:
                jobs_df = jobs_df.sort_values("score", ascending=False)
                st.session_state["job_df"] = jobs_df
                st.success(f"Fetched {len(jobs_df)} jobs. Top results shown below.")

with col2:
    st.subheader("Quick Metrics")
    job_df = st.session_state.get("job_df", pd.DataFrame())
    if not job_df.empty:
        st.metric("Jobs Fetched", len(job_df))
        st.metric("Top Score", float(job_df["score"].max()))
        fig = px.histogram(job_df["score"], nbins=10, title="Score Distribution")
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("No jobs in session. Click 'Fetch & Score Jobs' to load.")

# Display job cards
st.markdown("---")
job_df = st.session_state.get("job_df", pd.DataFrame())
if not job_df.empty:
    st.subheader("Job Matches (Sorted by Score)")
    # show interactive table
    display_cols = ["score","title","company","location","salary_max","apply_link","source"]
    df_show = job_df.copy()
    # human-friendly salary column
    df_show["Salary Display"] = df_show["salary_max"].apply(lambda x: f"₹{int(x):,}" if x and x>0 else "Not disclosed")
    st.dataframe(df_show[["score","title","company","location","Salary Display","apply_link","source"]].head(50))

    # Per-row actions (first N)
    for idx, row in df_show.head(25).iterrows():
        st.markdown(f"### {row['title']}  —  *{row['company']}*  |  Score: **{row['score']}**")
        st.markdown(f"Location: {row['location']}  •  Source: {row['source']}  •  Salary: {row.get('salary_max') or 'Not disclosed'}")
        cols = st.columns([3,1,1,2])
        cols[0].markdown(f"[Open Apply Page]({row['apply_link']})")
        if cols[1].button("Gen Msg", key=f"msg_{row['job_id']}"):
            msg = gen_linkedin_message("Vikrant Thenge", row["title"], row["company"], candidate_skills, "delivered forecasting & automation gains")
            st.text_area("LinkedIn Message (copy & paste)", value=msg, height=180)
        if cols[2].button("Gen Email", key=f"email_{row['job_id']}"):
            email_body = gen_email_cover("Vikrant Thenge", row["title"], row["company"], "improving forecasting accuracy and automating reporting")
            st.text_area("Email body (copy & paste)", value=email_body, height=160)
        if cols[3].button("Mark Applied", key=f"apply_{row['job_id']}"):
            sheet = get_gsheet(st.sidebar.text_input("Google Sheet URL", value=st.secrets.get("google",{}).get("sheet_url","")))
            timestamp = datetime.utcnow().isoformat()
            if sheet:
                try:
                    row_to_append = [row["job_id"], timestamp, row["title"], row["company"], row["location"], row["score"], row.get("apply_link",""), row.get("source",""), "Applied", ""]
                    sheet.append_row(row_to_append)
                    st.success("Logged to Google Sheet")
                except Exception as e:
                    st.error("Failed to write to Google Sheet: " + str(e))
            else:
                st.info("No Google Sheet configured. Add service_account in st.secrets.")

        st.markdown("---")

# Bulk export / download selected subset
if not job_df.empty:
    if st.button("Download Top 50 as CSV"):
        out = job_df.head(50).copy()
        out["salary_display"] = out["salary_max"].apply(lambda x: f"₹{int(x):,}" if x and x>0 else "Not disclosed")
        csv = out.to_csv(index=False)
        st.download_button("📥 Download CSV", data=csv, file_name=f"job_matches_{datetime.now().strftime('%Y%m%d_%H%M')}.csv", mime="text/csv")

# Send daily email (on demand)
st.markdown("---")
st.subheader("Email Alerts (Manual Trigger)")
smtp_user = st.secrets.get("smtp",{}).get("user","")
smtp_pass = st.secrets.get("smtp",{}).get("pass","")
to_email = st.text_input("Send alerts to (email)", value=smtp_user or "")
if st.button("Send Top 10 via Email") and not job_df.empty:
    if smtp_user and smtp_pass and to_email:
        top10 = job_df.head(10)
        html = "<h3>Top 10 job matches</h3><ul>"
        for _, r in top10.iterrows():
            link = r.get("apply_link","")
            html += f"<li><b>{r['title']}</b> at {r['company']} — Score {r['score']} — <a href='{link}'>Apply</a></li>"
        html += "</ul>"
        try:
            send_email_smtp("smtp.gmail.com", 587, smtp_user, smtp_pass, to_email, "Daily Job Matches - Job Bot", html)
            st.success("Email sent")
        except Exception as e:
            st.error("Email failed: " + str(e))
    else:
        st.error("Configure smtp user/pass in st.secrets and provide recipient email.")

# Footer
st.markdown("""
---
Built with ⚙️ • Job scraping (RapidAPI + optional Indeed) • Scoring • Message templates • Google Sheets logging • Email alerts  
No auto-apply. Respect platforms' terms of service.
""")


