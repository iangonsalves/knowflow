# KnowFlow

KnowFlow is a workspace-based business knowledge platform. Its approved product and technical scope is documented in the [Project Blueprint](docs/KnowFlow_Project_Blueprint.pdf), the [V1 Detailed Design](docs/KnowFlow_V1_Detailed_Design.pdf), and the editable [design source](docs/knowflow-v1-design.md). Architecture decisions are recorded in [docs/adr](docs/adr/).

## Current milestone

The project is being built in approved milestones. M1 establishes the local development foundation only. Authentication, workspace features, uploads, processing, search and answers are later milestones and are not implemented yet.

## Requirements

- Docker Engine with Docker Compose v2
- Node.js 22.13 or newer and npm (for frontend work outside Docker)
- Python 3.12 (for backend work outside Docker)

## Start the M1 foundation

```sh
cp .env.example .env
docker compose up --build -d
docker compose run --rm api alembic upgrade head
```

The local services are:

- Next.js shell: <http://localhost:3000>
- FastAPI shell and OpenAPI: <http://localhost:8000/docs>
- API liveness/readiness: <http://localhost:8000/health/live> and <http://localhost:8000/health/ready>
- PostgreSQL with pgvector: `localhost:5432`
- MinIO console: <http://localhost:9001>

Readiness is expected to fail until the initial database migration has been applied. Copy `.env.example` to `.env` before starting Compose. The example credentials are local development defaults only.

## Run checks

```sh
docker compose run --rm api ruff check app tests
docker compose run --rm api pytest
docker compose run --rm web npm run lint
docker compose run --rm web npm run typecheck
docker compose run --rm web npm run build
```

## Stop local services

```sh
docker compose down
```

Remove the local database and object storage volumes only when you intend to discard local data:

```sh
docker compose down --volumes
```

Do not commit `.env` or provider secrets.
KnowFlow
