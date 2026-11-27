# Every value that names an account, a bucket, a person or a network is a variable, set in a gitignored
# tfvars file. None has a default that points anywhere real.

variable "name" {
  description = "A short name for every resource this makes, such as factory-usage"
  type        = string
}

variable "region" {
  description = "The region the store runs in"
  type        = string
}

variable "bucket_name" {
  description = "The store's bucket, which this creates"
  type        = string
}

variable "prefix" {
  description = "The folder in the bucket the store lives under, the prefix in each sender's .sanvio/export.json"
  type        = string
  default     = "usage"
}

variable "keep_days" {
  description = "How long the store keeps every object: the same 90 days as the local logs (SPEC-004 PRIV-004)"
  type        = number
  default     = 90
}

variable "owner_role_arn" {
  description = "The factory owner's role: the only principal that can read detailed bundles (REQ-014)"
  type        = string
}

variable "node_ca_certificate_pem" {
  description = "The public certificate of the CA that signs each unattended node's certificate (REQ-019). Public, not a secret"
  type        = string
}

variable "people_principal_arns" {
  description = "Roles people send from, such as their single sign-on roles. Each needs a usage_node session tag set by the identity provider"
  type        = list(string)
  default     = []
}

variable "grafana_image" {
  description = "The image built from examples/usage-store/Dockerfile and pushed to the repository this creates"
  type        = string
}

variable "vpc_id" {
  description = "The network Grafana runs in"
  type        = string
}

variable "public_subnet_ids" {
  description = "Subnets for Grafana's load balancer"
  type        = list(string)
}

variable "private_subnet_ids" {
  description = "Subnets for Grafana itself, with a route out for sign-in and DuckDB's extensions. Unused with grafana_public_ip"
  type        = list(string)
  default     = []
}

variable "grafana_public_ip" {
  description = "Run Grafana in the public subnets with its own public address instead of the private ones, so the network needs no NAT gateway (about $33 a month in us-east-1, against about $4 for the address). Only the load balancer can reach it either way"
  type        = bool
  default     = false
}

variable "certificate_arn" {
  description = "The TLS certificate for Grafana's address"
  type        = string
}

variable "grafana_url" {
  description = "Grafana's address, such as https://usage.example.com"
  type        = string
}

variable "allowed_cidrs" {
  description = "Addresses that may reach Grafana's sign-in page"
  type        = list(string)
}

variable "oauth" {
  description = "The owner's identity provider, for Grafana's sign-in (REQ-023). Names only: the client secret is read from the secret store by client_secret_arn"
  type = object({
    name              = string
    client_id         = string
    client_secret_arn = string
    auth_url          = string
    token_url         = string
    api_url           = string
    allowed_domains   = string
  })
}

variable "alert_webhook_secret_arn" {
  description = "The secret holding the address alerts are posted to (SEC-005). Read by name, never put in a file"
  type        = string
}
