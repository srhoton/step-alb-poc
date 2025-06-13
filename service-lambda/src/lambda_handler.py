"""AWS Lambda handler for widget CRUD operations via ALB."""

import json
import logging
import os
import time
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize DynamoDB client
dynamodb = boto3.resource("dynamodb")
table_name = os.environ.get("DYNAMODB_TABLE_NAME", "step-alb-poc")
table = dynamodb.Table(table_name)


class HTTPError(Exception):
    """Custom exception for HTTP errors."""

    def __init__(self, status_code: int, message: str) -> None:
        """Initialize HTTPError.

        Args:
            status_code: HTTP status code
            message: Error message
        """
        self.status_code = status_code
        self.message = message
        super().__init__(message)


def create_response(status_code: int, body: Dict[str, Any]) -> Dict[str, Any]:
    """Create ALB response format.

    Args:
        status_code: HTTP status code
        body: Response body dictionary

    Returns:
        ALB-formatted response dictionary
    """
    return {
        "statusCode": status_code,
        "statusDescription": f"{status_code} {get_status_description(status_code)}",
        "isBase64Encoded": False,
        "headers": {
            "Content-Type": "application/json"
        },
        "body": json.dumps(body)
    }


def get_status_description(status_code: int) -> str:
    """Get HTTP status description.

    Args:
        status_code: HTTP status code

    Returns:
        Status description string
    """
    descriptions = {
        200: "OK",
        201: "Created",
        204: "No Content",
        400: "Bad Request",
        404: "Not Found",
        500: "Internal Server Error"
    }
    return descriptions.get(status_code, "Unknown")


def extract_widget_name(path: str) -> str:
    """Extract widget name from URI path.

    Args:
        path: URI path string

    Returns:
        Widget name

    Raises:
        HTTPError: If widget name cannot be extracted
    """
    path_parts = [part for part in path.split("/") if part]
    if not path_parts or len(path_parts) < 2:
        raise HTTPError(400, "Invalid path format. Expected: /widgets/{widget_name}")

    if path_parts[0] != "widgets":
        raise HTTPError(400, "Invalid path format. Expected: /widgets/{widget_name}")

    return path_parts[1]


def handle_post(widget_name: str) -> Dict[str, Any]:
    """Handle POST request to create a widget.

    Args:
        widget_name: Name of the widget to create

    Returns:
        Response dictionary

    Raises:
        HTTPError: If creation fails
    """
    try:
        current_time = int(time.time())
        transition_at = current_time + 3600  # +60 minutes

        # Check if widget already exists
        response = table.get_item(
            Key={"PK": widget_name, "SK": "new"}
        )

        if "Item" in response:
            raise HTTPError(400, f"Widget '{widget_name}' already exists")

        # Create new widget
        table.put_item(
            Item={
                "PK": widget_name,
                "SK": "new",
                "transitionAt": transition_at,
                "createdAt": current_time
            }
        )

        logger.info(f"Created widget: {widget_name}")
        return create_response(201, {
            "message": f"Widget '{widget_name}' created successfully",
            "widget": {
                "name": widget_name,
                "state": "new",
                "transitionAt": transition_at,
                "createdAt": current_time
            }
        })

    except ClientError as e:
        logger.error(f"DynamoDB error creating widget {widget_name}: {e}")
        raise HTTPError(500, "Failed to create widget") from e


def handle_put(widget_name: str, body: str) -> Dict[str, Any]:
    """Handle PUT request to update a widget.

    Args:
        widget_name: Name of the widget to update
        body: Request body JSON string

    Returns:
        Response dictionary

    Raises:
        HTTPError: If update fails
    """
    try:
        # Parse request body
        try:
            data = json.loads(body)
        except json.JSONDecodeError:
            raise HTTPError(400, "Invalid JSON in request body") from None

        if "state" not in data or "transitionAt" not in data:
            raise HTTPError(400, "Missing required fields: 'state' and 'transitionAt'")

        new_state = data["state"]
        new_transition_at = data["transitionAt"]

        if not isinstance(new_state, str) or not isinstance(new_transition_at, int):
            raise HTTPError(
                400,
                ("Invalid field types: 'state' must be string, "
                 "'transitionAt' must be integer"),
            )

        # Check if widget exists (get current state)
        response = table.scan(
            FilterExpression="PK = :pk",
            ExpressionAttributeValues={":pk": widget_name}
        )

        if not response["Items"]:
            raise HTTPError(404, f"Widget '{widget_name}' not found")

        # Get current item to update
        current_item = response["Items"][0]
        old_state = current_item["SK"]

        # Delete old state record
        table.delete_item(
            Key={"PK": widget_name, "SK": old_state}
        )

        # Create new state record
        current_time = int(time.time())
        table.put_item(
            Item={
                "PK": widget_name,
                "SK": new_state,
                "transitionAt": new_transition_at,
                "updatedAt": current_time,
                "createdAt": current_item.get("createdAt", current_time)
            }
        )

        logger.info(f"Updated widget {widget_name} from {old_state} to {new_state}")
        return create_response(200, {
            "message": f"Widget '{widget_name}' updated successfully",
            "widget": {
                "name": widget_name,
                "state": new_state,
                "transitionAt": new_transition_at,
                "updatedAt": current_time
            }
        })

    except ClientError as e:
        logger.error(f"DynamoDB error updating widget {widget_name}: {e}")
        raise HTTPError(500, "Failed to update widget") from e


def handle_get(widget_name: str) -> Dict[str, Any]:
    """Handle GET request to retrieve a widget.

    Args:
        widget_name: Name of the widget to retrieve

    Returns:
        Response dictionary

    Raises:
        HTTPError: If retrieval fails
    """
    try:
        # Get all records for this widget
        response = table.scan(
            FilterExpression="PK = :pk",
            ExpressionAttributeValues={":pk": widget_name}
        )

        if not response["Items"]:
            raise HTTPError(404, f"Widget '{widget_name}' not found")

        # Should only be one item, but handle gracefully
        item = response["Items"][0]

        widget_data = {
            "name": item["PK"],
            "state": item["SK"],
            "transitionAt": item["transitionAt"]
        }

        # Add optional timestamps
        if "createdAt" in item:
            widget_data["createdAt"] = item["createdAt"]
        if "updatedAt" in item:
            widget_data["updatedAt"] = item["updatedAt"]

        logger.info(f"Retrieved widget: {widget_name}")
        return create_response(200, {"widget": widget_data})

    except ClientError as e:
        logger.error(f"DynamoDB error retrieving widget {widget_name}: {e}")
        raise HTTPError(500, "Failed to retrieve widget") from e


def handle_delete(widget_name: str) -> Dict[str, Any]:
    """Handle DELETE request to remove a widget.

    Args:
        widget_name: Name of the widget to delete

    Returns:
        Response dictionary

    Raises:
        HTTPError: If deletion fails
    """
    try:
        # Get all records for this widget
        response = table.scan(
            FilterExpression="PK = :pk",
            ExpressionAttributeValues={":pk": widget_name}
        )

        if not response["Items"]:
            raise HTTPError(404, f"Widget '{widget_name}' not found")

        # Delete all records for this widget
        for item in response["Items"]:
            table.delete_item(
                Key={"PK": item["PK"], "SK": item["SK"]}
            )

        logger.info(f"Deleted widget: {widget_name}")
        return create_response(
            204, {"message": f"Widget '{widget_name}' deleted successfully"}
        )

    except ClientError as e:
        logger.error(f"DynamoDB error deleting widget {widget_name}: {e}")
        raise HTTPError(500, "Failed to delete widget") from e


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """AWS Lambda handler for ALB requests.

    Args:
        event: ALB event dictionary
        context: Lambda context object

    Returns:
        ALB response dictionary
    """
    try:
        # Extract request details
        http_method = event.get("httpMethod", "")
        path = event.get("path", "")
        body = event.get("body", "")

        logger.info(f"Processing {http_method} request for path: {path}")

        # Extract widget name from path
        widget_name = extract_widget_name(path)

        # Route to appropriate handler
        if http_method == "POST":
            return handle_post(widget_name)
        elif http_method == "PUT":
            return handle_put(widget_name, body)
        elif http_method == "GET":
            return handle_get(widget_name)
        elif http_method == "DELETE":
            return handle_delete(widget_name)
        else:
            raise HTTPError(400, f"Unsupported HTTP method: {http_method}")

    except HTTPError as e:
        logger.warning(f"HTTP error: {e.status_code} - {e.message}")
        return create_response(e.status_code, {"error": e.message})
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_response(500, {"error": "Internal server error"})

