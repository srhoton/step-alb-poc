import json
import logging
import os
from datetime import datetime, timezone
from typing import Any, Dict

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)


class StreamProcessorError(Exception):
    """Exception raised for errors in stream processing."""

    pass


class StepFunctionExecutionError(StreamProcessorError):
    """Exception raised for Step Function execution errors."""

    pass


def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Process DynamoDB stream records and trigger Step Functions.

    Process DynamoDB stream records and trigger Step Functions for new widget records.

    Args:
        event: DynamoDB stream event containing records
        context: Lambda context object

    Returns:
        Dict containing processing results
    """
    logger.info(f"Processing {len(event.get('Records', []))} stream records")

    step_function_arn = os.environ.get('STEP_FUNCTION_ARN')
    if not step_function_arn:
        raise StreamProcessorError("STEP_FUNCTION_ARN environment variable is required")

    sfn_client = boto3.client('stepfunctions')

    processed_count = 0
    errors = []

    for record in event.get('Records', []):
        try:
            if _should_process_record(record):
                widget_data = _extract_widget_data(record)
                _trigger_step_function(sfn_client, step_function_arn, widget_data)
                processed_count += 1
                logger.info(
                    f"Triggered Step Function for widget: {widget_data['widget_id']}"
                )
        except Exception as e:
            error_msg = f"Error processing record: {e!s}"
            logger.error(error_msg)
            errors.append(error_msg)

    result = {
        'processed_count': processed_count,
        'total_records': len(event.get('Records', [])),
        'errors': errors
    }

    logger.info(f"Processing complete: {result}")
    return result


def _should_process_record(record: Dict[str, Any]) -> bool:
    """Determine if a DynamoDB stream record should be processed.

    Only process INSERT events (new records with no OLD image).

    Args:
        record: DynamoDB stream record

    Returns:
        True if record should be processed
    """
    event_name = record.get('eventName')
    dynamodb_data = record.get('dynamodb', {})

    # Only process INSERT events
    if event_name != 'INSERT':
        logger.debug(f"Skipping record with eventName: {event_name}")
        return False

    # Verify no OLD image exists (should be None for INSERT)
    if dynamodb_data.get('OldImage') is not None:
        logger.debug("Skipping record with OldImage present")
        return False

    # Verify NEW image exists
    if dynamodb_data.get('NewImage') is None:
        logger.debug("Skipping record without NewImage")
        return False

    return True


def _extract_widget_data(record: Dict[str, Any]) -> Dict[str, Any]:
    """Extract widget data from DynamoDB stream record.

    Args:
        record: DynamoDB stream record

    Returns:
        Dict containing widget_id, state, and transitionAt (as ISO-8601 string)

    Raises:
        StreamProcessorError: If required data is missing
    """
    new_image = record.get('dynamodb', {}).get('NewImage', {})

    # Extract PK (widget_id)
    pk_data = new_image.get('PK', {})
    widget_id = pk_data.get('S')
    if not widget_id:
        raise StreamProcessorError("Missing or invalid PK (widget_id) in record")

    # Extract SK (state)
    sk_data = new_image.get('SK', {})
    state = sk_data.get('S')
    if not state:
        raise StreamProcessorError("Missing or invalid SK (state) in record")

    # Extract transitionAt (number/epoch timestamp)
    transition_at_data = new_image.get('transitionAt', {})
    transition_at = transition_at_data.get('N')
    if not transition_at:
        raise StreamProcessorError("Missing or invalid transitionAt in record")

    # Convert to float for epoch timestamp
    try:
        transition_at_epoch = float(transition_at)
    except (ValueError, TypeError) as e:
        raise StreamProcessorError("transitionAt must be a valid number") from e

    # Convert epoch timestamp to ISO-8601 format for Step Functions
    try:
        transition_at_iso = datetime.fromtimestamp(
            transition_at_epoch, tz=timezone.utc
        ).isoformat()
    except (ValueError, OSError) as e:
        raise StreamProcessorError("transitionAt must be a valid timestamp") from e

    return {
        'widget_id': widget_id,
        'state': state,
        'transitionAt': transition_at_iso
    }


def _trigger_step_function(
    client: Any,
    state_machine_arn: str,
    widget_data: Dict[str, Any],
) -> str:
    """Trigger Step Function execution with widget data.

    Args:
        client: Step Functions boto3 client
        state_machine_arn: ARN of the Step Function state machine
        widget_data: Widget data to pass as input

    Returns:
        Execution ARN

    Raises:
        StepFunctionExecutionError: If execution fails
    """
    execution_name = (
        f"widget-{widget_data['widget_id']}-{int(datetime.now().timestamp())}"
    )

    try:
        response = client.start_execution(
            stateMachineArn=state_machine_arn,
            name=execution_name,
            input=json.dumps(widget_data),
        )

        execution_arn: str = response["executionArn"]
        logger.info(f"Started Step Function execution: {execution_arn}")
        return execution_arn

    except ClientError as e:
        error_msg = f"Failed to start Step Function execution: {e}"
        logger.error(error_msg)
        raise StepFunctionExecutionError(error_msg) from e
