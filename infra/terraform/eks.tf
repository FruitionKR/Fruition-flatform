# §8.1: General node 2/2/3 On-Demand + AI Worker 0/0/2 Spot.
# Kafka(Strimzi)·API는 General node, ingest·converter는 AI Worker node(taint로 분리).
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "20.37.2"

  cluster_name                           = "${var.project}-eks"
  cluster_version                        = var.eks_version
  cloudwatch_log_group_retention_in_days = 14

  vpc_id     = module.vpc.vpc_id
  subnet_ids = module.vpc.private_subnets

  cluster_endpoint_private_access      = true
  cluster_endpoint_public_access       = length(var.eks_public_access_cidrs) > 0
  cluster_endpoint_public_access_cidrs = var.eks_public_access_cidrs
  # eks_admin_role_arn 지정 시 apply 주체의 암묵적 cluster-admin을 제거하고
  # 명시적 break-glass role로 대체한다.
  enable_cluster_creator_admin_permissions = var.eks_admin_role_arn == null

  cluster_security_group_additional_rules = {
    deployment_runner = {
      description              = "Private API from deployment runner only"
      type                     = "ingress"
      protocol                 = "tcp"
      from_port                = 443
      to_port                  = 443
      source_security_group_id = aws_security_group.runner.id
    }
  }

  # 애드온은 아래에서 직접 관리: 모듈의 전체 resource 출력에서 deprecated 속성 참조 방지.

  eks_managed_node_group_defaults = {
    ami_type = "AL2023_x86_64_STANDARD"
  }

  eks_managed_node_groups = {
    general = {
      credit_specification = { cpu_credits = "standard" }
      instance_types       = ["t3.large"] # 2 vCPU / 8GiB
      capacity_type        = "ON_DEMAND"
      min_size             = 2
      desired_size         = 2
      max_size             = 4 # 플랫폼 DaemonSet·Kafka·API 2 replicas와 rollout 여유
    }
    ai_worker = {
      instance_types = ["m5.xlarge", "m6i.xlarge"] # 4 vCPU / 16GiB
      capacity_type  = "SPOT"
      min_size       = 0
      desired_size   = 0
      max_size       = 2
      labels = {
        "fruition.io/node-role" = "ai-worker"
      }
      taints = {
        ai_worker = {
          key    = "fruition.io/ai-worker"
          value  = "true"
          effect = "NO_SCHEDULE"
        }
      }
    }
  }

  # 실제 권한은 플랫폼 관리자가 설치하는 fruition namespace RoleBinding으로 제한한다.
  access_entries = merge(
    {
      github_deploy = {
        principal_arn     = aws_iam_role.github_deploy.arn
        kubernetes_groups = ["fruition:deployers"]
      }
    },
    var.eks_admin_role_arn == null ? {} : {
      break_glass_admin = {
        principal_arn = var.eks_admin_role_arn
        policy_associations = {
          admin = {
            policy_arn   = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
            access_scope = { type = "cluster" }
          }
        }
      }
    }
  )
}

# 기존 모듈과 같은 버전·설정·충돌 처리·노드 생성 후 설치 순서를 유지한다.
locals {
  eks_addons = {
    coredns    = { addon_version = var.eks_addon_versions["coredns"] }
    kube-proxy = { addon_version = var.eks_addon_versions["kube-proxy"] }
    vpc-cni    = { addon_version = var.eks_addon_versions["vpc-cni"], configuration_values = jsonencode({ enableNetworkPolicy = "true" }) }
    # Strimzi Kafka PVC용 EBS gp3
    aws-ebs-csi-driver = {
      addon_version            = var.eks_addon_versions["aws-ebs-csi-driver"]
      service_account_role_arn = module.ebs_csi_irsa.iam_role_arn
    }
  }
}

resource "aws_eks_addon" "core" {
  for_each = local.eks_addons

  cluster_name                = module.eks.cluster_name
  addon_name                  = each.key
  addon_version               = each.value.addon_version
  configuration_values        = try(each.value.configuration_values, null)
  service_account_role_arn    = try(each.value.service_account_role_arn, null)
  preserve                    = true
  resolve_conflicts_on_create = "OVERWRITE"
  resolve_conflicts_on_update = "OVERWRITE"

  timeouts {}

  depends_on = [module.eks.eks_managed_node_groups]
}

# 기존 환경도 destroy/create 없이 동일 애드온의 Terraform 주소만 이동한다.
moved {
  from = module.eks.aws_eks_addon.this["coredns"]
  to   = aws_eks_addon.core["coredns"]
}

moved {
  from = module.eks.aws_eks_addon.this["kube-proxy"]
  to   = aws_eks_addon.core["kube-proxy"]
}

moved {
  from = module.eks.aws_eks_addon.this["vpc-cni"]
  to   = aws_eks_addon.core["vpc-cni"]
}

moved {
  from = module.eks.aws_eks_addon.this["aws-ebs-csi-driver"]
  to   = aws_eks_addon.core["aws-ebs-csi-driver"]
}

# --- IRSA roles (helm addon들이 사용하는 최소 권한) ---

module "ebs_csi_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"

  role_name             = "${var.project}-ebs-csi"
  attach_ebs_csi_policy = true

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:ebs-csi-controller-sa"]
    }
  }
}

module "alb_controller_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"

  role_name                              = "${var.project}-alb-controller"
  attach_load_balancer_controller_policy = false

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:aws-load-balancer-controller"]
    }
  }
}

module "external_secrets_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"

  role_name                             = "${var.project}-external-secrets"
  attach_external_secrets_policy        = true
  external_secrets_secrets_manager_arns = [aws_secretsmanager_secret.app.arn]
  external_secrets_kms_key_arns         = [aws_kms_key.secrets.arn]

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["external-secrets:external-secrets"]
    }
  }
}

module "cluster_autoscaler_irsa" {
  source  = "terraform-aws-modules/iam/aws//modules/iam-role-for-service-accounts-eks"
  version = "5.60.0"

  role_name                        = "${var.project}-cluster-autoscaler"
  attach_cluster_autoscaler_policy = false

  oidc_providers = {
    main = {
      provider_arn               = module.eks.oidc_provider_arn
      namespace_service_accounts = ["kube-system:cluster-autoscaler"]
    }
  }
}


// EKS v20은 ASG 태그 입력이 없다. 생성된 ASG에 별도 태그를 부여한다.
// for_each 키는 plan 시점에 고정되며 실제 ASG 이름만 apply 뒤 결정된다.
locals {
  autoscaler_tags = merge(
    { for group in ["general", "ai_worker"] : group => {
      "k8s.io/cluster-autoscaler/enabled"      = "true"
      "k8s.io/cluster-autoscaler/fruition-eks" = "owned"
    } },
    { ai_worker = {
      "k8s.io/cluster-autoscaler/enabled"                                   = "true"
      "k8s.io/cluster-autoscaler/fruition-eks"                              = "owned"
      "k8s.io/cluster-autoscaler/node-template/label/fruition.io/node-role" = "ai-worker"
      "k8s.io/cluster-autoscaler/node-template/taint/fruition.io/ai-worker" = "true:NoSchedule"
    } }
  )
  autoscaler_tag_entries = merge([for group, tags in local.autoscaler_tags : {
    for key, value in tags : "${group}/${key}" => { group = group, key = key, value = value }
  }]...)
}

resource "aws_autoscaling_group_tag" "discovery" {
  for_each               = local.autoscaler_tag_entries
  autoscaling_group_name = module.eks.eks_managed_node_groups[each.value.group].node_group_autoscaling_group_names[0]
  tag {
    key                 = each.value.key
    value               = each.value.value
    propagate_at_launch = false
  }
}


# 모듈 기본 정책의 다른 tag 계약 대신 실제 discovery tag 두 개로 쓰기를 제한한다.
resource "aws_iam_role_policy" "cluster_autoscaler" {
  name = "tag-scoped-autoscaling"
  role = module.cluster_autoscaler_irsa.iam_role_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["autoscaling:DescribeAutoScalingGroups", "autoscaling:DescribeAutoScalingInstances", "autoscaling:DescribeLaunchConfigurations", "autoscaling:DescribeScalingActivities", "autoscaling:DescribeTags", "ec2:DescribeLaunchTemplateVersions", "ec2:DescribeInstanceTypes", "ec2:DescribeImages", "ec2:GetInstanceTypesFromInstanceRequirements", "eks:DescribeNodegroup"]
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["autoscaling:SetDesiredCapacity", "autoscaling:TerminateInstanceInAutoScalingGroup"]
        Resource = "*"
        Condition = { StringEquals = {
          "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/enabled"      = "true"
          "autoscaling:ResourceTag/k8s.io/cluster-autoscaler/fruition-eks" = "owned"
        } }
      }
    ]
  })
}


# Controller와 같은 release의 공식 IAM policy를 사용한다.
resource "aws_iam_role_policy" "alb_controller" {
  name   = "controller-v3-5-0"
  role   = module.alb_controller_irsa.iam_role_name
  policy = file("${path.module}/policies/aws-load-balancer-controller-v3.5.0.json")
}
