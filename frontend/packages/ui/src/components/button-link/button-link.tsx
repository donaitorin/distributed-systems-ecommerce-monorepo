import type { ComponentProps } from "react";
import { cn } from "../../lib/cn";
import { buttonClasses, type ButtonVariant } from "../button/button-classes";

export type ButtonLinkProps = ComponentProps<"a"> & {
  variant?: ButtonVariant;
};

export function ButtonLink({ variant = "primary", className, children, ...props }: ButtonLinkProps) {
  return (
    <a className={cn(buttonClasses(variant), className)} {...props}>
      {children}
    </a>
  );
}
