"use client";

import { useEffect, useState } from "react";
import { useInfiniteQuery, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Button,
  ButtonLink,
  ConfirmDialog,
  formatBytes,
  ImportReport,
  type ReportProblem,
  type SeverityFilter,
} from "@ecommerce/ui";
import { isSessionFailure } from "../../lib/failure";
import type { ImportRequestError} from "../../lib/import-client";
import { problemsCsvUrl, unwrap } from "../../lib/import-client";
import { announcementFor, nextPollDelay, progressFraction, reportable, withPollCount, type PolledImport } from "../../lib/import-status";
import { importActionFailureMessage, importLoadFailureMessage } from "../../lib/messages";
import { LOGIN_PATH, PRODUCTS_PATH, ZONE_PATH } from "../../lib/paths";
import type { ImportView } from "../../lib/types";
import { useNavigation } from "../navigation";
import { useNotify } from "../notifications";
import type { ImportActions, ImportApi } from "./import-api";
import { UnknownCategoryAction } from "./unknown-category-action";

export type ImportPanelProps = {
  importId: string;
  existing: boolean;
  api: ImportApi;
  actions: ImportActions;
  onRestart: () => void;
};

const PROBLEMS_PAGE_SIZE = 50;

export function ImportPanel({ importId, existing, api, actions, onRestart }: ImportPanelProps) {
  const navigation = useNavigation();
  const notify = useNotify();
  const queryClient = useQueryClient();
  const key = ["import", importId] as const;
  const [severity, setSeverity] = useState<SeverityFilter>("all");
  const [available, setAvailable] = useState<readonly string[]>([]);
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState<"confirm" | "revalidate" | null>(null);
  const [actionError, setActionError] = useState<string>();

  const query = useQuery<PolledImport, ImportRequestError>({
    queryKey: key,
    queryFn: async () =>
      withPollCount(unwrap(await api.fetchImport(importId)).import, queryClient.getQueryData<PolledImport>(key)),
    refetchInterval: (current) => nextPollDelay(current.state.data),
  });
  const data = query.data;
  const loadFailure = query.error?.failure;

  useEffect(() => {
    if (loadFailure && isSessionFailure(loadFailure)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
    }
  }, [loadFailure, navigation]);

  const showReport = Boolean(data && data.summary && reportable(data.status));
  const problems = useInfiniteQuery({
    queryKey: ["import", importId, "problems", severity, data?.validated_at ?? ""],
    queryFn: async ({ pageParam }) =>
      unwrap(
        await api.fetchProblems(importId, {
          severity: severity === "all" ? null : severity,
          cursor: pageParam,
          limit: PROBLEMS_PAGE_SIZE,
        }),
      ).page,
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor ?? null,
    enabled: showReport,
  });

  const adopt = (next: ImportView) => {
    setActionError(undefined);
    queryClient.setQueryData<PolledImport>(key, { ...next, polls: 0 });
  };

  const run = async (kind: "confirm" | "revalidate") => {
    setBusy(kind);
    setActionError(undefined);
    const result = await (kind === "confirm" ? actions.confirmImport(importId) : actions.revalidateImport(importId));
    setBusy(null);
    if (result.ok) {
      setConfirming(false);
      setAvailable([]);
      adopt(result.import);
      return;
    }
    if (isSessionFailure(result)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    const message = importActionFailureMessage(result);
    setActionError(message);
    notify({
      title: kind === "confirm" ? "The import was not started" : "The file was not validated again",
      description: message,
      variant: "error",
    });
    if (result.status === 409) {
      void query.refetch();
    }
  };

  if (loadFailure && !data) {
    return (
      <div className="flex flex-col gap-4">
        <p role="alert" className="text-base font-medium text-danger-strong">
          {importLoadFailureMessage(loadFailure)}
        </p>
        <div className="flex flex-wrap gap-2">
          {loadFailure.status === 404 ? null : (
            <Button
              variant="secondary"
              onClick={() => {
                void query.refetch();
              }}
            >
              Try again
            </Button>
          )}
          <Button variant="secondary" onClick={onRestart}>
            Upload another file
          </Button>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <p role="status" className="text-base text-secondary">
        Loading the import
      </p>
    );
  }

  const summary = data.summary;
  const importable = summary?.importable_rows ?? 0;
  const settledValidation = data.status === "validated" || data.status === "rejected";
  const categoriesCreated = available.length > 0;
  const fraction = progressFraction(data);

  const items: ReportProblem[] = (problems.data?.pages ?? []).flatMap((page, pageIndex) =>
    page.items.map((problem, index) => ({
      id: `${pageIndex}-${index}`,
      severity: problem.severity === "warning" ? "warning" : "error",
      row: problem.row ?? null,
      column: problem.column ?? null,
      value: problem.value ?? null,
      reason: problem.reason,
    })),
  );

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-2">
        <h2 className="text-xl font-semibold break-all">{data.filename}</h2>
        <p className="text-sm text-secondary">
          {formatBytes(data.size_bytes)}. Status: {data.status}.
        </p>
        {existing ? (
          <p className="text-sm text-secondary">This file was uploaded before. This is its latest state.</p>
        ) : null}
        <p role="status" aria-live="polite" className="text-base font-medium">
          {announcementFor(data)}
        </p>
        {loadFailure ? (
          <p role="alert" className="text-sm font-medium text-danger-strong">
            {importLoadFailureMessage(loadFailure)}
          </p>
        ) : null}
        {fraction !== null && (data.status === "queued" || data.status === "processing") ? (
          <progress
            className="w-full max-w-md"
            aria-label="Import progress"
            value={data.progress.processed_rows}
            max={importable}
          />
        ) : null}
      </div>

      {data.status === "failed" ? (
        <div className="flex flex-col gap-3">
          <p role="alert" className="text-base font-medium text-danger-strong">
            {data.failure_reason ?? "The import failed."}
          </p>
          <div>
            <Button variant="secondary" onClick={onRestart}>
              Upload the file again
            </Button>
          </div>
        </div>
      ) : null}

      {data.status === "completed" ? (
        <div className="flex flex-col gap-3">
          <dl className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {(
              [
                ["Created", data.progress.created_rows],
                ["Updated", data.progress.updated_rows],
                ["Restored", data.progress.restored_rows],
                ["Unchanged", data.progress.unchanged_rows],
              ] as const
            ).map(([label, value]) => (
              <div key={label} className="flex flex-col gap-1 rounded-md border border-border bg-surface p-3">
                <dt className="text-sm text-secondary">{label}</dt>
                <dd className="text-2xl font-semibold">{value}</dd>
              </div>
            ))}
          </dl>
          <div className="flex flex-wrap gap-2">
            <ButtonLink href={`${ZONE_PATH}${PRODUCTS_PATH}`}>View products</ButtonLink>
            <Button variant="secondary" onClick={onRestart}>
              Import another file
            </Button>
          </div>
        </div>
      ) : null}

      {settledValidation ? (
        <div className="flex flex-col gap-3">
          {data.status === "validated" && importable === 0 ? (
            <p className="text-base">No rows can be imported. Fix the problems, then validate again or upload another file.</p>
          ) : null}
          {categoriesCreated ? (
            <p className="text-base font-medium">Categories were created. Validate the file again so its rows can use them.</p>
          ) : null}
          {actionError ? (
            <p role="alert" className="text-sm font-medium text-danger-strong">
              {actionError}
            </p>
          ) : null}
          <div className="flex flex-wrap gap-2">
            {data.status === "validated" && importable > 0 ? (
              <Button
                variant={categoriesCreated ? "secondary" : "primary"}
                disabled={busy !== null}
                onClick={() => {
                  setActionError(undefined);
                  setConfirming(true);
                }}
              >
                {`Import ${importable} ${importable === 1 ? "row" : "rows"}`}
              </Button>
            ) : null}
            <Button
              variant={categoriesCreated ? "primary" : "secondary"}
              loading={busy === "revalidate"}
              disabled={busy === "confirm"}
              onClick={() => {
                void run("revalidate");
              }}
            >
              Validate again
            </Button>
            <Button variant="secondary" onClick={onRestart} disabled={busy !== null}>
              Upload another file
            </Button>
          </div>
        </div>
      ) : null}

      {showReport && summary ? (
        <ImportReport
          counts={{
            rowsRead: summary.rows_read,
            importable,
            toCreate: summary.to_create,
            toUpdate: summary.to_update,
            toRestore: summary.to_restore,
            unchanged: summary.unchanged,
            errors: summary.error_count,
            warnings: summary.warning_count,
          }}
          truncated={summary.truncated}
          unknownCategories={summary.unknown_categories.map((category) => ({
            value: category.value,
            rows: category.rows,
            suggestion: category.suggestion ?? null,
          }))}
          renderCategoryAction={
            data.status === "validated" || data.status === "rejected"
              ? (category) => (
                  <UnknownCategoryAction
                    category={category}
                    createCategory={actions.createCategory}
                    onAvailable={(value) => {
                      setAvailable((current) => (current.includes(value) ? current : [...current, value]));
                    }}
                  />
                )
              : undefined
          }
          problems={items}
          severityFilter={severity}
          onSeverityFilterChange={setSeverity}
          hasMoreProblems={Boolean(problems.hasNextPage)}
          onLoadMoreProblems={() => {
            void problems.fetchNextPage();
          }}
          loadingProblems={problems.isFetching}
          problemsError={problems.isError ? "The problems could not be loaded. Try again." : undefined}
          problemsDownloadHref={problemsCsvUrl(importId)}
        />
      ) : null}

      <ConfirmDialog
        open={confirming}
        onOpenChange={setConfirming}
        title={`Import ${importable} ${importable === 1 ? "product" : "products"}?`}
        description={`${importable} valid ${importable === 1 ? "row is" : "rows are"} written to the catalog.${
          summary && summary.error_rows > 0 ? ` ${summary.error_rows} ${summary.error_rows === 1 ? "row has" : "rows have"} errors and ${summary.error_rows === 1 ? "is" : "are"} skipped.` : ""
        } Products that already exist are updated.`}
        confirmLabel={`Import ${importable} ${importable === 1 ? "row" : "rows"}`}
        pending={busy === "confirm"}
        error={actionError}
        onConfirm={() => {
          void run("confirm");
        }}
      />
    </div>
  );
}
