import type { Metadata } from "next";
import { notFound, redirect } from "next/navigation";
import { isFailure, type Failure, type Product } from "@ecommerce/web-core";
import { ProductDetail } from "../../../components/catalog/product-detail";
import { productHref } from "../../../lib/paths";
import { loadProduct } from "../../../server/catalog";

type ProductPageProps = {
  params: Promise<{ sku: string }>;
};

const DESCRIPTION_LENGTH = 160;

function readSku(raw: string): string {
  try {
    return decodeURIComponent(raw);
  } catch {
    return notFound();
  }
}

async function resolve(params: ProductPageProps["params"]): Promise<{ sku: string; result: Product | Failure }> {
  const sku = readSku((await params).sku);
  const result = await loadProduct(sku);
  if (isFailure(result) && result.status === 404) {
    notFound();
  }
  return { sku, result };
}

function summary(product: Product): string {
  const text = product.description?.trim();
  if (!text) {
    return `${product.name} at $${product.price}.`;
  }
  return text.length > DESCRIPTION_LENGTH ? `${text.slice(0, DESCRIPTION_LENGTH - 1).trimEnd()}…` : text;
}

export async function generateMetadata({ params }: ProductPageProps): Promise<Metadata> {
  const { result } = await resolve(params);
  if (isFailure(result)) {
    return { title: "Product unavailable", robots: { index: false } };
  }
  return {
    title: result.name,
    description: summary(result),
    alternates: { canonical: productHref(result.sku) },
    openGraph: { title: result.name, description: summary(result) },
  };
}

export default async function ProductPage({ params }: ProductPageProps) {
  const { sku, result } = await resolve(params);
  if (isFailure(result)) {
    return (
      <section aria-labelledby="product-error-heading" className="flex flex-col gap-4">
        <h1 id="product-error-heading" className="text-3xl font-semibold">
          Product unavailable
        </h1>
        <p role="alert" className="max-w-prose text-base text-danger-strong">
          This product could not be loaded right now. Try again in a moment.
        </p>
        <a href={productHref(sku)} className="text-accent-strong underline">
          Try again
        </a>
      </section>
    );
  }
  if (result.sku !== sku) {
    redirect(productHref(result.sku));
  }
  return <ProductDetail product={result} />;
}
