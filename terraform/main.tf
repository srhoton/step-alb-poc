resource "aws_dynamodb_table" "step_alb_poc" {
  name           = "step-alb-poc"
  billing_mode   = "PAY_PER_REQUEST"
  hash_key       = "PK"
  range_key      = "SK"
  stream_enabled = true
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

resource "aws_lb" "step_alb_poc" {
  name               = "step-alb-poc"
  internal           = false
  load_balancer_type = "application"
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