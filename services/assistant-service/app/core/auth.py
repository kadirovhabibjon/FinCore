from fincore_common import JWTVerifier

from app.core.config import settings

# Verifies customers' bearer tokens locally against identity-service's
# cached JWKS, like every other service (ADR-0003).
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)
