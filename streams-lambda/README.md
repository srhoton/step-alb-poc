# Widget Streams Lambda

AWS Lambda function for processing DynamoDB streams and triggering Step Functions.

## Functionality

This Lambda function:
- Processes DynamoDB stream records from the `step-alb-poc` table
- Identifies new widget records (INSERT events without OLD image)
- Extracts widget_id (PK), state (SK), and transitionAt attributes
- Triggers Step Function executions for state transitions

## Dependencies

- boto3 >= 1.34.0
- python-json-logger >= 2.0.0

## Development

Install development dependencies:
```bash
pip install -e .[dev]
```

Run tests:
```bash
pytest
```

Run linting and type checking:
```bash
ruff check
mypy src/
```