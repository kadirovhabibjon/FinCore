from fastapi import status
from fincore_common import DomainError


class MerchantNotFoundError(DomainError):
    """Also covers "exists but isn't yours" — same anti-enumeration
    reasoning as payment-service's own MerchantNotFoundError: payment-
    service's /internal/v1/merchants/{id} distinguishes "doesn't exist"
    (404) from "exists but belongs to someone else" (also raised as this
    error, by the caller comparing owner_user_id), and neither is
    revealed to the caller here beyond "not found."
    """

    status_code = status.HTTP_404_NOT_FOUND
    title = "Merchant Not Found"


class MerchantNotActiveError(DomainError):
    status_code = status.HTTP_409_CONFLICT
    title = "Merchant Not Active"


class WebhookEndpointNotFoundError(DomainError):
    status_code = status.HTTP_404_NOT_FOUND
    title = "Webhook Endpoint Not Found"


class InvalidWebhookUrlError(DomainError):
    """Rejected at registration time — a non-http(s) scheme or a target
    that resolves to a private/loopback/link-local/reserved address
    (spec Section 17: "SSRF protection").
    """

    status_code = status.HTTP_422_UNPROCESSABLE_CONTENT
    title = "Invalid Webhook URL"
