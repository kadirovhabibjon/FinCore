from fincore_common import require_internal_token

from app.core.config import settings

# fraud-service has no public API at all (spec Section 12: payment-service
# is its only caller, via /internal/v1/risk-checks) — every route uses
# this, none verify an end-user JWT.
require_internal_service = require_internal_token(settings.internal_service_token)
