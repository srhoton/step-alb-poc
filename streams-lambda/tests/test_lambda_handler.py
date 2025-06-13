import json
import os
from unittest.mock import Mock, patch

import pytest
from botocore.exceptions import ClientError

from src.lambda_handler import (
    StepFunctionExecutionError,
    StreamProcessorError,
    _extract_widget_data,
    _should_process_record,
    _trigger_step_function,
    lambda_handler,
)


class TestLambdaHandler:
    """Test cases for the main lambda_handler function."""

    @patch.dict(
        os.environ,
        {
            "STEP_FUNCTION_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:sm"
        },
    )
    @patch('src.lambda_handler.boto3.client')
    def test_lambda_handler_success(self, mock_boto_client):
        """Test successful processing of stream records."""
        mock_sfn_client = Mock()
        mock_boto_client.return_value = mock_sfn_client
        mock_sfn_client.start_execution.return_value = {
            "executionArn": (
                "arn:aws:states:us-east-1:123456789012:execution:test:test-exec"
            )
        }

        event = {
            'Records': [
                {
                    'eventName': 'INSERT',
                    'dynamodb': {
                        'NewImage': {
                            'PK': {'S': 'widget-123'},
                            'SK': {'S': 'new'},
                            'transitionAt': {'N': '1704110400'}
                        }
                    }
                }
            ]
        }

        result = lambda_handler(event, {})

        assert result['processed_count'] == 1
        assert result['total_records'] == 1
        assert result['errors'] == []
        mock_sfn_client.start_execution.assert_called_once()

    def test_lambda_handler_missing_env_var(self):
        """Test lambda_handler raises error when STEP_FUNCTION_ARN is missing."""
        with patch.dict(os.environ, {}, clear=True):
            with pytest.raises(
                StreamProcessorError,
                match="STEP_FUNCTION_ARN environment variable is required",
            ):
                lambda_handler({'Records': []}, {})

    @patch.dict(
        os.environ,
        {
            "STEP_FUNCTION_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:sm"
        },
    )
    @patch('src.lambda_handler.boto3.client')
    def test_lambda_handler_with_errors(self, mock_boto_client):
        """Test lambda_handler handles processing errors gracefully."""
        mock_sfn_client = Mock()
        mock_boto_client.return_value = mock_sfn_client

        event = {
            'Records': [
                {
                    'eventName': 'INSERT',
                    'dynamodb': {
                        'NewImage': {
                            'PK': {'S': 'widget-123'},
                            'SK': {'S': 'new'}
                            # Missing transitionAt to trigger error
                        }
                    }
                }
            ]
        }

        result = lambda_handler(event, {})

        assert result['processed_count'] == 0
        assert result['total_records'] == 1
        assert len(result['errors']) == 1
        assert 'Missing or invalid transitionAt' in result['errors'][0]

    @patch.dict(
        os.environ,
        {
            "STEP_FUNCTION_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:sm"
        },
    )
    @patch('src.lambda_handler.boto3.client')
    def test_lambda_handler_empty_records(self, mock_boto_client):
        """Test lambda_handler with no records."""
        result = lambda_handler({'Records': []}, {})

        assert result['processed_count'] == 0
        assert result['total_records'] == 0
        assert result['errors'] == []


class TestShouldProcessRecord:
    """Test cases for _should_process_record function."""

    def test_should_process_insert_record(self):
        """Test processing INSERT record without OldImage."""
        record = {
            'eventName': 'INSERT',
            'dynamodb': {
                'NewImage': {'PK': {'S': 'widget-123'}},
                'OldImage': None
            }
        }

        assert _should_process_record(record) is True

    def test_should_not_process_modify_record(self):
        """Test not processing MODIFY record."""
        record = {
            'eventName': 'MODIFY',
            'dynamodb': {
                'NewImage': {'PK': {'S': 'widget-123'}},
                'OldImage': {'PK': {'S': 'widget-123'}}
            }
        }

        assert _should_process_record(record) is False

    def test_should_not_process_remove_record(self):
        """Test not processing REMOVE record."""
        record = {
            'eventName': 'REMOVE',
            'dynamodb': {
                'OldImage': {'PK': {'S': 'widget-123'}}
            }
        }

        assert _should_process_record(record) is False

    def test_should_not_process_record_with_old_image(self):
        """Test not processing record with OldImage present."""
        record = {
            'eventName': 'INSERT',
            'dynamodb': {
                'NewImage': {'PK': {'S': 'widget-123'}},
                'OldImage': {'PK': {'S': 'widget-old'}}
            }
        }

        assert _should_process_record(record) is False

    def test_should_not_process_record_without_new_image(self):
        """Test not processing record without NewImage."""
        record = {
            'eventName': 'INSERT',
            'dynamodb': {
                'OldImage': None
            }
        }

        assert _should_process_record(record) is False


class TestExtractWidgetData:
    """Test cases for _extract_widget_data function."""

    def test_extract_widget_data_success(self):
        """Test successful extraction of widget data."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': 'widget-123'},
                    'SK': {'S': 'new'},
                    'transitionAt': {'N': '1704110400'}
                }
            }
        }

        result = _extract_widget_data(record)

        assert result == {
            'widget_id': 'widget-123',
            'state': 'new',
            'transitionAt': '2024-01-01T12:00:00+00:00'
        }

    def test_extract_widget_data_missing_pk(self):
        """Test error when PK is missing."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'SK': {'S': 'new'},
                    'transitionAt': {'N': '1704110400'}
                }
            }
        }

        with pytest.raises(StreamProcessorError, match="Missing or invalid PK"):
            _extract_widget_data(record)

    def test_extract_widget_data_missing_sk(self):
        """Test error when SK is missing."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': 'widget-123'},
                    'transitionAt': {'N': '1704110400'}
                }
            }
        }

        with pytest.raises(StreamProcessorError, match="Missing or invalid SK"):
            _extract_widget_data(record)

    def test_extract_widget_data_missing_transition_at(self):
        """Test error when transitionAt is missing."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': 'widget-123'},
                    'SK': {'S': 'new'}
                }
            }
        }

        with pytest.raises(
            StreamProcessorError, match="Missing or invalid transitionAt"
        ):
            _extract_widget_data(record)

    def test_extract_widget_data_empty_values(self):
        """Test error when values are empty strings."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': ''},
                    'SK': {'S': 'new'},
                    'transitionAt': {'N': '1704110400'}
                }
            }
        }

        with pytest.raises(StreamProcessorError, match="Missing or invalid PK"):
            _extract_widget_data(record)

    def test_extract_widget_data_invalid_transition_at_number(self):
        """Test error when transitionAt is not a valid number."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': 'widget-123'},
                    'SK': {'S': 'new'},
                    'transitionAt': {'N': 'invalid-number'}
                }
            }
        }

        with pytest.raises(
            StreamProcessorError, match="transitionAt must be a valid number"
        ):
            _extract_widget_data(record)

    def test_extract_widget_data_invalid_timestamp_range(self):
        """Test error when transitionAt is out of valid timestamp range."""
        record = {
            'dynamodb': {
                'NewImage': {
                    'PK': {'S': 'widget-123'},
                    'SK': {'S': 'new'},
                    'transitionAt': {'N': '9999999999999'}  # Far future timestamp
                }
            }
        }

        with pytest.raises(
            StreamProcessorError, match="transitionAt must be a valid timestamp"
        ):
            _extract_widget_data(record)


class TestTriggerStepFunction:
    """Test cases for _trigger_step_function function."""

    @patch('src.lambda_handler.datetime')
    def test_trigger_step_function_success(self, mock_datetime):
        """Test successful Step Function trigger."""
        mock_datetime.now.return_value.timestamp.return_value = 1704110400
        mock_client = Mock()
        mock_client.start_execution.return_value = {
            "executionArn": (
                "arn:aws:states:us-east-1:123456789012:execution:test:test-exec"
            )
        }

        widget_data = {
            'widget_id': 'widget-123',
            'state': 'new',
            'transitionAt': '2024-01-01T12:00:00+00:00'
        }

        result = _trigger_step_function(
            mock_client,
            'arn:aws:states:us-east-1:123456789012:stateMachine:test',
            widget_data
        )

        expected_arn = "arn:aws:states:us-east-1:123456789012:execution:test:test-exec"
        assert result == expected_arn
        mock_client.start_execution.assert_called_once_with(
            stateMachineArn='arn:aws:states:us-east-1:123456789012:stateMachine:test',
            name='widget-widget-123-1704110400',
            input=json.dumps(widget_data)
        )

    def test_trigger_step_function_client_error(self):
        """Test Step Function trigger with ClientError."""
        mock_client = Mock()
        mock_client.start_execution.side_effect = ClientError(
            {'Error': {'Code': 'InvalidParameterValue', 'Message': 'Invalid input'}},
            'StartExecution'
        )

        widget_data = {
            'widget_id': 'widget-123',
            'state': 'new',
            'transitionAt': '2024-01-01T12:00:00+00:00'
        }

        with pytest.raises(
            StepFunctionExecutionError, match="Failed to start Step Function execution"
        ):
            _trigger_step_function(
                mock_client,
                'arn:aws:states:us-east-1:123456789012:stateMachine:test',
                widget_data
            )


class TestIntegration:
    """Integration test cases."""

    @patch.dict(
        os.environ,
        {
            "STEP_FUNCTION_ARN": "arn:aws:states:us-east-1:123456789012:stateMachine:sm"
        },
    )
    @patch('src.lambda_handler.boto3.client')
    def test_end_to_end_processing(self, mock_boto_client):
        """Test end-to-end processing of multiple records."""
        mock_sfn_client = Mock()
        mock_boto_client.return_value = mock_sfn_client
        mock_sfn_client.start_execution.return_value = {
            "executionArn": (
                "arn:aws:states:us-east-1:123456789012:execution:test:test-exec"
            )
        }

        event = {
            'Records': [
                # Valid INSERT record
                {
                    'eventName': 'INSERT',
                    'dynamodb': {
                        'NewImage': {
                            'PK': {'S': 'widget-123'},
                            'SK': {'S': 'new'},
                            'transitionAt': {'N': '1704110400'}
                        }
                    }
                },
                # MODIFY record (should be skipped)
                {
                    'eventName': 'MODIFY',
                    'dynamodb': {
                        'NewImage': {
                            'PK': {'S': 'widget-456'},
                            'SK': {'S': 'in_progress'},
                            'transitionAt': {'N': '1704113600'}
                        },
                        'OldImage': {
                            'PK': {'S': 'widget-456'},
                            'SK': {'S': 'new'},
                            'transitionAt': {'N': '1704112200'}
                        }
                    }
                },
                # Another valid INSERT record
                {
                    'eventName': 'INSERT',
                    'dynamodb': {
                        'NewImage': {
                            'PK': {'S': 'widget-789'},
                            'SK': {'S': 'new'},
                            'transitionAt': {'N': '1704117200'}
                        }
                    }
                }
            ]
        }

        result = lambda_handler(event, {})

        # Should process 2 INSERT records, skip 1 MODIFY record
        assert result['processed_count'] == 2
        assert result['total_records'] == 3
        assert result['errors'] == []
        assert mock_sfn_client.start_execution.call_count == 2

