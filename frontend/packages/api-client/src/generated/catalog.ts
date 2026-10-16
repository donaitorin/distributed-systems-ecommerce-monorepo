export interface paths {
    "/api/v1/categories": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List all categories */
        get: operations["list_categories_api_v1_categories_get"];
        put?: never;
        /** Create a category (admin) */
        post: operations["create_category_api_v1_categories_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Upload a products CSV (admin)
         * @description Multipart field `file`. The file is stored, hashed and validated in the background; nothing is written to the catalog until the import is confirmed. Uploading the same file again returns the existing import with status 200.
         */
        post: operations["upload_import_api_v1_imports_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports/{import_id}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get an import with its status, counts and first problems (admin) */
        get: operations["get_import_api_v1_imports__import_id__get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports/{import_id}/confirm": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Confirm the import of the valid rows (admin)
         * @description Only a validated import can be confirmed. The valid rows are then written in the background; poll the import for progress. Repeating the call is harmless.
         */
        post: operations["confirm_import_api_v1_imports__import_id__confirm_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports/{import_id}/problems": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** List the problems of an import, in file order (admin) */
        get: operations["list_problems_api_v1_imports__import_id__problems_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports/{import_id}/problems.csv": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Download every problem of an import as a CSV (admin) */
        get: operations["download_problems_api_v1_imports__import_id__problems_csv_get"];
        put?: never;
        post?: never;
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/imports/{import_id}/revalidate": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        put?: never;
        /**
         * Validate the same file again against the current categories (admin)
         * @description Allowed for a rejected or validated import, for example after creating a category the file refers to. The previous report, problems and category snapshot are discarded together with the status change and the file is validated again in the background; poll the import for the result. Repeating the call while it is pending is harmless.
         */
        post: operations["revalidate_import_api_v1_imports__import_id__revalidate_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/products": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /**
         * Search and list products
         * @description Keyset-paginated listing. Without q the default order is newest first; with q it is relevance, and typos in q still match. sort=relevance without q falls back to newest. in_stock=true hides sold-out products; in_stock=false is the same as omitting it. An unknown category slug returns an empty page. A cursor is only valid with the q, category, price, in_stock and sort values it was issued for.
         */
        get: operations["list_products_api_v1_products_get"];
        put?: never;
        /** Create a product (admin) */
        post: operations["create_product_api_v1_products_post"];
        delete?: never;
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/products/{sku}": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        /** Get a product */
        get: operations["get_product_api_v1_products__sku__get"];
        /** Replace a product (admin, requires If-Match) */
        put: operations["replace_product_api_v1_products__sku__put"];
        post?: never;
        /** Soft delete a product (admin, requires If-Match) */
        delete: operations["delete_product_api_v1_products__sku__delete"];
        options?: never;
        head?: never;
        patch?: never;
        trace?: never;
    };
    "/api/v1/products/{sku}/image": {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        get?: never;
        /**
         * Set the product image (admin, requires If-Match)
         * @description Multipart field `file`: a JPEG, PNG or WebP image of at most 5 MB and 25 megapixels, validated by content. It is converted to WebP renditions of 400 px (`thumbnail_url`) and 1200 px (`image_url`) on the longest side, with metadata removed, and the product version is incremented.
         */
        put: operations["replace_image_api_v1_products__sku__image_put"];
        post?: never;
        /** Remove the product image (admin, requires If-Match) */
        delete: operations["remove_image_api_v1_products__sku__image_delete"];
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
        /** CategoryCreate */
        CategoryCreate: {
            /** Name */
            name: string;
        };
        /** CategoryOut */
        CategoryOut: {
            /**
             * Id
             * Format: uuid
             */
            id: string;
            /** Name */
            name: string;
            /** Slug */
            slug: string;
        };
        /** FieldProblem */
        FieldProblem: {
            /** Location */
            location: string;
            /** Message */
            message: string;
            /** Type */
            type: string;
        };
        /** HTTPValidationError */
        HTTPValidationError: {
            /** Detail */
            detail?: components["schemas"]["ValidationError"][];
        };
        /** ImportLinks */
        ImportLinks: {
            /**
             * Confirm
             * @description Present while the import can be confirmed
             */
            confirm?: string | null;
            /** Problems */
            problems: string;
            /** Problems Csv */
            problems_csv: string;
            /** Self */
            self: string;
        };
        /** ImportOut */
        ImportOut: {
            /** Confirmed At */
            confirmed_at: string | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Created By */
            created_by: string;
            /** Failure Reason */
            failure_reason: string | null;
            /** Filename */
            filename: string;
            /** Finished At */
            finished_at: string | null;
            /**
             * Id
             * Format: uuid
             */
            id: string;
            links: components["schemas"]["ImportLinks"];
            /**
             * Problems
             * @description The first problems, errors before warnings; use the links for all of them
             */
            problems: components["schemas"]["catalog__api__import_schemas__ProblemOut"][];
            progress: components["schemas"]["ProgressOut"];
            /** Sha256 */
            sha256: string;
            /** Size Bytes */
            size_bytes: number;
            /** Status */
            status: string;
            summary: components["schemas"]["ImportSummaryOut"] | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Validated At */
            validated_at: string | null;
        };
        /** ImportSummaryOut */
        ImportSummaryOut: {
            /** Blank Rows */
            blank_rows: number;
            /** Duplicate Rows */
            duplicate_rows: number;
            /** Error Count */
            error_count: number;
            /** Error Rows */
            error_rows: number;
            /** Importable Rows */
            importable_rows: number;
            /** Rejected */
            rejected: boolean;
            /** Rows Read */
            rows_read: number;
            /** Superseded Rows */
            superseded_rows: number;
            /** To Create */
            to_create: number;
            /** To Restore */
            to_restore: number;
            /** To Update */
            to_update: number;
            /**
             * Truncated
             * @description True when only the first problems are stored; the counts stay exact
             */
            truncated: boolean;
            /** Unchanged */
            unchanged: number;
            /** Unknown Categories */
            unknown_categories: components["schemas"]["UnknownCategoryOut"][];
            /** Warning Count */
            warning_count: number;
        };
        /** ProblemsPageOut */
        ProblemsPageOut: {
            /** Items */
            items: components["schemas"]["catalog__api__import_schemas__ProblemOut"][];
            /** Next Cursor */
            next_cursor?: string | null;
        };
        /** ProductCreate */
        ProductCreate: {
            /** Category Id */
            category_id?: string | null;
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
            /** Price */
            price: number | string;
            /** Sku */
            sku: string;
            /** Stock */
            stock: number;
            /** Weight Kg */
            weight_kg?: number | string | null;
        };
        /** ProductOut */
        ProductOut: {
            category: components["schemas"]["CategoryOut"] | null;
            /**
             * Created At
             * Format: date-time
             */
            created_at: string;
            /** Description */
            description: string | null;
            /**
             * Image Url
             * @description Public URL of the 1200 px WebP image, null without an image
             */
            image_url?: string | null;
            /** Name */
            name: string;
            /** Price */
            price: string;
            /** Sku */
            sku: string;
            /** Stock */
            stock: number;
            /**
             * Thumbnail Url
             * @description Public URL of the 400 px WebP thumbnail, null without an image
             */
            thumbnail_url?: string | null;
            /**
             * Updated At
             * Format: date-time
             */
            updated_at: string;
            /** Version */
            version: number;
            /** Weight Kg */
            weight_kg: string | null;
        };
        /** ProductPage */
        ProductPage: {
            /** Items */
            items: components["schemas"]["ProductOut"][];
            /**
             * Next Cursor
             * @description Opaque cursor for the next page, null on the last page
             */
            next_cursor?: string | null;
            /**
             * Prev Cursor
             * @description Opaque cursor for the previous page, null on the first page
             */
            prev_cursor?: string | null;
            /**
             * Total
             * @description Number of matching products; an estimate unless total_exact is true
             * @default 0
             */
            total: number;
            /**
             * Total Exact
             * @description True when total is an exact count, false when it is a planner estimate
             * @default true
             */
            total_exact: boolean;
        };
        /** ProductWrite */
        ProductWrite: {
            /** Category Id */
            category_id?: string | null;
            /** Description */
            description?: string | null;
            /** Name */
            name: string;
            /** Price */
            price: number | string;
            /** Stock */
            stock: number;
            /** Weight Kg */
            weight_kg?: number | string | null;
        };
        /** ProgressOut */
        ProgressOut: {
            /** Created Rows */
            created_rows: number;
            /** Processed Rows */
            processed_rows: number;
            /** Restored Rows */
            restored_rows: number;
            /** Unchanged Rows */
            unchanged_rows: number;
            /** Updated Rows */
            updated_rows: number;
        };
        /**
         * Sort
         * @enum {string}
         */
        Sort: "relevance" | "price_asc" | "price_desc" | "newest";
        /** UnknownCategoryOut */
        UnknownCategoryOut: {
            /** Rows */
            rows: number;
            /** Suggestion */
            suggestion: string | null;
            /** Value */
            value: string;
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
        /** ProblemOut */
        catalog__api__import_schemas__ProblemOut: {
            /** Code */
            code: string;
            /** Column */
            column: string | null;
            /** Reason */
            reason: string;
            /**
             * Row
             * @description Spreadsheet row; the header is row 1
             */
            row: number | null;
            /** Severity */
            severity: string;
            /**
             * Value
             * @description The value as received, truncated to 200 characters
             */
            value: string | null;
        };
        /** ProblemOut */
        catalog__api__schemas__ProblemOut: {
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
    };
    responses: never;
    parameters: never;
    requestBodies: never;
    headers: never;
    pathItems: never;
}
export type $defs = Record<string, never>;
export interface operations {
    list_categories_api_v1_categories_get: {
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
                    "application/json": components["schemas"]["CategoryOut"][];
                };
            };
        };
    };
    create_category_api_v1_categories_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["CategoryCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["CategoryOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Conflict with an existing resource */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    upload_import_api_v1_imports_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: string;
                };
            };
        };
        responses: {
            /** @description The same file was already uploaded; the existing import */
            200: {
                headers: {
                    [name: string]: unknown;
                };
                content?: never;
            };
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The upload exceeds the 5 MB limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The upload is not multipart or not a supported file */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The search exceeded its time limit; retry after the Retry-After delay */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    get_import_api_v1_imports__import_id__get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Import id */
                import_id: string;
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
                    "application/json": components["schemas"]["ImportOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
    confirm_import_api_v1_imports__import_id__confirm_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Import id */
                import_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Conflict with an existing resource */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
    list_problems_api_v1_imports__import_id__problems_get: {
        parameters: {
            query?: {
                severity?: ("error" | "warning") | null;
                cursor?: string | null;
                /** @description Page size: 25, 50, 100 or 500 */
                limit?: number;
            };
            header?: never;
            path: {
                /** @description Import id */
                import_id: string;
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
                    "application/json": components["schemas"]["ProblemsPageOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    download_problems_api_v1_imports__import_id__problems_csv_get: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Import id */
                import_id: string;
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
                    "text/csv": unknown;
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
    revalidate_import_api_v1_imports__import_id__revalidate_post: {
        parameters: {
            query?: never;
            header?: never;
            path: {
                /** @description Import id */
                import_id: string;
            };
            cookie?: never;
        };
        requestBody?: never;
        responses: {
            /** @description Successful Response */
            202: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ImportOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Conflict with an existing resource */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
    list_products_api_v1_products_get: {
        parameters: {
            query?: {
                /** @description Free text; typos are tolerated */
                q?: string | null;
                /** @description Category slug */
                category?: string | null;
                /** @description Minimum price, inclusive */
                min_price?: number | string | null;
                /** @description Maximum price, inclusive */
                max_price?: number | string | null;
                /** @description true hides sold-out products; false is the same as omitting it */
                in_stock?: boolean | null;
                /** @description Defaults to relevance when q is present, otherwise newest */
                sort?: components["schemas"]["Sort"] | null;
                /** @description Page size: 12, 24 or 48 */
                limit?: number;
                /** @description Opaque cursor from a previous page */
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
                    "application/json": components["schemas"]["ProductPage"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The search exceeded its time limit; retry after the Retry-After delay */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    create_product_api_v1_products_post: {
        parameters: {
            query?: never;
            header?: never;
            path?: never;
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProductCreate"];
            };
        };
        responses: {
            /** @description Successful Response */
            201: {
                headers: {
                    /** @description Version of the product */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Conflict with an existing resource */
            409: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    get_product_api_v1_products__sku__get: {
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
                    /** @description Version of the product */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductOut"];
                };
            };
            /** @description Unknown or deleted SKU */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
    replace_product_api_v1_products__sku__put: {
        parameters: {
            query?: never;
            header?: {
                /** @description ETag of the version being changed, or * to match any version */
                "if-match"?: string | null;
            };
            path: {
                /** @description Product SKU, case insensitive */
                sku: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "application/json": components["schemas"]["ProductWrite"];
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    /** @description Version of the product */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match does not match the current version */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match header is required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    delete_product_api_v1_products__sku__delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description ETag of the version being changed, or * to match any version */
                "if-match"?: string | null;
            };
            path: {
                /** @description Product SKU, case insensitive */
                sku: string;
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
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match does not match the current version */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
            /** @description If-Match header is required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    replace_image_api_v1_products__sku__image_put: {
        parameters: {
            query?: never;
            header?: {
                /** @description ETag of the version being changed, or * to match any version */
                "if-match"?: string | null;
            };
            path: {
                /** @description Product SKU, case insensitive */
                sku: string;
            };
            cookie?: never;
        };
        requestBody: {
            content: {
                "multipart/form-data": {
                    /** Format: binary */
                    file: string;
                };
            };
        };
        responses: {
            /** @description Successful Response */
            200: {
                headers: {
                    /** @description Version of the product */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match does not match the current version */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The upload exceeds the 5 MB limit */
            413: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The upload is not multipart or not a supported file */
            415: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Invalid request data */
            422: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match header is required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The search exceeded its time limit; retry after the Retry-After delay */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
        };
    };
    remove_image_api_v1_products__sku__image_delete: {
        parameters: {
            query?: never;
            header?: {
                /** @description ETag of the version being changed, or * to match any version */
                "if-match"?: string | null;
            };
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
                    /** @description Version of the product */
                    ETag?: string;
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["ProductOut"];
                };
            };
            /** @description Missing or invalid access token */
            401: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The token does not carry the admin role */
            403: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description Unknown or deleted SKU, or the product has no image */
            404: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description If-Match does not match the current version */
            412: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
            /** @description If-Match header is required */
            428: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
                };
            };
            /** @description The search exceeded its time limit; retry after the Retry-After delay */
            503: {
                headers: {
                    [name: string]: unknown;
                };
                content: {
                    "application/json": components["schemas"]["catalog__api__schemas__ProblemOut"];
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
