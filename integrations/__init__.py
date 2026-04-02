"""
Integrations package - Third-party service integrations
"""

from .claude import classify_ticket
from .slack import post_to_slack
from .email import send_summary_email

__all__ = ["classify_ticket", "post_to_slack", "send_summary_email"]
