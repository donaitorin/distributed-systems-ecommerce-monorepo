"use client";

import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { useQueryState } from "nuqs";
import { importUrlParser } from "../../lib/import-search";
import type { ImportView } from "../../lib/types";
import { DEFAULT_IMPORT_API, type ImportActions, type ImportApi } from "./import-api";
import { ImportPanel } from "./import-panel";
import { UploadStep } from "./upload-step";

export type ImportFlowProps = {
  maxBytes: number;
  actions: ImportActions;
  api?: ImportApi;
};

export function ImportFlow({ maxBytes, actions, api = DEFAULT_IMPORT_API }: ImportFlowProps) {
  const queryClient = useQueryClient();
  const [importId, setImportId] = useQueryState("import", importUrlParser.withOptions({ history: "push" }));
  const [existing, setExisting] = useState(false);

  if (importId === null) {
    return (
      <UploadStep
        maxBytes={maxBytes}
        api={api}
        onUploaded={(imported: ImportView, wasUploaded: boolean) => {
          queryClient.setQueryData(["import", imported.id], { ...imported, polls: 0 });
          setExisting(wasUploaded);
          void setImportId(imported.id);
        }}
      />
    );
  }

  return (
    <ImportPanel
      key={importId}
      importId={importId}
      existing={existing}
      api={api}
      actions={actions}
      onRestart={() => {
        setExisting(false);
        void setImportId(null);
      }}
    />
  );
}
