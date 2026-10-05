from fincore_common import JWTVerifier, require_internal_token

from app.core.config import settings

require_internal_service = require_internal_token(settings.internal_service_token)

# For the public notifications API. One verifier for the process: it
# caches identity-service's JWKS in memory, so verifying a customer's
# token makes no network call on a cache hit.
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)
