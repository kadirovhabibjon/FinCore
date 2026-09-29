// One typed function per public endpoint the SPA uses. Every type comes
// from the generated contract schemas (src/api/schema), never written by
// hand, so a backend contract change breaks the build here first.
import { refreshTransportHeaders, setAccessToken } from "../auth/tokenStore";
import { apiRequest } from "./client";
import type { components as IdentitySchemas } from "./schema/identity-service";
import type { components as LedgerSchemas } from "./schema/ledger-service";
import type { components as PaymentSchemas } from "./schema/payment-service";
import type { components as WebhookSchemas } from "./schema/webhook-service";

type Identity = IdentitySchemas["schemas"];
type Ledger = LedgerSchemas["schemas"];
type Payment = PaymentSchemas["schemas"];
type Webhook = WebhookSchemas["schemas"];

export type CurrentUser = Identity["CurrentUserResponse"];
export type UserSession = Identity["SessionResponse"];
export type AdminUser = Identity["AdminUserResponse"];
export type UserStatus = Identity["UserStatus"];
export type RegisterRequest = Identity["RegisterRequest"];
export type Wallet = Ledger["WalletResponse"];
export type LedgerEntry = Ledger["LedgerEntryResponse"];
export type Transfer = Payment["TransferResponse"];
export type PaymentRecord = Payment["PaymentResponse"];
export type Refund = Payment["RefundResponse"];
export type Transaction = Payment["TransactionResponse"];
export type AdminTransaction = Payment["AdminTransactionResponse"];
export type Merchant = Payment["MerchantResponse"];
export type ReviewDecision = Payment["ReviewDecision"];
export type TransactionType = Payment["TransactionType"];
export type WebhookEndpoint = Webhook["WebhookEndpointResponse"];
export type WebhookEndpointWithSecret = Webhook["WebhookEndpointWithSecretResponse"];
export type AdminWebhookEndpoint = Webhook["AdminWebhookEndpointResponse"];
export type WebhookDelivery = Webhook["WebhookDeliveryResponse"];

export interface Page {
  limit: number;
  offset: number;
}

// --- auth (identity-service) -------------------------------------------

export async function login(email: string, password: string): Promise<void> {
  const tokens = await apiRequest<Identity["TokenResponse"]>("/api/v1/auth/login", {
    method: "POST",
    body: { email, password },
    headers: refreshTransportHeaders(),
    authenticated: false,
  });
  setAccessToken(tokens.access_token);
}

export function register(data: RegisterRequest): Promise<Identity["UserResponse"]> {
  return apiRequest("/api/v1/auth/register", {
    method: "POST",
    body: data,
    authenticated: false,
  });
}

export function logout(): Promise<void> {
  return apiRequest("/api/v1/auth/logout", {
    method: "POST",
    headers: refreshTransportHeaders(),
    authenticated: false,
  });
}

export const getMe = () => apiRequest<CurrentUser>("/api/v1/users/me");
export const listSessions = () => apiRequest<UserSession[]>("/api/v1/users/me/sessions");
export const revokeSession = (sessionId: string) =>
  apiRequest<void>(`/api/v1/users/me/sessions/${sessionId}`, { method: "DELETE" });

// --- wallets (ledger-service) ------------------------------------------

export const listWallets = () => apiRequest<Wallet[]>("/api/v1/wallets");
export const getWallet = (walletId: string) => apiRequest<Wallet>(`/api/v1/wallets/${walletId}`);
export const createWallet = (currency: string) =>
  apiRequest<Wallet>("/api/v1/wallets", { method: "POST", body: { currency } });
export const listWalletEntries = (walletId: string, page: Page) =>
  apiRequest<LedgerEntry[]>(`/api/v1/wallets/${walletId}/entries`, { query: { ...page } });

// --- transfers, payments, history (payment-service) --------------------

export const createTransfer = (body: Payment["CreateTransferRequest"], idempotencyKey: string) =>
  apiRequest<Transfer>("/api/v1/transfers", { method: "POST", body, idempotencyKey });
export const getTransfer = (transferId: string) =>
  apiRequest<Transfer>(`/api/v1/transfers/${transferId}`);

export const createPayment = (body: Payment["CreatePaymentRequest"], idempotencyKey: string) =>
  apiRequest<PaymentRecord>("/api/v1/payments", { method: "POST", body, idempotencyKey });
export const getPayment = (paymentId: string) =>
  apiRequest<PaymentRecord>(`/api/v1/payments/${paymentId}`);
export const createRefund = (
  paymentId: string,
  body: Payment["CreateRefundRequest"],
  idempotencyKey: string,
) =>
  apiRequest<Refund>(`/api/v1/payments/${paymentId}/refunds`, {
    method: "POST",
    body,
    idempotencyKey,
  });

export const listTransactions = (page: Page) =>
  apiRequest<Transaction[]>("/api/v1/transactions", { query: { ...page } });
export const getTransaction = (transactionId: string) =>
  apiRequest<Transaction>(`/api/v1/transactions/${transactionId}`);

export const listMerchants = () => apiRequest<Merchant[]>("/api/v1/merchants");
export const getMerchant = (merchantId: string) =>
  apiRequest<Merchant>(`/api/v1/merchants/${merchantId}`);
export const createMerchant = (name: string) =>
  apiRequest<Merchant>("/api/v1/merchants", { method: "POST", body: { name } });
export const listMerchantPayments = (merchantId: string, page: Page) =>
  apiRequest<PaymentRecord[]>(`/api/v1/merchants/${merchantId}/payments`, {
    query: { ...page },
  });

// --- webhooks (webhook-service) ----------------------------------------

export const listWebhookEndpoints = () =>
  apiRequest<WebhookEndpoint[]>("/api/v1/webhooks/endpoints");
export const createWebhookEndpoint = (merchantId: string, url: string) =>
  apiRequest<WebhookEndpointWithSecret>("/api/v1/webhooks/endpoints", {
    method: "POST",
    body: { merchant_id: merchantId, url },
  });
export const rotateWebhookSecret = (endpointId: string) =>
  apiRequest<WebhookEndpointWithSecret>(`/api/v1/webhooks/endpoints/${endpointId}/rotate-secret`, {
    method: "POST",
  });
export const enableWebhookEndpoint = (endpointId: string) =>
  apiRequest<WebhookEndpoint>(`/api/v1/webhooks/endpoints/${endpointId}/enable`, {
    method: "POST",
  });
export const listWebhookDeliveries = (endpointId: string, page: Page) =>
  apiRequest<WebhookDelivery[]>(`/api/v1/webhooks/endpoints/${endpointId}/deliveries`, {
    query: { ...page },
  });

// --- admin panel (ADR-0005) --------------------------------------------

export const adminSearchUsers = (q: string, page: Page) =>
  apiRequest<AdminUser[]>("/api/v1/admin/users", { query: { q, ...page } });
export const adminGetUser = (userId: string) =>
  apiRequest<AdminUser>(`/api/v1/admin/users/${userId}`);
export const adminSetUserStatus = (userId: string, status: UserStatus) =>
  apiRequest<AdminUser>(`/api/v1/admin/users/${userId}/status`, {
    method: "POST",
    body: { status },
  });

export const adminListReviews = () => apiRequest<AdminTransaction[]>("/api/v1/admin/reviews");
export const adminDecideReview = (operationId: string, decision: ReviewDecision) =>
  apiRequest<AdminTransaction>(`/api/v1/admin/reviews/${operationId}`, {
    method: "POST",
    body: { decision },
  });

export interface AdminTransactionFilters {
  type?: TransactionType;
  status?: string;
  user_id?: string;
}

export const adminListTransactions = (filters: AdminTransactionFilters, page: Page) =>
  apiRequest<AdminTransaction[]>("/api/v1/admin/transactions", {
    query: { ...filters, ...page },
  });

export const adminListWebhookEndpoints = (status: string | undefined, page: Page) =>
  apiRequest<AdminWebhookEndpoint[]>("/api/v1/admin/webhooks/endpoints", {
    query: { status, ...page },
  });
export const adminListWebhookDeliveries = (endpointId: string, page: Page) =>
  apiRequest<WebhookDelivery[]>(`/api/v1/admin/webhooks/endpoints/${endpointId}/deliveries`, {
    query: { ...page },
  });
export const adminSetWebhookEndpointEnabled = (endpointId: string, enabled: boolean) =>
  apiRequest<AdminWebhookEndpoint>(
    `/api/v1/admin/webhooks/endpoints/${endpointId}/${enabled ? "enable" : "disable"}`,
    { method: "POST" },
  );
