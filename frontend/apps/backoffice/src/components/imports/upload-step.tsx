"use client";

import { useState } from "react";
import { FileDropzone } from "@ecommerce/ui";
import { formatBytes } from "@ecommerce/ui";
import { isSessionFailure } from "@ecommerce/web-core";
import { importUploadFailureMessage } from "../../lib/messages";
import { LOGIN_PATH } from "../../lib/paths";
import type { ImportView } from "../../lib/types";
import type { ImportApi } from "./import-api";
import { useNavigation } from "@ecommerce/web-core/client";

export type UploadStepProps = {
  maxBytes: number;
  api: ImportApi;
  onUploaded: (imported: ImportView, existing: boolean) => void;
};

export function UploadStep({ maxBytes, api, onUploaded }: UploadStepProps) {
  const navigation = useNavigation();
  const [uploading, setUploading] = useState<string | null>(null);
  const [error, setError] = useState<string>();

  const upload = async (file: File) => {
    setError(undefined);
    setUploading(file.name);
    const result = await api.uploadImportFile(file);
    setUploading(null);
    if (result.ok) {
      onUploaded(result.import, result.existing);
      return;
    }
    if (isSessionFailure(result)) {
      navigation.push(`${LOGIN_PATH}?reason=expired`);
      return;
    }
    setError(importUploadFailureMessage(result, maxBytes));
  };

  return (
    <FileDropzone
      label="Products CSV file"
      accept=".csv,text/csv"
      maxBytes={maxBytes}
      hint={`A CSV with a header row and the columns name, sku, price and stock (description, category and weight_kg are optional). Up to ${formatBytes(maxBytes)}. Nothing is imported until you confirm.`}
      loading={uploading !== null}
      loadingFileName={uploading ?? undefined}
      error={error}
      onFile={(file) => {
        void upload(file);
      }}
    />
  );
}
