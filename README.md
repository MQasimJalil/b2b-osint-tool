# B2B OSINT Tool v2.0 - Web-Ready Application

A comprehensive B2B intelligence platform for discovering, analyzing, and enriching company data at scale. Now restructured as a production-ready SaaS application with FastAPI backend, modern frontend, and scalable architecture.

## 🚀 What's New in v2.0

- **Complete Architecture Redesign**: Migrated from script-based to modern web application
- **FastAPI Backend**: RESTful API with automatic documentation
- **Database Migration**: From JSONL files to MongoDB with proper schemas
- **Background Processing**: Celery integration for long-running tasks
- **Authentication**: Auth0 integration for secure user management
- **Subscription Management**: Stripe integration for billing
- **Containerization**: Docker support for easy deployment
- **CI/CD**: GitHub Actions workflows for automated testing and deployment
- **Frontend Ready**: React/Vue boilerplate structure included

## 📋 Table of Contents

- [Architecture](#architecture)
- [Project Structure](#project-structure)
- [Quick Start](#quick-start)
- [Development Setup](#development-setup)
- [Deployment](#deployment)
- [API Documentation](#api-documentation)

## 🏗️ Architecture

```
                     ┌─────────────┐
                     │   Frontend  │  (React/Vue)
                     │  (Port 3000)│
                     └──────┬──────┘
                            │ HTTP/REST
                     ┌──────▼──────┐
                     │   FastAPI   │  (Python 3.11)
                     │  Backend    │
                     │ (Port 8000) │
                     └──────┬──────┘
                            │
    ┌────────────────┬──────┴────────┬─────────────┐
    │                │               │             │
┌───▼────┐    ┌──────▼──────┐  ┌─────▼────┐  ┌─────▼──┐
│MongoDB │    │   Redis     │  │  Celery  │  │  S3/   │
│        │    │   (Cache)   │  │  Workers │  │  GCS   │
└────────┘    └─────────────┘  └──────────┘  └────────┘
```

### Tech Stack

**Backend:**
- FastAPI (Python 3.11+)
- MongoDB / PostgreSQL
- Celery + Redis (Background tasks)
- SQLAlchemy / Beanie ODM
- Pydantic (Data validation)

**Frontend:**
- React / Vue.js
- Auth0 (Authentication)
- Stripe (Payments)
- Axios (API client)

**Infrastructure:**
- Docker & Docker Compose
- [PENDING] GitHub Actions (CI/CD)
- [PENDING] AWS/GCP (Cloud deployment)
- [PENDING] Nginx (Reverse proxy)

## 📁 Project Structure

```
b2b_osint_tool/
├── backend/                      # Backend application
│   ├── app/                      # FastAPI application
│   │   ├── api/                  # API routes
│   │   │   └── v1/
│   │   │       └── endpoints/    # API endpoints
│   │   ├── core/                 # Core configuration
│   │   │   ├── config.py         # Settings management
│   │   │   └── security.py       # Authentication
│   │   ├── crud/                 # Database operations
│   │   ├── db/                   # Database models
│   │   │   ├── models.py         # SQLAlchemy/Beanie models
│   │   │   └── session.py        # DB connection
│   │   ├── schemas/              # Pydantic schemas
│   │   ├── services/             # Business logic
│   │   │   ├── discovery/        # Company discovery
│   │   │   ├── enrichment/       # Contact enrichment
│   │   │   ├── email/            # Email services
│   │   │   ├── rag/              # RAG queries
│   │   │   └── ...
│   │   └── main.py               # FastAPI entry point
│   ├── tests/                    # Backend tests
│   ├── celery_app/               # Celery configuration
│   │   ├── tasks.py              # Background tasks
│   │   └── beat.py               # Scheduled tasks
│   ├── alembic/                  # Database migrations
│   ├── Dockerfile                # Backend Docker image
│   └── requirements.txt          # Python dependencies
│
├── frontend/                     # Frontend application
│   ├── public/                   # Static assets
│   ├── src/
│   │   ├── api/                  # API client
│   │   ├── components/           # React components
│   │   ├── pages/                # Page components
│   │   └── context/              # State management
│   ├── Dockerfile                # Frontend Docker image
│   └── package.json              # Node dependencies
│
├── scripts/                      # Utility scripts
│   ├── db_init.py                # Initialize database
│   ├── db_migrate_data.py        # Migrate JSONL to DB
│   ├── seed_dev_data.py          # Seed test data
│   ├── run_celery_worker.sh      # Start Celery worker
│   └── run_celery_beat.sh        # Start Celery beat
│
├── .github/workflows/            # CI/CD pipelines
│   ├── backend_ci.yml            # Backend tests
│   ├── frontend_ci.yml           # Frontend tests
│   └── deploy.yml                # Deployment
│
├── docker-compose.yml            # Local development setup
├── .env.example                  # Environment variables template
└── README.md                     # This file
```

## Quick Start

### Using Docker (Recommended)

1. **Clone and setup:**
   ```bash
   git clone <your-repo>
   cd b2b_osint_tool
   cp .env.example .env
   # Edit .env with your API keys
   ```

2. **Start all services:**
   ```bash
   docker-compose up -d
   ```

3. **Initialize database:**
   ```bash
   docker-compose exec backend python scripts/db_init.py
   ```

4. **Access the application:**
   - API: http://localhost:8000
   - API Docs: http://localhost:8000/docs
   - Frontend: http://localhost:3000 (when ready)

### Manual Setup

**Backend:**
```bash
cd backend
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Setup environment
cp ../.env.example ../.env
# Edit .env with your configuration

# Initialize database
python ../scripts/db_init.py

# Run development server
uvicorn app.main:app --reload --port 8000
```

**Celery Workers:**
```bash
# Terminal 1: Start worker
celery -A backend.celery_app worker --loglevel=info

# Terminal 2: Start beat (optional, for scheduled tasks)
celery -A backend.celery_app beat --loglevel=info
```

**Frontend:**
```bash
cd frontend
npm install
npm start
```

## 🔧 Development Setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- MongoDB or PostgreSQL
- Redis
- Docker & Docker Compose (optional)

### Database Choice

**MongoDB (Recommended for this project):**
- Better for document-based data
- Maps well to existing JSONL structure
- Flexible schema
- Update `DATABASE_URL` in `.env`:
  ```
  DATABASE_URL=mongodb://localhost:27017/b2b_osint
  ```

### Environment Variables

Copy `.env.example` to `.env` and configure:

```bash
# Required
DATABASE_URL=mongodb://localhost:27017/b2b_osint
REDIS_URL=redis://localhost:6379/0
SECRET_KEY=<generate-secure-key>

# API Keys (as needed)
GOOGLE_SEARCH_KEY=<your-key>
ANTHROPIC_API_KEY=<your-key>
STRIPE_SECRET_KEY=<your-key>

# See .env.example for full list
```

### Running Tests

**Backend:**
```bash
cd backend
pytest tests/ -v --cov=app
```

**Frontend:**
```bash
cd frontend
npm test
```

## 📚 API Documentation

Once the backend is running, visit:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### Key API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/users/me` | GET | Get current user |
| `/api/v1/companies/` | GET, POST | List/create companies |
| `/api/v1/companies/{id}` | GET, PUT, DELETE | Company CRUD |
| `/api/v1/products/` | GET, POST | List/create products |
| `/api/v1/discovery/run` | POST | Start discovery task |
| `/api/v1/enrichment/run` | POST | Enrich contacts |
| `/api/v1/email/verify` | POST | Verify emails |
| `/api/v1/rag/query` | POST | RAG queries |

### Authentication

All endpoints (except `/health` and `/`) require authentication:

```bash
# Get token (via Auth0 or your auth flow)
export TOKEN="your-jwt-token"

# Make authenticated request
curl -H "Authorization: Bearer $TOKEN" \
  http://localhost:8000/api/v1/companies/
```


---

**Built for B2B intelligence gathering**
