# Customer Churn Predictor (Explainable + What-If Dashboard)

Production-style churn prediction application with:

- FastAPI backend for prediction and explanation
- React + TypeScript frontend dashboard
- CatBoost inference + SHAP feature attributions
- What-if simulation and comparison workflow

## Stack

- Frontend: React, TypeScript, Vite, Tailwind CSS, Recharts
- Backend: FastAPI, Pydantic, Uvicorn, python-dotenv
- ML runtime: CatBoost, pandas, numpy, SHAP
- Data: Telco Customer Churn dataset

## Current Capabilities

- Predict churn probability with configurable threshold
- Explain predictions with top SHAP drivers
- Run what-if simulations and compare before/after outcomes
- Visualize confidence, trend proxy, and risk distribution
- Export chart data to CSV
- Persist form values in localStorage for continuity

## Implemented Improvements (Full Record)

This section tracks all non-model-architecture improvements completed in this project session.

### 1) Backend reliability and API hardening

- Expanded backend dependencies in `backend/requirements.txt` to include required runtime libs.
- Replaced hardcoded model path logic with portable `Path`-based loading in `backend/model_loader.py`.
- Added safer load-time error handling for model/SHAP artifacts.
- Strengthened request validation in `backend/schema.py` using strict enum-like literals and numeric constraints.
- Updated `backend/app.py` with:
  - env loading (`python-dotenv`)
  - env-driven CORS origins
  - improved exception handling and HTTP error responses
  - threshold query parameter support for `/predict`
  - robust `/explain` response serialization
- Added backend environment file support with allowed origins configuration.

### 2) Backend feature parity fix (critical bug)

- Corrected inference feature engineering in `backend/feature_engineering.py` to match training preprocessing for:
  - `TotalServices`
  - `TechIssueRisk`

This fixed a real training-vs-inference mismatch that could skew outputs.

### 3) Frontend API and typing improvements

- Added frontend env-based API URL configuration in `client/.env`.
- Updated `client/src/services/api.ts` to:
  - use `VITE_API_URL`
  - use stronger request typing
  - return clearer API error details
- Fixed a Vite-breaking syntax issue in `client/src/services/api.ts` (stray brace).
- Tightened form state typing in `client/src/types/formState.ts` with explicit unions.

### 4) Form UX, validation, and accessibility

- Rebuilt `client/src/components/ChurnForm.tsx` with:
  - progressive disclosure sections
  - completion indicators
  - chip-style controls for categorical choices
  - stronger client-side validation and reset behavior
  - improved keyboard/accessibility semantics
  - sticky mobile action bar

### 5) Dashboard and insights redesign

- Reworked `client/src/pages/Dashboard.tsx` with:
  - sticky form + analytics layout
  - KPI/stat ribbon and model meta strip
  - what-if comparison panel (delta + changed fields)
  - prediction method explainer modal
  - improved responsive behavior

### 6) Prediction card redesign

- Rebuilt `client/src/components/PredictionCard.tsx` with:
  - confidence ring visualization
  - risk tier messaging
  - actionable hints
  - loading skeleton states

### 7) Chart storytelling upgrade

- Upgraded `client/src/components/Charts.tsx` with:
  - clearer narrative framing
  - spike annotation treatment
  - segmented risk distribution view
  - mobile-friendly card/swipe behavior
  - CSV export support retained

### 8) Shared UI system refresh

- Restyled shared primitives:
  - `client/src/components/ui/Section.tsx`
  - `client/src/components/ui/KPI.tsx`
  - `client/src/components/ui/Toggle.tsx`
- Introduced unified visual language in `client/src/index.css`:
  - Teal + Copper palette
  - global design tokens
  - typography and atmospheric background treatment
  - motion/animation utilities

### 9) Explainability microcopy tooltips

- Added reusable info icon tooltip component:
  - `client/src/components/ui/InfoTip.tsx`
- Integrated contextual i-tooltips for technical labels in dashboard/cards/charts.

### 10) Repo cleanup

- Removed unused legacy files:
  - `app/main.py`
  - `app/utils.py`

### 11) Runtime sanity checks completed

- Verified endpoint behavior for:
  - `POST /predict`
  - `POST /explain`
  - threshold query behavior
  - invalid payload validation (`422`)
- Verified frontend production build succeeds (`npm run build`).

## Project Structure

- Backend API: `backend/app.py`
- Feature engineering at inference: `backend/feature_engineering.py`
- Model loading: `backend/model_loader.py`
- Frontend app shell: `client/src/pages/Dashboard.tsx`
- API client: `client/src/services/api.ts`

## Local Setup

### Prerequisites

- Node.js 18+
- Python 3.9+

### 1) Backend

```bash
cd backend
python -m venv .venv
# Windows
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m uvicorn app:app --host 127.0.0.1 --port 8000 --reload
```

### 2) Frontend

```bash
cd client
npm install
npm run dev
```

If port `5173` is occupied, Vite may auto-switch to another port (for example `5174`).

### 3) Build frontend

```bash
cd client
npm run build
```

## API Endpoints

- `POST /predict`
- `POST /explain`
- OpenAPI docs: `http://127.0.0.1:8000/docs`

## Screenshots

Old screenshots were removed and replaced with renamed, descriptive assets.

![Dashboard Overview - Teal Copper](client/src/assets/dashboard-overview-teal-copper.png)
![Prediction What-If Analysis Panel](client/src/assets/prediction-whatif-analysis-panel.png)
