# SovereignX — Phase 1: Project Foundation & Model Gateway

SovereignX is a modular AI-assisted document and telemetry analysis system built for the MRPL (Mangalore Refinery and Petrochemicals Limited) problem statement (SIH26117). 

Phase 1 establishes a clean, decoupled project architecture, health-check monitors, mock documents, and a generic **Model Gateway** interface supporting both Mock execution and local Ollama server integration.

---

## 1. Project Architecture

The workspace is organized as follows:
```text
sovereignx/
│
├── backend/
│   ├── app/
│   │   ├── main.py             # FastAPI entry point
│   │   ├── config.py           # Configuration manager using Pydantic Settings
│   │   │
│   │   ├── api/
│   │   │   ├── health.py       # Health checks (/health)
│   │   │   ├── models.py       # Model information and query router (/models, /models/chat)
│   │   │   ├── agents.py       # Agent runner placeholder (/agents/run)
│   │   │   └── documents.py    # Mock document listings (/documents)
│   │   │
│   │   ├── gateway/
│   │   │   ├── __init__.py     # ModelGateway factory function
│   │   │   ├── interface.py    # Abstract base ModelGateway class
│   │   │   ├── mock_gateway.py # Phase 1 Mock Gateway returning static analysis
│   │   │   └── ollama_gateway.py # Local Ollama Gateway implementation
│   │   │
│   │   ├── agents/             # Placeholder for future multi-agent workflows
│   │   ├── rag/                # Placeholder for future vector DB & RAG logic
│   │   ├── services/           # Placeholder for OCR/Parsing and database services
│   │   └── schemas/            # Modular Pydantic models (models, chat, agents, docs)
│   │
│   └── requirements.txt        # Backend dependencies
│
├── frontend/
│   ├── src/                    # React frontend source (Vite + Tailwind CSS)
│   │   ├── App.jsx             # SovereignX Monitor & Test Dashboard
│   │   ├── main.jsx
│   │   └── index.css
│   ├── package.json            # Node project dependencies
│   ├── tailwind.config.js      # CSS styles configuration
│   └── vite.config.js          # Vite config (dev server port 5173)
│
├── .env.example                # Config template
├── .env                        # Local configurations
├── .gitignore                  # Git exclude configurations
└── README.md                   # Setup and system manual
```

---

## 2. Backend Setup & Run

### Prerequisites
* Python 3.10+ installed.

### Installation
1. Navigate to the `backend/` directory:
   ```bash
   cd backend
   ```
2. Create and activate a virtual environment:
   * **Windows (PowerShell):**
     ```powershell
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   * **Linux/macOS:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
3. Install the dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Server
Start the backend using uvicorn:
```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
Verify the server is running by opening [http://localhost:8000/health](http://localhost:8000/health) in your browser.

---

## 3. Frontend Setup & Run

### Prerequisites
* Node.js (v18+) and npm installed.

### Installation
1. Navigate to the `frontend/` directory:
   ```bash
   cd frontend
   ```
2. Install the packages:
   ```bash
   npm install
   ```

### Running the Dashboard
Start the Vite local development server:
```bash
npm run dev
```
Open your browser and navigate to [http://localhost:5173/](http://localhost:5173/).

---

## 4. Switching Gateways (Mock vs. Ollama)

The Model Gateway design utilizes **Dependency Inversion**; all client and agent workflows query `ModelGateway.generate()` instead of making direct vendor calls.

To change configuration, edit the `.env` file in the project root:

### Using the Mock Model Gateway (Default)
Returns instantaneous, realistic inspection/SOP analysis without requiring local hardware resources:
```env
MODEL_PROVIDER=mock
```

### Using Local Ollama Integration
To route requests to a local LLM instance:
1. Ensure Ollama is running locally on your system, and pull the model you want:
   ```bash
   ollama pull qwen3.5:4b
   ```
2. Edit `.env` to set:
   ```env
   MODEL_PROVIDER=ollama
   OLLAMA_BASE_URL=http://localhost:11434
   MODEL_NAME=qwen3.5:4b  # SovereignX default (2026-08 benchmark) -- or any other model pulled via `ollama pull`
   OLLAMA_THINK=false     # Optional: disables "thinking" mode on models that support it (see below)
   ```
   SovereignX is model-configurable -- swap `MODEL_NAME` to any locally pulled Ollama model (e.g. `qwen2.5:7b`, `phi4-mini`) with no code changes. `OLLAMA_THINK` is likewise config-driven, not hardcoded per model: leave it unset to omit the field entirely (always safe, including for models with no thinking mode), or set `true`/`false` to force a specific model's thinking behavior.
3. Restart the FastAPI server. If the Ollama server is offline, the backend will launch successfully but mark the provider status as `offline` in `/models`.
