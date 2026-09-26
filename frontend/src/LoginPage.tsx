import { type FormEvent, useState } from "react";
import { requestCode, verifyCode } from "./api";
import LeagueBrand from "./LeagueBrand";

const inputClass = "rounded-lg border border-slate-300 px-3 py-2 text-base";
const buttonClass = "rounded-lg bg-slate-900 px-4 py-2 font-medium text-white";
const SERVER_UNREACHABLE = "Не удалось связаться с сервером. Попробуйте ещё раз.";

export default function LoginPage({ onLoggedIn }: { onLoggedIn: () => void }) {
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [error, setError] = useState<string | null>(null);

  async function submitPhone(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      await requestCode(phone);
      setCode("");
      setStep("code");
    } catch {
      setError(SERVER_UNREACHABLE);
    }
  }

  async function submitCode(event: FormEvent) {
    event.preventDefault();
    setError(null);
    try {
      if (await verifyCode(phone, code)) {
        onLoggedIn();
      } else {
        setError("Неверный или просроченный код");
      }
    } catch {
      setError(SERVER_UNREACHABLE);
    }
  }

  function changePhone() {
    setError(null);
    setStep("phone");
  }

  return (
    <main className="flex flex-1 items-center justify-center p-4">
      <div className="w-full max-w-sm rounded-2xl bg-white p-8 shadow-sm">
        <LeagueBrand className="mb-6 text-slate-900" />
        <h1 className="mb-6 text-xl font-semibold text-slate-900">
          Вход для администратора клуба
        </h1>
        {step === "phone" ? (
          <form onSubmit={submitPhone} className="flex flex-col gap-4">
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Номер телефона
              <input
                type="tel"
                autoComplete="tel"
                required
                placeholder="+7 900 000-00-00"
                value={phone}
                onChange={(event) => setPhone(event.target.value)}
                className={inputClass}
              />
            </label>
            <button type="submit" className={buttonClass}>
              Получить код
            </button>
          </form>
        ) : (
          <form onSubmit={submitCode} className="flex flex-col gap-4">
            <p className="text-sm text-slate-600">
              Код отправлен на {phone}. В прототипе SMS не уходит: код пишется в лог
              backend.
            </p>
            <label className="flex flex-col gap-1 text-sm text-slate-700">
              Код из SMS
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                required
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value)}
                className={`${inputClass} tracking-widest`}
              />
            </label>
            <button type="submit" className={buttonClass}>
              Войти
            </button>
            <button
              type="button"
              onClick={changePhone}
              className="text-sm text-slate-600 underline"
            >
              Изменить номер
            </button>
          </form>
        )}
        {error && (
          <p role="alert" className="mt-4 text-sm text-red-700">
            {error}
          </p>
        )}
      </div>
    </main>
  );
}
