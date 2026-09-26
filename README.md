<div align="center">

# 🧠 Minddora AI

### Chat with your own notes — locally, privately, and for free.

An open-source RAG (Retrieval-Augmented Generation) study assistant. Upload your documents, ask questions in plain English, and get answers pulled directly from your own material — with citations back to the source.

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/Python-3.11%2B-blue)](https://www.python.org/)
[![Flask](https://img.shields.io/badge/Flask-3.0-black)](https://flask.palletsprojects.com/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-14%2B-336791)](https://www.postgresql.org/)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen.svg)](CONTRIBUTING.md)

[Features](#-features) • [How It Works](#-how-it-works) • [Getting Started](#-getting-started) • [Optional AI Mode](#-optional-ai-powered-mode) • [Tech Stack](#-tech-stack) • [Team](#-team)

</div>

---

## 🎯 What is Minddora AI?

Most AI chat tools answer from general internet knowledge, which means they can confidently make things up. Minddora AI does the opposite: it only answers using **your own uploaded documents**, so every response can be traced back to the exact page it came from.

Under the hood, it's not a thin wrapper around an API — it's a genuinely engineered **hybrid retrieval engine** combining semantic search, keyword search, and cross-encoder reranking, running entirely on your own machine.

## ✨ Features

- 🔍 **Hybrid Search Engine** — Semantic search (sentence embeddings) + BM25 keyword search, merged with Reciprocal Rank Fusion, then re-ranked by a cross-encoder for real accuracy — not just vector similarity alone.
- 📄 **Multi-Format Document Support** — PDF, DOCX, TXT, Markdown, and even scanned images (via OCR).
- 🎯 **Direct Fact Extraction** — Structured lookups (dates, emails, IDs, amounts) get answered instantly through targeted extraction, without waiting on a full search pass.
- 🔒 **Fully Local & Private** — Your documents, embeddings, and vector index never leave your machine. No mandatory third-party API calls.
- ✨ **Optional AI-Powered Mode** — Plug in your own free Gemini API key anytime for richer, generated answers on top of the retrieval engine. Never required — always opt-in.
- 💬 **Real Conversations** — Full chat history, citations, and confidence scoring on every answer.
- 🖥️ **Live System Visualizations** — Built-in tools to literally *watch* the retrieval engine work: a real-time network diagram of system activity, and a visualizer showing exactly which chunks of your document were considered for a given question.
- 💯 **100% Free & Open Source** — No subscriptions, no vendor lock-in, no required API keys. Runs on infrastructure you already have.

## 🧩 How It Works

```
 Upload Document
       │
       ▼
 Extract & clean text  →  Split into chunks  →  Generate embeddings
       │
       ▼
 Store in PostgreSQL + local vector index
       │
       ▼
 ┌─────────────────────────────────────────────┐
 │              Ask a question                 │
 └─────────────────────────────────────────────┘
       │
       ▼
 Semantic search  +  BM25 keyword search
       │
       ▼
 Merge (Reciprocal Rank Fusion)  →  Cross-encoder reranking
       │
       ▼
 Extract the best-matching passage(s)  →  Answer, with citation
```

## 🚀 Getting Started

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 14+**
- **Tesseract OCR** (only needed for scanned image uploads)

### Installation

```bash
# Clone the repo
git clone https://github.com/YOUR-USERNAME/minddora-ai.git
cd minddora-ai

# Create and activate a virtual environment
python -m venv venv
source venv/bin/activate      # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Database Setup

```bash
psql -U postgres -c "CREATE DATABASE minddora_db;"
psql -U postgres -c "CREATE USER minddora_user WITH PASSWORD 'minddora_pass';"
psql -U postgres -c "GRANT ALL PRIVILEGES ON DATABASE minddora_db TO minddora_user;"
```

### Configuration

```bash
cp .env.example .env
```

Edit `.env` with your database credentials and a random secret key. See [`.env.example`](.env.example) for every available option.

### Run It

```bash
flask db upgrade
python run.py
```

Open `http://localhost:5000` — that's it. No sign-up, no login. This is the **local edition**: a single profile is created automatically on first run, and you're straight into the app.

## ✨ Optional: AI-Powered Mode

By default, Minddora AI answers using only its local retrieval engine — no API keys, no external calls. If you want richer, generated answers on top of that retrieval, you can optionally connect your own **free** Gemini API key:

1. Get a free key at [ai.google.dev](https://ai.google.dev)
2. Go to **Settings → AI Answer Mode** inside the app
3. Switch to "AI-Powered," paste your key, save

This is entirely optional and can be switched off at any time — the app is fully functional without it.

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python, Flask, SQLAlchemy |
| Database | PostgreSQL |
| Embeddings | Sentence-Transformers (MiniLM) |
| Vector Search | FAISS |
| Keyword Search | BM25 |
| Reranking | Cross-Encoder |
| Optional Generation | Google Gemini API (user-supplied key) |
| Frontend | HTML, CSS, Vanilla JavaScript |
| Document Processing | pdfplumber, python-docx, Tesseract OCR |

## 📸 Screenshots

> _Add screenshots or a short demo GIF here — the chat interface, the Live Network visualizer, and the RAG Visualizer are great ones to showcase._

## 🗺️ Roadmap

- [ ] Summarization / key-points extraction mode
- [ ] Multi-file drag-and-drop upload
- [ ] Inline PDF viewer with citation highlighting
- [ ] Background/async document processing for large files

Contributions and ideas are very welcome — see below.

## 🤝 Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you'd like to change.

```bash
git checkout -b feature/your-feature-name
# make your changes
git commit -m "Add your feature"
git push origin feature/your-feature-name
```

## 👥 Team

Built by a small team who wanted a better way to study:

- **Dhruvil Dave**
- **Archan**
- **Kartik**
- **Vasu**

Every part of this — from the retrieval engine to the UI to relentless bug-hunting — was very much a team effort.

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

<div align="center">

If this project helped you, consider giving it a ⭐ — it genuinely helps others find it.

</div>
