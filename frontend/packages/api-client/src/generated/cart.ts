export interface paths {
    "/api/v1/cart": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Get the cart of the authenticated user
         * @description Lines keep the price and name saved when they were added. `flags` compares each line with what the catalog says now: `price_changed` (old and new price), `unavailable` (the product was retired) and `insufficient_stock` (`available` may be 0). Nothing is changed silently.
         */
        get: operations["get_cart_api_v1_cart_get"];
        put?: never;
        post?: never;
        /** Empty the cart */
        delete: operations["clear_cart_api_v1_cart_delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/cart/items/{sku}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set the quantity of a product in the cart
         * @description Creates the line or replaces its quantity (1 to 99). A new line reads the product from the catalog and saves its price and name. A cart holds at most 100 different products. With `accepted_price` the line takes the current price and name, but only if that price is the one sent.
         */
        put: operations["put_item_api_v1_cart_items__sku__put"];
        post?: never;
        /**
         * Remove a product from the cart
         * @description Removing a product that is not in the cart is not an error.
         */
        delete: operations["delete_item_api_v1_cart_items__sku__delete"];
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
        /** CartOut */
        CartOut: {
            /**
             * Item Count
             * @description Total units in the cart
             */
            item_count: number;
            /** Items */
            items: components["schemas"]["LineOut"][];
            /**
             * Subtotal
             * @description Sum of the line totals at the saved prices
             */
            subtotal: string;
        };
        /** FlagOut */
        FlagOut: {
            /**
             * Available
             * @description Units in stock
             */
            available?: number | null;
            /**
             * New Price
             * @description Current catalog price
             */
            new_price?: string | null;
            /**
             * Old Price
             * @description Price saved in the cart
             */
            old_price?: string | null;
            type: components["schemas"]["FlagType"];
        };
        /**
         * FlagType
         * @enum {string}
         */
        FlagType: "price_changed" | "unavailable" | "insufficient_stock";
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ItemIn */
        ItemIn: {
            /**
             * Accepted Price
             * @description The price the customer agreed to. When present it must equal the current catalog price, otherwise the request fails with 409; on success the line takes the current price and name.
             */
            accepted_price?: number | string | null;
            /**
             * Quantity
             * @example 2
             */
            quantity: number;
        };
        /** LineOut */
        LineOut: {
            /** Flags */
            flags: components["schemas"]["FlagOut"][];
            /** Line Total */
            line_total: string;
            /** Name */
            name: string;
            /**
             * Price
             * @description Price saved when the line was added or last accepted
             */
            price: string;
            /** Quantity */
            quantity: number;
            /** Sku */
            sku: string;
            /**
             * Thumbnail Url
             * @description Public URL of the 400 px image
             */
            thumbnail_url: string | null;
        };
        /** ProblemOut */
        ProblemOut: {
            /** Detail */
            detail?: string | null;
            /** Instance */
            instance?: string | null;
            /** Request Id */
            request_id?: string | null;
            /** Status */
            status: number;
            /** Title */
            title: string;
            /** Type */
            type: string;
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
    get_cart_api_v1_cart_get: {
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
                    "application/json": components["schemas"]["CartOut"];
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
            /** @description The cart store or the catalog is unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    clear_cart_api_v1_cart_delete: {
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
            /** @description Missing, invalid or expired access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description The cart store or the catalog is unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    put_item_api_v1_cart_items__sku__put: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Product SKU, case insensitive */
                sku: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ItemIn"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CartOut"];
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
            /** @description Unknown or retired product */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description The cart is full or the accepted price is not the current price */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
            /** @description The cart store or the catalog is unavailable */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
                };
            };
        };
    };
    delete_item_api_v1_cart_items__sku__delete: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Product SKU, case insensitive */
                sku: string;
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
                    "application/json": components["schemas"]["CartOut"];
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
            /** @description Unknown or retired product */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProblemOut"];
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
            /** @description The cart store or the catalog is unavailable */
            503: {
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
