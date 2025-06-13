# Widget Service Lambda

AWS Lambda function for handling widget CRUD operations via Application Load Balancer.

## Features

- Create widgets with POST requests
- Update widget state with PUT requests  
- Retrieve widget data with GET requests
- Delete widgets with DELETE requests
- DynamoDB integration for persistence
- Comprehensive error handling
- Full test coverage

## API Endpoints

- `POST /widgets/{widget_name}` - Create a new widget
- `PUT /widgets/{widget_name}` - Update widget state and transition time
- `GET /widgets/{widget_name}` - Retrieve widget data
- `DELETE /widgets/{widget_name}` - Delete widget

## Environment Variables

- `DYNAMODB_TABLE_NAME` - DynamoDB table name (defaults to "step-alb-poc")

## Development

```bash
# Install dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Run linting
ruff check

# Run type checking
mypy src/
```