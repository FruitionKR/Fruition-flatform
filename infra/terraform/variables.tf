variable "project" {
  description = "리소스 이름 접두사"
  type        = string
  default     = "fruition"
  validation {
    condition     = var.project == "fruition"
    error_message = "현재 feedback 배포 profile은 project=fruition만 지원합니다."
  }
}

variable "region" {
  description = "AWS region"
  type        = string
  default     = "ap-northeast-2"
  validation {
    condition     = var.region == "ap-northeast-2"
    error_message = "현재 feedback 배포 profile은 서울 region만 지원합니다."
  }
}

variable "vpc_cidr" {
  description = "VPC CIDR"
  type        = string
  default     = "10.0.0.0/16"
}

variable "eks_version" {
  description = "EKS Kubernetes 버전"
  type        = string
  default     = "1.35"
  validation {
    condition     = var.eks_version == "1.35"
    error_message = "검토된 addon profile은 EKS 1.35입니다. 버전 변경은 addon 계약과 함께 검토하세요."
  }
}

variable "github_repo" {
  description = "GitHub Actions OIDC를 허용할 repo (owner/name)"
  type        = string
  default     = "FruitionKR/Fruition-flatform"
}

variable "github_deploy_environment" {
  description = "GitHub Actions 배포 Environment (workflow와 동일해야 함; 승인자·branch 제한은 GitHub 설정)"
  type        = string
  default     = "feedback"
  validation {
    condition     = var.github_deploy_environment == "feedback"
    error_message = "현재 workflow는 feedback Environment를 사용합니다."
  }
}

variable "eks_public_access_cidrs" {
  description = "관리자 임시 public API IPv4 CIDR. 기본 []는 private-only; 로컬 초기 설치 때 현재 공인 IP /32만 잠시 허용"
  type        = list(string)
  default     = []
  validation {
    condition     = alltrue([for cidr in var.eks_public_access_cidrs : can(cidrnetmask(cidr)) && try(tonumber(split("/", cidr)[1]) == 32, false)])
    error_message = "빈 목록(private-only) 또는 관리자 IPv4 /32만 허용합니다."
  }
}

variable "runner_ami_id" {
  description = "서울 Canonical Ubuntu 24.04 amd64 AMI ID. 실제 조회한 이미지를 입력해 고정"
  type        = string
  validation {
    condition     = can(regex("^ami-[0-9a-f]{17}$", var.runner_ami_id))
    error_message = "서울 리전에서 확인한 Ubuntu 24.04 amd64 AMI ID가 필요합니다."
  }
}

variable "eks_addon_versions" {
  description = "서울 EKS 1.35 describe-addon-versions로 확인한 정확한 addon build (기본값 없음)"
  type        = map(string)
  validation {
    condition = toset(keys(var.eks_addon_versions)) == toset(["vpc-cni", "coredns", "kube-proxy", "aws-ebs-csi-driver"]) && alltrue([
      for version in values(var.eks_addon_versions) : can(regex("^v[0-9]+\\.[0-9]+\\.[0-9]+-eksbuild\\.[0-9]+$", version))
    ])
    error_message = "네 managed addon의 검증된 정확한 vX.Y.Z-eksbuild.N을 모두 제공해야 합니다."
  }
}

variable "eks_admin_role_arn" {
  description = "클러스터 관리자(break-glass) IAM role ARN. 지정하면 apply 실행 주체의 암묵적 cluster-admin(creator admin)을 끈다"
  type        = string
  default     = null
  validation {
    condition     = var.eks_admin_role_arn == null || can(regex("^arn:aws:iam::[0-9]{12}:role/", var.eks_admin_role_arn))
    error_message = "IAM role ARN 형식(arn:aws:iam::<account>:role/...)이어야 합니다."
  }
}

variable "smtp_host" {
  description = "인증 및 STARTTLS를 지원하는 SMTP host"
  type        = string
  validation {
    condition     = length(trimspace(var.smtp_host)) > 0 && !strcontains(var.smtp_host, "REPLACE_ME")
    error_message = "smtp_host은 비어 있거나 placeholder일 수 없습니다."
  }
}

variable "smtp_username" {
  description = "SMTP 인증 사용자"
  type        = string
  sensitive   = true
  validation {
    condition     = length(trimspace(var.smtp_username)) > 0 && !strcontains(var.smtp_username, "REPLACE_ME")
    error_message = "smtp_username은 비어 있거나 placeholder일 수 없습니다."
  }
}

variable "smtp_password" {
  description = "SMTP 인증 비밀번호"
  type        = string
  sensitive   = true
  validation {
    condition     = length(trimspace(var.smtp_password)) > 0 && !strcontains(var.smtp_password, "REPLACE_ME")
    error_message = "smtp_password은 비어 있거나 placeholder일 수 없습니다."
  }
}

variable "mail_from" {
  description = "인증·초대 메일 발신 주소"
  type        = string
  validation {
    condition     = length(trimspace(var.mail_from)) > 0 && !strcontains(var.mail_from, "REPLACE_ME")
    error_message = "mail_from은 비어 있거나 placeholder일 수 없습니다."
  }
}

variable "smtp_port" {
  description = "STARTTLS SMTP port"
  type        = number
  default     = 587
  validation {
    condition     = var.smtp_port >= 1 && var.smtp_port <= 65535 && floor(var.smtp_port) == var.smtp_port
    error_message = "SMTP port는 1~65535 정수여야 합니다."
  }
}

variable "document_upload_allowed_origins" {
  description = "PDF 직접 업로드를 허용하는 프런트엔드 HTTPS origin 목록. 와일드카드는 허용하지 않는다."
  type        = list(string)
  default     = []
  validation {
    condition = alltrue([
      for origin in var.document_upload_allowed_origins : can(regex("^https://[a-zA-Z0-9.-]+(:[0-9]+)?$", origin))
    ])
    error_message = "직접 업로드에는 구체적인 HTTPS origin을 지정해야 합니다."
  }
}
