# Step ALB POC Terraform Infrastructure

This Terraform configuration deploys a complete serverless widget API infrastructure on AWS.

## Architecture

- **Application Load Balancer (ALB)**: Routes HTTP requests to Lambda function
- **AWS Lambda**: Python 3.13 function handling CRUD operations for widgets
- **DynamoDB**: NoSQL database for widget storage with PK/SK schema
- **CloudWatch**: Logging for Lambda function monitoring
- **Route 53**: Custom domain name mapping

## Prerequisites

- Terraform >= 1.0
- AWS CLI configured with appropriate credentials
- Existing VPC with public subnets (tagged as "public-*")
- Route 53 hosted zone for domain

## Deployment

1. Initialize Terraform:
   ```bash
   terraform init
   ```

2. Review the plan:
   ```bash
   terraform plan
   ```

3. Apply the configuration:
   ```bash
   terraform apply
   ```

## API Endpoints

After deployment, the API will be available at: `http://step-alb-poc.steverhoton.com/widgets`

### Supported Operations

- `POST /widgets/{widget_name}` - Create a new widget
- `GET /widgets/{widget_name}` - Retrieve widget data
- `PUT /widgets/{widget_name}` - Update widget state and transition time
- `DELETE /widgets/{widget_name}` - Delete a widget

### Example Usage

```bash
# Create a widget
curl -X POST http://step-alb-poc.steverhoton.com/widgets/my-widget

# Get widget data
curl -X GET http://step-alb-poc.steverhoton.com/widgets/my-widget

# Update widget
curl -X PUT http://step-alb-poc.steverhoton.com/widgets/my-widget \
  -H "Content-Type: application/json" \
  -d '{"state": "active", "transitionAt": 1609459200}'

# Delete widget
curl -X DELETE http://step-alb-poc.steverhoton.com/widgets/my-widget
```

## Resources Created

- DynamoDB table: `step-alb-poc`
- Lambda function: `step-alb-poc-widget-service`
- ALB: `step-alb-poc`
- IAM role and policies for Lambda execution and DynamoDB access
- CloudWatch log group: `/aws/lambda/step-alb-poc-widget-service`
- Route 53 record: `step-alb-poc.steverhoton.com`

## Monitoring

Lambda function logs are available in CloudWatch:
```bash
aws logs tail /aws/lambda/step-alb-poc-widget-service --follow
```

## Cleanup

To destroy all resources:
```bash
terraform destroy
```