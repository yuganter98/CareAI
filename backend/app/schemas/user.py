from pydantic import BaseModel, EmailStr, field_validator
from uuid import UUID
from datetime import datetime
from typing import Optional

class UserBase(BaseModel):
    name: str
    email: EmailStr

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2:
            raise ValueError("Name must be at least 2 characters")
        if len(v) > 100:
            raise ValueError("Name must be under 100 characters")
        return v

class UserCreate(UserBase):
    password: str

    @field_validator("password")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters")
        if len(v) > 128:
            raise ValueError("Password must be under 128 characters")
        return v

class UserUpdate(BaseModel):
    name: Optional[str] = None
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notify_sms: Optional[str] = None
    notify_email: Optional[str] = None
    notify_report_ready: Optional[str] = None
    notify_high_risk: Optional[str] = None

class UserResponse(UserBase):
    id: UUID
    created_at: datetime
    whatsapp_number: Optional[str] = None
    address: Optional[str] = None
    blood_type: Optional[str] = None
    emergency_contact_name: Optional[str] = None
    emergency_contact_phone: Optional[str] = None
    notify_sms: Optional[str] = "true"
    notify_email: Optional[str] = "true"
    notify_report_ready: Optional[str] = "true"
    notify_high_risk: Optional[str] = "true"
    
    class Config:
        from_attributes = True

class Token(BaseModel):
    access_token: str
    token_type: str

class TokenPayload(BaseModel):
    sub: Optional[str] = None
