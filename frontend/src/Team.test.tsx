import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import type { ActionLogEntry, Admin } from "./api";
import { fakeBackend, ME } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

// The owner is the one logged in.
const OWNER: Admin = { ...ME.admin, role: "owner" };
const BORIS: Admin = { id: 2, name: "Борис Аксёнов", phone: "+79990000002", role: "admin" };
const SERGEY: Admin = { id: 21, name: "Сергей Лебедев", phone: "+79990000021", role: "admin" };

function clubEntry(
  id: number,
  action: ActionLogEntry["action"],
  admin: Admin | null,
  details: string,
  created_at: string,
): ActionLogEntry {
  return { id, created_at, action, admin, by_league: admin === null, player: null, details };
}

async function openTeam(options: Parameters<typeof fakeBackend>[0] = {}) {
  const fetch = fakeBackend({
    loggedIn: true,
    role: "owner",
    team: [OWNER, BORIS, SERGEY],
    ...options,
  });
  const user = userEvent.setup();
  render(<App />);
  await user.click(await screen.findByRole("button", { name: "Команда" }));
  await screen.findByRole("list", { name: "Команда клуба" });
  return { user, fetch };
}

function members() {
  return within(screen.getByRole("list", { name: "Команда клуба" }))
    .getAllByRole("listitem")
    .map((item) => item.textContent);
}

describe("club team", () => {
  it("shows the owner the club's owners and admins, and only admins can be removed", async () => {
    await openTeam();

    expect(members()).toEqual([
      "Анна Соколова+7 999 000-00-01Владелец",
      "Борис Аксёнов+7 999 000-00-02Убрать",
      "Сергей Лебедев+7 999 000-00-21Убрать",
    ]);
  });

  it("is not shown to an admin", async () => {
    fakeBackend({ loggedIn: true });
    render(<App />);

    expect(await screen.findByRole("button", { name: "Турниры" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Команда" })).not.toBeInTheDocument();
  });

  it("adds an admin by name and phone, who shows up in the team", async () => {
    const { user, fetch } = await openTeam();

    await user.type(screen.getByLabelText("Имя"), "Виктор Осипов");
    await user.type(screen.getByLabelText("Телефон"), "8 913 000-00-05");
    await user.click(screen.getByRole("button", { name: "Добавить сотрудника" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Виктор Осипов теперь в команде");
    expect(fetch).toHaveBeenCalledWith(
      `/api/clubs/${ME.club.id}/team`,
      expect.objectContaining({ method: "POST" }),
    );
    expect(members()).toContain("Виктор Осипов+7 913 000-00-05Убрать");
    expect(screen.getByLabelText("Имя")).toHaveValue("");
  });

  it("says when an admin removed before is back in the team", async () => {
    const { user } = await openTeam({
      removedFromTeam: [{ id: 31, name: "Виталий Осипов", phone: "+79990000031", role: "admin" }],
    });

    await user.type(screen.getByLabelText("Имя"), "Виталий");
    await user.type(screen.getByLabelText("Телефон"), "+7 999 000-00-31");
    await user.click(screen.getByRole("button", { name: "Добавить сотрудника" }));

    expect(await screen.findByRole("status")).toHaveTextContent("Виталий Осипов снова в команде");
    expect(members()).toContain("Виталий Осипов+7 999 000-00-31Убрать");
  });

  it("shows why a phone cannot be added, keeping what was typed", async () => {
    const { user } = await openTeam();

    await user.type(screen.getByLabelText("Имя"), "Борис");
    await user.type(screen.getByLabelText("Телефон"), "+7 999 000-00-02");
    await user.click(screen.getByRole("button", { name: "Добавить сотрудника" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("Борис Аксёнов уже в команде клуба");
    expect(screen.getByLabelText("Имя")).toHaveValue("Борис");
    expect(members()).toHaveLength(3);
  });

  it("removes an admin after the owner confirms, and they leave the team", async () => {
    const confirm = vi.fn<(question: string) => boolean>(() => true);
    vi.stubGlobal("confirm", confirm);
    const { user, fetch } = await openTeam();

    const boris = screen.getByRole("listitem", { name: "Борис Аксёнов" });
    await user.click(within(boris).getByRole("button", { name: "Убрать" }));

    expect(confirm).toHaveBeenCalledWith(
      "Убрать из команды: Борис Аксёнов? Вход в админ-панель закроется сразу, имя останется в кассе и журнале.",
    );
    expect(await screen.findByRole("status")).toHaveTextContent("Борис Аксёнов больше не в команде");
    expect(fetch).toHaveBeenCalledWith(
      `/api/clubs/${ME.club.id}/team/${BORIS.id}`,
      expect.objectContaining({ method: "DELETE" }),
    );
    expect(members()).toEqual([
      "Анна Соколова+7 999 000-00-01Владелец",
      "Сергей Лебедев+7 999 000-00-21Убрать",
    ]);
  });

  it("keeps the admin when the owner thinks better of it", async () => {
    vi.stubGlobal("confirm", vi.fn(() => false));
    const { user, fetch } = await openTeam();

    const boris = screen.getByRole("listitem", { name: "Борис Аксёнов" });
    await user.click(within(boris).getByRole("button", { name: "Убрать" }));

    expect(fetch).not.toHaveBeenCalledWith(expect.stringContaining("/team/"), expect.anything());
    expect(members()).toHaveLength(3);
  });

  it("shows the club's log of team changes, the league's among them, the latest first", async () => {
    await openTeam({
      clubLog: [
        clubEntry(2, "admin_removed", OWNER, "Виталий Осипов, +7 999 000-00-31", "2026-10-02T13:00:00Z"),
        clubEntry(1, "owner_appointed", null, "Анна Соколова, +7 999 000-00-01", "2026-09-01T05:00:00Z"),
      ],
    });

    // Times in the club's time, Novosibirsk.
    const log = await screen.findByRole("list", { name: "Журнал клуба" });
    expect(within(log).getAllByRole("listitem").map((item) => item.textContent)).toEqual([
      expect.stringMatching(/2 окт\.?, 20:00.*Сотрудник убран.*Анна Соколова · Виталий Осипов, \+7 999 000-00-31$/),
      expect.stringMatching(/1 сент\.?, 12:00.*Назначен владелец.*лига · Анна Соколова, \+7 999 000-00-01$/),
    ]);
  });

  it("puts a change of the team in the club's log at once", async () => {
    const { user } = await openTeam();

    await user.type(screen.getByLabelText("Имя"), "Виктор Осипов");
    await user.type(screen.getByLabelText("Телефон"), "+7 913 000-00-05");
    await user.click(screen.getByRole("button", { name: "Добавить сотрудника" }));

    const log = await screen.findByRole("list", { name: "Журнал клуба" });
    expect(within(log).getByRole("listitem")).toHaveTextContent(
      /Сотрудник добавлен.*Анна Соколова · Виктор Осипов, \+7 913 000-00-05/,
    );
  });

  it("says the admin was not removed when the server cannot be reached", async () => {
    vi.stubGlobal("confirm", vi.fn(() => true));
    const { user } = await openTeam({ down: [`DELETE /api/clubs/${ME.club.id}/team/${BORIS.id}`] });

    const boris = screen.getByRole("listitem", { name: "Борис Аксёнов" });
    await user.click(within(boris).getByRole("button", { name: "Убрать" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Сотрудник не убран: Не удалось связаться с сервером. Попробуйте ещё раз.",
    );
    expect(screen.queryByText("Сотрудник не добавлен:")).not.toBeInTheDocument();
    expect(members()).toHaveLength(3);
  });
});
