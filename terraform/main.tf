resource "aws_dynamodb_table" "step_alb_poc" {
  name             = "step-alb-poc"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "PK"
  range_key        = "SK"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  tags = {
    Name        = "step-alb-poc"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Security group for ALB
resource "aws_security_group" "alb_sg" {
  name        = "step-alb-poc-alb-sg"
  description = "Security group for step-alb-poc ALB"
  vpc_id      = data.aws_vpc.main_vpc.id

  ingress {
    description = "HTTP from current IP"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["108.39.232.76/32"]
  }

  egress {
    from_port        = 0
    to_port          = 0
    protocol         = "-1"
    cidr_blocks      = ["0.0.0.0/0"]
    ipv6_cidr_blocks = ["::/0"]
  }

  tags = {
    Name        = "step-alb-poc-alb-sg"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

resource "aws_lb" "step_alb_poc" {
  name               = "step-alb-poc"
  internal           = false
  load_balancer_type = "application"
  security_groups    = [aws_security_group.alb_sg.id]
  subnets            = data.aws_subnets.public_subnets.ids

  enable_deletion_protection = false

  tags = {
    Name        = "step-alb-poc"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

resource "aws_route53_record" "step_alb_poc" {
  zone_id = data.aws_route53_zone.steverhoton_com.zone_id
  name    = "step-alb-poc.steverhoton.com"
  type    = "A"

  alias {
    name                   = aws_lb.step_alb_poc.dns_name
    zone_id                = aws_lb.step_alb_poc.zone_id
    evaluate_target_health = true
  }
}

# Create Lambda deployment package
data "archive_file" "lambda_zip" {
  type        = "zip"
  source_dir  = "${path.root}/../service-lambda/src"
  output_path = "${path.root}/lambda_deployment.zip"
  excludes    = ["__pycache__", "*.pyc", "tests"]
}

# IAM role for Lambda
resource "aws_iam_role" "lambda_role" {
  name = "step-alb-poc-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "lambda.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "step-alb-poc-lambda-role"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# IAM policy for DynamoDB access
resource "aws_iam_policy" "lambda_dynamodb_policy" {
  name        = "step-alb-poc-lambda-dynamodb-policy"
  description = "IAM policy for Lambda to access DynamoDB"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan",
          "dynamodb:Query"
        ]
        Resource = aws_dynamodb_table.step_alb_poc.arn
      }
    ]
  })

  tags = {
    Name        = "step-alb-poc-lambda-dynamodb-policy"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Attach DynamoDB policy to Lambda role
resource "aws_iam_role_policy_attachment" "lambda_dynamodb_policy_attachment" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = aws_iam_policy.lambda_dynamodb_policy.arn
}

# Attach basic execution role for CloudWatch logs
resource "aws_iam_role_policy_attachment" "lambda_basic_execution" {
  role       = aws_iam_role.lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# CloudWatch log group for Lambda
resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/step-alb-poc-widget-service"
  retention_in_days = 14

  tags = {
    Name        = "step-alb-poc-lambda-logs"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Lambda function
resource "aws_lambda_function" "widget_service" {
  filename         = data.archive_file.lambda_zip.output_path
  function_name    = "step-alb-poc-widget-service"
  role             = aws_iam_role.lambda_role.arn
  handler          = "lambda_handler.lambda_handler"
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  runtime          = "python3.13"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      DYNAMODB_TABLE_NAME = aws_dynamodb_table.step_alb_poc.name
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_basic_execution,
    aws_iam_role_policy_attachment.lambda_dynamodb_policy_attachment,
    aws_cloudwatch_log_group.lambda_logs,
  ]

  tags = {
    Name        = "step-alb-poc-widget-service"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# ALB target group for Lambda
resource "aws_lb_target_group" "lambda_tg" {
  name        = "step-alb-poc-lambda-tg"
  target_type = "lambda"

  tags = {
    Name        = "step-alb-poc-lambda-tg"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Attach Lambda to target group
resource "aws_lb_target_group_attachment" "lambda_attachment" {
  target_group_arn = aws_lb_target_group.lambda_tg.arn
  target_id        = aws_lambda_function.widget_service.arn
  depends_on       = [aws_lambda_permission.alb_invoke]
}

# Permission for ALB to invoke Lambda
resource "aws_lambda_permission" "alb_invoke" {
  statement_id  = "AllowExecutionFromALB"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.widget_service.function_name
  principal     = "elasticloadbalancing.amazonaws.com"
  source_arn    = aws_lb_target_group.lambda_tg.arn
}

# ALB listener
resource "aws_lb_listener" "web" {
  load_balancer_arn = aws_lb.step_alb_poc.arn
  port              = "80"
  protocol          = "HTTP"

  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.lambda_tg.arn
  }

  tags = {
    Name        = "step-alb-poc-listener"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}