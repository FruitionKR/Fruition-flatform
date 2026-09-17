# §9.1: GitHub Actions는 장기 access key 대신 OIDC로 deploy role을 assume한다.
variable "github_oidc_subject_prefix" {
  description = "GitHub OIDC settings API의 sub_claim_prefix. Immutable subject는 owner/repository ID를 포함한다."
  type        = string
  validation {
    condition = (
      can(regex("^repo:[A-Za-z0-9_.-]+(@[0-9]+)?/[A-Za-z0-9_.-]+(@[0-9]+)?$", var.github_oidc_subject_prefix)) &&
      replace(var.github_oidc_subject_prefix, "/@[0-9]+/", "") == "repo:${var.github_repo}"
    )
    error_message = "github_repo와 일치하는 실제 sub_claim_prefix를 GitHub API에서 확인해 입력하세요."
  }
}

resource "aws_iam_openid_connect_provider" "github" {
  url            = "https://token.actions.githubusercontent.com"
  client_id_list = ["sts.amazonaws.com"]
  # GitHub OIDC 루트 CA thumbprint (AWS가 신뢰 검증을 자체 수행하므로 값은 형식 요건)
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

resource "aws_iam_role" "github_deploy" {
  name = "${var.project}-github-deploy"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Federated = aws_iam_openid_connect_provider.github.arn
        }
        Action = "sts:AssumeRoleWithWebIdentity"
        Condition = {
          StringEquals = {
            "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
            "token.actions.githubusercontent.com:sub" = "${var.github_oidc_subject_prefix}:environment:${var.github_deploy_environment}"
          }
        }
      }
    ]
  })
}

# 배포 role은 게시된 ECR 이미지 조회만 허용한다. 별도 publisher role이 이미지를 게시한다.
resource "aws_iam_role_policy" "github_deploy_alerts" {
  name = "deployment-failure-alerts"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["sns:Publish"]
      Resource = aws_sns_topic.operations.arn
    }]
  })
}

resource "aws_iam_role_policy" "github_deploy_ecr" {
  name = "application-images"
  role = aws_iam_role.github_deploy.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:ListImages", "ecr:DescribeImages"]
        Resource = [for repository in aws_ecr_repository.services : repository.arn]
      }
    ]
  })
}

resource "aws_iam_role_policy" "github_deploy_eks" {
  name = "eks-describe"
  role = aws_iam_role.github_deploy.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["eks:DescribeCluster"]
        Resource = [module.eks.cluster_arn]
      }
    ]
  })
}
