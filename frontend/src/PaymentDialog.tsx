import { type ReactNode, useEffect, useId, useRef, useState } from "react";
import type { PaymentMethod } from "./api";
import { smallButton } from "./forms";
import { METHOD_NAMES, money } from "./payments";

type Request = {
  /** What is paid for and by whom, e.g. "Бай-ин: Иван Петров". */
  what: string;
  amount: number;
  pay: (method: PaymentMethod) => void;
};

/** Asks how the player pays before a paid action (a check-in, a re-entry, an add-on, a late
 * seat) is sent: every payment is recorded in the tournament's cashier as cash or card. */
export function usePayment(): {
  /** Runs `pay` once the admin says how the player paid; at once, with no method, when the
   * action is free. */
  askToPay: (what: string, amount: number, pay: (method: PaymentMethod | null) => void) => void;
  /** The dialog to render while the admin is asked. */
  paymentDialog: ReactNode;
} {
  const [request, setRequest] = useState<Request | null>(null);

  function askToPay(what: string, amount: number, pay: (method: PaymentMethod | null) => void) {
    if (amount === 0) {
      pay(null);
      return;
    }
    setRequest({
      what,
      amount,
      pay: (method) => {
        setRequest(null);
        pay(method);
      },
    });
  }

  return {
    askToPay,
    paymentDialog: request && <PaymentDialog request={request} onClose={() => setRequest(null)} />,
  };
}

function PaymentDialog({ request, onClose }: { request: Request; onClose: () => void }) {
  const headingId = useId();
  const first = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    first.current?.focus();
    const closeOnEscape = (event: KeyboardEvent) => event.key === "Escape" && onClose();
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [onClose]);

  const methodButton = "flex-1 rounded-lg px-4 py-3 text-base font-medium text-white";
  return (
    <div className="fixed inset-0 z-10 flex items-center justify-center bg-slate-900/40 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className="w-full max-w-sm rounded-2xl bg-white p-6 shadow-lg"
      >
        <h3 id={headingId} className="text-lg font-semibold text-slate-900">
          Оплата
        </h3>
        <p className="mt-1 text-slate-700">{request.what}</p>
        <p className="mt-3 text-3xl font-semibold tabular-nums text-slate-900">
          {money(request.amount)}
        </p>
        <p className="mt-4 text-sm text-slate-600">Как заплатил игрок?</p>
        <div className="mt-2 flex gap-2">
          <button
            ref={first}
            type="button"
            onClick={() => request.pay("cash")}
            className={`${methodButton} bg-emerald-700`}
          >
            {METHOD_NAMES.cash}
          </button>
          <button
            type="button"
            onClick={() => request.pay("card")}
            className={`${methodButton} bg-sky-700`}
          >
            {METHOD_NAMES.card}
          </button>
        </div>
        <button type="button" onClick={onClose} className={`${smallButton} mt-4 w-full py-2`}>
          Отмена
        </button>
      </div>
    </div>
  );
}
