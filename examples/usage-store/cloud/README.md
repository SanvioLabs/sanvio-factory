# The usage store in your own cloud account

**Not yet run against a real account.** This Terraform passes `terraform validate`, and the local form has
been run end to end, but the cloud checks (senders can't read or cross prefixes, the team's Grafana can't
open detailed bundles, a revoked node is locked out, the same rows from the bucket as from a folder) haven't
been run yet. The first deployment runs them, as below, before anyone relies on it. Expect to fix things.

Terraform for the bucket, the key for detailed bundles, the senders' roles, the validator and the team's
Grafana. Copy this folder into your infrastructure repository and run it from there, through your own
pipeline. Nothing in it names an account: every value is a variable, set in a `*.tfvars` file that the
[`.gitignore`](.gitignore) here keeps out of git.

## Before the first apply

- **A CA for your unattended machines.** Each node gets a certificate whose common name is its node name,
  and signs in with AWS's `aws_signing_helper` against the trust anchor this makes. Pass the CA's public
  certificate as `node_ca_certificate_pem`.
- **The owner's role**, `owner_role_arn`: the only principal that can decrypt detailed bundles. Give the
  role's exact ARN, path included (a single sign-on role's has one): the key refuses every other principal,
  administrators too. This
  Terraform grants it the key and nothing in the bucket, so give that role `s3:ListBucket` on the bucket
  and `s3:GetObject` on `<prefix>/accepted/*` in your own IAM, for the copy the owner reads from.
- **People's roles**, `people_principal_arns`, if people send from laptops. Each person's role must carry a
  `usage_node` session tag set by your identity provider. The person can write only under
  `incoming/<that tag>/`, so their prefix is exactly as firm as that attribute.
- **Two secrets in your secret store**, named by ARN: the identity provider's client secret for Grafana's
  sign-in, and the webhook address alerts go to. Their values never appear in this Terraform or its state.
- **A network**: a VPC, public subnets for the load balancer, private subnets with a route out for Grafana,
  and a TLS certificate for its address. Or set `grafana_public_ip` and leave out the private subnets: Grafana
  then runs in the public ones with its own address, and the network needs no NAT gateway, which is the
  biggest line in its cost. Its security group takes traffic only from the load balancer either way.

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

## Taking a newer factory

The validator checks bundles against the copy of [`scripts/usage_shape.py`](../../../scripts/usage_shape.py) it was deployed with. After you
pull a factory release whose changelog touches the shape, apply this Terraform again, or the newer senders'
bundles land in `rejected/`. Look in `rejected/` after any update; each object there has a `.reason.json`.

## Revoking a node

Roles Anywhere checks each node's certificate against a revocation list you import. To lock one node out,
revoke its certificate at your CA, then import the CA's list, or update it if there is one:

```
aws rolesanywhere import-crl --name usage-nodes --trust-anchor-arn <trust_anchor_arn> --crl-data fileb://crl.pem --enabled
aws rolesanywhere update-crl --crl-id <id> --crl-data fileb://crl.pem
```

The node's next sign-in is refused. Credentials it already holds last until they expire, an hour at most.

## Checks for the first deployment

Run these once after the first apply, with invented bundles, and record what each showed in
[SPEC-004's TASKS.md](../../../docs/specs/004-usage-export/TASKS.md), T026. They're the spec's AC-010,
AC-011, AC-015 and AC-017.

1. **Senders write only their own prefix.** As a node, `aws s3api get-object` on its own bundle is refused,
   and `put-object` under another node's `incoming/` is refused. As a person, assuming the role with another
   `usage_node` tag is refused.
2. **The validator sorts.** An off-shape bundle lands in `rejected/` with a reason, and a period resent with
   the same chain head and other counts gets a mark under `marks/`.
3. **Detailed stays the owner's.** With Grafana's task role, `get-object` on an accepted detailed bundle is
   refused; with the owner's role it decrypts. A general bundle put under the detailed key is refused.
4. **Alerts.** Stop a test node's loop: one stopped-loop alert. Stop its heartbeats: one silent-node alert
   inside 31 minutes. Push a run past 80% of its budget: one budget alert. None repeats while it stays down.
5. **A revoked node is locked out.** Revoke the test node's certificate and import the list: its next
   sign-in is refused. It holds no access key on disk at any point.
6. **The same rows from the bucket as from a folder.** Copy `accepted/` to a folder, start the local
   Grafana on it, and compare each panel with the cloud Grafana's.
7. **Nothing else is reachable.** The DuckDB plugin holds the task's whole environment, the two secrets
   included, because it needs the task role's credentials from it. In the cloud Grafana, queries of
   `read_text('/proc/self/environ')`, `read_text('/proc/1/environ')`, `glob('/proc/*')` and
   `getenv('USAGE_ALERT_WEBHOOK')` are refused, `duckdb_secrets(redact=false)` is refused, and the API refuses
   basic auth. Ask for a length, never the value, so a check that fails shows nothing.

Then delete the test bundles, or leave them to expire.

## What reads what

| Principal | May |
|---|---|
| A node | Put general bundles and heartbeats under `incoming/<its certificate's CN>/`. Nothing detailed, nothing read |
| A person | Put under `incoming/<their usage_node tag>/`, detailed ones under the detailed key. Nothing read |
| The validator | Read and delete `incoming/`, write `accepted/`, `rejected/` and `marks/`, and use the detailed key to move detailed bundles |
| Grafana | Read general bundles, heartbeats and the shape files under `accepted/`. No detailed bundles, no key |
| The owner | Read everything, detailed bundles included, from a copy: see [`../local/README.md`](../local/README.md) |

Everything expires after `keep_days`, 90 by default, the same as the local logs.
