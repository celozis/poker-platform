# Poker Platform: Domain & Context

**Project**: A digital platform for managing a network of sport poker clubs in Siberia.

**Status**: Greenfield project, beginning MVP development (2–3 clubs).

---

## Project Overview

We're building a system to replace manual tournament management (spreadsheets, chat, handwritten notes) with a digital platform that unifies game registration, cashier accounting, player ratings, and real-time synchronization across multiple clubs.

**Key stakeholders:**
- **Players** (guests): want easy registration, live rating, and tournament info
- **Club admins**: want to run tournaments fast, manage seating, track cash
- **Club owners**: want to see financials and attendance across their network
- **Dilers**: need to seat guests, track the game state, report results
- **The Siberian Poker League**: unifies independent clubs under one shared rating

**Non-goal**: This is NOT a gambling platform. It's sports poker (no money prizes, only bragging rights via rating).

---

## Domain Glossary

### Clubs & Organization

**Club**: A sports poker venue (e.g., "Club Moscow", "Club Novosibirsk"). Independent operation, own brand, own player base. Belong to the Siberian Poker League.

**League (Сибирская лига покера)**: The network that ties clubs together. Clubs operate independently but share a unified rating (club-level, city-level, Russia/CIS-level).

**Network**: The set of all clubs in the league.

### Players & Identity

**Player**: A person who plays tournaments. Has a profile (phone, name, Telegram/VK ID), status (Guest → Regular → VIP, per ЮДС loyalty system), and rating.

**Status**: Player's loyalty tier (auto-calculated from number of games, ЮДС integration). Affects discount on buy-in.

**Registration**: Player signs up for a tournament. States: Pending → Checked In → In Game → Out (place assigned) → Final Results.

### Tournaments

**Tournament**: A structured poker game event at a specific club on a specific date/time. Has: buy-in, starting stack, blind structure, rules (re-entry, add-on, late registration).

**Blind Level**: A row in the tournament's structure. Defines: small blind, big blind, ante, duration, which level it is.

**Buy-in**: The entry fee (registration cost). Paid either cash-on-entry or online through app.

**Re-entry**: Player's option to buy back in if they bust. Must happen during the re-entry window (first N levels, configurable).

**Add-on**: Player's option to buy extra chips at a fixed point in the tournament. Usually during the break before money (bubble).

**Late Registration**: Window during which new players can join an already-running tournament. Typically until a certain blind level.

**Seating**: Assignment of players to tables and positions. Auto-computed by the system, balanced to keep tables even.

**Final Table**: The last table when only N players remain. Automatically assembled when game reaches this stage.

**Place (Finish)**: Where a player finished (1st, 2nd, 3rd, out). Determines rating points.

### Rating & Leaderboard

**Rating**: A player's cumulative score across tournaments. Calculated from places (1st = most points, out = 0) and bounties (KO format).

**Rating Level**: Hierarchical: Club Rating → City Rating → Russia/CIS Rating. Separate leaderboards.

**Period**: Season or timeframe (e.g., September 2024 → January 2025). Resets for new periods.

**Points**: Numeric score for each tournament result. Formula defined per club or league-wide.

### Cashier & Financial

**Cashier (Касса)**: The financial ledger of a tournament and club. Records: buy-ins, re-entries, add-ons, payouts, rake (if any).

**Transaction**: A single cash movement (entry, re-entry, add-on, bar charge, payout). Recorded in real-time during tournament.

**iiko Integration**: The club's POS/cashier system (iiko is the target, but generalize). We sync tournament cash data to iiko and read back player balances.

**ЮДС System**: Loyalty/rewards system used by the club. We integrate to read player status and apply discounts.

### Roles & Permissions

**Admin (Администратор)**: Runs tournaments: register players, manage seating, track results, handle disputes.

**Floor Manager (Флор-менеджер)**: Oversees the game floor: resolves disputes, calls dealer rotations, enforces rules.

**Dealer (Диллер)**: Sits at a table, manages the game state, collects antes, and reports results.

**Bar Staff (Бар)**: Handles food/drink orders from the table.

**Owner (Владелец клуба)**: Views financials, stats, and player data. Configures club branding.

**Network Owner**: Views consolidated stats across all clubs in the network.

### Tech Terms

**Telegram Bot**: Mini-app inside Telegram for player registration and rating check. Primary entry point for players.

**Web Cabinet (ЛК)**: Web-based personal account. Player sees their profile, history, rating. Login via phone/VK/Telegram.

**Admin Panel**: Web dashboard for admins to run tournaments, manage players, track cash.

**Dealer Cabinet**: Minimal screen for dealers showing their table, seating, rotation alerts, dispute-raise button.

**Tabletop (Табло)**: Browser-based display (on a TV in the hall) showing current blind level, players in game, average stack. Live-synced.

**WebSocket**: Real-time sync between Admin Panel ↔ Tabletop ↔ Bot. Changes on admin instantly appear everywhere.

---

## Architecture Overview

**Layers:**

- **Backend API** (FastAPI, Python): Manages tournaments, players, ratings, cash. Exposes REST + WebSocket.
- **Telegram Bot** (aiogram, Python): Primary player entry point.
- **Web Frontend** (React, TS): Admin Panel, Player Cabinet, Dealer Cabinet, Tabletop.
- **Database** (PostgreSQL): Multi-tenant (per-club) schema or row-level security. Accessed via SQLAlchemy 2 with sync sessions (ADR-0002); Alembic migrations run automatically on backend start.
- **Integrations**: iiko (cashier), ЮДС (loyalty), Telegram API, VK ID (auth).

**MVP (Phase 1):**
- Core tournament engine (register, seat, blind timer, results)
- Telegram bot for players (register, see rating, get reminders)
- Admin web panel (manage tournament, track cash)
- Tabletop display (browser-based timer)
- 2–3 clubs running live

**Phase 2+:**
- Dealer cabinet
- Multi-level rating (city, Russia/CIS)
- iiko + ЮДС integrations
- Richer analytics
- Expand to all 50 clubs

---

## Known Constraints

1. **Sport poker model**: No money prizes, only rating points. Buy-in is for table rental + dealer fees. This shapes all our financial flows.

2. **Compliance (152-ФЗ)**: Player data in Russia must be on Russian servers, with proper consent collection. GDPR-like but simpler.

3. **Multi-tenancy from day 1**: 50 clubs planned. Database must support independent club data + shared (league-wide) rating.

4. **Integrations are read-heavy for now**: iiko is mature POS; we sync TO it, not replace it. ЮДС is external; we read status. Telegram is stateless; we webhook.

5. **No mobile app yet**: Telegram bot + web is the MVP. iOS/Android apps are deferred (Phase 3+).

6. **Realtime is a hard requirement**: Tabletop must show blind level and seating in <1s of admin change. WebSocket mandatory.

---

## Running the Project

Requires Docker (Docker Desktop on Windows/macOS). Repo layout: `backend/` (FastAPI + Alembic), `frontend/` (React + Vite), `docker-compose.yml` at the root.

```bash
# Start everything: PostgreSQL, backend (applies migrations on start), frontend
docker compose up --build
```

- Frontend: http://localhost:5173 (the home page shows API and database status)
- Backend API: http://localhost:8000 (health check: `/api/health`, docs: `/docs`)
- PostgreSQL: `localhost:5433`, user/password `poker`/`poker`, databases `poker` (dev) and `poker_test` (tests). Host port 5433 avoids clashing with a locally installed PostgreSQL.

### Running tests

Backend tests hit a real PostgreSQL (`poker_test`), so the `db` service must be running. `poker_test` is created only when the `pgdata` volume is first initialised; if your volume predates it, run `docker compose exec db createdb -U poker poker_test` once (or recreate the volume with `docker compose down -v`, which deletes dev data). The test fixture resets the schema and refuses to run against a database whose name doesn't end in `_test`.

```bash
# Backend: inside the container
docker compose run --rm backend pytest
docker compose run --rm backend mypy

# Backend: on the host (Python 3.12), with `docker compose up -d db` running
cd backend
python -m venv .venv && .venv/Scripts/pip install -r requirements-dev.txt   # .venv/bin/pip on Linux/macOS
.venv/Scripts/python -m pytest
.venv/Scripts/python -m mypy

# Frontend (Node 22)
cd frontend
npm ci
npm test
npm run typecheck
```

### Migrations

```bash
# Create a new migration after changing models
docker compose run --rm backend alembic revision --autogenerate -m "describe change"
# Migrations are applied automatically on backend start; to apply by hand:
docker compose run --rm backend alembic upgrade head
```

CI (GitHub Actions, `.github/workflows/ci.yml`) runs backend mypy + pytest against a PostgreSQL service container and frontend typecheck + tests on every push.

The Telegram bot (aiogram) is not part of the skeleton yet.

---

## Links & References

- **Spec**: See GitHub Issues tagged `ready-for-agent`
- **Architecture Decisions**: See `docs/adr/`
- **Setup**: See `CLAUDE.md`
- **GitHub Repo**: (To be set up on GitHub)

---

**Last updated**: 2026-09-25  
**Owner**: Matt Getsov
