// One typed function per public endpoint the SPA uses. Every type comes
// from the generated contract schemas (src/api/schema), never written by
// hand, so a backend contract change breaks the build here first.
import { refreshTransportHeaders, setAccessToken } from "../auth/tokenStore";
import { apiDownload, apiRequest } from "./client";
import type { components as IdentitySchemas } from "./schema/identity-service";
import type { components as LedgerSchemas } from "./schema/ledger-service";
import type { components as PaymentSchemas } from "./schema/payment-service";
import type { components as AssistantSchemas } from "./schema/assistant-service";
import type { components as NotificationSchemas } from "./schema/notification-service";
import type { components as WebhookSchemas } from "./schema/webhook-service";

type Identity = IdentitySchemas["schemas"];
type Ledger = LedgerSchemas["schemas"];
type Payment = PaymentSchemas["schemas"];
type Webhook = WebhookSchemas["schemas"];
type Notifications = NotificationSchemas["schemas"];

export type CurrentUser = Identity["CurrentUserResponse"];
export type UserSession = Identity["SessionResponse"];
export type AdminUser = Identity["AdminUserResponse"];
export type UserStatus = Identity["UserStatus"];
export type RegisterRequest = Identity["RegisterRequest"];
export type Wallet = Ledger["WalletResponse"];
export type LedgerEntry = Ledger["LedgerEntryResponse"];
export type WalletLimit = Payment["LimitResponse"];
export type Transfer = Payment["TransferResponse"];
export type Recipient = Payment["RecipientResponse"];
export type RecentRecipient = Payment["RecentRecipientResponse"];
export type MoneyRequest = Payment["MoneyRequestResponse"];
export type Stats = Payment["StatsResponse"];
export type CurrencyStats = Payment["CurrencyStats"];
export type ExchangeQuote = Payment["QuoteResponse"];
export type Exchange = Payment["ExchangeResponse"];
export type PaymentRecord = Payment["PaymentResponse"];
export type Refund = Payment["RefundResponse"];
export type Transaction = Payment["TransactionResponse"];
export type AdminTransaction = Payment["AdminTransactionResponse"];
export type Merchant = Payment["MerchantResponse"];
export type Notification = Notifications["NotificationResponse"];
export type NotificationList = Notifications["NotificationListResponse"];
export type Announcement = Notifications["AnnouncementResponse"];
export type NewsItem = Notifications["NewsResponse"];
export type NewsList = Notifications["NewsListResponse"];
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

/** Signs in with a phone number or an email address, whichever was typed
 * (anything with an "@" is an email). identity-service normalizes the
 * phone, so any common way of writing it works. */
export async function login(identifier: string, password: string): Promise<void> {
  const value = identifier.trim();
  const credentials = value.includes("@") ? { email: value } : { phone: value };
  const tokens = await apiRequest<Identity["TokenResponse"]>("/api/v1/auth/login", {
    method: "POST",
    body: { ...credentials, password },
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

/** The same "phone or email" rule as login: anything with an "@" is an email. */
function accountIdentifier(identifier: string): { email: string } | { phone: string } {
  const value = identifier.trim();
  return value.includes("@") ? { email: value } : { phone: value };
}

/** Asks for a reset code to be emailed. Succeeds whether or not such an
 * account exists: the server never says which. */
export function requestPasswordReset(identifier: string): Promise<void> {
  return apiRequest("/api/v1/auth/password-reset/request", {
    method: "POST",
    body: accountIdentifier(identifier),
    authenticated: false,
  });
}

export function confirmPasswordReset(
  identifier: string,
  code: string,
  newPassword: string,
): Promise<void> {
  return apiRequest("/api/v1/auth/password-reset/confirm", {
    method: "POST",
    body: { ...accountIdentifier(identifier), code, new_password: newPassword },
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
/** Changes the fields given; a new email or phone needs `current_password`. */
export const updateProfile = (body: Identity["UpdateProfileRequest"]) =>
  apiRequest<CurrentUser>("/api/v1/users/me", { method: "PATCH", body });
export const listSessions = () => apiRequest<UserSession[]>("/api/v1/users/me/sessions");
export const revokeSession = (sessionId: string) =>
  apiRequest<void>(`/api/v1/users/me/sessions/${sessionId}`, { method: "DELETE" });
export const changePassword = (body: Identity["ChangePasswordRequest"]) =>
  apiRequest<void>("/api/v1/users/me/password", { method: "POST", body });

// --- wallets (ledger-service) ------------------------------------------

export const listWallets = () => apiRequest<Wallet[]>("/api/v1/wallets");
export const getWallet = (walletId: string) => apiRequest<Wallet>(`/api/v1/wallets/${walletId}`);
export const createWallet = (currency: string) =>
  apiRequest<Wallet>("/api/v1/wallets", { method: "POST", body: { currency } });
/** The owner's own label for a wallet; null or blank removes it. */
export const renameWallet = (walletId: string, name: string | null) =>
  apiRequest<Wallet>(`/api/v1/wallets/${walletId}`, { method: "PATCH", body: { name } });
export const makeWalletPrimary = (walletId: string) =>
  apiRequest<Wallet>(`/api/v1/wallets/${walletId}/primary`, { method: "POST" });
/** Blocked: money can still arrive, none can leave. */
export const setWalletBlocked = (walletId: string, blocked: boolean) =>
  apiRequest<Wallet>(`/api/v1/wallets/${walletId}/${blocked ? "block" : "unblock"}`, {
    method: "POST",
  });
export const getWalletLimit = (walletId: string) =>
  apiRequest<WalletLimit>(`/api/v1/limits/${walletId}`);
/** `dailyLimit` is a decimal string in the wallet's currency; null removes the limit. */
export const setWalletLimit = (walletId: string, dailyLimit: string | null) =>
  apiRequest<WalletLimit>(`/api/v1/limits/${walletId}`, {
    method: "PUT",
    body: { daily_limit: dailyLimit },
  });
export const listWalletEntries = (walletId: string, page: Page) =>
  apiRequest<LedgerEntry[]>(`/api/v1/wallets/${walletId}/entries`, { query: { ...page } });

// --- transfers, payments, history (payment-service) --------------------

export const createTransfer = (body: Payment["CreateTransferRequest"], idempotencyKey: string) =>
  apiRequest<Transfer>("/api/v1/transfers", { method: "POST", body, idempotencyKey });
/** Cards the customer has sent money to before, most recent first. */
export const listRecentRecipients = () =>
  apiRequest<RecentRecipient[]>("/api/v1/transfers/recipients");

/** Who a transfer to this card number (16 digits) would go to. */
export const findRecipient = (cardNumber: string) =>
  apiRequest<Recipient>("/api/v1/transfers/recipient", { query: { card_number: cardNumber } });
export const getTransfer = (transferId: string) =>
  apiRequest<Transfer>(`/api/v1/transfers/${transferId}`);

// Asking someone for money. Paying a request is a transfer, so it
// carries an Idempotency-Key like one.
export const listMoneyRequests = () => apiRequest<MoneyRequest[]>("/api/v1/money-requests");
export const createMoneyRequest = (body: Payment["CreateMoneyRequest"]) =>
  apiRequest<MoneyRequest>("/api/v1/money-requests", { method: "POST", body });
export const payMoneyRequest = (requestId: string, sourceWalletId: string, idempotencyKey: string) =>
  apiRequest<MoneyRequest>(`/api/v1/money-requests/${requestId}/pay`, {
    method: "POST",
    body: { source_wallet_id: sourceWalletId },
    idempotencyKey,
  });
export const declineMoneyRequest = (requestId: string) =>
  apiRequest<MoneyRequest>(`/api/v1/money-requests/${requestId}/decline`, { method: "POST" });
export const cancelMoneyRequest = (requestId: string) =>
  apiRequest<MoneyRequest>(`/api/v1/money-requests/${requestId}/cancel`, { method: "POST" });

// Exchanging between the customer's own wallets. A quote moves nothing;
// the exchange is refused (409) if it would give a different amount
// than the one the customer saw.
export const getExchangeQuote = (
  sourceWalletId: string,
  destinationWalletId: string,
  amount: string,
) =>
  apiRequest<ExchangeQuote>("/api/v1/exchanges/quote", {
    query: {
      source_wallet_id: sourceWalletId,
      destination_wallet_id: destinationWalletId,
      amount,
    },
  });
export const createExchange = (body: Payment["CreateExchangeRequest"], idempotencyKey: string) =>
  apiRequest<Exchange>("/api/v1/exchanges", { method: "POST", body, idempotencyKey });

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

// --- notifications (notification-service) ------------------------------

/** The newest notifications and how many of all of them are unread. */
export const listNotifications = () =>
  apiRequest<NotificationList>("/api/v1/notifications", { query: { limit: 20 } });
export const markNotificationsRead = () =>
  apiRequest<void>("/api/v1/notifications/read", { method: "POST" });

/** Banking news from public feeds, newest first, with the unread count. */
export const listNews = (limit = 20) =>
  apiRequest<NewsList>("/api/v1/news", { query: { limit } });
export const getNewsItem = (newsId: string) => apiRequest<NewsItem>(`/api/v1/news/${newsId}`);
export const markNewsRead = () => apiRequest<void>("/api/v1/news/read", { method: "POST" });

/** Money in and out per calendar month, per currency. */
export const getStats = (months: number) =>
  apiRequest<Stats>("/api/v1/transactions/stats", { query: { months } });

/** One operation as a PDF receipt. */
export const downloadReceipt = (transactionId: string) =>
  apiDownload(`/api/v1/transactions/${transactionId}/receipt.pdf`, "fincore-receipt.pdf");
/** The whole history as a CSV file for a spreadsheet. */
export const downloadStatement = () =>
  apiDownload("/api/v1/transactions/export.csv", "fincore-history.csv");

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

// --- assistant (assistant-service) -------------------------------------

export type ChatMessage = AssistantSchemas["schemas"]["ChatMessage"];

export const askAssistant = (messages: ChatMessage[]) =>
  apiRequest<AssistantSchemas["schemas"]["ChatResponse"]>("/api/v1/assistant/chat", {
    method: "POST",
    body: { messages },
  });

/** Messages from staff to every customer; they appear in each bell. */
export const adminListAnnouncements = () =>
  apiRequest<Announcement[]>("/api/v1/admin/announcements");
export const adminPublishAnnouncement = (body: Notifications["CreateAnnouncementRequest"]) =>
  apiRequest<Announcement>("/api/v1/admin/announcements", { method: "POST", body });
export const adminWithdrawAnnouncement = (announcementId: string) =>
  apiRequest<void>(`/api/v1/admin/announcements/${announcementId}`, { method: "DELETE" });
