from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.db.session import get_db
from app.db.models import User, EmergencyContact
from app.agents.emergency_agent import evaluate_and_trigger_emergency

router = APIRouter()

class EmergencyContactCreate(BaseModel):
    name: str
    phone_number: str
    relation: str = None

@router.post("/add-contact", status_code=status.HTTP_201_CREATED)
async def add_emergency_contact(
    payload: EmergencyContactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Saves a new patient next-of-kin configuration strictly to their DB ID."""
    contact = EmergencyContact(
        user_id=current_user.id,
        name=payload.name,
        phone_number=payload.phone_number,
        relation=payload.relation
    )
    db.add(contact)
    await db.commit()
    await db.refresh(contact)
    return {"message": "Emergency contact added successfully", "contact_id": contact.id}

@router.post("/trigger-alert")
async def trigger_manual_alert(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Panic Button: Manually triggers the overarching emergency pipeline for immediate manual testing.
    Forces 'HIGH' risk payload into the dispatch pipeline dynamically.
    """
    mock_high_risk_payload = {
        "risk_level": "HIGH",
        "summary": "Manual panic button activated by patient.",
        "suggested_actions": ["Immediate physical assistance required."]
    }
    
    # Trigger the agent directly (Note: Production deployments offload this to Celery beat queues)
    await evaluate_and_trigger_emergency(str(current_user.id), mock_high_risk_payload, db)
    
    return {"message": "Emergency notification pipeline triggered successfully."}
