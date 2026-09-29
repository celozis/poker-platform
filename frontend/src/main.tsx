import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Board from "./Board";
import Cabinet from "./Cabinet";
import "./index.css";

// The hall board lives at /board/<its secret code> and needs no login; the admin panel at /admin;
// everything else is the player's cabinet, the address players are given.
const path = window.location.pathname;
const board = path.match(/^\/board\/(\w+)\/?$/);

function Page() {
  if (board) return <Board token={board[1]} />;
  if (/^\/admin\/?$/.test(path)) return <App />;
  return <Cabinet />;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <Page />
  </StrictMode>,
);
