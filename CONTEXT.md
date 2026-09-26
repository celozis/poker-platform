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

**Club Branding**: A club's logo and two colours (primary, accent). The Admin Panel is dressed in the admin's club branding; the league mark is always shown next to it.

**Tenant**: A club, as the unit of data isolation. Club-owned rows carry `club_id`; an admin reaches only their own club's data (ADR-0003).

### Players & Identity

**Player**: A person who plays tournaments. Has a profile (phone, name, Telegram/VK ID), status (Guest → Regular → VIP, per ЮДС loyalty system), and rating. One player per phone number across the whole league: a person who plays in several clubs is the same player everywhere (ADR-0005).

**Club Player List**: The players who have been to a club. An admin sees, searches and registers only their own club's players. Entering a phone the league already knows adds that player to the club instead of creating a second one; the existing name is kept.

**Consent (согласие на обработку персональных данных)**: The player's agreement to the processing of personal data under 152-ФЗ. The admin ticks it when adding a player; without it no player is added.

**Status**: Player's loyalty tier (auto-calculated from number of games, ЮДС integration). Affects discount on buy-in.

**Registration**: A club player signed up for a tournament, at most once per tournament. States: Registered → Checked In → In Game (seated) → Out (finished with a place). Players sign up until the tournament is started, however late that is, and afterwards only during Late Registration; they drop out only before the start.

**Check-in**: Marking on the day that a registered player has come to the club. Open from 12 hours before the tournament's start time to 12 hours after it, and closed once the tournament is started: a player who comes later is seated through Late Registration, which checks them in. A mistaken check-in can be taken back while check-in is open. Clubs have no time zone yet, which is why this is a window around the start rather than a calendar day.

### Tournaments

**Tournament**: A structured poker game event at a specific club on a specific date/time. Has: name, start time, buy-in, starting stack, seats per table, blind structure, rules (re-entry, add-on, late registration). States: Created (`scheduled` in code) → Running ⇄ Paused → Finished, or Created → Cancelled. A tournament is **started** when the admin starts it, not when its start time comes; a finished one is never started again. Only a tournament that has not started can be edited or cancelled; a cancelled one stays on the list, marked as cancelled.
_Avoid_: "In Progress" (say Running)

**Live Tournament**: One that is Running or Paused: players are knocked out, re-enter, take add-ons and sit down.

**Seats per Table**: How many players a table of this tournament seats, from 2 to 10; 9 unless the admin says otherwise.

**Blind Structure**: The tournament's levels and breaks in play order. Stored as a whole with the tournament (ADR-0004).

**Blind Level**: A row in the tournament's structure. Defines: small blind, big blind, ante, duration. Levels are numbered 1..N in play order; breaks are not numbered.

**Blind Clock**: The timer of a started tournament: which level or break is being played and how much of it is left. It moves on to the next level or break by itself when time is up; the admin can pause it and switch to the next or previous level or break, which then starts from its full duration. The last level goes on with no time left.

**Break**: A pause between levels in the blind structure. Has only a duration.

**Blind Structure Template**: A league-wide ready-made blind structure (e.g. "Стандартная лиги", "Турбо"). The admin picks one when creating a tournament and adjusts the copy. In the MVP templates live in backend code (ADR-0004).

**Buy-in**: The entry fee (registration cost). Paid either cash-on-entry or online through app.

**Knock-out**: A player leaving the game for good (unless they re-enter). The admin marks it; it gives the player their Place.
_Avoid_: Bust, elimination (in the admin panel)

**Re-entry**: Player's option to buy back in after a knock-out, taking a new seat. Allowed up to and including a given level ("re-entry until level N"), or not offered at all; as many times as the window allows.

**Add-on**: Player's option to buy extra chips at a fixed point in the tournament: at a given level, or not offered at all. One per entry: a player who re-entered can take it again.

**Late Registration**: Window during which new players can join, and registered players who came late can sit down, in a started tournament: up to and including a given level, or not offered at all.

Rule levels always refer to blind level numbers (breaks not counted) and must exist in the tournament's structure. A break belongs to the level before it: on the break after level N the windows of level N are still open, which is when clubs usually give the add-on.

**Seating**: Assignment of players to tables and seats. At the start the system draws everyone who has come at random over as few tables as fit them, with player counts differing by at most one. A latecomer or a re-entry gets a random free seat at the table with the fewest players.

**Move (пересадка)**: One player moved to another table to keep tables even. After knock-outs the system suggests the next move (a table no longer needed is broken up first, one player at a time) and the admin makes it; a move can also go to any other free seat.
_Avoid_: Rebalance, reseat

**Final Table**: The one table left once the remaining players fit at it. The system assembles it by itself right after the knock-out that makes this possible, drawing every seat again.

**Place (Finish)**: Where a player finished. Whoever finishes later places higher; the last player standing wins (place 1) and finishes the tournament. A re-entry or a late player after a knock-out moves that knocked-out player's place down. Determines rating points.

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

**Admin (Администратор)**: Runs tournaments: register players, manage seating, track results, handle disputes. Belongs to exactly one club.

**Login Code**: A six-digit one-time code for passwordless login by phone number. Valid for 5 minutes, burns after 5 wrong tries, and a new one is sent at most once a minute. In the prototype it is written to the backend log instead of being sent by SMS.

**Admin Session**: What a successful login creates: an HttpOnly cookie holding a random token, stored hashed on the server for 7 days. Logout deletes it on the server.

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
- **Database** (PostgreSQL): Multi-tenant via shared tables with a `club_id` column; access is enforced by the `AdminClub` dependency on every `/api/clubs/{club_id}/...` route (ADR-0003). Accessed via SQLAlchemy 2 with sync sessions (ADR-0002); Alembic migrations run automatically on backend start.
- **Players**: League-wide `players` (one per phone), each club's list in `club_players`, and `registrations` of a club's players for its tournaments (ADR-0005).
- **Running a tournament**: the game lives in the tournament row (status, blind clock) and in its registrations (seat, finish order, re-entries, add-ons); the blind clock is worked out from the time, with no background job (ADR-0006).
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

- Frontend: http://localhost:5173 (admin login; API and database status in the footer)
- Backend API: http://localhost:8000 (health check: `/api/health`, docs: `/docs`)
- PostgreSQL: `localhost:5433`, user/password `poker`/`poker`, databases `poker` (dev) and `poker_test` (tests). Host port 5433 avoids clashing with a locally installed PostgreSQL.

### Test clubs and admin login

```bash
# With the stack running (`docker compose up`, which applies migrations first),
# create (or refresh) the two test clubs and their admins; safe to run again
docker compose exec backend python -m app.seed
```

| Club | Admin | Phone |
|---|---|---|
| Покер-клуб «Обь» | Анна Соколова | +7 999 000-00-01 |
| Покер-клуб «Енисей» | Дмитрий Орлов | +7 999 000-00-02 |

To log in, enter the phone on http://localhost:5173 and read the code from the backend log (no SMS is sent in the prototype):

```bash
docker compose logs backend | grep "Код входа"
```

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

**Last updated**: 2026-09-26  
**Owner**: Matt Getsov
