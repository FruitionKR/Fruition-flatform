# §8.5: Redis single node cache.t4g.micro. 실시간 상태 전용(권한 projection·SSE relay·TTL 캐시).
# k8s/base/redis.yaml(pod)을 대체한다.
resource "aws_elasticache_subnet_group" "main" {
  name       = "${var.project}-redis"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "redis" {
  name   = "${var.project}-redis"
  vpc_id = module.vpc.vpc_id

  ingress {
    description     = "EKS node -> Redis"
    from_port       = 6379
    to_port         = 6379
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

# Redis 7 selectors로 Access projection은 삭제만 허용한다.
locals {
  redis_acl = {
    access   = "on -@all resetkeys resetchannels +ping +hello +client|setname (+eval +evalsha +incr +expire +ttl ~auth:mfa:attempts:* ~auth:email-availability:*) (+set +getdel ~oauth:exchange:*) (+scan +del ~authz:role:*)"
    document = "on -@all resetkeys resetchannels +ping +hello +client|setname (+get +set ~authz:role:*) (+get +set +incr +expire +pexpire +del +exists +lrange +rpush +ltrim +eval +evalsha +publish +subscribe +unsubscribe ~query:* &query-events)"
    pipeline = "on -@all resetkeys resetchannels +ping +hello +client|setname +get +setex +del ~wiki:concept-index:*"
  }
}

resource "random_password" "redis" {
  for_each = local.redis_acl
  length   = 48
  special  = false
}

resource "aws_elasticache_user" "service" {
  for_each      = local.redis_acl
  user_id       = "${var.project}-${each.key}"
  user_name     = each.key
  engine        = "REDIS"
  access_string = each.value
  passwords     = [random_password.redis[each.key].result]
}

resource "aws_elasticache_user" "disabled_default" {
  user_id       = "${var.project}-default-disabled"
  user_name     = "default"
  engine        = "REDIS"
  access_string = "off -@all"
  authentication_mode { type = "no-password-required" }
}

resource "aws_elasticache_user_group" "services" {
  engine        = "REDIS"
  user_group_id = "${var.project}-services"
  user_ids      = concat([aws_elasticache_user.disabled_default.user_id], [for u in aws_elasticache_user.service : u.user_id])
}

resource "aws_elasticache_replication_group" "main" {
  replication_group_id       = "${var.project}-redis"
  description                = "서비스별 ACL을 사용하는 feedback Redis"
  engine                     = "redis"
  engine_version             = "7.1"
  node_type                  = "cache.t4g.micro"
  num_cache_clusters         = 1
  port                       = 6379
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  transit_encryption_mode    = "required"
  user_group_ids             = [aws_elasticache_user_group.services.user_group_id]
  subnet_group_name          = aws_elasticache_subnet_group.main.name
  security_group_ids         = [aws_security_group.redis.id]
}
