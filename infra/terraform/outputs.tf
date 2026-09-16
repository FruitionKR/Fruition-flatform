output "cluster_name" {
  value = module.eks.cluster_name
}

output "cluster_arn" {
  value = module.eks.cluster_arn
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}

output "ecr_repository_urls" {
  value = { for k, r in aws_ecr_repository.services : k => r.repository_url }
}

output "access_rds_endpoint" {
  description = "access-svc deployment env POSTGRES_HOST에 넣을 값"
  value       = aws_db_instance.access.address
}

output "core_rds_endpoint" {
  description = "document-svc deployment·pipeline env POSTGRES_HOST에 넣을 값"
  value       = aws_db_instance.core.address
}

output "redis_endpoint" {
  description = "k8s/overlays/aws configmap의 REDIS_HOST에 넣을 값"
  value       = aws_elasticache_replication_group.main.primary_endpoint_address
}

output "s3_bucket" {
  description = "k8s/overlays/aws configmap의 S3_BUCKET에 넣을 값"
  value       = aws_s3_bucket.storage.bucket
}

output "app_secret_arn" {
  value = aws_secretsmanager_secret.app.arn
}

output "github_deploy_role_arn" {
  description = "GitHub repo variable AWS_DEPLOY_ROLE_ARN에 넣을 값"
  value       = aws_iam_role.github_deploy.arn
}

output "irsa_role_arns" {
  description = "helm addon 설치 시 serviceAccount annotation에 넣을 role ARN"
  value = {
    alb_controller     = module.alb_controller_irsa.iam_role_arn
    external_secrets   = module.external_secrets_irsa.iam_role_arn
    cluster_autoscaler = module.cluster_autoscaler_irsa.iam_role_arn
  }
}

output "storage_role_arns" {
  value = { for service, role in module.storage_irsa : service => role.iam_role_arn }
}
output "network_deploy_inputs" {
  value = {
    vpc_cidr          = module.vpc.vpc_cidr_block
    alb_subnet_cidr_1 = module.vpc.public_subnets_cidr_blocks[0]
    alb_subnet_cidr_2 = module.vpc.public_subnets_cidr_blocks[1]
    smtp_port         = tostring(var.smtp_port)
  }
}
