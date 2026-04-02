"""
Support Ticket Router - Webhook-triggered workflow automation POC
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

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config.from_object(Config)

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
        payload = request.get_json()
        if not payload:
            return jsonify({"error": "Empty request body"}), 400
        
        ticket = TicketRequest(**payload)
        logger.info("Received ticket from %s: %s" % (ticket.email, ticket.subject))
        
        classification = classify_ticket(ticket)
        logger.info("Classified: urgency=%s, category=%s" % (classification.urgency, classification.category))
        
        slack_channel = ROUTING_MAP.get((classification.urgency, classification.category), "#support")
        
        try:
            slack_message = format_slack_message(ticket, classification, slack_channel)
            post_to_slack(slack_channel, slack_message)
        except:
            pass
        
        try:
            subject = "[%s] %s" % (classification.urgency.upper(), ticket.subject)
            body = format_email_body(ticket, classification, slack_channel)
            send_summary_email(app.config["ADMIN_EMAIL"], subject, body)
        except:
            pass
        
        log_ticket(ticket, classification, slack_channel)
        
        return jsonify({
            "status": "success",
            "ticket_id": "TKT-%d" % int(__import__("time").time()),
            "routed_to": slack_channel,
            "classification": {
                "urgency": classification.urgency,
                "category": classification.category,
            },
        }), 202
        
    except ValidationError as e:
        return jsonify({"error": "Invalid ticket data"}), 422
    except Exception as e:
        logger.exception("Error: %s" % str(e))
        return jsonify({"error": "Internal server error"}), 500


def format_slack_message(ticket, classification, channel):
    emoji = {"urgent": "??", "normal": "??", "low": "??"}.get(classification.urgency, "?")
    desc = ticket.description[:500] + ("..." if len(ticket.description) > 500 else "")
    
    return {
        "blocks": [
            {"type": "header", "text": {"type": "plain_text", "text": "%s %s - %s" % (emoji, classification.urgency.upper(), ticket.subject)}},
            {"type": "section", "fields": [{"type": "mrkdwn", "text": "*From:*\n%s" % ticket.email}, {"type": "mrkdwn", "text": "*Category:*\n%s" % classification.category}]},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Description:*\n%s" % desc}},
            {"type": "section", "text": {"type": "mrkdwn", "text": "*Summary:*\n%s" % classification.summary}},
            {"type": "divider"},
            {"type": "context", "elements": [{"type": "mrkdwn", "text": "_Received at %sZ_" % datetime.utcnow().isoformat()}]},
        ]
    }


def format_email_body(ticket, classification, channel):
    return "New Support Ticket\n\nFrom: %s\nSubject: %s\n\nCLASSIFICATION\nUrgency: %s\nCategory: %s\nRouted To: %s\n\nDESCRIPTION\n%s\n\nCLAUDE ANALYSIS\n%s\n\n---\nAutomated message from Workflow Automation POC." % (ticket.email, ticket.subject, classification.urgency.upper(), classification.category, channel, ticket.description, classification.summary)


def log_ticket(ticket, classification, channel):
    import os
    os.makedirs("logs", exist_ok=True)
    entry = json.dumps({"timestamp": datetime.utcnow().isoformat(), "email": ticket.email, "subject": ticket.subject, "urgency": classification.urgency, "category": classification.category, "channel": channel})
    with open("logs/tickets.jsonl", "a") as f:
        f.write(entry + "\n")


@app.errorhandler(404)
def not_found(e):
    return jsonify({"error": "Not found"}), 404

@app.errorhandler(500)
def error(e):
    return jsonify({"error": "Server error"}), 500


if __name__ == "__main__":
    app.run(debug=app.config["DEBUG"], host="0.0.0.0", port=5000)
