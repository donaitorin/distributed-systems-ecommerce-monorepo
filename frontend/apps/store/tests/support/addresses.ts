import type { Address } from "../../src/lib/addresses";

export const ADDRESS_ID = "0b8f6d2e-5c1a-4f7b-8e3d-9a2c4b6d8e10";
export const OTHER_ADDRESS_ID = "1c9a7e3f-6d2b-4a8c-9f4e-0b3d5c7e9f21";

export function address(overrides: Partial<Address> = {}): Address {
  return {
    id: ADDRESS_ID,
    recipient_name: "Ada Lovelace",
    line1: "12 Analytical St",
    line2: null,
    city: "London",
    region: null,
    postal_code: "N1 9GU",
    country: "GB",
    phone: "+442071234567",
    created_at: "2026-10-14T10:00:00Z",
    ...overrides,
  };
}
