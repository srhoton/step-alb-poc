terraform {
  backend "s3" {
    bucket = "srhoton-tfstate"
    key    = "step-alb-poc/terraform.tfstate"
    region = "us-east-1"
  }
}