terraform {
  required_version = ">= 1.9"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 6.0"
    }
  }

  # Estado remoto recomendado (descomente e ajuste). O lock nativo do S3 dispensa DynamoDB.
  # backend "s3" {
  #   bucket       = "meu-terraform-state"
  #   key          = "it-asset-lakehouse/terraform.tfstate"
  #   region       = "sa-east-1"
  #   encrypt      = true
  #   use_lockfile = true
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      project     = var.project
      environment = var.environment
      managed_by  = "terraform"
      repository  = var.github_repository
    }
  }
}
