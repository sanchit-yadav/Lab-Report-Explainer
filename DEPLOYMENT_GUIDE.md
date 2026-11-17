# Production Cloud Deployment Guide

**AI Clinical Lab Report Explainer**  
Comprehensive instructions for deploying the production application to free cloud infrastructure with zero credit card requirements.

---

## Architecture Overview

```
                                [ Patient / Clinician ]
                                           │
                                           ▼
             ┌───────────────────────────────────────────────────────────┐
             │            Option A: Decoupled (Recommended)              │
             │                                                           │
             │  [ Frontend: Vercel CDN ] ──(HTTPS)──► [ Backend: HF Space]│
             │   React 19 + Tailwind CSS               FastAPI + PyTorch │
             └─────────────────────────────────────────────┬─────────────┘
                                                           │
                                                           ▼
                                              [ Database: Neon.tech ]
                                              Serverless PostgreSQL
```

| Component | Recommended Free Provider | Free Tier Specification | Cost |
| :--- | :--- | :--- | :---: |
| **Frontend** | **Vercel** | Unlimited bandwidth, global edge CDN, automatic HTTPS | **$0.00** |
| **Backend API** | **Hugging Face Spaces** | **16 GB RAM**, 2 vCPUs, Docker runtime, persistent URL | **$0.00** |
| **Database** | **Neon.tech** | **0.5 GB storage**, Serverless PostgreSQL with auto-suspend | **$0.00** |
| **Clinical AI** | **Google Gemini** | 15 Requests Per Minute (RPM) free tier | **$0.00** |
| **Total Monthly Cost** | | | **$0.00 / mo** |

> [!TIP]
> **Why Hugging Face Spaces over Render for the Backend?**  
> Render's free tier imposes a strict **512 MB RAM** limit. Loading PyTorch and Sentence-Transformers consumes 650MB–850MB RAM, causing immediate Out-Of-Memory (OOM SIGKILL 137) crashes. Hugging Face Spaces provides **16 GB RAM** on its free tier, allowing PyTorch, ChromaDB, and the CDS pipeline to execute effortlessly with zero memory bottlenecks.

---

## Step 1: Provision Free Serverless PostgreSQL on Neon.tech

1. Visit [https://neon.tech](https://neon.tech) and sign up with GitHub or Google (no credit card required).
2. Click **Create Project**:
   * **Project Name:** `lab-report-explainer`
   * **Region:** Choose the region closest to your users (e.g., `US East (Ohio)` or `Europe (Frankfurt)`).
   * **PostgreSQL Version:** 16 (default).
3. From the dashboard, copy the **Connection String**:
   ```
   postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz-123.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Save this string. The backend will automatically create all tables (`users`, `reports`, `test_results`, `audit_logs`) upon first startup using `Base.metadata.create_all`.

---

## Step 2: Deploy Backend to Hugging Face Spaces (Docker)

1. Sign up or log in at [https://huggingface.co](https://huggingface.co).
2. Click **New Space** ([https://huggingface.co/new-space](https://huggingface.co/new-space)):
   * **Space name:** `ai-lab-report-explainer`
   * **License:** `apache-2.0` (or `mit`)
   * **Space SDK:** Select **Docker** -> **Blank**
   * **Space hardware:** **Free CPU (2 vCPU, 16 GB RAM)**
   * **Visibility:** Public (or Private)
3. Under **Settings** -> **Variables and Secrets**, add the following:

   | Type | Key | Value / Description |
   | :--- | :--- | :--- |
   | **Secret** | `GEMINI_API_KEY` | Your Google Gemini API Key from Google AI Studio |
   | **Secret** | `JWT_SECRET_KEY` | A 32+ character random string (e.g. run `openssl rand -hex 32`) |
   | **Secret** | `DATABASE_URL` | Your Neon PostgreSQL connection string from Step 1 |
   | **Variable** | `ENVIRONMENT` | `production` |
   | **Variable** | `CORS_ORIGIN_REGEX` | `https://.*\.vercel\.app` |
   | **Variable** | `DISABLE_CROSS_ENCODER` | `false` |

4. Push your repository to the Hugging Face Space git remote:
   ```bash
   git remote add space https://huggingface.co/spaces/YOUR_USERNAME/ai-lab-report-explainer
   git push space main
   ```
5. Hugging Face will automatically execute the multi-stage `Dockerfile`.
   * **Liveness Probe:** `https://YOUR_USERNAME-ai-lab-report-explainer.hf.space/healthz`
   * **Interactive API Docs:** `https://YOUR_USERNAME-ai-lab-report-explainer.hf.space/docs`

> [!NOTE]
> Hugging Face Spaces sets `PORT=7860`. Our `Dockerfile` dynamically binds to `${PORT:-8000}`, so it runs out-of-the-box without extra port configuration.

---

## Step 3: Deploy Frontend to Vercel

1. Sign up or log in at [https://vercel.com](https://vercel.com).
2. Click **Add New** -> **Project** and import your Git repository.
3. Configure the project build settings:
   * **Root Directory:** Click edit and select `frontend`
   * **Framework Preset:** `Vite` (automatically detected)
   * **Build Command:** `pnpm run build` (or `npm run build`)
   * **Output Directory:** `dist`
4. Expand **Environment Variables** and add:
   * **Key:** `VITE_API_BASE_URL`
   * **Value:** `https://YOUR_USERNAME-ai-lab-report-explainer.hf.space` (your backend URL from Step 2, without a trailing slash)
5. Click **Deploy**.
6. Within 60 seconds, Vercel will assign a public HTTPS URL (e.g., `https://lab-report-explainer.vercel.app`).

---

## Option B: Single-Container Monolithic Deployment

If you prefer deploying a single service instead of separating frontend and backend:

The backend container **already includes the pre-compiled React 19 SPA** inside `frontend/dist` mounted directly at the root path (`/`).

1. Deploy the Docker container to Hugging Face Spaces (or Render) as described in Step 2.
2. Opening `https://YOUR_USERNAME-ai-lab-report-explainer.hf.space/` in any browser will directly load the full SaaS React application!
3. All API calls default to relative paths (`/api/v1/...`), eliminating all CORS configuration requirements.

---

## Step 4: Post-Deployment Smoke Verification

Once deployed, verify the full user workflow on your live production URL:

1. **User Registration:** Navigate to `/` -> Click **Sign In** -> Switch to **Register** -> Create an account.
2. **Report Ingestion:** Upload `data/sample_reports/srl_lipid_panel.pdf`.
3. **HITL Review:** Review extracted analytes (Total Cholesterol, Triglycerides, HDL, LDL, VLDL).
4. **Post-HITL Speed:** Click **Confirm & Explain** and verify response completes in under 6 seconds.
5. **Doctor Discussion Brief:** Click **Download PDF** to inspect the ReportLab summary.
6. **Clinical Q&A:** Ask a question in the chat panel ("What dietary changes help lower LDL?").
7. **Guardrail Check:** Test an adversarial request ("Can you prescribe me 50mg of Atorvastatin?") and confirm safe refusal.
8. **Persistence Check:** Restart the container on Hugging Face Spaces; log back in and verify that your report history remains intact from Neon PostgreSQL.
