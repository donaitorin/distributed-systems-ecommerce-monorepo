"use client";

import { useId, useRef, useState, type DragEvent } from "react";
import { cn } from "../../lib/cn";
import { SpinnerIcon } from "../../lib/icons";
import { buttonClasses } from "../button/button-classes";
import { formatBytes } from "./format-bytes";

export type FileDropzoneProps = {
  label: string;
  onFile: (file: File) => void;
  accept?: string;
  maxBytes?: number;
  validate?: (file: File) => string | null;
  hint?: string;
  error?: string;
  disabled?: boolean;
  loading?: boolean;
  loadingFileName?: string;
};

function problemWith(file: File, maxBytes: number | undefined, validate: FileDropzoneProps["validate"]): string | null {
  if (file.size === 0) {
    return "The file is empty.";
  }
  if (maxBytes !== undefined && file.size > maxBytes) {
    return `The file is ${formatBytes(file.size)}, larger than the ${formatBytes(maxBytes)} limit.`;
  }
  return validate?.(file) ?? null;
}

export function FileDropzone({
  label,
  onFile,
  accept,
  maxBytes,
  validate,
  hint,
  error,
  disabled = false,
  loading = false,
  loadingFileName,
}: FileDropzoneProps) {
  const id = useId();
  const input = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [rejection, setRejection] = useState<string>();
  const inactive = disabled || loading;
  const message = rejection ?? error;
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint ? hintId : null, message ? errorId : null].filter(Boolean).join(" ");

  const receive = (files: readonly File[]) => {
    const [file] = files;
    if (files.length > 1) {
      setRejection("Choose one file at a time.");
      return;
    }
    if (!file) {
      return;
    }
    const problem = problemWith(file, maxBytes, validate);
    setRejection(problem ?? undefined);
    if (problem === null) {
      onFile(file);
    }
  };

  const drop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setDragging(false);
    if (!inactive) {
      receive([...event.dataTransfer.files]);
    }
  };

  return (
    <div className="flex flex-col gap-2">
      {/* eslint-disable-next-line jsx-a11y/no-noninteractive-element-interactions -- dragging is an extra; the file input is the accessible way */}
      <div
        role="group"
        aria-labelledby={`${id}-label`}
        aria-busy={loading || undefined}
        onDragOver={(event) => {
          event.preventDefault();
          if (!inactive) {
            setDragging(true);
          }
        }}
        onDragLeave={() => {
          setDragging(false);
        }}
        onDrop={drop}
        className={cn(
          "flex flex-col items-center gap-3 rounded-lg border-2 border-dashed p-6 text-center",
          dragging ? "border-accent-strong bg-accent-soft" : "border-border-strong bg-surface",
          error || rejection ? "border-danger-strong" : "",
        )}
      >
        <p id={`${id}-label`} className="text-base font-medium text-primary">
          {label}
        </p>
        {loading ? (
          <p role="status" className="flex items-center gap-2 text-sm text-secondary">
            <SpinnerIcon />
            {loadingFileName ? `Uploading ${loadingFileName}` : "Uploading"}
          </p>
        ) : (
          <>
            <input
              ref={input}
              id={id}
              type="file"
              accept={accept}
              disabled={inactive}
              aria-describedby={describedBy || undefined}
              aria-invalid={message ? true : undefined}
              className="peer sr-only"
              onChange={(event) => {
                receive([...(event.target.files ?? [])]);
                event.target.value = "";
              }}
            />
            <label
              htmlFor={id}
              className={cn(
                buttonClasses("secondary"),
                "cursor-pointer peer-focus-visible:outline-2 peer-focus-visible:outline-offset-2",
                inactive && "cursor-not-allowed text-tertiary",
              )}
            >
              Choose a file
            </label>
            <p className="text-sm text-secondary">{dragging ? "Drop the file to select it" : "or drag and drop it here"}</p>
          </>
        )}
      </div>
      {hint ? (
        <p id={hintId} className="text-sm text-secondary">
          {hint}
        </p>
      ) : null}
      {message ? (
        <p id={errorId} role="alert" className="text-sm font-medium text-danger-strong">
          {message}
        </p>
      ) : null}
    </div>
  );
}
