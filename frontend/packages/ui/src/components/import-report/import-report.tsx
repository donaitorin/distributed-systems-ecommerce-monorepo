import type { ReactNode } from "react";
import { AlertIcon, InfoIcon } from "../../lib/icons";
import { Button } from "../button/button";
import { ButtonLink } from "../button-link/button-link";
import { Select, type SelectOption } from "../select/select";
import { Table, type TableColumn } from "../table/table";

export type ImportReportCounts = {
  rowsRead: number;
  importable: number;
  toCreate: number;
  toUpdate: number;
  toRestore: number;
  unchanged: number;
  errors: number;
  warnings: number;
};

export type ReportUnknownCategory = {
  value: string;
  rows: number;
  suggestion: string | null;
};

export type ReportProblem = {
  id: string;
  severity: "error" | "warning";
  row: number | null;
  column: string | null;
  value: string | null;
  reason: string;
};

export type SeverityFilter = "all" | "error" | "warning";

export type ImportReportProps = {
  counts: ImportReportCounts;
  truncated?: boolean;
  unknownCategories: readonly ReportUnknownCategory[];
  renderCategoryAction?: (category: ReportUnknownCategory) => ReactNode;
  problems: readonly ReportProblem[];
  severityFilter: SeverityFilter;
  onSeverityFilterChange: (filter: SeverityFilter) => void;
  hasMoreProblems: boolean;
  onLoadMoreProblems: () => void;
  loadingProblems?: boolean;
  problemsError?: string;
  problemsDownloadHref?: string;
};

const FILTER_OPTIONS: readonly SelectOption[] = [
  { value: "all", label: "Errors and warnings" },
  { value: "error", label: "Errors only" },
  { value: "warning", label: "Warnings only" },
];

const NUMBER_FORMAT = new Intl.NumberFormat("en-US");

function SeverityLabel({ severity }: { severity: ReportProblem["severity"] }) {
  return severity === "error" ? (
    <span className="inline-flex items-center gap-1 font-medium text-danger-strong">
      <AlertIcon />
      Error
    </span>
  ) : (
    <span className="inline-flex items-center gap-1 font-medium text-warning-strong">
      <InfoIcon />
      Warning
    </span>
  );
}

const COLUMNS: readonly TableColumn<ReportProblem>[] = [
  { key: "row", header: "Row", cell: (problem) => problem.row ?? "File", align: "right" },
  { key: "severity", header: "Severity", cell: (problem) => <SeverityLabel severity={problem.severity} /> },
  { key: "column", header: "Column", cell: (problem) => problem.column ?? "" },
  { key: "value", header: "Value", cell: (problem) => <span className="break-all">{problem.value ?? ""}</span> },
  { key: "reason", header: "Problem", cell: (problem) => problem.reason },
];

function Count({ label, value }: { label: string; value: number }) {
  return (
    <div className="flex flex-col gap-1 rounded-md border border-border bg-surface p-3">
      <dt className="text-sm text-secondary">{label}</dt>
      <dd className="text-2xl font-semibold text-primary">{NUMBER_FORMAT.format(value)}</dd>
    </div>
  );
}

export function ImportReport({
  counts,
  truncated = false,
  unknownCategories,
  renderCategoryAction,
  problems,
  severityFilter,
  onSeverityFilterChange,
  hasMoreProblems,
  onLoadMoreProblems,
  loadingProblems = false,
  problemsError,
  problemsDownloadHref,
}: ImportReportProps) {
  return (
    <div className="flex flex-col gap-8">
      <section aria-labelledby="report-summary" className="flex flex-col gap-3">
        <h2 id="report-summary" className="text-xl font-semibold">
          Summary
        </h2>
        <p className="text-sm text-secondary">
          {NUMBER_FORMAT.format(counts.rowsRead)} rows read, {NUMBER_FORMAT.format(counts.importable)} can be imported.
        </p>
        <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          <Count label="To create" value={counts.toCreate} />
          <Count label="To update" value={counts.toUpdate} />
          <Count label="To restore" value={counts.toRestore} />
          <Count label="Unchanged" value={counts.unchanged} />
          <Count label="Errors" value={counts.errors} />
          <Count label="Warnings" value={counts.warnings} />
        </dl>
        {truncated ? (
          <p className="text-sm font-medium text-warning-strong">
            The file has more problems than the report lists. The counts are exact; the list stops at its limit.
          </p>
        ) : null}
      </section>
      {unknownCategories.length > 0 ? (
        <section aria-labelledby="report-categories" className="flex flex-col gap-3">
          <h2 id="report-categories" className="text-xl font-semibold">
            Unknown categories
          </h2>
          <p className="text-sm text-secondary">
            Rows with these categories are errors. Create the category, or fix the name in the file.
          </p>
          <ul className="flex list-none flex-col gap-3 p-0">
            {unknownCategories.map((category) => (
              <li
                key={category.value}
                className="flex flex-col gap-2 rounded-md border border-border bg-surface p-4 sm:flex-row sm:items-center sm:justify-between"
              >
                <div className="flex flex-col gap-1">
                  <p className="font-medium break-all">{category.value}</p>
                  <p className="text-sm text-secondary">
                    {category.rows === 1 ? "1 row" : `${NUMBER_FORMAT.format(category.rows)} rows`}
                    {category.suggestion ? `. Closest existing category: ${category.suggestion}` : ""}
                  </p>
                </div>
                {renderCategoryAction?.(category)}
              </li>
            ))}
          </ul>
        </section>
      ) : null}
      <section aria-labelledby="report-problems" className="flex flex-col gap-4">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <h2 id="report-problems" className="text-xl font-semibold">
            Problems
          </h2>
          {problemsDownloadHref ? (
            <ButtonLink variant="secondary" href={problemsDownloadHref} download>
              Download problems.csv
            </ButtonLink>
          ) : null}
        </div>
        <div className="max-w-xs">
          <Select
            label="Show"
            options={FILTER_OPTIONS}
            value={severityFilter}
            onValueChange={(value) => {
              onSeverityFilterChange(value as SeverityFilter);
            }}
          />
        </div>
        <Table
          caption="Problems found in the file"
          columns={COLUMNS}
          rows={problems}
          getRowKey={(problem) => problem.id}
          loading={loadingProblems && problems.length === 0}
          error={problemsError}
          emptyMessage="No problems to show."
          renderCard={(problem) => (
            <div className="flex flex-col gap-1 text-sm">
              <p className="flex flex-wrap items-center gap-2">
                <SeverityLabel severity={problem.severity} />
                <span className="text-secondary">{problem.row === null ? "File" : `Row ${problem.row}`}</span>
              </p>
              {problem.column ? <p className="text-secondary">Column: {problem.column}</p> : null}
              {problem.value ? <p className="break-all">Value: {problem.value}</p> : null}
              <p>{problem.reason}</p>
            </div>
          )}
        />
        {hasMoreProblems ? (
          <div>
            <Button variant="secondary" loading={loadingProblems} onClick={onLoadMoreProblems}>
              Show more problems
            </Button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
