"""
Configuration management for the Workflow Automation POC
Loads settings from environment variables with sensible defaults
"""

import os
from dotenv import load_dotenv

# Load from .env file if it exists
load_dotenv()


class Config:
    """Base configuration"""

    DEBUG = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")

    # Claude API
    ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
    if not ANTHROPIC_API_KEY:
        raise ValueError("ANTHROPIC_API_KEY environment variable is required")

    # Slack
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    if not SLACK_BOT_TOKEN:
        raise ValueError("SLACK_BOT_TOKEN environment variable is required")

    # Email
    ADMIN_EMAIL = os.getenv("ADMIN_EMAIL")
    if not ADMIN_EMAIL:
        raise ValueError("ADMIN_EMAIL environment variable is required")

    EMAIL_FROM = os.getenv("EMAIL_FROM", "noreply@workflow-poc.local")
    SMTP_SERVER = os.getenv("SMTP_SERVER", "smtp.gmail.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")

    # App settings
    LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
    ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


class TestConfig(Config):
    """Testing configuration - uses dummy values"""

    DEBUG = True
    ANTHROPIC_API_KEY = "sk-test-key"
    SLACK_BOT_TOKEN = "xoxb-test-token"
    ADMIN_EMAIL = "test@example.com"
    SMTP_USERNAME = "test@example.com"
    SMTP_PASSWORD = "test-password"
    ENVIRONMENT = "testing"
