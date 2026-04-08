from sqlalchemy import Column, String, Float, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship
import uuid
from datetime import datetime
from app.db.base_class import Base

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    name = Column(String, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # Extended Profile
    whatsapp_number = Column(String, nullable=True)
    address = Column(String, nullable=True)
    blood_type = Column(String, nullable=True)
    emergency_contact_name = Column(String, nullable=True)
    emergency_contact_phone = Column(String, nullable=True)
    notify_sms = Column(String, nullable=True, default="true")
    notify_email = Column(String, nullable=True, default="true")
    notify_report_ready = Column(String, nullable=True, default="true")
    notify_high_risk = Column(String, nullable=True, default="true")

    reports = relationship("Report", back_populates="owner", cascade="all, delete")
    health_metrics = relationship("HealthMetric", back_populates="owner", cascade="all, delete")
    emergency_contacts = relationship("EmergencyContact", back_populates="user", cascade="all, delete")
    medications = relationship("Medication", back_populates="user", cascade="all, delete")

class Report(Base):
    __tablename__ = "reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    file_url = Column(String, nullable=False)
    file_type = Column(String, nullable=False)
    uploaded_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="reports")
    health_metrics = relationship("HealthMetric", back_populates="report", cascade="all, delete")

class HealthMetric(Base):
    __tablename__ = "health_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    metric_name = Column(String, index=True, nullable=False)
    metric_value = Column(Float, nullable=True)
    unit = Column(String, nullable=True)
    recorded_at = Column(DateTime, default=datetime.utcnow)

    report = relationship("Report", back_populates="health_metrics")
    owner = relationship("User", back_populates="health_metrics")

class EmergencyContact(Base):
    __tablename__ = "emergency_contacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    name = Column(String, nullable=False)
    phone_number = Column(String, nullable=False)
    relation = Column(String, nullable=True)

    user = relationship("User", back_populates="emergency_contacts")

class Medication(Base):
    __tablename__ = "medications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    medicine_name = Column(String, nullable=False)
    dosage = Column(String, nullable=False)
    time = Column(String, nullable=False)  # Cron format or simple HH:MM string
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="medications")

class AgentLog(Base):
    """Tracks each agent's execution lifecycle per report for full observability."""
    __tablename__ = "agent_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True)
    report_id = Column(UUID(as_uuid=True), ForeignKey("reports.id", ondelete="CASCADE"), nullable=False, index=True)
    agent_name = Column(String, nullable=False)             # e.g. "ReportAnalyzerAgent"
    status = Column(String, nullable=False)                 # "started" | "completed" | "failed"
    message = Column(String, nullable=True)                 # Optional detail / error text
    duration_ms = Column(Float, nullable=True)              # Execution time in milliseconds
    timestamp = Column(DateTime, default=datetime.utcnow, nullable=False)
