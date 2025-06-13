# Widget Mod Lambda

A Python 3.13 Lambda function that integrates with AWS Step Functions to update widgets via the ALB REST API.

## Overview

This Lambda function is designed to be invoked by AWS Step Functions to modify existing widgets. It accepts Step Functions events containing widget update information and calls the widget service API through the Application Load Balancer (ALB) to update widgets with new status and transition timestamp values.

## Features

- **Step Functions Integration**: Accepts events from AWS Step Functions
- **Widget Updates**: Only performs PUT operations to update existing widgets
- **Status Validation**: Validates status values are either 'in_progress' or 'done'
- **Error Handling**: Comprehensive error handling with structured logging
- **Type Safety**: Full type annotations and mypy compliance
- **Test Coverage**: 98% test coverage with comprehensive test suite

## Event Format

The Lambda function expects Step Functions events with the following structure:

```json
{
  "widget_id": "widget-123",
  "status": "in_progress",
  "transitionAt": 1640995200
}
```

### Required Fields

- `widget_id` (string): The ID of the widget to update (non-empty string)
- `status` (string): The new status value, must be either 'in_progress' or 'done'
- `transitionAt` (number): The new transition timestamp in epoch seconds (non-negative)

## Response Format

On successful execution, the function returns:

```json
{
  "statusCode": 200,
  "body": {
    "message": "Widget updated successfully",
    "widget_id": "widget-123",
    "status": "in_progress",
    "transitionAt": 1640995200,
    "alb_response": {
      // Response from ALB API
    }
  }
}
```

## Environment Variables

- `ALB_ENDPOINT` (required): The ALB endpoint URL for the widget service API

## Error Handling

The function raises `ModLambdaError` exceptions for:

- Missing or invalid required fields
- ALB API connection failures
- API response errors (4xx, 5xx status codes)
- Network timeouts

All errors bubble up to Step Functions for proper workflow error handling.

## Development

### Prerequisites

- Python 3.13+
- pip

### Installation

```bash
# Install in development mode
pip install -e .

# Install with development dependencies
pip install -e ".[dev]"
```

### Testing

```bash
# Run tests
python -m pytest tests/

# Run tests with coverage
python -m pytest tests/ --cov=src --cov-report=html
```

### Code Quality

```bash
# Run linting
python -m ruff check src/ tests/

# Run type checking
python -m mypy src/ tests/

# Format code
python -m ruff format src/ tests/
```

## Infrastructure

The Lambda function is deployed via Terraform with the following AWS resources:

- Lambda function with Python 3.13 runtime
- IAM role with basic execution permissions
- CloudWatch log group for function logs
- Environment variable configuration for ALB endpoint

### IAM Permissions

The Lambda function requires:

- `AWSLambdaBasicExecutionRole` for CloudWatch logs
- No additional AWS service permissions (only makes HTTP calls to ALB)

## Usage in Step Functions

The function is designed to be called from Step Functions state machines:

```json
{
  "Type": "Task",
  "Resource": "arn:aws:lambda:region:account:function:step-alb-poc-widget-mod",
  "Parameters": {
    "widget_id": "$.widget_id",
    "status": "$.status", 
    "transitionAt": "$.transitionAt"
  },
  "Next": "NextState"
}
```

## API Integration

The function calls the widget service API through the ALB using PUT requests:

```
PUT {ALB_ENDPOINT}/widgets/{widget_id}
Content-Type: application/json

{
  "status": "in_progress",
  "transitionAt": 1640995200
}
```

## Monitoring

The function provides structured logging for:

- Incoming Step Functions events
- ALB API requests and responses
- Error conditions and stack traces

All logs are sent to CloudWatch Logs under `/aws/lambda/step-alb-poc-widget-mod`.