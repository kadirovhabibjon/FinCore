# ADR-0006: Browser Token Storage and Staff Authorization

## Status

Accepted

## Context

ADR-0005 added a React SPA and left one security-sensitive question open
on purpose: where a browser keeps the two tokens `identity-service`
issues (spec Section 5).

* The **access token** is a 15-minute Ed25519 JWT that every service
  verifies locally against the JWKS (ADR-0003).
* The **refresh token** is opaque, lives 30 days, is single-use, and is
  rotated on every refresh. Replaying a used one revokes the whole
  session (the refresh-token family).

A browser has three places it could keep them: script-readable storage
(`localStorage`/`sessionStorage`), JavaScript memory, or a cookie. Each
one trades off XSS exposure, CSRF exposure, and whether a session
survives a page reload.

The admin panel in ADR-0005 also needs authorization rules that the
backend didn't have yet:

* who may see and act on other users' data;
* how the first staff account comes to exist.

## Decision

### Access token: JavaScript memory only

The SPA keeps the access token in a module variable
(`frontend/src/auth/tokenStore.ts`). It never writes it to
`localStorage` or `sessionStorage`, so script injected through an XSS
bug can't read a token that stays valid after the tab is closed. A page
reload loses the access token on purpose.

### Refresh token: httpOnly cookie, opt-in per request

`POST /api/v1/auth/login` and `/refresh` return the refresh token as a
cookie instead of in the JSON body when the request carries
`X-Refresh-Token-Transport: cookie`. The cookie is set as follows:

```text
fincore_refresh=<token>; HttpOnly; Secure; SameSite=Strict; Path=/api/v1/auth; Max-Age=<ttl>
```

* **`HttpOnly`**: no script can read it, not even the SPA's own.
* **`SameSite=Strict`**, and **`Path=/api/v1/auth`**: the browser sends
  it only on same-site requests to the three auth endpoints, never on a
  wallet or transfer call.
* **`Secure`**: configurable through `REFRESH_COOKIE_SECURE`. It stays on
  by default. Browsers accept Secure cookies on `http://localhost`, so
  the local stack works without TLS.

On load, the SPA calls `/refresh` once to get a new access token. It
does the same on any 401, with the refresh made single-flight, because
refresh tokens are single-use: two parallel refreshes would spend the
same cookie and trip reuse detection.

In cookie mode, `/refresh` and `/logout` only read the cookie when the
opt-in header is present. That header is a CSRF defence layered on top
of `SameSite=Strict`: a cross-site form can't set a custom header, and a
cross-site `fetch` that sets one needs a CORS preflight that the gateway
never approves. The JSON-body mode is unchanged, so API clients, the
e2e suite and the load test keep working as before.

### Separate sessions for the customer site and the admin console

*Added after a staff member, already signed in to the customer site,
opened the admin sign-in page and was signed straight into the app by a
reload.*

The two apps live in one browser, at one origin, but never share a
session.

* The admin console sends `X-Refresh-Token-Transport: cookie-admin`
  instead of `cookie`. Its refresh token lives in its own cookie,
  `fincore_refresh_admin`, with the same attributes as the customer one.
* Signing in to, or out of, either app leaves the other untouched. A
  customer session never opens the console.
* `/login` with `cookie-admin` refuses accounts without SUPPORT or ADMIN
  (403), before any session is created. A console refresh whose account
  has lost its staff role revokes that session.

**The page decides only on a definite answer from the server.** On load
the SPA:

* shows the sign-in page only when `/refresh` says the session is gone
  (401/403);
* retries a network error, timeout, 5xx or 429 a few times, then shows
  "Can't reach FinCore" with a retry button. Before this change, a
  restart of identity-service showed the sign-in page and the next
  reload signed the user back in;
* gets a fast failure when a service is down: the gateway gives up
  connecting after 3 s instead of nginx's default 60 s.

**Signing out is remembered.** Revoking the httpOnly refresh cookie
needs the server. Sign-out is retried, and if it still fails, a
`fincore:signed-out:<app>` marker in localStorage makes every later load
stay signed out and retry the revocation, instead of quietly restoring
the session. The marker holds no secret: only the fact that the user
chose to sign out.

### Same origin

The gateway serves the SPA and the API from one origin. The SPA runs in
its own Nginx container, and the gateway sends it every non-`/api` path.
One origin means:

* no CORS configuration exists at all;
* the strict CSP (`default-src 'self'`) holds;
* the `SameSite=Strict` cookie is always first-party.

The gateway also answers 404 for `/internal/*`, `/metrics` and any
unknown `/api/*` path, so none of them falls through to the SPA's
`index.html`.

### Staff authorization

Roles are `USER`, `SUPPORT` and `ADMIN` (spec Section 5).

* **Access:** `SUPPORT` and `ADMIN` can read other users' data. Only
  `ADMIN` can change it: a user's status, a fraud-review decision, or
  disabling a webhook endpoint.
* **Where the admin API lives:** each service serves its own part under
  `/api/v1/admin/*`, next to the data it owns. There is no separate
  admin service reaching into other services' databases.
* **Where roles are checked:**
  * `identity-service` owns roles, so it re-reads them from its
    database on every request.
  * The other services trust the `roles` claim in the signed access
    token.
* **First admin:** no HTTP endpoint grants a role. The first `ADMIN`,
  and every staff account after it, is granted with
  `python -m app.cli grant-role <email> <ROLE>` inside the
  `identity-service` container. That needs shell access to the running
  system, never just network access.
* **Blocking a user:** setting a user to `BLOCKED` or `SUSPENDED`
  revokes all of that user's sessions in the same transaction. After
  that, refresh rejects any token whose owner isn't `ACTIVE`.
* **Sessions:** each session records its user agent, IP address and
  last use. Users can list and revoke their own sessions, and the access
  token carries a `sid` claim so the UI can mark the current device.

## Consequences

* A reload costs one extra `/refresh` round trip before the first
  authenticated call.
* A revoked session or a blocked user stays able to call services other
  than `identity-service` until the current access token expires, for
  up to 15 minutes. The same applies to a revoked role in
  `payment-service` and `webhook-service`. This is the cost of stateless
  JWT verification (ADR-0003). A denylist or introspection call would
  close the gap at the price of a per-request dependency on
  `identity-service`.
* XSS is still serious, since a script running in the page can make
  requests as the user while the page is open. What it can't do is take
  a long-lived credential away with it. The CSP and React's escaping
  are the defences against the XSS itself.
* Operators need container access to create staff accounts. That is
  deliberate, and it is documented in the README.

## Alternatives Considered

* **Both tokens in `localStorage`.** Simplest, and survives reloads. It
  was rejected because any XSS would carry off a 30-day refresh token.
* **Access token in a cookie as well.** This would make every API route
  cookie-authenticated and so CSRF-relevant, and every service would
  have to learn to read cookies. Keeping the bearer header leaves the
  services unchanged.
* **A backend-for-frontend holding the tokens server-side.** This is the
  strongest option. It was rejected because it adds a stateful service
  and a session store, which is out of proportion for this project. It
  remains the upgrade path if requirements tighten.
* **Checking roles by calling `identity-service` from every service.**
  This gives fresher revocation, but puts a synchronous dependency on
  `identity-service` into every admin request. That is the pattern
  ADR-0003 avoids for authentication.
