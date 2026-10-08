// Generated from contracts/openapi/notification-service.json by scripts/generate-api-types.mjs.
// Do not edit by hand: run `npm run gen:api`.

export interface paths {
    "/api/v1/admin/announcements": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Announcements
         * @description Published announcements, newest first. SUPPORT and ADMIN.
         */
        get: operations["list_announcements_api_v1_admin_announcements_get"];
        put?: never;
        /**
         * Publish Announcement
         * @description Publishes a message to every customer at once. ADMIN only. Shown
         *     as plain text: no markup or links are interpreted.
         */
        post: operations["publish_announcement_api_v1_admin_announcements_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/announcements/{announcement_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        post?: never;
        /**
         * Withdraw Announcement
         * @description Withdraws an announcement: it disappears from every bell. ADMIN only.
         */
        delete: operations["withdraw_announcement_api_v1_admin_announcements__announcement_id__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List Threads
         * @description Every customer's conversation: open ones first, then by latest
         *     message. SUPPORT and ADMIN.
         */
        get: operations["list_threads_api_v1_admin_support_threads_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get Thread */
        get: operations["get_thread_api_v1_admin_support_threads__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads/{user_id}/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Reply
         * @description Replies to a customer who has written; they are told in their
         *     bell. A customer who never wrote can't be written to from here.
         */
        post: operations["reply_api_v1_admin_support_threads__user_id__messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads/{user_id}/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark Thread Read
         * @description A staff member has opened the conversation. Idempotent.
         */
        post: operations["mark_thread_read_api_v1_admin_support_threads__user_id__read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads/{user_id}/reopen": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Reopen Thread */
        post: operations["reopen_thread_api_v1_admin_support_threads__user_id__reopen_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/support/threads/{user_id}/resolve": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Resolve Thread
         * @description Nothing left to answer. The customer writing again reopens it.
         */
        post: operations["resolve_thread_api_v1_admin_support_threads__user_id__resolve_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/news": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List News
         * @description Banking and finance news from public feeds, newest first, and how
         *     many arrived since the caller last opened the news.
         */
        get: operations["list_news_api_v1_news_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/news/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark News Read
         * @description Everything fetched so far counts as seen by the caller. Idempotent.
         */
        post: operations["mark_news_read_api_v1_news_read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/news/{news_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get News Item */
        get: operations["get_news_item_api_v1_news__news_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List My Notifications
         * @description The caller's own notifications together with FinCore's
         *     announcements to everyone, newest first, and how many of all of
         *     them are unread.
         *
         *     The two are merged here rather than in SQL: they live in different
         *     tables with different read tracking (per notification, and one
         *     "last looked" moment per customer for announcements), and both are
         *     read newest-first up to the end of the requested page.
         */
        get: operations["list_my_notifications_api_v1_notifications_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/notifications/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark My Notifications Read
         * @description Marks every unread notification of the caller read, and every
         *     announcement so far seen (opening the bell). Idempotent.
         */
        post: operations["mark_my_notifications_read_api_v1_notifications_read_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/messages": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get My Conversation
         * @description The caller's conversation with staff, oldest message first.
         */
        get: operations["get_my_conversation_api_v1_support_messages_get"];
        put?: never;
        /**
         * Write To Support
         * @description Writes to staff. At most 20 messages in ten minutes.
         */
        post: operations["write_to_support_api_v1_support_messages_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/support/read": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Mark Replies Read
         * @description The customer has opened the conversation. Idempotent.
         */
        post: operations["mark_replies_read_api_v1_support_read_post"];
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
    "/internal/v1/dead-letters": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List Dead Letters */
        get: operations["list_dead_letters_internal_v1_dead_letters_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/dead-letters/{dead_letter_id}/replay": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Replay */
        post: operations["replay_internal_v1_dead_letters__dead_letter_id__replay_post"];
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
        /** AnnouncementResponse */
        AnnouncementResponse: {
            /** Body */
            body: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Created By User Id
             * Format: uuid
             */
            created_by_user_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Title */
            title: string;
        };
        /**
         * ConversationResponse
         * @description The caller's conversation with staff. Before they have written
         *     anything: OPEN, nothing unread, no messages.
         */
        ConversationResponse: {
            /** Items */
            items: components["schemas"]["MessageResponse"][];
            status: components["schemas"]["SupportStatus"];
            /** Unread Count */
            unread_count: number;
        };
        /** CreateAnnouncementRequest */
        CreateAnnouncementRequest: {
            /** Body */
            body: string;
            /** Title */
            title: string;
        };
        /** DeadLetterResponse */
        DeadLetterResponse: {
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
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Error */
            last_error: string;
            /** Replayed At */
            replayed_at: string | null;
            /** Topic */
            topic: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** InboxResponse */
        InboxResponse: {
            /** Items */
            items: components["schemas"]["ThreadResponse"][];
            /** Waiting Count */
            waiting_count: number;
        };
        /** MessageResponse */
        MessageResponse: {
            /** Body */
            body: string;
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
            sender: components["schemas"]["SupportSender"];
        };
        /** NewsListResponse */
        NewsListResponse: {
            /** Items */
            items: components["schemas"]["NewsResponse"][];
            /** Unread Count */
            unread_count: number;
        };
        /** NewsResponse */
        NewsResponse: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /**
             * Published At
             * Format: date-time
             */
            published_at: string;
            /** Source */
            source: string;
            /** Summary */
            summary: string;
            /** Title */
            title: string;
            /** Unread */
            unread: boolean;
            /** Url */
            url: string;
        };
        /**
         * NotificationListResponse
         * @description One request serves the bell: the badge and the list under it.
         */
        NotificationListResponse: {
            /** Items */
            items: components["schemas"]["NotificationResponse"][];
            /** Unread Count */
            unread_count: number;
        };
        /** NotificationResponse */
        NotificationResponse: {
            /** Body */
            body: string;
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
            /** Params */
            params: {
                [key: string]: unknown;
            } | null;
            /** Read */
            read: boolean;
            /** Title */
            title: string;
            /** Type */
            type: string;
        };
        /** PostMessageRequest */
        PostMessageRequest: {
            /** Body */
            body: string;
        };
        /**
         * SupportSender
         * @enum {string}
         */
        SupportSender: "CUSTOMER" | "STAFF";
        /**
         * SupportStatus
         * @enum {string}
         */
        SupportStatus: "OPEN" | "RESOLVED";
        /** ThreadDetailResponse */
        ThreadDetailResponse: {
            /** Items */
            items: components["schemas"]["MessageResponse"][];
            /** Last Body */
            last_body: string;
            /**
             * Last Message At
             * Format: date-time
             */
            last_message_at: string;
            last_sender: components["schemas"]["SupportSender"];
            status: components["schemas"]["SupportStatus"];
            /** Unread Count */
            unread_count: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
        };
        /**
         * ThreadResponse
         * @description A conversation as staff see it in the inbox.
         */
        ThreadResponse: {
            /** Last Body */
            last_body: string;
            /**
             * Last Message At
             * Format: date-time
             */
            last_message_at: string;
            last_sender: components["schemas"]["SupportSender"];
            status: components["schemas"]["SupportStatus"];
            /** Unread Count */
            unread_count: number;
            /**
             * User Id
             * Format: uuid
             */
            user_id: string;
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_announcements_api_v1_admin_announcements_get: {
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
                    "application/json": components["schemas"]["AnnouncementResponse"][];
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
    publish_announcement_api_v1_admin_announcements_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CreateAnnouncementRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AnnouncementResponse"];
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
    withdraw_announcement_api_v1_admin_announcements__announcement_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                announcement_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_threads_api_v1_admin_support_threads_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["SupportStatus"] | null;
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
                    "application/json": components["schemas"]["InboxResponse"];
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
    get_thread_api_v1_admin_support_threads__user_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["ThreadDetailResponse"];
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
    reply_api_v1_admin_support_threads__user_id__messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PostMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
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
    mark_thread_read_api_v1_admin_support_threads__user_id__read_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["ThreadResponse"];
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
    reopen_thread_api_v1_admin_support_threads__user_id__reopen_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["ThreadResponse"];
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
    resolve_thread_api_v1_admin_support_threads__user_id__resolve_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                user_id: string;
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
                    "application/json": components["schemas"]["ThreadResponse"];
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
    list_news_api_v1_news_get: {
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
                    "application/json": components["schemas"]["NewsListResponse"];
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
    mark_news_read_api_v1_news_read_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_news_item_api_v1_news__news_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                news_id: string;
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
                    "application/json": components["schemas"]["NewsResponse"];
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
    list_my_notifications_api_v1_notifications_get: {
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
                    "application/json": components["schemas"]["NotificationListResponse"];
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
    mark_my_notifications_read_api_v1_notifications_read_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
        };
    };
    get_my_conversation_api_v1_support_messages_get: {
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
                    "application/json": components["schemas"]["ConversationResponse"];
                };
            };
        };
    };
    write_to_support_api_v1_support_messages_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PostMessageRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["MessageResponse"];
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
    mark_replies_read_api_v1_support_read_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
    list_dead_letters_internal_v1_dead_letters_get: {
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
                    "application/json": components["schemas"]["DeadLetterResponse"][];
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
    replay_internal_v1_dead_letters__dead_letter_id__replay_post: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
            path: {
                dead_letter_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            204: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
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
