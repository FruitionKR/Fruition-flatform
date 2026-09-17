# §9.1: GitHub Actions는 장기 access key 대신 OIDC로 deploy role을 assume한다.
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
            "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:environment:${var.github_deploy_environment}"
          }
        }
      }
    ]
  })
}

# 플랫폼은 게시된 ECR 이미지 태그만 조회한다. 이미지 게시 권한은 서비스 저장소가 소유한다.
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
        Action   = ["ecr:ListImages"]
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
