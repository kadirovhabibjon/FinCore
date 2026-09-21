from fincore_common import JWTVerifier

from app.core.config import settings

# Same pattern as payment-service: verifies end-user bearer tokens
# locally via identity-service's cached JWKS, no call to identity-service
# per request (ADR-0003). Used only by the public endpoint-registration
# API — webhook-service exposes no /internal/* endpoints of its own, so
# it has no matching require_internal_service dependency.
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)
