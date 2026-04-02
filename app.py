"""
Support Ticket Router - Webhook-triggered workflow automation POC
Routes incoming support tickets using Claude classification to appropriate channels
"""

import json
import logging
from datetime import datetime
from typing import Dict, Any

from flask import Flask, request, jsonify
from pydantic import ValidationError

from config import Config
from models import TicketRequest, Classification
from integrations.claude import classify_ticket
from integrations.slack import post_to_slack
from integrations.email import send_summary_email

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

# Routing map: (urgency, category) -> slack_channel
ROUTING_MAP = {
    ("urgent", "technical"): "#incidents",
    ("urgent", "billing"): "#billing-urgent",
    ("urgent", "feature-request"): "#feature-requests",
    ("normal", "technical"): "#support",
    ("normal", "billing"): "#billing",
    ("normal", "feature-request"): "#feature-requests",
    ("low", "technical"): "#support",
    ("low", "billing"): "#billing",
    ("low", "feature-request"): "#feature-requests",
}


@app.route("/health", methods=["GET"])
def health():
    """Health check endpoint"""
    return jsonify({"status": "healthy"}), 200


@app.route("/webhook/ticket", methods=["POST"])
def handle_ticket():
    """
    Webhook endpoint to receive support tickets
    
    Expected JSON:
    {
        "email": "customer@example.com",
        "subject": "Cannot login",
        "description": "I'"'"'ve been locked out of my account..."
    }
    """
    try:
        # Validate request JSON
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({"error": "Empty request body"}), 400
        except Exception as e:
            logger.error(f"Failed to parse JSON: {e}")
            return jsonify({"error": "Invalid JSON"}), 400

        # Parse and validate ticket data
        try:
            ticket = TicketRequest(**payload)
        except ValidationError as e:
            logger.error(f"Validation error: {e}")
            return jsonify({"error": "Invalid ticket data", "details": e.errors()}), 422

        logger.info(f"Received ticket from {ticket.email}: {ticket.subject}")

        # Step 1: Classify the ticket using Claude
        try:
            classification = classify_ticket(ticket)
            logger.info(
                f"Classified ticket: urgency={classification.urgency}, "
                f"category={classification.category}"
            )
        except Exception as e:
            logger.error(f"Classification failed: {e}")
            return jsonify({"error": "Failed to classify ticket"}), 500

        # Step 2: Determine routing
        slack_channel = ROUTING_MAP.get(
            (classification.urgency, classification.category), "#support"
        )
        logger.info(f"Routing to {slack_channel}")

        # Step 3: Post to Slack
        try:
            slack_message = format_slack_message(ticket, classification, slack_channel)
            post_to_slack(slack_channel, slack_message)
            logger.info(f"Posted to Slack channel {slack_channel}")
        except Exception as e:
            logger.error(f"Slack posting failed: {e}")
            pass

        # Step 4: Send email summary
        try:
            email_subject = f"[{classification.urgency.upper()}] {ticket.subject}"
            email_body = format_email_body(ticket, classification, slack_channel)
            send_summary_email(
                recipient=app.config["ADMIN_EMAIL"],
                subject=email_subject,
                body=email_body,
            )
            logger.info(f"Sent email summary to {app.config['"'"'ADMIN_EMAIL'"'"']}")
        except Exception as e:
            logger.error(f"Email sending failed: {e}")
            pass

        # Step 5: Log ticket for audit trail
        log_ticket(ticket, classification, slack_channel)

        # Return success
        return (
            jsonify(
                {
                    "status": "success",
                    "ticket_id": generate_ticket_id(),
                    "routed_to": slack_channel,
                    "classification": {
                        "urgency": classification.urgency,
                        "category": classification.category,
                    },
                }
            ),
            202,
        )

    except Exception as e:
        logger.exception(f"Unhandled error in ticket processing: {e}")
        return jsonify({"error": "Internal server error"}), 500


def format_slack_message(
    ticket: TicketRequest, classification: Classification, channel: str
) -> Dict[str, Any]:
    """Format ticket as a Slack message"""
    urgency_emoji = {
        "urgent": "??",
        "normal": "??",
        "low": "??",
    }
    emoji = urgency_emoji.get(classification.urgency, "?")

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": f"{emoji} {classification.urgency.upper()} - {ticket.subject}",
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": f"*From:*\n{ticket.email}",
                    },
                    {
                        "type": "mrkdwn",
                        "text": f"*Category:*\n{classification.category}",
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Description:*\n{ticket.description[:500]}{'"'"'...'"'"' if len(ticket.description) > 500 else '"'"''"'"'}",
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary:*\n{classification.summary}",
                },
            },
            {
                "type": "divider",
            },
            {
                "type": "context",
                "elements": [
                    {
                        "type": "mrkdwn",
                        "text": f"_Received at {datetime.utcnow().isoformat()}Z_",
                    }
                ],
            },
        ]
    }


def format_email_body(
    ticket: TicketRequest, classification: Classification, channel: str
) -> str:
    """Format ticket as an email body"""
    return f"""
New Support Ticket Received

From: {ticket.email}
Subject: {ticket.subject}
Received: {datetime.utcnow().isoformat()}Z

CLASSIFICATION
==============
Urgency: {classification.urgency.upper()}
Category: {classification.category}
Routed To: {channel}

DESCRIPTION
===========
{ticket.description}

CLAUDE ANALYSIS
===============
{classification.summary}

---
This is an automated message from the Workflow Automation POC.
"""


def generate_ticket_id() -> str:
    """Generate a simple ticket ID based on timestamp"""
    import time

    return f"TKT-{int(time.time())}"


def log_ticket(
    ticket: TicketRequest, classification: Classification, channel: str
) -> None:
    """Log ticket to audit trail (simple file-based for POC)"""
    import os

    logs_dir = "logs"
    os.makedirs(logs_dir, exist_ok=True)

    log_entry = {
        "timestamp": datetime.utcnow().isoformat(),
        "email": ticket.email,
        "subject": ticket.subject,
        "urgency": classification.urgency,
        "category": classification.category,
        "channel": channel,
        "summary": classification.summary,
    }

    log_file = os.path.join(logs_dir, "tickets.jsonl")
    with open(log_file, "a") as f:
        f.write(json.dumps(log_entry) + "\n")


@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404


@app.errorhandler(500)
def internal_error(error):
    logger.error(f"Internal server error: {error}")
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
