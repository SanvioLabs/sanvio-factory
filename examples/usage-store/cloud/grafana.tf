# The team's Grafana (SPEC-004 REQ-022, REQ-023): the image from ../Dockerfile on a container service,
# reading general bundles and heartbeats from the bucket with its own role, and nothing detailed. Sign-in is
# only through the owner's identity provider; there's no password login and no anonymous view.
#
# Grafana's own database lives in the task's storage, so a restart rebuilds it from the provisioning files.
# Dashboards, data source and alert rules come back as they were; alert history doesn't, so a restart sends
# each alert that's still firing once more.

resource "aws_ecr_repository" "grafana" {
  name                 = "${var.name}-grafana"
  image_tag_mutability = "IMMUTABLE"
  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecs_cluster" "usage" {
  name = var.name
}

resource "aws_cloudwatch_log_group" "grafana" {
  name              = "/ecs/${var.name}-grafana"
  retention_in_days = 30
}

data "aws_iam_policy_document" "ecs_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

# What starts the task: pulls the image, writes logs, and hands it the two secrets by reference.
resource "aws_iam_role" "grafana_execution" {
  name               = "${var.name}-grafana-execution"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

resource "aws_iam_role_policy_attachment" "grafana_execution" {
  role       = aws_iam_role.grafana_execution.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

data "aws_iam_policy_document" "grafana_secrets" {
  statement {
    actions   = ["secretsmanager:GetSecretValue"]
    resources = [var.oauth.client_secret_arn, var.alert_webhook_secret_arn]
  }
}

resource "aws_iam_role_policy" "grafana_secrets" {
  role   = aws_iam_role.grafana_execution.id
  policy = data.aws_iam_policy_document.grafana_secrets.json
}

# What Grafana reads with: general bundles, heartbeats and the shape files. No detailed/ and no key.
resource "aws_iam_role" "grafana_task" {
  name               = "${var.name}-grafana-task"
  assume_role_policy = data.aws_iam_policy_document.ecs_trust.json
}

data "aws_iam_policy_document" "grafana_task" {
  statement {
    actions = ["s3:GetObject"]
    resources = [
      "${local.accepted}/*/*/general/*",
      "${local.accepted}/*/heartbeat/*",
      "${local.accepted}/_shape/*",
    ]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [local.bucket]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.prefix}/accepted/*"]
    }
  }
}

resource "aws_iam_role_policy" "grafana_task" {
  role   = aws_iam_role.grafana_task.id
  policy = data.aws_iam_policy_document.grafana_task.json
}

resource "aws_ecs_task_definition" "grafana" {
  family                   = "${var.name}-grafana"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 512
  memory                   = 1024
  execution_role_arn       = aws_iam_role.grafana_execution.arn
  task_role_arn            = aws_iam_role.grafana_task.arn
  runtime_platform {
    operating_system_family = "LINUX"
    cpu_architecture        = "ARM64"
  }
  container_definitions = jsonencode([{
    name         = "grafana"
    image        = var.grafana_image
    essential    = true
    portMappings = [{ containerPort = 3000, protocol = "tcp" }]
    environment = [
      { name = "USAGE_ROOT", value = "s3://${aws_s3_bucket.store.id}/${local.prefix}" },
      # The bucket needs these first: DuckDB's S3 and cloud-credential extensions, and a secret that takes
      # the task role's credentials from the environment. It names no key.
      { name = "USAGE_INIT", value = "INSTALL httpfs; LOAD httpfs; INSTALL aws; LOAD aws; CREATE OR REPLACE SECRET usage_store (TYPE s3, PROVIDER credential_chain, REGION '${var.region}');" },
      { name = "GF_SERVER_ROOT_URL", value = var.grafana_url },
      { name = "GF_AUTH_DISABLE_LOGIN_FORM", value = "true" },
      { name = "GF_AUTH_ANONYMOUS_ENABLED", value = "false" },
      { name = "GF_AUTH_GENERIC_OAUTH_ENABLED", value = "true" },
      { name = "GF_AUTH_GENERIC_OAUTH_NAME", value = var.oauth.name },
      { name = "GF_AUTH_GENERIC_OAUTH_CLIENT_ID", value = var.oauth.client_id },
      { name = "GF_AUTH_GENERIC_OAUTH_AUTH_URL", value = var.oauth.auth_url },
      { name = "GF_AUTH_GENERIC_OAUTH_TOKEN_URL", value = var.oauth.token_url },
      { name = "GF_AUTH_GENERIC_OAUTH_API_URL", value = var.oauth.api_url },
      { name = "GF_AUTH_GENERIC_OAUTH_ALLOWED_DOMAINS", value = var.oauth.allowed_domains },
      { name = "GF_AUTH_GENERIC_OAUTH_SCOPES", value = "openid email profile" },
      { name = "GF_USERS_AUTO_ASSIGN_ORG_ROLE", value = "Viewer" },
    ]
    secrets = [
      { name = "GF_AUTH_GENERIC_OAUTH_CLIENT_SECRET", valueFrom = var.oauth.client_secret_arn },
      { name = "USAGE_ALERT_WEBHOOK", valueFrom = var.alert_webhook_secret_arn },
    ]
    logConfiguration = {
      logDriver = "awslogs"
      options = {
        awslogs-group         = aws_cloudwatch_log_group.grafana.name
        awslogs-region        = var.region
        awslogs-stream-prefix = "grafana"
      }
    }
  }])
}

resource "aws_security_group" "alb" {
  name   = "${var.name}-alb"
  vpc_id = var.vpc_id
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = var.allowed_cidrs
  }
  egress {
    from_port   = 3000
    to_port     = 3000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_security_group" "grafana" {
  name   = "${var.name}-grafana"
  vpc_id = var.vpc_id
  ingress {
    from_port       = 3000
    to_port         = 3000
    protocol        = "tcp"
    security_groups = [aws_security_group.alb.id]
  }
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_lb" "grafana" {
  name                       = "${var.name}-grafana"
  load_balancer_type         = "application"
  subnets                    = var.public_subnet_ids
  security_groups            = [aws_security_group.alb.id]
  drop_invalid_header_fields = true
}

resource "aws_lb_target_group" "grafana" {
  name        = "${var.name}-grafana"
  port        = 3000
  protocol    = "HTTP"
  target_type = "ip"
  vpc_id      = var.vpc_id
  health_check {
    path = "/api/health"
  }
}

resource "aws_lb_listener" "grafana" {
  load_balancer_arn = aws_lb.grafana.arn
  port              = 443
  protocol          = "HTTPS"
  ssl_policy        = "ELBSecurityPolicy-TLS13-1-2-2021-06"
  certificate_arn   = var.certificate_arn
  default_action {
    type             = "forward"
    target_group_arn = aws_lb_target_group.grafana.arn
  }
}

resource "aws_ecs_service" "grafana" {
  name            = "${var.name}-grafana"
  cluster         = aws_ecs_cluster.usage.id
  task_definition = aws_ecs_task_definition.grafana.arn
  desired_count   = 1
  launch_type     = "FARGATE"
  network_configuration {
    subnets          = var.private_subnet_ids
    security_groups  = [aws_security_group.grafana.id]
    assign_public_ip = false
  }
  load_balancer {
    target_group_arn = aws_lb_target_group.grafana.arn
    container_name   = "grafana"
    container_port   = 3000
  }
  depends_on = [aws_lb_listener.grafana]
}
