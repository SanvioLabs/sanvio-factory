# The usage store on one machine

From nothing to the dashboard, with Docker and nothing else.

1. **Pick a folder for the store** and point your own `.sanvio/export.json` at it:

   ```json
   {"send": true, "store": {"kind": "folder", "path": "~/usage-store"}, "node": "my-laptop"}
   ```

   A teammate can point theirs at the same folder if it's shared with them, a mounted drive say.

2. **Send something**, so there's a number to see:

   ```
   python3 scripts/export.py --out reports/usage/export.json
   python3 scripts/send_usage.py reports/usage/export.json
   ```

3. **Sort what arrived.** Run this whenever something new has been sent:

   ```
   python3 examples/usage-store/validator.py --folder ~/usage-store
   ```

   Good objects move to `accepted/`, the rest to `rejected/` with a `.reason.json` beside each. It also
   removes anything older than 90 days (`SANVIO_KEEP_DAYS`), the same as the local logs keep.

   Nothing reaches the dashboard until it's sorted, so a machine whose heartbeats sit in `incoming/` reads as
   silent. Where machines send on their own, run it on a schedule too, more often than the 30-minute alert:

   ```
   */5 * * * *  python3 /path/to/factory/examples/usage-store/validator.py --folder ~/usage-store
   ```

4. **Start Grafana**, from [`examples/usage-store/`](../):

   ```
   USAGE_STORE=~/usage-store docker compose -f local/compose.yaml up -d --build
   ```

   Then open <http://127.0.0.1:3000>. *Factory usage* has RQ-1 to RQ-5, and *Factory usage, detailed* has
   RQ-6. It listens on `127.0.0.1` only, so anyone at this machine can read it without signing in, and
   nobody else can reach it. To get the alerts somewhere, set `USAGE_ALERT_WEBHOOK` to a webhook's address
   in the same command; without it they still show in Grafana's own alert list.

5. **Stop it** with `USAGE_STORE=~/usage-store docker compose -f local/compose.yaml down`: the compose file
   needs the store's folder named even to stop. The store is untouched, since Grafana mounts it read-only.
   Grafana's own database, which remembers which alerts it has already sent, stays in a Docker volume, so
   the next `up` doesn't send them again. `down -v` removes that volume too.

## Reading a cloud store here

The owner reads detailed bundles this way, since the team's Grafana in the cloud can't. Copy the bucket's
`accepted/` into a folder with your own profile, which is the one that can decrypt them, and start Grafana
on that folder:

```
aws s3 sync s3://<bucket>/<prefix>/accepted ~/usage-copy/accepted --profile <your profile>
USAGE_STORE=~/usage-copy docker compose -f local/compose.yaml up -d
```

The copy holds the commands in the clear on your disk, so delete it when you're done reading.
