from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from pydantic import BaseModel, Field, model_validator
from datetime import datetime
from typing import Optional
import uuid

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, Medication

router = APIRouter()

class MedicationCreate(BaseModel):
    medicine_name: str = Field(min_length=1, max_length=200)
    dosage: str = Field(min_length=1, max_length=100)
    # 24h 'HH:MM' — the reminder scheduler matches on this exact format
    time: str = Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    start_date: datetime
    end_date: Optional[datetime] = None

    @model_validator(mode="after")
    def check_dates(self):
        if self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self

@router.post("/add", status_code=status.HTTP_201_CREATED)
async def add_medication(
    payload: MedicationCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Inserts a new medication schema requirement mapping to the current user."""
    med = Medication(
        user_id=current_user.id,
        medicine_name=payload.medicine_name,
        dosage=payload.dosage,
        time=payload.time,
        start_date=payload.start_date,
        end_date=payload.end_date
    )
    db.add(med)
    await db.commit()
    await db.refresh(med)
    return med

@router.get("/list")
async def list_medications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetches all actively tracked prescription schedules."""
    result = await db.execute(
        select(Medication).where(Medication.user_id == current_user.id)
    )
    return result.scalars().all()

@router.delete("/{med_id}")
async def delete_medication(
    med_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Kills and deletes an active prescription reminder."""
    try:
        med_uuid = uuid.UUID(med_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid medication ID mapping.")
        
    result = await db.execute(
        select(Medication).where(Medication.id == med_uuid, Medication.user_id == current_user.id)
    )
    med = result.scalars().first()
    
    if not med:
        raise HTTPException(status_code=404, detail="Medication target not found")
        
    await db.delete(med)
    await db.commit()
    return {"message": f"Medication {med.medicine_name} tracking successfully halted and deleted."}
