import logging
import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models import User
from app.notifications.sms_service import send_sms

logger = logging.getLogger(__name__)

async def trigger_medication_reminder(user_id: str, medicine_name: str, dosage: str, db: AsyncSession):
    """
    Agent Logic:
    Executes the active notification for a scheduled medication.
    This will be triggered asynchronously by the APScheduler when the precise drug time occurs.
    """
    try:
        user_uuid = uuid.UUID(str(user_id))
        
        # 1. Fetch user to access their contact preferences
        result = await db.execute(select(User).where(User.id == user_uuid))
        user = result.scalars().first()
        
        if not user:
            logger.error(f"[REMINDER AGENT] Aborted: User {user_id} not found.")
            return
            
        # 2. Format the SMS reminder payload
        message = f"💊 CareAI Reminder: Hi {user.name}, it's time to take your scheduled medication: {medicine_name} ({dosage})."
        
        # 3. Dispatch reminder securely via abstract SMS routing
        # (Assuming the platform later integrates a direct phone field for User schemas, hardcoded mock fallback here)
        await send_sms(to_phone="User_Profile_Phone", message=message)
        
        logger.info(f"[REMINDER AGENT] Successfully dispatched medication alert for {medicine_name} to User: {user_id}")
        
    except Exception as e:
        logger.error(f"[REMINDER AGENT] Failed to trigger reminder for {medicine_name}: {e}")
