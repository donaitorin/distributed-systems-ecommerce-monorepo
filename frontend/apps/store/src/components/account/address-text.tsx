import { addressLines, type Address } from "../../lib/addresses";

export type AddressTextProps = {
  address: Pick<Address, "recipient_name" | "line1" | "line2" | "city" | "region" | "postal_code" | "country" | "phone">;
};

export function AddressText({ address }: AddressTextProps) {
  return (
    <address className="flex flex-col text-base not-italic">
      <span className="font-semibold">{address.recipient_name}</span>
      {addressLines(address).map((line) => (
        <span key={line}>{line}</span>
      ))}
      {address.phone ? <span>{address.phone}</span> : null}
    </address>
  );
}
