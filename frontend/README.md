# Frontend

React 19 + TypeScript + Vite + Tailwind + Recharts dashboard for the churn API: customer form,
prediction card with SHAP drivers, what-if comparison and monitoring charts.

## Run

```bash
cd frontend
cp .env.example .env     # then edit VITE_API_URL if your API is not on 127.0.0.1:8000
npm install
npm run dev              # http://localhost:5173
npm run build            # type-check + production build into dist/
```

## Configuration

| Variable | Purpose |
|---|---|
| `VITE_API_URL` | Base URL of the backend, e.g. `https://your-api.onrender.com` (no trailing slash). Read at **build time**. |

In `npm run dev` an unset `VITE_API_URL` falls back to `http://127.0.0.1:8000`. In a production build it
does **not** fall back to localhost: requests go same-origin and fail, so set the variable in the Vercel
project settings (Settings > Environment Variables) before deploying. The backend must also list the
frontend's exact origin in `ALLOWED_ORIGINS`.

## Demo sign-in

The role switcher signs in with the seeded demo accounts (`admin`, `analyst`, `viewer`). Their
passwords are embedded in this bundle (see `loginWithRole` in `src/services/api.ts`), so they are
public on any deployed copy. This is a demo convenience, not authentication; do not point a deployed
frontend at a backend that holds real data.

See the repository root `README.md` for the model, API and deployment documentation.
