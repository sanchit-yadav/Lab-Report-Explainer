"""Tests for the frontend API client (CDSAPIClient)."""

from unittest.mock import MagicMock, patch

from src.frontend.api_client import CDSAPIClient


def test_api_client_initialization_and_headers():
    """Verify headers include Authorization only when token is set."""
    client_no_token = CDSAPIClient(base_url="http://testserver")
    assert client_no_token._headers() == {}

    client_with_token = CDSAPIClient(base_url="http://testserver", token="sample_jwt_123")
    assert client_with_token._headers() == {"Authorization": "Bearer sample_jwt_123"}


def test_api_client_auth_methods():
    """Verify registration, login, and profile fetching methods."""
    client = CDSAPIClient(base_url="http://testserver")

    with patch("httpx.Client.post") as mock_post, patch("httpx.Client.get") as mock_get:
        # Register
        mock_post.return_value = MagicMock(
            status_code=201,
            json=lambda: {"access_token": "tok1", "user": {"email": "a@b.com"}},
            raise_for_status=lambda: None,
        )
        res_reg = client.register("a@b.com", "Password123!", "Alice")
        assert res_reg["access_token"] == "tok1"

        # Login
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"access_token": "tok2", "user": {"email": "a@b.com"}},
            raise_for_status=lambda: None,
        )
        res_login = client.login("a@b.com", "Password123!")
        assert res_login["access_token"] == "tok2"
        assert client.token == "tok2"

        # Get Me
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"id": "uid1", "email": "a@b.com"},
            raise_for_status=lambda: None,
        )
        res_me = client.get_me()
        assert res_me["id"] == "uid1"


def test_api_client_report_workflow_methods():
    """Verify upload, status polling, extraction review, and confirmation methods."""
    client = CDSAPIClient(base_url="http://testserver", token="tok123")

    with patch("httpx.Client.post") as mock_post, patch("httpx.Client.get") as mock_get:
        # Upload
        mock_post.return_value = MagicMock(
            status_code=202,
            json=lambda: {"job_id": "job-abc", "status": "queued"},
            raise_for_status=lambda: None,
        )
        res_upload = client.upload_report(b"%PDF", "test.pdf", auto_confirm=False)
        assert res_upload["job_id"] == "job-abc"

        # Get Status
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"job_id": "job-abc", "status": "review_needed", "progress_pct": 40},
            raise_for_status=lambda: None,
        )
        res_status = client.get_job_status("job-abc")
        assert res_status["status"] == "review_needed"

        # Get Extracted
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: {"job_id": "job-abc", "total_tests": 1, "tests": [{"test_name": "Hemoglobin"}]},
            raise_for_status=lambda: None,
        )
        res_ext = client.get_extracted_report("job-abc")
        assert res_ext["total_tests"] == 1

        # Confirm
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"job_id": "job-abc", "status": "flagging", "confirmed_tests_count": 1},
            raise_for_status=lambda: None,
        )
        res_conf = client.confirm_report("job-abc", [{"test_name": "Hemoglobin", "value": 14.2}])
        assert res_conf["confirmed_tests_count"] == 1

        # Download PDF
        mock_get.return_value = MagicMock(
            status_code=200,
            content=b"%PDF-DoctorBriefData",
            raise_for_status=lambda: None,
        )
        pdf_bytes = client.download_doctor_brief_pdf("job-abc")
        assert pdf_bytes == b"%PDF-DoctorBriefData"

        # Ask question
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"answer_en": "Oxygen carrier", "blocked": False},
            raise_for_status=lambda: None,
        )
        qa_res = client.ask_question("job-abc", "What is hemoglobin?")
        assert qa_res["answer_en"] == "Oxygen carrier"


def test_api_client_confirm_report_sanitizes_nan_and_na():
    """Verify confirm_report cleanly sanitizes float('nan'), inf, and pandas NA before HTTP POST."""
    import pandas as pd
    client = CDSAPIClient(base_url="http://testserver", token="tok123")

    with patch("httpx.Client.post") as mock_post:
        mock_post.return_value = MagicMock(
            status_code=200,
            json=lambda: {"job_id": "job-nan", "status": "flagging", "confirmed_tests_count": 2},
            raise_for_status=lambda: None,
        )
        tests_with_nan = [
            {"test_name": "Test1", "value": float("nan"), "ref_low": None, "ref_high": float("inf")},
            {"test_name": "Test2", "value": 15.0, "ref_low": pd.NA, "ref_high": float("nan")},
        ]
        res = client.confirm_report("job-nan", tests=tests_with_nan)
        assert res["confirmed_tests_count"] == 2

        # Verify the payload passed to httpx.Client.post was properly sanitized
        call_kwargs = mock_post.call_args.kwargs
        json_payload = call_kwargs["json"]
        assert json_payload["tests"][0]["value"] is None
        assert json_payload["tests"][0]["ref_high"] is None
        assert json_payload["tests"][1]["ref_low"] is None
        assert json_payload["tests"][1]["ref_high"] is None
        assert json_payload["tests"][1]["value"] == 15.0


def test_api_client_delete_and_list_reports():
    """Verify list_reports and delete_report methods in CDSAPIClient."""
    client = CDSAPIClient(base_url="http://testserver", token="tok123")

    with patch("httpx.Client.get") as mock_get, patch("httpx.Client.delete") as mock_delete:
        mock_get.return_value = MagicMock(
            status_code=200,
            json=lambda: [{"job_id": "job-1", "status": "ready"}],
            raise_for_status=lambda: None,
        )
        reports = client.list_reports(limit=10)
        assert len(reports) == 1
        assert reports[0]["job_id"] == "job-1"

        mock_delete.return_value = MagicMock(
            status_code=200,
            json=lambda: {"job_id": "job-1", "status": "deleted"},
            raise_for_status=lambda: None,
        )
        del_res = client.delete_report("job-1")
        assert del_res["status"] == "deleted"
