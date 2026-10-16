import { fireEvent, render, screen } from "@testing-library/react";
import { axe } from "jest-axe";
import { ProductImage } from "./product-image";

const THUMBNAIL = "/media/products/A/1-400.webp";
const FULL = "/media/products/A/1-1200.webp";

describe("ProductImage", () => {
  it("has no accessibility violations with an image and with the placeholder", async () => {
    const { container } = render(
      <>
        <ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" />
        <ProductImage thumbnailUrl={null} imageUrl={null} alt="Toy robot" />
      </>,
    );

    expect(await axe(container)).toHaveNoViolations();
  });

  it("offers the 400w and 1200w renditions in srcset", () => {
    render(<ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" />);
    const image = screen.getByRole("img", { name: "Running shoes" });

    expect(image).toHaveAttribute("srcset", `${THUMBNAIL} 400w, ${FULL} 1200w`);
    expect(image).toHaveAttribute("src", THUMBNAIL);
    expect(image).toHaveAttribute("sizes");
  });

  it("uses only the thumbnail when there is no full image", () => {
    render(<ProductImage thumbnailUrl={THUMBNAIL} imageUrl={null} alt="Running shoes" />);

    expect(screen.getByRole("img")).toHaveAttribute("srcset", `${THUMBNAIL} 400w`);
  });

  it("falls back to the full image when there is no thumbnail", () => {
    render(<ProductImage thumbnailUrl={null} imageUrl={FULL} alt="Running shoes" />);
    const image = screen.getByRole("img");

    expect(image).toHaveAttribute("src", FULL);
    expect(image).toHaveAttribute("srcset", `${FULL} 1200w`);
  });

  it("shows the labelled placeholder when both urls are null", () => {
    const { container } = render(<ProductImage thumbnailUrl={null} imageUrl={null} alt="Toy robot" />);

    expect(screen.getByRole("img", { name: "Toy robot" })).toBeInTheDocument();
    expect(container.querySelector("img")).toBeNull();
  });

  it("switches to the placeholder when the image fails to load", () => {
    const { container } = render(
      <ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" />,
    );

    fireEvent.error(container.querySelector("img") as HTMLImageElement);

    expect(container.querySelector("img")).toBeNull();
    expect(screen.getByRole("img", { name: "Running shoes" })).toBeInTheDocument();
  });

  it("tries the new image again when the urls change after a failure", () => {
    const { container, rerender } = render(
      <ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" />,
    );
    fireEvent.error(container.querySelector("img") as HTMLImageElement);

    rerender(
      <ProductImage thumbnailUrl="/other-400.webp" imageUrl="/other-1200.webp" alt="Running shoes" />,
    );

    expect(container.querySelector("img")).toHaveAttribute("src", "/other-400.webp");
  });

  it("loads lazily by default and eagerly with priority", () => {
    const { rerender } = render(
      <ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" />,
    );

    expect(screen.getByRole("img")).toHaveAttribute("loading", "lazy");

    rerender(<ProductImage thumbnailUrl={THUMBNAIL} imageUrl={FULL} alt="Running shoes" priority />);

    expect(screen.getByRole("img")).toHaveAttribute("loading", "eager");
    expect(screen.getByRole("img")).toHaveAttribute("fetchpriority", "high");
  });
});
