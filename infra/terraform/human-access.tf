# Human administration is a temporary, MFA-authenticated role. GitHub OIDC and
# application IRSA identities remain independent of a person's long-lived key.
variable "human_operator_user_name" {
  type        = string
  description = "Existing IAM user to migrate to MFA-only role access; empty leaves human access unmanaged."
  default     = ""
  validation {
    condition     = var.human_operator_user_name == "" || can(regex("^[A-Za-z0-9+=,.@_-]+$", var.human_operator_user_name))
    error_message = "Provide an IAM user name without a path."
  }
}

variable "enforce_human_mfa_only" {
  type        = bool
  default     = false
  description = "Enable only after the owner enrolled MFA and verified a separate role session."
}

locals {
  human_operator_arn = "arn:aws:iam::${data.aws_caller_identity.budget.account_id}:user/${var.human_operator_user_name}"
}

resource "aws_iam_role" "human_admin" {
  count                = var.human_operator_user_name == "" ? 0 : 1
  name                 = "${var.project}-human-admin"
  max_session_duration = 3600
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { AWS = local.human_operator_arn }
      Action    = "sts:AssumeRole"
      Condition = { Bool = { "aws:MultiFactorAuthPresent" = "true" } }
    }]
  })
}

resource "aws_iam_role_policy_attachment" "human_admin" {
  count      = var.human_operator_user_name == "" ? 0 : 1
  role       = aws_iam_role.human_admin[0].name
  policy_arn = "arn:aws:iam::aws:policy/AdministratorAccess"
}

resource "aws_eks_access_entry" "human_admin" {
  count         = var.human_operator_user_name == "" ? 0 : 1
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.human_admin[0].arn
  type          = "STANDARD"
}

resource "aws_eks_access_policy_association" "human_admin" {
  count         = var.human_operator_user_name == "" ? 0 : 1
  cluster_name  = module.eks.cluster_name
  principal_arn = aws_iam_role.human_admin[0].arn
  policy_arn    = "arn:aws:eks::aws:cluster-access-policy/AmazonEKSClusterAdminPolicy"
  access_scope { type = "cluster" }
  depends_on = [aws_eks_access_entry.human_admin]
}

resource "aws_iam_user_policy" "human_mfa_only" {
  count = var.enforce_human_mfa_only && var.human_operator_user_name != "" ? 1 : 0
  name  = "${var.project}-mfa-only-role-access"
  user  = var.human_operator_user_name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "AssumeMfaRole"
        Effect   = "Allow"
        Action   = "sts:AssumeRole"
        Resource = aws_iam_role.human_admin[0].arn
      },
      {
        Sid         = "DenyOtherRoleAssumption"
        Effect      = "Deny"
        Action      = "sts:AssumeRole"
        NotResource = aws_iam_role.human_admin[0].arn
      },
      {
        Sid      = "ViewOwnMfa"
        Effect   = "Allow"
        Action   = ["iam:GetUser", "iam:ListMFADevices", "iam:ResyncMFADevice"]
        Resource = local.human_operator_arn
      },
      {
        Sid      = "ChangeOwnConsolePassword"
        Effect   = "Allow"
        Action   = "iam:ChangePassword"
        Resource = local.human_operator_arn
      },
      {
        Sid         = "DenyOtherUserPasswordChange"
        Effect      = "Deny"
        Action      = "iam:ChangePassword"
        NotResource = local.human_operator_arn
      },
      {
        Sid      = "ReadPasswordRequirements"
        Effect   = "Allow"
        Action   = "iam:GetAccountPasswordPolicy"
        Resource = "*"
      },
      {
        Sid    = "DenyDirectServiceAccess"
        Effect = "Deny"
        NotAction = ["sts:AssumeRole", "sts:GetSessionToken", "sts:GetCallerIdentity",
          "iam:GetUser", "iam:ListMFADevices", "iam:ResyncMFADevice",
        "iam:ChangePassword", "iam:GetAccountPasswordPolicy"]
        Resource = "*"
      }
    ]
  })
}

output "human_admin_role_arn" {
  value = try(aws_iam_role.human_admin[0].arn, null)
}
