export interface paths {
    "/api/v1/admin/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List every order, newest first (admin) */
        get: operations["list_all_orders_api_v1_admin_orders_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/admin/orders/{order_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get any order (admin) */
        get: operations["get_any_order_api_v1_admin_orders__order_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/orders": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List your orders, newest first */
        get: operations["list_orders_api_v1_orders_get"];
        put?: never;
        /**
         * Place an order
         * @description Creates the order as PENDING and starts the checkout saga. Requires an Idempotency-Key header: the same key with the same body returns the same response for 24 hours, the same key with a different body is rejected.
         */
        post: operations["place_order_api_v1_orders_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/orders/{order_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get one of your orders with its lines, totals and status history */
        get: operations["get_order_api_v1_orders__order_id__get"];
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
        /** Health */
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
        /** Ready */
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
        /** FieldProblem */
        FieldProblem: {
            /** Location */
            location: string;
            /** Message */
            message: string;
            /** Type */
            type: string;
        };
        /** HistoryEntryOut */
        HistoryEntryOut: {
            /**
             * At
             * Format: date-time
             */
            at: string;
            from_status: components["schemas"]["OrderStatus"] | null;
            /** Reason */
            reason: string | null;
            to_status: components["schemas"]["OrderStatus"];
        };
        /** OrderAcceptedOut */
        OrderAcceptedOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            status: components["schemas"]["OrderStatus"];
        };
        /** OrderDetailOut */
        OrderDetailOut: {
            /** Cancel Reason */
            cancel_reason: string | null;
            /** Card Last4 */
            card_last4: string;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /**
             * Customer Id
             * Format: uuid
             */
            customer_id: string;
            /** History */
            history: components["schemas"]["HistoryEntryOut"][];
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Lines */
            lines: components["schemas"]["OrderLineOut"][];
            /** Refunded At */
            refunded_at: string | null;
            shipping_address: components["schemas"]["ShippingAddressOut"];
            status: components["schemas"]["OrderStatus"];
            /** Total */
            total: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** OrderIn */
        OrderIn: {
            /** Lines */
            lines: components["schemas"]["OrderLineIn"][];
            payment: components["schemas"]["PaymentIn"];
            shipping_address: components["schemas"]["ShippingAddressIn"];
        };
        /** OrderLineIn */
        OrderLineIn: {
            /** Quantity */
            quantity: number;
            /**
             * Sku
             * @example RS-001
             */
            sku: string;
            /**
             * Unit Price
             * @description The price the customer saw
             */
            unit_price: number | string;
        };
        /** OrderLineOut */
        OrderLineOut: {
            /** Line Total */
            line_total: string;
            /** Name */
            name: string | null;
            /** Quantity */
            quantity: number;
            /** Sku */
            sku: string;
            /** Unit Price */
            unit_price: string;
        };
        /** OrderPageOut */
        OrderPageOut: {
            /** Items */
            items: components["schemas"]["OrderSummaryOut"][];
            /** Next Cursor */
            next_cursor: string | null;
        };
        /**
         * OrderStatus
         * @enum {string}
         */
        OrderStatus: "PENDING" | "STOCK_RESERVED" | "PAID" | "CONFIRMED" | "CANCELLED";
        /** OrderSummaryOut */
        OrderSummaryOut: {
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Currency */
            currency: string;
            /**
             * Customer Id
             * Format: uuid
             */
            customer_id: string;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Item Count */
            item_count: number;
            status: components["schemas"]["OrderStatus"];
            /** Total */
            total: string;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
        };
        /** PaymentIn */
        PaymentIn: {
            /**
             * Card Number
             * Format: password
             * @description Simulated card number. Only the last 4 digits are kept
             * @example 4111 1111 1111 1111
             */
            card_number: string;
        };
        /** ProblemOut */
        ProblemOut: {
            /** Code */
            code?: string | null;
            /** Detail */
            detail?: string | null;
            /** Errors */
            errors?: components["schemas"]["FieldProblem"][] | null;
            /** Instance */
            instance: string;
            /** Request Id */
            request_id?: string | null;
            /** Status */
            status: number;
            /** Title */
            title: string;
            /**
             * Type
             * @default about:blank
             */
            type: string;
        };
        /** ShippingAddressIn */
        ShippingAddressIn: {
            /** City */
            city: string;
            /**
             * Country
             * @example ES
             */
            country: string;
            /** Line1 */
            line1: string;
            /** Line2 */
            line2?: string | null;
            /** Phone */
            phone?: string | null;
            /** Postal Code */
            postal_code: string;
            /** Recipient Name */
            recipient_name: string;
            /** Region */
            region?: string | null;
        };
        /** ShippingAddressOut */
        ShippingAddressOut: {
            /** City */
            city: string;
            /** Country */
            country: string;
            /** Line1 */
            line1: string;
            /** Line2 */
            line2: string | null;
            /** Phone */
            phone: string | null;
            /** Postal Code */
            postal_code: string;
            /** Recipient Name */
            recipient_name: string;
            /** Region */
            region: string | null;
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
    list_all_orders_api_v1_admin_orders_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["OrderStatus"] | null;
                /** @description Created at or after this moment (with time zone) */
                created_from?: string | null;
                /** @description Created before this moment (with time zone) */
                created_to?: string | null;
                /** @description Page size: 25, 50 or 100 */
                limit?: number;
                cursor?: string | null;
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
                    "application/json": components["schemas"]["OrderPageOut"];
                };
            };
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data, or an idempotency key reused with a different body */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    get_any_order_api_v1_admin_orders__order_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                order_id: string;
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
                    "application/json": components["schemas"]["OrderDetailOut"];
                };
            };
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description No such order */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data, or an idempotency key reused with a different body */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    list_orders_api_v1_orders_get: {
        parameters: {
            query?: {
                status?: components["schemas"]["OrderStatus"] | null;
                /** @description Page size: 25, 50 or 100 */
                limit?: number;
                cursor?: string | null;
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
                    "application/json": components["schemas"]["OrderPageOut"];
                };
            };
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data, or an idempotency key reused with a different body */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    place_order_api_v1_orders_post: {
        parameters: {
            query?: never;
            header?: {
                "Idempotency-Key"?: string | null;
            };
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["OrderIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["OrderAcceptedOut"];
                };
            };
            /** @description The Idempotency-Key header is missing or malformed */
            400: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data, or an idempotency key reused with a different body */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    get_order_api_v1_orders__order_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                order_id: string;
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
                    "application/json": components["schemas"]["OrderDetailOut"];
                };
            };
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description No such order */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data, or an idempotency key reused with a different body */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
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
                    "application/json": unknown;
                };
            };
        };
    };
}
