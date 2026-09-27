import { useEffect, useId, useRef, useState } from "react";
import {
  type Cashier,
  cashierCsvUrl,
  changePaymentMethod,
  type Club,
  fetchCashier,
  type PaymentMethod,
  RejectedError,
  reverseTransaction,
  type Tournament,
  type Transaction,
} from "./api";
import { startFormat } from "./dates";
import { SERVER_UNREACHABLE, smallButton } from "./forms";
import { KIND_NAMES, METHOD_NAMES, money } from "./payments";

const OTHER_METHOD: Record<PaymentMethod, PaymentMethod> = { cash: "card", card: "cash" };

const SWITCH_TO: Record<PaymentMethod, string> = {
  cash: "Сменить на наличные",
  card: "Сменить на карту",
};

const timeFormat = new Intl.DateTimeFormat("ru-RU", {
  day: "numeric",
  month: "short",
  hour: "2-digit",
  minute: "2-digit",
});

type Loaded = { status: "loading" } | { status: "loaded"; cashier: Cashier } | { status: "failed" };

/** A tournament's cashier: what has been paid, by operation and by payment method, and every
 * operation. A mistaken one is reversed by a storno and stays in the history. */
export default function CashierPage({
  club,
  tournament,
  onBack,
}: {
  club: Club;
  tournament: Tournament;
  onBack: () => void;
}) {
  const [loaded, setLoaded] = useState<Loaded>({ status: "loading" });
  const [error, setError] = useState("");
  // One correction at a time: a second click while the first is on its way is ignored.
  const correcting = useRef(false);

  useEffect(() => {
    let stale = false;
    fetchCashier(club.id, tournament.id)
      .then((cashier) => !stale && setLoaded({ status: "loaded", cashier }))
      .catch(() => !stale && setLoaded({ status: "failed" }));
    return () => {
      stale = true;
    };
  }, [club.id, tournament.id]);

  async function correct(question: string, action: () => Promise<Cashier>) {
    if (correcting.current || !window.confirm(question)) return;
    correcting.current = true;
    setError("");
    try {
      setLoaded({ status: "loaded", cashier: await action() });
    } catch (failure) {
      setError(failure instanceof RejectedError ? failure.messages.join("\n") : SERVER_UNREACHABLE);
    } finally {
      correcting.current = false;
    }
  }

  function reverse(transaction: Transaction) {
    correct(
      `Сторнировать ${describe(transaction)}? Операция останется в истории.`,
      () => reverseTransaction(club.id, tournament.id, transaction.id),
    );
  }

  function switchMethod(transaction: Transaction) {
    const method = OTHER_METHOD[transaction.payment_method];
    correct(
      `${describe(transaction)}: оплата была «${METHOD_NAMES[method]}», а не «${
        METHOD_NAMES[transaction.payment_method]
      }»? Операция будет сторнирована и проведена заново.`,
      () => changePaymentMethod(club.id, tournament.id, transaction.id, method),
    );
  }

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-wrap items-start justify-between gap-3 rounded-2xl bg-white p-6 shadow-sm">
        <div>
          <h2 className="text-lg font-semibold text-slate-900">{tournament.name}</h2>
          <p className="text-sm text-slate-600">
            {startFormat.format(new Date(tournament.starts_at))} · касса турнира
          </p>
        </div>
        <button
          type="button"
          onClick={onBack}
          className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
        >
          Назад к списку
        </button>
      </div>

      {loaded.status === "loading" && <p className="text-slate-600">Загружаем кассу…</p>}
      {loaded.status === "failed" && (
        <p role="alert" className="text-red-700">
          Не удалось загрузить кассу. Обновите страницу.
        </p>
      )}
      {loaded.status === "loaded" && (
        <>
          <Summary
            cashier={loaded.cashier}
            csvUrl={cashierCsvUrl(club.id, tournament.id)}
          />
          <History
            cashier={loaded.cashier}
            error={error}
            onReverse={reverse}
            onSwitchMethod={switchMethod}
          />
        </>
      )}
    </div>
  );
}

/** "Re-entry, Иван Петров, 2 000 ₽" */
function describe(transaction: Transaction): string {
  return `${KIND_NAMES[transaction.kind]}, ${transaction.player.name}, ${money(transaction.amount)}`;
}

const cell = "px-3 py-2";
const amountCell = `${cell} text-right tabular-nums`;

function Summary({ cashier, csvUrl }: { cashier: Cashier; csvUrl: string }) {
  const headingId = useId();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
        <h3 id={headingId} className="text-lg font-semibold text-slate-900">
          Сводка
        </h3>
        <a href={csvUrl} download className={smallButton}>
          Выгрузить в CSV
        </a>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <table aria-label="По операциям" className="w-full text-sm">
          <thead className="text-left text-slate-500">
            <tr>
              <th className={cell}>Операция</th>
              <th className={`${cell} text-right`}>Кол-во</th>
              <th className={`${cell} text-right`}>Сумма</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {cashier.by_kind.map((total) => (
              <tr key={total.kind}>
                <td className={cell}>{KIND_NAMES[total.kind]}</td>
                <td className={amountCell}>{total.count}</td>
                <td className={amountCell}>{money(total.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <table aria-label="По способам оплаты" className="w-full text-sm">
          <thead className="text-left text-slate-500">
            <tr>
              <th className={cell}>Способ оплаты</th>
              <th className={`${cell} text-right`}>Сумма</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-200">
            {cashier.by_method.map((total) => (
              <tr key={total.payment_method}>
                <td className={cell}>{METHOD_NAMES[total.payment_method]}</td>
                <td className={amountCell}>{money(total.amount)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="mt-4 text-lg font-semibold text-slate-900">
        Всего в кассе: <span className="tabular-nums">{money(cashier.total)}</span>
      </p>
    </section>
  );
}

function History({
  cashier,
  error,
  onReverse,
  onSwitchMethod,
}: {
  cashier: Cashier;
  error: string;
  onReverse: (transaction: Transaction) => void;
  onSwitchMethod: (transaction: Transaction) => void;
}) {
  const headingId = useId();
  // The latest first: that is what the admin has just done and may need to put right.
  const latestFirst = [...cashier.transactions].reverse();
  return (
    <section aria-labelledby={headingId} className="rounded-2xl bg-white p-6 shadow-sm">
      <h3 id={headingId} className="mb-3 text-lg font-semibold text-slate-900">
        Операции
      </h3>
      {error && (
        <p role="alert" className="mb-3 whitespace-pre-line rounded-lg bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}
      {latestFirst.length === 0 ? (
        <p className="text-sm text-slate-500">Оплат пока не было</p>
      ) : (
        <ul aria-label="Операции" className="divide-y divide-slate-200 rounded-xl border border-slate-200">
          {latestFirst.map((transaction) => (
            <Operation
              key={transaction.id}
              transaction={transaction}
              onReverse={() => onReverse(transaction)}
              onSwitchMethod={() => onSwitchMethod(transaction)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

function Operation({
  transaction,
  onReverse,
  onSwitchMethod,
}: {
  transaction: Transaction;
  onReverse: () => void;
  onSwitchMethod: () => void;
}) {
  const storno = transaction.reverses_id !== null;
  const reversed = transaction.reversed_by_id !== null;
  // Only an operation that stands can be put right.
  const standing = !storno && !reversed;
  return (
    <li
      aria-label={`Операция № ${transaction.id}`}
      className={`flex flex-wrap items-center gap-x-4 gap-y-2 p-3 ${standing ? "" : "bg-slate-50"}`}
    >
      <div className="w-28 text-sm text-slate-500">
        <p>№&nbsp;{transaction.id}</p>
        <p>{timeFormat.format(new Date(transaction.created_at))}</p>
      </div>
      <div className="min-w-40 flex-1">
        <p className={`font-medium ${reversed ? "text-slate-400 line-through" : "text-slate-900"}`}>
          {KIND_NAMES[transaction.kind]} · {transaction.player.name}
        </p>
        <p className="text-sm text-slate-600">
          {METHOD_NAMES[transaction.payment_method]} · {transaction.admin.name}
        </p>
        {storno && (
          <p className="text-sm text-amber-800">Сторно операции №&nbsp;{transaction.reverses_id}</p>
        )}
        {transaction.replaces_id !== null && (
          <p className="text-sm text-slate-600">Взамен операции №&nbsp;{transaction.replaces_id}</p>
        )}
        {reversed && (
          <p className="text-sm text-amber-800">
            Сторнирована операцией №&nbsp;{transaction.reversed_by_id}
          </p>
        )}
      </div>
      <span
        className={`font-medium tabular-nums ${transaction.amount < 0 ? "text-red-700" : "text-slate-900"}`}
      >
        {money(transaction.amount)}
      </span>
      {standing && (
        <div className="flex flex-wrap gap-2">
          <button type="button" onClick={onSwitchMethod} className={smallButton}>
            {SWITCH_TO[OTHER_METHOD[transaction.payment_method]]}
          </button>
          <button
            type="button"
            onClick={onReverse}
            className="rounded-lg border border-red-200 px-3 py-1 text-sm text-red-700"
          >
            Сторнировать
          </button>
        </div>
      )}
    </li>
  );
}
