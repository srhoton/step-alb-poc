"""Lambda function for modifying widgets via Step Functions integration."""

import json
import logging
import os
from typing import Any

import requests

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)


class ModLambdaError(Exception):
    """Custom exception for mod lambda errors."""

    def __init__(self, message: str, status_code: int = 500) -> None:
        """Initialize ModLambdaError.

        Args:
            message: Error message
            status_code: HTTP status code
        """
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def validate_event(event: dict[str, Any]) -> dict[str, Any]:
    """Validate the Step Functions event structure.

    Args:
        event: The Step Functions event

    Returns:
        Dict containing validated widget_id, status, and transitionAt

    Raises:
        ModLambdaError: If validation fails
    """
    required_fields = ["widget_id", "status", "transitionAt"]

    for field in required_fields:
        if field not in event:
            raise ModLambdaError(f"Missing required field: {field}", 400)

    widget_id = event["widget_id"]
    status = event["status"]
    transition_at = event["transitionAt"]

    if not isinstance(widget_id, str) or not widget_id.strip():
        raise ModLambdaError("widget_id must be a non-empty string", 400)

    if status not in ["in_progress", "done"]:
        raise ModLambdaError(
            "status must be either 'in_progress' or 'done'", 400
        )

    if not isinstance(transition_at, int | float) or transition_at < 0:
        raise ModLambdaError(
            "transitionAt must be a non-negative number (epoch seconds)", 400
        )

    return {
        "widget_id": widget_id.strip(),
        "status": status,
        "transitionAt": int(transition_at),
    }


def update_widget_via_alb(
    widget_id: str, status: str, transition_at: int, alb_endpoint: str
) -> dict[str, Any]:
    """Update widget via ALB REST API.

    Args:
        widget_id: The widget ID to update
        status: The new status value
        transition_at: The new transitionAt epoch seconds value
        alb_endpoint: The ALB endpoint URL

    Returns:
        Response from the ALB API

    Raises:
        ModLambdaError: If the API call fails
    """
    url = f"{alb_endpoint.rstrip('/')}/widgets/{widget_id}"

    payload = {
        "status": status,
        "transitionAt": transition_at,
    }

    headers = {
        "Content-Type": "application/json",
    }

    try:
        logger.info(
            "Updating widget via ALB",
            extra={
                "widget_id": widget_id,
                "status": status,
                "transitionAt": transition_at,
                "url": url,
            },
        )

        response = requests.put(
            url, json=payload, headers=headers, timeout=30
        )

        logger.info(
            "ALB API response",
            extra={
                "status_code": response.status_code,
                "response_body": response.text,
            },
        )

        if response.status_code >= 400:
            raise ModLambdaError(
                f"ALB API request failed with status {response.status_code}: "
                f"{response.text}",
                response.status_code,
            )

        return response.json() if response.text else {}

    except requests.exceptions.Timeout:
        raise ModLambdaError("ALB API request timed out", 504) from None
    except requests.exceptions.ConnectionError:
        raise ModLambdaError("Failed to connect to ALB API", 502) from None
    except (requests.exceptions.JSONDecodeError, json.JSONDecodeError, ValueError):
        logger.warning("ALB API returned non-JSON response or raised ValueError")
        return {}
    except requests.exceptions.RequestException as e:
        raise ModLambdaError(f"ALB API request failed: {str(e)}", 500) from e


def lambda_handler(event: dict[str, Any], context: Any) -> dict[str, Any]:
    """Lambda handler for Step Functions widget modification.

    Args:
        event: Step Functions event containing widget_id, status, and transitionAt
        context: Lambda context (unused)

    Returns:
        Success response with updated widget data

    Raises:
        ModLambdaError: If processing fails
    """
    try:
        logger.info("Processing Step Functions event", extra={"event": event})

        # Get ALB endpoint from environment
        alb_endpoint = os.environ.get("ALB_ENDPOINT")
        if not alb_endpoint:
            raise ModLambdaError(
                "ALB_ENDPOINT environment variable not set", 500
            )

        # Validate the event
        validated_data = validate_event(event)

        # Update widget via ALB
        result = update_widget_via_alb(
            validated_data["widget_id"],
            validated_data["status"],
            validated_data["transitionAt"],
            alb_endpoint,
        )

        success_response = {
            "statusCode": 200,
            "body": {
                "message": "Widget updated successfully",
                "widget_id": validated_data["widget_id"],
                "status": validated_data["status"],
                "transitionAt": validated_data["transitionAt"],
                "alb_response": result,
            },
        }

        logger.info("Widget update completed successfully", extra=success_response)
        return success_response

    except ModLambdaError:
        # Re-raise custom errors to bubble up to Step Functions
        raise
    except Exception as e:
        logger.error("Unexpected error processing event", extra={"error": str(e)})
        raise ModLambdaError(f"Unexpected error: {str(e)}", 500) from e
