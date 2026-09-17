from fincore_common import JWTVerifier

from app.core.config import settings

# Same pattern as ledger-service: verifies end-user bearer tokens locally
# via identity-service's cached JWKS, no call to identity-service per
# request (ADR-0003).
jwt_verifier = JWTVerifier(
    jwks_url=settings.identity_service_jwks_url,
    issuer=settings.jwt_issuer,
)
