"""FastAPI HTTP client wrapper for the decoupled Streamlit user interface."""

from __future__ import annotations

import logging
import math
import os
from typing import Any, Dict, List, Optional

import httpx

logger = logging.getLogger("api_client")

FASTAPI_BASE_URL = os.environ.get("FASTAPI_URL", "http://localhost:8000").rstrip("/")


def _sanitize_for_json(data: Any) -> Any:
    """Recursively sanitize data structures to ensure strict JSON compliance (convert NaN/inf/NA to None)."""
    if data is None:
        return None
    if isinstance(data, dict):
        return {k: _sanitize_for_json(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [_sanitize_for_json(item) for item in data]

    try:
        import pandas as pd

        if pd.isna(data):
            return None
    except Exception:
        pass

    if isinstance(data, float):
        if math.isnan(data) or math.isinf(data):
            return None
        return data
    return data


class CDSAPIClient:
    """Client for communicating with the Clinical CDS FastAPI backend microservice."""

    def __init__(self, base_url: str = FASTAPI_BASE_URL, token: Optional[str] = None):
        self.base_url = base_url
        self.token = token

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def register(
        self,
        email: str,
        password: str,
        full_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register a new user account."""
        url = f"{self.base_url}/api/v1/auth/register"
        payload = {
            "email": email,
            "password": password,
            "full_name": full_name,
        }
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            return resp.json()

    def login(self, email: str, password: str) -> Dict[str, Any]:
        """Authenticate user and obtain JWT access token."""
        url = f"{self.base_url}/api/v1/auth/login"
        payload = {"email": email, "password": password}
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
            resp.raise_for_status()
            data = resp.json()
            self.token = data.get("access_token")
            return data

    def get_me(self) -> Dict[str, Any]:
        """Retrieve current authenticated user profile."""
        url = f"{self.base_url}/api/v1/auth/me"
        with httpx.Client(timeout=5.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def upload_report(
        self,
        file_bytes: bytes,
        filename: str,
        explain_all: bool = False,
        auto_confirm: bool = False,
    ) -> Dict[str, Any]:
        """Upload laboratory report document to initiate processing."""
        url = f"{self.base_url}/api/v1/reports/upload"
        params = {
            "explain_all": str(explain_all).lower(),
            "auto_confirm": str(auto_confirm).lower(),
        }
        files = {"file": (filename, file_bytes, "application/pdf")}
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, params=params, files=files, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_job_status(self, job_id: str) -> Dict[str, Any]:
        """Poll job lifecycle status and progress percentage."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/status"
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_extracted_report(self, job_id: str) -> Dict[str, Any]:
        """Retrieve raw extracted biomarkers for human-in-the-loop inspection and editing."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/extracted"
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def confirm_report(
        self,
        job_id: str,
        tests: List[Dict[str, Any]],
        patient_name: Optional[str] = None,
        explain_all: bool = False,
    ) -> Dict[str, Any]:
        """Submit confirmed/edited biomarker parameters to generate clinical explanations."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/confirm"
        payload = {
            "patient_name": patient_name,
            "tests": _sanitize_for_json(tests),
            "explain_all": explain_all,
        }
        with httpx.Client(timeout=20.0) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def get_explanation(self, job_id: str) -> Dict[str, Any]:
        """Fetch final bilingual explanation and panic alerts."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/explanation"
        with httpx.Client(timeout=20.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def download_doctor_brief_pdf(self, job_id: str) -> bytes:
        """Download generated Doctor Discussion Brief PDF."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/pdf"
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(url, headers=self._headers())
            resp.raise_for_status()
            return resp.content

    def ask_question(
        self,
        job_id: str,
        question: str,
        chat_history: Optional[List[Dict[str, str]]] = None,
    ) -> Dict[str, Any]:
        """Submit clinical question contextualized with patient report."""
        url = f"{self.base_url}/api/v1/reports/{job_id}/qa"
        payload = {
            "question": question,
            "chat_history": chat_history or [],
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(url, json=payload, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def list_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        """List recent jobs associated with the current user."""
        url = f"{self.base_url}/api/v1/reports"
        params = {"limit": limit}
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params, headers=self._headers())
            resp.raise_for_status()
            return resp.json()

    def delete_report(self, job_id: str) -> Dict[str, Any]:
        """Permanently delete a laboratory report by ID."""
        url = f"{self.base_url}/api/v1/reports/{job_id}"
        with httpx.Client(timeout=10.0) as client:
            resp = client.delete(url, headers=self._headers())
            resp.raise_for_status()
            return resp.json()
