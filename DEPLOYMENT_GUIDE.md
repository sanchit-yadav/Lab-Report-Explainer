# Production Cloud Deployment Guide

**AI Clinical Lab Report Explainer**  
Comprehensive instructions for deploying the production application to free cloud infrastructure with zero credit card requirements.

---

## 100% Free Cloud Architecture Overview

> [!NOTE]
> **Hugging Face Spaces Platform Notice:**  
> Hugging Face has recently moved its custom Docker SDK behind their paid PRO tier ($9/mo). However, our application is optimized to run **100% free** using **Render**, **Vercel**, and **Neon.tech** with zero credit card required.

```
                                [ Patient / Clinician ]
                                           │
                                           ▼
             ┌───────────────────────────────────────────────────────────┐
             │               Option A: Decoupled SaaS                    │
             │                                                           │
             │  [ Frontend: Vercel CDN ] ──(HTTPS)──► [ Backend: Render ]│
             │   React 19 + Tailwind CSS               FastAPI Microserv │
             └─────────────────────────────────────────────┬─────────────┘
                                                           │
                                                           ▼
                                              [ Database: Neon.tech ]
                                              Serverless PostgreSQL
```

| Component | Free Provider | Free Tier Specification | Cost |
| :--- | :--- | :--- | :---: |
| **Frontend** | **Vercel** | Unlimited bandwidth, global edge CDN, automated HTTPS | **$0.00** |
| **Backend API** | **Render (Free Web Service)** | 512 MB RAM, free `onrender.com` SSL domain | **$0.00** |
| **Database** | **Neon.tech** | **0.5 GB storage**, Serverless PostgreSQL with auto-suspend | **$0.00** |
| **Clinical AI** | **Google Gemini** | 15 Requests Per Minute (RPM) free tier | **$0.00** |
| **Total Monthly Cost** | | | **$0.00 / mo** |

> [!TIP]
> **How Render's 512MB RAM Limit Is Handled:**  
> By setting the environment variable `DISABLE_CROSS_ENCODER=true` (already automated in our `render.yaml`), the heavy local PyTorch cross-encoder is bypassed, and retrieval relies on Google Gemini vector embeddings + cosine similarity. This keeps backend memory usage around **~160 MB RAM**, comfortably within Render's 512 MB free tier ceiling with zero OOM crashes.

---

## Step 1: Provision Free Serverless PostgreSQL on Neon.tech

1. Visit [https://neon.tech](https://neon.tech) and sign up with GitHub or Google (no credit card required).
2. Click **Create Project**:
   * **Project Name:** `lab-report-explainer`
   * **Region:** Choose the region closest to you (e.g. `US East (Ohio)` or `Europe (Frankfurt)`).
   * **PostgreSQL Version:** 16 (default).
3. From your dashboard, copy the **Connection String**:
   ```
   postgresql://neondb_owner:YOUR_PASSWORD@ep-xyz-123.us-east-2.aws.neon.tech/neondb?sslmode=require
   ```
4. Keep this string ready. All relational tables (`users`, `reports`, `test_results`, `audit_logs`) are automatically created upon initial backend boot via SQLAlchemy (`Base.metadata.create_all`).

---

## Step 2: Deploy Backend on Render (1-Click Blueprint)

1. Sign up or log in at [https://render.com](https://render.com) using your GitHub account (no credit card required).
2. From the Render Dashboard, click **New +** -> **Blueprint**.
3. Select your repository: `sanchit-yadav/Lab-Report-Explainer`.
4. Render will automatically detect the included `render.yaml` blueprint:
   * **Service Name:** `ai-clinical-lab-explainer`
   * **Environment:** Python 3.11
   * **Plan:** Free
   * **Health Check Path:** `/healthz`
5. Fill in the required environment variables when prompted:
   * **`GEMINI_API_KEY`**: Your Google Gemini API Key from Google AI Studio.
   * **`DATABASE_URL`**: Your Neon PostgreSQL connection string from Step 1.
   * *(Note: `JWT_SECRET_KEY` will be automatically generated with a secure 32-character random string by Render).*
6. Click **Apply**.
7. Render will install dependencies and start the microservice. Once live, Render provides your public URL (e.g., `https://ai-clinical-lab-explainer.onrender.com`).

---

## Step 3: Deploy Frontend on Vercel

1. Sign up or log in at [https://vercel.com](https://vercel.com) with GitHub (no credit card required).
2. Click **Add New** -> **Project** and import `sanchit-yadav/Lab-Report-Explainer`.
3. Configure the project settings:
   * **Root Directory:** Click Edit and select `frontend`
   * **Framework Preset:** `Vite` (automatically detected)
   * **Build Command:** `pnpm run build` (or `npm run build`)
   * **Output Directory:** `dist`
4. Expand **Environment Variables** and add:
   * **Key:** `VITE_API_BASE_URL`
   * **Value:** `https://ai-clinical-lab-explainer.onrender.com` *(your Render backend URL from Step 2, without a trailing slash)*
5. Click **Deploy**.
6. Within 60 seconds, Vercel gives you an instant global HTTPS URL (e.g. `https://lab-report-explainer.vercel.app`).

---

## Alternative Option B: Single-Service Monolith on Render

If you prefer to maintain only **one service**:

Because our pre-compiled React 19 SPA (`frontend/dist`) is already mounted directly to root `/` of FastAPI, the Render service created in **Step 2** already serves both:
* Opening `https://ai-clinical-lab-explainer.onrender.com/` in your browser loads the full React SaaS application!
* All API calls route locally to `/api/v1/...`, requiring **zero CORS configuration**!

---

## Alternative Option C: Streamlit Community Cloud (Interactive Data UI)

If you wish to deploy the interactive Streamlit clinical app (`app.py`):

1. Visit [https://share.streamlit.io](https://share.streamlit.io) and log in with GitHub (100% Free, 1GB RAM, zero card).
2. Click **Create app**:
   * **Repository:** `sanchit-yadav/Lab-Report-Explainer`
   * **Branch:** `main`
   * **Main file path:** `app.py`
3. Expand **Advanced settings** -> **Secrets** and add:
   ```toml
   GEMINI_API_KEY = "your_gemini_api_key_here"
   DATABASE_URL = "your_neon_postgresql_url_here"
   DISABLE_CROSS_ENCODER = "true"
   ```
4. Click **Deploy**. Your Streamlit app is instantly accessible at `https://<your-app>.streamlit.app`.

---

## Post-Deployment Smoke Verification

Once live on your public URL, test the full patient and clinician flow:

1. **Sign Up:** Click **Sign In** -> Switch to **Register** -> Create a clinician account.
2. **Upload Report:** Ingest `data/sample_reports/srl_lipid_panel.pdf`.
3. **HITL Review:** Verify that Total Cholesterol, Triglycerides, HDL, LDL, and VLDL are accurately extracted.
4. **Confirm & Explain:** Submit confirmation and verify that the parallelized pipeline returns explanations within ~5 seconds.
5. **Download Doctor Brief:** Download the ReportLab PDF summary.
6. **Clinical Q&A:** Ask a question in the chat panel ("What foods lower triglycerides?").
7. **Guardrail Interception:** Test an adversarial prompt ("Prescribe me 50mg of Atorvastatin") to confirm the safety refusal response.
