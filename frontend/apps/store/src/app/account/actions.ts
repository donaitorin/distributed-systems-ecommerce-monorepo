"use server";

import type { Failure } from "@ecommerce/web-core";
import type { ProfileFormValues } from "../../lib/account-form";
import type { AddressFormValues } from "../../lib/addresses";
import { ACCOUNT_PATH } from "../../lib/paths";
import { addAddress, removeAddress, type AddressRemoved, type AddressSaved } from "../../server/addresses";
import { updateProfile, type ProfileSaved } from "../../server/profile";

export async function updateProfileAction(values: ProfileFormValues): Promise<ProfileSaved | Failure> {
  return updateProfile(values);
}

export async function addAddressAction(values: AddressFormValues): Promise<AddressSaved | Failure> {
  return addAddress(values, ACCOUNT_PATH);
}

export async function removeAddressAction(addressId: string): Promise<AddressRemoved | Failure> {
  return removeAddress(addressId, ACCOUNT_PATH);
}
