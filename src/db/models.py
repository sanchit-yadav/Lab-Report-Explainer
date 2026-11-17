"""SQLAlchemy ORM models for Users, Reports, and Biomarker Test Records."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
import uuid

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from src.db.session import Base


def generate_uuid() -> str:
    """Generate canonical UUID v4 string identifier."""
    return str(uuid.uuid4())


def utc_now() -> datetime:
    """Return timezone-aware current UTC datetime."""
    return datetime.now(timezone.utc)


class User(Base):
    """User account model supporting patient, clinician, and admin roles."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    role = Column(String(50), default="patient", nullable=False)  # "patient", "clinician", "admin"
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    reports = relationship("Report", back_populates="user", cascade="all, delete-orphan")
    test_records = relationship("TestRecord", back_populates="user", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<User(id={self.id}, email={self.email}, role={self.role})>"


class Report(Base):
    """Diagnostic laboratory report metadata, status lifecycle, and artifact cache."""

    __tablename__ = "reports"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)
    filename = Column(String(255), nullable=False)
    file_hash = Column(String(64), index=True, nullable=False)
    file_size_bytes = Column(Integer, nullable=False)
    status = Column(String(50), default="queued", index=True, nullable=False)
    progress_pct = Column(Integer, default=0, nullable=False)

    # Extracted metadata
    patient_name = Column(String(255), nullable=True, index=True)
    report_date = Column(String(100), nullable=True)
    lab_name = Column(String(255), nullable=True)

    # Serialized JSON representations
    extracted_data = Column(Text, nullable=True)     # Raw extracted LabReport JSON
    explanation_data = Column(Text, nullable=True)   # Complete ReportExplanation JSON
    pdf_path = Column(String(500), nullable=True)     # Path on disk or blob URL
    error = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    # Relationships
    user = relationship("User", back_populates="reports")
    test_records = relationship("TestRecord", back_populates="report", cascade="all, delete-orphan")

    def __repr__(self) -> str:
        return f"<Report(id={self.id}, user_id={self.user_id}, status={self.status})>"


class TestRecord(Base):
    """Normalized biomarker test observation for longitudinal analytics and trends."""

    __test__ = False  # Prevent pytest from collecting this ORM model as a test case
    __tablename__ = "test_records"

    id = Column(String(36), primary_key=True, default=generate_uuid, index=True)
    report_id = Column(String(36), ForeignKey("reports.id", ondelete="CASCADE"), index=True, nullable=False)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), index=True, nullable=True)

    test_name = Column(String(255), nullable=False, index=True)
    value = Column(Float, nullable=True)
    raw_value = Column(String(100), nullable=True)
    unit = Column(String(50), nullable=True)
    ref_low = Column(Float, nullable=True)
    ref_high = Column(Float, nullable=True)
    ref_raw = Column(String(100), nullable=True)
    flag = Column(String(50), default="unknown", nullable=False)

    # Clinical ontology mapping
    loinc_code = Column(String(50), nullable=True, index=True)
    loinc_name = Column(String(255), nullable=True)
    category = Column(String(100), nullable=True)

    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    # Relationships
    report = relationship("Report", back_populates="test_records")
    user = relationship("User", back_populates="test_records")

    def __repr__(self) -> str:
        return f"<TestRecord(test={self.test_name}, val={self.value} {self.unit}, flag={self.flag})>"
