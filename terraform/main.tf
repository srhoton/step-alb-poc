# Local values for configuration
locals {
  # AWS Lambda IP ranges for us-east-1 region
  # These ranges allow Lambda functions to reach ALB endpoints
  # Source: https://docs.aws.amazon.com/general/latest/gr/aws-ip-ranges.html
  lambda_ip_ranges = [
    "52.94.198.112/28",
    "52.94.199.0/24",
    "52.119.205.0/24",
    "52.119.207.0/24",
    "52.119.214.0/23"
  ]
}

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
    description = "HTTP from allowed IPs"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidr_blocks
  }

  ingress {
    description = "HTTP from Lambda IP ranges"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = local.lambda_ip_ranges
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

# ===== MOD-LAMBDA INFRASTRUCTURE =====

# Create mod-lambda deployment package
data "archive_file" "mod_lambda_zip" {
  type        = "zip"
  source_dir  = "${path.root}/../mod-lambda/src"
  output_path = "${path.root}/mod_lambda_deployment.zip"
  excludes    = ["__pycache__", "*.pyc", "tests"]
}

# IAM role for mod-lambda
resource "aws_iam_role" "mod_lambda_role" {
  name = "step-alb-poc-mod-lambda-role"

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
    Name        = "step-alb-poc-mod-lambda-role"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# IAM policy for mod-lambda Step Functions integration
resource "aws_iam_policy" "mod_lambda_step_functions_policy" {
  name        = "step-alb-poc-mod-lambda-step-functions-policy"
  description = "IAM policy for mod-lambda to be invoked by Step Functions"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      }
    ]
  })

  tags = {
    Name        = "step-alb-poc-mod-lambda-step-functions-policy"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Attach Step Functions policy to mod-lambda role
resource "aws_iam_role_policy_attachment" "mod_lambda_step_functions_policy_attachment" {
  role       = aws_iam_role.mod_lambda_role.name
  policy_arn = aws_iam_policy.mod_lambda_step_functions_policy.arn
}

# Attach basic execution role for CloudWatch logs
resource "aws_iam_role_policy_attachment" "mod_lambda_basic_execution" {
  role       = aws_iam_role.mod_lambda_role.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# CloudWatch log group for mod-lambda
resource "aws_cloudwatch_log_group" "mod_lambda_logs" {
  name              = "/aws/lambda/step-alb-poc-widget-mod"
  retention_in_days = 14

  tags = {
    Name        = "step-alb-poc-mod-lambda-logs"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Mod-Lambda function
resource "aws_lambda_function" "widget_mod" {
  filename         = data.archive_file.mod_lambda_zip.output_path
  function_name    = "step-alb-poc-widget-mod"
  role             = aws_iam_role.mod_lambda_role.arn
  handler          = "lambda_handler.lambda_handler"
  source_code_hash = data.archive_file.mod_lambda_zip.output_base64sha256
  runtime          = "python3.13"
  timeout          = 30
  memory_size      = 256

  environment {
    variables = {
      ALB_ENDPOINT = "http://${aws_route53_record.step_alb_poc.name}"
    }
  }

  depends_on = [
    aws_iam_role_policy_attachment.mod_lambda_basic_execution,
    aws_iam_role_policy_attachment.mod_lambda_step_functions_policy_attachment,
    aws_cloudwatch_log_group.mod_lambda_logs,
  ]

  tags = {
    Name        = "step-alb-poc-widget-mod"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Permission for Step Functions to invoke mod-lambda
resource "aws_lambda_permission" "step_functions_invoke_mod_lambda" {
  statement_id  = "AllowExecutionFromStepFunctions"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.widget_mod.function_name
  principal     = "states.amazonaws.com"
}

# ===== STEP FUNCTIONS INFRASTRUCTURE =====

# IAM role for Step Functions
resource "aws_iam_role" "step_functions_role" {
  name = "step-alb-poc-step-functions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "states.amazonaws.com"
        }
      }
    ]
  })

  tags = {
    Name        = "step-alb-poc-step-functions-role"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# IAM policy for Step Functions to invoke Lambda
resource "aws_iam_policy" "step_functions_lambda_policy" {
  name        = "step-alb-poc-step-functions-lambda-policy"
  description = "IAM policy for Step Functions to invoke mod-lambda"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "lambda:InvokeFunction"
        ]
        Resource = aws_lambda_function.widget_mod.arn
      },
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogDelivery",
          "logs:GetLogDelivery",
          "logs:UpdateLogDelivery",
          "logs:DeleteLogDelivery",
          "logs:ListLogDeliveries",
          "logs:PutResourcePolicy",
          "logs:DescribeResourcePolicies",
          "logs:DescribeLogGroups"
        ]
        Resource = "*"
      }
    ]
  })

  tags = {
    Name        = "step-alb-poc-step-functions-lambda-policy"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Attach Lambda invoke policy to Step Functions role
resource "aws_iam_role_policy_attachment" "step_functions_lambda_policy_attachment" {
  role       = aws_iam_role.step_functions_role.name
  policy_arn = aws_iam_policy.step_functions_lambda_policy.arn
}

# CloudWatch log group for Step Functions
resource "aws_cloudwatch_log_group" "step_functions_logs" {
  name              = "/aws/stepfunctions/step-alb-poc-widget-state-machine"
  retention_in_days = 14

  tags = {
    Name        = "step-alb-poc-step-functions-logs"
    Environment = "dev"
    ManagedBy   = "terraform"
  }
}

# Step Functions state machine definition
locals {
  state_machine_definition = jsonencode({
    Comment = "Widget state transition management"
    StartAt = "WaitForInitialTransition"
    States = {
      WaitForInitialTransition = {
        Type          = "Wait"
        TimestampPath = "$.transitionAt"
        Next          = "UpdateToInProgress"
      }
      UpdateToInProgress = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.widget_mod.function_name
          Payload = {
            "widget_id.$" = "$.widget_id"
            "status"      = "in_progress"
          }
        }
        ResultPath = "$.lambdaResult"
        Next       = "WaitForFinalTransition"
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed"]
            IntervalSeconds = 2
            MaxAttempts     = 1
            BackoffRate     = 2.0
          }
        ]
      }
      WaitForFinalTransition = {
        Type    = "Wait"
        Seconds = 3600
        Next    = "UpdateToDone"
      }
      UpdateToDone = {
        Type     = "Task"
        Resource = "arn:aws:states:::lambda:invoke"
        Parameters = {
          FunctionName = aws_lambda_function.widget_mod.function_name
          Payload = {
            "widget_id.$" = "$.widget_id"
            "status"      = "done"
          }
        }
        End = true
        Retry = [
          {
            ErrorEquals     = ["States.TaskFailed"]
            IntervalSeconds = 2
            MaxAttempts     = 1
            BackoffRate     = 2.0
          }
        ]
      }
    }
  })
}

# Step Functions state machine
resource "aws_sfn_state_machine" "widget_state_machine" {
  name       = "step-alb-poc-widget-state-machine"
  role_arn   = aws_iam_role.step_functions_role.arn
  definition = local.state_machine_definition

  logging_configuration {
    log_destination        = "${aws_cloudwatch_log_group.step_functions_logs.arn}:*"
    include_execution_data = true
    level                  = "ERROR"
  }

  tags = {
    Name        = "step-alb-poc-widget-state-machine"
    Environment = "dev"
    ManagedBy   = "terraform"
  }

  depends_on = [
    aws_iam_role_policy_attachment.step_functions_lambda_policy_attachment,
    aws_cloudwatch_log_group.step_functions_logs,
  ]
}