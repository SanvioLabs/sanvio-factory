# The usage store in your own cloud account (SPEC-004 REQ-013, REQ-014, REQ-019, REQ-021, REQ-023).
#
#   bucket   <prefix>/incoming/  senders put, nobody reads
#            <prefix>/accepted/  the validator moves each good object here; Grafana reads general and heartbeats
#            <prefix>/rejected/  the rest, with a .reason.json beside each
#            <prefix>/marks/     chain marks
#   key      detailed bundles are encrypted with a key only the owner, the people who send them and the
#            validator can use. Grafana's role has no use of it, so the team's dashboard can't read commands
#   senders  nodes by certificate, through IAM Roles Anywhere, each to incoming/<its certificate's CN>/;
#            people by their own role, each to incoming/<the usage_node tag their identity provider sets>/
#   grafana  the image from ../Dockerfile on a container service, behind a load balancer, with sign-in only
#            through the owner's identity provider

terraform {
  required_version = ">= 1.6"
  required_providers {
    aws     = { source = "hashicorp/aws", version = "~> 6.0" }
    archive = { source = "hashicorp/archive", version = "~> 2.7" }
  }
}

provider "aws" {
  region = var.region
}

data "aws_caller_identity" "here" {}

locals {
  prefix   = trim(var.prefix, "/")
  bucket   = aws_s3_bucket.store.arn
  incoming = "${aws_s3_bucket.store.arn}/${local.prefix}/incoming"
  accepted = "${aws_s3_bucket.store.arn}/${local.prefix}/accepted"
  shape = {
    "accepted/_shape/_shape/general/shape.json"  = "{\"kind\": \"shape\"}\n"
    "accepted/_shape/_shape/detailed/shape.json" = "{\"kind\": \"shape\"}\n"
    "accepted/_shape/heartbeat/shape.json"       = "{\"kind\": \"shape\"}\n"
  }
}

# -- the bucket ---------------------------------------------------------------------------------------------

resource "aws_s3_bucket" "store" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_public_access_block" "store" {
  bucket                  = aws_s3_bucket.store.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "store" {
  bucket = aws_s3_bucket.store.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "store" {
  bucket = aws_s3_bucket.store.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "store" {
  bucket = aws_s3_bucket.store.id
  rule {
    id     = "keep-${var.keep_days}-days"
    status = "Enabled"
    filter {
      prefix = "${local.prefix}/"
    }
    expiration {
      days = var.keep_days
    }
  }
}

data "aws_iam_policy_document" "bucket" {
  statement {
    sid       = "TlsOnly"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [local.bucket, "${local.bucket}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }
  statement {
    sid       = "DetailedOnlyUnderItsKey"
    effect    = "Deny"
    actions   = ["s3:PutObject"]
    resources = ["${local.incoming}/*/*/detailed/*", "${local.accepted}/*/*/detailed/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringNotEquals"
      variable = "s3:x-amz-server-side-encryption-aws-kms-key-id"
      values   = [aws_kms_key.detailed.arn]
    }
  }
  # Only detailed bundles go under the detailed key. A general bundle or heartbeat under it would be one the
  # team's Grafana can't read, so one sender could blank everyone's dashboard.
  statement {
    sid     = "GeneralNotUnderTheDetailedKey"
    effect  = "Deny"
    actions = ["s3:PutObject"]
    resources = [
      "${local.incoming}/*/*/general/*", "${local.incoming}/*/heartbeat/*",
      "${local.accepted}/*/*/general/*", "${local.accepted}/*/heartbeat/*",
    ]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "StringEquals"
      variable = "s3:x-amz-server-side-encryption"
      values   = ["aws:kms", "aws:kms:dsse"]
    }
  }
}

resource "aws_s3_bucket_policy" "store" {
  bucket = aws_s3_bucket.store.id
  policy = data.aws_iam_policy_document.bucket.json
}

resource "aws_s3_object" "shape" {
  for_each     = local.shape
  bucket       = aws_s3_bucket.store.id
  key          = "${local.prefix}/${each.key}"
  content      = each.value
  content_type = "application/json"
}

# -- the key for detailed bundles ---------------------------------------------------------------------------

data "aws_iam_policy_document" "detailed_key" {
  statement {
    sid       = "AccountAdministers"
    actions   = ["kms:*"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["arn:aws:iam::${data.aws_caller_identity.here.account_id}:root"]
    }
  }
  # The account statement above lets the account's IAM grant the key to anyone. This one stops that for
  # reading: only the owner and the validator ever decrypt, whatever IAM says.
  statement {
    sid       = "NobodyElseDecrypts"
    effect    = "Deny"
    actions   = ["kms:Decrypt", "kms:ReEncryptFrom"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = ["*"]
    }
    condition {
      test     = "ArnNotEquals"
      variable = "aws:PrincipalArn"
      values   = [var.owner_role_arn, aws_iam_role.validator.arn]
    }
  }
  statement {
    sid       = "OwnerReads"
    actions   = ["kms:Decrypt", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = [var.owner_role_arn]
    }
  }
  statement {
    sid       = "ValidatorMoves"
    actions   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
    resources = ["*"]
    principals {
      type        = "AWS"
      identifiers = [aws_iam_role.validator.arn]
    }
  }
  dynamic "statement" {
    for_each = length(var.people_principal_arns) > 0 ? [1] : []
    content {
      sid       = "PeopleEncryptOnly"
      actions   = ["kms:GenerateDataKey", "kms:DescribeKey"]
      resources = ["*"]
      principals {
        type        = "AWS"
        identifiers = [aws_iam_role.person_sender[0].arn]
      }
    }
  }
}

resource "aws_kms_key" "detailed" {
  description         = "${var.name}: detailed usage bundles, readable by the factory owner only"
  enable_key_rotation = true
}

resource "aws_kms_key_policy" "detailed" {
  key_id = aws_kms_key.detailed.id
  policy = data.aws_iam_policy_document.detailed_key.json
}

resource "aws_kms_alias" "detailed" {
  name          = "alias/${var.name}-detailed"
  target_key_id = aws_kms_key.detailed.key_id
}

# -- senders: nodes by certificate --------------------------------------------------------------------------

resource "aws_rolesanywhere_trust_anchor" "nodes" {
  name    = "${var.name}-nodes"
  enabled = true
  source {
    source_type = "CERTIFICATE_BUNDLE"
    source_data {
      x509_certificate_data = var.node_ca_certificate_pem
    }
  }
}

data "aws_iam_policy_document" "node_trust" {
  statement {
    actions = ["sts:AssumeRole", "sts:TagSession", "sts:SetSourceIdentity"]
    principals {
      type        = "Service"
      identifiers = ["rolesanywhere.amazonaws.com"]
    }
    condition {
      test     = "ArnEquals"
      variable = "aws:SourceArn"
      values   = [aws_rolesanywhere_trust_anchor.nodes.arn]
    }
  }
}

resource "aws_iam_role" "node_sender" {
  name                 = "${var.name}-node-sender"
  assume_role_policy   = data.aws_iam_policy_document.node_trust.json
  max_session_duration = 3600
}

# Each node writes only under incoming/<its certificate's common name>/, and never detailed (REQ-011).
data "aws_iam_policy_document" "node_sender" {
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${local.incoming}/$${aws:PrincipalTag/x509Subject/CN}/*/general/*", "${local.incoming}/$${aws:PrincipalTag/x509Subject/CN}/heartbeat/*"]
  }
}

resource "aws_iam_role_policy" "node_sender" {
  role   = aws_iam_role.node_sender.id
  policy = data.aws_iam_policy_document.node_sender.json
}

resource "aws_rolesanywhere_profile" "nodes" {
  name             = "${var.name}-nodes"
  enabled          = true
  role_arns        = [aws_iam_role.node_sender.arn]
  duration_seconds = 3600
}

# -- senders: people by their own role ----------------------------------------------------------------------

data "aws_iam_policy_document" "person_trust" {
  count = length(var.people_principal_arns) > 0 ? 1 : 0
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "AWS"
      identifiers = var.people_principal_arns
    }
  }
  # The usage_node tag comes from the identity provider, carried on the caller's own session. A caller who
  # tries to set a different one on the way in is refused, so nobody writes under another's node.
  statement {
    actions = ["sts:TagSession"]
    principals {
      type        = "AWS"
      identifiers = var.people_principal_arns
    }
    condition {
      test     = "StringEquals"
      variable = "aws:RequestTag/usage_node"
      values   = ["$${aws:PrincipalTag/usage_node}"]
    }
  }
}

resource "aws_iam_role" "person_sender" {
  count                = length(var.people_principal_arns) > 0 ? 1 : 0
  name                 = "${var.name}-person-sender"
  assume_role_policy   = data.aws_iam_policy_document.person_trust[0].json
  max_session_duration = 3600
}

# A person writes only under incoming/<their usage_node tag>/. The identity provider sets that tag, so a
# person's prefix is only as firm as that attribute: say so to whoever runs it.
data "aws_iam_policy_document" "person_sender" {
  count = length(var.people_principal_arns) > 0 ? 1 : 0
  statement {
    actions   = ["s3:PutObject"]
    resources = ["${local.incoming}/$${aws:PrincipalTag/usage_node}/*"]
  }
  statement {
    actions   = ["kms:GenerateDataKey"]
    resources = [aws_kms_key.detailed.arn]
  }
}

resource "aws_iam_role_policy" "person_sender" {
  count  = length(var.people_principal_arns) > 0 ? 1 : 0
  role   = aws_iam_role.person_sender[0].id
  policy = data.aws_iam_policy_document.person_sender[0].json
}

# -- the validator ------------------------------------------------------------------------------------------

data "archive_file" "validator" {
  type        = "zip"
  output_path = "${path.module}/.build/validator.zip"
  source {
    content  = file("${path.module}/../validator.py")
    filename = "validator.py"
  }
  source {
    content  = file("${path.module}/../../../scripts/usage_shape.py")
    filename = "usage_shape.py"
  }
}

data "aws_iam_policy_document" "lambda_trust" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "validator" {
  name               = "${var.name}-validator"
  assume_role_policy = data.aws_iam_policy_document.lambda_trust.json
}

data "aws_iam_policy_document" "validator" {
  statement {
    actions   = ["s3:GetObject", "s3:DeleteObject"]
    resources = ["${local.incoming}/*"]
  }
  statement {
    actions   = ["s3:GetObject", "s3:PutObject"]
    resources = ["${local.accepted}/*", "${local.bucket}/${local.prefix}/rejected/*", "${local.bucket}/${local.prefix}/marks/*"]
  }
  statement {
    actions   = ["s3:ListBucket"]
    resources = [local.bucket]
    condition {
      test     = "StringLike"
      variable = "s3:prefix"
      values   = ["${local.prefix}/accepted/*", "${local.prefix}/incoming/*"]
    }
  }
  statement {
    actions   = ["logs:CreateLogStream", "logs:PutLogEvents"]
    resources = ["${aws_cloudwatch_log_group.validator.arn}:*"]
  }
}

resource "aws_iam_role_policy" "validator" {
  role   = aws_iam_role.validator.id
  policy = data.aws_iam_policy_document.validator.json
}

resource "aws_cloudwatch_log_group" "validator" {
  name              = "/aws/lambda/${var.name}-validator"
  retention_in_days = 30
}

resource "aws_lambda_function" "validator" {
  function_name    = "${var.name}-validator"
  role             = aws_iam_role.validator.arn
  runtime          = "python3.12"
  architectures    = ["arm64"]
  handler          = "validator.handler"
  filename         = data.archive_file.validator.output_path
  source_code_hash = data.archive_file.validator.output_base64sha256
  timeout          = 60
  memory_size      = 256
  environment {
    variables = { USAGE_PREFIX = local.prefix }
  }
  depends_on = [aws_cloudwatch_log_group.validator]
}

resource "aws_lambda_permission" "bucket" {
  statement_id  = "BucketCallsValidator"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.validator.function_name
  principal     = "s3.amazonaws.com"
  source_arn    = aws_s3_bucket.store.arn
}

resource "aws_s3_bucket_notification" "incoming" {
  bucket = aws_s3_bucket.store.id
  lambda_function {
    lambda_function_arn = aws_lambda_function.validator.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "${local.prefix}/incoming/"
    filter_suffix       = ".json"
  }
  depends_on = [aws_lambda_permission.bucket]
}
