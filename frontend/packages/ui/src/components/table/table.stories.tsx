import type { Meta, StoryObj } from "@storybook/nextjs-vite";
import { PriceTag } from "../price-tag/price-tag";
import { StockBadge } from "../stock-badge/stock-badge";
import { Table, type TableColumn } from "./table";

type Product = { sku: string; name: string; price: string; stock: number };

const COLUMNS: readonly TableColumn<Product>[] = [
  { key: "sku", header: "SKU", cell: (product) => product.sku },
  { key: "name", header: "Name", cell: (product) => product.name },
  { key: "price", header: "Price", cell: (product) => <PriceTag amount={product.price} />, align: "right" },
  { key: "stock", header: "Stock", cell: (product) => <StockBadge stock={product.stock} /> },
];

const PRODUCTS: readonly Product[] = [
  { sku: "RS-001", name: "Running shoes", price: "59.00", stock: 24 },
  { sku: "TY-002", name: "Toy robot", price: "19.50", stock: 3 },
  { sku: "BK-003", name: "Paperback novel", price: "12.00", stock: 0 },
];

const meta = {
  title: "Components/Table",
  component: Table<Product>,
  parameters: { layout: "padded" },
  args: {
    caption: "Products",
    columns: COLUMNS,
    rows: PRODUCTS,
    getRowKey: (product: Product) => product.sku,
  },
} satisfies Meta<typeof Table<Product>>;

export default meta;
type Story = StoryObj<typeof meta>;

export const Default: Story = { args: { loading: false } };

export const Loading: Story = { args: { loading: true, rows: [] } };

export const Empty: Story = { args: { rows: [], emptyMessage: "No products match your filters." } };

export const Error: Story = { args: { rows: [], error: "Could not load products. Try again." } };

export const Mobile: Story = {
  globals: { viewport: { value: "mobile", isRotated: false } },
};

const renderCard = (product: Product) => (
  <div className="flex flex-col gap-2">
    <p className="font-semibold">{product.name}</p>
    <p className="text-sm text-secondary">{product.sku}</p>
    <div className="flex items-center justify-between">
      <PriceTag amount={product.price} />
      <StockBadge stock={product.stock} />
    </div>
  </div>
);

export const CardsOnMobile: Story = {
  args: { renderCard },
  globals: { viewport: { value: "mobile", isRotated: false } },
};

export const CardsLoading: Story = {
  args: { renderCard, loading: true, rows: [] },
  globals: { viewport: { value: "mobile", isRotated: false } },
};

export const CardsEmpty: Story = {
  args: { renderCard, rows: [], emptyMessage: "No products match your filters." },
  globals: { viewport: { value: "mobile", isRotated: false } },
};

export const CardsError: Story = {
  args: { renderCard, rows: [], error: "Could not load products. Try again." },
  globals: { viewport: { value: "mobile", isRotated: false } },
};
