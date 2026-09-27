import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { Transaction } from "./api";
import { aPlayer, aTournament, fakeBackend, ME } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

const IVAN = aPlayer({ id: 1, name: "Иван Петров" });
const MARIA = aPlayer({ id: 2, name: "Мария Иванова" });
const FRIDAY = aTournament({ id: 5, name: "Пятничный турнир", status: "running" });

function transaction(
  id: number,
  kind: Transaction["kind"],
  player: Transaction["player"],
  amount: number,
  payment_method: Transaction["payment_method"],
  overrides: Partial<Transaction> = {},
): Transaction {
  return {
    id,
    created_at: "2026-10-02T12:05:00Z",
    kind,
    amount,
    payment_method,
    player,
    admin: ME.admin,
    reverses_id: null,
    replaces_id: null,
    reversed_by_id: null,
    ...overrides,
  };
}

// Ivan paid cash, Maria by card; Maria's cash add-on was a mistake and was reversed.
const TRANSACTIONS = [
  transaction(1, "buy_in", IVAN, 2000, "cash"),
  transaction(2, "buy_in", MARIA, 2000, "card"),
  transaction(3, "addon", MARIA, 1000, "cash", { reversed_by_id: 4 }),
  transaction(4, "addon", MARIA, -1000, "cash", { reverses_id: 3 }),
  transaction(5, "reentry", IVAN, 2000, "card"),
];

async function openCashier(options: Parameters<typeof fakeBackend>[0] = {}) {
  const fetch = fakeBackend({
    loggedIn: true,
    tournaments: { live: [FRIDAY], upcoming: [], past: [] },
    cashiers: { 5: TRANSACTIONS },
    ...options,
  });
  const user = userEvent.setup();
  render(<App />);
  const row = await screen.findByRole("listitem", { name: "Пятничный турнир" });
  await user.click(within(row).getByRole("button", { name: "Касса" }));
  await screen.findByRole("heading", { name: "Пятничный турнир" });
  return { user, fetch };
}

/** Amounts are written with a non-breaking space ("4 000 ₽"); compared with a plain one. */
const plain = (text: string | null) => (text ?? "").replace(/\s/g, " ");

function summaryRows(name: string) {
  return within(screen.getByRole("table", { name })).getAllByRole("row").map((row) =>
    within(row)
      .queryAllByRole("cell")
      .map((cell) => plain(cell.textContent)),
  );
}

function operations() {
  return screen.getByRole("list", { name: "Операции" });
}

describe("tournament cashier", () => {
  it("sums the payments up by operation and by payment method", async () => {
    await openCashier();

    await screen.findByRole("table", { name: "По операциям" });
    expect(summaryRows("По операциям").slice(1)).toEqual([
      ["Бай-ин", "2", "4 000 ₽"],
      ["Re-entry", "1", "2 000 ₽"],
      ["Add-on", "0", "0 ₽"],
    ]);
    expect(summaryRows("По способам оплаты").slice(1)).toEqual([
      ["Наличные", "2 000 ₽"],
      ["Карта", "4 000 ₽"],
    ]);
    expect(screen.getByText(/Всего в кассе/)).toHaveTextContent("Всего в кассе: 6 000 ₽");
  });

  it("lists every operation, the latest first, with a storno and what it reversed", async () => {
    await openCashier();

    const list = await screen.findByRole("list", { name: "Операции" });
    const rows = within(list).getAllByRole("listitem");
    expect(rows.map((row) => row.getAttribute("aria-label"))).toEqual([
      "Операция № 5",
      "Операция № 4",
      "Операция № 3",
      "Операция № 2",
      "Операция № 1",
    ]);
    expect(rows[0]).toHaveTextContent("Re-entry");
    expect(rows[0]).toHaveTextContent("Иван Петров");
    expect(rows[0]).toHaveTextContent("Карта");
    expect(rows[0]).toHaveTextContent("2 000 ₽");
    expect(rows[0]).toHaveTextContent("Анна Соколова");
    expect(rows[1]).toHaveTextContent("Сторно операции № 3");
    expect(rows[1]).toHaveTextContent("−1 000 ₽");
    expect(rows[2]).toHaveTextContent("Сторнирована операцией № 4");
    // Neither a storno nor a reversed operation can be put right again.
    expect(within(rows[1]).queryByRole("button")).not.toBeInTheDocument();
    expect(within(rows[2]).queryByRole("button")).not.toBeInTheDocument();
  });

  it("reverses a mistaken operation after the admin confirms", async () => {
    const confirm = vi.fn<(question: string) => boolean>(() => true);
    vi.stubGlobal("confirm", confirm);
    const { user, fetch } = await openCashier();
    const reentry = await within(await screen.findByRole("list", { name: "Операции" })).findByRole(
      "listitem",
      { name: "Операция № 5" },
    );

    await user.click(within(reentry).getByRole("button", { name: "Сторнировать" }));

    expect(plain(confirm.mock.calls[0][0])).toBe(
      "Сторнировать Re-entry, Иван Петров, 2 000 ₽? Операция останется в истории.",
    );
    expect(
      await within(operations()).findByRole("listitem", { name: "Операция № 6" }),
    ).toHaveTextContent("Сторно операции № 5");
    expect(within(operations()).getByRole("listitem", { name: "Операция № 5" })).toHaveTextContent(
      "Сторнирована",
    );
    expect(summaryRows("По операциям")[2]).toEqual(["Re-entry", "0", "0 ₽"]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/cashier/transactions/5/reverse",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("puts right a payment taken the wrong way", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    const { user, fetch } = await openCashier();
    const ivan = await within(await screen.findByRole("list", { name: "Операции" })).findByRole(
      "listitem",
      { name: "Операция № 1" },
    );

    await user.click(within(ivan).getByRole("button", { name: "Сменить на карту" }));

    const again = await within(operations()).findByRole("listitem", { name: "Операция № 7" });
    expect(again).toHaveTextContent("Карта");
    expect(again).toHaveTextContent("Взамен операции № 1");
    expect(again).toHaveTextContent("Иван Петров");
    expect(summaryRows("По способам оплаты").slice(1)).toEqual([
      ["Наличные", "0 ₽"],
      ["Карта", "6 000 ₽"],
    ]);
    expect(fetch).toHaveBeenCalledWith(
      "/api/clubs/7/tournaments/5/cashier/transactions/1/payment-method",
      expect.objectContaining({ body: JSON.stringify({ payment_method: "card" }) }),
    );
  });

  it("leaves the cashier as it was when the admin changes their mind", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const { user, fetch } = await openCashier();
    const ivan = await within(await screen.findByRole("list", { name: "Операции" })).findByRole(
      "listitem",
      { name: "Операция № 1" },
    );

    await user.click(within(ivan).getByRole("button", { name: "Сторнировать" }));

    expect(fetch.mock.calls.some(([url]) => String(url).endsWith("/reverse"))).toBe(false);
    expect(within(ivan).queryByText("Сторнирована")).not.toBeInTheDocument();
  });

  it("exports the cashier to a CSV file", async () => {
    await openCashier();

    expect(await screen.findByRole("link", { name: "Выгрузить в CSV" })).toHaveAttribute(
      "href",
      "/api/clubs/7/tournaments/5/cashier.csv",
    );
  });

  it("says when nothing has been paid yet", async () => {
    await openCashier({ cashiers: {} });
    expect(await screen.findByText("Оплат пока не было")).toBeInTheDocument();
  });

  it("says when the cashier cannot be loaded", async () => {
    await openCashier({ down: ["GET /api/clubs/7/tournaments/5/cashier"] });

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось загрузить кассу. Обновите страницу.",
    );
  });
});
