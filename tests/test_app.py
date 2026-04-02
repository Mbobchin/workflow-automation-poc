"""
Test suite for Workflow Automation POC
Covers happy paths, edge cases, and integration points
"""

import json
import pytest
from unittest.mock import Mock, patch, MagicMock
from pydantic import ValidationError

from app import app, ROUTING_MAP, format_slack_message, format_email_body
from models import TicketRequest, Classification
from integrations.claude import classify_ticket
from integrations.slack import post_to_slack
from integrations.email import send_summary_email


# ============================================================================
# FIXTURES
# ============================================================================


@pytest.fixture
def client():
    """Flask test client"""
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client


@pytest.fixture
def valid_ticket():
    """Valid ticket fixture"""
    return {
        "email": "customer@example.com",
        "subject": "Cannot login to my account",
        "description": "I'"'"'ve been locked out of my account for the past 2 hours. I'"'"'ve tried resetting my password but haven'"'"'t received the reset email.",
    }


@pytest.fixture
def valid_classification():
    """Valid classification fixture"""
    return Classification(
        urgency="urgent",
        category="technical",
        summary="Customer is locked out. Recommend immediate manual password reset.",
    )


# ============================================================================
# TEST: Models and Validation
# ============================================================================


def test_ticket_request_valid():
    """Valid ticket should be accepted"""
    ticket = TicketRequest(
        email="user@example.com",
        subject="Issue with payment",
        description="I was charged twice for my subscription this month.",
    )
    assert ticket.email == "user@example.com"
    assert ticket.subject == "Issue with payment"


def test_ticket_request_invalid_email():
    """Invalid email should raise ValidationError"""
    with pytest.raises(ValidationError):
        TicketRequest(
            email="not-an-email",
            subject="Test subject",
            description="Test description that is long enough",
        )


def test_ticket_request_subject_too_short():
    """Subject shorter than 5 chars should fail"""
    with pytest.raises(ValidationError):
        TicketRequest(
            email="user@example.com",
            subject="Hi",
            description="Test description that is long enough",
        )


def test_ticket_request_description_too_short():
    """Description shorter than 10 chars should fail"""
    with pytest.raises(ValidationError):
        TicketRequest(
            email="user@example.com",
            subject="Test subject",
            description="Short",
        )


def test_classification_valid():
    """Valid classification should be accepted"""
    classification = Classification(
        urgency="normal",
        category="billing",
        summary="User is asking about invoice details.",
    )
    assert classification.urgency == "normal"
    assert classification.category == "billing"


def test_classification_invalid_urgency():
    """Invalid urgency should raise ValidationError"""
    with pytest.raises(ValidationError):
        Classification(
            urgency="critical",
            category="technical",
            summary="Test",
        )


def test_classification_invalid_category():
    """Invalid category should raise ValidationError"""
    with pytest.raises(ValidationError):
        Classification(
            urgency="normal",
            category="other",
            summary="Test",
        )


# ============================================================================
# TEST: Webhook Endpoint
# ============================================================================


def test_health_endpoint(client):
    """Health check should return 200"""
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json["status"] == "healthy"


def test_webhook_missing_field(client, valid_ticket):
    """Missing required field should return 422"""
    payload = valid_ticket.copy()
    del payload["email"]

    response = client.post(
        "/webhook/ticket", data=json.dumps(payload), content_type="application/json"
    )

    assert response.status_code == 422
    assert "error" in response.json


def test_webhook_invalid_json(client):
    """Invalid JSON should return 400"""
    response = client.post(
        "/webhook/ticket",
        data="not json",
        content_type="application/json",
    )
    assert response.status_code == 400


def test_webhook_empty_body(client):
    """Empty body should return 400"""
    response = client.post(
        "/webhook/ticket",
        data="",
        content_type="application/json",
    )
    assert response.status_code == 400


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_webhook_success(mock_email, mock_slack, mock_classify, client, valid_ticket):
    """Valid ticket should be processed successfully"""
    mock_classify.return_value = Classification(
        urgency="urgent",
        category="technical",
        summary="Test issue",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["status"] == "success"
    assert "ticket_id" in response.json
    assert response.json["routed_to"] == "#incidents"

    mock_classify.assert_called_once()
    mock_slack.assert_called_once()
    mock_email.assert_called_once()


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_webhook_routing_normal_technical(
    mock_email, mock_slack, mock_classify, client, valid_ticket
):
    """Normal + technical should route to #support"""
    mock_classify.return_value = Classification(
        urgency="normal",
        category="technical",
        summary="Test issue",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["routed_to"] == "#support"


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_webhook_routing_normal_billing(
    mock_email, mock_slack, mock_classify, client, valid_ticket
):
    """Normal + billing should route to #billing"""
    mock_classify.return_value = Classification(
        urgency="normal",
        category="billing",
        summary="Test issue",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["routed_to"] == "#billing"


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_webhook_routing_low_feature_request(
    mock_email, mock_slack, mock_classify, client, valid_ticket
):
    """Low + feature-request should route to #feature-requests"""
    mock_classify.return_value = Classification(
        urgency="low",
        category="feature-request",
        summary="Test issue",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["routed_to"] == "#feature-requests"


@patch("app.classify_ticket", side_effect=Exception("Claude API error"))
def test_webhook_classification_error(mock_classify, client, valid_ticket):
    """Classification error should return 500"""
    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 500
    assert "error" in response.json


@patch("app.classify_ticket")
@patch("app.post_to_slack", side_effect=Exception("Slack API error"))
@patch("app.send_summary_email")
def test_webhook_slack_failure_non_fatal(
    mock_email, mock_slack, mock_classify, client, valid_ticket
):
    """Slack failure should not fail the entire request"""
    mock_classify.return_value = Classification(
        urgency="normal",
        category="technical",
        summary="Test issue",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(valid_ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["status"] == "success"


# ============================================================================
# TEST: Formatting Functions
# ============================================================================


def test_format_slack_message(valid_ticket, valid_classification):
    """Slack message formatting should produce valid block structure"""
    ticket = TicketRequest(**valid_ticket)
    message = format_slack_message(ticket, valid_classification, "#incidents")

    assert "blocks" in message
    assert len(message["blocks"]) > 0
    assert message["blocks"][0]["type"] == "header"


def test_format_email_body(valid_ticket, valid_classification):
    """Email formatting should include all required information"""
    ticket = TicketRequest(**valid_ticket)
    body = format_email_body(ticket, valid_classification, "#incidents")

    assert valid_ticket["email"] in body
    assert valid_ticket["subject"] in body
    assert valid_classification.urgency.upper() in body
    assert valid_classification.category in body
    assert "#incidents" in body


# ============================================================================
# TEST: Integration Routing
# ============================================================================


def test_routing_map_coverage():
    """All routing combinations should be covered"""
    urgencies = ["urgent", "normal", "low"]
    categories = ["technical", "billing", "feature-request"]

    for urgency in urgencies:
        for category in categories:
            assert (urgency, category) in ROUTING_MAP, (
                f"Missing routing for {urgency}/{category}"
            )


def test_routing_map_values():
    """All routing values should be valid Slack channels"""
    for channel in ROUTING_MAP.values():
        assert channel.startswith("#"), f"Invalid channel format: {channel}"
        assert len(channel) > 1, f"Channel too short: {channel}"


# ============================================================================
# TEST: 404 and Error Handlers
# ============================================================================


def test_invalid_endpoint(client):
    """Invalid endpoint should return 404"""
    response = client.get("/invalid/endpoint")
    assert response.status_code == 404
    assert "error" in response.json


# ============================================================================
# TEST: End-to-End Scenarios
# ============================================================================


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_e2e_urgent_technical_issue(mock_email, mock_slack, mock_classify, client):
    """E2E: System down scenario"""
    ticket = {
        "email": "ops@example.com",
        "subject": "Production database is down",
        "description": "Our production database stopped responding 5 minutes ago. All users are unable to access their accounts.",
    }

    mock_classify.return_value = Classification(
        urgency="urgent",
        category="technical",
        summary="Production outage. Immediate escalation required.",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["routed_to"] == "#incidents"


@patch("app.classify_ticket")
@patch("app.post_to_slack")
@patch("app.send_summary_email")
def test_e2e_low_feature_request(mock_email, mock_slack, mock_classify, client):
    """E2E: Feature request scenario"""
    ticket = {
        "email": "user@example.com",
        "subject": "Would like dark mode option",
        "description": "It would be nice if the application had a dark mode option for late night usage.",
    }

    mock_classify.return_value = Classification(
        urgency="low",
        category="feature-request",
        summary="Feature request for dark mode. Add to product backlog.",
    )

    response = client.post(
        "/webhook/ticket",
        data=json.dumps(ticket),
        content_type="application/json",
    )

    assert response.status_code == 202
    assert response.json["routed_to"] == "#feature-requests"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
