// Generated from contracts/openapi/payment-service.json by scripts/generate-api-types.mjs.
// Do not edit by hand: run `npm run gen:api`.

export interface paths {
    "/api/v1/admin/reviews": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Reviews
         * @description Transfers and payments whose fraud check returned REVIEW and that
         *     nobody has decided on yet, oldest first. A payment left here past
         *     `payment_review_ttl_seconds` is expired by the expiration worker and
         *     drops out of the queue.
         */
        get: operations["list_reviews_api_v1_admin_reviews_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/reviews/{operation_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decide Review
         * @description APPROVE runs the rest of the saga synchronously, so the response
         *     already shows where it landed (COMPLETED/SUCCESS, FAILED, or
         *     PROCESSING on an unknown ledger outcome); REJECT fails it.
         */
        post: operations["decide_review_api_v1_admin_reviews__operation_id__post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/transactions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List All Transactions
         * @description Every user's transfers and payments, newest first. `status` is
         *     matched against each type's own state machine, so e.g. SUCCESS only
         *     ever matches payments and COMPLETED only transfers. Merged in Python
         *     the same way the user-facing `GET /api/v1/transactions` is.
         */
        get: operations["list_all_transactions_api_v1_admin_transactions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/merchants": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List My Merchants */
        get: operations["list_my_merchants_api_v1_merchants_get"];
        put?: never;
        /** Create Merchant */
        post: operations["create_merchant_api_v1_merchants_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/merchants/{merchant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Merchant */
        get: operations["get_merchant_api_v1_merchants__merchant_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/merchants/{merchant_id}/payments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Merchant Payments
         * @description Payments *received* by one of the caller's merchants, newest
         *     first. The merchant side's counterpart to `GET /api/v1/payments/{id}`
         *     (which only the payer can read), and how an owner finds the payment
         *     id that `POST /api/v1/payments/{id}/refunds` needs.
         */
        get: operations["list_merchant_payments_api_v1_merchants__merchant_id__payments_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/money-requests": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Money Requests
         * @description Requests the caller made (OUTGOING) and requests made to the
         *     caller (INCOMING), newest first.
         */
        get: operations["list_money_requests_api_v1_money_requests_get"];
        put?: never;
        /**
         * Create Money Request
         * @description Asks the owner of a card to send the caller money. Nothing moves
         *     until that person pays; they are notified and can pay or decline.
         *     The card must belong to someone else and be in the same currency as
         *     the wallet the money should arrive in. A customer may have 20
         *     unanswered requests, 3 to any one person.
         */
        post: operations["create_money_request_api_v1_money_requests_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/money-requests/{request_id}/cancel": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Cancel Money Request
         * @description The requester withdraws a request nobody has answered yet.
         */
        post: operations["cancel_money_request_api_v1_money_requests__request_id__cancel_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/money-requests/{request_id}/decline": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Decline Money Request
         * @description The person asked says no. The requester is notified.
         */
        post: operations["decline_money_request_api_v1_money_requests__request_id__decline_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/money-requests/{request_id}/pay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Pay Money Request
         * @description Pays a request made to the caller, as an ordinary transfer from
         *     `source_wallet_id` (fraud check, ledger posting and all). Needs an
         *     Idempotency-Key like any money movement. The result's `status` says
         *     how it went: PAID, PROCESSING (in progress or waiting for review),
         *     or PENDING again with `last_failure` if the transfer failed. A
         *     request can be paid once: a second payment gets 409.
         */
        post: operations["pay_money_request_api_v1_money_requests__request_id__pay_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/payments": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Post Payment
         * @description Spec Section 11's flow, in the same order transfers use: authorize
         *     -> validate -> idempotency check -> create + run the saga.
         */
        post: operations["post_payment_api_v1_payments_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/payments/{payment_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Payment */
        get: operations["get_payment_api_v1_payments__payment_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/payments/{payment_id}/refunds": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Post Refund
         * @description Refunds are merchant-initiated (spec Section 11 doesn't say so
         *     explicitly, but a refund is a merchant deciding to give money back —
         *     the same real-world shape as every payment platform's own refund
         *     API), so the caller must own the merchant the payment was made to,
         *     not be the payer.
         */
        post: operations["post_refund_api_v1_payments__payment_id__refunds_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transactions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Transactions
         * @description The caller's own business-operation history (spec Section 20),
         *     newest first across *both* Transfer and Payment: everything they
         *     started (`direction: OUT`) and every transfer that reached them
         *     (`direction: IN`). A merchant's received payments are on the
         *     merchant's own endpoints, not here.
         *
         *     Merged and sorted in Python rather than a single SQL query, since
         *     Transfer and Payment are two separate tables (each operation type
         *     gets its own table, spec Section 7.1) — a reasonable v1 approach at
         *     this scale; a UNION query would be the next step if this list ever
         *     needs to paginate over a serious volume of rows.
         */
        get: operations["list_transactions_api_v1_transactions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transactions/{transaction_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Transaction */
        get: operations["get_transaction_api_v1_transactions__transaction_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transfers": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Post Transfer
         * @description Spec Section 10.1's flow, in the order the spec states it:
         *     authorize -> validate -> idempotency check -> create + run the saga.
         */
        post: operations["post_transfer_api_v1_transfers_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transfers/recipient": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Recipient
         * @description Who would receive a transfer sent to this card number: the wallet
         *     to send to, its currency, and the owner's first name and last
         *     initial. Signed-in customers only, and rate-limited at the gateway,
         *     since it turns a card number into a name.
         */
        get: operations["get_recipient_api_v1_transfers_recipient_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transfers/recipients": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Recent Recipients
         * @description The cards the caller has sent money to, most recent first, one
         *     entry per card - for choosing the same person again without typing
         *     16 digits. Only transfers that completed, and whose card is known.
         *     The name is the one recorded when the money was last sent; the Send
         *     page still looks the card up again before anything is sent.
         */
        get: operations["list_recent_recipients_api_v1_transfers_recipients_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/transfers/{transfer_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Transfer */
        get: operations["get_transfer_api_v1_transfers__transfer_id__get"];
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
    "/internal/v1/merchants/{merchant_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get Merchant
         * @description Lets webhook-service verify a merchant's owner and status before
         *     registering a webhook endpoint for it, reusing this service's own
         *     merchants table instead of webhook-service duplicating it.
         */
        get: operations["get_merchant_internal_v1_merchants__merchant_id__get"];
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
         * @description Readiness: can the service actually serve traffic (spec Section
         *     24: DB and Kafka connectivity, not just liveness).
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
         * AdminTransactionResponse
         * @description TransactionResponse plus what staff need and a user's own history
         *     doesn't show: whose operation it is, where the money was headed, and
         *     the fraud/review trail (the admin panel, ADR-0005).
         */
        AdminTransactionResponse: {
            /** Amount Minor */
            amount_minor: number;
            /** Completed At */
            completed_at: string | null;
            /**
             * Counterparty Id
             * Format: uuid
             */
            counterparty_id: string;
            /** Counterparty Name */
            counterparty_name: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Description */
            description: string | null;
            direction: components["schemas"]["TransactionDirection"];
            /** Failure Reason */
            failure_reason: string | null;
            fraud_decision: components["schemas"]["FraudDecision"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Initiator User Id
             * Format: uuid
             */
            initiator_user_id: string;
            /** Reference */
            reference: string;
            /** Reviewed At */
            reviewed_at: string | null;
            /** Reviewed By User Id */
            reviewed_by_user_id: string | null;
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
            /** Status */
            status: string;
            type: components["schemas"]["TransactionType"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** CreateMerchantRequest */
        CreateMerchantRequest: {
            /** Name */
            name: string;
        };
        /** CreateMoneyRequest */
        CreateMoneyRequest: {
            /** Amount */
            amount: string;
            /** From Card Number */
            from_card_number: string;
            /** Note */
            note?: string | null;
            /**
             * Wallet Id
             * Format: uuid
             */
            wallet_id: string;
        };
        /** CreatePaymentRequest */
        CreatePaymentRequest: {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Description */
            description?: string | null;
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
        };
        /** CreateRefundRequest */
        CreateRefundRequest: {
            /** Amount */
            amount: string;
            /** Reason */
            reason?: string | null;
        };
        /** CreateTransferRequest */
        CreateTransferRequest: {
            /** Amount */
            amount: string;
            /** Currency */
            currency: string;
            /** Description */
            description?: string | null;
            /**
             * Destination Wallet Id
             * Format: uuid
             */
            destination_wallet_id: string;
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
        };
        /**
         * FraudDecision
         * @enum {string}
         */
        FraudDecision: "ALLOW" | "REVIEW" | "BLOCK";
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * MerchantOwnershipResponse
         * @description Lets a caller (webhook-service, registering a webhook endpoint)
         *     verify who owns a merchant and whether it's active, without needing
         *     its own copy of the merchants table — same reasoning as
         *     ledger-service's SystemAccountResponse.
         */
        MerchantOwnershipResponse: {
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
            status: components["schemas"]["MerchantStatus"];
        };
        /** MerchantResponse */
        MerchantResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /**
             * Owner User Id
             * Format: uuid
             */
            owner_user_id: string;
            status: components["schemas"]["MerchantStatus"];
        };
        /**
         * MerchantStatus
         * @enum {string}
         */
        MerchantStatus: "ACTIVE" | "SUSPENDED";
        /** MoneyRequestResponse */
        MoneyRequestResponse: {
            /** Amount Minor */
            amount_minor: number;
            /** Counterparty Name */
            counterparty_name: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            direction: components["schemas"]["RequestDirection"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Failure */
            last_failure: string | null;
            /** Note */
            note: string | null;
            /** Reference */
            reference: string;
            status: components["schemas"]["RequestState"];
            /** Transfer Id */
            transfer_id: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PayMoneyRequest */
        PayMoneyRequest: {
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
        };
        /** PaymentResponse */
        PaymentResponse: {
            /** Amount Minor */
            amount_minor: number;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Description */
            description: string | null;
            /** Failure Reason */
            failure_reason: string | null;
            fraud_decision: components["schemas"]["FraudDecision"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /** Reference */
            reference: string;
            /** Refunded Amount Minor */
            refunded_amount_minor: number;
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
            status: components["schemas"]["PaymentStatus"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * PaymentStatus
         * @description State machine (spec Section 11), enforced the same way Transfer's
         *     is: every transition is an atomic `UPDATE ... WHERE status =
         *     :expected` (`PaymentRepository.transition_status`), never assumed
         *     from in-memory state.
         *
         *     CREATED             -> PROCESSING | FAILED | EXPIRED
         *     PROCESSING          -> SUCCESS | FAILED
         *     SUCCESS             -> REFUNDED (full) | PARTIALLY_REFUNDED
         *     PARTIALLY_REFUNDED  -> REFUNDED
         *     FAILED, EXPIRED, REFUNDED -> terminal
         * @enum {string}
         */
        PaymentStatus: "CREATED" | "PROCESSING" | "SUCCESS" | "FAILED" | "EXPIRED" | "PARTIALLY_REFUNDED" | "REFUNDED";
        /**
         * RecentRecipientResponse
         * @description Someone the caller has sent money to before.
         */
        RecentRecipientResponse: {
            /** Card Number */
            card_number: string;
            /** Currency */
            currency: string;
            /** Display Name */
            display_name: string | null;
            /**
             * Last Sent At
             * Format: date-time
             */
            last_sent_at: string;
        };
        /**
         * RecipientResponse
         * @description Who a card number belongs to, for the sender to confirm.
         */
        RecipientResponse: {
            /** Currency */
            currency: string;
            /** Display Name */
            display_name: string;
            /** Own */
            own: boolean;
            /**
             * Wallet Id
             * Format: uuid
             */
            wallet_id: string;
        };
        /** RefundResponse */
        RefundResponse: {
            /** Amount Minor */
            amount_minor: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Failure Reason */
            failure_reason: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Payment Id
             * Format: uuid
             */
            payment_id: string;
            /** Reason */
            reason: string | null;
            status: components["schemas"]["RefundStatus"];
        };
        /**
         * RefundStatus
         * @description A minimal state machine — not the full Payment/Transfer saga
         *     treatment, but the same underlying reason those have one: the
         *     ledger posting a refund makes is itself only reachable over the
         *     network, so an unknown outcome (timeout, 5xx) has to leave *some*
         *     durable, retriable state rather than nothing at all — otherwise a
         *     retried refund request would mint a fresh id each time and risk a
         *     duplicate posting instead of safely retrying the same one.
         * @enum {string}
         */
        RefundStatus: "PENDING" | "COMPLETED" | "FAILED";
        /**
         * RequestDirection
         * @enum {string}
         */
        RequestDirection: "INCOMING" | "OUTGOING";
        /**
         * RequestState
         * @description What a customer sees.
         * @enum {string}
         */
        RequestState: "PENDING" | "PROCESSING" | "PAID" | "DECLINED" | "CANCELLED";
        /**
         * ReviewDecision
         * @enum {string}
         */
        ReviewDecision: "APPROVE" | "REJECT";
        /** ReviewDecisionRequest */
        ReviewDecisionRequest: {
            decision: components["schemas"]["ReviewDecision"];
        };
        /**
         * TransactionDirection
         * @enum {string}
         */
        TransactionDirection: "OUT" | "IN";
        /**
         * TransactionResponse
         * @description A type-erased view over any business operation (Transfer or
         *     Payment) for the user-facing history endpoints
         *     (`GET /api/v1/transactions[/{id}]`) — distinct from
         *     `TransferResponse`/`PaymentResponse`, which are type-specific and
         *     used by their own APIs.
         */
        TransactionResponse: {
            /** Amount Minor */
            amount_minor: number;
            /** Completed At */
            completed_at: string | null;
            /** Counterparty Name */
            counterparty_name: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Description */
            description: string | null;
            direction: components["schemas"]["TransactionDirection"];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reference */
            reference: string;
            /** Status */
            status: string;
            type: components["schemas"]["TransactionType"];
        };
        /**
         * TransactionType
         * @description The kind of business operation a transaction summarizes (spec
         *     Section 20's API map).
         * @enum {string}
         */
        TransactionType: "TRANSFER" | "PAYMENT";
        /** TransferResponse */
        TransferResponse: {
            /** Amount Minor */
            amount_minor: number;
            /** Completed At */
            completed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /** Description */
            description: string | null;
            /**
             * Destination Wallet Id
             * Format: uuid
             */
            destination_wallet_id: string;
            /** Failure Reason */
            failure_reason: string | null;
            fraud_decision: components["schemas"]["FraudDecision"] | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Reference */
            reference: string;
            /**
             * Source Wallet Id
             * Format: uuid
             */
            source_wallet_id: string;
            status: components["schemas"]["TransferStatus"];
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /**
         * TransferStatus
         * @description State machine (spec Section 7.3). Allowed transitions:
         *
         *     PENDING     -> PROCESSING | CANCELLED | FAILED
         *     PROCESSING  -> COMPLETED  | FAILED
         *     COMPLETED   -> (terminal)
         *     FAILED      -> (terminal)
         *     CANCELLED   -> (terminal)
         *
         *     Enforced in app/services/transfers.py, and guarded at the database
         *     update with `WHERE status = :expected` — never assumed from
         *     in-memory state alone.
         * @enum {string}
         */
        TransferStatus: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED" | "CANCELLED";
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_reviews_api_v1_admin_reviews_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["AdminTransactionResponse"][];
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
    decide_review_api_v1_admin_reviews__operation_id__post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                operation_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ReviewDecisionRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminTransactionResponse"];
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
    list_all_transactions_api_v1_admin_transactions_get: {
        parameters: {
            query?: {
                type?: components["schemas"]["TransactionType"] | null;
                status?: string | null;
                user_id?: string | null;
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["AdminTransactionResponse"][];
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
    list_my_merchants_api_v1_merchants_get: {
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
                    "application/json": components["schemas"]["MerchantResponse"][];
                };
            };
        };
    };
    create_merchant_api_v1_merchants_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateMerchantRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MerchantResponse"];
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
    get_merchant_api_v1_merchants__merchant_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                merchant_id: string;
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
                    "application/json": components["schemas"]["MerchantResponse"];
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
    list_merchant_payments_api_v1_merchants__merchant_id__payments_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                merchant_id: string;
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
                    "application/json": components["schemas"]["PaymentResponse"][];
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
    list_money_requests_api_v1_money_requests_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["MoneyRequestResponse"][];
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
    create_money_request_api_v1_money_requests_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateMoneyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MoneyRequestResponse"];
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
    cancel_money_request_api_v1_money_requests__request_id__cancel_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
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
                    "application/json": components["schemas"]["MoneyRequestResponse"];
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
    decline_money_request_api_v1_money_requests__request_id__decline_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                request_id: string;
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
                    "application/json": components["schemas"]["MoneyRequestResponse"];
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
    pay_money_request_api_v1_money_requests__request_id__pay_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                request_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PayMoneyRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MoneyRequestResponse"];
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
    post_payment_api_v1_payments_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreatePaymentRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["PaymentResponse"];
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
    get_payment_api_v1_payments__payment_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                payment_id: string;
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
                    "application/json": components["schemas"]["PaymentResponse"];
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
    post_refund_api_v1_payments__payment_id__refunds_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path: {
                payment_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateRefundRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["RefundResponse"];
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
    list_transactions_api_v1_transactions_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
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
                    "application/json": components["schemas"]["TransactionResponse"][];
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
    get_transaction_api_v1_transactions__transaction_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transaction_id: string;
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
                    "application/json": components["schemas"]["TransactionResponse"];
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
    post_transfer_api_v1_transfers_post: {
        parameters: {
            query?: never;
            header: {
                "Idempotency-Key": string;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateTransferRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TransferResponse"];
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
    get_recipient_api_v1_transfers_recipient_get: {
        parameters: {
            query: {
                card_number: string;
            };
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
                    "application/json": components["schemas"]["RecipientResponse"];
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
    list_recent_recipients_api_v1_transfers_recipients_get: {
        parameters: {
            query?: {
                limit?: number;
            };
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
                    "application/json": components["schemas"]["RecentRecipientResponse"][];
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
    get_transfer_api_v1_transfers__transfer_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                transfer_id: string;
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
                    "application/json": components["schemas"]["TransferResponse"];
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
    get_merchant_internal_v1_merchants__merchant_id__get: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path: {
                merchant_id: string;
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
                    "application/json": components["schemas"]["MerchantOwnershipResponse"];
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
