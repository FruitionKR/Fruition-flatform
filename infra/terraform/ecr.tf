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

# 서비스별 빌드 태그(b-…)는 바뀐 서비스만 새로 쌓인다. 이전 release ID 태그(schema 1·2)와 함께
# 저장소마다 최근 60개 이미지를 보존한다(이전 정책 10개).
# 실행 중인 digest와 rollback 대상 digest가 이 범위를 벗어나면 만료되어 검증에서 실패한다.
resource "aws_ecr_lifecycle_policy" "services" {
  for_each   = aws_ecr_repository.services
  repository = each.value.name

  policy = jsonencode({
    rules = [
      {
        # 빌드 태그(b-)·이전 release 태그·태그 없는 하위 이미지를 함께 센다. 우선순위로 나눠도
        # tagStatus any 규칙은 앞 규칙이 남긴 이미지까지 세므로 한 규칙으로 넉넉히 둔다.
        rulePriority = 1
        description  = "keep last 60 images"
        selection = {
          tagStatus   = "any"
          countType   = "imageCountMoreThan"
          countNumber = 60
        }
        action = { type = "expire" }
      }
    ]
  })
}
