import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import Board from "./Board";
import "./index.css";

// The hall board lives at /board/<its secret code> and needs no login; everything else is the
// admin panel.
const board = window.location.pathname.match(/^\/board\/(\w+)\/?$/);

createRoot(document.getElementById("root")!).render(
  <StrictMode>{board ? <Board token={board[1]} /> : <App />}</StrictMode>,
);
