import {
  addressFailureMessage,
  addressFieldErrors,
  addressFormSchema,
  addressLines,
  addressSummary,
  COUNTRY_MESSAGE,
  EMPTY_ADDRESS,
  toAddressBody,
} from "../src/lib/addresses";
import { PHONE_MESSAGE } from "../src/lib/account-form";
import { address } from "./support/addresses";

const valid = {
  ...EMPTY_ADDRESS,
  recipient_name: " Ada Lovelace ",
  line1: "12 Analytical St",
  city: "London",
  postal_code: "N1 9GU",
  country: "gb",
};

describe("addressFormSchema", () => {
  it("accepts the required fields and trims them", () => {
    const parsed = addressFormSchema.parse(valid);

    expect(parsed.recipient_name).toBe("Ada Lovelace");
    expect(parsed.country).toBe("gb");
  });

  it.each([
    ["recipient_name", ""],
    ["line1", "  "],
    ["city", ""],
    ["postal_code", ""],
    ["country", "G"],
    ["country", "GBR"],
    ["country", "G1"],
    ["phone", "12345"],
    ["line1", "x".repeat(201)],
  ])("rejects %s = %j", (field, value) => {
    const result = addressFormSchema.safeParse({ ...valid, [field]: value });

    expect(result.success).toBe(false);
  });

  it("accepts a phone with separators and leaves optional fields empty", () => {
    expect(addressFormSchema.safeParse({ ...valid, phone: "+44 20 7123 4567" }).success).toBe(true);
  });
});

describe("toAddressBody", () => {
  it("sends blank optional fields as null and uppercases the country", () => {
    expect(toAddressBody(addressFormSchema.parse(valid))).toEqual({
      recipient_name: "Ada Lovelace",
      line1: "12 Analytical St",
      line2: null,
      city: "London",
      region: null,
      postal_code: "N1 9GU",
      country: "GB",
      phone: null,
    });
  });

  it("keeps the optional fields that were filled", () => {
    const body = toAddressBody(addressFormSchema.parse({ ...valid, line2: "Flat 2", region: "Greater London", phone: "+442071234567" }));

    expect(body).toMatchObject({ line2: "Flat 2", region: "Greater London", phone: "+442071234567" });
  });
});

describe("addressFieldErrors", () => {
  it("keeps the API messages, except phone and country which are worded for the customer", () => {
    expect(
      addressFieldErrors({ city: "Field required", phone: "phone must start with +", country: "country must be", unknown: "x" }),
    ).toEqual({ city: "Field required", phone: PHONE_MESSAGE, country: COUNTRY_MESSAGE });
  });
});

describe("address text", () => {
  it("lists the lines in order, skipping empty ones", () => {
    expect(addressLines(address())).toEqual(["12 Analytical St", "London, N1 9GU", "GB"]);
    expect(addressLines(address({ line2: "Flat 2", region: "Greater London" }))).toEqual([
      "12 Analytical St",
      "Flat 2",
      "London, Greater London, N1 9GU",
      "GB",
    ]);
  });

  it("summarises an address on one line", () => {
    expect(addressSummary(address())).toBe("Ada Lovelace, 12 Analytical St, London, N1 9GU, GB");
  });
});

describe("addressFailureMessage", () => {
  it.each([
    [409, /10 saved addresses/],
    [422, /highlighted fields/],
    [429, /Too many requests/],
    [503, /could not be saved/],
    [null, /could not be saved/],
  ])("explains %s", (status, expected) => {
    expect(addressFailureMessage(status)).toMatch(expected);
  });
});
