# BreakCheck Fleet (v1.1)

Fleet is an optional self-hosted, small-fleet monitoring preview. Desktop features remain standalone. The headless agent runs as the user or service account that can read the selected project folders. It has no remote command channel.

## 1. Enroll devices

Generate a different high-entropy token for the dashboard administrator and each agent:

```sh
python3 -c 'import secrets; print(secrets.token_urlsafe(32))'
```

Keep the tokens out of source control, command arguments, screenshots and logs. The collector reads two environment variables:

- BREAKCHECK_ADMIN_TOKEN: the administrator's random token.
- BREAKCHECK_AGENT_TOKENS: a JSON object mapping each enrolled agent ID to its own random token, e.g. {"office-01":"REPLACE_WITH_RANDOM_AGENT_TOKEN"}.

Agent IDs are operator-selected labels, not automatic hostnames. Only ASCII letters, digits, dots, underscores and hyphens are allowed (1–64 characters). Use non-sensitive IDs. Tokens must be 32–128 URL-safe characters. Never reuse a token. Restart the server after changing enrollment; removing an ID removes its stored report.

## 2. Start the collector

From a source checkout or the published Python application, with the environment above configured:

```sh
python3 BreakCheck.pyz fleet-server --db ./fleet-data/fleet.sqlite3
```

Open http://127.0.0.1:8765 in a local browser. Log in as admin with the administrator token as password. The default bind address is loopback. The JSON status API at /api/v1/status accepts either the same Basic authentication or the admin token as a Bearer credential.

For Docker Compose, copy fleet.env.example to fleet.env inside the deployment folder and replace both placeholders with random tokens. Restrict file permissions to the operator. Then run from the repository root:

```sh
cp deploy/fleet.env.example deploy/fleet.env
chmod 600 deploy/fleet.env
# Edit deploy/fleet.env before launching.
docker compose -f deploy/compose.yaml up -d --build
```

The service listens on host loopback port 8765, stores its latest reports in a named volume, runs as a non-root user and does not need access to host files. Do not publish this port publicly. Docker uses a non-loopback bind within its private network.

## 3. HTTPS for remote agents

Put the collector behind a trusted HTTPS reverse proxy reachable through your private LAN/VPN. Configure valid certificates trusted by each endpoint, authentication-header forwarding, request body limits (4 KiB), timeouts and rate limits. Keep the upstream port private. An example Caddyfile is included; replace its hostname with your own DNS name and configure certificates as appropriate. Plain HTTP is accepted by the agent only on localhost/loopback for local testing. TLS verification remains enabled and HTTP redirects are refused.

## 4. Run a Windows or Linux agent

Set BREAKCHECK_AGENT_TOKEN in the agent's private service environment to the enrolled device token. Choose an independent writable BREAKCHECK_STATE_DIR, outside all monitored folders, to avoid interfering with desktop or other monitoring processes.

```sh
export BREAKCHECK_STATE_DIR="$HOME/.local/share/breakcheck-fleet"
python3 BreakCheck.pyz fleet-agent /srv/project-a /srv/project-b --id office-01 --server https://fleet.example.internal --interval 60
```

```powershell
$env:BREAKCHECK_STATE_DIR = "$env:LOCALAPPDATA\BreakCheckFleet"
.\BreakCheckCLI.exe fleet-agent D:\Projects --id office-01 --server https://fleet.example.internal --interval 60
```

Replace example folders and URL. The token is set separately in a private environment. Use --once for a connectivity/scan check. The normal loop waits after each scan; it retries on delivery failures and does not queue historical reports. Ctrl+C stops it. Use an approved systemd service, Windows Task Scheduler or enterprise supervisor for persistent deployment. A Linux user-service example is included in deploy/. The Windows agent is a foreground CLI, not a Windows Service installer.

For IGEL OS, run on the Linux terminal server when that is where files are stored. Local IGEL deployment requires administrator-provisioned Python 3.10+, persistent storage and supported application deployment. No IGEL-native package is certified.

## Data and security

Each report contains only the selected agent ID (URL), version, requested interval, folder count, observed file count, logical byte count, known broken-link count and counts of partial/failed folders. The server records reception time. Files, paths, error messages, history, hostnames and contents are not included. Network metadata such as IP addresses is visible to the server/proxy. Separate credentials authorize reporting for one agent and dashboard access. Tokens are compared using SHA-256 digests and constant-time comparison. They are not stored in the reports database.

The latest report per agent is retained, not historical events. A stale indicator means a report is older than three requested intervals (minimum 180 seconds), not proof that a machine is offline. Large scans may take longer. Counts are partial where indicated; zero known broken links does not guarantee safety.

This preview uses a small single-request HTTP collector and SQLite. It is for trusted private deployments, not direct public Internet exposure, multi-tenant environments or high availability. Do not share the administrator token with agents. Protect server data/configuration and terminate TLS at the proxy. No remote commands, remote file access, policy distribution, webhooks, SSO or automatic updates are provided. Scale and real IGEL/terminal-server deployments have not been independently certified.
