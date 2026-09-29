// Generated from contracts/openapi/webhook-service.json by scripts/generate-api-types.mjs.
// Do not edit by hand: run `npm run gen:api`.

export interface paths {
    "/api/v1/admin/webhooks/endpoints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Endpoints */
        get: operations["list_endpoints_api_v1_admin_webhooks_endpoints_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/webhooks/endpoints/{endpoint_id}/deliveries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Endpoint Deliveries */
        get: operations["list_endpoint_deliveries_api_v1_admin_webhooks_endpoints__endpoint_id__deliveries_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/webhooks/endpoints/{endpoint_id}/disable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Disable Endpoint */
        post: operations["disable_endpoint_api_v1_admin_webhooks_endpoints__endpoint_id__disable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/webhooks/endpoints/{endpoint_id}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Endpoint */
        post: operations["enable_endpoint_api_v1_admin_webhooks_endpoints__endpoint_id__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/webhooks/endpoints": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List My Endpoints */
        get: operations["list_my_endpoints_api_v1_webhooks_endpoints_get"];
        put?: never;
        /** Create Endpoint */
        post: operations["create_endpoint_api_v1_webhooks_endpoints_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/webhooks/endpoints/{endpoint_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Endpoint */
        get: operations["get_endpoint_api_v1_webhooks_endpoints__endpoint_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/webhooks/endpoints/{endpoint_id}/deliveries": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Deliveries
         * @description Delivery history (spec Section 17: "every attempt with status
         *     code and latency") — each delivery's own attempts embedded, so a
         *     merchant can see the full retry sequence for one event without a
         *     second call per delivery.
         */
        get: operations["list_deliveries_api_v1_webhooks_endpoints__endpoint_id__deliveries_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/webhooks/endpoints/{endpoint_id}/enable": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Enable Endpoint */
        post: operations["enable_endpoint_api_v1_webhooks_endpoints__endpoint_id__enable_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/webhooks/endpoints/{endpoint_id}/rotate-secret": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Rotate Secret */
        post: operations["rotate_secret_api_v1_webhooks_endpoints__endpoint_id__rotate_secret_post"];
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
         * AdminWebhookEndpointResponse
         * @description Staff view: adds who owns the endpoint. Still never the secret —
         *     not even an admin can read a merchant's signing key back.
         */
        AdminWebhookEndpointResponse: {
            /** Consecutive Failures */
            consecutive_failures: number;
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
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /**
             * Owner User Id
             * Format: uuid
             */
            owner_user_id: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Url */
            url: string;
        };
        /** CreateWebhookEndpointRequest */
        CreateWebhookEndpointRequest: {
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /** Url */
            url: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
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
        /** WebhookAttemptResponse */
        WebhookAttemptResponse: {
            /** Attempt Number */
            attempt_number: number;
            /**
             * Attempted At
             * Format: date-time
             */
            attempted_at: string;
            /** Error */
            error: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Latency Ms */
            latency_ms: number | null;
            /** Status Code */
            status_code: number | null;
        };
        /** WebhookDeliveryResponse */
        WebhookDeliveryResponse: {
            /**
             * Attempt History
             * @default []
             */
            attempt_history: components["schemas"]["WebhookAttemptResponse"][];
            /** Attempts */
            attempts: number;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Event Id
             * Format: uuid
             */
            event_id: string;
            /** Event Type */
            event_type: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Error */
            last_error: string | null;
            /** Status */
            status: string;
        };
        /**
         * WebhookEndpointResponse
         * @description Never includes `secret` — a plain GET/list must not be able to
         *     read back the signing key, only see that an endpoint exists and
         *     what state it's in.
         */
        WebhookEndpointResponse: {
            /** Consecutive Failures */
            consecutive_failures: number;
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
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Url */
            url: string;
        };
        /**
         * WebhookEndpointStatus
         * @enum {string}
         */
        WebhookEndpointStatus: "ACTIVE" | "DISABLED";
        /**
         * WebhookEndpointWithSecretResponse
         * @description Returned only once, at creation and at rotation time (spec
         *     Section 17: "per-endpoint secrets, stored securely, rotatable") —
         *     the caller must save it then, since no later call ever returns it
         *     again.
         */
        WebhookEndpointWithSecretResponse: {
            /** Consecutive Failures */
            consecutive_failures: number;
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
            /**
             * Merchant Id
             * Format: uuid
             */
            merchant_id: string;
            /** Secret */
            secret: string;
            /** Status */
            status: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Url */
            url: string;
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
    list_endpoints_api_v1_admin_webhooks_endpoints_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["WebhookEndpointStatus"] | null;
                merchant_id?: string | null;
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
                    "application/json": components["schemas"]["AdminWebhookEndpointResponse"][];
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
    list_endpoint_deliveries_api_v1_admin_webhooks_endpoints__endpoint_id__deliveries_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["WebhookDeliveryResponse"][];
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
    disable_endpoint_api_v1_admin_webhooks_endpoints__endpoint_id__disable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["AdminWebhookEndpointResponse"];
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
    enable_endpoint_api_v1_admin_webhooks_endpoints__endpoint_id__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["AdminWebhookEndpointResponse"];
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
    list_my_endpoints_api_v1_webhooks_endpoints_get: {
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
                    "application/json": components["schemas"]["WebhookEndpointResponse"][];
                };
            };
        };
    };
    create_endpoint_api_v1_webhooks_endpoints_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateWebhookEndpointRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["WebhookEndpointWithSecretResponse"];
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
    get_endpoint_api_v1_webhooks_endpoints__endpoint_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["WebhookEndpointResponse"];
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
    list_deliveries_api_v1_webhooks_endpoints__endpoint_id__deliveries_get: {
        parameters: {
            query?: {
                limit?: number;
                offset?: number;
            };
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["WebhookDeliveryResponse"][];
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
    enable_endpoint_api_v1_webhooks_endpoints__endpoint_id__enable_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["WebhookEndpointResponse"];
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
    rotate_secret_api_v1_webhooks_endpoints__endpoint_id__rotate_secret_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                endpoint_id: string;
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
                    "application/json": components["schemas"]["WebhookEndpointWithSecretResponse"];
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
