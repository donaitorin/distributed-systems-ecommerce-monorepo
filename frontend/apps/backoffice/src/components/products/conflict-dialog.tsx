"use client";

import { Button, Modal } from "@ecommerce/ui";

export type Difference = {
  label: string;
  mine: string;
  latest: string;
};

export type ConflictDialogProps = {
  open: boolean;
  differences: readonly Difference[];
  latestAvailable: boolean;
  onLoadLatest: () => void;
  onKeepMine: () => void;
  onDismiss: () => void;
};

export function ConflictDialog({
  open,
  differences,
  latestAvailable,
  onLoadLatest,
  onKeepMine,
  onDismiss,
}: ConflictDialogProps) {
  return (
    <Modal
      open={open}
      onOpenChange={(next) => {
        if (!next) {
          onDismiss();
        }
      }}
      title="This product was changed by someone else"
      description={
        latestAvailable
          ? "Someone saved a newer version while you were editing. Your input is still in the form and nothing was saved."
          : "Someone saved a newer version while you were editing, and the latest version could not be loaded. Your input is still in the form and nothing was saved. Reload the page to see the latest version."
      }
      footer={
        latestAvailable ? (
          <>
            <Button variant="secondary" onClick={onLoadLatest}>
              Discard my changes and load the latest
            </Button>
            <Button onClick={onKeepMine}>Keep my changes and overwrite</Button>
          </>
        ) : (
          <Button variant="secondary" onClick={onDismiss}>
            Close
          </Button>
        )
      }
    >
      {differences.length > 0 ? (
        <div className="flex flex-col gap-3">
          <p className="text-sm font-medium">Fields that differ:</p>
          <ul className="flex list-none flex-col gap-3 p-0">
            {differences.map((difference) => (
              <li key={difference.label} className="rounded-md border border-border p-3">
                <p className="text-sm font-semibold">{difference.label}</p>
                <dl className="mt-1 flex flex-col gap-1 text-sm">
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-secondary">Your value:</dt>
                    <dd className="break-words">{difference.mine || "Empty"}</dd>
                  </div>
                  <div className="flex flex-wrap gap-x-2">
                    <dt className="text-secondary">Current value:</dt>
                    <dd className="break-words">{difference.latest || "Empty"}</dd>
                  </div>
                </dl>
              </li>
            ))}
          </ul>
        </div>
      ) : latestAvailable ? (
        <p className="text-sm">The other change did not touch the fields you edited, for example it was an image change.</p>
      ) : null}
    </Modal>
  );
}
