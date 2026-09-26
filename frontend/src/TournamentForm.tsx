import { type FormEvent, useEffect, useState } from "react";
import {
  type BlindTemplate,
  fetchBlindTemplates,
  RejectedError,
  type Tournament,
  type TournamentInput,
} from "./api";
import { inputClass, labelClass, SERVER_UNREACHABLE } from "./forms";
import StructureEditor, { fromRows, type StructureRow, toRows } from "./StructureEditor";

const pad = (value: number) => String(value).padStart(2, "0");

/** An ISO moment as the value of a datetime-local input, in the admin's own time zone. */
function toLocalInput(iso: string): string {
  const date = new Date(iso);
  return (
    `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}` +
    `T${pad(date.getHours())}:${pad(date.getMinutes())}`
  );
}

function fromLocalInput(value: string): string {
  const date = new Date(value);
  // An unreadable date goes to the server as is, and the server explains what is wrong.
  return Number.isNaN(date.getTime()) ? value : date.toISOString();
}

const optionalLevel = (value: string) => (value.trim() === "" ? null : Number(value));
const levelText = (level: number | null) => (level === null ? "" : String(level));

type Fields = {
  name: string;
  startsAt: string;
  buyIn: string;
  startingStack: string;
  reentryUntilLevel: string;
  addonAtLevel: string;
  lateRegistrationUntilLevel: string;
  seatsPerTable: string;
};

function initialFields(tournament?: Tournament): Fields {
  return {
    name: tournament?.name ?? "",
    startsAt: tournament ? toLocalInput(tournament.starts_at) : "",
    buyIn: tournament ? String(tournament.buy_in) : "",
    startingStack: tournament ? String(tournament.starting_stack) : "",
    reentryUntilLevel: levelText(tournament?.reentry_until_level ?? null),
    addonAtLevel: levelText(tournament?.addon_at_level ?? null),
    lateRegistrationUntilLevel: levelText(tournament?.late_registration_until_level ?? null),
    seatsPerTable: String(tournament?.seats_per_table ?? 9),
  };
}

/** Creates a tournament (no `tournament` given) or edits one that has not started yet. */
export default function TournamentForm({
  tournament,
  primaryColor,
  save,
  onClose,
}: {
  tournament?: Tournament;
  primaryColor: string;
  save: (input: TournamentInput) => Promise<unknown>;
  onClose: () => void;
}) {
  const [fields, setFields] = useState(() => initialFields(tournament));
  const [rows, setRows] = useState<StructureRow[]>(() =>
    tournament ? toRows(tournament.structure) : [],
  );
  const [templates, setTemplates] = useState<BlindTemplate[]>([]);
  const [templateId, setTemplateId] = useState("");
  const [errors, setErrors] = useState<string[]>([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    fetchBlindTemplates()
      .then((loaded) => {
        setTemplates(loaded);
        // A new tournament starts from the league's first template.
        if (!tournament && loaded.length > 0) {
          setTemplateId(loaded[0].id);
          setRows(toRows(loaded[0].structure));
        }
      })
      .catch(() => setErrors(["Не удалось загрузить шаблоны структуры блайндов."]));
  }, [tournament]);

  function changeHandler(field: keyof Fields) {
    return (event: { target: { value: string } }) =>
      setFields((current) => ({ ...current, [field]: event.target.value }));
  }

  function chooseTemplate(id: string) {
    const template = templates.find((candidate) => candidate.id === id);
    setTemplateId(id);
    if (template) setRows(toRows(template.structure));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setErrors([]);
    setSaving(true);
    try {
      await save({
        name: fields.name,
        starts_at: fromLocalInput(fields.startsAt),
        buy_in: Number(fields.buyIn),
        starting_stack: Number(fields.startingStack),
        structure: fromRows(rows),
        reentry_until_level: optionalLevel(fields.reentryUntilLevel),
        addon_at_level: optionalLevel(fields.addonAtLevel),
        late_registration_until_level: optionalLevel(fields.lateRegistrationUntilLevel),
        seats_per_table: Number(fields.seatsPerTable),
      });
    } catch (error) {
      setErrors(error instanceof RejectedError ? error.messages : [SERVER_UNREACHABLE]);
      setSaving(false);
    }
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-6">
      <h2 className="text-lg font-semibold text-slate-900">
        {tournament ? `Изменить турнир «${tournament.name}»` : "Новый турнир"}
      </h2>

      <div className="grid gap-4 sm:grid-cols-2">
        <label className={`${labelClass} sm:col-span-2`}>
          Название
          <input required value={fields.name} onChange={changeHandler("name")} className={inputClass} />
        </label>
        <label className={labelClass}>
          Начало
          <input
            type="datetime-local"
            required
            value={fields.startsAt}
            onChange={changeHandler("startsAt")}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Бай-ин, ₽
          <input
            type="number"
            required
            min={0}
            value={fields.buyIn}
            onChange={changeHandler("buyIn")}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Стартовый стек
          <input
            type="number"
            required
            min={1}
            value={fields.startingStack}
            onChange={changeHandler("startingStack")}
            className={inputClass}
          />
        </label>
        <label className={labelClass}>
          Мест за столом
          <input
            type="number"
            required
            min={2}
            max={10}
            value={fields.seatsPerTable}
            onChange={changeHandler("seatsPerTable")}
            className={inputClass}
          />
        </label>
      </div>

      <fieldset className="flex min-w-0 flex-col gap-3">
        <legend className="mb-2 font-medium text-slate-900">Структура блайндов</legend>
        <div className={`${labelClass} max-w-sm`}>
          <label htmlFor="blind-template">Шаблон структуры</label>
          <select
            id="blind-template"
            value={templateId}
            onChange={(event) => chooseTemplate(event.target.value)}
            className={inputClass}
          >
            <option value="" disabled>
              {tournament ? "Структура этого турнира" : "Выберите шаблон"}
            </option>
            {templates.map((template) => (
              <option key={template.id} value={template.id}>
                {template.name}
              </option>
            ))}
          </select>
          <span className="text-xs text-slate-500">
            Выбор шаблона заменяет структуру ниже. Уровни можно править.
          </span>
        </div>
        <StructureEditor rows={rows} onChange={setRows} />
      </fieldset>

      <fieldset className="flex min-w-0 flex-col gap-3">
        <legend className="mb-2 font-medium text-slate-900">Правила</legend>
        <p className="text-xs text-slate-500">
          Номера уровней считаются без перерывов. Оставьте поле пустым, если опция не
          разрешена.
        </p>
        <div className="grid gap-4 sm:grid-cols-3">
          <label className={labelClass}>
            Re-entry до уровня
            <input
              type="number"
              min={1}
              value={fields.reentryUntilLevel}
              onChange={changeHandler("reentryUntilLevel")}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Add-on на уровне
            <input
              type="number"
              min={1}
              value={fields.addonAtLevel}
              onChange={changeHandler("addonAtLevel")}
              className={inputClass}
            />
          </label>
          <label className={labelClass}>
            Поздняя регистрация до уровня
            <input
              type="number"
              min={1}
              value={fields.lateRegistrationUntilLevel}
              onChange={changeHandler("lateRegistrationUntilLevel")}
              className={inputClass}
            />
          </label>
        </div>
      </fieldset>

      {errors.length > 0 && (
        <div role="alert" className="rounded-lg bg-red-50 p-4 text-sm text-red-800">
          <p className="mb-1 font-medium">Турнир не сохранён:</p>
          <ul className="list-disc pl-5">
            {errors.map((error, index) => (
              // The same message can come twice, e.g. for two empty breaks after one level.
              <li key={index}>{error}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="flex flex-wrap gap-3">
        <button
          type="submit"
          disabled={saving}
          className="rounded-lg px-4 py-2 font-medium text-white disabled:opacity-60"
          style={{ backgroundColor: primaryColor }}
        >
          Сохранить турнир
        </button>
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-slate-300 px-4 py-2 font-medium text-slate-700"
        >
          Назад к списку
        </button>
      </div>
    </form>
  );
}
