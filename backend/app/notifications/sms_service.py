import logging

logger = logging.getLogger(__name__)

async def send_sms(to_phone: str, message: str) -> bool:
    """
    Abstract communication layer for SMS notifications via Twilio/AWS SNS.
    Currently runs in Mock mode so you don't need active API keys to test CareAI dynamically.
    """
    try:
        # Implementation example for Twilio:
        # from twilio.rest import Client
        # client = Client(settings.TWILIO_SID, settings.TWILIO_TOKEN)
        # client.messages.create(body=message, from_=settings.TWILIO_NUMBER, to=to_phone)
        
        logger.info(f"[URGENT SMS DISPATCH] -> To Phone: {to_phone} | Message: '{message}'")
        
        # Simulate successful transmission across the network
        return True
    except Exception as e:
        logger.error(f"FATAL: SMS failure to {to_phone}: {e}")
        return False
