from fincore_common import JWTVerifier, require_internal_token

from app.core.config import settings

# Same pattern as ledger-service: verifies end-user bearer tokens locally
# via identity-service's cached JWKS, no call to identity-service per
# request (ADR-0003).
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)

# Verifies the shared secret other services send on payment-service's own
# /internal/* API (Section 19) — payment-service is a caller of this
# pattern elsewhere (ledger.py, fraud.py) and now also a callee, for
# webhook-service's merchant-ownership lookup.
require_internal_service = require_internal_token(settings.internal_service_token)
