# Deployment-only host. Service image builds and PR tests stay on hosted runners.
data "aws_ami" "runner" {
  owners = ["099720109477"] # Canonical
  filter {
    name   = "image-id"
    values = [var.runner_ami_id]
  }
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }
  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
  filter {
    name   = "state"
    values = ["available"]
  }
}

resource "aws_security_group" "runner" {
  name        = "${var.project}-feedback-runner"
  description = "No inbound connections; SSM and GitHub use outbound connections"
  vpc_id      = module.vpc.vpc_id
  # Package repositories, GitHub, AWS APIs and private EKS endpoint.
  # DNS(VPC resolver)는 SG 규칙 대상이 아니므로 별도 허용이 필요 없다.
  egress {
    description = "HTTPS: GitHub, AWS APIs, EKS private endpoint, apt TLS mirrors"
    protocol    = "tcp"
    from_port   = 443
    to_port     = 443
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "HTTP: apt package mirrors"
    protocol    = "tcp"
    from_port   = 80
    to_port     = 80
    cidr_blocks = ["0.0.0.0/0"]
  }
  egress {
    description = "Amazon Time Sync"
    protocol    = "udp"
    from_port   = 123
    to_port     = 123
    cidr_blocks = ["169.254.169.123/32"]
  }
}

resource "aws_iam_role" "runner_host" {
  name = "${var.project}-feedback-runner-host"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

# Host credentials provide management connectivity only. No EKS access entry,
# application secrets, image push or Terraform privileges are assigned here.
resource "aws_iam_role_policy_attachment" "runner_ssm" {
  role       = aws_iam_role.runner_host.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "runner" {
  name = "${var.project}-feedback-runner"
  role = aws_iam_role.runner_host.name
}

resource "aws_instance" "runner" {
  ami                         = data.aws_ami.runner.id
  instance_type               = "t3.small"
  subnet_id                   = module.vpc.private_subnets[0]
  vpc_security_group_ids      = [aws_security_group.runner.id]
  associate_public_ip_address = false
  iam_instance_profile        = aws_iam_instance_profile.runner.name
  user_data_replace_on_change = true

  credit_specification {
    cpu_credits = "standard"
  }

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }
  root_block_device {
    volume_size           = 30
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true
  }

  # No GitHub registration token or AWS access key is passed through user data/state.
  user_data = "#cloud-config\n${yamlencode({
    write_files = [
      {
        path        = "/etc/fruition-runner.json"
        owner       = "root:root"
        permissions = "0644"
        content     = jsonencode({ github_repo = var.github_repo })
      },
      {
        path        = "/usr/local/sbin/fruition-runner-bootstrap"
        owner       = "root:root"
        permissions = "0700"
        content     = file("${path.module}/../runner/bootstrap.sh")
      },
      {
        path        = "/usr/local/sbin/fruition-runner-register"
        owner       = "root:root"
        permissions = "0700"
        content     = file("${path.module}/../runner/register.sh")
      }
    ]
    runcmd = [["/usr/local/sbin/fruition-runner-bootstrap"]]
  })}"

  tags = { Name = "${var.project}-feedback-runner", Purpose = "github-deploy-only" }
  # Ensure the private subnet's NAT route and SSM permissions exist at first boot.
  depends_on = [module.vpc, aws_iam_role_policy_attachment.runner_ssm]
}
