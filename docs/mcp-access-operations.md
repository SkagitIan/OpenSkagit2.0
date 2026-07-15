# OpenSkagit MCP Access Operations

Status: production runbook
Date: 2026-07-15
Public catalog: `https://openskagit.com/mcp/`
Connector endpoint: `https://openskagit.com/mcp/api/`

## Review an access request

1. Open Django admin and review **MCP access requests**.
2. Confirm the request has a real contact, an understandable use case, an appropriate expected volume, and acceptance of the responsible-use statement.
3. Decline requests that ask for scraping, bulk redistribution, privileged actions, or uses that cannot tolerate source uncertainty. Record the reason in `admin_notes`.
4. For an approved request, issue credentials from a Railway shell:

```powershell
python manage.py approve_mcp_access REQUEST_ID --name "Organization / client"
```

For a non-Claude client, repeat `--redirect-uri` for every exact callback URI approved for that client. Never accept wildcard redirect URIs.

## Deliver credentials

The command prints the connector URL, client ID, and client secret. Send the client ID and secret through an approved secure channel, not the public form or an issue tracker. The command and Django admin do not display the secret again. The encrypted value remains recoverable only while the deployment `SECRET_KEY` is unchanged.

For Claude, the approved user adds the remote URL under **Customize -> Connectors -> Add custom connector**, then supplies the client ID and secret in Advanced settings.

## Revoke or expire access

In Django admin, open **MCP OAuth clients** and clear `active`, or set `expires_at` to a past time. Existing access-token verification checks client activity, so disabling the client blocks active grants immediately. Refresh-token exchange also requires the client to remain available.

Optionally mark active rows under **MCP OAuth grants** inactive for a narrower revocation. Never edit token digests or encrypted secrets.

## Audit and incident response

- Review `last_used_at`, client activity, pending requests, and active grants regularly.
- Do not copy tokens, client secrets, authorization codes, or encrypted secret values into logs or tickets.
- If a client secret is exposed, disable that client, issue a replacement, and deliver it securely.
- If `SECRET_KEY` must rotate, disable or reissue all OAuth clients because existing encrypted client secrets will no longer decrypt.
- If abuse affects the service, disable the client first, preserve request/client identifiers and timestamps, then investigate upstream source load.

## Deployment smoke checks

After each web deployment, verify:

```text
GET  https://openskagit.com/mcp/
GET  https://openskagit.com/.well-known/oauth-authorization-server
GET  https://openskagit.com/.well-known/oauth-protected-resource/mcp/api/
POST https://openskagit.com/mcp/api/  -> 401 without a bearer token
```

The authorization metadata must advertise HTTPS endpoints, `openskagit.read`, authorization-code and refresh-token grants, client-secret authentication, and S256 PKCE. The protected-resource document must identify `https://openskagit.com/mcp/api/`.

## Retention

Authorization codes are single-use and expire after five minutes. Access tokens expire after one hour. Refresh tokens expire after 30 days and rotate when used. Periodically delete expired authorization-code and inactive/expired grant rows after the desired audit-retention window.