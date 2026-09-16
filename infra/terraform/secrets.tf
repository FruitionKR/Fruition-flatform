# 앱 시크릿 원본 (k8s/base/secret.yaml 평문 대체).
# ExternalSecrets Operator가 서비스별 허용 키만 개별 Kubernetes Secret으로 투영한다.
# 초기값만 Terraform이 넣고 이후 값 관리는 콘솔/CLI — ignore_changes로 덮어쓰지 않는다.
# DB 계정 비밀번호는 init-db-isolation.sh 실행 시 여기 값과 동일하게 넣어야 한다 (README 절차).
resource "aws_secretsmanager_secret" "app" {
  name = "${var.project}/app"
}

resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "random_password" "internal_callback_token" {
  length  = 48
  special = false
}

resource "random_password" "agent_internal_token" {
  length  = 48
  special = false
}

resource "random_id" "mfa_encryption_key" {
  byte_length = 32
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id

  secret_string = jsonencode({
    # --- PostgreSQL (access RDS / core RDS 분리) ---
    ACCESS_DB_RUNTIME_PASSWORD   = random_password.db_role["access_runtime"].result
    ACCESS_DB_MIGRATION_PASSWORD = random_password.db_role["access_migration"].result
    CORE_DB_RUNTIME_PASSWORD     = random_password.db_role["core_runtime"].result
    CORE_DB_MIGRATION_PASSWORD   = random_password.db_role["core_migration"].result
    AI_DB_RUNTIME_PASSWORD       = random_password.db_role["ai_runtime"].result
    AI_DB_MIGRATION_PASSWORD     = random_password.db_role["ai_migration"].result
    # ai-svc runtime 저장소는 core RDS 인스턴스의 ai_db에 격리한다.
    AI_DATABASE_URL     = "postgresql://ai_runtime:${random_password.db_role["ai_runtime"].result}@${aws_db_instance.core.address}:5432/ai_db"
    AI_DB_MIGRATION_URL = "postgresql://ai_migration:${random_password.db_role["ai_migration"].result}@${aws_db_instance.core.address}:5432/ai_db"
    # --- 스토리지·인증 ---
    ACCESS_REDIS_PASSWORD   = random_password.redis["access"].result
    DOCUMENT_REDIS_PASSWORD = random_password.redis["document"].result
    PIPELINE_REDIS_PASSWORD = random_password.redis["pipeline"].result
    JWT_SECRET              = random_password.jwt_secret.result
    MFA_ENCRYPTION_KEY      = random_id.mfa_encryption_key.b64_std
    SPRING_MAIL_HOST        = var.smtp_host
    SPRING_MAIL_USERNAME    = var.smtp_username
    SPRING_MAIL_PASSWORD    = var.smtp_password
    MAIL_FROM               = var.mail_from
    INTERNAL_CALLBACK_TOKEN = random_password.internal_callback_token.result
    AGENT_INTERNAL_TOKEN    = random_password.agent_internal_token.result
    OPENAI_API_KEY          = ""
    GEMINI_API_KEY          = ""
    ANTHROPIC_API_KEY       = ""
    LANGSMITH_API_KEY       = ""
    TAVILY_API_KEY          = ""
  })

  lifecycle {
    ignore_changes = [secret_string]
  }
}
