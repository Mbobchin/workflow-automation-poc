"""
Claude API integration for intelligent ticket classification
Uses Claude to analyze and classify incoming support tickets
"""

import json
import logging
from typing import Optional

from anthropic import Anthropic

from config import Config
from models import TicketRequest, Classification

logger = logging.getLogger(__name__)

# Initialize Anthropic client
client = Anthropic(api_key=Config.ANTHROPIC_API_KEY)


def classify_ticket(ticket: TicketRequest) -> Classification:
    """
    Use Claude to classify a support ticket
    
    Returns urgency level, category, and a summary/action plan
    """

    prompt = f"""You are a support ticket classification system. Analyze the following ticket and provide:

1. URGENCY: Must be exactly one of: "urgent", "normal", or "low"
   - urgent: System down, security issue, payment failure, can'"'"'t access critical features
   - normal: Standard support request, feature questions, general issues
   - low: Feature requests, minor bugs, documentation questions

2. CATEGORY: Must be exactly one of: "technical", "billing", or "feature-request"

3. SUMMARY: A 2-3 sentence summary of the issue and recommended next steps

Ticket Details:
From: {ticket.email}
Subject: {ticket.subject}
Description: {ticket.description}

Respond ONLY with a valid JSON object (no markdown, no code blocks) with keys: urgency, category, summary
Example:
{{"urgency": "urgent", "category": "technical", "summary": "Customer reports cannot access their account. This is a high-priority issue that needs immediate attention. Recommended: verify account status, check for lockouts, issue temporary password."}}
"""

    try:
        response = client.messages.create(
            model="claude-opus-4-1",
            max_tokens=500,
            messages=[{"role": "user", "content": prompt}],
        )

        # Extract the response text
        response_text = response.content[0].text.strip()

        logger.debug(f"Claude response: {response_text}")

        # Parse JSON response
        try:
            parsed = json.loads(response_text)
        except json.JSONDecodeError:
            # If Claude returns markdown code block, extract JSON
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0].strip()
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0].strip()
            parsed = json.loads(response_text)

        # Validate and create Classification object
        classification = Classification(**parsed)

        logger.info(
            f"Classified ticket: urgency={classification.urgency}, "
            f"category={classification.category}"
        )

        return classification

    except Exception as e:
        logger.error(f"Error classifying ticket: {e}")
        raise


def get_suggested_action(classification: Classification) -> str:
    """
    Get AI-suggested next actions based on classification
    Useful for drafting responses or escalation
    """

    prompt = f"""Based on this ticket classification:
- Urgency: {classification.urgency}
- Category: {classification.category}

Suggest 3 concrete next actions for the support team. Be specific and actionable.
Format as a numbered list."""

    try:
        response = client.messages.create(
            model="claude-opus-4-1",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        return response.content[0].text

    except Exception as e:
        logger.error(f"Error getting suggested actions: {e}")
        return "Unable to generate suggested actions"
