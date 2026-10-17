/**
 * @jest-environment node
 */
import { addAddressAction, removeAddressAction, updateProfileAction } from "../src/app/account/actions";

const server = {
  addAddress: jest.fn(),
  removeAddress: jest.fn(),
  updateProfile: jest.fn(),
};

jest.mock("../src/server/addresses", () => ({
  addAddress: (...args: unknown[]) => server.addAddress(...args) as unknown,
  removeAddress: (...args: unknown[]) => server.removeAddress(...args) as unknown,
}));
jest.mock("../src/server/profile", () => ({ updateProfile: (...args: unknown[]) => server.updateProfile(...args) as unknown }));

beforeEach(() => {
  jest.clearAllMocks();
});

describe("account actions", () => {
  it("saves and deletes addresses from the account page", async () => {
    server.addAddress.mockResolvedValue({ ok: true });
    server.removeAddress.mockResolvedValue({ ok: true });
    server.updateProfile.mockResolvedValue({ ok: true });

    await addAddressAction({ recipient_name: "Ada" } as never);
    await removeAddressAction("a1");
    await updateProfileAction({ name: "Ada", phone: "" });

    expect(server.addAddress).toHaveBeenCalledWith({ recipient_name: "Ada" }, "/account");
    expect(server.removeAddress).toHaveBeenCalledWith("a1", "/account");
    expect(server.updateProfile).toHaveBeenCalledWith({ name: "Ada", phone: "" });
  });
});
