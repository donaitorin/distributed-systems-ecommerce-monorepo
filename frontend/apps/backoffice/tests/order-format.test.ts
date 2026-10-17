import { cancelReasonLabel, customerLabel, paymentStatusLabel, shortOrderId } from "../src/lib/order-format";

describe("order formats", () => {
  it.each([
    ["insufficient_stock", "Insufficient stock"],
    ["product_unavailable", "Product unavailable"],
    ["price_changed", "Price changed"],
    ["payment_failed", "Payment declined"],
    ["saga_timeout", "Payment timed out"],
    ["something_new", "something_new"],
    [null, "No reason recorded"],
  ])("labels the cancel reason %j as %s", (reason, label) => {
    expect(cancelReasonLabel(reason)).toBe(label);
  });

  it.each([
    ["PENDING", "Pending"],
    ["SUCCEEDED", "Succeeded"],
    ["FAILED", "Failed"],
    ["REFUNDED", "Refunded"],
    ["NEW", "NEW"],
  ])("labels the payment status %s as %s", (status, label) => {
    expect(paymentStatusLabel(status)).toBe(label);
  });

  it("shortens an order id", () => {
    expect(shortOrderId("6f1c2f64-3f0e-4c1a-9d52-7a1b8c9d0e21")).toBe("6F1C2F64");
  });

  it("shows the email of the customer, or the start of the customer id for old orders", () => {
    expect(customerLabel({ customer_email: "ada@example.com", customer_id: "0f6c1f0e-7a52" })).toBe("ada@example.com");
    expect(customerLabel({ customer_email: null, customer_id: "0f6c1f0e-7a52" })).toBe("Customer 0f6c1f0e");
  });
});
