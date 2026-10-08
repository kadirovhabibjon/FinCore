// Generated from contracts/openapi/identity-service.json by scripts/generate-api-types.mjs.
// Do not edit by hand: run `npm run gen:api`.

export interface paths {
    "/.well-known/jwks.json": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Jwks */
        get: operations["jwks__well_known_jwks_json_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Search Users */
        get: operations["search_users_api_v1_admin_users_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/stats": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get User Stats
         * @description How many accounts there are, by status, and how many were created
         *     on each of the last `days` days (UTC). SUPPORT and ADMIN.
         */
        get: operations["get_user_stats_api_v1_admin_users_stats_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User */
        get: operations["get_user_api_v1_admin_users__user_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/users/{user_id}/status": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Update User Status */
        post: operations["update_user_status_api_v1_admin_users__user_id__status_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/login": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Login */
        post: operations["login_api_v1_auth_login_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/logout": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Logout */
        post: operations["logout_api_v1_auth_logout_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password-reset/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Confirm Password Reset
         * @description Sets a new password using the emailed code, and signs the account
         *     out everywhere. Any failure is the same 422.
         */
        post: operations["confirm_password_reset_api_v1_auth_password_reset_confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/password-reset/request": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Request Password Reset
         * @description Emails a 6-digit reset code to the account's address, if there is
         *     such an account. Always 202 with no body: the answer, and how long it
         *     takes, is the same whether or not the account exists (the email goes
         *     out after the response).
         */
        post: operations["request_password_reset_api_v1_auth_password_reset_request_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/refresh": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Refresh */
        post: operations["refresh_api_v1_auth_refresh_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/auth/register": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /** Register */
        post: operations["register_api_v1_auth_register_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/me": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Read Current User */
        get: operations["read_current_user_api_v1_users_me_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        /**
         * Update My Profile
         * @description Edits the caller's own name, email address or phone number; only
         *     the fields sent, and only those that differ, change. A new email or
         *     phone needs `current_password` (they are how the account is signed
         *     in to and recovered) and must be unused. The account's previous
         *     email address is told about such a change.
         */
        patch: operations["update_my_profile_api_v1_users_me_patch"];
        trace?: never;
    };
    "/api/v1/users/me/password": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Change My Password
         * @description Requires the current password even though the caller is signed in,
         *     so a borrowed unlocked device can't lock the owner out. Signs out
         *     every other session; this one stays.
         */
        post: operations["change_my_password_api_v1_users_me_password_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/me/sessions": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * List My Sessions
         * @description The caller's refreshable sessions (ADR-0005: "view/revoke active
         *     sessions"), most recently used first, with the one this request's
         *     token came from marked `current`.
         */
        get: operations["list_my_sessions_api_v1_users_me_sessions_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/users/me/sessions/{session_id}": {
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
         * Revoke My Session
         * @description Revokes one of the caller's own sessions — every refresh token it
         *     will ever issue stops working. An access token already issued from it
         *     stays valid until it expires (short-lived by design). Revoking the
         *     current session is allowed: that's a remote logout of this device.
         */
        delete: operations["revoke_my_session_api_v1_users_me_sessions__session_id__delete"];
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
    "/internal/v1/users/by-phone": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get User By Phone
         * @description Whose phone number this is - for payment-service, which lets a
         *     customer send money to a phone number. The number may be typed any
         *     of the ways sign-in accepts; it is put in the stored form here, so
         *     there is one definition of that form.
         */
        get: operations["get_user_by_phone_internal_v1_users_by_phone_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/internal/v1/users/{user_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get User */
        get: operations["get_user_internal_v1_users__user_id__get"];
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
        /** AdminUserResponse */
        AdminUserResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            /** First Name */
            first_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            /** Phone */
            phone: string;
            /** Roles */
            roles: string[];
            status: components["schemas"]["UserStatus"];
        };
        /** ChangePasswordRequest */
        ChangePasswordRequest: {
            /** Current Password */
            current_password: string;
            /** New Password */
            new_password: string;
        };
        /**
         * CurrentUserResponse
         * @description `GET /users/me`: the caller's own profile plus their roles, so a
         *     client can decide what to show (e.g. the admin panel) without
         *     decoding the JWT itself. Server-side checks never rely on this.
         */
        CurrentUserResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            /** First Name */
            first_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            /** Phone */
            phone: string;
            /** Roles */
            roles: string[];
            status: components["schemas"]["UserStatus"];
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /**
         * InternalUserResponse
         * @description The little another service may know about a user: who they are
         *     by name and whether the account is usable. No email, phone or roles.
         */
        InternalUserResponse: {
            /** First Name */
            first_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            status: components["schemas"]["UserStatus"];
        };
        /**
         * LoginRequest
         * @description Sign in with email or phone number - exactly one - and password.
         */
        LoginRequest: {
            /** Email */
            email?: string | null;
            /** Password */
            password: string;
            /** Phone */
            phone?: string | null;
        };
        /** LogoutRequest */
        LogoutRequest: {
            /** Refresh Token */
            refresh_token: string;
        };
        /** PasswordResetConfirmRequest */
        PasswordResetConfirmRequest: {
            /** Code */
            code: string;
            /** Email */
            email?: string | null;
            /** New Password */
            new_password: string;
            /** Phone */
            phone?: string | null;
        };
        /**
         * PasswordResetRequest
         * @description Whose password to reset: email or phone number, exactly one.
         */
        PasswordResetRequest: {
            /** Email */
            email?: string | null;
            /** Phone */
            phone?: string | null;
        };
        /** RefreshRequest */
        RefreshRequest: {
            /** Refresh Token */
            refresh_token: string;
        };
        /** RegisterRequest */
        RegisterRequest: {
            /**
             * Email
             * Format: email
             */
            email: string;
            /** First Name */
            first_name: string;
            /** Last Name */
            last_name: string;
            /** Password */
            password: string;
            /** Phone */
            phone: string;
        };
        /** RegistrationsDay */
        RegistrationsDay: {
            /**
             * Date
             * Format: date
             */
            date: string;
            /** Registered */
            registered: number;
        };
        /** SessionResponse */
        SessionResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /**
             * Current
             * @default false
             */
            current: boolean;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Ip Address */
            ip_address: string | null;
            /** Last Used At */
            last_used_at: string | null;
            /** User Agent */
            user_agent: string | null;
        };
        /** TokenResponse */
        TokenResponse: {
            /** Access Token */
            access_token: string;
            /** Expires In */
            expires_in: number;
            /** Refresh Token */
            refresh_token: string | null;
            /**
             * Token Type
             * @default bearer
             */
            token_type: string;
        };
        /**
         * UpdateProfileRequest
         * @description Only the fields to change. Email and phone are validated and
         *     normalized exactly as at registration.
         */
        UpdateProfileRequest: {
            /** Current Password */
            current_password?: string | null;
            /** Email */
            email?: string | null;
            /** First Name */
            first_name?: string | null;
            /** Last Name */
            last_name?: string | null;
            /** Phone */
            phone?: string | null;
        };
        /** UserResponse */
        UserResponse: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Email */
            email: string;
            /** First Name */
            first_name: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Last Name */
            last_name: string;
            /** Phone */
            phone: string;
            status: components["schemas"]["UserStatus"];
        };
        /** UserStatsResponse */
        UserStatsResponse: {
            /** By Status */
            by_status: {
                [key: string]: number;
            };
            /** Days */
            days: components["schemas"]["RegistrationsDay"][];
            /** Total */
            total: number;
        };
        /**
         * UserStatus
         * @enum {string}
         */
        UserStatus: "ACTIVE" | "BLOCKED" | "SUSPENDED";
        /** UserStatusUpdateRequest */
        UserStatusUpdateRequest: {
            status: components["schemas"]["UserStatus"];
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
    jwks__well_known_jwks_json_get: {
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
                        [key: string]: unknown;
                    };
                };
            };
        };
    };
    search_users_api_v1_admin_users_get: {
        parameters: {
            query?: {
                q?: string | null;
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
                    "application/json": components["schemas"]["AdminUserResponse"][];
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
    get_user_stats_api_v1_admin_users_stats_get: {
        parameters: {
            query?: {
                days?: number;
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
                    "application/json": components["schemas"]["UserStatsResponse"];
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
    get_user_api_v1_admin_users__user_id__get: {
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
                    "application/json": components["schemas"]["AdminUserResponse"];
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
    update_user_status_api_v1_admin_users__user_id__status_post: {
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
                "application/json": components["schemas"]["UserStatusUpdateRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["AdminUserResponse"];
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
    login_api_v1_auth_login_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Refresh-Token-Transport"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["LoginRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
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
    logout_api_v1_auth_logout_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Refresh-Token-Transport"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["LogoutRequest"] | null;
            };
        };
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
    confirm_password_reset_api_v1_auth_password_reset_confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetConfirmRequest"];
            };
        };
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
    request_password_reset_api_v1_auth_password_reset_request_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["PasswordResetRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": unknown;
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
    refresh_api_v1_auth_refresh_post: {
        parameters: {
            query?: never;
            header?: {
                "X-Refresh-Token-Transport"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody?: {
            content: {
                "application/json": components["schemas"]["RefreshRequest"] | null;
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["TokenResponse"];
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
    register_api_v1_auth_register_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["RegisterRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["UserResponse"];
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
    read_current_user_api_v1_users_me_get: {
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
                    "application/json": components["schemas"]["CurrentUserResponse"];
                };
            };
        };
    };
    update_my_profile_api_v1_users_me_patch: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["UpdateProfileRequest"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CurrentUserResponse"];
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
    change_my_password_api_v1_users_me_password_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ChangePasswordRequest"];
            };
        };
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
    list_my_sessions_api_v1_users_me_sessions_get: {
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
                    "application/json": components["schemas"]["SessionResponse"][];
                };
            };
        };
    };
    revoke_my_session_api_v1_users_me_sessions__session_id__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                session_id: string;
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
    get_user_by_phone_internal_v1_users_by_phone_get: {
        parameters: {
            query: {
                phone: string;
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
                    "application/json": components["schemas"]["InternalUserResponse"];
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
    get_user_internal_v1_users__user_id__get: {
        parameters: {
            query?: never;
            header: {
                "x-internal-token": string;
            };
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
                    "application/json": components["schemas"]["InternalUserResponse"];
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
