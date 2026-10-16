"use client";

import { useEffect, useId, useState } from "react";
import { Button, ConfirmDialog, ProductImage } from "@ecommerce/ui";
import { isSessionFailure } from "../../lib/failure";
import { sameOriginMedia } from "../../lib/media";
import { imageFailureMessage, validateImageFile, ACCEPTED_IMAGE_TYPES, MAX_IMAGE_BYTES } from "../../lib/messages";
import { LOGIN_PATH } from "../../lib/paths";
import type { Product } from "../../lib/types";
import type { UploadResult } from "../../lib/upload-client";
import type { SaveResult } from "../../server/product-actions";
import { useNotify } from "../notifications";
import { useNavigation } from "../navigation";

export type ProductImageEditorProps = {
  product: Pick<Product, "sku" | "name" | "image_url" | "thumbnail_url">;
  etag: string;
  uploadImage: (sku: string, etag: string, file: File) => Promise<UploadResult>;
  removeImage: (sku: string, etag: string) => Promise<SaveResult>;
  onChanged: (product: Product, etag: string) => void;
};

const MEGABYTES = MAX_IMAGE_BYTES / (1024 * 1024);

export function ProductImageEditor({ product, etag, uploadImage, removeImage, onChanged }: ProductImageEditorProps) {
  const router = useNavigation();
  const notify = useNotify();
  const inputId = useId();
  const [selection, setSelection] = useState<{ file: File; url: string } | null>(null);
  const [fileError, setFileError] = useState<string>();
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState<"upload" | "remove" | null>(null);
  const [confirmingRemoval, setConfirmingRemoval] = useState(false);
  const [removalError, setRemovalError] = useState<string>();
  const [inputKey, setInputKey] = useState(0);
  const hasImage = Boolean(product.image_url);

  useEffect(() => {
    const url = selection?.url;
    return () => {
      if (url) {
        URL.revokeObjectURL(url);
      }
    };
  }, [selection]);

  const file = selection?.file ?? null;
  const preview = selection?.url ?? null;

  const clearSelection = () => {
    setSelection(null);
    setFileError(undefined);
    setInputKey((key) => key + 1);
  };

  const sessionExpired = () => {
    router.push(`${LOGIN_PATH}?reason=expired`);
  };

  const upload = async () => {
    if (!file) {
      return;
    }
    setBusy("upload");
    setStatus("Uploading the image");
    const result = await uploadImage(product.sku, etag, file);
    setBusy(null);
    if (result.ok) {
      clearSelection();
      onChanged(result.product, result.etag);
      setStatus("Image uploaded");
      notify({ title: "Image uploaded", description: `The image of ${product.sku} was updated.`, variant: "success" });
      return;
    }
    if (isSessionFailure(result)) {
      sessionExpired();
      return;
    }
    const message = imageFailureMessage(result);
    setFileError(message);
    setStatus("");
    notify({ title: "The image was not uploaded", description: message, variant: "error" });
  };

  const remove = async () => {
    setBusy("remove");
    const result = await removeImage(product.sku, etag);
    setBusy(null);
    if (result.ok) {
      setConfirmingRemoval(false);
      setRemovalError(undefined);
      onChanged(result.product, result.etag);
      setStatus("Image removed");
      notify({ title: "Image removed", description: `${product.sku} has no image now.`, variant: "success" });
      return;
    }
    if (isSessionFailure(result)) {
      sessionExpired();
      return;
    }
    const message = imageFailureMessage(result);
    setRemovalError(message);
    notify({ title: "The image was not removed", description: message, variant: "error" });
  };

  const current = sameOriginMedia(product.image_url);
  const currentThumbnail = sameOriginMedia(product.thumbnail_url);

  return (
    <section aria-labelledby={`${inputId}-heading`} className="flex max-w-xl flex-col gap-4">
      <h2 id={`${inputId}-heading`} className="text-xl font-semibold">
        Image
      </h2>
      <div className="w-48 overflow-hidden rounded-md border border-border">
        <ProductImage
          thumbnailUrl={preview ?? currentThumbnail}
          imageUrl={preview ?? current}
          alt={preview ? "Preview of the selected image" : hasImage ? `Image of ${product.name}` : `${product.name} has no image`}
          sizes="192px"
        />
      </div>
      <div className="flex flex-col gap-1">
        <label htmlFor={inputId} className="text-sm font-medium text-primary">
          {hasImage ? "Replace the image" : "Upload an image"}
        </label>
        <input
          key={inputKey}
          id={inputId}
          type="file"
          accept={ACCEPTED_IMAGE_TYPES.join(",")}
          aria-invalid={fileError ? true : undefined}
          aria-describedby={`${inputId}-hint${fileError ? ` ${inputId}-error` : ""}`}
          className="min-h-11 text-sm"
          onChange={(event) => {
            const selected = event.target.files?.[0] ?? null;
            const problem = selected ? validateImageFile(selected) : null;
            setStatus("");
            if (selected && problem) {
              setSelection(null);
              setFileError(problem);
              return;
            }
            setFileError(undefined);
            setSelection(selected ? { file: selected, url: URL.createObjectURL(selected) } : null);
          }}
        />
        <p id={`${inputId}-hint`} className="text-sm text-secondary">
          JPEG, PNG or WebP, up to {MEGABYTES} MB.
        </p>
        {fileError ? (
          <p id={`${inputId}-error`} role="alert" className="text-sm font-medium text-danger-strong">
            {fileError}
          </p>
        ) : null}
      </div>
      <p role="status" className="text-sm text-secondary">
        {status}
      </p>
      <div className="flex flex-wrap gap-2">
        <Button
          loading={busy === "upload"}
          disabled={!file || busy !== null}
          onClick={() => {
            void upload();
          }}
        >
          Upload image
        </Button>
        {file ? (
          <Button variant="secondary" onClick={clearSelection} disabled={busy !== null}>
            Clear selection
          </Button>
        ) : null}
        {hasImage ? (
          <Button
            variant="danger"
            disabled={busy !== null}
            onClick={() => {
              setRemovalError(undefined);
              setConfirmingRemoval(true);
            }}
          >
            Remove image
          </Button>
        ) : null}
      </div>
      <ConfirmDialog
        open={confirmingRemoval}
        onOpenChange={setConfirmingRemoval}
        title="Remove this image?"
        description="The product will show the placeholder until you upload another image."
        confirmLabel="Remove image"
        variant="danger"
        pending={busy === "remove"}
        error={removalError}
        onConfirm={() => {
          void remove();
        }}
      />
    </section>
  );
}
