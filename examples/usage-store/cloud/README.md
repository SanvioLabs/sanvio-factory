# The usage store in your own cloud account

Terraform for the bucket, the key for detailed bundles, the senders' roles, the validator and the team's
Grafana. Copy this folder into your infrastructure repository and run it from there, through your own
pipeline. Nothing in it names an account: every value is a variable, set in a `*.tfvars` file that the
[`.gitignore`](.gitignore) here keeps out of git.

## Before the first apply

- **A CA for your unattended machines.** Each node gets a certificate whose common name is its node name,
  and signs in with AWS's `aws_signing_helper` against the trust anchor this makes. Pass the CA's public
  certificate as `node_ca_certificate_pem`.
- **The owner's role**, `owner_role_arn`: the only principal that can decrypt detailed bundles. This
  Terraform grants it the key and nothing in the bucket, so give that role `s3:ListBucket` on the bucket
  and `s3:GetObject` on `<prefix>/accepted/*` in your own IAM, for the copy the owner reads from.
- **People's roles**, `people_principal_arns`, if people send from laptops. Each person's role must carry a
  `usage_node` session tag set by your identity provider. The person can write only under
  `incoming/<that tag>/`, so their prefix is exactly as firm as that attribute.
- **Two secrets in your secret store**, named by ARN: the identity provider's client secret for Grafana's
  sign-in, and the webhook address alerts go to. Their values never appear in this Terraform or its state.
- **A network**: a VPC, public subnets for the load balancer, private subnets with a route out for Grafana,
  and a TLS certificate for its address.

## The image

Grafana runs the image built from [`../Dockerfile`](../Dockerfile), pushed to the repository this makes:

```
docker build --platform linux/arm64 -t <grafana_repository>:<tag> examples/usage-store
docker push <grafana_repository>:<tag>
```

then set `grafana_image` to that tag. Tags in the repository can't be overwritten.

## After the apply

The `store` output is what each sender adds to `.sanvio/export.json`, with the name of its own CLI profile; [`export.example.json`](export.example.json) is a whole one, with invented values.
For a node, that profile is the signing helper's:

```ini
[profile usage-sender]
credential_process = aws_signing_helper credential-process --certificate <cert> --private-key <key> --trust-anchor-arn <trust_anchor_arn> --profile-arn <profile_arn> --role-arn <role_arn>
```

## What reads what

| Principal | May |
|---|---|
| A node | Put general bundles and heartbeats under `incoming/<its certificate's CN>/`. Nothing detailed, nothing read |
| A person | Put under `incoming/<their usage_node tag>/`, detailed ones under the detailed key. Nothing read |
| The validator | Read and delete `incoming/`, write `accepted/`, `rejected/` and `marks/`, and use the detailed key to move detailed bundles |
| Grafana | Read general bundles, heartbeats and the shape files under `accepted/`. No detailed bundles, no key |
| The owner | Read everything, detailed bundles included, from a copy: see [`../local/README.md`](../local/README.md) |

Everything expires after `keep_days`, 90 by default, the same as the local logs.
