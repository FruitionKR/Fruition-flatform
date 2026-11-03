# §8.5 + 물리 DB 분할: Access RDS / Core RDS 2 instance.
# k8s/base/postgres.yaml(pod)을 대체한다.
# - access-postgres: access_db (users·oauth·workspaces·members)
# - core-postgres:   core_db (문서·채팅) + 물리적으로 분리된 ai_db
# 앱 계정(runtime/migration, AI converter)은 provisioning 후 infra/postgres/init-db-isolation.sh를
# 각 endpoint에 psql로 실행해 생성한다 (README 절차 참조).
resource "random_password" "db_role" {
  for_each = toset([
    "access_runtime", "access_migration",
    "core_runtime", "core_migration",
    "ai_runtime", "ai_migration", "ai_converter",
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

# RDS가 내보내는 로그의 그룹을 먼저 만들어 14일 보관 기간을 건다(없으면 RDS가 만료 없는 그룹을 자동 생성한다).
# 기존 그룹은 rds_log_groups_to_import에 지정해 plan에서 import를 검토한다.
variable "rds_log_groups_to_import" {
  description = "이미 존재하는 RDS 로그 그룹만 지정한다. 신규 설치는 빈 집합으로 생성한다."
  type        = set(string)
  default     = []
  validation {
    condition     = alltrue([for name in var.rds_log_groups_to_import : contains(["access", "core"], name)])
    error_message = "RDS 로그 그룹은 access 또는 core만 지정할 수 있습니다."
  }
}

import {
  for_each = var.rds_log_groups_to_import
  to       = aws_cloudwatch_log_group.rds[each.key]
  id       = "/aws/rds/instance/${var.project}-${each.key}-postgres/postgresql"
}

resource "aws_cloudwatch_log_group" "rds" {
  for_each          = toset(["access", "core"])
  name              = "/aws/rds/instance/${var.project}-${each.key}-postgres/postgresql"
  retention_in_days = 14
}

variable "access_db_apply_immediately" {
  description = "access DB 변경을 유지 관리 기간을 기다리지 않고 바로 적용할지 정한다. 재시작이 따르는 변경이면 Single-AZ라 몇 분 접속이 끊긴다."
  type        = bool
  default     = false
}

resource "aws_db_instance" "access" {
  identifier     = "${var.project}-access-postgres"
  engine         = "postgres"
  engine_version = "16"
  # 30일 FreeableMemory 최소 0.98GB·연결 최대 30으로 small 메모리의 절반 이상이 남아 micro로 줄인다.
  instance_class = "db.t4g.micro"
  # 기본은 다음 유지 관리 기간에 적용한다. 크기 변경처럼 바로 반영할 때만 -var로 켠다.
  apply_immediately = var.access_db_apply_immediately

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
  # 비용 절감을 위해 core DB와 같이 Single-AZ로 운영한다. 백업 7일·암호화·삭제 보호는 유지한다.
  # Multi-AZ 해제는 중단 없이 다음 유지 관리 기간에 적용된다(ModifyDBInstance MultiAZ).
  multi_az            = false
  publicly_accessible = false

  backup_retention_period   = 7
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "${var.project}-access-postgres-final"

  depends_on                      = [aws_cloudwatch_log_group.rds["access"]]
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

  depends_on                      = [aws_cloudwatch_log_group.rds["core"]]
  enabled_cloudwatch_logs_exports = ["postgresql"]
  performance_insights_enabled    = false
}
