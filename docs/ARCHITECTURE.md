# 🏗️ Onkar AI Architecture

## System Overview

```text
User
   │
   ▼
React + Vite Frontend
   │
   ▼
FastAPI Backend
   │
   ▼
Brain
   ├── AI Model (Groq)
   ├── Memory
   ├── PDF RAG
   └── Chat History
```

---

## Backend Structure

app/
├── agents/
├── api/
├── config/
├── database/
├── memory/
├── models/
├── services/
└── main.py

---

## Frontend Structure

frontend/src/
├── components/
│   ├── Chat/
│   ├── Sidebar/
│   ├── Upload/
│   └── Common/
├── hooks/
├── services/
└── App.jsx

---

## Database

- SQLite
- chat_history.db
- memory.db

---

## Deployment

Frontend → Vercel

Backend → Render