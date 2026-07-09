# 🤖 Onkar AI

> A Full-Stack AI Personal Assistant built with FastAPI, React, Groq LLM, Tavily Search and PDF RAG.

![React](https://img.shields.io/badge/React-19-61DAFB?logo=react)
![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi)
![Python](https://img.shields.io/badge/Python-3.13-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green)

---

# 📸 Screenshots

## 🏠 Home
![Home](screenshots/home.png)

## 💬 Chat
![Chat](screenshots/chat.png)

## 🌐 Internet Search
![Internet Search](screenshots/internet-search.png)

## 📄 PDF RAG
![PDF RAG](screenshots/pdf-rag.png)

## 💻 Code Generation
![Code](screenshots/code-generation.png)

## ⚙️ Settings
![Settings](screenshots/settings.png)

---

# ✨ Features

- 🤖 AI Chat Assistant
- 💬 Multi Chat Support
- 📚 Conversation Memory
- 🌐 Internet Search (Tavily)
- 📄 PDF RAG
- ⚡ Streaming Responses
- 🔄 Regenerate Response
- 📝 Markdown Support
- 💻 Syntax Highlighting
- 🔊 Text To Speech
- 📂 Chat History
- ⚙️ Settings Panel

---

# 🏗 Architecture

```
React Frontend
        │
        ▼
 FastAPI Backend
        │
        ▼
     Brain Agent
   ┌────┴────┐
   ▼         ▼
Groq LLM   Tavily Search
   │
   ▼
 PDF RAG + Memory
```

---

# 🛠 Tech Stack

### Frontend
- React
- Vite
- Tailwind CSS

### Backend
- FastAPI
- SQLite
- Pydantic

### AI
- Groq LLM
- Tavily Search
- PDF RAG

---

# 📂 Folder Structure

```text
Onkar-AI
│
├── app
├── frontend
├── screenshots
├── README.md
├── requirements.txt
└── .env.example
```

---

# 🚀 Installation

```bash
git clone https://github.com/onkarsalgude-sketch/Onkar-AI.git

cd Onkar-AI
```

Backend

```bash
python -m venv .venv

pip install -r requirements.txt

uvicorn app.main:app --reload
```

Frontend

```bash
cd frontend

npm install

npm run dev
```

---

# 🔑 Environment Variables

Create `.env`

```env
GROQ_API_KEY=your_key
TAVILY_API_KEY=your_key
GROQ_MODEL=llama-3.3-70b-versatile
```

---

# 🛣 Roadmap

## ✅ Version 1.0

- Multi Chat
- PDF RAG
- Internet Search
- Memory
- Streaming
- Settings
- Markdown

## 🚀 Version 2.0

- Voice Chat
- Vision AI
- Theme Switch
- Export Chat
- Multiple PDFs
- PostgreSQL

---

# 👨‍💻 Author

**Onkar Haribhau Salgude**

GitHub:
https://github.com/onkarsalgude-sketch

---

# 📄 License

This project is licensed under the MIT License.