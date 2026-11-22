output "store" {
  description = "What goes in each sender's .sanvio/export.json, beside its own profile name"
  value = {
    kind         = "s3"
    bucket       = aws_s3_bucket.store.id
    prefix       = local.prefix
    region       = var.region
    detailed_key = aws_kms_key.detailed.arn # the ARN, not the alias: the bucket policy compares the ARN
  }
}

output "node_profile" {
  description = "For each node's aws_signing_helper: the trust anchor, profile and role it signs in with"
  value = {
    trust_anchor_arn = aws_rolesanywhere_trust_anchor.nodes.arn
    profile_arn      = aws_rolesanywhere_profile.nodes.arn
    role_arn         = aws_iam_role.node_sender.arn
  }
}

output "person_sender_role_arn" {
  description = "The role people send from, when people_principal_arns names any"
  value       = length(aws_iam_role.person_sender) > 0 ? aws_iam_role.person_sender[0].arn : null
}

output "grafana_repository" {
  description = "Where to push the image built from ../Dockerfile"
  value       = aws_ecr_repository.grafana.repository_url
}

output "grafana_address" {
  description = "Point Grafana's DNS name here"
  value       = aws_lb.grafana.dns_name
}
