from fincore_common import JWTVerifier, require_internal_token

from app.core.config import settings

# One verifier instance for the process: it caches identity-service's
# JWKS response in memory (see fincore_common.auth.JWTVerifier) so a
# cache hit never makes a network call.
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)

require_internal_service = require_internal_token(settings.internal_service_token)
