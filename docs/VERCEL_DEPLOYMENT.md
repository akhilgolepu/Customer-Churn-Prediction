# Vercel Frontend Deployment Guide

## Pre-Deployment Checklist

### ✅ Frontend Status

- [x] React 19.2 + TypeScript configured
- [x] Vite 7 build system ready
- [x] Tailwind CSS + PostCSS configured
- [x] Environment variable support via `VITE_API_URL`
- [x] API service uses env fallback
- [x] Build script tested locally: `npm run build`
- [x] `vercel.json` configured
- [x] `.vercelignore` configured

### ⚠️ Backend Status (Required)

- Backend must be deployed first (Render/Koyeb)
- Get backend URL: `https://your-backend.onrender.com`
- Required for `VITE_API_URL` environment variable

---

## Step 1: Prepare Backend URL

The frontend needs your backend API URL. You must deploy the backend first or have the URL ready.

**Backend Deployment Options:**

1. **Render** (recommended): https://dashboard.render.com
2. **Koyeb**: https://app.koyeb.com

Once backend is running, you'll have a URL like:

```
https://churn-backend-xxxx.onrender.com
```

---

## Step 2: Connect GitHub to Vercel

1. Go to https://vercel.com/new
2. Click **Import Git Repository**
3. Select your GitHub repository
4. Choose **Vercel** when prompted for your Git provider
5. In **Project Settings**:
   - Set **Framework Preset** to `Vite`
   - Set **Root Directory** to `./client` (or let Vercel auto-detect)

---

## Step 3: Configure Environment Variables

In Vercel dashboard:

1. Go to **Settings** → **Environment Variables**
2. Add this variable:

| Key            | Value                                   | Notes                                |
| -------------- | --------------------------------------- | ------------------------------------ |
| `VITE_API_URL` | `https://your-backend-url.onrender.com` | Replace with your actual backend URL |

**Vercel Environment Stages:**

- Add to: **Production**, **Preview**, **Development**
- (Or just Production if you prefer not to mock in preview)

---

## Step 4: Deploy

1. Click **Deploy** on the Vercel dashboard
2. Wait for build to complete (usually 30-60 seconds)
3. Vercel will report the deployment URL: `https://your-project.vercel.app`

---

## Step 5: Verify Deployment

Once deployed, test from the Vercel URL:

### Test Login

```bash
curl -X POST https://your-project.vercel.app/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "admin123"}'
```

### Test Prediction

```bash
# After getting access token from login
curl -X POST https://your-project.vercel.app/api/v1/predictions/predict \
  -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{...prediction input...}'
```

### Check Frontend Load

Open `https://your-project.vercel.app` in browser and verify:

- [ ] Dashboard loads without 404 errors
- [ ] API calls succeed (check browser Network tab)
- [ ] Login form appears
- [ ] Analytics events fire (check browser Console)

---

## Step 6: Enable Auto-Deployments (Optional)

1. In Vercel **Settings** → **Git** → **Deploy on Push**
2. Enable: "Automatically deploy main branch"
3. Now every push to main triggers a new Vercel deployment

---

## Troubleshooting

### Issue: "Failed to fetch from VITE_API_URL"

**Cause:** Backend API URL is unreachable or not set.

**Fix:**

1. Verify backend is actually running on the URL you specified
2. Check CORS settings on backend:
   ```python
   # In backend/.env or Render env vars:
   ALLOWED_ORIGINS=["https://your-project.vercel.app"]
   ```
3. Check browser Network tab for specific error

### Issue: "Cannot find module X"

**Cause:** Missing dependency or build issue.

**Fix:**

```bash
# Test build locally first
cd client
npm ci
npm run build
```

### Issue: Build succeeds but app is blank

**Cause:** VITE_API_URL not passed during build.

**Fix:**

1. Verify `VITE_API_URL` is set in Vercel env vars (not just secrets)
2. Rebuild with Vercel dashboard "Redeploy" button

---

## Performance Tips

### Enable Caching

In `vercel.json`, add caching headers:

```json
{
  "headers": [
    {
      "source": "/dist/:path*",
      "headers": [
        {
          "key": "cache-control",
          "value": "public, max-age=31536000, immutable"
        }
      ]
    }
  ]
}
```

### Monitor Build Size

Check Vercel Analytics dashboard for:

- Build time
- Output size
- Cold/hot start times

---

## Automation: CI/CD Integration

The GitHub Actions workflow (`.github/workflows/cd.yml`) can:

1. Run tests on push
2. Automatically trigger Vercel deployment on `main`
3. Add Vercel deployment comment to PRs

To enable:

1. Add Vercel environment variables to GitHub secrets:
   - `VERCEL_PROJECT_ID`
   - `VERCEL_ORG_ID`
   - `VERCEL_TOKEN`

2. The CD workflow will:
   - Deploy frontend via Vercel Deploy Hook
   - Deploy backend via Render Deploy Hook
   - Verify both are healthy

---

## Rollback

To rollback to a previous deployment:

1. In Vercel dashboard, go to **Deployments**
2. Find the deployment you want to rollback to
3. Click the **...** menu → **Promote to Production**

---

## Next: Backend + CD Setup

Once Vercel frontend is live:

1. Deploy backend to Render: [Render Deployment Guide](./RENDER_DEPLOYMENT.md)
2. Set up MLflow on DAGsHub: [DAGsHub MLflow Setup](./DAGSHUB_MLFLOW_SETUP.md)
3. Configure GitHub secrets for CD workflow
4. Enable automatic deployments

---

## Quick Reference

| Item             | Value                              |
| ---------------- | ---------------------------------- |
| Frontend         | Vercel                             |
| Build            | `npm run build`                    |
| Output           | `dist/`                            |
| Root Dir         | `./client`                         |
| Framework        | Vite                               |
| Key Env Var      | `VITE_API_URL`                     |
| Default Fallback | `http://127.0.0.1:8000` (dev only) |
