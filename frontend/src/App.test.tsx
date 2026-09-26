import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { fakeBackend, VALID_CODE } from "./testing/fakeBackend";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("admin login", () => {
  it("shows the login form with the league branding to a visitor", async () => {
    fakeBackend();

    render(<App />);

    expect(await screen.findByLabelText("Номер телефона")).toBeInTheDocument();
    expect(screen.getByText("Сибирская лига покера")).toBeInTheDocument();
  });

  it("logs the admin in with the code and opens the panel in the club's branding", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.type(await screen.findByLabelText("Код из SMS"), VALID_CODE);
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(
      await screen.findByRole("heading", { name: "Покер-клуб «Обь»" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("img", { name: "Логотип: Покер-клуб «Обь»" })).toHaveAttribute(
      "src",
      "/logos/ob.svg",
    );
    expect(screen.getByRole("banner")).toHaveStyle({ backgroundColor: "#0B3D91" });
    expect(screen.getByText("Сибирская лига покера")).toBeInTheDocument();
    expect(screen.getByText("Анна Соколова")).toBeInTheDocument();
  });

  it("keeps the admin out and says why when the code is wrong", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.type(await screen.findByLabelText("Код из SMS"), "000000");
    await user.click(screen.getByRole("button", { name: "Войти" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Неверный или просроченный код",
    );
    expect(screen.queryByRole("banner")).not.toBeInTheDocument();
  });

  it("lets the admin go back from the code step to fix the phone number", async () => {
    fakeBackend();
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000009");
    await user.click(screen.getByRole("button", { name: "Получить код" }));
    await user.click(await screen.findByRole("button", { name: "Изменить номер" }));

    expect(screen.getByLabelText("Номер телефона")).toHaveValue("+79990000009");
  });

  it("tells the admin when the server cannot be reached", async () => {
    fakeBackend({ down: ["POST /api/auth/request-code"] });
    const user = userEvent.setup();
    render(<App />);

    await user.type(await screen.findByLabelText("Номер телефона"), "+79990000001");
    await user.click(screen.getByRole("button", { name: "Получить код" }));

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "Не удалось связаться с сервером",
    );
  });

  it("logs the admin out back to the login form", async () => {
    const fetch = fakeBackend({ loggedIn: true });
    const user = userEvent.setup();
    render(<App />);

    await user.click(await screen.findByRole("button", { name: "Выйти" }));

    expect(await screen.findByLabelText("Номер телефона")).toBeInTheDocument();
    expect(fetch).toHaveBeenCalledWith("/api/auth/logout", expect.objectContaining({ method: "POST" }));
  });
});
