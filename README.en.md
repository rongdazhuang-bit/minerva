# Minerva

Minerva is an enterprise-level intelligent application platform built on modern technology stack, featuring FastAPI backend, React frontend, and PostgreSQL database architecture. The project is organized in a modular manner, offering high scalability and maintainability.

## Core Features:

- **AI Intelligence Integration**: Built-in OpenAI-compatible AI calling module supporting multiple large model providers with unified AI service interfaces
- **Rule Engine System**: Powerful rule management module supporting business logic configuration for engineering codes, review rules, etc.
- **Distributed Task Scheduling**: Celery-based distributed task scheduling system supporting hot updates and visual Cron expression configuration
- **OCR Document Processing**: Integration of multiple OCR engines supporting file recognition and intelligent document processing
- **Data Dictionary Management**: Unified data dictionary system supporting multi-level classification management
- **S3 Cloud Storage Integration**: Comprehensive cloud storage solution
- **Technical Advantages**: The project adopts Domain-Driven Design (DDD) architecture with clear module decoupling and multi-tenant isolation support. Through Docker containerized deployment, it provides complete development environment and production deployment solutions. Minerva is dedicated to providing enterprises with intelligent business processing platforms, particularly suitable for application scenarios requiring rule engines, AI integration, and automated task scheduling.

## Environment Requirements

| Dependency | Description |
|------------|-------------|
| Docker | For starting PostgreSQL with `docker compose` |
| Python | 3.11+ |
| Node.js | 20+ |
| System | Ports 5432, 8000, 5173 should be available for local access |

## 1. Code Setup and Infrastructure

1. Clone this repository and execute in the **repository root directory** to start the database:

   ```bash
   docker compose up -d
   ```

2. Confirm the `postgres` container is running normally (Up).

## 2. Environment Variables Configuration

Copy `backend/.env.example` to `backend/.env` (if there's another `.env.example` in the repository root directory, follow the instructions in `backend/.env.example`):

**Linux / macOS:**

```bash
cp backend/.env.example backend/.env.local
```

**Windows (PowerShell):**

```powershell
Copy-Item backend/.env.example backend/.env.local
```

Optional team dev config: `cp backend/.env.example backend/.env.dev` (loaded with `run-backend dev`).

The default configuration in `backend/.env.local` can connect to the database exposed by local `docker compose` (`127.0.0.1:5432`). **For production or team collaboration, modify `JWT_SECRET` to a sufficiently long random string.**

## 3. Backend: Dependency Installation and Startup

Execute the following commands in the **`backend` directory** (first `cd backend`).

### Install Dependencies

1. **Recommended: Create and activate virtual environment**

   **Windows**

   *PowerShell:*

   ```powershell
   python -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

   *cmd:*

   ```bat
   python -m venv .venv
   .\.venv\Scripts\activate.bat
   ```

   **Linux / macOS:**

   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

2. **Install project dependencies (editable mode, including development dependencies like ruff, etc.)**

   ```bash
   pip install -e ".[dev]"
   ```

   Note: Dependencies are defined in `backend/pyproject.toml`; `[dev]` is an optional development toolset. If development tools are not needed, execute only `pip install -e .`.

### Database Migration

After initial setup or code updates, execute Alembic migration to synchronize table structure with current code (requires `SYNC_DATABASE_URL` etc. configured in `backend/.env.local` or the active profile file):

```bash
alembic upgrade head
```

### Start Service

With the **virtual environment activated** and (if needed) migration completed, start the API with Uvicorn hot reload (default `http://0.0.0.0:8000`):

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Recommended:** In the **repository root directory**, use startup scripts (preferentially uses Python from `backend/.venv`; on Windows without venv, tries `py -3.13` / `py -3.12` / `py -3.11` and `python` in sequence, **avoiding** `py -3` which may select "3.13 free-threaded version"):

1. **API:** `scripts\run-backend.cmd` (Windows) or `bash scripts/run-backend.sh` (Linux/macOS) — no args loads `backend/.env.local`; `run-backend dev` loads `.env.dev`
2. **Celery** (requires Redis; Beat needed for scheduled tasks): must pass profile and subcommand explicitly, e.g.:
   - `scripts\run-celery.cmd local worker` and `scripts\run-celery.cmd local beat`
   - `bash scripts/run-celery.sh local worker` / `local beat`

**Windows Celery troubleshooting**

- **Two terminals**: Scheduled tasks and “run now” require **separate Worker and Beat terminals**. Worker-only means no scheduling; Beat-only means nothing consumes the queue.
- **Worker pool**: On Windows, `run-celery.cmd` defaults to the **`threads` pool** (`MINERVA_CELERY_POOL`, `MINERVA_CELERY_CONCURRENCY`, default concurrency 4). `MINERVA_CELERY_USE_PREFORK=1` is a legacy switch equivalent to `MINERVA_CELERY_POOL=prefork`.
- **Stuck / not consuming**: Check in order:
  1. Redis reachable (startup scripts run broker preflight; or `cd backend` then `python -m app.sys.celery.service.broker_preflight`).
  2. Beat terminal shows periodic `Scheduler: Sending due task`; Worker shows `ready` and `received` for tasks.
  3. Queue depth: `redis-cli LLEN celery` (or the queue name from `CELERY_DEFAULT_QUEUE` in `.env`) keeps growing.
  4. Singleton locks: if logs show many `already_running`, inspect and remove stale `minerva:celery:scheduled_singleton:*` keys, then retry run-now.
- **Ctrl+C does not exit**: Run `scripts\stop-celery.cmd` first (kills `celery.exe` and Python trees whose command line contains `celery -A app.celery_app`); on Linux/macOS use `bash scripts/stop-celery.sh`.
- **Optional**: Run Worker/Beat inside WSL2 or Docker (Linux) with `bash scripts/run-celery.sh`, keeping API and frontend on Windows; if the broker is Redis on the host, bind `0.0.0.0` and point `CELERY_BROKER_URL` at the host IP.

Optional: `MINERVA_BACKEND_PORT` overrides API port (default 8000).

**Troubleshooting (Windows + Python 3.13):** If encountering `No module named 'pydantic_core._pydantic_core'`, it's often because the startup or `pip` is using **3.13t** (`python3.13t.exe`) while `pydantic-core` has no corresponding precompiled package. Use **standard 3.13** to create venv and install dependencies: ``py -3.13 -m venv .venv``, activate it and then ``pip install -e ".[dev]"``; or for global installation/repair use ``py -3.13 -m pip install --force-reinstall "pydantic" "pydantic-core"``, do not use ``py -3 -m pip`` at this time (may still point to 3.13t).

After successful startup, access API documentation: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs), health check: [http://127.0.0.1:8000/healthz](http://127.0.0.1:8000/healthz).

**Notes:**

- Backend loads a single `backend/.env.<profile>` (e.g. `.env.local`) based on `APP_ENV` for `DATABASE_URL`, `SYNC_DATABASE_URL` (Alembic uses synchronous URL), JWT, etc.
- For frontend integration debugging, when `APP_ENV` is dev/development/local/test, CORS allows **any port** for `http://localhost` and `http://127.0.0.1` (convenient for Vite using 5174, etc.); in production environment, tighten as needed and list only real site origins.

## 4. Start Frontend

Open another terminal and operate in the **`minerva-ui` directory**:

1. Copy frontend environment file (if not exists):

   **Windows (PowerShell):**

   ```powershell
   cd minerva-ui
   Copy-Item .env.example .env
   ```

   **Linux / macOS:**

   ```bash
   cd minerva-ui
   cp .env.dev.example .env.dev
   ```

2. Confirm `VITE_API_BASE_URL` in `.env` points to local API, for example:

   ```env
   VITE_API_BASE_URL=http://127.0.0.1:8000
   ```

3. Install dependencies and start development server:

   ```bash
   npm install
   npm run dev
   ```

4. Open the address shown in terminal in browser (usually [http://127.0.0.1:5173](http://127.0.0.1:5173)), **register/login** on the page to use connected functional modules.

5. Production build:

   ```bash
   npm run build
   ```

   Output is in `minerva-ui/dist/`, can be served by any static resource server or reverse proxy to backend.

## 5. Services and Addresses Overview

| Service | Default Address | Description |
|---------|-----------------|-------------|
| Frontend (Vite) | http://127.0.0.1:5173 | See `npm run dev` output in `minerva-ui` |
| Backend API | http://127.0.0.1:8000 | FastAPI, Swagger at `/docs` |
| PostgreSQL | 127.0.0.1:5432 | User/database/password consistent with `docker-compose.yml`, can use default connection string from `backend/.env.example` |

## Usage Instructions (Brief)

- Login/Register calls `POST /auth/login`, `/auth/register`; current workspace ID is in JWT's `wid` claim, frontend uses this to request authorized backend resources.

## Contributing

1. Fork this repository and create a new feature branch.
2. Before submitting, execute `ruff check .` in backend directory, and `npm run build` in `minerva-ui` for basic validation.
3. Merge via Pull Request.
