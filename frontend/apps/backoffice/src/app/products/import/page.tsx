import type { Metadata } from "next";
import { ButtonLink } from "@ecommerce/ui";
import { ImportFlow } from "../../../components/imports/import-flow";
import { ImportQueryProvider } from "../../../components/imports/import-query-provider";
import { PRODUCTS_PATH, ZONE_PATH } from "../../../lib/paths";
import { importMaxBytes } from "../../../server/import-config";
import { createCategoryAction } from "../../categories/actions";
import { confirmImportAction, revalidateImportAction } from "./actions";

export const metadata: Metadata = { title: "Import products" };

export default function ImportProductsPage() {
  return (
    <section aria-labelledby="import-heading" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <h1 id="import-heading" className="text-3xl font-semibold">
          Import products from CSV
        </h1>
        <ButtonLink variant="secondary" href={`${ZONE_PATH}${PRODUCTS_PATH}`}>
          Back to products
        </ButtonLink>
      </div>
      <ImportQueryProvider>
        <ImportFlow
          maxBytes={importMaxBytes()}
          actions={{
            confirmImport: confirmImportAction,
            revalidateImport: revalidateImportAction,
            createCategory: createCategoryAction,
          }}
        />
      </ImportQueryProvider>
    </section>
  );
}
