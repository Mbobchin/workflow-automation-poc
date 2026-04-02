"""
Slack API integration for posting tickets to appropriate channels
Uses Slack SDK for reliable message delivery
"""

import logging
from typing import Dict, Any

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

from config import Config

logger = logging.getLogger(__name__)

# Initialize Slack client
slack_client = WebClient(token=Config.SLACK_BOT_TOKEN)


def post_to_slack(channel: str, message: Dict[str, Any]) -> str:
    """
    Post a formatted message to a Slack channel
    
    Args:
        channel: Channel name (e.g., "#support")
        message: Slack message blocks (see format_slack_message in app.py)
        
    Returns:
        Message timestamp if successful
    """

    try:
        # Ensure channel starts with #
        if not channel.startswith("#"):
            channel = f"#{channel}"

        # Remove # for API call
        channel_name = channel.lstrip("#")

        logger.debug(f"Posting to Slack channel: {channel}")

        response = slack_client.chat_postMessage(
            channel=channel_name, blocks=message.get("blocks", [])
        )

        logger.info(f"Message posted to {channel}: {response['"'"'ts'"'"']}")

        return response["ts"]

    except SlackApiError as e:
        logger.error(f"Slack API error: {e.response['"'"'error'"'"']}")
        raise
    except Exception as e:
        logger.error(f"Error posting to Slack: {e}")
        raise


def list_channels() -> list:
    """
    List all available Slack channels (for debugging/setup)
    Useful for verifying channels exist
    """

    try:
        response = slack_client.conversations_list()
        channels = [ch["name"] for ch in response["channels"]]
        logger.info(f"Available channels: {channels}")
        return channels

    except SlackApiError as e:
        logger.error(f"Error listing channels: {e.response['"'"'error'"'"']}")
        raise


def test_connection() -> bool:
    """
    Test Slack connection and bot auth
    Returns True if connection successful
    """

    try:
        response = slack_client.auth_test()
        logger.info(f"Slack auth test successful: {response['"'"'user_id'"'"']} in {response['"'"'team_id'"'"']}")
        return True
    except SlackApiError as e:
        logger.error(f"Slack auth test failed: {e.response['"'"'error'"'"']}")
        return False
