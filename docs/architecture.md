# Portfolio Platform — Architecture Document

## Table of Contents

1. [Requirements Analysis](#1-requirements-analysis)
2. [Proposed Architecture](#2-proposed-architecture)
3. [Architecture Diagram](#3-architecture-diagram)
4. [Technology Choices and Justification](#4-technology-choices-and-justification)
5. [Repository Structure](#5-repository-structure)
6. [Database Architecture](#6-database-architecture)
7. [REST API Design](#7-rest-api-design)
8. [Security Model](#8-security-model)
9. [Analytics Architecture](#9-analytics-architecture)
10. [Docker Architecture](#10-docker-architecture)
11. [Home-Server Deployment Architecture](#11-home-server-deployment-architecture)
12. [Testing Strategy](#12-testing-strategy)
13. [CI/CD Strategy](#13-cicd-strategy)
14. [Learning Roadmap](#14-learning-roadmap)
15. [Development Milestones](#15-development-milestones)
16. [Risks and Open Technical Decisions](#16-risks-and-open-technical-decisions)

---

## 1. Requirements Analysis

### Functional Requirements

| Requirement | Detail |
|---|---|
| Responsive design | Mobile-first, works on all screen sizes |
| Bilingual EN/ES | Single codebase with i18n, language persists between visits |
| Project showcase | Categorized project cards, detailed case-study pages |
| Skills display | Grouped by discipline, not flat badge lists |
| Public access | Recruiters browse without accounts |
| Admin dashboard | Authenticated private analytics view |
| Analytics | First-party, privacy-conscious, aggregate stats |
| CV download | PDF download tracked as analytics event |
| SEO | Sitemap, meta tags, Open Graph, semantic HTML |

### Non-Functional Requirements

| Requirement | Detail |
|---|---|
| Dockerized | All services in containers via Docker Compose |
| Self-hostable | Deployable on a Linux home server |
| HTTPS | TLS termination via Caddy |
| Secure by default | Auth, CORS, CSP, no DB exposure, secret management |
| Maintainable | Clean code, documented decisions, modular structure |
| Testable | Backend pytest, frontend component tests, CI enforced |
| Accessible | WCAG 2.1 AA target, keyboard nav, alt text, contrast |

### Constraints

- Single developer (beginner in web development)
- Home server deployment (dynamic IP likely, possibly CGNAT)
- No Kubernetes, microservices, Redis, or message queues unless proven necessary
- PostgreSQL must never be publicly exposed
- Admin interface must require authentication

---

## 2. Proposed Architecture

### High-Level Pattern

**Monolithic multi-container application** with clear service boundaries inside Docker Compose.

```
Internet → DNS → Caddy (TLS + reverse proxy)
                    ├── Static files (frontend SPA)
                    └── /api/* → FastAPI backend → PostgreSQL
```

The frontend is a single-page application (SPA) built with React/TypeScript/Vite. In production, Vite builds static files that Caddy serves directly. The backend is a Python FastAPI application exposing a versioned REST API. PostgreSQL stores project data, translations, skills, and analytics events.

### Why monolith over microservices

A personal portfolio has modest traffic and a single developer. A monolith inside Docker with well-structured code gives clean separation without the operational complexity of service discovery, inter-service auth, distributed tracing, or separate deployments. The Docker Compose setup already provides container-level isolation.

### Why SPA over SSR

The portfolio is primarily read-heavy content for recruiters. An SPA with static asset serving gives excellent performance via Caddy's caching headers. SEO is addressed through pre-built meta tags, a sitemap, and Open Graph metadata rendered in the HTML shell. For a portfolio with fewer than 50 pages, client-side routing with React Router is sufficient. Server-side rendering (Next.js, Nuxt) introduces complexity that does not justify itself at this scale.

---

## 3. Architecture Diagram

```
┌─────────────────────────────────────────────────────────┐
│                      INTERNET                           │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  DNS Provider                                             │
│  (Cloudflare / provider DNS / dynamic DNS)               │
│  A record → public IP                                    │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Home Router / Firewall                                   │
│  Port 80 + 443 forwarded → host machine                  │
│  (or tunnel endpoint if CGNAT)                            │
└──────────────────────┬──────────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────┐
│  Host Machine (Linux)                                     │
│  Docker Engine + Docker Compose                           │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Docker Network: portfolio-net (bridge)             │  │
│  │                                                      │  │
│  │  ┌──────────────┐  ┌──────────────┐                │  │
│  │  │   Caddy       │  │   Frontend    │                │  │
│  │  │   :80/:443    │──│   (nginx)     │                │  │
│  │  │   (public)    │  │   :3000       │                │  │
│  │  │              │  │   (internal)   │                │  │
│  │  └──────┬───────┘  └──────────────┘                │  │
│  │         │ /api/*                                    │  │
│  │         ▼                                           │  │
│  │  ┌──────────────┐  ┌──────────────┐                │  │
│  │  │   Backend     │  │  PostgreSQL   │                │  │
│  │  │   FastAPI     │──│   :5432       │                │  │
│  │  │   :8000       │  │   (internal)  │                │  │
│  │  │   (internal)  │  │              │                │  │
│  │  └──────────────┘  └──────────────┘                │  │
│  └────────────────────────────────────────────────────┘  │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │  Docker Volumes:                                     │  │
│  │    portfolio_pgdata (PostgreSQL persistent data)     │  │
│  │    portfolio_caddy_data (Caddy TLS certificates)     │  │
│  │    portfolio_uploads (project images)                │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

**Data flow for a public visitor:**

1. Browser resolves DNS → public IP
2. Request hits Caddy on port 443 (TLS terminated)
3. Caddy serves static frontend files from the frontend container (nginx)
4. SPA routes (`/projects/*`, `/about`, `/skills`) are handled by React Router client-side
5. API calls (`/api/v1/*`) are proxied by Caddy to the FastAPI backend
6. Backend queries PostgreSQL and returns JSON
7. Analytics events are POSTed to `/api/v1/analytics/events`

**Data flow for admin:**

1. Admin navigates to `/admin`
2. React Router serves the admin login page
3. Credentials submitted to `/api/v1/auth/login` (HTTPS)
4. Backend validates, issues HttpOnly secure cookie
5. Admin dashboard fetches `/api/v1/admin/analytics` with cookie
6. Backend verifies session, returns aggregate analytics

---

## 4. Technology Choices and Justification

### Frontend

| Technology | Purpose | Justification |
|---|---|---|
| **React 18+** | UI framework | Largest ecosystem, excellent for component-based UI, massive hiring-market relevance |
| **TypeScript** | Type safety | Catches bugs early, improves IDE support, demonstrates professional practice |
| **Vite** | Build tool | Fast HMR, simple config, modern standard, excellent DX |
| **React Router v6** | Client-side routing | Standard for React SPAs, file-based route convention available |
| **i18next + react-i18next** | Internationalization | Mature i18n library, supports interpolation, lazy loading, language persistence via localStorage |
| **CSS Modules** | Styling | Scoped styles without extra build dependency, good for learning CSS fundamentals |

### Backend

| Technology | Purpose | Justification |
|---|---|---|
| **Python 3.12+** | Language | Already known to the developer, strong ecosystem |
| **FastAPI** | Web framework | Async by default, automatic OpenAPI docs, Pydantic validation, modern Python standard |
| **Pydantic v2** | Data validation | Integrated with FastAPI, excellent for request/response models, serialization |
| **SQLAlchemy 2.0+** | ORM | Industry-standard Python ORM, works with async, Alembic integration |
| **Alembic** | Database migrations | Standard for SQLAlchemy, version-controlled schema changes |
| **uvicorn** | ASGI server | Production-grade async server for FastAPI |
| **bcrypt (via passlib)** | Password hashing | Proven password hashing algorithm, handles salting automatically |
| **python-jose** | JWT/cookie tokens | Token generation for admin sessions |
| **python-multipart** | Form/file parsing | Required for file uploads in FastAPI |

### Database

| Technology | Purpose | Justification |
|---|---|---|
| **PostgreSQL 16** | Primary database | Robust, supports JSON for flexible fields, excellent ecosystem, handles analytics aggregation well |

### Infrastructure

| Technology | Purpose | Justification |
|---|---|---|
| **Docker** | Containerization | Reproducible environments, isolate services, standard industry tool |
| **Docker Compose** | Multi-container orchestration | Simple local dev, sufficient for 4 containers, no need for Kubernetes |
| **Caddy** | Reverse proxy + TLS | Automatic HTTPS via Let's Encrypt, simple config, modern alternative to Nginx for this use case |
| **nginx** | Frontend static serving (inside container) | Efficient static file serving, gzip, caching headers. Alternative: Caddy can serve static files directly — **Decision: use Caddy for everything** to reduce container count |

### Testing

| Technology | Purpose | Justification |
|---|---|---|
| **pytest** | Backend testing | Python standard, extensive plugin ecosystem |
| **pytest-asyncio** | Async test support | Required for async FastAPI endpoint testing |
| **httpx** | Test HTTP client | Async-compatible, works with FastAPI TestClient |
| **Vitest** | Frontend testing | Fast, Vite-native, compatible with React Testing Library |
| **@testing-library/react** | Component testing | Tests components from user perspective, not implementation details |

### CI/CD

| Technology | Purpose | Justification |
|---|---|---|
| **GitHub Actions** | CI pipeline | Free for public repos, integrated with GitHub, YAML-based |

---

## 5. Repository Structure

```
portfolio/
├── frontend/                          # React + TypeScript SPA
│   ├── public/                        # Static assets (favicon, robots.txt, sitemap.xml)
│   │   ├── favicon.ico
│   │   ├── robots.txt
│   │   └── sitemap.xml
│   ├── src/
│   │   ├── main.tsx                   # Application entry point
│   │   ├── App.tsx                    # Root component, router setup
│   │   ├── vite-env.d.ts
│   │   ├── components/                # Shared/reusable components
│   │   │   ├── Layout/
│   │   │   │   ├── Header.tsx
│   │   │   │   ├── Footer.tsx
│   │   │   │   └── Layout.tsx
│   │   │   ├── LanguageSwitcher/
│   │   │   │   └── LanguageSwitcher.tsx
│   │   │   ├── ProjectCard/
│   │   │   │   └── ProjectCard.tsx
│   │   │   ├── SkillCategory/
│   │   │   │   └── SkillCategory.tsx
│   │   │   └── SEO/
│   │   │       └── SEOHead.tsx
│   │   ├── pages/                     # Route-level components
│   │   │   ├── Home/
│   │   │   │   └── Home.tsx
│   │   │   ├── About/
│   │   │   │   └── About.tsx
│   │   │   ├── Skills/
│   │   │   │   └── Skills.tsx
│   │   │   ├── Projects/
│   │   │   │   ├── ProjectList.tsx
│   │   │   │   └── ProjectDetail.tsx
│   │   │   ├── Contact/
│   │   │   │   └── Contact.tsx
│   │   │   ├── admin/
│   │   │   │   ├── AdminLogin.tsx
│   │   │   │   └── AdminDashboard.tsx
│   │   │   └── NotFound.tsx
│   │   ├── hooks/                     # Custom React hooks
│   │   │   ├── useAnalytics.ts
│   │   │   └── useProjects.ts
│   │   ├── services/                  # API client functions
│   │   │   └── api.ts
│   │   ├── i18n/                      # Internationalization
│   │   │   ├── index.ts              # i18next config
│   │   │   ├── en.json               # English translations
│   │   │   └── es.json               # Spanish translations
│   │   ├── types/                     # TypeScript type definitions
│   │   │   └── index.ts
│   │   ├── utils/                     # Utility functions
│   │   └── styles/                    # Global styles, CSS variables
│   │       └── global.css
│   ├── index.html                     # HTML shell (meta tags, OG, title)
│   ├── Dockerfile                     # Multi-stage build
│   ├── nginx.conf                     # Static file serving config
│   ├── package.json
│   ├── tsconfig.json
│   ├── vite.config.ts
│   └── vitest.config.ts
│
├── backend/                           # FastAPI application
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py                    # FastAPI app factory, middleware, CORS
│   │   ├── config.py                  # Settings via pydantic-settings (env vars)
│   │   ├── database.py                # SQLAlchemy engine, session management
│   │   ├── models/                    # SQLAlchemy ORM models
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── skill.py
│   │   │   ├── analytics.py
│   │   │   └── admin.py
│   │   ├── schemas/                   # Pydantic request/response schemas
│   │   │   ├── __init__.py
│   │   │   ├── project.py
│   │   │   ├── skill.py
│   │   │   ├── analytics.py
│   │   │   └── auth.py
│   │   ├── routes/                    # API route modules
│   │   │   ├── __init__.py
│   │   │   ├── projects.py
│   │   │   ├── skills.py
│   │   │   ├── analytics.py
│   │   │   ├── auth.py
│   │   │   └── admin.py
│   │   ├── services/                  # Business logic layer
│   │   │   ├── __init__.py
│   │   │   ├── project_service.py
│   │   │   ├── analytics_service.py
│   │   │   └── auth_service.py
│   │   ├── middleware/                 # Custom middleware
│   │   │   ├── __init__.py
│   │   │   └── security.py
│   │   └── utils/                     # Helpers
│   │       ├── __init__.py
│   │       └── translations.py
│   ├── alembic/                       # Database migrations
│   │   ├── env.py
│   │   ├── script.py.mako
│   │   └── versions/                  # Migration files
│   ├── alembic.ini
│   ├── tests/
│   │   ├── __init__.py
│   │   ├── conftest.py               # Fixtures, test DB setup
│   │   ├── test_projects.py
│   │   ├── test_analytics.py
│   │   ├── test_auth.py
│   │   └── test_skills.py
│   ├── Dockerfile                     # Multi-stage build
│   ├── requirements.txt
│   ├── requirements-dev.txt           # Dev/test dependencies
│   └── pyproject.toml                 # Project config, pytest settings
│
├── infrastructure/
│   ├── caddy/
│   │   ├── Caddyfile                   # Caddy reverse proxy config
│   │   └── caddy.env
│   └── nginx/
│       └── default.conf               # Frontend nginx config (if used)
│
├── docs/
│   ├── architecture.md                # This document
│   ├── development.md                 # Local development guide
│   ├── deployment.md                  # Production deployment guide
│   ├── database.md                    # Schema documentation
│   ├── api.md                         # API reference
│   ├── security.md                    # Security model documentation
│   ├── analytics.md                   # Analytics system documentation
│   ├── testing.md                     # Testing strategy and guide
│   └── troubleshooting.md            # Common issues and fixes
│
├── scripts/
│   ├── backup.sh                      # PostgreSQL backup script
│   ├── restore.sh                     # Database restore script
│   └── seed.py                        # Database seeding for dev
│
├── .github/
│   └── workflows/
│       └── ci.yml                     # GitHub Actions CI pipeline
│
├── docker-compose.yml                 # Production compose
├── docker-compose.dev.yml             # Development overrides
├── .env.example                       # Environment variable template
├── .gitignore
└── README.md
```

### Directory Responsibilities

| Directory | Responsibility |
|---|---|
| `frontend/src/pages/` | One directory per route-level page component. Each contains the page component and any page-specific sub-components. |
| `frontend/src/components/` | Shared components used across multiple pages (Header, Footer, ProjectCard, etc.) |
| `frontend/src/hooks/` | Custom React hooks for data fetching, analytics tracking, and state management. |
| `frontend/src/services/` | API client abstraction. All backend calls go through `api.ts`, centralizing base URL, error handling, and auth headers. |
| `frontend/src/i18n/` | i18next configuration and translation JSON files. One file per supported language. |
| `frontend/src/types/` | TypeScript interfaces and type aliases shared across the frontend. |
| `backend/app/routes/` | FastAPI router modules. One file per domain (projects, skills, analytics, auth, admin). |
| `backend/app/models/` | SQLAlchemy ORM model definitions. One file per entity. |
| `backend/app/schemas/` | Pydantic models for request validation and response serialization. Mirrors models but with API-specific fields. |
| `backend/app/services/` | Business logic extracted from routes. Handles database queries, computation, and orchestration. |
| `infrastructure/` | Reverse proxy configuration files (Caddy, optionally nginx). |
| `docs/` | Project documentation explaining architecture, setup, and decisions. |
| `scripts/` | Operational scripts for backup, restore, and development seeding. |

---

## 6. Database Architecture

### Translation Strategy Decision

**Option A: Translation tables (normalized)**
```
projects → project_translations (project_id, locale, title, description, ...)
```

**Option B: Column suffixes (denormalized)**
```
projects → title_en, title_es, description_en, description_es
```

**Decision: Option A — Translation tables.**

Tradeoff analysis:

| Factor | Translation Tables (A) | Column Suffixes (B) |
|---|---|---|
| Adding a new language | Add rows, zero schema migration | Add columns, requires migration |
| Query complexity | JOIN required | Simple SELECT |
| Data integrity | Enforced by FK | No referential integrity per locale |
| Admin editing | More complex UI | Simpler UI |
| Scalability | O(1) columns per new language | O(n) columns per new language |
| Performance | Marginal JOIN overhead | Slightly faster reads |

For a portfolio with 2 languages today but potentially more later, and with modest data volume (tens of projects, not millions), translation tables are the better long-term choice. The JOIN overhead is negligible at this scale. Adding a third language requires inserting rows, not altering tables.

### Entity-Relationship Diagram

```
┌─────────────────────┐       ┌──────────────────────────────┐
│    projects          │       │    project_translations       │
├─────────────────────┤       ├──────────────────────────────┤
│ id          PK UUID │◄──┐   │ id              PK UUID      │
│ slug        UK TEXT │   │   │ project_id      FK UUID ─────│──┐
│ category    ENUM    │   │   │ locale       ENUM(en,es)    │  │
│ status      ENUM    │   │   │ title          TEXT NOT NULL  │  │
│ github_url  TEXT?   │   │   │ short_desc     TEXT NOT NULL  │  │
│ demo_url    TEXT?   │   │   │ overview       TEXT           │  │
│ featured    BOOL    │   │   │ problem        TEXT           │  │
│ sort_order  INT     │   │   │ requirements   TEXT           │  │
│ created_at  TIMESTZ │   │   │ architecture   TEXT           │  │
│ updated_at  TIMESTZ │   │   │ implementation TEXT           │  │
└─────────────────────┘   │   │ decisions      TEXT           │  │
                          │   │ challenges     TEXT           │  │
                          │   │ testing_desc   TEXT           │  │
                          │   │ results        TEXT           │  │
                          │   │ lessons        TEXT           │  │
                          │   │ locale    UK+FK (project_id, │  │
                          │   │                         locale)│  │
                          │   └──────────────────────────────┘  │
                          │                                      │
                          │   ┌──────────────────────────────┐  │
                          │   │    project_images             │  │
                          │   ├──────────────────────────────┤  │
                          │   │ id              PK UUID      │  │
                          │   │ project_id      FK UUID ─────│──┘
                          │   │ url             TEXT NOT NULL │
                          │   │ alt_text        TEXT          │
                          │   │ is_hero         BOOL          │
                          │   │ sort_order      INT           │
                          │   │ created_at      TIMESTZ       │
                          │   └──────────────────────────────┘
                          │
                          │   ┌──────────────────────────────┐
                          │   │    project_technologies      │
                          │   ├──────────────────────────────┤
                          │   │ project_id      FK UUID ─────│──┐
                          │   │ technology_id   FK UUID ─────│──│──┐
                          │   └──────────────────────────────┘  │  │
                          │                                     │  │
                          │   ┌──────────────────────────────┐  │  │
                          │   │    technologies              │  │  │
                          │   ├──────────────────────────────┤  │  │
                          │   │ id          PK UUID          │  │  │
                          │   │ name        TEXT UNIQUE      │  │  │
                          │   │ category    ENUM             │  │  │
                          │   │ icon_url    TEXT?            │  │  │
                          │   └──────────────────────────────┘  │  │
                          │                                     │  │
                          │   ┌──────────────────────────────┐  │  │
                          │   │    skills                    │  │  │
                          │   ├──────────────────────────────┤  │  │
                          │   │ id          PK UUID          │  │  │
                          │   │ name        TEXT UNIQUE      │  │  │
                          │   │ category    ENUM             │  │  │
                          │   │ featured_rank INT?           │  │  │
                          │   │ sort_order  INT              │  │  │
                          │   └──────────────────────────────┘  │
                          │                                     │
                          │   ┌──────────────────────────────┐  │
                          │   │    analytics_events          │  │  │
                          │   ├──────────────────────────────┤  │  │
                          │   │ id              PK BIGINT    │  │  │
                          │   │ event_type      ENUM         │  │  │
                          │   │ session_id      TEXT         │  │  │
                          │   │ project_id      FK UUID? ────│──┘
                          │   │ metadata        JSONB?       │
                          │   │ locale          ENUM?        │
                          │   │ user_agent_hash TEXT?        │
                          │   │ ip_hash         TEXT?        │
                          │   │ created_at      TIMESTZ      │
                          │   └──────────────────────────────┘
                          │
                          │   ┌──────────────────────────────┐
                          │   │    admin_users                │
                          │   ├──────────────────────────────┤
                          │   │ id              PK UUID      │
                          │   │ username        UK TEXT      │
                          │   │ password_hash   TEXT         │
                          │   │ created_at      TIMESTZ      │
                          │   │ last_login      TIMESTZ?     │
                          │   └──────────────────────────────┘
```

### Enumerations

```python
# project_translations.locale
enum Locale { en, es }

# projects.category
enum ProjectCategory {
    featured, software, embedded, electronics,
    robotics, ml_data, cybersecurity,
    devops_infra, academic_research
}

# projects.status — NOT NULL, defaults to `complete`
enum ProjectStatus { complete, in_development }

# technologies.category
enum TechCategory {
    programming, embedded_systems, electronics,
    automation, web_dev, ml_data,
    cybersecurity, linux_devops, engineering_tools
}

# skills.category — declaration order IS the on-page section order
# (Postgres sorts an enum column by the type's declared order).
enum SkillCategory {
    programming, embedded_systems, hardware_design,
    robotics, networks, web_backend,
    linux_devops, data_ml
}

# analytics_events.event_type
enum AnalyticsEventType {
    page_view, project_view, project_link_click,
    github_click, cv_download, contact_click,
    language_change
}
```

**Why `skills` has no `proficiency`.** It did, on a 1–5 self-assessed scale
rendered as bars. A self-assessed 3/5 beside "SolidWorks" is not a fact a
reader can act on, and it invited a comparison the data could not support — so
the column was dropped rather than hidden, and the projects carry the evidence
of depth instead. `icon_url` went with it: never populated, and icons now live
in the frontend's `SkillBadge` map, where changing one is an edit rather than a
migration.

`featured_rank` replaced both. One nullable integer carries two facts: NULL
means the skill is not in the page's opening Featured row, and any value is its
position in that row. A "featured" *category* was the obvious alternative and is
wrong — `skills.name` is UNIQUE, so it would require Python and Docker to exist
as duplicate rows.

**Why `projects.status` exists.** A null `github_url` was carrying two very
different meanings — *the work is private or offline* versus *the work isn't
finished yet* — and the UI could only render the absence, never the reason. A
visitor reading a project card with no repo link had no way to tell an
unpublished repo from an unwritten one. `in_development` says the second one
out loud: the card and detail page get an explicit badge, and the detail page
adds a short note that the write-up and repository will follow as the work
advances. The default is `complete`, so a project only declares a status when
it is *not* finished.

### Key Constraints and Indexes

```sql
-- projects
ALTER TABLE projects ADD CONSTRAINT uq_projects_slug UNIQUE (slug);
CREATE INDEX idx_projects_category ON projects (category);
CREATE INDEX idx_projects_featured ON projects (featured) WHERE featured = true;
CREATE INDEX idx_projects_sort_order ON projects (sort_order);

-- project_translations
ALTER TABLE project_translations
  ADD CONSTRAINT uq_project_locale UNIQUE (project_id, locale);
CREATE INDEX idx_pt_locale ON project_translations (locale);

-- technologies
ALTER TABLE technologies ADD CONSTRAINT uq_technologies_name UNIQUE (name);
CREATE INDEX idx_technologies_category ON technologies (category);

-- skills
ALTER TABLE skills ADD CONSTRAINT uq_skills_name UNIQUE (name);
CREATE INDEX idx_skills_category ON skills (category);

-- analytics_events
CREATE INDEX idx_analytics_event_type ON analytics_events (event_type);
CREATE INDEX idx_analytics_created_at ON analytics_events (created_at);
CREATE INDEX idx_analytics_project_id ON analytics_events (project_id)
  WHERE project_id IS NOT NULL;
CREATE INDEX idx_analytics_session ON analytics_events (session_id);

-- For time-range queries (daily aggregation)
CREATE INDEX idx_analytics_created_date
  ON analytics_events (DATE(created_at), event_type);

-- admin_users
ALTER TABLE admin_users ADD CONSTRAINT uq_admin_username UNIQUE (username);
```

### Migration Strategy

Alembic manages all schema changes. Workflow:

1. Modify SQLAlchemy models in `backend/app/models/`
2. Run `alembic revision --autogenerate -m "description"`
3. Review generated migration in `alembic/versions/`
4. Test migration up and down: `alembic upgrade head` / `alembic downgrade -1`
5. Commit both model changes and migration file

In production, migrations run as part of the backend container startup or via a one-shot init container.

---

## 7. REST API Design

### Base URL

```
https://<domain>/api/v1
```

### Public Endpoints

#### `GET /api/v1/projects`

Returns all published projects with translations for the requested locale.

**Query parameters:**
- `locale` (optional, default: `en`) — `en` or `es`
- `category` (optional) — Filter by category
- `featured` (optional) — Boolean filter

**Response:**
```json
{
  "projects": [
    {
      "id": "uuid",
      "slug": "sumobot",
      "category": "robotics",
      "status": "complete",
      "github_url": "https://github.com/user/sumobot",
      "demo_url": null,
      "featured": true,
      "title": "SumoBot Competition Robot",
      "short_desc": "Autonomous sumo robot with sensor fusion...",
      "thumbnail_url": "/uploads/images/sumobot-thumb.webp",
      "technologies": ["Arduino", "C++", "Python", "PCB Design"],
      "images_count": 12
    }
  ]
}
```

#### `GET /api/v1/projects/{slug}`

Returns full project detail including translations and images.

**Response:**
```json
{
  "id": "uuid",
  "slug": "sumobot",
  "category": "robotics",
  "status": "complete",
  "github_url": "https://github.com/user/sumobot",
  "demo_url": null,
  "featured": true,
  "title": "SumoBot Competition Robot",
  "short_desc": "Autonomous sumo robot...",
  "overview": "Full overview text...",
  "problem": "Problem description...",
  "requirements": "...",
  "architecture": "...",
  "implementation": "...",
  "decisions": "...",
  "challenges": "...",
  "testing_desc": "...",
  "results": "...",
  "lessons": "...",
  "technologies": [
    { "name": "Arduino", "category": "embedded_systems" },
    { "name": "C++", "category": "programming" }
  ],
  "images": [
    {
      "url": "/uploads/images/sumobot-hero.webp",
      "alt_text": "SumoBot front view",
      "is_hero": true
    }
  ]
}
```

#### `GET /api/v1/skills`

Returns all skills grouped by category, plus the curated Featured row.

Skill names are technology names — they are not translated, so this endpoint
takes no `locale`. Only the *category headings* are localised, and those live in
the frontend i18n bundles under `skills.categories`.

`featured` is a flat list rather than a group: it is a cross-section of the
categories below, so giving it a group shape would mean inventing a
`SkillCategory` value that no row actually holds.

**Response:**
```json
{
  "featured": [
    { "name": "Python" },
    { "name": "C++" },
    { "name": "ESP32" }
  ],
  "categories": [
    {
      "category": "programming",
      "skills": [
        { "name": "Python" },
        { "name": "C" },
        { "name": "C++" }
      ]
    }
  ]
}
```

#### `POST /api/v1/analytics/events`

Records an analytics event.

**Request:**
```json
{
  "event_type": "project_view",
  "session_id": "abc123",
  "project_slug": "sumobot",
  "locale": "en",
  "metadata": {}
}
```

**Response:**
```json
{ "status": "recorded" }
```

**Rate limiting:** Max 60 events per session per minute (tracked server-side per session_id).

#### `GET /api/v1/health`

Health check endpoint.

**Response:**
```json
{
  "status": "healthy",
  "database": "connected",
  "version": "1.0.0",
  "timestamp": "2026-08-17T12:00:00Z"
}
```

### Authenticated Endpoints

#### `POST /api/v1/auth/login`

Admin login.

**Request:**
```json
{
  "username": "admin",
  "password": "..."
}
```

**Response:**
```json
{ "status": "authenticated" }
```
Sets `HttpOnly`, `Secure`, `SameSite=Strict` session cookie.

**Security:** Rate-limited to 5 attempts per IP per 15-minute window. Exponential backoff on repeated failures.

#### `POST /api/v1/auth/logout`

Destroys session cookie.

**Response:**
```json
{ "status": "logged_out" }
```

#### `GET /api/v1/admin/analytics` (Authenticated)

Returns aggregate analytics for the dashboard.

**Query parameters:**
- `days` (optional, default: `30`) — Time range
- `granularity` (optional, default: `day`) — `day`, `week`, `month`

**Response:**
```json
{
  "summary": {
    "total_page_views": 1523,
    "unique_sessions": 412,
    "total_project_views": 876,
    "github_clicks": 89,
    "cv_downloads": 34,
    "contact_clicks": 21,
    "project_link_clicks": 17,
    "language_changes": 63,
    "total_events": 2623,
    "language_distribution": { "en": 340, "es": 72 }
  },
  "engagement": {
    "bounce_rate": 0.41,
    "pages_per_session": 3.7,
    "avg_events_per_session": 6.4,
    "avg_session_duration_seconds": 142.5,
    "returning_sessions": 38
  },
  "timeseries": [
    { "date": "2026-08-01", "page_views": 52, "unique_sessions": 14, "unique_visitors": 12 }
  ],
  "top_projects": [
    { "slug": "sumobot", "title": "SumoBot", "views": 234 }
  ],
  "top_pages": [
    { "path": "/projects", "views": 310, "unique_sessions": 180 }
  ],
  "event_breakdown": [
    { "event_type": "page_view", "count": 1523 }
  ],
  "device_breakdown": [
    { "device_class": "desktop", "sessions": 260 }
  ],
  "referrers": [
    { "host": "linkedin.com", "sessions": 74 },
    { "host": "direct", "sessions": 210 }
  ],
  "hourly_activity": [
    { "hour": 0, "events": 12 }
  ],
  "recent_events": [
    { "event_type": "project_view", "project_slug": "sumobot", "timestamp": "..." }
  ]
}
```

`event_breakdown` always carries all seven event types and `hourly_activity`
all 24 hours, zero-filled — see §9. `unique_visitors` counts distinct `ip_hash`
in the bucket; the hash salt rotates daily, so it is exact at `day` granularity
(the only one the dashboard requests) and becomes visitor-*days* at `week` or
`month`. `device_breakdown` and `referrers` report only over the window where
those columns were being collected, so both are empty on a database whose
events all predate migration `d7a5e91c2f48`.

#### `GET /api/v1/admin/analytics/raw` (Authenticated)

Returns raw event data for admin export/debugging.

### Endpoint Authorization Summary

| Endpoint | Public | Auth Required |
|---|---|---|
| `GET /api/v1/projects` | Yes | No |
| `GET /api/v1/projects/{slug}` | Yes | No |
| `GET /api/v1/skills` | Yes | No |
| `POST /api/v1/analytics/events` | Yes | No |
| `GET /api/v1/health` | Yes | No |
| `POST /api/v1/auth/login` | Yes | No (but rate-limited) |
| `POST /api/v1/auth/logout` | No | Yes |
| `GET /api/v1/admin/analytics` | No | Yes |
| `GET /api/v1/admin/analytics/raw` | No | Yes |

---

## 8. Security Model

### Threat Model

| Threat | Risk | Mitigation |
|---|---|---|
| **Credential exposure** | High | bcrypt hashing (cost factor 12), environment variables, .gitignore, never commit secrets |
| **Brute-force auth** | High | Rate limiting (5 attempts/IP/15min), exponential backoff, logging failed attempts |
| **SQL injection** | High | SQLAlchemy ORM parameterized queries, Pydantic input validation |
| **XSS** | Medium | React auto-escapes JSX output, Content Security Policy headers via Caddy, sanitize any user-generated HTML |
| **CSRF** | Medium | SameSite=Strict cookies, origin checking on auth endpoints |
| **CORS misconfiguration** | Medium | Explicit allowed origins in FastAPI config, no wildcard in production |
| **Dependency vulnerabilities** | Medium | `npm audit`, `pip-audit` in CI, Dependabot/Renovate |
| **Database exposure** | High | PostgreSQL bound to Docker network only, never exposed to host ports in production |
| **Secret leakage in logs** | Medium | Structured logging, no passwords/tokens in log output, log level configuration |
| **Container escape** | Low | Run containers as non-root user where possible, keep images updated |
| **File upload abuse** | Medium | Validate file type/size server-side, store uploads outside webroot, scan uploaded files |
| **DoS** | Low | Caddy request limits, backend rate limiting, reasonable payload size limits |
| **Man-in-the-middle** | High | TLS via Caddy/Let's Encrypt, HSTS header, no mixed content |
| **Backup data exposure** | Medium | Encrypted backup storage, restrict backup file permissions |

### Authentication Architecture

- **Mechanism:** Server-side session stored in a signed, HttpOnly, Secure cookie
- **NOT JWT in localStorage** — JWT in localStorage is vulnerable to XSS. A server-side session with a random session ID in an HttpOnly cookie is more secure for this use case.
- **Session storage:** PostgreSQL table `admin_sessions` with session_id, user_id, expiry, created_at
- **Session duration:** 24 hours, renewable on activity
- **Password hashing:** bcrypt with work factor 12 (configurable)
- **Admin user seeding:** Single admin user created via `scripts/seed.py` or Alembic migration

### Cookie Settings

```python
session_cookie = {
    "httponly": True,       # Not accessible via JavaScript
    "secure": True,         # Only sent over HTTPS
    "samesite": "strict",   # No cross-site sending
    "path": "/",
    "max_age": 86400        # 24 hours
}
```

### Security Headers (via Caddy)

```
Strict-Transport-Security: max-age=31536000; includeSubDomains
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
Referrer-Policy: strict-origin-when-cross-origin
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'
Permissions-Policy: camera=(), microphone=(), geolocation=()
```

### Secret Management

All secrets stored in `.env` file (never committed, template in `.env.example`):

```
DATABASE_URL=postgresql://user:pass@localhost:5432/portfolio
ADMIN_USERNAME=admin
ADMIN_PASSWORD=changeme
SESSION_SECRET_KEY=changeme-random-64-char-string
CORS_ALLOWED_ORIGINS=https://yourdomain.com
```

---

## 9. Analytics Architecture

### Design Principles

1. **First-party only** — No Google Analytics, no third-party tracking scripts
2. **No PII** — No names, emails, IPs (only hashed for duplicate suppression), no full user agents
3. **Aggregate-first** — Dashboard shows summaries; raw data is ephemeral
4. **Bot-resistant** — Session-based deduplication, rate limiting, minimum time between identical events
5. **Privacy-compliant** — GDPR/CCPA friendly by design

### Event Schema

```sql
CREATE TABLE analytics_events (
    id              BIGSERIAL PRIMARY KEY,
    event_type      analytics_event_type NOT NULL,
    session_id      TEXT NOT NULL,       -- random client-generated ID
    project_id      UUID REFERENCES projects(id),
    project_slug    TEXT,                -- denormalized for query convenience
    locale          locale_type,
    metadata        JSONB,              -- allowlisted event-specific data
    user_agent_hash TEXT,               -- SHA-256 truncated for dedup
    ip_hash         TEXT,               -- SHA-256 truncated for dedup
    device_class    TEXT,               -- 'mobile'|'tablet'|'desktop'|'unknown'
    referrer_host   TEXT,               -- hostname only, never a path or query
    created_at      TIMESTAMPTZ DEFAULT now()
);
```

`metadata` is **not** free-form despite the JSONB type. `backend/app/schemas/analytics.py`
holds a key allowlist (`path`, `from`, `to`, `link`, `ref`) with a regex per key;
anything else is dropped rather than rejected, because the endpoint is a
fire-and-forget beacon that cannot react to a 4xx. Adding a tracked dimension
means editing that file, which is the review checkpoint principle 2 needs.

**The last two columns are derived, and both are narrower than what they are
derived from** (migration `d7a5e91c2f48`):

- `device_class` is computed from the User-Agent at write time by
  `analytics_service.classify_device` and is one of four fixed strings. The UA
  itself is still only ever stored as a truncated hash. Four buckets is
  deliberately coarser than a UA-parsing library would give — browser and
  version would be a fingerprinting surface, and "does the layout need to work
  on a phone" is fully answered by four.
- `referrer_host` is the `hostname` of `document.referrer` and nothing else.
  `hooks/useAnalytics.ts` parses it client-side so the path and query string —
  where a search term or an address would live — never leave the browser, and
  the allowlist pattern rejects any value containing `/`, `?` or `:` as a
  second line of defence.

**NULL in `device_class` is load-bearing.** Every row the instrumented build
writes carries a value, down to the literal `'unknown'` for a request with no UA
header. So `device_class IS NULL` identifies exactly the rows written before the
column existed, and the device and referrer aggregations filter on it — without
that filter, a year of pre-existing rows would be reported as an enormous
"unknown device, direct traffic" cohort that really means "not measured".

**No synthetic rows.** `scripts/seed.py` used to plant ~500 fabricated events so
this dashboard had a shape to render before the recording pipeline existed. It
no longer does, and migration `d7a5e91c2f48` deletes the ones it planted
(`ip_hash IS NULL` identifies them exactly: `record_event` hashes the client IP
unconditionally, the seed set neither hash). Every number the admin dashboard
shows is now earned by a real visit.

### Client-Side Implementation

```typescript
// hooks/useAnalytics.ts
// Generates a random session_id stored in localStorage
// On page load, sends PAGE_VIEW event
// On project view, sends PROJECT_VIEW
// On link clicks, sends appropriate CLICK event
// Includes session_id and locale with every event
```

### Duplicate Prevention

| Mechanism | Implementation |
|---|---|
| Session ID | Client generates UUID, stores in localStorage, sends with events. Same session = same ID |
| Event throttling | Client minimum 1-second gap between identical events (e.g., no double page_view) |
| Server-side dedup | Within a session, ignore duplicate `page_view` for same path within 30 seconds |
| Bot filtering | Ignore events from known bot user-agent strings; ignore events with no session_id |
| IP hashing | SHA-256 of IP + daily salt for approximate unique counting without storing IPs |

### Aggregation Queries

The admin dashboard runs pre-aggregated queries, not raw event scans. All of
them live in `backend/app/services/analytics_service.py` and are assembled into
one `AdminAnalyticsResponse` by `get_admin_analytics`.

```sql
-- Daily page views
SELECT DATE(created_at) as day, COUNT(*) as views
FROM analytics_events
WHERE event_type = 'page_view'
  AND created_at > now() - INTERVAL '30 days'
GROUP BY day ORDER BY day;

-- Unique sessions (approximate)
SELECT COUNT(DISTINCT session_id) as unique_sessions
FROM analytics_events
WHERE event_type = 'page_view'
  AND created_at > now() - INTERVAL '30 days';

-- Most viewed projects
SELECT project_slug, COUNT(*) as views
FROM analytics_events
WHERE event_type = 'project_view'
GROUP BY project_slug
ORDER BY views DESC LIMIT 10;

-- Language distribution
SELECT locale, COUNT(DISTINCT session_id) as sessions
FROM analytics_events
WHERE event_type = 'page_view'
GROUP BY locale;

-- Top pages. `metadata.path` had been written on every page_view since the
-- recording pipeline shipped and read by nothing: the dashboard could say how
-- many pages were viewed, but not which ones.
SELECT metadata->>'path' as path, COUNT(*) as views,
       COUNT(DISTINCT session_id) as sessions
FROM analytics_events
WHERE event_type = 'page_view' AND metadata->>'path' IS NOT NULL
GROUP BY path ORDER BY views DESC LIMIT 10;

-- Session shape. Everything folds to one row per session FIRST, then
-- aggregates those rows — averaging over events instead would weight a visitor
-- who read ten pages ten times as heavily as one who read a single page, and
-- the point of a session metric is that each visit counts once.
WITH sessions AS (
    SELECT session_id, COUNT(*) as events,
           COUNT(*) FILTER (WHERE event_type = 'page_view') as page_views,
           MIN(created_at) as first_seen, MAX(created_at) as last_seen,
           COUNT(DISTINCT date_trunc('day', created_at)) as active_days
    FROM analytics_events
    WHERE created_at > now() - INTERVAL '30 days'
    GROUP BY session_id
)
SELECT COUNT(*) FILTER (WHERE events = 1 AND page_views = 1)::float
         / NULLIF(COUNT(*), 0)                              as bounce_rate,
       AVG(events)                                          as events_per_session,
       AVG(EXTRACT(epoch FROM last_seen - first_seen))
         FILTER (WHERE events > 1)                          as avg_duration_s,
       COUNT(*) FILTER (WHERE active_days > 1)              as returning
FROM sessions;

-- Acquisition + device, one row per session. The referrer rides only a
-- session's first page_view, so grouping events instead of sessions would file
-- every later click under 'direct' and bury the real source under our own
-- traffic. The device_class IS NOT NULL filter is the collection-window guard
-- described above.
WITH dims AS (
    SELECT session_id, MAX(device_class) as device_class,
           MAX(referrer_host) as referrer_host
    FROM analytics_events
    WHERE created_at > now() - INTERVAL '30 days' AND device_class IS NOT NULL
    GROUP BY session_id
)
SELECT COALESCE(referrer_host, 'direct') as host, COUNT(*) as sessions
FROM dims GROUP BY host ORDER BY sessions DESC LIMIT 10;
```

**Zero-filling is part of the contract, not cosmetics.** `event_breakdown`
returns all seven event types and `hourly_activity` all 24 hours, present or
not. A type missing from a list is indistinguishable from a type whose
instrumentation broke; an explicit `0` says "we asked, and nobody did this".
That distinction is why `project_link_click` and `language_change` went
unnoticed for as long as they did — both were recorded from the start, and the
summary simply counted five of the seven types.

### Data Retention

- Raw events older than 90 days are archived or deleted
- Aggregated daily summaries are retained indefinitely (future optimization)
- First implementation: delete raw events > 90 days via scheduled script

---

## 10. Docker Architecture

### Production Compose (`docker-compose.yml`)

```yaml
services:
  caddy:
    image: caddy:2-alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./infrastructure/caddy/Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
      - caddy_config:/config
    depends_on:
      - frontend
      - backend
    restart: unless-stopped
    networks:
      - portfolio-net

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
    # Served internally, not exposed to host
    expose:
      - "80"
    restart: unless-stopped
    networks:
      - portfolio-net

  backend:
    build:
      context: ./backend
      dockerfile: Dockerfile
    expose:
      - "8000"
    env_file:
      - .env
    depends_on:
      postgres:
        condition: service_healthy
    restart: unless-stopped
    networks:
      - portfolio-net
    volumes:
      - uploads_data:/app/uploads

  postgres:
    image: postgres:16-alpine
    expose:
      - "5432"              # NOT published to host
    env_file:
      - .env
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U $${POSTGRES_USER} -d $${POSTGRES_DB}"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: unless-stopped
    networks:
      - portfolio-net

volumes:
  pgdata:
  caddy_data:
  caddy_config:
  uploads_data:

networks:
  portfolio-net:
    driver: bridge
```

### Development Compose Override (`docker-compose.dev.yml`)

```yaml
services:
  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      target: development
    ports:
      - "5173:5173"         # Vite dev server exposed to host
    volumes:
      - ./frontend/src:/app/src  # Hot reload source mount
    environment:
      - VITE_API_URL=http://localhost:8000

  backend:
    ports:
      - "8000:8000"         # Expose for direct API testing
    volumes:
      - ./backend/app:/app/app  # Hot reload source mount
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

  postgres:
    ports:
      - "5432:5432"         # Expose for local DB tools
```

### Container Details

#### Frontend Container (Multi-stage)

```dockerfile
# Stage 1: Build
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Stage 2: Serve (production)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

#### Backend Container (Multi-stage)

```dockerfile
# Stage 1: Build/dependencies
FROM python:3.12-slim AS build
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Stage 2: Runtime
FROM python:3.12-slim
WORKDIR /app
COPY --from=build /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=build /usr/local/bin /usr/local/bin
COPY . .
RUN useradd -m appuser
USER appuser
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

### Development vs Production Differences

| Aspect | Development | Production |
|---|---|---|
| Frontend build | Vite dev server with HMR | Pre-built static files via nginx |
| Backend | `--reload` flag for auto-restart | Standard uvicorn |
| Ports exposed | 5173, 8000, 5432 to host | Only 80, 443 |
| Source code | Volume-mounted for hot reload | Copied into image at build |
| Database | Accessible from host for tools | Internal only |
| Environment | `.env` with dev values | `.env` with production secrets |
| TLS | Disabled (HTTP only locally) | Automatic via Caddy |

---

## 11. Home-Server Deployment Architecture

### Network Path

```
User Browser
    │
    ▼
ISP Network
    │
    ▼
Public IP (dynamic or static)
    │
    ▼
Home Router
    │ (Port forwarding: 80 → host:80, 443 → host:443)
    ▼
Linux Host Machine
    │ (Docker)
    ▼
Caddy Container (TLS termination + reverse proxy)
    │
    ├── Frontend Container (static files)
    └── Backend Container (API) → PostgreSQL Container
```

### Step 1: Determine CGNAT Status

Before selecting an exposure strategy, determine whether the ISP uses CGNAT.

**Method 1: Compare IPs**
```bash
# Get your public IP from an external service
curl -s ifconfig.me
# Compare with your router's WAN IP (usually at 192.168.1.1 admin page)
# If they differ significantly, you are likely behind CGNAT
```

**Method 2: Check traceroute**
```bash
traceroute -m 5 ifconfig.me
# If the second hop is a carrier-grade NAT (100.64.0.0/10), you are behind CGNAT
```

**Method 3: Check router settings**
- Look for "CGNAT" or "Carrier Grade NAT" in router WAN settings
- Look for WAN IP in 100.64.0.0 – 100.127.255.255 range

### Deployment Strategies

#### Strategy A: Direct Port Forwarding (No CGNAT)

Requirements:
- Public IP (dynamic or static)
- Ports 80 and 443 open (ISP not blocking them)
- Not behind CGNAT
- Port forwarding configured on router

Steps:
1. Configure router to forward ports 80 and 443 to host machine's local IP
2. Set up dynamic DNS (if dynamic IP) via Cloudflare API, DuckDNS, or ddclient
3. Point domain A record to public IP
4. Caddy handles TLS via Let's Encrypt automatically
5. Configure firewall (UFW): allow 80, 443 only

```bash
# Host firewall
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

#### Strategy B: Cloudflare Tunnel (Behind CGNAT)

If direct port forwarding is impossible (CGNAT, ISP blocking ports):

1. Install `cloudflared` on host
2. Create Cloudflare tunnel
3. Tunnel routes public domain → localhost:443 (Caddy)
4. Caddy still handles TLS, or use Cloudflare's edge TLS

Advantages: Works behind CGNAT, DDoS protection, no open ports needed
Disadvantages: Traffic routes through Cloudflare, requires Cloudflare account

#### Strategy C: Tailscale Funnel (Alternative)

1. Install Tailscale on host
2. Enable Tailscale Funnel for public access
3. Routes public internet → host via Tailscale network

Advantages: Simple setup, WireGuard encryption
Disadvantages: Tailscale dependency, less control

**Recommended strategy: A if possible, B as fallback.**

### Dynamic DNS

If the home IP is dynamic (changes periodically):

**Option 1: Cloudflare DNS API**
```bash
# Cron job every 5 minutes
*/5 * * * * /opt/scripts/update-dns.sh
```
Script queries current public IP, compares to DNS record, updates via Cloudflare API if changed.

**Option 2: DuckDNS**
```bash
curl "https://www.duckdns.org/update?domains=YOURDOMAIN&token=TOKEN&ip="
```

### TLS Certificates

Caddy handles this automatically via ACME (Let's Encrypt):

```
# Caddyfile
yourdomain.com {
    reverse_proxy backend:8000 {
        path /api/*
    }
    reverse_proxy frontend:80

    header {
        Strict-Transport-Security max-age=31536000;includeSubDomains
        X-Content-Type-Options nosniff
        X-Frame-Options DENY
    }
}
```

Caddy automatically provisions and renews TLS certificates. No manual certificate management needed.

### Backup Strategy

#### PostgreSQL Backups

```bash
#!/bin/bash
# scripts/backup.sh
BACKUP_DIR="/opt/backups/postgres"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS=30

# Create backup
docker exec portfolio-postgres-1 pg_dump \
  -U $POSTGRES_USER -d $POSTGRES_DB \
  --format=custom | gzip > "$BACKUP_DIR/portfolio_$TIMESTAMP.sql.gz"

# Rotate old backups
find "$BACKUP_DIR" -name "*.sql.gz" -mtime +$KEEP_DAYS -delete
```

**Cron:** Daily at 3:00 AM
```bash
0 3 * * * /opt/scripts/backup.sh >> /var/log/portfolio-backup.log 2>&1
```

#### Restore Procedure

```bash
# Restore from backup
gunzip -c backup_file.sql.gz | docker exec -i portfolio-postgres-1 \
  pg_restore -U $POSTGRES_USER -d $POSTGRES_DB --clean
```

#### What is backed up

| Data | Location | Backup Method |
|---|---|---|
| PostgreSQL data | Docker volume `pgdata` | pg_dump via cron |
| Uploaded images | Docker volume `uploads_data` | File copy to backup location |
| Caddy TLS certs | Docker volume `caddy_data` | Let's Encrypt re-provisions automatically |
| Environment config | `.env` file | Manual (git-ignored, store securely) |
| Source code | Git repository | GitHub remote |

---

## 12. Testing Strategy

### Backend Tests

| Test Type | What | Tool | Priority |
|---|---|---|---|
| Unit tests | Service logic, utility functions, data transforms | pytest | High |
| API integration tests | Endpoint request/response, status codes, auth | pytest + httpx | High |
| Database tests | Model CRUD, constraints, migrations | pytest + test DB | High |
| Auth tests | Login flow, session management, rate limiting | pytest + httpx | High |
| Analytics tests | Event recording, deduplication, aggregation | pytest | Medium |

**Test database:** Separate PostgreSQL instance (or SQLite for unit tests, PostgreSQL for integration).

### Frontend Tests

| Test Type | What | Tool | Priority |
|---|---|---|---|
| Component tests | Component rendering, props, events | Vitest + React Testing Library | High |
| Navigation tests | Route rendering, page transitions | Vitest + MemoryRouter | Medium |
| i18n tests | Language switching, translation rendering | Vitest + RTL | Medium |
| Project rendering | Project cards, detail pages with mock data | Vitest + RTL | Medium |
| Error states | Loading, error, empty states | Vitest + RTL | Low |

### What NOT to test (at this scale)

- CSS styling (visual regression testing is overkill for a portfolio)
- Third-party library internals (React Router, i18next)
- Exact pixel layouts
- Static content accuracy

### E2E Testing (Future)

Cypress or Playwright after core functionality is stable. Focus on:
- Full page load and navigation flow
- Language switching
- Project browsing
- Admin login and dashboard
- Analytics event recording

---

## 13. CI/CD Strategy

### GitHub Actions Pipeline

```yaml
# .github/workflows/ci.yml
name: CI

on:
  push:
    branches: [main]
  pull_request:
    branches: [main]

jobs:
  lint-and-typecheck:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Frontend lint
        working-directory: frontend
        run: npm ci && npm run lint
      - name: Frontend typecheck
        working-directory: frontend
        run: npm run typecheck

  frontend-tests:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Frontend tests
        working-directory: frontend
        run: npm ci && npm run test

  backend-tests:
    runs-on: ubuntu-latest
    services:
      postgres:
        image: postgres:16-alpine
        env:
          POSTGRES_USER: test_user
          POSTGRES_PASSWORD: test_pass
          POSTGRES_DB: test_portfolio
        ports:
          - 5432:5432
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'
      - name: Backend tests
        working-directory: backend
        run: |
          pip install -r requirements.txt -r requirements-dev.txt
          DATABASE_URL=postgresql://test_user:test_pass@localhost:5432/test_portfolio
          pytest --cov=app --cov-report=xml

  build-images:
    needs: [lint-and-typecheck, frontend-tests, backend-tests]
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4
      - name: Build frontend image
        run: docker build -t portfolio-frontend ./frontend
      - name: Build backend image
        run: docker build -t portfolio-backend ./backend
```

### Pipeline Stages

```
PR/Push to main
    │
    ├── Lint + TypeCheck (parallel)
    ├── Frontend Tests (parallel)
    ├── Backend Tests (parallel, with PostgreSQL service)
    │
    └── Build Docker Images (after all pass, main branch only)
```

Deployment is manual in early stages. When ready, add a deploy step that SSHs to the home server and runs `docker compose pull && docker compose up -d`.

---

## 14. Learning Roadmap

Ordered by dependency and complexity:

1. **HTML/CSS** → Static portfolio pages
2. **JavaScript** → Interactivity, DOM manipulation
3. **React fundamentals** → Component model, props, state, hooks
4. **TypeScript basics** → Type annotations, interfaces
5. **Vite** → Modern build tooling
6. **React Router** → Client-side routing
7. **i18next** → Internationalization integration
8. **Python/FastAPI basics** → REST API development
9. **SQLAlchemy** → ORM and database interaction
10. **Alembic** → Database migrations
11. **PostgreSQL** → Relational database fundamentals
12. **Docker** → Containerization
13. **Docker Compose** → Multi-container orchestration
14. **Authentication** → Session management, security
15. **Caddy** → Reverse proxy, TLS
16. **Testing** → pytest, Vitest, test patterns
17. **CI/CD** → GitHub Actions
18. **Linux administration** → Server management, monitoring, backups

---

## 15. Development Milestones

Each milestone produces a working, demonstrable system.

### M0 — Development Environment

**Deliverable:** All development tools installed and configured, Docker Compose running.

**Scope:**
- Install Node.js, Python, Docker, Docker Compose
- Initialize `docker-compose.dev.yml` with PostgreSQL and backend/frontend services
- Create `.env` and `.env.example`
- Verify PostgreSQL connection from backend
- Create `Makefile` or scripts for common commands (`make dev`, `make test`, `make db-migrate`)
- Git repository initialized with `.gitignore`

**Verification:** `docker compose -f docker-compose.dev.yml up` runs all services. Backend connects to PostgreSQL. Frontend dev server starts.

---

### M1 — Static HTML/CSS Portfolio

**Deliverable:** Responsive, bilingual static portfolio served by the frontend container.

**Scope:**
- HTML5 pages: Home, About, Skills, Projects, Contact
- CSS with responsive layout (flexbox/grid)
- Language toggle (EN/ES) — initial implementation with i18next
- Professional design system: colors, typography, spacing
- Semantic HTML (header, nav, main, section, footer)
- Accessible: keyboard navigation, alt text, contrast
- Content populated via i18n JSON files
- Docker: frontend served via nginx or Vite dev server
- Basic SEO: page titles, meta descriptions

**Verification:** Open browser. See professional portfolio. Toggle language. Resize window. Navigate all pages via links.

---

### M2 — JavaScript Fundamentals and Interactivity

**Deliverable:** Interactive elements, dynamic content loading.

**Scope:**
- Smooth scroll navigation
- Mobile hamburger menu
- Project filtering by category
- Animated section reveals on scroll
- Form validation on contact page
- Language preference persistence (localStorage)
- Basic analytics events (console.log for now)

**Verification:** Navigate site interactively. Filter projects. Language preference survives page refresh.

---

### M3 — React + TypeScript Conversion

**Deliverable:** Static portfolio rebuilt as React SPA with TypeScript.

**Scope:**
- Convert HTML pages to React components
- Set up React Router for page navigation
- TypeScript interfaces for all data structures
- Component hierarchy: Layout → Pages → Components
- Custom hooks for shared logic
- CSS Modules for scoped styles
- Vite production build

**Verification:** All pages render via React Router. TypeScript compiles without errors. Build produces optimized static output.

---

### M4 — Bilingual Interface (i18n completion)

**Deliverable:** Full i18n implementation with language persistence.

**Scope:**
- Complete translation files for all content
- LanguageSwitcher component
- Language persists via localStorage
- All text externalized from components
- SEO meta tags update with language
- `lang` attribute on `<html>` element

**Verification:** Switch language on any page. All text changes. Refresh page — language persists. Inspect HTML — correct lang attribute.

---

### M5 — Project Data Architecture

**Deliverable:** Structured project data model in the frontend (later migrated to API).

**Scope:**
- TypeScript types for projects, skills, technologies
- JSON data files for projects with full case-study content
- Project card components with thumbnails
- Project detail page with full content sections
- Skills grouped by category
- Technology badges on projects
- Seed content for at least 2 projects (SumoBot, Portfolio Website itself)

**Verification:** Project list renders with cards. Click card → detail page. Skills display grouped. Technology badges visible.

---

### M6 — FastAPI Backend

**Deliverable:** REST API serving project and skill data.

**Scope:**
- FastAPI application with Pydantic schemas
- SQLAlchemy models matching database architecture
- `/api/v1/projects`, `/api/v1/projects/{slug}`, `/api/v1/skills` endpoints
- Locale-aware responses
- Alembic initial migration
- Seed script to populate database
- CORS configuration
- Health endpoint
- OpenAPI docs accessible at `/docs`

**Verification:** `curl localhost:8000/api/v1/projects` returns JSON. Swagger UI at `/docs`. Frontend fetches data from API.

---

### M7 — PostgreSQL Integration

**Deliverable:** Full database integration with migration workflow.

**Scope:**
- Complete SQLAlchemy models for all entities
- Alembic migrations for full schema
- Seed script populates all tables
- Translation table queries (JOIN-based locale responses)
- Project images model
- Technology ↔ Project many-to-many
- Database constraints and indexes as specified

**Verification:** Run migrations from clean database. Seed data. Query API — responses match schema. Add new project via seed script, appears in API.

---

### M8 — Analytics

**Deliverable:** First-party analytics system.

**Scope:**
- `analytics_events` table and model
- `POST /api/v1/analytics/events` endpoint with rate limiting
- Client-side `useAnalytics` hook
- Events: PAGE_VIEW, PROJECT_VIEW, PROJECT_LINK_CLICK, GITHUB_CLICK, CV_DOWNLOAD, CONTACT_CLICK, LANGUAGE_CHANGE
- Session ID generation (client-side UUID in localStorage)
- Duplicate suppression (server-side)
- Basic aggregation queries

**Verification:** Browse site. Check `analytics_events` table — events recorded. Refresh page — no duplicate within 30s. Check rate limiting — rapid requests blocked.

---

### M9 — Administrator Authentication

**Deliverable:** Secure admin login system.

**Scope:**
- `admin_users` table, `admin_sessions` table
- bcrypt password hashing
- Login endpoint with rate limiting
- Session cookie (HttpOnly, Secure, SameSite=Strict)
- Logout endpoint
- Admin route protection (frontend and backend)
- Seed admin user

**Verification:** Navigate to `/admin` → login page. Login with admin credentials → dashboard accessible. Wrong password → rejected. Rapid attempts → rate-limited. Logout → session destroyed.

---

### M10 — Administrator Analytics Dashboard

**Deliverable:** Private admin dashboard with aggregate analytics.

**Scope:**
- `GET /api/v1/admin/analytics` endpoint
- Dashboard page with charts (use a lightweight chart library: Chart.js or recharts)
- Total visits, unique sessions, project views, link clicks
- Time-series chart (visits over time)
- Top projects by views
- Language distribution
- Recent activity feed
- Date range selector

**Verification:** Login as admin. Dashboard loads with analytics data. Charts render. Date range filtering works.

---

### M11 — Automated Testing

**Deliverable:** Test suite for backend and frontend.

**Scope:**
- Backend: pytest fixtures, test database, API integration tests
- Backend: Auth flow tests, analytics tests
- Frontend: Component tests with Vitest + React Testing Library
- Frontend: Navigation tests, i18n tests
- `npm run test` and `pytest` pass cleanly

**Verification:** Run `pytest` — all tests pass. Run `npm run test` — all tests pass. Intentionally break something — test catches it.

---

### M12 — Dockerization

**Deliverable:** Complete Docker setup for production.

**Scope:**
- Frontend multi-stage Dockerfile (build → nginx)
- Backend multi-stage Dockerfile (build → runtime)
- Production `docker-compose.yml`
- Development `docker-compose.dev.yml`
- Health checks on PostgreSQL and backend
- Named volumes for persistence
- Internal-only network for PostgreSQL
- No ports exposed except 80/443 in production

**Verification:** `docker compose up --build` in production mode. Site accessible on port 80/443. Database persists across container restarts. PostgreSQL not accessible from host.

---

### M13 — Reverse Proxy and HTTPS

**Deliverable:** Caddy reverse proxy — `infrastructure/caddy/Caddyfile`. **Built.**

**Correction to this milestone's original premise:** it assumed Caddy would
do ACME certificate provisioning itself. That is incompatible with the
network strategy `security.md` §2 later chose: ACME needs inbound `:80`/`:443`
publicly reachable, and §4 never opens them — the entire point of the
Cloudflare Tunnel is that nothing listens on the home IP. **Public TLS
therefore terminates at Cloudflare's edge, not here.** The visitor still gets
valid HTTPS and HTTP→HTTPS redirection; both are Cloudflare's job now. The
public site block is written `http://{$DOMAIN}` explicitly so Caddy skips
certificate provisioning rather than retrying it forever against ports that
will never be reachable. End-to-end TLS ("Full (strict)") remains available
via a Cloudflare Origin Certificate and is documented in the Caddyfile as
hardening, not a prerequisite.

**Scope — as built:**
- **Two site blocks with different exposure.** Public (`{$DOMAIN}` on `:80`,
  reachable only through the tunnel) and admin (`:8443`, reachable only over
  Tailscale). The admin surface is not merely login-protected on the public
  hostname — it is absent from it.
- **Public block refuses four path groups** (`/internal/*`,
  `/api/v1/admin/*`, `/api/v1/auth/*`, `/admin*`), each returning 404.
  `/internal/*` is what makes `routes/internal.py`'s docstring true — that
  endpoint is unauthenticated *on the grounds* that Caddy never proxies it.
  Wrapped in `route` rather than bare `handle` so the denies hold their
  written order instead of depending on Caddy's implicit specificity sort.
- **`/api/v1/auth/*` is denied publicly** — stricter than `security.md` §3's
  sketch, which left login exposed. The admin only ever signs in over
  Tailscale, so a public login form is a brute-force target with no upside.
  `auth_service`'s rate limiting becomes defence-in-depth behind this.
- **Client-IP forwarding**, the piece M16's proxy fix depends on:
  `header_up X-Forwarded-For {http.request.header.CF-Connecting-IP}`
  overwrites the chain with Cloudflare's authoritative visitor IP, so a
  client cannot forge its own address by sending `X-Forwarded-For` itself.
  Verified: a request carrying both a forged chain and a `CF-Connecting-IP`
  reaches the backend with only the real address.
- **Security headers** via a shared snippet, plus `-Server` to stop
  advertising the proxy.
- **CSP corrected.** The policy sketched in `security.md` §3 omitted
  `font-src` and the `fonts.googleapis.com` entry in `style-src`, which would
  have silently broken every Fraunces/Karla webfont — i.e. the entire
  typography `frontend-design.md` §1 specifies — in production only.
- **Compression** (`encode zstd gzip`). Static cache headers stay in
  `frontend/nginx.conf`, which already owns them; duplicating them here would
  create two sources of truth. (§16's "Caddy serves everything" open decision
  is therefore still open, and deliberately so — resolving it is a bigger
  change that also interacts with M17's prerendered per-route files.)
- **Catch-all `:80` block returning 404.** Caddy answers an unmatched `Host`
  with an empty `200` by default, which makes a misrouted tunnel ingress rule
  look healthy.

**Verification — performed:** `caddy validate` passes. Routing exercised
against stub upstreams on an isolated Docker network: all four public deny
groups return 404 while `/api/v1/projects` and `/` proxy correctly; the admin
block reaches `/api/v1/admin/*` and `/api/v1/auth/*` but still refuses
`/internal/*`; an unmatched Host returns 404. All six security headers
confirmed present on a real response with `Server` absent.

**Still open:** end-to-end verification against the real Cloudflare edge
(needs the tunnel from M14 actually running).

---

### M14 — Home-Server Deployment

**Deliverable:** Portfolio live on the internet from the home server.
Production compose file — `docker-compose.yml` — **built**; host-level steps
remain.

**Correction to this milestone's original premise:** "Port forwarding
configuration" and "Dynamic DNS setup" are obsolete. `security.md` §2 chose
the Cloudflare Tunnel, which makes an *outbound* connection — so no port is
forwarded, no inbound port is opened, and no dynamic-DNS updater is needed
because DNS points at Cloudflare's proxy IPs rather than at the (changing)
home IP. The CGNAT check is likewise no longer a gate: the tunnel works
*regardless* of the answer, which is precisely why it was chosen.

**Scope — as built (`docker-compose.yml`):**
- **Nothing publishes a port to `0.0.0.0`.** Postgres drops the dev stack's
  `5432` publication entirely; backend and frontend publish nothing. The
  single published port is Caddy's admin site, bound to `${TAILSCALE_IP}:8443`
   — verified in the rendered config as `host_ip: 100.x.y.z`, not `0.0.0.0`.
- **Tailscale binding corrected.** `security.md` §3 sketched `bind tailscale0`
  inside the Caddyfile. That cannot work from a container — the host's
  `tailscale0` interface does not exist in the container's network namespace.
  Publishing the port bound to the host's Tailscale IP achieves the same
  restriction with no host networking and no Tailscale-in-container sidecar.
- **`cloudflared` service**, token from `.env`, ingress pointing at
  `http://caddy:80`.
- **Hardening carried over from `security.md` §7**, which had been written as
  "carry into the production compose file" against a file that did not exist:
  `no-new-privileges` on every service (not just `noc`), `restart:
  unless-stopped` on every service (nothing had a restart policy),
  per-service memory limits, and `read_only` retained on `noc`.
- **Log rotation** (`max-size`/`max-file`) on every service via a YAML anchor
  — an M16 item, applied here because the file it belongs in is this one.
- **Healthchecks** on postgres, backend (`/api/v1/health`, via `python` since
  the image has no `curl`), frontend, and Caddy (its localhost-only admin
  API), with `depends_on: condition: service_healthy` chaining startup.
- **Deterministic proxy trust.** The network pins subnet `172.20.0.0/16` and
  Caddy takes a static `172.20.0.10`, so the backend's `TRUSTED_PROXY_IPS`
  names exactly one address rather than a whole subnet or a
  Docker-assigned-at-random one.

**Two production-only bugs found and fixed while building this:**
- **`frontend/package-lock.json` did not exist**, so the production image
  stage (`npm ci`) could not build at all — it had never been built. The dev
  stage uses `npm install`, which is why this stayed invisible. Lockfile
  generated (`lockfileVersion 3`, 330 packages); production image now builds.
  M15's CI depends on this too.
- **`VITE_API_URL` was never passed to the build stage.** Vite inlines
  `VITE_*` at build time, so the production bundle baked
  `api.ts`'s dev fallback, `http://localhost:8000` — every API call in
  production would have gone to the *visitor's own machine* and been
  CSP-blocked besides. Fixed with an `ARG` in `frontend/Dockerfile`, and
  hardcoded empty in the production compose rather than inherited from
  `.env`, so copying `.env.example` to the server cannot reintroduce it.
  Verified both ways: the fixed image contains no `localhost:8000`; building
  without the fix demonstrably bakes it in.

**Remaining (host-level, not repo-level):** `cloudflared` tunnel created and
DNS proxied per `security.md` §2; Tailscale installed and `TAILSCALE_IP` set;
`ufw` per §4; `.env` populated and `chmod 600`.

**Verification:** `docker compose config` validates and confirms the port
map. Remaining once the host steps are done: load the site from a mobile
device on cellular, confirm the certificate is Cloudflare's and the page
renders with webfonts intact (proves the CSP fix), confirm `/admin` returns
404 from the public hostname, and confirm admin login works over Tailscale
but not from the public internet.

---

### M15 — CI/CD

**Deliverable:** GitHub Actions pipeline.

**Scope:**
- Lint + typecheck
- Frontend tests
- Backend tests (with PostgreSQL service)
- Docker image builds
- Pipeline badges in README

**Verification:** Push to GitHub. Actions run. All stages pass. PRs blocked from merging if tests fail.

---

### M16 — Monitoring, Backups, and Security Hardening

**Deliverable:** Operational reliability — the site survives a disk filling
up, a container dying at 3am, a dependency CVE, and a botnet finding the
login form, without the owner having to be watching.

**Relationship to `security.md`:** that document already picks the concrete
tooling for most of this (§10 restic + `pg_dump`, §11 `unattended-upgrades`
+ Diun, §7 container hardening, §12 how the NOC service fits). This
milestone does **not** restate those choices — it's the list of what's
actually still missing in the repo, and what "done" means for each. Where a
tool is already chosen, the entry says *build the thing* rather than
*decide again*.

**Root cause to design around:** the operational layer is currently
**write-only** — several subsystems produce data forever and nothing
consumes, bounds, or prunes it, and the pieces that *would* bound it live in
files that don't exist yet (`infrastructure/` is an empty directory; there
is no production compose file; `.github/` has no workflows). Every item
below is either an unbounded growth path or a control that's documented as
existing but isn't in the tree.

**Scope:**

- **Data retention — DONE.** `app/services/retention_service.py` now enforces
  what §9 previously only described, with every window a named constant and a
  reason: analytics 90 days (§9's own figure), `login_attempts` 30 days (rate
  limiting only looks back 15 minutes; the rest is for security review, and
  unbounded retention makes sustained guessing a slow disk-fill attack),
  expired `admin_sessions` on a 1-hour grace. Runs on a timer in the API
  process's lifespan — sweeping once at startup, so a server restarted more
  often than the interval still purges — plus
  `python -m scripts.purge_retention` (with `--dry-run`) for cron or manual
  use, and `RETENTION_PURGE_ENABLED=false` to hand the job to cron instead.
  `oldest_row_ages()` exists so retention can be *observed*: a purge task that
  silently stopped running otherwise looks identical to one with nothing to do.
  Verified end to end — a 95-day row seeded and removed by the timed sweep
  across a real backend restart, while a 10-day row survived. Covered by
  `tests/test_retention.py` (7 tests), which asserts both sides of every
  boundary: a sweep that deleted the whole table would otherwise pass a naive
  "old rows are gone" check.
  **Also fixed:** application `INFO` logging was being discarded entirely —
  uvicorn configures only its own `uvicorn.*` loggers, and nothing handled the
  root logger — so the sweep's "deleted N rows" line, the only evidence the
  §9 commitment is being kept, went nowhere. (`WARNING` and above did still
  surface via logging's last-resort handler, so the earlier
  `TRUSTED_PROXY_IPS='*'` warning was unaffected.)
- **Analytics test bench — DONE.** `tests/test_analytics_privacy.py` (26
  tests) and `frontend/src/hooks/useAnalytics.test.tsx` (6 tests) turn §9's
  five design principles from prose into assertions, in two halves:
  - *The numbers are real.* Dashboard totals must equal the events actually
    seeded — no inflation, no double counting — and the mechanisms that
    reduce counts must genuinely drop rows: bot user-agents ignored,
    session-less events ignored, same-path page views deduplicated inside 30
    seconds while genuine navigation still counts, and a single session
    capped at 60 events/minute.
  - *Nothing personal is collected.* The raw IP and user agent must not
    appear in any column of the stored row (checked across all columns,
    including the free-form JSONB); `ip_hash` must not be an unsalted digest,
    which would be brute-forceable back to the address in minutes; the daily
    salt must actually rotate, so a visitor cannot be joined across days,
    while still separating two visitors within one day. Schema assertions
    enumerate columns from the live database rather than a hardcoded list, so
    a future migration adding an `email` or `message` column fails the bench
    instead of quietly widening what the site collects.

  All inputs are synthetic — RFC 5737 documentation IPs and invented
  identifiers. No real visitor data is needed to run any of it.

  On the client side the bench pins down the case that matters most: the
  Contact page asks for a name, an email address and a message, and its
  submit handler fires a `contact_click` event. The tests assert the event
  records *that a submission happened* and carries none of what was typed —
  no metadata at all. Both halves were confirmed non-vacuous by deliberately
  breaking them (making `hash_ip_daily` return the raw IP tripped three
  backend tests; leaking the email field into the event tripped three
  frontend ones).
- **Data retention — original finding, kept for context.** `architecture.md`
  §9 sets a 90-day analytics retention policy and nothing implemented it.
  `network_health_samples` is the only table with a real purge (7 days,
  enforced twice — `noc/monitor.py`'s `purge_old_samples` and
  `network_health_service.purge_old_samples`). Missing:
  - `analytics_events` — grows forever; the stated 90-day policy is
    currently documentation-only. This is a **privacy** commitment, not just
    a disk one.
  - `login_attempts` — one row per failed login forever; a sustained
    brute-force attempt is also a slow database-fill attack, and
    `check_rate_limit` scans this table on every login.
  - `admin_sessions` — expired sessions are deleted **only** when that exact
    session id is looked up again (`auth_service.get_session_user`). A
    session that expires and is never revisited stays in the table
    permanently.

  Build one scheduled purge path covering all three, on the same mechanism
  (not three ad-hoc ones), and make retention windows named constants
  consistent with §9.
- **Real client IP behind the proxy — backend half DONE, Caddy half open.**
  Both `routes/auth.py` and `routes/analytics.py` read `request.client.host`,
  which behind Caddy + Cloudflare Tunnel (`security.md` §2) is the *proxy's*
  IP. `security.md` §9 flagged the analytics consequence; the **auth**
  consequence was undocumented and worse: `hash_ip(...)` collapses to one
  value for all traffic, degrading `check_rate_limit`'s "5 failures per 15
  minutes per IP" into *5 failures per 15 minutes globally*.
  - **Implemented:** uvicorn's `ProxyHeadersMiddleware` wired as the
    outermost middleware in `app/main.py`, trusting only `TRUSTED_PROXY_IPS`
    (new setting in `config.py`, defaulting to loopback so it fails closed);
    both call sites unified behind `app/middleware/proxy.py`'s `client_ip()`;
    `tests/test_proxy_headers.py` covers spoofing from an untrusted peer,
    CIDR ranges, multi-hop chain resolution, and the M16 assertion that two
    `X-Forwarded-For` values yield two `ip_hash` values. Verified end to end
    against the running stack: from a trusted peer two visitors recorded two
    distinct hashes; from an untrusted peer both correctly collapsed to the
    peer's own hash.
  - **Caddy half — now also done (M13).** `infrastructure/caddy/Caddyfile`
    sets `trusted_proxies static private_ranges` and rewrites
    `X-Forwarded-For` from `CF-Connecting-IP`, and `docker-compose.yml` pins
    Caddy to `172.20.0.10` so `TRUSTED_PROXY_IPS` names one exact address.
    Verified against stub upstreams: a request carrying a forged
    `X-Forwarded-For` *and* a `CF-Connecting-IP` reaches the backend with
    only the real visitor address. The empty-header fallback that this
    rewrite can produce is covered by `test_empty_forwarded_header_falls_back_to_peer`.
  - **Still open:** confirming real visitor IPs land correctly once the
    tunnel is actually running (needs M14's host-level steps).
- **`/internal/*` deny — DONE (M13).** `routes/internal.py`'s docstring
  justified leaving `GET /internal/metrics` unauthenticated on the grounds
  that it's "never proxied by Caddy (see `infrastructure/caddy/Caddyfile`)",
  and `security.md` §12 repeated it — but that file did not exist. It now
  does, and denies `/internal/*` on **both** site blocks, making the
  docstring literally true. Verified returning 404 through Caddy.
  **Still open:** a test that fails if the deny rule is ever removed — an
  unauthenticated endpoint whose only protection is a config file needs that
  protection under test, and Caddyfile routing isn't currently exercised by
  any automated suite. Note §5's repo structure also lists an
  `infrastructure/nginx/default.conf` that doesn't exist and isn't needed
  (the frontend image carries its own `nginx.conf`); §5 should be corrected.
- **Production compose file — DONE (M14).** `docker-compose.yml` now carries
  the `security.md` §7 hardening that had been written against a file that
  didn't exist: `no-new-privileges` and `restart: unless-stopped` on every
  service, `deploy.resources.limits`, `read_only` retained on `noc`, and no
  published Postgres port.
- **Least-privilege `noc_writer` database role — DONE.** What `security.md`
  §7 called "the single highest-value hardening item left over": the `noc`
  container — the most exposed process in the stack, since it dials the
  public internet on a timer — held the backend's full-access credential.
  It now connects as `noc_writer`, provisioned by
  `scripts/create_noc_role.sql` (idempotent, and re-running is how the
  password rotates) via `make noc-role` / `make noc-role-prod`, and wired
  through `NOC_DATABASE_URL` in both compose files.
  - Granted `SELECT, INSERT, DELETE` on `network_health_samples` plus
    `USAGE` on its sequence — §7's sketch omitted the sequence, without
    which every insert fails, since `id` is `BIGSERIAL`.
  - Withheld `UPDATE` and `TRUNCATE` on that same table: append-and-prune
    only, so a compromised NOC container can neither rewrite recorded
    history nor wipe it.
  - Verified by running the real service on the credential, and by a
    privilege matrix confirming every other table, all DDL, and all role
    escalation are denied. `backend/tests/test_noc_role.py` locks this in,
    enumerating tables at runtime so future migrations are covered by
    default; confirmed non-vacuous by temporarily widening a grant and
    watching it fail. Skips cleanly where the role isn't provisioned.
  - The shared-credential fallback remains for fresh checkouts but now
    prints which credential it holds at startup, so the weaker path is
    visible rather than silent.
  - Also fixed while here: `backend/tests/conftest.py` disposes the shared
    SQLAlchemy engine between tests. pytest-asyncio gives each test its own
    event loop, so the second DB-touching test in a module was pulling an
    asyncpg connection bound to the previous, closed loop.
- **Container health monitoring — DONE (M14) for production.** Healthchecks
  on postgres, backend (`/api/v1/health`, via `python` since the image has no
  `curl`), frontend, and Caddy, chained with `depends_on: service_healthy`.
  **Still open:** `docker-compose.dev.yml` still healthchecks only postgres.
  Lower priority (dev failures are visible immediately) but it diverges from
  production, which is its own hazard.
- **Log rotation — DONE (M14) for production.** `max-size: 10m` /
  `max-file: 5` applied to every service via a YAML anchor; without it the
  `noc`'s ~2,900 lines/day and Caddy's access log would grow unbounded on the
  very disk the NOC reports on. Caddy logs to stdout by design so Docker owns
  rotation rather than accumulating an IP-bearing file inside the container.
  **Still open:** `docker-compose.dev.yml` has no logging limits either.
- **Dependency scanning — DONE, and it found real vulnerabilities.**
  `.github/workflows/ci.yml` now runs `npm audit --audit-level=high` and
  `pip-audit --strict`, both **failing the build** rather than reporting. It
  also provisions the `noc_writer` role so `test_noc_role.py` actually runs
  in CI instead of skipping, builds both production images (which is what
  would have caught M14's missing lockfile), and validates the Caddyfile.

  Running the audits for the first time surfaced live CVEs, now fixed:
  - **Backend, production-affecting.** `starlette` 0.41.3 carried nine
    advisories and `python-multipart` 0.0.19 three — both ship in the
    running API. The root cause was FastAPI being pinned 26 minor versions
    behind (0.115.6), which held `starlette` back. Upgraded to FastAPI
    0.141.1 / `python-multipart` 0.0.32 / uvicorn 0.38.0; `pip-audit` now
    reports **no known vulnerabilities**, and all backend tests pass on the
    new versions.
  - **Frontend, dev-only.** One critical (`vitest` UI server arbitrary file
    read/execute) and one high (`vite` path traversal). Neither ships in the
    bundle — the exposure is a developer's machine — but both were fixable:
    vite 7 / vitest 4 / plugin-react 5. Tests, typecheck and the production
    build all pass on the upgrade, and the admin `recharts` code-split
    survives it. Two moderate advisories remain, below the gate.
- **Rate limiting — DONE.** `app/services/rate_limit_service.py` adds an
  IP-keyed sliding-window limiter, deliberately in memory rather than in a
  table: a persistent limiter would mean writing a row per visitor request,
  i.e. building exactly the per-visitor history §9 promises not to keep.
  Addresses are stored hashed. Applied to:
  - `POST /api/v1/analytics/events` — closes the bypass. The existing
    60/min limit keys on client-supplied `session_id`, so rotating it
    defeated the cap entirely; the new backstop keys on IP, which the client
    cannot choose. Both now apply.
  - `POST /api/v1/contact` — 1 message per 5 minutes and 5 per hour. Two
    windows rather than one, because an hourly cap alone still permits five
    messages in five seconds.
  - `POST /api/v1/auth/login` — unchanged and already sound; its only defect
    was the proxy-IP issue, now fixed.
  - Public `GET` routes still have no limit; that belongs at the Caddy layer
    and remains open.
- **Backup and restore — DONE.** `scripts/backup.sh` streams `pg_dump`
  straight into `restic backup --stdin` (no plaintext dump ever touches
  disk), prunes on §10's schedule, and verifies repository integrity.
  `scripts/restore.sh` defaults to a **throwaway** database and refuses to
  target the live one without an explicit
  `--i-understand-this-overwrites-live` flag — a restore script whose easiest
  path overwrites production eventually will. `.env` is deliberately excluded
  from the repository and belongs in a separate `age`-encrypted copy (§8), so
  one password does not unlock both the data and every secret.
  Round-trip verified on the dev database (2 projects / 9 skills / 2
  certifications restored exactly); `restic` itself is not yet installed on
  this host, so the restic leg is verified by construction rather than
  execution.
- **Documentation of all security decisions** — `security.md`'s own open
  loops are now closed: the `noc_writer` role (§7) and the `trusted_proxies`
  config (§9). Its §13 pre-launch checklist remains, being host-level work.

**Verification:** Run `scripts/backup.sh`; restore that snapshot into a
throwaway database and diff row counts against the source. Stop the
`backend` container and confirm the NOC dashboard shows it down within one
poll interval, and that `restart: unless-stopped` brings it back. Confirm
`docker inspect` shows a log size cap on every service. Seed
`analytics_events` with a row older than the retention window and confirm
the purge removes it. Send two requests with different `X-Forwarded-For`
values and assert the recorded `ip_hash` values differ. `curl` the public
hostname's `/internal/metrics` and confirm it does not resolve to the
metrics payload. Introduce a known-vulnerable dependency in a branch and
confirm CI fails.

---

### M17 — Performance, Accessibility, and SEO Optimization

**Deliverable:** Production-quality metrics, and a portfolio that's fully
legible to search engines, social-media link unfurlers, LLM crawlers, and
screen readers — not just to a human clicking through the rendered app.

**Root cause to design around:** the app is a client-only Vite/React SPA
served from one static `index.html` (`frontend/index.html`) via
`try_files ... /index.html` in `frontend/nginx.conf`. Every route currently
inherits the same `<title>`, meta description, and OG tags because nothing
varies them per route, and anything only set via client-side JS
(`document.title = ...`) is invisible to clients that don't execute
JavaScript — social unfurlers (Slack, X/Twitter, LinkedIn, iMessage) and
most LLM/agent crawlers included. Title, description, canonical, OG, and
structured data all trace back to this one gap, so they share one two-part
fix instead of five unrelated ones:

1. **Client-side head sync** — a `useDocumentHead` hook called once per page
   component, keeping `<title>`, meta description, and canonical correct
   during in-app SPA navigation, for the human in the browser.
2. **Build-time prerendering** — after `vite build`, crawl the app's known
   static routes (`/`, `/about`, `/skills`, `/projects`, `/projects/:slug`
   per published project, `/certifications`, `/contact`, and the 404 shell)
   and write each one's fully-rendered HTML — title, meta, canonical, and
   JSON-LD included — to its own `dist/<route>/index.html`. This is what a
   non-JS client (view-source, a link unfurler, most LLM crawlers) actually
   receives. `admin*` routes are excluded from the crawl and additionally
   marked `noindex` (below), since they aren't public content.

**Scope:**

- **View-source integrity** — the prerender step above makes `view-source:`
  on any public route show that page's real title, description, canonical,
  OG tags, and JSON-LD, instead of the one generic shell every route shows
  today. `admin`, `admin/dashboard`, `admin/network-health` get
  `<meta name="robots" content="noindex,nofollow">` and are excluded from
  both the sitemap and the prerender crawl list.
- **Real 404s** — `frontend/src/pages/NotFound.tsx` already renders a
  not-found UI, but `nginx.conf`'s `try_files $uri $uri/ /index.html;`
  returns HTTP 200 for every unmatched path (a "soft 404" search engines
  penalize). Fix: `try_files $uri $uri/ =404;` paired with
  `error_page 404 = /404/index.html;`, so nginx serves the prerendered
  404 shell while preserving the real `404` status code.
- **Unique `<title>` per page** — replace the single static
  `<title>Your Name — Portfolio</title>` in `frontend/index.html` with a
  per-route value from `useDocumentHead`, pattern `{Page} — {Site Name}`
  (e.g. `Projects — [Name] Portfolio`,
  `{Project Title} — Projects — [Name] Portfolio`). All 7 public routes
  currently ship the identical title.
- **Meta descriptions per page** — one distinct, human-written
  `<meta name="description">` per route (150–160 chars), sourced from
  `i18n` strings so `/es` gets a real translated description too, not the
  homepage's description reused everywhere as today.
- **Open Graph image** — no OG image exists yet (`frontend/public` only has
  `favicon.svg` and `robots.txt`). Add `frontend/public/og-default.png`
  (1200×630) plus a per-project OG image where a project has a hero image,
  wired via `og:image` + `og:image:width/height` +
  `twitter:card=summary_large_image`.
- **Structured data (JSON-LD)**, emitted per route by the same
  prerender/head-sync mechanism:
  - Home / About → `Person` (name, jobTitle, url, `sameAs` → GitHub/LinkedIn)
  - Home → `WebSite` (add `SearchAction` only if/when on-site search exists)
  - `/projects/:slug` → `CreativeWork` or `SoftwareSourceCode`, whichever
    matches the project shape better
  - `/certifications` → `ItemList` of `EducationalOccupationalCredential`

  None of this exists today.
- **H1 discipline** — already compliant; documenting the rule so it stays
  that way: exactly one `<h1>` per route, always `PageHeader`'s title or
  (on `ProjectDetail`, which doesn't use `PageHeader`) the project title.
  Verified: no current route renders more than one.
- **Canonical tag** —
  `<link rel="canonical" href="https://portfolio.example.com{path}">` per
  route via `useDocumentHead`: absolute URL, no query string. Prevents
  `/projects/foo` vs `/projects/foo/` vs `?utm=...` duplicate-content
  splitting.
- **`llms.txt`** — add `frontend/public/llms.txt` (served at `/llms.txt`):
  a short Markdown summary of who the site belongs to, what's on it, and
  links to each public section's canonical URL, for LLM-based
  crawlers/agents that check it before crawling.
- **Favicon — full set, not just the SVG** — only `favicon.svg` is
  referenced today. Add the standard fallback set: `favicon.ico`
  (multi-size, for older user agents), `apple-touch-icon.png` (180×180),
  and a minimal `site.webmanifest` (name, icons, `theme_color` matching the
  palette in `frontend-design.md`), all linked from `frontend/index.html`.
- **Sitemap** — `robots.txt` already points to `/sitemap.xml`, but the file
  doesn't exist. Generate `dist/sitemap.xml` at build time (static routes +
  one `<url>` per published project, from the same data the prerender step
  crawls), `lastmod` from each project's `updated_at`. Exclude `admin*`.
- **Language attributes** — `<html lang>` is already set correctly at
  runtime (`document.documentElement.lang = i18n.language` in `App.tsx`);
  extend this with `hreflang` alternate links (`en`, `es`, `x-default`) per
  route once prerendering exists — hreflang must be present in the static
  HTML to be crawled, so a runtime-only `lang` attribute isn't enough for
  the `es` alternate to be discovered.
- **Alt text audit** — `ProjectDetail.tsx`'s hero image already has real
  alt text with a fallback (`hero.altText ?? project.title`): compliant.
  `ProjectShowcase.tsx` and `CertificationCard.tsx` both hardcode `alt=""`
  on images carrying real visual information (project screenshot,
  certification badge) rather than being decorative — audit each call site
  and either supply real alt text or confirm decorative intent explicitly
  in a code comment, since bare `alt=""` currently reads as an oversight,
  not a decision.
- **Sourcemaps not exposed** — Vite's production build already defaults
  `build.sourcemap` to `false` (unset in `vite.config.ts`); confirmed no
  `.map` files ship in `dist/`. Set `build: { sourcemap: false }` in
  `vite.config.ts` explicitly anyway, so the setting survives a future Vite
  default change instead of relying on today's default.
- **JS bundle reduction** — `recharts` (~450 kB) is already code-split
  behind `lazy()` for the admin dashboard (`App.tsx`) — keep this pattern.
  Audit the main bundle with `vite build` + `rollup-plugin-visualizer` to
  confirm nothing else non-essential leaks into the initial chunk beyond
  `motion`/`i18next`/`react-i18next`, and route-split
  `ProjectDetail`/`Certifications` if the visualizer shows them as large
  disjoint chunks. Once a baseline is measured, add a bundle-size budget
  check in CI (`M15`) so regressions are caught in review, not after
  deploy.

**Verification:** Lighthouse Performance/Accessibility/SEO all >90.
`curl -s https://portfolio.example.com/projects/<slug> | grep '<title>'`
returns that project's real title, not the generic one.
`curl -o /dev/null -s -w '%{http_code}' https://portfolio.example.com/nope`
returns `404`. Facebook Sharing Debugger / Twitter Card Validator render the
correct title, description, and image per URL. `/sitemap.xml` and
`/llms.txt` both resolve. No `.map` files present under `dist/`. `admin*`
routes carry `noindex` and are absent from the sitemap.

---

## 16. Risks and Open Technical Decisions

### Open Decisions

| Decision | Options | Recommendation | Status |
|---|---|---|---|
| CSS approach | CSS Modules vs Tailwind | CSS Modules (simpler, teaches CSS fundamentals) | Pending approval |
| Frontend serving in Docker | nginx vs Caddy serves static | Caddy serves everything (fewer containers) | Pending approval |
| Session storage | PostgreSQL table vs in-memory | PostgreSQL (survives restarts) | Pending approval |
| Chart library | Chart.js vs recharts vs Victory | recharts (React-native, lightweight) | Pending approval |
| Contact form backend | Email sending vs form-to-database | **Resolved: email relay, nothing stored.** See below | Implemented |
| Image hosting | Local uploads vs external | Local Docker volume (self-contained) | Pending approval |
| Admin content management | Seed scripts vs admin CRUD UI | Seed scripts initially, CRUD UI in later milestone | Pending approval |
| WYSIWYG for admin content | Markdown vs rich text vs raw HTML | Markdown with preview (simpler, safer) | Pending approval |

### Contact Form — Resolved Decision

The form on the Contact page previously **asked for a name, email address and
message, then silently discarded all three**: its submit handler called
`preventDefault()` and fired an analytics event, nothing more. A visitor got
no confirmation and no error, and believed a message had been sent that never
existed. That is worse than having no form.

**Resolved as an email relay that stores nothing** (`app/services/contact_service.py`),
overriding this table's original lean toward form-to-database:

- **Nothing is persisted.** A `contact_submissions` table holding name, email
  and message would be the largest concentration of personal data on the site,
  would need its own retention policy, and would sit in every backup —
  contradicting §9's "no visitor PII". Relaying keeps that promise intact, and
  the analytics privacy bench's schema assertions enforce it.
- **The destination is private.** It lives in `.env` as `CONTACT_TO_EMAIL`,
  never in the frontend bundle, never in an API response, never committed.
  Verified absent from the built production bundle and from the repository.
- **Failures are reported, not swallowed.** Delivery failure returns 502 and
  the UI tells the visitor to email directly — the specific bug the previous
  implementation had.
- **Abuse surface, since it is unauthenticated and causes outbound mail:**
  header-injection refused (a `\r\n` in the name or address would let a
  submitter append `Bcc:` and turn the form into a relay sending from the
  owner's authenticated mailbox), a hidden honeypot field answered with a
  fake success so bots get no signal, IP-keyed rate limiting, length caps
  validated before any SMTP connection opens, and a `To:` the visitor can
  never influence. `From` stays the authenticated mailbox with the visitor on
  `Reply-To`, since sending as them would fail SPF/DKIM.

The trade-off, stated plainly: with no stored copy, a message lost to an SMTP
outage is lost. That is why the route surfaces the failure rather than
accepting silently. Covered by `backend/tests/test_contact.py` (21 tests).

### Risks

| Risk | Impact | Likelihood | Mitigation |
|---|---|---|---|
| ISP blocks ports 80/443 | Cannot self-host directly | Medium | Cloudflare Tunnel as fallback |
| CGNAT | Cannot receive inbound connections | Medium | Cloudflare Tunnel |
| Dynamic IP changes faster than DNS update | Brief downtime | Medium | Cloudflare with short TTL, cron-based DNS update every 2 min |
| Home server hardware failure | Portfolio offline | Low | GitHub Pages as emergency static fallback |
| Scope creep | Milestones delayed | High | Strict milestone adherence, defer features |
| Security vulnerability discovered | Data breach | Low | Conservative defaults, dependency scanning, minimal attack surface |
| PostgreSQL data loss | Content/analytics lost | Low | Automated backups, Docker volume persistence, tested restore procedure |
| Burnout / motivation loss | Project stalls | Medium | Small milestones, visible progress, working system at every milestone |

### Future Considerations (Not Now)

- Contact form → email forwarding (requires email service: Resend, SMTP, etc.)
- Admin CRUD for content management (project editing UI)
- RSS feed for projects
- Dark mode toggle
- PWA support
- Search functionality
- Server-side rendering for SEO (if needed)
- CDN for static assets
- Rate limiting with Redis (if traffic grows)

---

*This document should be reviewed and approved before any implementation begins. Modify any section to match your preferences, then we proceed to M0.*