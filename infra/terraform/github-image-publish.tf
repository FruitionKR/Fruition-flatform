# Hosted main workflow builds approved public service revisions. No EKS/state/secrets access.
resource "aws_iam_role" "github_image_publish" {
  name                 = "${var.project}-github-image-publish"
  max_session_duration = 7200
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Federated = aws_iam_openid_connect_provider.github.arn }
      Action    = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
          "token.actions.githubusercontent.com:sub" = "repo:${var.github_repo}:ref:refs/heads/main"
        }
      }
    }]
  })
}

resource "aws_iam_role_policy" "github_image_publish" {
  name = "publish-application-images"
  role = aws_iam_role.github_image_publish.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["ecr:GetAuthorizationToken"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer",
          "ecr:InitiateLayerUpload", "ecr:UploadLayerPart", "ecr:CompleteLayerUpload",
          "ecr:PutImage", "ecr:DescribeImages", "ecr:DescribeRepositories"
        ]
        Resource = [for repository in aws_ecr_repository.services : repository.arn]
      }
    ]
  })
}

output "github_image_publish_role_arn" {
  description = "Repository variable AWS_IMAGE_PUBLISH_ROLE_ARN (main-only ECR publisher)"
  value       = aws_iam_role.github_image_publish.arn
}
