"""
Data models for ticket classification and validation
Uses Pydantic for type safety and validation
"""

from typing import Literal
from pydantic import BaseModel, EmailStr, Field


class TicketRequest(BaseModel):
    """Incoming support ticket from webhook"""

    email: EmailStr = Field(..., description="Customer email address")
    subject: str = Field(..., min_length=5, max_length=200, description="Ticket subject")
    description: str = Field(
        ..., min_length=10, max_length=5000, description="Ticket description"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "email": "customer@example.com",
                "subject": "Cannot login to my account",
                "description": "I'"'"'ve been locked out of my account for the past 2 hours. I'"'"'ve tried resetting my password but haven'"'"'t received the reset email.",
            }
        }


class Classification(BaseModel):
    """Claude'"'"'s classification of a ticket"""

    urgency: Literal["urgent", "normal", "low"] = Field(
        description="Priority level of the ticket"
    )
    category: Literal["technical", "billing", "feature-request"] = Field(
        description="Category of the ticket"
    )
    summary: str = Field(
        description="Brief summary of the issue and suggested resolution"
    )

    class Config:
        json_schema_extra = {
            "example": {
                "urgency": "urgent",
                "category": "technical",
                "summary": "Customer is locked out of their account. Likely a forgotten password issue. Recommend: 1) Verify account exists, 2) Manually reset password, 3) Send reset instructions via SMS as backup.",
            }
        }
