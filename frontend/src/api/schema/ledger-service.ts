// Generated from contracts/openapi/ledger-service.json by scripts/generate-api-types.mjs.
// Do not edit by hand: run `npm run gen:api`.

export interface paths {
    "/api/v1/wallets": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List My Wallets */
        get: operations["list_my_wallets_api_v1_wallets_get"];
        put?: never;
        /** Open Wallet */
        post: operations["open_wallet_api_v1_wallets_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/wallets/{wallet_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Wallet */
        get: operations["get_wallet_api_v1_wallets__wallet_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/wallets/{wallet_id}/entries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Wallet Entries */
        get: operations["list_wallet_entries_api_v1_wallets__wallet_id__entries_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/health": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Health
         * @description Liveness: is the process up. No dependency checks.
         */
        get: operations["health_health_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/accounts/system": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get System Account
         * @description Lets a caller (payment-service, building a refund posting) look
         *     up the id of a pooled system account (e.g. MERCHANT_SETTLEMENT for
         *     a currency) without needing to know or store it itself — the same
         *     reason `capture_hold` looks this account up internally rather than
         *     requiring the caller to pass its id (app/services/holds.py).
         */
        get: operations["get_system_account_internal_v1_accounts_system_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/accounts/wallet-by-card": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Wallet By Card
         * @description The wallet a card number belongs to, whatever its status: whether
         *     a frozen or closed wallet may receive money is the caller's rule.
         */
        get: operations["get_wallet_by_card_internal_v1_accounts_wallet_by_card_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/accounts/wallets/{wallet_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Wallet Owner
         * @description Whose wallet this is - for payment-service, which records the
         *     recipient of a transfer so they can be told about it.
         */
        get: operations["get_wallet_owner_internal_v1_accounts_wallets__wallet_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/holds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Hold */
        post: operations["post_hold_internal_v1_holds_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/holds/{hold_id}/capture": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Capture */
        post: operations["post_capture_internal_v1_holds__hold_id__capture_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/holds/{hold_id}/release": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Release */
        post: operations["post_release_internal_v1_holds__hold_id__release_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/postings": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Post Posting */
        post: operations["post_posting_internal_v1_postings_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/postings/{source_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Posting
         * @description Lets a caller (payment-service's recovery worker) resolve the
         *     outcome of a posting call whose original response was lost to a
         *     timeout, per the transfer saga's "unknown outcome" branch (spec
         *     Section 10.1, ADR-0003).
         */
        get: operations["get_posting_internal_v1_postings__source_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/reconciliation": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Reconciliation Report
         * @description Triggers one reconciliation pass on demand (spec Section 8.4) — for
         *     ops/debugging between the background loop's own scheduled runs
         *     (app/main.py). Does not auto-correct anything it finds (ADR-0002).
         */
        get: operations["get_reconciliation_report_internal_v1_reconciliation_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/ready": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Ready
         * @description Readiness: can the service actually serve traffic (DB reachable).
         */
        get: operations["ready_ready_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
}
export type webhooks = Record<string, never>;
export interface components {
    schemas: {
        /**
         * AccountKind
         * @description Account kinds and their normal balance side (ADR-0002):
         *
         *     USER_WALLET / MERCHANT_SETTLEMENT / FEES  -> CREDIT-normal (liability/revenue)
         *     EXTERNAL_FUNDING                          -> DEBIT-normal  (clearing)
         *     EXTERNAL_PAYOUT                           -> CREDIT-normal (clearing)
         *     SUSPENSE                                  -> no normal side; must net to zero
         * @enum {string}
         */
        AccountKind: "USER_WALLET" | "EXTERNAL_FUNDING" | "EXTERNAL_PAYOUT" | "MERCHANT_SETTLEMENT" | "FEES" | "SUSPENSE";
        /**
         * AccountStatus
         * @enum {string}
         */
        AccountStatus: "ACTIVE" | "FROZEN" | "CLOSED";
        /** CaptureHoldRequest */
        CaptureHoldRequest: {
            /** Amount Minor */
            amount_minor: number;
            /** Source Id */
            source_id: string;
            /** Source Service */
            source_service: string;
        };
        /** CreateHoldRequest */
        CreateHoldRequest: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount Minor */
            amount_minor: number;
            /** Currency */
            currency: string;
            /** Source Id */
            source_id: string;
            /** Source Service */
            source_service: string;
            /**
             * Ttl Seconds
             * @default 900
             */
            ttl_seconds: number;
        };
        /** CreatePostingRequest */
        CreatePostingRequest: {
            /** Currency */
            currency: string;
            /** Entries */
            entries: components["schemas"]["EntryRequest"][];
            /** Source Id */
            source_id: string;
            /** Source Service */
            source_service: string;
            type: components["schemas"]["PostingType"];
        };
        /**
         * EntryDirection
         * @enum {string}
         */
        EntryDirection: "DEBIT" | "CREDIT";
        /** EntryRequest */
        EntryRequest: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount Minor */
            amount_minor: number;
            direction: components["schemas"]["EntryDirection"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** HoldResponse */
        HoldResponse: {
            /**
             * Account Id
             * Format: uuid
             */
            account_id: string;
            /** Amount Minor */
            amount_minor: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /**
             * Expires At
             * Format: date-time
             */
            expires_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Resolved At */
            resolved_at: string | null;
            status: components["schemas"]["HoldStatus"];
        };
        /**
         * HoldStatus
         * @enum {string}
         */
        HoldStatus: "ACTIVE" | "CAPTURED" | "RELEASED" | "EXPIRED";
        /** LedgerEntryResponse */
        LedgerEntryResponse: {
            /** Amount Minor */
            amount_minor: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            direction: components["schemas"]["EntryDirection"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Posting Id
             * Format: uuid
             */
            posting_id: string;
        };
        /** PostingResponse */
        PostingResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Source Id */
            source_id: string;
            /** Source Service */
            source_service: string;
            type: components["schemas"]["PostingType"];
        };
        /**
         * PostingType
         * @description Mirrors the business operation types (spec Section 7.1). A posting
         *     always exists *because* payment-service asked for one of these; the
         *     type is recorded so `(source_service, source_id, type)` can be a
         *     precise idempotency key — the same transfer could in principle
         *     produce more than one posting type over its life (e.g. a payment's
         *     capture vs. its later refund).
         * @enum {string}
         */
        PostingType: "TRANSFER" | "PAYMENT" | "DEPOSIT" | "WITHDRAWAL" | "REFUND";
        /** ReconciliationReportResponse */
        ReconciliationReportResponse: {
            /** Balance Mismatches */
            balance_mismatches: string[];
            /** Duplicate Source Postings */
            duplicate_source_postings: [
                string,
                string,
                string
            ][];
            /** Is Clean */
            is_clean: boolean;
            /** Negative Available Wallets */
            negative_available_wallets: string[];
            /** Unbalanced Postings */
            unbalanced_postings: string[];
        };
        /** SystemAccountResponse */
        SystemAccountResponse: {
            /** Currency */
            currency: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            kind: components["schemas"]["AccountKind"];
        };
        /** ValidationError */
        ValidationError: {
            /** Context */
            ctx?: Record<string, never>;
            /** Input */
            input?: unknown;
            /** Location */
            loc: (string | number)[];
            /** Message */
            msg: string;
            /** Error Type */
            type: string;
        };
        /**
         * WalletByCardResponse
         * @description Who a card number belongs to - for payment-service, which shows
         *     the sender a recipient before a transfer. Never exposed publicly:
         *     it carries the owner's user id.
         */
        WalletByCardResponse: {
            /** Card Number */
            card_number: string;
            /** Currency */
            currency: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Owner User Id
             * Format: uuid
             */
            owner_user_id: string;
            status: components["schemas"]["AccountStatus"];
        };
        /** WalletCreateRequest */
        WalletCreateRequest: {
            /** Currency */
            currency: string;
        };
        /** WalletResponse */
        WalletResponse: {
            /** Balance Minor */
            balance_minor: number;
            /** Card Number */
            card_number: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Held Minor */
            held_minor: number;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            status: components["schemas"]["AccountStatus"];
        };
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_my_wallets_api_v1_wallets_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WalletResponse"][];
                };
            };
        };
    };
    open_wallet_api_v1_wallets_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["WalletCreateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WalletResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_wallet_api_v1_wallets__wallet_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                wallet_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WalletResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    list_wallet_entries_api_v1_wallets__wallet_id__entries_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                wallet_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["LedgerEntryResponse"][];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    health_health_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
    get_system_account_internal_v1_accounts_system_get: {
        parameters: {
            query: {
                kind: components["schemas"]["AccountKind"];
                currency: string;
            };
            header: {
                "x-internal-token": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["SystemAccountResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_wallet_by_card_internal_v1_accounts_wallet_by_card_get: {
        parameters: {
            query: {
                card_number: string;
            };
            header: {
                "x-internal-token": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WalletByCardResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_wallet_owner_internal_v1_accounts_wallets__wallet_id__get: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path: {
                wallet_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WalletByCardResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_hold_internal_v1_holds_post: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateHoldRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_capture_internal_v1_holds__hold_id__capture_post: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path: {
                hold_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CaptureHoldRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_release_internal_v1_holds__hold_id__release_post: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path: {
                hold_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HoldResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    post_posting_internal_v1_postings_post: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePostingRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_posting_internal_v1_postings__source_id__get: {
        parameters: {
            query: {
                source_service: string;
                type: components["schemas"]["PostingType"];
            };
            header: {
                "x-internal-token": string;
            };
            path: {
                source_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PostingResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    get_reconciliation_report_internal_v1_reconciliation_get: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ReconciliationReportResponse"];
                };
            };
            /** @description Validation Error */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["HTTPValidationError"];
                };
            };
        };
    };
    ready_ready_get: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": {
                        [key: string]: string;
                    };
                };
            };
        };
    };
}
