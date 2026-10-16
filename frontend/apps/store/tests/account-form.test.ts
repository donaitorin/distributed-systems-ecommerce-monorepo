/**
 * @jest-environment node
 */
import {
  PHONE_MESSAGE,
  profileFieldErrors,
  profileFormSchema,
  profileToFormValues,
  toPatchBody,
} from "../src/lib/account-form";

describe("profileFormSchema", () => {
  it("accepts a name with or without a phone and trims both", () => {
    expect(profileFormSchema.parse({ name: "  Ada  ", phone: "" })).toEqual({ name: "Ada", phone: "" });
    expect(profileFormSchema.parse({ name: "Ada", phone: " +34 600-123.456 " }).phone).toBe("+34 600-123.456");
    expect(profileFormSchema.safeParse({ name: "Ada", phone: "(+44) 20 7946 0958" }).success).toBe(true);
  });

  it("requires a name of at most 100 characters", () => {
    expect(profileFormSchema.safeParse({ name: "   ", phone: "" }).error?.issues[0]?.message).toBe("Enter your name");
    expect(profileFormSchema.safeParse({ name: "x".repeat(101), phone: "" }).error?.issues[0]?.message).toContain("100");
    expect(profileFormSchema.safeParse({ name: "x".repeat(100), phone: "" }).success).toBe(true);
  });

  it.each(["600123456", "+12345", "+1234567890123456", "+34 abc", "phone"])("explains a bad phone: %s", (phone) => {
    expect(profileFormSchema.safeParse({ name: "Ada", phone }).error?.issues[0]?.message).toBe(PHONE_MESSAGE);
  });
});

describe("profile values", () => {
  it("turns a profile with missing data into empty fields", () => {
    expect(profileToFormValues({ name: null, phone: null })).toEqual({ name: "", phone: "" });
    expect(profileToFormValues({ name: "Ada", phone: "+34600123456" })).toEqual({ name: "Ada", phone: "+34600123456" });
  });

  it("sends a blank phone as null so the API clears it", () => {
    expect(toPatchBody({ name: "Ada", phone: "" })).toEqual({ name: "Ada", phone: null });
    expect(toPatchBody({ name: "Ada", phone: "+34600123456" })).toEqual({ name: "Ada", phone: "+34600123456" });
  });

  it("keeps the API's name error and words the phone error in plain language", () => {
    expect(profileFieldErrors({ name: "must not be empty", phone: "phone must start with +", other: "x" })).toEqual({
      name: "must not be empty",
      phone: PHONE_MESSAGE,
    });
    expect(profileFieldErrors({})).toEqual({});
  });
});
