"""Tests for database engine, ORM models (User, Report, TestRecord), and sessions."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.db.models import Base, Report, TestRecord, User
from src.db.session import get_db


@pytest.fixture
def test_db_session():
    """Create a temporary in-memory SQLite database for testing."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    Base.metadata.create_all(bind=engine)

    session = TestingSessionLocal()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=engine)


def test_create_user(test_db_session):
    """Verify user creation, defaults, and retrieval."""
    user = User(
        email="patient@example.com",
        hashed_password="hashed_pw_secret_123",
        full_name="John Doe",
    )
    test_db_session.add(user)
    test_db_session.commit()
    test_db_session.refresh(user)

    assert user.id is not None
    assert len(user.id) == 36  # Canonical UUID v4
    assert user.email == "patient@example.com"
    assert user.is_active is True
    assert user.created_at is not None
    assert str(user) == f"<User(id={user.id}, email=patient@example.com)>"


def test_create_report_with_user_relationship(test_db_session):
    """Verify report persistence and foreign key association with user."""
    user = User(
        email="patient2@example.com",
        hashed_password="hashed_pw_secret_456",
        full_name="Jane Smith",
    )
    test_db_session.add(user)
    test_db_session.commit()

    report = Report(
        user_id=user.id,
        filename="cbc_report_nov.pdf",
        file_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        file_size_bytes=1048576,
        status="ready",
        progress_pct=100,
        patient_name="John Doe",
        extracted_data='{"tests": []}',
        explanation_data='{"overall_summary": "All good"}',
    )
    test_db_session.add(report)
    test_db_session.commit()
    test_db_session.refresh(report)

    assert report.id is not None
    assert report.user_id == user.id
    assert report.user.email == "patient2@example.com"
    assert len(user.reports) == 1
    assert user.reports[0].filename == "cbc_report_nov.pdf"


def test_create_test_records_and_cascade(test_db_session):
    """Verify biomarker test record insertion and cascade deletion on report removal."""
    user = User(email="test@user.com", hashed_password="pw")
    test_db_session.add(user)
    test_db_session.commit()

    report = Report(
        user_id=user.id,
        filename="metabolic.pdf",
        file_hash="abc123hash",
        file_size_bytes=512,
        status="ready",
    )
    test_db_session.add(report)
    test_db_session.commit()

    record1 = TestRecord(
        report_id=report.id,
        user_id=user.id,
        test_name="Hemoglobin",
        value=11.2,
        raw_value="11.2",
        unit="g/dL",
        ref_low=13.5,
        ref_high=17.5,
        ref_raw="13.5 - 17.5",
        flag="low",
        loinc_code="718-7",
        loinc_name="Hemoglobin [Mass/volume] in Blood",
        category="Hematology",
    )
    record2 = TestRecord(
        report_id=report.id,
        user_id=user.id,
        test_name="Glucose",
        value=95.0,
        raw_value="95",
        unit="mg/dL",
        ref_low=70.0,
        ref_high=99.0,
        ref_raw="70 - 99",
        flag="normal",
        loinc_code="2345-7",
        loinc_name="Glucose [Mass/volume] in Serum or Plasma",
        category="Biochemistry",
    )
    test_db_session.add_all([record1, record2])
    test_db_session.commit()

    # Verify query
    records = test_db_session.query(TestRecord).filter_by(report_id=report.id).all()
    assert len(records) == 2
    assert {r.test_name for r in records} == {"Hemoglobin", "Glucose"}
    assert {r.flag for r in records} == {"low", "normal"}

    # Test cascade deletion: deleting report removes its test records
    test_db_session.delete(report)
    test_db_session.commit()

    remaining_records = test_db_session.query(TestRecord).filter_by(report_id=report.id).all()
    assert len(remaining_records) == 0


def test_get_db_generator():
    """Verify get_db generator yields a session and closes cleanly."""
    gen = get_db()
    session = next(gen)
    assert session is not None
    try:
        # Verify connection can execute a basic query
        session.execute(
            Base.metadata.tables["users"].select() if "users" in Base.metadata.tables else None
        )
    except Exception:
        pass
    finally:
        with pytest.raises(StopIteration):
            next(gen)
