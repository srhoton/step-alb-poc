data "aws_vpc" "main_vpc" {
  tags = {
    Name = "dev-env-default_vpc"
  }
}

data "aws_subnets" "public_subnets" {
  filter {
    name   = "vpc-id"
    values = [data.aws_vpc.main_vpc.id]
  }

  tags = {
    Name = "public-*"
  }
}

data "aws_route53_zone" "steverhoton_com" {
  zone_id = "Z0738030YKODO2ZBZ8JM"
}