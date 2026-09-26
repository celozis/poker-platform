import { type FormEvent, useState } from "react";
import { type PlayerAdded, type PlayerInput, RejectedError } from "./api";
import { inputClass, labelClass, SERVER_UNREACHABLE } from "./forms";

const EMPTY: PlayerInput = { name: "", phone: "", consent: false };

/** What happened, in words for the admin. */
export function addedMessage({ player, outcome }: PlayerAdded): string {
  switch (outcome) {
    case "created":
      return `Игрок ${player.name} добавлен`;
    case "added_to_club":
      return `Игрок ${player.name} уже есть в лиге и теперь добавлен в ваш клуб`;
    case "already_in_club":
      return `Игрок ${player.name} уже есть в вашем клубе`;
  }
}

/** A new player: name, phone and consent to data processing. A phone already known in the
 * league brings that player into the club instead of creating a second one. */
export default function PlayerForm({
  primaryColor,
  submitLabel,
  add,
}: {
  primaryColor: string;
  submitLabel: string;
  /** Saves the player; a RejectedError keeps the form filled in and shows why. */
  add: (input: PlayerInput) => Promise<unknown>;
}) {
  const [fields, setFields] = useState<PlayerInput>(EMPTY);
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setErrors([]);
    setSaving(true);
    try {
      await add(fields);
      setFields(EMPTY);
    } catch (error) {
      setErrors(error instanceof RejectedError ? error.messages : [SERVER_UNREACHABLE]);
    } finally {
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <label className={labelClass}>
          Имя
          <input
            required
            value={fields.name}
            onChange={(event) => setFields({ ...fields, name: event.target.value })}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Телефон
          <input
            type="tel"
            required
            placeholder="+7 913 555-12-34"
            value={fields.phone}
            onChange={(event) => setFields({ ...fields, phone: event.target.value })}
            className={inputClass}
          />
        </label>
      </div>
      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={fields.consent}
          onChange={(event) => setFields({ ...fields, consent: event.target.checked })}
          className="mt-1 h-4 w-4"
        />
        <span>
          Игрок согласен на обработку персональных данных (152-ФЗ). Без согласия игрока не
          завести.
        </span>
      </label>
      {errors.length > 0 && (
        <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          <p className="mb-1 font-medium">Игрок не добавлен:</p>
          <ul className="list-disc pl-5">
            {errors.map((error) => (
              <li key={error}>{error}</li>
            ))}
          </ul>
        </div>
      )}
      <div>
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg px-4 py-2 font-medium text-white disabled:opacity-60"
          style={{ backgroundColor: primaryColor }}
        >
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
