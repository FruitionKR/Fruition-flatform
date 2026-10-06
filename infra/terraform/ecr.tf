# 서비스별 컨테이너 레지스트리. pipeline-api·ingest-worker는 같은 이미지(fruition-pipeline)를 쓴다.
# frontend는 Fargate에서 실행하는 Next.js 화면이다.
locals {
  ecr_repos = ["document-svc", "access-svc", "pipeline", "converter", "frontend"]
}

resource "aws_ecr_repository" "services" {
  for_each = toset(local.ecr_repos)

  name                 = "${var.project}-${each.key}"
  image_tag_mutability = "IMMUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }
}

# 서비스별 빌드 태그(b-…)는 바뀐 서비스만 새로 쌓이므로 최근 30개 빌드를 보존한다.
# 이전 release ID 태그(schema 1·2)는 rollback 후보로 별도 30개를 보존한다.
# 실행 중인 digest와 rollback 대상 digest가 이 범위를 벗어나면 만료되어 검증에서 실패한다.
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        rulePriority = 1
        description  = "keep last 30 per-service build images"
        selection = {
          tagStatus     = "tagged"
          tagPrefixList = ["b-"]
          countType     = "imageCountMoreThan"
          countNumber   = 30
        }
        action = { type = "expire" }
      },
      {
        rulePriority = 2
        description  = "keep last 30 legacy release images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 30
        }
        action = { type = "expire" }
      }
    ]
  })
}
