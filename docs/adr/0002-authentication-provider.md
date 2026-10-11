# ADR 0002 Managed OIDC provider

**Status:** Accepted for V1 (approved 9 October 2026)

## Context

KnowFlow uses Next.js and FastAPI and should avoid building password storage, reset, verification and abuse defenses. The browser should use an HttpOnly cookie/BFF pattern, while FastAPI independently verifies short-lived credentials.

## Decision

Use WorkOS AuthKit. Use Next.js server-side session handling with a Secure, HttpOnly, SameSite=Lax cookie; keep refresh credentials in the sealed session; forward a short-lived JWT from the BFF to FastAPI. Starting defaults are a 15-minute API access token, 7-day maximum app session, and 12-hour idle timeout where provider settings support them. FastAPI verifies JWKS signature, issuer, audience and expiry, then maps `sub` to an internal user. WorkOS organizations are not the app's authorization source. KnowFlow workspace membership and Owner/Member authorization remain entirely in the application/database.

## Alternatives

- Auth0: mature Next.js and Python API support, 25,000 MAU free tier, but current feature/org limits need review.
- Clerk: polished Next.js experience, 50,000 monthly retained users and 100 retained organizations/20 members each on current free tier; cross-runtime BFF and product tenancy coupling require care.
- Microsoft Entra External ID: Azure-aligned OIDC and free MAU tier, but more setup for this exact stack.
- Self-hosted identity service or application-managed credentials.

## Consequences

WorkOS offers current free headroom, separate staging/production and local emulator, with Next.js and Python integration paths. Production requires billing details even below its free usage threshold; optional custom domains and enterprise connections can cost extra. Verify current pricing before setup. Provider pricing was reviewed on 9 October 2026 and must be rechecked before production setup.

## M2 implementation notes

Next.js AuthKit owns the PKCE callback and sealed cookie session. Server components and Server Actions forward a short-lived bearer token to FastAPI; the browser never receives the token. FastAPI verifies RS256 signature through the client-specific JWKS and validates issuer, audience, expiry and subject. AuthKit access tokens do not include an `aud` claim by default, so the WorkOS JWT template must add the configured API audience (local default: `https://api.knowflow.example`) and `WORKOS_TOKEN_AUDIENCE` must match it. It retrieves user profile data with the server-side WorkOS API key and maps the immutable `sub` to `users.auth_subject`. Email is normalized profile data, not an authorization key. Membership provisioning uses WorkOS user lookup and accepts only an existing verified account. The WorkOS user ID and any WorkOS role/org claim do not grant workspace access.
