# 우리 서비스를 만들 준비물 185개

작은 가게를 만든다고 생각해 보세요. 가게만 있으면 끝일까요? 문, 열쇠, 보관함, 안내판도 필요합니다. 우리 서비스도 비슷합니다.

**185개는 컴퓨터 185대가 아닙니다.** 컴퓨터를 만드는 설정뿐 아니라, 출입 허가증과 알림 연결도 하나씩 센 숫자입니다.

이 목록은 2026-09-16의 `feedback-observability.tfplan`을 보고 만들었습니다. 새로 만들 항목 185개이고, 바꾸거나 지울 항목은 0개입니다. **이미 모두 만들어졌다는 뜻은 아닙니다.** 비밀번호와 API 키의 실제 값은 이 글에 적지 않았습니다.

이후 보안·유지보수 설정과 배포 실패 알림 IAM 정책이 추가됐습니다. 이 표는 당시 plan의 기록이며, 현재 생성 개수는 새 plan으로 확인해야 합니다. [현재 유지보수 설정](aws-maintenance.md)

## 어려운 이름은 이렇게 읽어요

| 이름 | 쉽게 떠올릴 모습 |
|---|---|
| VPC·subnet | 컴퓨터들이 있는 마을과 구역 |
| 서버·노드 | 일을 하는 컴퓨터 |
| EKS | 컴퓨터와 작은 일꾼을 관리하는 관리자 |
| Pod | 컴퓨터 안에서 프로그램을 실행하는 작은 일꾼 |
| IAM 역할·정책 | 누가 어떤 일을 할 수 있는지 적힌 출입증과 허가 규칙 |
| 보안 그룹 | 누가 어느 문으로 들어올 수 있는지 정한 규칙 |
| RDS·PostgreSQL | 중요한 내용을 차곡차곡 적는 기록장 |
| Redis | 빨리 보고 고치는 메모장 |
| S3 | 파일 보관함 |
| ECR 이미지 | 사진이 아니라, 설치할 프로그램을 담은 상자 |
| Secret | 비밀번호 같은 비밀. Secrets Manager에 잠가 보관해요 |
| runner | 새 프로그램을 설치하는 담당 컴퓨터 |
| CloudWatch | 컴퓨터의 일기와 바쁜 정도를 모아 보여주는 관찰 도구 |
| SNS·Lambda·SQS | 소식 전달 길·소식을 보내는 프로그램·못 보낸 소식 보관함 |
| WAF | 너무 많은 요청이 들어오면 막는 문지기 |

## 분야별 개수

| 분야 | 개수 |
|---|---:|
| 네트워크 | 20 |
| EKS 제어 영역·권한·통신 | 34 |
| EKS 노드·자동 확장 | 20 |
| Pod 전용 IAM 역할 | 16 |
| PostgreSQL | 4 |
| Redis | 8 |
| 파일·이미지 저장소 | 14 |
| 비밀정보 생성·보관 | 19 |
| 배포 runner·GitHub 인증 | 9 |
| CloudWatch 수집·대시보드·경보 | 23 |
| 예산·Discord 알림 전달 | 17 |
| 요청 비용 보호 | 1 |
| **합계** | **185** |

## 읽는 방법

먼저 **쉬운 설명**만 읽어도 됩니다. 긴 영어 이름은 운영자가 설정 파일에서 같은 항목을 찾을 때 쓰는 이름표입니다. 외우거나 바꿀 필요는 없습니다.

- 표 한 줄이 준비물 하나입니다. 1번부터 185번까지 있습니다.
- `module.`은 여러 설정을 묶어 놓은 상자 안에 있다는 뜻입니다. `[0]` 같은 숫자는 그 안의 번호입니다.
- `policy_attachment`는 허가 규칙을 출입증에 붙이는 일입니다. 컴퓨터를 새로 만드는 일이 아닙니다.
- `random_*`는 비밀값이나 이름표를 만드는 일입니다. `null_resource`는 검사, `time_sleep`은 잠깐 기다리기입니다. 이들도 컴퓨터는 아닙니다.
- 정보를 읽기만 하는 `data.*`와 결과를 보여주는 outputs는 185개에 넣지 않았습니다.

설정 숫자와 원래 이름은 마지막 두 칸에 남겼습니다. 돈 이야기는 [비용 안내](aws-deployment-costs.md), 알림을 켜는 순서는 [CloudWatch 안내](aws-observability.md)에 있습니다.

## 네트워크 — 20개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 1 | 파일 보관함까지 전용 길을 내서 NAT 길 사용료를 줄여요. | `aws_vpc_endpoint.s3` | S3 Gateway endpoint; private route의 S3 트래픽 NAT 우회 |
| 2 | 마을 입구의 기본 통행 규칙이에요. 세부 출입 검사는 다른 문에서 해요. | `module.vpc.aws_default_network_acl.this[0]` | VPC 기본 네트워크 ACL 관리; 현재 송수신 허용, 세부 통제는 보안 그룹 |
| 3 | 마을의 기본 길 안내판이에요. | `module.vpc.aws_default_route_table.default[0]` | VPC 기본 라우팅 테이블 관리 |
| 4 | 기본 출입문 규칙을 관리해요. | `module.vpc.aws_default_security_group.this[0]` | VPC 기본 보안 그룹 관리 |
| 5 | 밖으로 나가는 길에 고정 주소를 붙여요. | `module.vpc.aws_eip.nat[0]` | NAT Gateway용 공인 고정 IPv4 |
| 6 | 바깥 구역과 인터넷을 이어요. | `module.vpc.aws_internet_gateway.this[0]` | public subnet 인터넷 통신 연결 |
| 7 | 안쪽 컴퓨터가 인터넷으로 나갈 길을 만들어요. | `module.vpc.aws_nat_gateway.this[0]` | private subnet 외부 통신용 NAT 1개 |
| 8 | 안쪽에서 나갈 때 NAT 길을 쓰라고 알려줘요. | `module.vpc.aws_route.private_nat_gateway[0]` | private→NAT 기본 경로 |
| 9 | 바깥 구역에서 인터넷으로 갈 길을 알려줘요. | `module.vpc.aws_route.public_internet_gateway[0]` | public→Internet Gateway 기본 경로 |
| 10 | 안쪽 구역의 길 안내를 모아요. | `module.vpc.aws_route_table.private[0]` | private subnet 경로 집합 |
| 11 | 바깥 구역의 길 안내를 모아요. | `module.vpc.aws_route_table.public[0]` | public subnet 경로 집합 |
| 12 | 이 구역에 맞는 길 안내판을 연결해요. | `module.vpc.aws_route_table_association.private[0]` | 해당 subnet을 private 경로에 연결 |
| 13 | 이 구역에 맞는 길 안내판을 연결해요. | `module.vpc.aws_route_table_association.private[1]` | 해당 subnet을 private 경로에 연결 |
| 14 | 이 구역에 맞는 길 안내판을 연결해요. | `module.vpc.aws_route_table_association.public[0]` | 해당 subnet을 public 경로에 연결 |
| 15 | 이 구역에 맞는 길 안내판을 연결해요. | `module.vpc.aws_route_table_association.public[1]` | 해당 subnet을 public 경로에 연결 |
| 16 | 서버·DB가 일할 안쪽 구역을 만들어요. | `module.vpc.aws_subnet.private[0]` | private subnet: EKS·DB·Redis·runner 배치 |
| 17 | 서버·DB가 일할 안쪽 구역을 만들어요. | `module.vpc.aws_subnet.private[1]` | private subnet: EKS·DB·Redis·runner 배치 |
| 18 | 입구 안내원과 NAT 길을 둘 바깥 구역을 만들어요. | `module.vpc.aws_subnet.public[0]` | public subnet: ALB·NAT 배치 |
| 19 | 입구 안내원과 NAT 길을 둘 바깥 구역을 만들어요. | `module.vpc.aws_subnet.public[1]` | public subnet: ALB·NAT 배치 |
| 20 | 우리 컴퓨터들이 사용할 마을을 만들어요. | `module.vpc.aws_vpc.this[0]` | 10.0.0.0/16 전용 네트워크, DNS 활성화 |

## EKS 제어 영역·권한·통신 — 34개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 21 | 관리자가 한 일과 로그인 확인 기록을 14일 보관해요. | `module.eks.aws_cloudwatch_log_group.this[0]` | EKS API·audit·authenticator 로그, 14일 보존 |
| 22 | 처음 가게를 만든 관리자가 누구인지 등록해요. | `module.eks.aws_eks_access_entry.this["cluster_creator"]` | 클러스터 생성 관리자 identity 연결 |
| 23 | GitHub의 설치 담당자가 들어올 수 있게 등록해요. | `module.eks.aws_eks_access_entry.this["github_deploy"]` | GitHub 배포 역할을 fruition:deployers 그룹에 연결 |
| 24 | 처음 만든 관리자에게 관리할 권한을 줘요. | `module.eks.aws_eks_access_policy_association.this["cluster_creator_admin"]` | 클러스터 생성 관리자에게 EKS 관리 권한 연결 |
| 25 | 일꾼에게 필요한 저장 공간을 붙여 주는 도구예요. | `aws_eks_addon.core["aws-ebs-csi-driver"]` | EBS PVC provisioner |
| 26 | 이름을 보고 컴퓨터를 찾는 주소록이에요. | `aws_eks_addon.core["coredns"]` | 클러스터 DNS |
| 27 | 요청이 알맞은 프로그램으로 가게 도와줘요. | `aws_eks_addon.core["kube-proxy"]` | 서비스 네트워크 프록시 |
| 28 | 작은 일꾼들이 통신하는 길과 규칙을 다뤄요. | `aws_eks_addon.core["vpc-cni"]` | Pod VPC 네트워크와 NetworkPolicy |
| 29 | 컴퓨터와 일꾼을 관리할 EKS를 만들어요. | `module.eks.aws_eks_cluster.this[0]` | fruition-eks 1.35 제어 영역, private API 및 초기 관리자 /32 접근 |
| 30 | 일꾼의 신분을 확인해서 필요한 출입증을 받게 해요. | `module.eks.aws_iam_openid_connect_provider.oidc_provider[0]` | Pod IRSA 인증용 EKS OIDC provider |
| 31 | EKS가 자료를 잠글 열쇠를 쓰도록 허락해요. | `module.eks.aws_iam_policy.cluster_encryption[0]` | EKS KMS 암호화 키 사용 정책 |
| 32 | 묶음 도구가 기본으로 만든 이름표 조건 규칙이에요. Auto Mode를 켰다는 뜻은 아니에요. | `module.eks.aws_iam_policy.custom[0]` | 모듈 기본 Auto Mode custom-tag 조건 정책; Auto Mode 사용을 의미하지 않음 |
| 33 | EKS 관리자 프로그램의 출입증이에요. | `module.eks.aws_iam_role.this[0]` | EKS 제어 영역 실행 역할 |
| 34 | 잠금 열쇠 사용 규칙을 EKS 출입증에 붙여요. | `module.eks.aws_iam_role_policy_attachment.cluster_encryption[0]` | EKS 암호화 정책 연결 |
| 35 | 이름표 조건 규칙을 EKS 출입증에 붙여요. | `module.eks.aws_iam_role_policy_attachment.custom[0]` | 모듈 custom-tag 정책 연결 |
| 36 | EKS 기본 관리 규칙을 출입증에 붙여요. | `module.eks.aws_iam_role_policy_attachment.this["AmazonEKSClusterPolicy"]` | EKS 기본 클러스터 정책 연결 |
| 37 | EKS가 통신 장치를 다루는 규칙을 붙여요. | `module.eks.aws_iam_role_policy_attachment.this["AmazonEKSVPCResourceController"]` | EKS VPC 리소스 제어 정책 연결 |
| 38 | EKS 관리실에 누가 들어올지 정해요. | `module.eks.aws_security_group.cluster[0]` | EKS 제어 영역 보안 그룹 |
| 39 | 일하는 컴퓨터의 출입 규칙을 모아요. | `module.eks.aws_security_group.node[0]` | EKS 노드 공통 보안 그룹 |
| 40 | 설치 담당 컴퓨터가 EKS 관리실에 연락하게 해요. | `module.eks.aws_security_group_rule.cluster["deployment_runner"]` | runner→EKS API 443 |
| 41 | 일하는 컴퓨터가 EKS 관리실에 연락하게 해요. | `module.eks.aws_security_group_rule.cluster["ingress_nodes_443"]` | 노드→EKS API 443 |
| 42 | 일하는 컴퓨터가 밖으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["egress_all"]` | 노드 외부 송신 허용 |
| 43 | 관리실이 컴퓨터의 정해진 문(443)으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_443"]` | 제어 영역→노드 webhook 포트 443 |
| 44 | 관리실이 컴퓨터의 정해진 문(4443)으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_4443_webhook"]` | 제어 영역→노드 webhook 포트 4443 |
| 45 | 관리실이 컴퓨터의 정해진 문(6443)으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_6443_webhook"]` | 제어 영역→노드 webhook 포트 6443 |
| 46 | 관리실이 컴퓨터의 정해진 문(8443)으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_8443_webhook"]` | 제어 영역→노드 webhook 포트 8443 |
| 47 | 관리실이 컴퓨터의 정해진 문(9443)으로 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_9443_webhook"]` | 제어 영역→노드 webhook 포트 9443 |
| 48 | 관리실이 컴퓨터의 일꾼 담당자에게 연락하게 해요. | `module.eks.aws_security_group_rule.node["ingress_cluster_kubelet"]` | 제어 영역→kubelet |
| 49 | 컴퓨터끼리 임시로 쓰는 통신 문을 열어요. | `module.eks.aws_security_group_rule.node["ingress_nodes_ephemeral"]` | 노드 간 ephemeral 포트 |
| 50 | 컴퓨터끼리 주소를 묻는 길이에요. TCP 방식이에요. | `module.eks.aws_security_group_rule.node["ingress_self_coredns_tcp"]` | 노드 간 DNS TCP 53 |
| 51 | 컴퓨터끼리 주소를 묻는 길이에요. UDP 방식이에요. | `module.eks.aws_security_group_rule.node["ingress_self_coredns_udp"]` | 노드 간 DNS UDP 53 |
| 52 | EKS 준비가 끝날 때까지 잠깐 기다려요. | `module.eks.time_sleep.this[0]` | EKS 생성 후 후속 작업 대기; 별도 AWS 서버 아님 |
| 53 | 잠금 열쇠에 찾기 쉬운 이름을 붙여요. | `module.eks.module.kms.aws_kms_alias.this["cluster"]` | EKS 암호화 키의 알아보기 쉬운 별칭 |
| 54 | EKS의 자료를 잠글 열쇠를 만들고 주기적으로 새 재료로 바꿔요. | `module.eks.module.kms.aws_kms_key.this[0]` | EKS용 KMS 키, 자동 rotation 활성화 |

## EKS 노드·자동 확장 — 20개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 55 | AI 컴퓨터 묶음을 자동 확장 담당자가 찾게 표시해요. | `aws_autoscaling_group_tag.discovery["ai_worker/k8s.io/cluster-autoscaler/enabled"]` | AI node group Autoscaler 검색 활성화 태그 |
| 56 | AI 컴퓨터가 우리 서비스 소속임을 표시해요. | `aws_autoscaling_group_tag.discovery["ai_worker/k8s.io/cluster-autoscaler/fruition-eks"]` | AI node group 대상 클러스터 소유권 태그 |
| 57 | AI 컴퓨터가 0대여도 어떤 작업용인지 알 수 있게 해요. | `aws_autoscaling_group_tag.discovery["ai_worker/k8s.io/cluster-autoscaler/node-template/label/fruition.io/node-role"]` | AI node group scale-from-zero용 AI 노드 label 정보 |
| 58 | AI 컴퓨터에 들어갈 수 있는 일꾼 조건을 미리 알려줘요. | `aws_autoscaling_group_tag.discovery["ai_worker/k8s.io/cluster-autoscaler/node-template/taint/fruition.io/ai-worker"]` | AI node group scale-from-zero용 AI 노드 taint 정보 |
| 59 | 일반 컴퓨터 묶음을 자동 확장 담당자가 찾게 표시해요. | `aws_autoscaling_group_tag.discovery["general/k8s.io/cluster-autoscaler/enabled"]` | 일반 node group Autoscaler 검색 활성화 태그 |
| 60 | 일반 컴퓨터가 우리 서비스 소속임을 표시해요. | `aws_autoscaling_group_tag.discovery["general/k8s.io/cluster-autoscaler/fruition-eks"]` | 일반 node group 대상 클러스터 소유권 태그 |
| 61 | AI 컴퓨터 묶음이에요. 처음 0대, 많아도 2대예요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_eks_node_group.this[0]` | CPU Spot m5/m6i.xlarge, 초기 0·최대 2대 |
| 62 | AI 컴퓨터가 사용할 출입증이에요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_iam_role.this[0]` | AI 노드의 AWS 실행 역할 |
| 63 | 설치할 프로그램 상자를 가져올 수 있게 해요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_iam_role_policy_attachment.this["AmazonEC2ContainerRegistryReadOnly"]` | ECR 이미지 읽기 |
| 64 | 컴퓨터가 EKS에서 일할 기본 권한을 줘요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_iam_role_policy_attachment.this["AmazonEKSWorkerNodePolicy"]` | EKS worker 기본 API 권한 |
| 65 | 일꾼의 통신 길을 만들 권한을 줘요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_iam_role_policy_attachment.this["AmazonEKS_CNI_Policy"]` | VPC CNI 네트워크 권한 |
| 66 | 컴퓨터를 어떻게 켤지 적은 설명서예요. 안전한 신분 확인(IMDSv2)을 써요. | `module.eks.module.eks_managed_node_group["ai_worker"].aws_launch_template.this[0]` | AI 노드 EC2 실행 설정(IMDSv2) |
| 67 | 일반 컴퓨터 묶음이에요. 보통 2대, 많아도 3대예요. | `module.eks.module.eks_managed_node_group["general"].aws_eks_node_group.this[0]` | t3.large On-Demand, 최소/초기 2·최대 3대 |
| 68 | 일반 컴퓨터가 사용할 출입증이에요. | `module.eks.module.eks_managed_node_group["general"].aws_iam_role.this[0]` | 일반 노드의 AWS 실행 역할 |
| 69 | 설치할 프로그램 상자를 가져올 수 있게 해요. | `module.eks.module.eks_managed_node_group["general"].aws_iam_role_policy_attachment.this["AmazonEC2ContainerRegistryReadOnly"]` | ECR 이미지 읽기 |
| 70 | 컴퓨터가 EKS에서 일할 기본 권한을 줘요. | `module.eks.module.eks_managed_node_group["general"].aws_iam_role_policy_attachment.this["AmazonEKSWorkerNodePolicy"]` | EKS worker 기본 API 권한 |
| 71 | 일꾼의 통신 길을 만들 권한을 줘요. | `module.eks.module.eks_managed_node_group["general"].aws_iam_role_policy_attachment.this["AmazonEKS_CNI_Policy"]` | VPC CNI 네트워크 권한 |
| 72 | 컴퓨터를 어떻게 켤지 적은 설명서예요. 안전한 신분 확인(IMDSv2)을 써요. 추가 CPU 요금 대신 속도를 제한해요. | `module.eks.module.eks_managed_node_group["general"].aws_launch_template.this[0]` | 일반 노드 EC2 실행 설정(IMDSv2, Standard CPU credit) |
| 73 | 컴퓨터를 켜기 전에 내부 주소 설정을 검사해요. 새 서버는 만들지 않아요. | `module.eks.module.eks_managed_node_group["ai_worker"].module.user_data.null_resource.validate_cluster_service_cidr` | 부팅 설정의 cluster service CIDR 검증; AWS 서버를 만들지 않음 |
| 74 | 컴퓨터를 켜기 전에 내부 주소 설정을 검사해요. 새 서버는 만들지 않아요. | `module.eks.module.eks_managed_node_group["general"].module.user_data.null_resource.validate_cluster_service_cidr` | 부팅 설정의 cluster service CIDR 검증; AWS 서버를 만들지 않음 |

## Pod 전용 IAM 역할 — 16개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 75 | 입구 안내 도구가 AWS에서 해도 되는 일을 적어요. | `aws_iam_role_policy.alb_controller` | ALB controller 공식 API 정책 |
| 76 | 자동 확장 담당자가 우리 컴퓨터만 조절하게 해요. | `aws_iam_role_policy.cluster_autoscaler` | 해당 클러스터 tag로 제한한 Autoscaler 변경 권한 |
| 77 | 입구 안내 도구만 쓰는 출입증을 만들어요. | `module.alb_controller_irsa.aws_iam_role.this[0]` | ALB controller의 IRSA 역할 |
| 78 | 기록 수집 도구만 쓰는 출입증을 만들어요. | `module.cloudwatch_irsa.aws_iam_role.this[0]` | CloudWatch agent·Fluent Bit의 IRSA 역할 |
| 79 | 기록 수집 도구에 허가 규칙을 붙여요. | `module.cloudwatch_irsa.aws_iam_role_policy_attachment.this["agent"]` | CloudWatch agent·Fluent Bit 역할에 권한 정책 연결 |
| 80 | 컴퓨터 수 조절 도구만 쓰는 출입증을 만들어요. | `module.cluster_autoscaler_irsa.aws_iam_role.this[0]` | Cluster Autoscaler의 IRSA 역할 |
| 81 | 저장 공간 연결 도구가 해도 되는 일을 적어요. | `module.ebs_csi_irsa.aws_iam_policy.ebs_csi[0]` | EBS CSI의 AWS 접근 정책 |
| 82 | 저장 공간 연결 도구만 쓰는 출입증을 만들어요. | `module.ebs_csi_irsa.aws_iam_role.this[0]` | EBS CSI의 IRSA 역할 |
| 83 | 저장 공간 연결 도구에 허가 규칙을 붙여요. | `module.ebs_csi_irsa.aws_iam_role_policy_attachment.ebs_csi[0]` | EBS CSI 역할에 권한 정책 연결 |
| 84 | 비밀정보 전달 도구가 해도 되는 일을 적어요. | `module.external_secrets_irsa.aws_iam_policy.external_secrets[0]` | External Secrets Operator의 AWS 접근 정책 |
| 85 | 비밀정보 전달 도구만 쓰는 출입증을 만들어요. | `module.external_secrets_irsa.aws_iam_role.this[0]` | External Secrets Operator의 IRSA 역할 |
| 86 | 비밀정보 전달 도구에 허가 규칙을 붙여요. | `module.external_secrets_irsa.aws_iam_role_policy_attachment.external_secrets[0]` | External Secrets Operator 역할에 권한 정책 연결 |
| 87 | 문서 서비스만 쓰는 출입증을 만들어요. | `module.storage_irsa["document"].aws_iam_role.this[0]` | Document S3 접근의 IRSA 역할 |
| 88 | 문서 서비스에 허가 규칙을 붙여요. | `module.storage_irsa["document"].aws_iam_role_policy_attachment.this["storage"]` | Document S3 접근 역할에 권한 정책 연결 |
| 89 | AI 처리 서비스만 쓰는 출입증을 만들어요. | `module.storage_irsa["pipeline"].aws_iam_role.this[0]` | Pipeline S3 접근의 IRSA 역할 |
| 90 | AI 처리 서비스에 허가 규칙을 붙여요. | `module.storage_irsa["pipeline"].aws_iam_role_policy_attachment.this["storage"]` | Pipeline S3 접근 역할에 권한 정책 연결 |

## PostgreSQL — 4개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 91 | 로그인 쪽 중요한 기록을 보관할 DB예요. | `aws_db_instance.access` | Access 전용 PostgreSQL 16, db.t4g.small, 암호화 gp3 30GB, private Single-AZ, 백업 7일 |
| 92 | 문서와 AI 쪽 중요한 기록을 보관할 DB예요. | `aws_db_instance.core` | Core·AI DB용 PostgreSQL 16, db.t4g.small, 암호화 gp3 30GB, private Single-AZ, 백업 7일 |
| 93 | DB를 둘 안쪽 구역을 정해요. | `aws_db_subnet_group.main` | DB 배치용 private subnet 집합 |
| 94 | EKS 컴퓨터만 DB의 정해진 문으로 오게 해요. | `aws_security_group.rds` | EKS 노드에서 PostgreSQL 5432 접근만 허용 |

## Redis — 8개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 95 | 자주 쓰는 정보를 빨리 찾는 Redis 메모장이에요. | `aws_elasticache_replication_group.main` | Redis 7.1 cache.t4g.micro 1대, TLS·저장 암호화 |
| 96 | Redis를 둘 안쪽 구역을 정해요. | `aws_elasticache_subnet_group.main` | Redis 배치용 private subnet 집합 |
| 97 | 기본 Redis 계정은 쓰지 못하게 해요. | `aws_elasticache_user.disabled_default` | default 사용자 비활성화 |
| 98 | access 서비스가 Redis에서 쓸 자기 계정이에요. | `aws_elasticache_user.service["access"]` | access 서비스 전용 Redis ACL 사용자 |
| 99 | document 서비스가 Redis에서 쓸 자기 계정이에요. | `aws_elasticache_user.service["document"]` | document 서비스 전용 Redis ACL 사용자 |
| 100 | pipeline 서비스가 Redis에서 쓸 자기 계정이에요. | `aws_elasticache_user.service["pipeline"]` | pipeline 서비스 전용 Redis ACL 사용자 |
| 101 | 서비스별 Redis 계정을 메모장에 연결해요. | `aws_elasticache_user_group.services` | 서비스별 Redis 사용자들을 묶어 Redis에 연결 |
| 102 | EKS 컴퓨터만 Redis의 정해진 문으로 오게 해요. | `aws_security_group.redis` | EKS 노드에서 Redis 6379 접근만 허용 |

## 파일·이미지 저장소 — 14개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 103 | access-svc의 설치용 프로그램 상자를 최근 10개만 남겨요. | `aws_ecr_lifecycle_policy.services["access-svc"]` | access-svc 저장소 최근 10개 이미지 보존 |
| 104 | converter의 설치용 프로그램 상자를 최근 10개만 남겨요. | `aws_ecr_lifecycle_policy.services["converter"]` | converter 저장소 최근 10개 이미지 보존 |
| 105 | document-svc의 설치용 프로그램 상자를 최근 10개만 남겨요. | `aws_ecr_lifecycle_policy.services["document-svc"]` | document-svc 저장소 최근 10개 이미지 보존 |
| 106 | pipeline의 설치용 프로그램 상자를 최근 10개만 남겨요. | `aws_ecr_lifecycle_policy.services["pipeline"]` | pipeline 저장소 최근 10개 이미지 보존 |
| 107 | access-svc의 프로그램 상자 보관함이에요. 같은 이름표로 덮어쓰지 못하고 넣을 때 검사해요. | `aws_ecr_repository.services["access-svc"]` | access-svc 이미지 저장소, immutable tag·push scan |
| 108 | converter의 프로그램 상자 보관함이에요. 같은 이름표로 덮어쓰지 못하고 넣을 때 검사해요. | `aws_ecr_repository.services["converter"]` | converter 이미지 저장소, immutable tag·push scan |
| 109 | document-svc의 프로그램 상자 보관함이에요. 같은 이름표로 덮어쓰지 못하고 넣을 때 검사해요. | `aws_ecr_repository.services["document-svc"]` | document-svc 이미지 저장소, immutable tag·push scan |
| 110 | pipeline의 프로그램 상자 보관함이에요. 같은 이름표로 덮어쓰지 못하고 넣을 때 검사해요. | `aws_ecr_repository.services["pipeline"]` | pipeline 이미지 저장소, immutable tag·push scan |
| 111 | document 서비스가 S3의 정해진 이름 범위에서 읽고 쓰고 지우게 해요. | `aws_iam_policy.storage["document"]` | document 서비스별 S3 prefix 읽기·쓰기·삭제 권한 |
| 112 | pipeline 서비스가 S3의 정해진 이름 범위에서 읽고 쓰고 지우게 해요. | `aws_iam_policy.storage["pipeline"]` | pipeline 서비스별 S3 prefix 읽기·쓰기·삭제 권한 |
| 113 | 문서와 AI 파일을 넣을 보관함이에요. | `aws_s3_bucket.storage` | 문서·AI 파일 저장용 버킷 |
| 114 | 임시 파일과 끝내지 못한 업로드를 7일 기준으로 정리해요. 예전 파일은 남을 수 있어요. | `aws_s3_bucket_lifecycle_configuration.storage` | tmp/ 현재 버전 7일 만료·미완료 multipart 7일 정리 |
| 115 | 파일 보관함을 누구나 열지 못하게 해요. | `aws_s3_bucket_public_access_block.storage` | 앱 버킷 public access 모두 차단 |
| 116 | 파일을 고쳐도 예전 모습을 남겨요. | `aws_s3_bucket_versioning.storage` | 파일 이전 버전 보존 활성화 |

## 비밀정보 생성·보관 — 19개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 117 | 앱 비밀정보를 넣을 잠긴 보관함을 만들어요. | `aws_secretsmanager_secret.app` | 앱 Secret 컨테이너 |
| 118 | Discord 비밀 주소를 넣을 빈 보관함이에요. 주소는 나중에 넣어요. | `aws_secretsmanager_secret.budget_discord` | Discord webhook용 빈 Secret; URL 별도 입력 |
| 119 | 앱의 처음 비밀값들을 보관해요. 나중에 운영자가 고친 값은 덮어쓰지 않아요. | `aws_secretsmanager_secret_version.app` | 앱 초기 DB·Redis·SMTP·인증값 JSON 저장, 이후 Terraform 덮어쓰기 방지 |
| 120 | 다른 파일 보관함과 이름이 겹치지 않게 꼬리표를 만들어요. | `random_id.bucket` | 버킷 이름 충돌 방지 suffix 생성 |
| 121 | 추가 로그인 인증(MFA) 정보를 잠글 열쇠를 만들어요. | `random_id.mfa_encryption_key` | MFA 암호화 키 생성(32바이트); 값 비공개 |
| 122 | AI agent끼리 서로 확인할 비밀값을 만들어요. | `random_password.agent_internal_token` | agent 내부 인증 비밀값 생성; 값 비공개 |
| 123 | access DB 관리자 비밀번호는 RDS가 Secrets Manager에서 직접 관리해요. | `aws_db_instance.access` (`manage_master_user_password`) | 마스터 비밀번호가 Terraform state에 저장되지 않음 |
| 124 | core DB 관리자 비밀번호는 RDS가 Secrets Manager에서 직접 관리해요. | `aws_db_instance.core` (`manage_master_user_password`) | 마스터 비밀번호가 Terraform state에 저장되지 않음 |
| 125 | access_migration용 비밀번호를 만들어요. DB 구조를 고칠 때 써요. | `random_password.db_role["access_migration"]` | DB 역할 access_migration 비밀값 생성; 값 비공개 |
| 126 | access_runtime용 비밀번호를 만들어요. 앱이 평소 DB를 쓸 때 써요. | `random_password.db_role["access_runtime"]` | DB 역할 access_runtime 비밀값 생성; 값 비공개 |
| 127 | ai_migration용 비밀번호를 만들어요. DB 구조를 고칠 때 써요. | `random_password.db_role["ai_migration"]` | DB 역할 ai_migration 비밀값 생성; 값 비공개 |
| 128 | ai_runtime용 비밀번호를 만들어요. 앱이 평소 DB를 쓸 때 써요. | `random_password.db_role["ai_runtime"]` | DB 역할 ai_runtime 비밀값 생성; 값 비공개 |
| 129 | core_migration용 비밀번호를 만들어요. DB 구조를 고칠 때 써요. | `random_password.db_role["core_migration"]` | DB 역할 core_migration 비밀값 생성; 값 비공개 |
| 130 | core_runtime용 비밀번호를 만들어요. 앱이 평소 DB를 쓸 때 써요. | `random_password.db_role["core_runtime"]` | DB 역할 core_runtime 비밀값 생성; 값 비공개 |
| 131 | 내부 프로그램이 결과를 돌려줄 때 신분을 확인할 비밀값이에요. | `random_password.internal_callback_token` | 내부 callback 인증 비밀값 생성; 값 비공개 |
| 132 | 로그인 증명서(JWT)가 진짜인지 확인할 비밀값을 만들어요. | `random_password.jwt_secret` | JWT 서명 비밀값 생성; 값 비공개 |
| 133 | access 서비스가 Redis에 들어갈 비밀번호를 만들어요. | `random_password.redis["access"]` | Redis access 비밀값 생성; 값 비공개 |
| 134 | document 서비스가 Redis에 들어갈 비밀번호를 만들어요. | `random_password.redis["document"]` | Redis document 비밀값 생성; 값 비공개 |
| 135 | pipeline 서비스가 Redis에 들어갈 비밀번호를 만들어요. | `random_password.redis["pipeline"]` | Redis pipeline 비밀값 생성; 값 비공개 |

## 배포 runner·GitHub 인증 — 9개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 136 | 설치 담당 컴퓨터에 출입증을 달아요. | `aws_iam_instance_profile.runner` | runner EC2에 서버 역할 연결 |
| 137 | GitHub 신분을 확인하고 잠시 쓸 권한을 받게 해요. | `aws_iam_openid_connect_provider.github` | GitHub Actions OIDC 임시 인증 provider |
| 138 | GitHub의 feedback 배포에 사용할 출입증이에요. | `aws_iam_role.github_deploy` | GitHub feedback Environment 배포 역할 |
| 139 | 운영자가 설치 담당 컴퓨터를 관리할 때 쓸 권한이에요. | `aws_iam_role.runner_host` | runner SSM 관리 역할 |
| 140 | 설치할 프로그램 상자의 이름표를 읽게 해요. | `aws_iam_role_policy.github_deploy_ecr` | ECR 이미지 태그 조회 권한 |
| 141 | 설치할 EKS가 어떤 곳인지 확인하게 해요. | `aws_iam_role_policy.github_deploy_eks` | 대상 EKS DescribeCluster 권한 |
| 142 | SSM으로 컴퓨터를 관리할 수 있도록 규칙을 붙여요. | `aws_iam_role_policy_attachment.runner_ssm` | runner 역할에 AmazonSSMManagedInstanceCore 연결 |
| 143 | 새 프로그램을 설치할 runner 컴퓨터 1대를 준비해요. | `aws_instance.runner` | private EC2 t3.small, gp3 30GB 암호화, Standard credit, 배포 도구 초기 설치 |
| 144 | 밖에서 직접 들어오는 문은 없애고 나가는 연락은 허용해요. | `aws_security_group.runner` | runner inbound 없음, outbound 허용 |

## CloudWatch 수집·대시보드·경보 — 23개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 145 | 사용량과 문제, 최근 일기를 한 화면에서 봐요. | `aws_cloudwatch_dashboard.operations` | fruition-operations 사용량·경보·최근 로그 대시보드 |
| 146 | Discord로 소식을 보낸 프로그램의 일기를 14일 보관해요. | `aws_cloudwatch_log_group.budget_discord` | Discord 알림 Lambda 로그, 14일 보존 |
| 147 | 앱이 화면 출력처럼 남긴 일기를 14일 보관해요. | `aws_cloudwatch_log_group.containers["application"]` | 앱 stdout/stderr 로그, 14일 보존 |
| 148 | 컴퓨터 안에서 일을 처리하는 부분의 일기를 14일 보관해요. | `aws_cloudwatch_log_group.containers["dataplane"]` | 노드 데이터 영역 로그, 14일 보존 |
| 149 | 컴퓨터 운영체제의 일기를 14일 보관해요. | `aws_cloudwatch_log_group.containers["host"]` | 노드 OS 로그, 14일 보존 |
| 150 | 컴퓨터와 일꾼이 얼마나 바빴는지 14일 보관해요. | `aws_cloudwatch_log_group.containers["performance"]` | Container Insights 성능 로그, 14일 보존 |
| 151 | Discord에 못 보낸 소식이 있는지 알림판에 표시해요. | `aws_cloudwatch_metric_alarm.notification_failures` | Discord 실패 큐 메시지 존재 경보; 재귀 알림 방지로 dashboard 전용 |
| 152 | 5분 동안 앱 일기가 100MiB보다 많이 들어오면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["application_log_volume"]` | 앱 로그 유입 5분 100MiB 초과 경보 |
| 153 | 고장 난 컴퓨터가 있다는 기록이 약 10분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["failed_nodes"]` | 실패 노드 0 초과, 10분 경보 |
| 154 | NAT 길로 밖에 보낸 자료가 5분에 1GiB를 넘으면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["nat_egress"]` | NAT 외부 송신 5분 1GiB 초과 경보 |
| 155 | 컴퓨터의 평균 계산 사용량이 80%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["node_cpu"]` | 노드 CPU 평균 80% 초과, 15분 경보 |
| 156 | 컴퓨터 메모리 사용량의 최대값이 85%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["node_memory"]` | 노드 메모리 최대 85% 초과, 15분 경보 |
| 157 | Discord 소식이 잘 도착하는지 시험하는 벨이에요. | `aws_cloudwatch_metric_alarm.operations["notification_test"]` | Discord ALARM/OK 전달 시험 전용 경보 |
| 158 | 앱 일꾼 CPU 사용량의 최대값이 80%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["pod_cpu"]` | fruition Pod CPU 최대 80% 초과, 15분 경보 |
| 159 | 앱 일꾼 메모리 사용량의 최대값이 85%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["pod_memory"]` | fruition Pod 메모리 최대 85% 초과, 15분 경보 |
| 160 | 로그인 DB의 평균 CPU 사용량이 80%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["rds_access_cpu"]` | Access DB CPU 평균 80% 초과, 15분 경보 |
| 161 | 로그인 DB의 가장 적은 빈 공간이 5GiB 미만인 상태가 약 10분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["rds_access_space"]` | Access DB 여유 공간 5GiB 미만, 10분 경보 |
| 162 | 문서·AI DB의 평균 CPU 사용량이 80%를 넘는 상태가 약 15분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["rds_core_cpu"]` | Core DB CPU 평균 80% 초과, 15분 경보 |
| 163 | 문서·AI DB의 가장 적은 빈 공간이 5GiB 미만인 상태가 약 10분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["rds_core_space"]` | Core DB 여유 공간 5GiB 미만, 10분 경보 |
| 164 | Redis 메모리 사용량의 최대값이 80%를 넘는 상태가 약 10분 이어지면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["redis_memory"]` | Redis primary 메모리 80% 초과, 10분 경보 |
| 165 | 컴퓨터의 CPU 사용량 소식이 약 15분 동안 없으면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["telemetry_missing"]` | 노드 CPU 수집 표본 없음, 15분 경보 |
| 166 | 문지기가 5분에 요청을 100건보다 많이 막으면 알려줘요. | `aws_cloudwatch_metric_alarm.operations["waf_blocked"]` | WAF 차단 요청 5분 100건 초과 경보 |
| 167 | 일기와 사용량을 모으는 CloudWatch 도구를 설치해요. | `aws_eks_addon.observability` | CloudWatch Observability v6.6.0-eksbuild.1, 사용량·컨테이너 로그 수집 |

## 예산·Discord 알림 전달 — 17개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 168 | 400달러보다 이 계정의 한 달 사용료가 많아지면 알려줘요. 자동으로 멈추지는 않아요. | `aws_budgets_budget.monthly["400"]` | 400 USD 계정 전체 월 실제 비용 초과 알림 |
| 169 | 550달러보다 이 계정의 한 달 사용료가 많아지면 알려줘요. 자동으로 멈추지는 않아요. | `aws_budgets_budget.monthly["550"]` | 550 USD 계정 전체 월 실제 비용 초과 알림 |
| 170 | 650달러보다 이 계정의 한 달 사용료가 많아지면 알려줘요. 자동으로 멈추지는 않아요. | `aws_budgets_budget.monthly["650"]` | 650 USD 계정 전체 월 실제 비용 초과 알림 |
| 171 | 소식 보내는 Lambda 프로그램의 출입증이에요. | `aws_iam_role.budget_discord` | 알림 Lambda 실행 역할 |
| 172 | Lambda가 비밀 주소를 읽고 기록과 실패 소식을 남기게 해요. | `aws_iam_role_policy.budget_discord` | 알림 Lambda에 webhook 읽기·로그·실패 큐 쓰기 권한 |
| 173 | 예산·문제·복구 소식을 Discord로 보내는 프로그램이에요. | `aws_lambda_function.budget_discord` | Python3.12, 128MB, 20초; 예산/경보/복구를 Discord에 전달 |
| 174 | 못 보낸 소식을 다시 시도하고, 끝내 못 보내면 상자에 넣어요. | `aws_lambda_function_event_invoke_config.budget_discord` | 비동기 실패 재시도 2회·최대 나이 1시간·SQS 목적지 |
| 175 | 예산 소식 길에서만 Lambda를 부르게 허락해요. | `aws_lambda_permission.budget_sns` | 예산 SNS topic만 Lambda 호출 허용 |
| 176 | 운영 소식 길에서만 Lambda를 부르게 허락해요. | `aws_lambda_permission.operations_sns` | 운영 SNS topic만 Lambda 호출 허용 |
| 177 | 돈에 관한 소식을 전달하는 길이에요. | `aws_sns_topic.budget` | 예산 이벤트 전달 topic |
| 178 | 문제와 복구 소식을 전달하는 길이에요. | `aws_sns_topic.operations` | 운영 경보 이벤트 전달 topic |
| 179 | 우리 프로젝트의 예산 서비스가 이 길로 소식을 보내게 해요. | `aws_sns_topic_policy.budget` | 해당 계정의 프로젝트 예산만 service publisher로 허용 |
| 180 | 우리 프로젝트의 CloudWatch 경보가 이 길로 소식을 보내게 해요. | `aws_sns_topic_policy.operations` | CloudWatch의 프로젝트 경보만 service publisher로 허용 |
| 181 | 예산 소식 길을 Lambda와 연결해요. 못 보낸 소식은 보관해요. | `aws_sns_topic_subscription.budget` | 예산 SNS→알림 Lambda 구독·실패 큐 연결 |
| 182 | 운영 소식 길을 Lambda와 연결해요. 못 보낸 소식은 보관해요. | `aws_sns_topic_subscription.operations` | 운영 SNS→알림 Lambda 구독·실패 큐 연결 |
| 183 | 못 보낸 소식을 잠가서 14일 보관하는 상자예요. | `aws_sqs_queue.budget_failures` | SNS/Lambda 전송 실패 이벤트 14일 보관·서버 측 암호화 |
| 184 | 예산·운영 소식 길이 실패 상자에 기록을 넣게 해요. | `aws_sqs_queue_policy.budget_failures` | 예산/운영 SNS에서 실패 큐로 전달 허용 |

## 요청 비용 보호 — 1개

| 번호 | 쉬운 설명 | 설정에서 찾을 이름 (운영자용) | 정확한 설정 (운영자용) |
|---:|---|---|---|
| 185 | 너무 많은 요청을 거절하는 문지기예요. 긴급 문닫기는 처음에는 꺼져 있어요. | `aws_wafv2_web_acl.cost_guard` | 서울 regional WAF: IP별 600/5분·전체 3000/5분 초과 429, 수동 긴급 차단 기본 꺼짐 |

## 이 목록에 따로 넣지 않은 것도 있어요

| 물건·설정 | 왜 따로 보나요? |
|---|---|
| Terraform 기록용 S3와 보안 설정 5개 | 처음 준비하는 별도 폴더(bootstrap)에서 이미 관리해요 |
| EKS의 실제 컴퓨터·자동 확장 묶음·디스크 | 컴퓨터 묶음(Node Group)이 필요할 때 만들고 교체해요. 여기서는 묶음을 한 항목으로 세요 |
| ALB와 안내 규칙 | 앱의 입구 설정(Ingress)을 설치한 뒤 관리 도구가 만들어요 |
| 앱 일꾼·Kafka·KEDA·비밀 전달·출입 규칙 | Kubernetes 설정 파일과 Helm으로 따로 설치해요 |
| Kafka 저장 디스크 | 저장 공간 요청(PVC)을 보고 EBS CSI가 만들어요 |
| ALB용 CloudWatch 경보 3개 | 아직 ALB 이름표를 입력하지 않아 빠졌어요. 입력하면 추가돼요 |
| Vercel·ACM 인증서·인터넷 주소·외부 AI 계정 | 이 Terraform 폴더에서 만드는 대상이 아니에요 |

긴급 문닫기 스위치는 꺼져 있습니다. 자동으로 문을 닫는 연결은 아직 없습니다. 운영자가 Discord 비밀 주소와 사용할 AI 제공자의 키도 넣어야 합니다.

이 목록은 위 계획을 확인한 날의 준비물 목록입니다. 설정을 바꾸고 새 계획을 만들면 개수도 달라질 수 있습니다.
