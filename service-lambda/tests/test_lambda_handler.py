"""Tests for lambda_handler module."""

import json
from unittest.mock import Mock, patch

import boto3
import pytest
from moto import mock_aws

from src.lambda_handler import (
    HTTPError,
    create_response,
    extract_widget_name,
    get_status_description,
    handle_delete,
    handle_get,
    handle_post,
    handle_put,
    lambda_handler,
)


class TestHTTPError:
    """Test HTTPError exception class."""

    def test_init(self) -> None:
        """Test HTTPError initialization."""
        error = HTTPError(404, "Not found")
        assert error.status_code == 404
        assert error.message == "Not found"
        assert str(error) == "Not found"


class TestUtilityFunctions:
    """Test utility functions."""

    def test_create_response(self) -> None:
        """Test create_response function."""
        body = {"message": "success"}
        response = create_response(200, body)

        expected = {
            "statusCode": 200,
            "statusDescription": "200 OK",
            "isBase64Encoded": False,
            "headers": {"Content-Type": "application/json"},
            "body": json.dumps(body)
        }
        assert response == expected

    def test_get_status_description(self) -> None:
        """Test get_status_description function."""
        assert get_status_description(200) == "OK"
        assert get_status_description(201) == "Created"
        assert get_status_description(404) == "Not Found"
        assert get_status_description(999) == "Unknown"

    def test_extract_widget_name_valid(self) -> None:
        """Test extract_widget_name with valid paths."""
        assert extract_widget_name("/widgets/test-widget") == "test-widget"
        assert extract_widget_name("/widgets/my_widget") == "my_widget"
        assert extract_widget_name("widgets/widget123") == "widget123"

    def test_extract_widget_name_invalid(self) -> None:
        """Test extract_widget_name with invalid paths."""
        with pytest.raises(HTTPError) as exc_info:
            extract_widget_name("/invalid/path")
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPError) as exc_info:
            extract_widget_name("/widgets")
        assert exc_info.value.status_code == 400

        with pytest.raises(HTTPError) as exc_info:
            extract_widget_name("")
        assert exc_info.value.status_code == 400


@mock_aws
class TestCRUDHandlers:
    """Test CRUD operation handlers."""

    def setup_method(self, method) -> None:
        """Set up test environment."""
        # Create mock DynamoDB table
        self.dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        self.table = self.dynamodb.create_table(
            TableName="step-alb-poc",
            KeySchema=[
                {"AttributeName": "PK", "KeyType": "HASH"},
                {"AttributeName": "SK", "KeyType": "RANGE"}
            ],
            AttributeDefinitions=[
                {"AttributeName": "PK", "AttributeType": "S"},
                {"AttributeName": "SK", "AttributeType": "S"}
            ],
            BillingMode="PAY_PER_REQUEST"
        )

        # Patch the table in the module
        with patch("src.lambda_handler.table", self.table):
            pass

    @patch("src.lambda_handler.table")
    @patch("src.lambda_handler.time.time")
    def test_handle_post_success(self, mock_time: Mock, mock_table: Mock) -> None:
        """Test successful POST request."""
        mock_time.return_value = 1000
        mock_table.get_item.return_value = {}  # Widget doesn't exist
        mock_table.put_item.return_value = {}

        response = handle_post("test-widget")

        assert response["statusCode"] == 201
        body = json.loads(response["body"])
        assert body["widget"]["name"] == "test-widget"
        assert body["widget"]["state"] == "new"
        assert body["widget"]["transitionAt"] == 4600  # 1000 + 3600

        mock_table.put_item.assert_called_once()

    @patch("src.lambda_handler.table")
    def test_handle_post_widget_exists(self, mock_table: Mock) -> None:
        """Test POST request when widget already exists."""
        mock_table.get_item.return_value = {"Item": {"PK": "test-widget"}}

        with pytest.raises(HTTPError) as exc_info:
            handle_post("test-widget")

        assert exc_info.value.status_code == 400
        assert "already exists" in exc_info.value.message

    @patch("src.lambda_handler.table")
    @patch("src.lambda_handler.time.time")
    def test_handle_put_success(self, mock_time: Mock, mock_table: Mock) -> None:
        """Test successful PUT request."""
        mock_time.return_value = 2000
        mock_table.scan.return_value = {
            "Items": [{
                "PK": "test-widget",
                "SK": "old-state",
                "createdAt": 1000
            }]
        }
        mock_table.delete_item.return_value = {}
        mock_table.put_item.return_value = {}

        body_data = {"state": "new-state", "transitionAt": 5000}
        response = handle_put("test-widget", json.dumps(body_data))

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        assert body["widget"]["state"] == "new-state"
        assert body["widget"]["transitionAt"] == 5000

        mock_table.delete_item.assert_called_once()
        mock_table.put_item.assert_called_once()

    @patch("src.lambda_handler.table")
    def test_handle_put_invalid_json(self, mock_table: Mock) -> None:
        """Test PUT request with invalid JSON."""
        with pytest.raises(HTTPError) as exc_info:
            handle_put("test-widget", "invalid json")

        assert exc_info.value.status_code == 400
        assert "Invalid JSON" in exc_info.value.message

    @patch("src.lambda_handler.table")
    def test_handle_put_missing_fields(self, mock_table: Mock) -> None:
        """Test PUT request with missing fields."""
        body_data = {"state": "new-state"}  # Missing transitionAt

        with pytest.raises(HTTPError) as exc_info:
            handle_put("test-widget", json.dumps(body_data))

        assert exc_info.value.status_code == 400
        assert "Missing required fields" in exc_info.value.message

    @patch("src.lambda_handler.table")
    def test_handle_put_widget_not_found(self, mock_table: Mock) -> None:
        """Test PUT request when widget doesn't exist."""
        mock_table.scan.return_value = {"Items": []}

        body_data = {"state": "new-state", "transitionAt": 5000}

        with pytest.raises(HTTPError) as exc_info:
            handle_put("test-widget", json.dumps(body_data))

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message

    @patch("src.lambda_handler.table")
    def test_handle_get_success(self, mock_table: Mock) -> None:
        """Test successful GET request."""
        mock_table.scan.return_value = {
            "Items": [{
                "PK": "test-widget",
                "SK": "active",
                "transitionAt": 5000,
                "createdAt": 1000,
                "updatedAt": 2000
            }]
        }

        response = handle_get("test-widget")

        assert response["statusCode"] == 200
        body = json.loads(response["body"])
        widget = body["widget"]
        assert widget["name"] == "test-widget"
        assert widget["state"] == "active"
        assert widget["transitionAt"] == 5000
        assert widget["createdAt"] == 1000
        assert widget["updatedAt"] == 2000

    @patch("src.lambda_handler.table")
    def test_handle_get_not_found(self, mock_table: Mock) -> None:
        """Test GET request when widget doesn't exist."""
        mock_table.scan.return_value = {"Items": []}

        with pytest.raises(HTTPError) as exc_info:
            handle_get("test-widget")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message

    @patch("src.lambda_handler.table")
    def test_handle_delete_success(self, mock_table: Mock) -> None:
        """Test successful DELETE request."""
        mock_table.scan.return_value = {
            "Items": [{
                "PK": "test-widget",
                "SK": "active"
            }]
        }
        mock_table.delete_item.return_value = {}

        response = handle_delete("test-widget")

        assert response["statusCode"] == 204
        body = json.loads(response["body"])
        assert "deleted successfully" in body["message"]

        mock_table.delete_item.assert_called_once()

    @patch("src.lambda_handler.table")
    def test_handle_delete_not_found(self, mock_table: Mock) -> None:
        """Test DELETE request when widget doesn't exist."""
        mock_table.scan.return_value = {"Items": []}

        with pytest.raises(HTTPError) as exc_info:
            handle_delete("test-widget")

        assert exc_info.value.status_code == 404
        assert "not found" in exc_info.value.message


class TestLambdaHandler:
    """Test main lambda_handler function."""

    @patch("src.lambda_handler.handle_post")
    def test_lambda_handler_post(self, mock_handle_post: Mock) -> None:
        """Test lambda_handler with POST request."""
        mock_handle_post.return_value = {"statusCode": 201}

        event = {
            "httpMethod": "POST",
            "path": "/widgets/test-widget",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 201
        mock_handle_post.assert_called_once_with("test-widget")

    @patch("src.lambda_handler.handle_put")
    def test_lambda_handler_put(self, mock_handle_put: Mock) -> None:
        """Test lambda_handler with PUT request."""
        mock_handle_put.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "PUT",
            "path": "/widgets/test-widget",
            "body": '{"state": "active", "transitionAt": 5000}'
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        mock_handle_put.assert_called_once_with(
            "test-widget", '{"state": "active", "transitionAt": 5000}'
        )

    @patch("src.lambda_handler.handle_get")
    def test_lambda_handler_get(self, mock_handle_get: Mock) -> None:
        """Test lambda_handler with GET request."""
        mock_handle_get.return_value = {"statusCode": 200}

        event = {
            "httpMethod": "GET",
            "path": "/widgets/test-widget",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 200
        mock_handle_get.assert_called_once_with("test-widget")

    @patch("src.lambda_handler.handle_delete")
    def test_lambda_handler_delete(self, mock_handle_delete: Mock) -> None:
        """Test lambda_handler with DELETE request."""
        mock_handle_delete.return_value = {"statusCode": 204}

        event = {
            "httpMethod": "DELETE",
            "path": "/widgets/test-widget",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 204
        mock_handle_delete.assert_called_once_with("test-widget")

    def test_lambda_handler_unsupported_method(self) -> None:
        """Test lambda_handler with unsupported HTTP method."""
        event = {
            "httpMethod": "PATCH",
            "path": "/widgets/test-widget",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Unsupported HTTP method" in body["error"]

    def test_lambda_handler_invalid_path(self) -> None:
        """Test lambda_handler with invalid path."""
        event = {
            "httpMethod": "GET",
            "path": "/invalid/path",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 400
        body = json.loads(response["body"])
        assert "Invalid path format" in body["error"]

    @patch("src.lambda_handler.handle_get")
    def test_lambda_handler_unexpected_error(self, mock_handle_get: Mock) -> None:
        """Test lambda_handler with unexpected error."""
        mock_handle_get.side_effect = Exception("Unexpected error")

        event = {
            "httpMethod": "GET",
            "path": "/widgets/test-widget",
            "body": ""
        }

        response = lambda_handler(event, None)

        assert response["statusCode"] == 500
        body = json.loads(response["body"])
        assert body["error"] == "Internal server error"

