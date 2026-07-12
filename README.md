# 🤖 Onkar AI

> A full-stack AI personal assistant built with FastAPI, React, Groq LLM, Tavily Search, PDF RAG, persistent memory and Docker.

[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=white)](https://react.dev/)
[![FastAPI](https://img.shields.io/badge/FastAPI-Backend-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Python](https://img.shields.io/badge/Python-3.11-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ED?logo=docker&logoColor=white)](https://www.docker.com/)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)

---

## 🌐 Live Application

- **Frontend:** https://onkar-ai.vercel.app
- **Backend:** https://onkar-ai-backend.onrender.com
- **API Documentation:** https://onkar-ai-backend.onrender.com/docs

> The backend is hosted on Render, so the first request may take a little longer when the service wakes up.

---

## 📸 Screenshots

### 🏠 Home

![Home](screenshots/home.png)

### 💬 AI Chat

![Chat](screenshots/chat.png)

### 🌐 Internet Search

![Internet Search](screenshots/internet-search.png)

### 📄 PDF RAG

![PDF RAG](screenshots/pdf-rag.png)

### 💻 Code Generation

![Code Generation](screenshots/code-generation.png)

### ⚙️ Settings

![Settings](screenshots/settings.png)

---

## ✨ Features

- 🤖 AI-powered chat assistant
- 💬 Multiple chat conversations
- 📚 Persistent conversation memory
- 🌐 Real-time internet search using Tavily
- 📄 PDF upload and Retrieval-Augmented Generation
- ⚡ Streaming AI responses
- 🔄 Regenerate and retry responses
- 🧠 Multiple Groq model selection
- 📝 Markdown rendering
- 💻 Syntax-highlighted code blocks
- 📋 Copy Code button
- 🔊 Text-to-speech support
- 📂 Persistent chat history
- ⚙️ Settings panel
- 📡 Online and offline status handling
- 🚨 User-friendly error messages
- 🐳 Docker and Docker Compose support
- 💾 Persistent Docker volumes

---

## 🆕 Version 2.4 Highlights

Version 2.4 improves the AI chat experience and deployment workflow.

- Added Groq model selector
- Added multiple supported AI models
- Improved Markdown rendering
- Added syntax highlighting
- Added Copy Code functionality
- Added retry support for failed messages
- Added better API and network error handling
- Added online/offline detection
- Added Dockerfile
- Added Docker Compose setup
- Added persistent database and storage volumes
- Updated project documentation

---

## 🧠 Supported AI Models

Onkar AI currently supports the following Groq models:

- `llama-3.3-70b-versatile`
- `llama-3.1-8b-instant`
- `openai/gpt-oss-20b`
- `openai/gpt-oss-120b`

The selected model is saved in the browser and reused for future chats.

---

## 🏗 Architecture

```text
┌──────────────────────┐
│    React Frontend    │
│   Vite + Tailwind    │
└──────────┬───────────┘
           │ HTTP / Streaming
           ▼
┌──────────────────────┐
│   FastAPI Backend    │
│  REST API + Uploads  │
└──────────┬───────────┘
           ▼
┌──────────────────────┐
│     Brain Agent      │
└──────┬───────┬───────┘
       │       │
       ▼       ▼
┌──────────┐ ┌──────────────┐
│ Groq LLM │ │ Tavily Search│
└────┬─────┘ └──────────────┘
     │
     ▼
┌──────────────────────┐
│ PDF RAG + Memory     │
│ SQLite + Vector DB   │
└──────────────────────┘
```

---

## 🛠 Tech Stack

### Frontend

- React 19
- Vite
- Tailwind CSS
- React Markdown
- Syntax Highlighting
- Fetch Streaming API

### Backend

- Python 3.11
- FastAPI
- Uvicorn
- Pydantic
- SQLite
- ChromaDB

### Artificial Intelligence

- Groq LLM API
- Tavily Search API
- PDF Retrieval-Augmented Generation
- Conversation Memory
- Multi-model support

### DevOps and Deployment

- Docker
- Docker Compose
- Vercel
- Render
- GitHub

---

## 📂 Folder Structure

```text
Onkar-AI/
│
├── app/
│   ├── agents/
│   ├── api/
│   ├── config/
│   ├── database/
│   ├── models/
│   ├── services/
│   └── main.py
│
├── frontend/
│   ├── public/
│   ├── src/
│   ├── package.json
│   └── vite.config.js
│
├── storage/
│   ├── pdfs/
│   ├── uploads/
│   └── vector_db/
│
├── screenshots/
│
├── .dockerignore
├── .env.example
├── .gitignore
├── compose.yaml
├── Dockerfile
├── README.md
└── requirements.txt
```

---

## 🔑 Environment Variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_api_key
TAVILY_API_KEY=your_tavily_api_key
```

Do not commit the `.env` file to GitHub.

You can copy the example environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

---

## 🚀 Run with Docker Compose

Docker Compose is the recommended way to run the backend.

### 1. Clone the repository

```bash
git clone https://github.com/onkarsalgude-sketch/Onkar-AI.git
cd Onkar-AI
```

### 2. Create the environment file

```powershell
Copy-Item .env.example .env
```

Add your API keys to `.env`.

### 3. Build and start the backend

```bash
docker compose up --build -d
```

### 4. Check container status

```bash
docker compose ps
```

### 5. Open API documentation

```text
http://127.0.0.1:8000/docs
```

### View container logs

```bash
docker compose logs -f backend
```

### Stop the application

```bash
docker compose down
```

### Stop and remove persistent volumes

```bash
docker compose down -v
```

> Warning: `docker compose down -v` permanently removes Docker database and storage volumes.

---

## 🐳 Run with Docker

### Build the image

```bash
docker build -t onkar-ai-backend:v2.4 .
```

### Run the container

```powershell
docker run --name onkar-ai-backend `
  --env-file .env `
  -p 8000:8000 `
  onkar-ai-backend:v2.4
```

Open:

```text
http://127.0.0.1:8000/docs
```

---

## 💻 Local Development Setup

### Prerequisites

- Python 3.11
- Node.js
- npm
- Git

### 1. Clone the repository

```bash
git clone https://github.com/onkarsalgude-sketch/Onkar-AI.git
cd Onkar-AI
```

### 2. Create a Python virtual environment

```bash
python -m venv .venv
```

Activate it on Windows:

```powershell
.venv\Scripts\Activate.ps1
```

Activate it on Linux or macOS:

```bash
source .venv/bin/activate
```

### 3. Install backend dependencies

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Start the FastAPI backend

```bash
uvicorn app.main:app --reload
```

The backend will be available at:

```text
http://127.0.0.1:8000
```

API documentation:

```text
http://127.0.0.1:8000/docs
```

### 5. Start the frontend

Open another terminal:

```bash
cd frontend
npm install
npm run dev
```

The frontend will usually be available at:

```text
http://localhost:5173
```

---

## 💾 Persistent Storage

Onkar AI stores application data in:

```text
app/database/
storage/
```

Docker Compose uses named volumes for:

```text
/app/app/database
/app/storage
```

This keeps chat history, uploaded documents and vector data available after the container restarts.

---

## 🔌 Main API Capabilities

The FastAPI backend provides APIs for:

- AI chat
- Streaming responses
- Chat history
- Model listing and selection
- Internet search
- PDF upload and retrieval
- Conversation memory
- Chat regeneration
- Health and API documentation

Open Swagger UI to view and test the available endpoints:

```text
http://127.0.0.1:8000/docs
```

---

## 🧪 Useful Docker Commands

List running containers:

```bash
docker ps
```

List Docker images:

```bash
docker images
```

Restart the backend:

```bash
docker compose restart backend
```

Rebuild after code changes:

```bash
docker compose up --build -d
```

View recent logs:

```bash
docker compose logs --tail=100 backend
```

Open a shell inside the container:

```bash
docker compose exec backend bash
```

---

## 🛣 Roadmap

### ✅ Version 1.0

- AI chat
- Multiple chats
- PDF RAG
- Internet search
- Conversation memory
- Streaming responses
- Settings panel
- Markdown rendering

### ✅ Version 2.3

- Improved user interface
- Better chat experience
- Deployment improvements
- Stable frontend and backend integration

### ✅ Version 2.4

- Model selector
- Better Markdown rendering
- Syntax highlighting
- Copy Code button
- Error handling
- Retry support
- Docker setup
- Persistent volumes
- Updated documentation

### 🔮 Future Plans

- Speech-to-text input
- Vision and image understanding
- User authentication
- Multiple PDF knowledge bases
- Chat export
- PostgreSQL support
- Agent tools and automation
- Mobile application

---

## 🤝 Contributing

Contributions, suggestions and bug reports are welcome.

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push the branch
5. Open a pull request

---

## 👨‍💻 Author

**Onkar Haribhau Salgude**

- GitHub: https://github.com/onkarsalgude-sketch
- Project Repository: https://github.com/onkarsalgude-sketch/Onkar-AI

---

## 📄 License

This project is licensed under the MIT License.