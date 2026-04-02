"""
Email integration for sending ticket summaries
Supports Gmail via SMTP (app passwords required)
"""

import logging
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from config import Config

logger = logging.getLogger(__name__)


def send_summary_email(recipient: str, subject: str, body: str) -> bool:
    """
    Send an email summary of a classified ticket
    
    Args:
        recipient: Email address to send to
        subject: Email subject line
        body: Email body (plain text)
        
    Returns:
        True if successful
    """

    if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured, skipping email")
        return False

    try:
        # Create email message
        message = MIMEMultipart()
        message["From"] = Config.EMAIL_FROM
        message["To"] = recipient
        message["Subject"] = subject

        message.attach(MIMEText(body, "plain"))

        logger.debug(f"Sending email to {recipient} via {Config.SMTP_SERVER}:{Config.SMTP_PORT}")

        # Send via SMTP
        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)
            server.send_message(message)

        logger.info(f"Email sent successfully to {recipient}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"SMTP authentication failed: {e}")
        raise
    except smtplib.SMTPException as e:
        logger.error(f"SMTP error: {e}")
        raise
    except Exception as e:
        logger.error(f"Error sending email: {e}")
        raise


def test_email_connection() -> bool:
    """
    Test email configuration
    Attempts to connect to SMTP server
    """

    if not Config.SMTP_USERNAME or not Config.SMTP_PASSWORD:
        logger.warning("SMTP credentials not configured")
        return False

    try:
        logger.info(f"Testing SMTP connection to {Config.SMTP_SERVER}:{Config.SMTP_PORT}")

        with smtplib.SMTP(Config.SMTP_SERVER, Config.SMTP_PORT) as server:
            server.starttls()
            server.login(Config.SMTP_USERNAME, Config.SMTP_PASSWORD)

        logger.info("SMTP connection successful")
        return True

    except Exception as e:
        logger.error(f"SMTP connection test failed: {e}")
        return False
