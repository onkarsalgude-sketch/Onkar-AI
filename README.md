# 🤖 Onkar AI

A modern AI-powered personal assistant built with **FastAPI**, **React**, **Groq LLM**, **Tavily Search**, and **PDF RAG**.

---

## ✨ Features

- 💬 Multi Chat
- 🧠 Conversation Memory
- 🌐 Internet Search
- 📄 PDF RAG
- ⚡ Streaming Responses
- 🔄 Regenerate Response
- 📝 Markdown Support
- 💻 Syntax Highlighting
- 🔊 Text-to-Speech
- 📁 Chat History
- 🔍 Search Chats
- ☁️ Deploy Ready

---

## 🛠 Tech Stack

### Frontend
- React
- Vite
- TailwindCSS
- Axios
- React Markdown

### Backend
- FastAPI
- Groq API
- Tavily Search
- SQLite
- PyPDF

---

## 📂 Project Structure

```text
Onkar-AI
│
├── app
│   ├── agents
│   ├── api
│   ├── config
│   ├── database
│   ├── memory
│   ├── models
│   ├── services
│   └── uploads
│
├── frontend
│   ├── src
│   ├── public
│   └── package.json
│
├── docs
├── screenshots
└── README.md
```

---

## 🚀 Installation

### Clone Repository

```bash
git clone https://github.com/onkarsalgude-sketch/Onkar-AI.git

cd Onkar-AI
```

### Backend

```bash
python -m venv .venv

source .venv/bin/activate

pip install -r requirements.txt

uvicorn app.main:app --reload
```

### Frontend

```bash
cd frontend

npm install

npm run dev
```

---

## 🔑 Environment Variables

Create `.env`

```env
GROQ_API_KEY=

TAVILY_API_KEY=

GROQ_MODEL=llama-3.3-70b-versatile
```

---

## 📸 Screenshots

### Chat

(Add Screenshot)

### Internet Search

(Add Screenshot)

### PDF RAG

(Add Screenshot)

---

## 🏗 Architecture

```text
                User

                  │

            React Frontend

                  │

             FastAPI Backend

                  │

               Brain Router

      ┌───────────┼───────────┐

      ▼           ▼           ▼

 Internet     PDF RAG      Memory

                  │

              Groq LLM
```

---

## 🎯 Roadmap

- ✅ Multi Chat
- ✅ Internet Search
- ✅ PDF Chat
- ✅ Memory
- ✅ Streaming
- ✅ Regenerate
- ⏳ Sources Card
- ⏳ Theme Switch
- ⏳ Voice Chat
- ⏳ Vision AI
- ⏳ Authentication

---

## 👨‍💻 Author

**Onkar Haribhau Salgude**

GitHub:
https://github.com/onkarsalgude-sketch

---

## ⭐ Support

If you like this project, don't forget to star the repository.