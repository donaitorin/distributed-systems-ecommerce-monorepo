import { TEST_CARDS } from "../../lib/checkout";

export function PaymentNote() {
  return (
    <div className="flex flex-col gap-2 rounded-md border-2 border-border-strong bg-surface-2 p-3 text-sm text-primary">
      <p>
        <strong className="font-semibold">Payments are simulated.</strong> No real card is charged. Use a test card
        number that ends with:
      </p>
      <ul className="flex list-disc flex-col gap-1 pl-5">
        {TEST_CARDS.map((card) => (
          <li key={card.ending}>
            <strong className="font-semibold">{card.ending}</strong> {card.outcome}
          </li>
        ))}
      </ul>
    </div>
  );
}
