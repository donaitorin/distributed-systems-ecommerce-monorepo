import { redirect } from "next/navigation";
import { toSearchParams, type SearchParamsRecord } from "@ecommerce/web-core";
import { PRODUCTS_PATH } from "../lib/paths";

type HomePageProps = {
  searchParams: Promise<SearchParamsRecord>;
};

export default async function HomePage({ searchParams }: HomePageProps) {
  const query = toSearchParams(await searchParams).toString();
  return redirect(query ? `${PRODUCTS_PATH}?${query}` : PRODUCTS_PATH);
}
