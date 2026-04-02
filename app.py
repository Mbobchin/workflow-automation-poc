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
    return jsonify({"status": "healthy"}), 200


@app.route("/webhook/ticket", methods=["POST"])
def handle_ticket():
    try:
        try:
            payload = request.get_json()
            if not payload:
                return jsonify({"error": "Empty request body"}), 400
        except Exception as e:
            logger.error("Failed to parse JSON: " + str(e))
            return jsonify({"error": "Invalid JSON"}), 400

        try:
            ticket = TicketRequest(**payload)
        except ValidationError as e:
            logger.error("Validation error: " + str(e))
            return jsonify({"error": "Invalid ticket data", "details": str(e.errors())}), 422

        logger.info("Received ticket from " + ticket.email + ": " + ticket.subject)

        try:
            classification = classify_ticket(ticket)
            logger.info("Classified: urgency=" + classification.urgency + ", category=" + classification.category)
        except Exception as e:
            logger.error("Classification failed: " + str(e))
            return jsonify({"error": "Failed to classify ticket"}), 500

        slack_channel = ROUTING_MAP.get(
            (classification.urgency, classification.category), "#support"
        )
        logger.info("Routing to " + slack_channel)

        try:
            slack_message = format_slack_message(ticket, classification, slack_channel)
            post_to_slack(slack_channel, slack_message)
            logger.info("Posted to Slack: " + slack_channel)
        except Exception as e:
            logger.error("Slack posting failed: " + str(e))
            pass

        try:
            email_subject = "[" + classification.urgency.upper() + "] " + ticket.subject
            email_body = format_email_body(ticket, classification, slack_channel)
            send_summary_email(
                recipient=app.config["ADMIN_EMAIL"],
                subject=email_subject,
                body=email_body,
            )
            logger.info("Email sent to " + app.config["ADMIN_EMAIL"])
        except Exception as e:
            logger.error("Email sending failed: " + str(e))
            pass

        log_ticket(ticket, classification, slack_channel)

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
        logger.exception("Unhandled error: " + str(e))
        return jsonify({"error": "Internal server error"}), 500


def format_slack_message(
    ticket: TicketRequest, classification: Classification, channel: str
) -> Dict[str, Any]:
    urgency_emoji = {
        "urgent": "??",
        "normal": "??",
        "low": "??",
    }
    emoji = urgency_emoji.get(classification.urgency, "?")
    
    desc_preview = ticket.description[:500]
    if len(ticket.description) > 500:
        desc_preview = desc_preview + "..."

    return {
        "blocks": [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": emoji + " " + classification.urgency.upper() + " - " + ticket.subject,
                },
            },
            {
                "type": "section",
                "fields": [
                    {
                        "type": "mrkdwn",
                        "text": "*From:*\n" + ticket.email,
                    },
                    {
                        "type": "mrkdwn",
                        "text": "*Category:*\n" + classification.category,
                    },
                ],
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Description:*\n" + desc_preview,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": "*Summary:*\n" + classification.summary,
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
                        "text": "_Received at " + datetime.utcnow().isoformat() + "Z_",
                    }
                ],
            },
        ]
    }


def format_email_body(
    ticket: TicketRequest, classification: Classification, channel: str
) -> str:
    return """
New Support Ticket Received

From: """ + ticket.email + """
Subject: """ + ticket.subject + """
Received: """ + datetime.utcnow().isoformat() + """Z

CLASSIFICATION
==============
Urgency: """ + classification.urgency.upper() + """
Category: """ + classification.category + """
Routed To: """ + channel + """

DESCRIPTION
===========
""" + ticket.description + """

CLAUDE ANALYSIS
===============
""" + classification.summary + """

---
This is an automated message from the Workflow Automation POC.
"""


def generate_ticket_id() -> str:
    import time
    return "TKT-" + str(int(time.time()))


def log_ticket(
    ticket: TicketRequest, classification: Classification, channel: str
) -> None:
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
    logger.error("Internal server error: " + str(error))
    return jsonify({"error": "Internal server error"}), 500


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
