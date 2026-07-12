# Frontend (React) -- placeholder

This directory is reserved for the React frontend. The backend is already
CORS-configured (see `CORS_ORIGINS` in `.env`) and returns clean JSON from
every endpoint, so any standard React setup (Vite, Next.js, CRA) can be
dropped in here without backend changes.

Suggested setup:

```bash
cd frontend
npm create vite@latest . -- --template react-ts
npm install
npm install axios react-query   # or @tanstack/react-query
```

Point the frontend at the backend via an environment variable, e.g. for Vite:

```
VITE_API_BASE_URL=http://localhost:8000/api/v1
```

See the root `README.md` > "User Flow" section for the screens this API
naturally maps to (upload leads -> run campaign -> live progress -> results
table -> charts -> report downloads), and > "All Endpoints" for the full API
surface to build against. Once a frontend exists here, uncomment the
`frontend` service in `../docker-compose.yml`.
