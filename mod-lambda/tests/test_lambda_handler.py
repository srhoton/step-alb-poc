"""Tests for mod lambda handler."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest
import responses

from src.lambda_handler import (
    ModLambdaError,
    lambda_handler,
    update_widget_via_alb,
    validate_event,
)


class TestModLambdaError:
    """Test ModLambdaError exception class."""

    def test_init_with_message_only(self) -> None:
        """Test ModLambdaError initialization with message only."""
        error = ModLambdaError("test message")
        assert str(error) == "test message"
        assert error.message == "test message"
        assert error.status_code == 500

    def test_init_with_message_and_status_code(self) -> None:
        """Test ModLambdaError initialization with message and status code."""
        error = ModLambdaError("test message", 400)
        assert str(error) == "test message"
        assert error.message == "test message"
        assert error.status_code == 400


class TestValidateEvent:
    """Test validate_event function."""

    def test_validate_event_success(self) -> None:
        """Test successful event validation."""
        event = {
            "widget_id": "test-widget-123",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        result = validate_event(event)

        assert result == {
            "widget_id": "test-widget-123",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

    def test_validate_event_with_float_transition_at(self) -> None:
        """Test event validation with float transitionAt."""
        event = {
            "widget_id": "test-widget",
            "status": "done",
            "transitionAt": 1640995200.5,
        }

        result = validate_event(event)

        assert result["transitionAt"] == 1640995200

    def test_validate_event_strips_whitespace(self) -> None:
        """Test event validation strips whitespace from widget_id."""
        event = {
            "widget_id": "  test-widget  ",
            "status": "done",
            "transitionAt": 1640995200,
        }

        result = validate_event(event)

        assert result["widget_id"] == "test-widget"

    def test_validate_event_missing_widget_id(self) -> None:
        """Test validation fails when widget_id is missing."""
        event = {
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "Missing required field: widget_id"
        assert exc_info.value.status_code == 400

    def test_validate_event_missing_status(self) -> None:
        """Test validation fails when status is missing."""
        event = {
            "widget_id": "test-widget",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "Missing required field: status"
        assert exc_info.value.status_code == 400

    def test_validate_event_missing_transition_at(self) -> None:
        """Test validation fails when transitionAt is missing."""
        event = {
            "widget_id": "test-widget",
            "status": "in_progress",
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "Missing required field: transitionAt"
        assert exc_info.value.status_code == 400

    def test_validate_event_empty_widget_id(self) -> None:
        """Test validation fails when widget_id is empty."""
        event = {
            "widget_id": "",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "widget_id must be a non-empty string"
        assert exc_info.value.status_code == 400

    def test_validate_event_whitespace_only_widget_id(self) -> None:
        """Test validation fails when widget_id is whitespace only."""
        event = {
            "widget_id": "   ",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "widget_id must be a non-empty string"
        assert exc_info.value.status_code == 400

    def test_validate_event_non_string_widget_id(self) -> None:
        """Test validation fails when widget_id is not a string."""
        event = {
            "widget_id": 123,
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "widget_id must be a non-empty string"
        assert exc_info.value.status_code == 400

    def test_validate_event_invalid_status(self) -> None:
        """Test validation fails with invalid status."""
        event = {
            "widget_id": "test-widget",
            "status": "invalid_status",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == "status must be either 'in_progress' or 'done'"
        assert exc_info.value.status_code == 400

    def test_validate_event_negative_transition_at(self) -> None:
        """Test validation fails with negative transitionAt."""
        event = {
            "widget_id": "test-widget",
            "status": "in_progress",
            "transitionAt": -1,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == (
            "transitionAt must be a non-negative number (epoch seconds)"
        )
        assert exc_info.value.status_code == 400

    def test_validate_event_string_transition_at(self) -> None:
        """Test validation fails with string transitionAt."""
        event = {
            "widget_id": "test-widget",
            "status": "in_progress",
            "transitionAt": "not_a_number",
        }

        with pytest.raises(ModLambdaError) as exc_info:
            validate_event(event)

        assert str(exc_info.value) == (
            "transitionAt must be a non-negative number (epoch seconds)"
        )
        assert exc_info.value.status_code == 400


class TestUpdateWidgetViaAlb:
    """Test update_widget_via_alb function."""

    @responses.activate
    def test_update_widget_success(self) -> None:
        """Test successful widget update via ALB."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            json={"id": "test-widget", "status": "in_progress"},
            status=200,
        )

        result = update_widget_via_alb(
            "test-widget", "in_progress", 1640995200, "https://test-alb.com"
        )

        assert result == {"id": "test-widget", "status": "in_progress"}
        assert len(responses.calls) == 1

        request = responses.calls[0].request
        assert request.url == "https://test-alb.com/widgets/test-widget"
        assert json.loads(request.body or "") == {
            "status": "in_progress",
            "transitionAt": 1640995200,
        }
        assert request.headers["Content-Type"] == "application/json"

    @responses.activate
    def test_update_widget_success_with_trailing_slash(self) -> None:
        """Test successful widget update with trailing slash in endpoint."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            json={"success": True},
            status=200,
        )

        result = update_widget_via_alb(
            "test-widget", "done", 1640995200, "https://test-alb.com/"
        )

        assert result == {"success": True}

    @responses.activate
    def test_update_widget_empty_response(self) -> None:
        """Test widget update with empty response body."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body="",
            status=204,
        )

        result = update_widget_via_alb(
            "test-widget", "done", 1640995200, "https://test-alb.com"
        )

        assert result == {}

    @responses.activate
    def test_update_widget_4xx_error(self) -> None:
        """Test widget update with 4xx error response."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body="Widget not found",
            status=404,
        )

        with pytest.raises(ModLambdaError) as exc_info:
            update_widget_via_alb(
                "test-widget", "done", 1640995200, "https://test-alb.com"
            )

        assert "ALB API request failed with status 404" in str(exc_info.value)
        assert exc_info.value.status_code == 404

    @responses.activate
    def test_update_widget_5xx_error(self) -> None:
        """Test widget update with 5xx error response."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body="Internal server error",
            status=500,
        )

        with pytest.raises(ModLambdaError) as exc_info:
            update_widget_via_alb(
                "test-widget", "done", 1640995200, "https://test-alb.com"
            )

        assert "ALB API request failed with status 500" in str(exc_info.value)
        assert exc_info.value.status_code == 500

    @responses.activate
    def test_update_widget_timeout(self) -> None:
        """Test widget update with timeout."""
        from requests.exceptions import Timeout

        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body=Timeout("Request timed out"),
        )

        with pytest.raises(ModLambdaError) as exc_info:
            update_widget_via_alb(
                "test-widget", "done", 1640995200, "https://test-alb.com"
            )

        assert str(exc_info.value) == "ALB API request timed out"
        assert exc_info.value.status_code == 504

    @responses.activate
    def test_update_widget_connection_error(self) -> None:
        """Test widget update with connection error."""
        from requests.exceptions import ConnectionError

        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body=ConnectionError("Connection failed"),
        )

        with pytest.raises(ModLambdaError) as exc_info:
            update_widget_via_alb(
                "test-widget", "done", 1640995200, "https://test-alb.com"
            )

        assert str(exc_info.value) == "Failed to connect to ALB API"
        assert exc_info.value.status_code == 502

    @responses.activate
    def test_update_widget_invalid_json_response(self) -> None:
        """Test widget update with invalid JSON response."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body="invalid json",
            status=200,
        )

        result = update_widget_via_alb(
            "test-widget", "done", 1640995200, "https://test-alb.com"
        )

        assert result == {}


class TestLambdaHandler:
    """Test lambda_handler function."""

    @patch.dict(os.environ, {"ALB_ENDPOINT": "https://test-alb.com"})
    @responses.activate
    def test_lambda_handler_success(self) -> None:
        """Test successful lambda handler execution."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            json={"id": "test-widget", "status": "in_progress"},
            status=200,
        )

        event = {
            "widget_id": "test-widget",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        result = lambda_handler(event, None)

        expected = {
            "statusCode": 200,
            "body": {
                "message": "Widget updated successfully",
                "widget_id": "test-widget",
                "status": "in_progress",
                "transitionAt": 1640995200,
                "alb_response": {"id": "test-widget", "status": "in_progress"},
            },
        }

        assert result == expected

    def test_lambda_handler_missing_alb_endpoint(self) -> None:
        """Test lambda handler fails when ALB_ENDPOINT is not set."""
        event = {
            "widget_id": "test-widget",
            "status": "in_progress",
            "transitionAt": 1640995200,
        }

        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(ModLambdaError) as exc_info:
                lambda_handler(event, None)

        assert str(exc_info.value) == "ALB_ENDPOINT environment variable not set"
        assert exc_info.value.status_code == 500

    @patch.dict(os.environ, {"ALB_ENDPOINT": "https://test-alb.com"})
    def test_lambda_handler_invalid_event(self) -> None:
        """Test lambda handler with invalid event."""
        event = {
            "widget_id": "",
            "status": "invalid",
            "transitionAt": -1,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            lambda_handler(event, None)

        assert str(exc_info.value) == "widget_id must be a non-empty string"
        assert exc_info.value.status_code == 400

    @patch.dict(os.environ, {"ALB_ENDPOINT": "https://test-alb.com"})
    @responses.activate
    def test_lambda_handler_alb_api_error(self) -> None:
        """Test lambda handler with ALB API error."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/test-widget",
            body="Widget not found",
            status=404,
        )

        event = {
            "widget_id": "test-widget",
            "status": "done",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            lambda_handler(event, None)

        assert "ALB API request failed with status 404" in str(exc_info.value)
        assert exc_info.value.status_code == 404

    @patch.dict(os.environ, {"ALB_ENDPOINT": "https://test-alb.com"})
    @patch("src.lambda_handler.validate_event")
    def test_lambda_handler_unexpected_error(self, mock_validate: MagicMock) -> None:
        """Test lambda handler with unexpected error."""
        mock_validate.side_effect = ValueError("Unexpected error")

        event = {
            "widget_id": "test-widget",
            "status": "done",
            "transitionAt": 1640995200,
        }

        with pytest.raises(ModLambdaError) as exc_info:
            lambda_handler(event, None)

        assert "Unexpected error: Unexpected error" in str(exc_info.value)
        assert exc_info.value.status_code == 500

    @patch.dict(os.environ, {"ALB_ENDPOINT": "https://test-alb.com"})
    @responses.activate
    def test_lambda_handler_done_status(self) -> None:
        """Test lambda handler with 'done' status."""
        responses.add(
            responses.PUT,
            "https://test-alb.com/widgets/widget-123",
            json={"id": "widget-123", "status": "done"},
            status=200,
        )

        event = {
            "widget_id": "widget-123",
            "status": "done",
            "transitionAt": 1703980800,
        }

        result = lambda_handler(event, None)

        assert result["statusCode"] == 200
        assert result["body"]["status"] == "done"
        assert result["body"]["widget_id"] == "widget-123"
        assert result["body"]["transitionAt"] == 1703980800

