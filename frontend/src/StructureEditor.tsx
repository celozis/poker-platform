import type { StructureItem } from "./api";

// Numbers are kept as typed, so a field can be cleared while editing; they become numbers on save.
export type LevelRow = {
  key: number;
  kind: "level";
  small_blind: string;
  big_blind: string;
  ante: string;
  duration_minutes: string;
};
export type BreakRow = { key: number; kind: "break"; duration_minutes: string };
export type StructureRow = LevelRow | BreakRow;

let lastKey = 0;
const newKey = () => ++lastKey;

const DEFAULT_BREAK_MINUTES = "10";

export function toRows(structure: StructureItem[]): StructureRow[] {
  return structure.map((item) =>
    item.kind === "level"
      ? {
          key: newKey(),
          kind: "level",
          small_blind: String(item.small_blind),
          big_blind: String(item.big_blind),
          ante: String(item.ante),
          duration_minutes: String(item.duration_minutes),
        }
      : { key: newKey(), kind: "break", duration_minutes: String(item.duration_minutes) },
  );
}

export function fromRows(rows: StructureRow[]): StructureItem[] {
  return rows.map((row) =>
    row.kind === "level"
      ? {
          kind: "level",
          small_blind: Number(row.small_blind),
          big_blind: Number(row.big_blind),
          ante: Number(row.ante),
          duration_minutes: Number(row.duration_minutes),
        }
      : { kind: "break", duration_minutes: Number(row.duration_minutes) },
  );
}

/** A new last level: the previous level with blinds and ante doubled. */
function nextLevel(rows: StructureRow[]): LevelRow {
  const last = [...rows].reverse().find((row): row is LevelRow => row.kind === "level");
  const double = (value: string) => String(Number(value) * 2);
  return {
    key: newKey(),
    kind: "level",
    small_blind: last ? double(last.small_blind) : "100",
    big_blind: last ? double(last.big_blind) : "200",
    ante: last ? double(last.ante) : "0",
    duration_minutes: last ? last.duration_minutes : "20",
  };
}

type LevelField = Exclude<keyof LevelRow, "key" | "kind">;

const cellInput = "w-24 rounded-md border border-slate-300 px-2 py-1 text-right";
const rowButton = "rounded-md px-2 py-1 text-sm text-slate-600 hover:bg-slate-100";

/** Blind levels and breaks in play order; levels are numbered, breaks are not. */
export default function StructureEditor({
  rows,
  onChange,
}: {
  rows: StructureRow[];
  onChange: (rows: StructureRow[]) => void;
}) {
  function update(key: number, field: LevelField, value: string) {
    onChange(rows.map((row) => (row.key === key ? { ...row, [field]: value } : row)));
  }

  function remove(key: number) {
    onChange(rows.filter((row) => row.key !== key));
  }

  function addBreakAfter(index: number) {
    const breakRow: BreakRow = {
      key: newKey(),
      kind: "break",
      duration_minutes: DEFAULT_BREAK_MINUTES,
    };
    onChange([...rows.slice(0, index + 1), breakRow, ...rows.slice(index + 1)]);
  }

  let levelNumber = 0;
  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-left text-slate-500">
              <th className="py-1 pr-2 font-normal">Уровень</th>
              <th className="px-1 font-normal">Малый блайнд</th>
              <th className="px-1 font-normal">Большой блайнд</th>
              <th className="px-1 font-normal">Анте</th>
              <th className="px-1 font-normal">Минут</th>
              <th />
            </tr>
          </thead>
          <tbody>
            {rows.map((row, index) => {
              if (row.kind === "break") {
                const name = levelNumber
                  ? `перерыв после уровня ${levelNumber}`
                  : "перерыв в начале";
                return (
                  <tr key={row.key} className="bg-amber-50">
                    <td className="py-1 pr-2 font-medium text-amber-800">Перерыв</td>
                    <td colSpan={3} />
                    <td className="px-1 py-1">
                      <input
                        type="number"
                        required
                        aria-label={`Длительность: ${name}`}
                        value={row.duration_minutes}
                        onChange={(event) =>
                          update(row.key, "duration_minutes", event.target.value)
                        }
                        className={cellInput}
                      />
                    </td>
                    <td className="py-1 text-right whitespace-nowrap">
                      <button
                        type="button"
                        aria-label={`Удалить ${name}`}
                        onClick={() => remove(row.key)}
                        className={rowButton}
                      >
                        Удалить
                      </button>
                    </td>
                  </tr>
                );
              }
              levelNumber += 1;
              const number = levelNumber;
              const field = (name: LevelField, label: string) => (
                <td className="px-1 py-1">
                  <input
                    type="number"
                    required
                    aria-label={`Уровень ${number}: ${label}`}
                    value={row[name]}
                    onChange={(event) => update(row.key, name, event.target.value)}
                    className={cellInput}
                  />
                </td>
              );
              return (
                <tr key={row.key}>
                  <td className="py-1 pr-2 font-medium text-slate-900">{number}</td>
                  {field("small_blind", "малый блайнд")}
                  {field("big_blind", "большой блайнд")}
                  {field("ante", "анте")}
                  {field("duration_minutes", "минут")}
                  <td className="py-1 text-right whitespace-nowrap">
                    <button
                      type="button"
                      aria-label={`Добавить перерыв после уровня ${number}`}
                      onClick={() => addBreakAfter(index)}
                      className={rowButton}
                    >
                      + перерыв
                    </button>
                    <button
                      type="button"
                      aria-label={`Удалить уровень ${number}`}
                      onClick={() => remove(row.key)}
                      className={rowButton}
                    >
                      Удалить
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <button
        type="button"
        onClick={() => onChange([...rows, nextLevel(rows)])}
        className="mt-2 rounded-lg border border-slate-300 px-3 py-1 text-sm"
      >
        Добавить уровень
      </button>
    </div>
  );
}
