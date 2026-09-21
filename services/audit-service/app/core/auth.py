from fincore_common import require_internal_token

from app.core.config import settings

# audit-service has no public API (same shape as notification-service):
# everything it exposes is under /internal/*, shared-secret authenticated.
require_internal_service = require_internal_token(settings.internal_service_token)
