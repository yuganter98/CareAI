import logging

logger = logging.getLogger(__name__)

async def send_email(to_email: str, subject: str, message: str) -> bool:
    """
    Abstract communication layer for Email notifications via SMTP/SendGrid.
    """
    try:
        # Implementation example for python SMTP:
        # import smtplib
        # server = smtplib.SMTP('smtp.gmail.com', 587)
        # server.sendmail(settings.SENDER_EMAIL, to_email, msg)
        
        logger.info(f"[EMAIL DISPATCH] -> To: {to_email} | Subject: '{subject}' | Body: '{message}'")
        
        return True
    except Exception as e:
        logger.error(f"FATAL: Email failure to {to_email}: {e}")
        return False
