# §8.5 + 물리 DB 분할: Access RDS / Core RDS 2 instance.
# k8s/base/postgres.yaml(pod)을 대체한다.
# - access-postgres: access_db (users·oauth·workspaces·members)
# - core-postgres:   core_db (문서·채팅) + 물리적으로 분리된 ai_db
# 앱 계정(runtime/migration)은 provisioning 후 infra/postgres/init-db-isolation.sh를
# 각 endpoint에 psql로 실행해 생성한다 (README 절차 참조).
resource "random_password" "db_role" {
  for_each = toset([
    "access_runtime", "access_migration",
    "core_runtime", "core_migration",
    "ai_runtime", "ai_migration",
  ])
  length  = 32
  special = false
}

resource "aws_db_subnet_group" "main" {
  name       = "${var.project}-db"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name   = "${var.project}-rds"
  vpc_id = module.vpc.vpc_id

  ingress {
    description     = "EKS nodes to PostgreSQL"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  # RDS는 outbound 연결을 시작하지 않는다 — egress 불필요 (탈취 경로 차단).
}

# TLS 강제: 평문 5432 접속과 VPC 내 credential 스니핑을 차단한다.
resource "aws_db_parameter_group" "postgres16" {
  name   = "${var.project}-postgres16"
  family = "postgres16"

  parameter {
    name         = "rds.force_ssl"
    value        = "1"
    apply_method = "pending-reboot"
  }
}

resource "aws_db_instance" "access" {
  identifier     = "${var.project}-access-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.small"

  allocated_storage = 30
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "postgres"
  username = "fruition_admin"
  # 마스터 비밀번호는 RDS 관리 Secrets Manager secret으로 관리 — Terraform state에 남지 않는다.
  manage_master_user_password = true

  parameter_group_name   = aws_db_parameter_group.postgres16.name
  ca_cert_identifier     = "rds-ca-rsa2048-g1"
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = false
  publicly_accessible    = false

  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-access-postgres-final"

  enabled_cloudwatch_logs_exports = ["postgresql"]
  performance_insights_enabled    = false
}

resource "aws_db_instance" "core" {
  identifier     = "${var.project}-core-postgres"
  engine         = "postgres"
  engine_version = "16"
  instance_class = "db.t4g.small"

  allocated_storage = 30
  storage_type      = "gp3"
  storage_encrypted = true

  db_name  = "postgres"
  username = "fruition_admin"
  # 마스터 비밀번호는 RDS 관리 Secrets Manager secret으로 관리 — Terraform state에 남지 않는다.
  manage_master_user_password = true

  parameter_group_name   = aws_db_parameter_group.postgres16.name
  ca_cert_identifier     = "rds-ca-rsa2048-g1"
  db_subnet_group_name   = aws_db_subnet_group.main.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  multi_az               = false
  publicly_accessible    = false

  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-core-postgres-final"

  enabled_cloudwatch_logs_exports = ["postgresql"]
  performance_insights_enabled    = false
}
