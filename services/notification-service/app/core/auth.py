from fincore_common import require_internal_token

from app.core.config import settings

require_internal_service = require_internal_token(settings.internal_service_token)
