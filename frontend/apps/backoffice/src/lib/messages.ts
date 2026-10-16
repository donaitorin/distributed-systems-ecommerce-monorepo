import type { Failure } from "./failure";

export const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
export const ACCEPTED_IMAGE_TYPES = ["image/jpeg", "image/png", "image/webp"] as const;
const MEGABYTES = 1024 * 1024;

export function describeRetry(seconds: number): string {
  if (seconds < 90) {
    return `${seconds} ${seconds === 1 ? "second" : "seconds"}`;
  }
  const minutes = Math.ceil(seconds / 60);
  return `${minutes} minutes`;
}

function retrySuffix(failure: Failure): string {
  return failure.retryAfterSeconds === undefined ? "" : ` Try again in ${describeRetry(failure.retryAfterSeconds)}.`;
}

function unavailable(failure: Failure): string {
  return `The service is not available right now.${retrySuffix(failure) || " Try again in a moment."}`;
}

export function saveFailureMessage(failure: Failure): string {
  switch (failure.status) {
    case 404:
      return "This product no longer exists. It may have been deleted by someone else.";
    case 409:
      return "That SKU is already in use, possibly by a deleted product. SKUs of deleted products stay reserved, so choose a different SKU.";
    case 422:
      return "Some fields need attention. Check the highlighted fields and try again.";
    case 428:
      return "The page is out of date. Reload it and try again.";
    case 429:
      return `Too many requests.${retrySuffix(failure) || " Wait a moment and try again."}`;
    default:
      return failure.status === null || failure.status >= 500
        ? unavailable(failure)
        : (failure.detail ?? failure.title);
  }
}

export function deleteFailureMessage(failure: Failure): string {
  switch (failure.status) {
    case 404:
      return "This product was already deleted.";
    case 412:
      return "The product was changed by someone else since you opened it. Reload the list and try again.";
    default:
      return failure.status === null || failure.status >= 500
        ? unavailable(failure)
        : (failure.detail ?? failure.title);
  }
}

export function imageFailureMessage(failure: Failure): string {
  switch (failure.status) {
    case 404:
      return "This product has no image, or it no longer exists.";
    case 412:
      return "The product was changed by someone else. Reload the latest version and try again.";
    case 413:
      return `The image is larger than ${MAX_IMAGE_BYTES / MEGABYTES} MB. Choose a smaller file.`;
    case 415:
      return "That file type is not supported. Upload a JPEG, PNG or WebP image.";
    case 422:
      return "The image could not be used. It may be corrupted, too large in pixels (over 25 megapixels), or not a real image.";
    case 503:
      return `Image storage is not available right now.${retrySuffix(failure) || " Try again in a moment."}`;
    default:
      return failure.status === null || failure.status >= 500
        ? unavailable(failure)
        : (failure.detail ?? failure.title);
  }
}

export function validateImageFile(file: { size: number; type: string }): string | null {
  if (!(ACCEPTED_IMAGE_TYPES as readonly string[]).includes(file.type)) {
    return "That file type is not supported. Upload a JPEG, PNG or WebP image.";
  }
  if (file.size > MAX_IMAGE_BYTES) {
    return `The image is larger than ${MAX_IMAGE_BYTES / MEGABYTES} MB. Choose a smaller file.`;
  }
  if (file.size === 0) {
    return "The file is empty.";
  }
  return null;
}
