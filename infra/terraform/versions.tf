# 소규모 사용자 피드백 profile (docs/Fruition_AWS_MSA_Architecture.md §8) 기준 IaC.
terraform {
  required_version = ">= 1.10, < 2.0"

  required_providers {
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.7"
    }
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }

  # bucket/key/region/kms_key_id는 저장소 밖 backend 설정으로 전달한다.
  # kms_key_id는 terraform-state-bootstrap output state_kms_key_arn 값을 사용한다.
  backend "s3" {
    use_lockfile = true
    encrypt      = true
  }
}

provider "aws" {
  region = var.region

  default_tags {
    tags = {
      Project   = var.project
      ManagedBy = "terraform"
    }
  }
}
