import { ProductCardSkeleton } from "@ecommerce/ui";

const PLACEHOLDER_COUNT = 4;

export default function HomePage() {
  return (
    <section aria-labelledby="home-heading" className="flex flex-col gap-6">
      <h1 id="home-heading" className="text-3xl font-semibold">
        Welcome to the store
      </h1>
      <p className="max-w-prose text-base text-secondary">
        The catalog is on its way. Products will appear here soon.
      </p>
      <ul className="grid list-none grid-cols-1 gap-4 p-0 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
        {Array.from({ length: PLACEHOLDER_COUNT }, (_, index) => (
          <li key={index}>
            <ProductCardSkeleton />
          </li>
        ))}
      </ul>
    </section>
  );
}
