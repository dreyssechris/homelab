# Keycloak

## Overview

Keycloak 26 runs in namespace `keycloak` (manifests in `deploy/k8s/platform/keycloak/`) and is reachable at `https://auth.chrispicloud.dev` through the Cloudflare Tunnel and Traefik. The admin console is at `https://auth.chrispicloud.dev/admin`.

Secrets (created by hand, see [Secrets Management](secrets-management.md)): `keycloak-admin-credentials` (bootstrap admin) and `keycloak-postgres-credentials`.

## Realms

One realm per group of users, not one per app. A realm is a separate user world (accounts, passwords, roles, signing keys), and single sign-on only works inside one realm. The private apps share one realm, each app is a client in it.

| Realm | Purpose | Clients |
|---|---|---|
| `master` | Administer Keycloak only. No apps here | built-in |
| `chrispicloud` | Shared realm for all private apps | `ascent-web` (CHOAM follows) |
| `choam` | CHOAM until it moves to `chrispicloud` | `choam-web` |

The realm name is part of every token's issuer (`https://auth.chrispicloud.dev/realms/chrispicloud`), so renaming it later means migrating every app.

## Realm `chrispicloud`

The realm is described in [`deploy/k8s/platform/keycloak/realms/chrispicloud.json`](../deploy/k8s/platform/keycloak/realms/chrispicloud.json). The file is not applied by Flux (it is not listed in the kustomization); it is imported once in the admin console.

### Create it

1. Admin console, realm menu top left, **Create realm**.
2. **Resource file**: choose `chrispicloud.json`, then **Create**.
3. **Users › Create new user** in realm `chrispicloud`: username, email, *Email verified* on. Then tab **Credentials › Set password**, *Temporary* off.

What the file sets:

- **Security:** brute force detection (lockout after 10 failures, temporary, up to 15 minutes), no self registration, no password reset by email (no SMTP configured).
- **Token lifetimes (Keycloak defaults):** access token 5 minutes, SSO session idle 30 minutes and max 10 hours, offline session idle 30 days.
- **Refresh token rotation:** `revokeRefreshToken` on, `refreshTokenMaxReuse` 1. Each refresh returns a new refresh token and older ones stop working. One reuse is allowed so that a refresh whose response was lost (no reception in the gym) does not log the app out.
- **Client `ascent-web`:** public client (no secret, the PWA cannot keep one), standard flow only, PKCE `S256` required, redirect and post logout URIs `https://ascent.chrispicloud.dev/*`, web origin `https://ascent.chrispicloud.dev`, scope `offline_access` optional (the app requests it), audience mapper that adds `ascent-api` to the access token.

### Check it

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  https://auth.chrispicloud.dev/realms/chrispicloud/.well-known/openid-configuration   # 200
```

In the console: **Clients › ascent-web › Client scopes › Evaluate**, pick a user, *Generated access token* must contain `"aud": [..., "ascent-api"]`.

### Changes after the import

The file is the starting point, not a sync. Changes made in the console are not written back. When a setting matters for rebuilding the realm, change it in the console and in the file.

## Audience per API

Keycloak puts `aud: account` into almost every access token. An API that accepts `account` therefore accepts tokens issued for any app in the realm. Each API checks only its own audience, and its client gets an audience mapper:

| Client | Audience mapper | API setting |
|---|---|---|
| `ascent-web` | `ascent-api` | `Keycloak__Audience=ascent-api` (overlay `apps/ascent/overlays/prod`) |

## Users

This repository is public, so user names are not listed here. Rule of thumb: accounts in `master` only administer Keycloak and never log into apps; every person who uses the apps has exactly one account in `chrispicloud`.

## Open points

1. Move CHOAM to `chrispicloud`: client `choam-web` with client roles `director` and `agent` instead of realm roles, issuer in API and frontend, users created again, no `account` audience fallback.
2. Disable the bootstrap admin from `keycloak-admin-credentials` once the personal admin account is confirmed to have full access, and enable OTP for the personal admin account.
3. Require PKCE `S256` for `choam-web` (Advanced tab).
4. Turn on brute force detection in `master` and `choam`.
