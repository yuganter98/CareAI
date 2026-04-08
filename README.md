# 🚀 CareAI — Agentic AI Healthcare Assistant

> A production-aware, full-stack AI system that analyzes medical reports, tracks health trends, and delivers personalized insights using a **multi-agent architecture with LLM-driven orchestration**.

---

## ⚡ TL;DR

CareAI is an intelligent healthcare system that:

* 📄 Understands medical reports using **RAG (Retrieval-Augmented Generation)**
* 🤖 Uses **multi-agent AI orchestration** for analysis and reasoning
* ⚡ Streams **real-time agent execution updates**
* 📊 Provides **analytics + trend visualization**
* 💬 Enables **chat-based health copilot**
* 🚨 Triggers alerts for **high-risk conditions**

---

## 🧠 Overview

Medical reports are complex and difficult to interpret, especially for non-medical users.

CareAI solves this by converting:

```text
Unstructured Medical Reports → AI Analysis → Structured Insights → Actionable Intelligence
```

Users can:

* Upload reports (PDF/Image)
* Get simplified explanations
* Track health trends over time
* Receive alerts for risky conditions
* Interact with an AI-powered health copilot

> **Disclaimer:** AI-generated insights only. Not a substitute for professional medical advice.

---

## 🔄 End-to-End Pipeline

```text
Upload Report (PDF/Image)
        ↓
Text Extraction (PyMuPDF + Tesseract OCR)
        ↓
RAG Indexing (Sentence Transformers → FAISS)
        ↓
LLM Planner decides which agents to run
        ↓
Agent Pipeline (Analyzer → Diagnosis → Insights → Emergency?)
        ↓
Metrics stored in PostgreSQL + Observability logs
        ↓
Personalized Dashboard + Real-time UI
        ↓
SMS / Email Alerts (if HIGH risk)
```

---

## 🏗️ Architecture

```text
Frontend (Next.js)
        ↓
FastAPI Backend
        ↓
Agent Orchestrator (Core Brain)
        ↓
AI Agents + RAG Pipeline
        ↓
PostgreSQL + FAISS
        ↓
LLM (Local / API)
```

---

## 🚀 Key Highlights

* ✅ Multi-agent AI system with LLM-driven orchestration
* ✅ RAG pipeline for contextual medical understanding
* ✅ Real-time observability using WebSockets
* ✅ Explainable AI with grounded reasoning
* ✅ Personalized health analytics and trend detection
* ✅ Production-aware backend design (async, validation, fallback logic)

---

## 🧩 Multi-Agent System

| Agent                    | Responsibility                 | Fallback            |
| ------------------------ | ------------------------------ | ------------------- |
| **LLM Planner**          | Decides which agents to run    | Default pipeline    |
| **ReportAnalyzerAgent**  | Summary + abnormalities + risk | Structured fallback |
| **DiagnosisAgent**       | Clinical interpretation        | Heuristic fallback  |
| **InsightsAgent**        | Patient-friendly insights      | Template fallback   |
| **EmergencyAgent**       | Sends alerts for HIGH risk     | Always enforced     |
| **ExplainabilityEngine** | Answers “why” questions        | Raw data fallback   |

---

## 🧠 LLM-Driven Orchestration

Instead of a fixed pipeline, CareAI uses an LLM to dynamically decide execution:

```python
{
  "agents_to_run": ["ReportAnalyzerAgent", "DiagnosisAgent", "InsightsAgent"],
  "reasoning": "Elevated glucose detected — clinical analysis required.",
  "risk_hint": "Medium"
}
```

* If planning fails → fallback to full pipeline
* HIGH-risk always triggers EmergencyAgent

---

## 🛡️ Structured Output & Reliability

Every LLM response is:

* Parsed safely
* Validated via Pydantic
* Fallback applied if invalid

```python
parsed = json.loads(parse_json_block(raw))
output = ReportAnalysisOutput.model_validate(parsed)
```

👉 Ensures **no unvalidated AI output reaches production logic**

---

## 📊 Analytics & Insights Engine

* Extracts structured medical metrics (glucose, hemoglobin, etc.)
* Computes trends: increasing / decreasing / stable
* Applies clinical reference ranges
* Generates personalized insights

```python
REFERENCE_RANGES = {
    "glucose": {"normal": (70, 100), "borderline": (100, 126)},
    "hemoglobin": {"normal": (12, 17.5)}
}
```

---

## 💬 Explainability Engine

API:

```http
POST /api/v1/ai/explain
```

Example response:

```json
{
  "explanation": "Glucose was 287 mg/dL, exceeding critical threshold of 200...",
  "supporting_data": ["glucose: 287 mg/dL"],
  "confidence": "high"
}
```

👉 Ensures **transparent and trustworthy AI decisions**

---

## 🔍 RAG Pipeline

* Embeddings: `all-MiniLM-L6-v2`
* Vector store: FAISS
* Chunking: 500 words + overlap
* Per-report filtering

👉 Enables **accurate, context-aware answers**

---

## 🔎 Agent Observability

Every agent execution is logged:

```text
Agent            Status     Duration
------------------------------------
Analyzer         Completed  1240ms
Diagnosis        Completed   890ms
Emergency        Completed   210ms
```

👉 Provides:

* Debugging visibility
* Performance tracking
* Production observability

---

## ⚡ Real-Time System

* WebSocket-based event streaming
* Live agent execution updates

```text
🟡 Running Analyzer...
✅ Diagnosis Completed
🚨 Emergency Triggered
```

---

## 🔐 Security

| Concern    | Implementation          |
| ---------- | ----------------------- |
| Auth       | JWT in httpOnly cookies |
| CORS       | Restricted origins      |
| Validation | Pydantic                |
| Passwords  | bcrypt                  |
| Secrets    | `.env` + `.gitignore`   |

---

## 🧠 Tech Stack

**Backend:** FastAPI, SQLAlchemy (async), PostgreSQL
**AI/ML:** OpenAI / LM Studio, FAISS, Sentence Transformers
**Frontend:** Next.js 16, TypeScript, Tailwind, Recharts
**Realtime:** WebSockets
**DevOps:** Docker, pytest

---

## 🛠️ Running Locally

```bash
# Start DB
docker compose up -d

# Backend
cd backend
cp .env.example .env
pip install -r requirements.txt
python run.py

# Frontend
cd frontend
npm install
npm run dev
```

---

## 📡 API Endpoints

| Method | Endpoint           | Description     |
| ------ | ------------------ | --------------- |
| POST   | /auth/login        | Login           |
| POST   | /reports/upload    | Upload report   |
| POST   | /ai/process-report | Run AI pipeline |
| POST   | /ai/copilot-chat   | Chat with AI    |
| POST   | /ai/explain        | Explain results |
| GET    | /metrics/trends    | Analytics data  |

---

## 🔮 Future Improvements

* Redis (distributed real-time system)
* pgvector (scalable vector DB)
* Doctor dashboard (multi-patient)
* Predictive health modeling

---

## 💼 Why This Project Stands Out

This is not just a chatbot.

It demonstrates:

* Multi-agent AI system design
* RAG-based contextual intelligence
* Real-time event-driven architecture
* Explainable AI for healthcare
* Production-aware full-stack engineering

---

## 🎤 Interview Notes

* Designed **LLM-driven orchestration** instead of static pipelines
* Implemented **structured validation for all AI outputs**
* Built **observability system for agent execution tracking**
* Ensured **graceful fallback for reliability**
* Focused on **explainability for healthcare trust**

---

## 👨💻 Author

Built to demonstrate **agentic AI, system design, and production-ready engineering**.

---

⭐ If you found this interesting, consider giving it a star!
