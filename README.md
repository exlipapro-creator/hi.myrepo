# hi.myrepo

**Developer Operations Control Plane** — An event-driven, AI-augmented incident management system.

hi.myrepo watches, correlates, investigates, challenges its own conclusions, recommends, executes constrained procedures, verifies its work, and learns from outcomes.

## Architecture

```
APPLICATIONS
     │
     ▼
TELEMETRY / WEBHOOKS / HEARTBEATS
     │
     ▼
EVENT INGESTION
     │
     ▼
IMMUTABLE EVENT SPINE
     │
     ├──► Correlation
     ├──► Fingerprinting
     ├──► Incident State Machine
     ├──► Historical Analysis
     ├──► Policy Engine
     ├──► AI Investigation
     ├──► Runbook Engine
     ├──► Verification
     └──► Memory
             │
             ▼
       DERIVED SYSTEM STATE
             │
             ▼
       COMMAND CENTER UI
```

## Core Principles

- **Event-driven architecture** — The UI does not own system state
- **Deterministic vs Probabilistic boundary** — AI proposes, Policy authorizes, Runbooks execute
- **Bounded AI** — No unrestricted AI authority over production
- **Evidence-driven autonomy** — The system earns autonomy through evidence
- **Self-monitoring** — hi.myrepo monitors itself as its own first customer

## Autonomy Levels

| Level | Name | Description |
|-------|------|-------------|
| 0 | Observe | Receives events, detects failures, records incidents |
| 1 | Understand | Fingerprints errors, correlates, investigates |
| 2 | Recommend | Proposes runbooks, calculates confidence |
| 3 | Guarded Action | Auto-executes explicitly pre-authorized low-risk runbooks |
| 4 | Conditional Autonomy | Auto-executes when all policy conditions are satisfied |
| 5 | Never Unrestricted | AI proposes, Policy authorizes, Runbook executes |

## Tech Stack

- **Backend**: Python, FastAPI, SQLAlchemy, Alembic
- **Database**: PostgreSQL (Supabase)
- **AI Gateway**: OpenAI-compatible interface with Gemini, OpenAI, Groq
- **Auth**: JWT with role-based access control
- **Frontend**: React + Vite (planned)

## Quick Start

```bash
# 1. Clone and configure
cp .env.example .env
# Edit .env with your configuration

# 2. Start with Docker
docker-compose up -d

# 3. Apply migrations
cd backend
alembic upgrade head

# 4. Access the API
open http://localhost:8000/docs
```

## Project Structure

```
hi.myrepo/
├── backend/
│   ├── app/
│   │   ├── api/           # REST API routes
│   │   ├── core/          # Configuration
│   │   ├── events/        # Event spine & fingerprinting
│   │   ├── incidents/     # Incident state machine
│   │   ├── council/       # Engineering Council (5 agents)
│   │   ├── gateway/       # AI gateway with circuit breakers
│   │   ├── policy/        # Policy engine
│   │   ├── runbooks/      # Runbook engine
│   │   ├── verification/  # Post-remediation verification
│   │   ├── memory/        # Institutional memory
│   │   ├── telemetry/     # Client telemetry receiver
│   │   ├── security/      # Auth, SSRF protection
│   │   └── main.py        # FastAPI application
│   ├── alembic/           # Database migrations
│   ├── tests/             # Backend tests
│   └── Dockerfile
├── frontend/              # React + Vite frontend
├── workers/               # Heartbeat workers
├── database/              # Seeds, policies
├── docs/                  # Architecture documentation
└── scripts/               # Operational scripts
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/v1/auth/register` | POST | Register user |
| `/api/v1/auth/login` | POST | Login |
| `/api/v1/projects` | GET/POST | List/create projects |
| `/api/v1/events` | GET/POST | Query/ingest events |
| `/api/v1/incidents` | GET/POST | List/create incidents |
| `/v1/chat/completions` | POST | AI gateway (OpenAI-compatible) |
| `/api/v1/runbooks` | GET | List runbooks |
| `/api/v1/telemetry/ingest` | POST | Ingest telemetry |
| `/api/v1/audit` | GET | Audit logs |
| `/api/v1/memory/search` | GET | Search memory |

## Development

```bash
# Install dependencies
cd backend && pip install -r requirements.txt

# Run tests
pytest

# Run locally
uvicorn app.main:app --reload

# Generate migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head
```

## License

MIT
