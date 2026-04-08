import logging
from datetime import datetime
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy.future import select

from app.db.session import async_session_maker
from app.db.models import Medication
from app.agents.reminder_agent import trigger_medication_reminder

logger = logging.getLogger(__name__)

# Global Singleton for Background Event Loop
scheduler = AsyncIOScheduler()

async def check_medications_job():
    """
    Native Background Job triggered strictly every minute.
    Synchronizes the server clock with Postgres and executes Action Agents on match.
    """
    now = datetime.utcnow()
    # E.g. expected format stored in Postgres: '08:00' or '14:30'
    current_time_str = now.strftime("%H:%M") 
    
    async with async_session_maker() as db:
        # Fetch active drugs securely for this minute
        result = await db.execute(
            select(Medication)
            .where(Medication.time == current_time_str)
            .where(Medication.start_date <= now)
        )
        meds = result.scalars().all()
        
        for med in meds:
            # Skip expired prescriptions
            if med.end_date and med.end_date < now:
                continue
                
            # Asynchronously fire the SMS layer through the Medication Reminder Agent!
            await trigger_medication_reminder(
                user_id=str(med.user_id),
                medicine_name=med.medicine_name,
                dosage=med.dosage,
                db=db
            )

def start_scheduler():
    """
    Starts the native AsyncIOScheduler loop. 
    To be injected cleanly into FastAPI's lifespan bootup logic.
    """
    if not scheduler.running:
        # Check active medications automatically every single minute via internal cron
        scheduler.add_job(check_medications_job, "cron", minute="*")
        scheduler.start()
        logger.info("[SCHEDULER] CareAI Background cron loop initialized successfully.")
