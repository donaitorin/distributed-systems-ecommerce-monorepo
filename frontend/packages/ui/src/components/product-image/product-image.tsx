"use client";

import { useCallback, useState } from "react";
import { cn } from "../../lib/cn";

export type ProductImageProps = {
  thumbnailUrl: string | null;
  imageUrl: string | null;
  alt: string;
  sizes?: string;
  priority?: boolean;
  className?: string;
};

const THUMBNAIL_WIDTH = 400;
const IMAGE_WIDTH = 1200;
const DEFAULT_SIZES =
  "(min-width: 80rem) 25vw, (min-width: 64rem) 33vw, (min-width: 40rem) 50vw, 100vw";

export function ProductImagePlaceholder({ label }: { label: string }) {
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 400 400"
      role="img"
      aria-label={label}
      className="size-full bg-surface-2 text-secondary"
    >
      <rect width="400" height="400" fill="currentColor" fillOpacity="0.08" />
      <g fill="none" stroke="currentColor" strokeWidth="12" strokeLinecap="round" strokeLinejoin="round">
        <rect x="104" y="120" width="192" height="160" rx="16" />
        <circle cx="156" cy="172" r="16" />
        <path d="m112 264 56-56 40 40 32-32 48 48" />
      </g>
    </svg>
  );
}

function sourceSet(thumbnailUrl: string | null, imageUrl: string | null): string {
  const candidates = [
    thumbnailUrl ? `${thumbnailUrl} ${THUMBNAIL_WIDTH}w` : null,
    imageUrl ? `${imageUrl} ${IMAGE_WIDTH}w` : null,
  ];
  return candidates.filter((entry) => entry !== null).join(", ");
}

export function ProductImage({
  thumbnailUrl,
  imageUrl,
  alt,
  sizes = DEFAULT_SIZES,
  priority = false,
  className,
}: ProductImageProps) {
  const source = thumbnailUrl ?? imageUrl;
  const sourceKey = `${thumbnailUrl ?? ""}|${imageUrl ?? ""}`;
  const [failedKey, setFailedKey] = useState<string | null>(null);
  const showPlaceholder = source === null || failedKey === sourceKey;
  const detectEarlyFailure = useCallback(
    (image: HTMLImageElement | null) => {
      if (image?.complete && image.naturalWidth === 0 && image.currentSrc !== "") {
        setFailedKey(sourceKey);
      }
    },
    [sourceKey],
  );

  return (
    <div className={cn("aspect-square w-full overflow-hidden bg-surface-2", className)}>
      {showPlaceholder ? (
        <ProductImagePlaceholder label={alt} />
      ) : (
        <img
          ref={detectEarlyFailure}
          src={source}
          srcSet={sourceSet(thumbnailUrl, imageUrl)}
          sizes={sizes}
          alt={alt}
          loading={priority ? "eager" : "lazy"}
          fetchPriority={priority ? "high" : "auto"}
          decoding="async"
          onError={() => {
            setFailedKey(sourceKey);
          }}
          className="size-full object-cover"
        />
      )}
    </div>
  );
}
