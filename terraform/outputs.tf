# Outputs for the step-alb-poc infrastructure

output "alb_dns_name" {
  description = "DNS name of the Application Load Balancer"
  value       = aws_lb.step_alb_poc.dns_name
}

output "alb_zone_id" {
  description = "Zone ID of the Application Load Balancer"
  value       = aws_lb.step_alb_poc.zone_id
}

output "domain_name" {
  description = "Custom domain name for the application"
  value       = aws_route53_record.step_alb_poc.fqdn
}

output "lambda_function_arn" {
  description = "ARN of the Lambda function"
  value       = aws_lambda_function.widget_service.arn
}

output "lambda_function_name" {
  description = "Name of the Lambda function"
  value       = aws_lambda_function.widget_service.function_name
}

output "dynamodb_table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.step_alb_poc.name
}

output "dynamodb_table_arn" {
  description = "ARN of the DynamoDB table"
  value       = aws_dynamodb_table.step_alb_poc.arn
}

output "cloudwatch_log_group" {
  description = "CloudWatch log group for Lambda function"
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "api_base_url" {
  description = "Base URL for the widget API"
  value       = "http://${aws_route53_record.step_alb_poc.fqdn}/widgets"
}