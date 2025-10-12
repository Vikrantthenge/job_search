# 🔍 Job Search Match

**Smart Resume-to-Job Matching App — Built for Recruiters, Job Seekers, and Career Strategists**

[![Open in Streamlit](https://static.streamlit.io/badges/streamlit_badge_black_white.svg)](https://jobsearchmatch.streamlit.app/)

---

### 🏷️ Badge Row: Tech Stack & App Status

![Python](https://img.shields.io/badge/Python-3.10-blue?logo=python)
![Streamlit](https://img.shields.io/badge/Streamlit-app-red?logo=streamlit)
![scikit-learn](https://img.shields.io/badge/scikit--learn-TF--IDF-orange?logo=scikit-learn)
![NLP](https://img.shields.io/badge/NLP-Cosine_Similarity-green)
![Status](https://img.shields.io/badge/Status-Live-brightgreen)
![License](https://img.shields.io/badge/License-MIT-yellow)
![Smart Salary Filter](https://img.shields.io/badge/Salary%20Filter-Smart%20Toggle%20%2B%20Histogram-8B0000)

---

## 🚀 Overview

JobSearchMatch uses NLP-powered cosine similarity to instantly match resumes with job descriptions. Upload both documents and get a match score with keyword breakdowns — all in seconds.

---

## 🧠 Features

- 📄 Upload resume and job description (PDF or text)
- 📊 Cosine similarity via TF-IDF vectorization
- 🔍 Visual breakdown of matching keywords
- ⚡ Fast, intuitive Streamlit interface

---

### 📊 Smart Salary Filter + Histogram

This app now includes a recruiter-grade salary filter with a toggle for broad search and a histogram to visualize INR salary distribution.

- ✅ **Broad Search Toggle**: Includes jobs with missing or unspecified salary data.
- ✅ **Minimum Salary Filter**: Set your threshold in LPA (Lakhs Per Annum).
- ✅ **Salary Histogram**: Visualizes how many jobs report INR salaries — helps calibrate realistic expectations.
- ✅ **Fallback Logic**: Ensures jobs aren't excluded due to missing salary fields.

> This feature improves recruiter scanability and ensures high-salary roles aren't missed due to API limitations.

---

## 💼 Use Cases

- Recruiters screening candidate-job fit
- Job seekers tailoring resumes for specific roles
- Career coaches optimizing applications

---

## 🛠️ Tech Stack

- Python 3.10
- Streamlit
- scikit-learn (TF-IDF)
- NLP (Cosine Similarity)

---

## 📎 Launch Now

👉 [Live App](https://jobsearchmatch.streamlit.app/)  
👉 [Portfolio README](https://github.com/vikrantthenge/job_search)
