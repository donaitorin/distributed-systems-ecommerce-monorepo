import type { ReactNode } from "react";
import { cn } from "../../lib/cn";

export type TableColumn<Row> = {
  key: string;
  header: string;
  cell: (row: Row) => ReactNode;
  align?: "left" | "right";
};

export type TableProps<Row> = {
  caption: string;
  columns: readonly TableColumn<Row>[];
  rows: readonly Row[];
  getRowKey: (row: Row) => string;
  loading?: boolean;
  error?: string;
  emptyMessage?: string;
  skeletonRowCount?: number;
};

const ALIGN_CLASSES = { left: "text-left", right: "text-right" } as const;

export function Table<Row>({
  caption,
  columns,
  rows,
  getRowKey,
  loading = false,
  error,
  emptyMessage = "No results found.",
  skeletonRowCount = 5,
}: TableProps<Row>) {
  const cellClasses = (column: TableColumn<Row>) =>
    cn("px-4 py-3 text-sm", ALIGN_CLASSES[column.align ?? "left"]);

  const messageRow = (message: string, role?: "alert") => (
    <tr>
      <td colSpan={columns.length} className="px-4 py-8 text-center text-sm" role={role}>
        {message}
      </td>
    </tr>
  );

  const body = () => {
    if (loading) {
      return Array.from({ length: skeletonRowCount }, (_, index) => (
        <tr key={index} className="border-t border-border">
          {columns.map((column) => (
            <td key={column.key} className={cellClasses(column)}>
              <span className="block h-4 animate-pulse rounded-sm bg-muted" aria-hidden="true" />
            </td>
          ))}
        </tr>
      ));
    }
    if (error) {
      return messageRow(error, "alert");
    }
    if (rows.length === 0) {
      return messageRow(emptyMessage);
    }
    return rows.map((row) => (
      <tr key={getRowKey(row)} className="border-t border-border">
        {columns.map((column) => (
          <td key={column.key} className={cellClasses(column)}>
            {column.cell(row)}
          </td>
        ))}
      </tr>
    ));
  };

  return (
    <div
      role="region"
      aria-label={caption}
      // eslint-disable-next-line jsx-a11y/no-noninteractive-tabindex -- keyboard users must be able to scroll wide tables
      tabIndex={0}
      className="overflow-x-auto rounded-md border border-border"
    >
      <table className="w-full border-collapse" aria-busy={loading || undefined}>
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-muted">
          <tr>
            {columns.map((column) => (
              <th key={column.key} scope="col" className={cn(cellClasses(column), "font-semibold")}>
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{body()}</tbody>
      </table>
      {loading ? (
        <p role="status" className="sr-only">
          Loading
        </p>
      ) : null}
    </div>
  );
}
