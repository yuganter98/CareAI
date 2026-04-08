import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import User, EmergencyContact
from app.notifications.sms_service import send_sms
from app.notifications.email_service import send_email

logger = logging.getLogger(__name__)

async def evaluate_and_trigger_emergency(user_id: str, analysis_result: dict, db: AsyncSession):
    """
    Evaluates the analysis result. If risk_level == "HIGH", triggers the entire emergency 
    notification pipeline.
    Designed to be run asynchronously via FastAPI BackgroundTasks so it does not block HTTP responses.
    """
    risk_level = analysis_result.get("risk_level", "").upper()
    
    if risk_level == "HIGH":
        logger.warning(f"[AGENT] HIGH risk detected for {user_id}. Initiating emergency protocols.")
        
        try:
            user_uuid = uuid.UUID(str(user_id))
            
            # Fetch patient
            user_result = await db.execute(select(User).where(User.id == user_uuid))
            user = user_result.scalars().first()
            if not user:
                logger.error(f"[AGENT] Emergency aborted. User {user_id} not found.")
                return
                
            # Fetch assigned emergency contacts
            contact_result = await db.execute(
                select(EmergencyContact).where(EmergencyContact.user_id == user_uuid)
            )
            emergency_contacts = contact_result.scalars().all()
            
            # Formulate action templates
            patient_alert_msg = "⚠️ Health Alert: Your recent CareAI report shows high risk. Please consult a doctor immediately."
            kin_alert_msg = f"⚠️ Emergency Alert: {user.name}'s recent health report indicates high risk. Please check on them immediately."
            
            # 1. Alert the User via Email (Since User schema assumes email only)
            await send_email(
                to_email=user.email,
                subject="URGENT: HIGH RISK Health Report Analyzed by CareAI",
                message=patient_alert_msg
            )
            
            # 2. Alert the Next-of-Kin via SMS
            for contact in emergency_contacts:
                await send_sms(to_phone=contact.phone_number, message=kin_alert_msg)
                
            logger.info(f"[AGENT] Protocol Complete: Emailed patient and SMS texted {len(emergency_contacts)} emergency contacts.")
            
        except Exception as e:
            logger.error(f"[AGENT] Emergency execution failed critically: {e}")
    else:
        logger.info(f"[AGENT] Evaluation cleared. Risk Level: {risk_level}")
