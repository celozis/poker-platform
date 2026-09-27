import type { PaymentMethod, Player, TransactionKind } from "./api";

const roubles = new Intl.NumberFormat("ru-RU");

/** An amount in roubles as the admin reads it, e.g. "2 000 ₽" or "−2 000 ₽". */
export function money(amount: number): string {
  return `${amount < 0 ? "−" : ""}${roubles.format(Math.abs(amount))} ₽`;
}

export const KIND_NAMES: Record<TransactionKind, string> = {
  buy_in: "Бай-ин",
  reentry: "Re-entry",
  addon: "Add-on",
};

export const METHOD_NAMES: Record<PaymentMethod, string> = { cash: "Наличные", card: "Карта" };

/** What a payment is for, as the payment dialog asks it: "Re-entry: Иван Петров". */
export function paidFor(kind: TransactionKind, player: Player): string {
  return `${KIND_NAMES[kind]}: ${player.name}`;
}
