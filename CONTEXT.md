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

**Club Player List**: The players who have been to a club or chose it as their club in the bot. An admin sees, searches and registers only their own club's players. Entering a phone the league already knows adds that player to the club instead of creating a second one; the existing name is kept.

**Consent (согласие на обработку персональных данных)**: The player's agreement to the processing of personal data under 152-ФЗ. The admin ticks it when adding a player; without it no player is added. In the bot the player gives it themselves, before anything else; without it the bot goes no further.

**Telegram Link (привязка Telegram)**: A player's Telegram account tied to their player by the phone they share with the bot. Only the user's own contact counts, as Telegram confirms that number is theirs. A phone the league knows links to that player, keeping the name the club typed; a new phone makes a new player named as in Telegram. One Telegram account per player: the account that last shared the phone.

**Player's Club (in the bot)**: The club the player chose in the bot: the bot shows its schedule, and the player joins its Club Player List. The player can change it (`/club`).

**Schedule (расписание)**: A club's tournaments that have not started and are not cancelled, the ten soonest, with date, time (league time) and buy-in. One the admin has neither started nor cancelled drops out once its check-in closes, 12 hours after its start.

**Status**: Player's loyalty tier (auto-calculated from number of games, ЮДС integration). Affects discount on buy-in.

**Registration**: A club player signed up for a tournament, at most once per tournament. States: Registered → Checked In → In Game (seated) → Out (finished with a place). Players sign up until the tournament is started, however late that is, and afterwards only during Late Registration; they drop out only before the start.

**Check-in**: Marking on the day that a registered player has come to the club; the player pays the buy-in then. Open from 12 hours before the tournament's start time to 12 hours after it, and closed once the tournament is started: a player who comes later is seated through Late Registration, which checks them in. A mistaken check-in can be taken back while check-in is open, which gives the buy-in back by a storno. Clubs have no time zone yet, which is why this is a window around the start rather than a calendar day.

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

**Buy-in**: The entry fee: rent of the table and the dealer's work, not a stake. Paid in cash or by card when the player comes (check-in), or when a latecomer sits down through Late Registration; a player who drops out before the start, or whose tournament is cancelled, gets it back by a storno. Signing up (also from the bot) costs nothing. Online payment is Phase 2+.

**Knock-out**: A player leaving the game for good (unless they re-enter). The admin marks it; it gives the player their Place. A knock-out marked by mistake can be undone while the tournament is live: the player sits down again, and it is not a re-entry.
_Avoid_: Bust, elimination (in the admin panel)

**Re-entry**: Player's option to buy back in after a knock-out, taking a new seat and a new starting stack. Allowed up to and including a given level ("re-entry until level N"), or not offered at all; as many times as the window allows. Costs the buy-in.

**Add-on**: Player's option to buy extra chips at a fixed point in the tournament: at a given level, or not offered at all. Gives as many chips as the tournament says (its add-on stack) and costs its add-on price. One per entry: a player who re-entered can take it again.

**Average Stack**: All the chips in play shared among the players still at the tables: a starting stack for every entry (the first one and each re-entry) and the add-on stack for every add-on. A knocked-out player's chips stay in play.

**Late Registration**: Window during which new players can join, and registered players who came late can sit down, in a started tournament: up to and including a given level, or not offered at all.

Rule levels always refer to blind level numbers (breaks not counted) and must exist in the tournament's structure. A break belongs to the level before it: on the break after level N the windows of level N are still open, which is when clubs usually give the add-on.

**Seating**: Assignment of players to tables and seats. At the start the system draws everyone who has come at random over as few tables as fit them, with player counts differing by at most one. A latecomer or a re-entry gets a random free seat at the table with the fewest players.

**Move (пересадка)**: One player moved to another table to keep tables even. After knock-outs the system suggests the next move (a table no longer needed is broken up first, one player at a time) and the admin makes it; a move can also go to any other free seat.
_Avoid_: Rebalance, reseat

**Final Table**: The one table left once the remaining players fit at it. The system assembles it by itself right after the knock-out that makes this possible, drawing every seat again.

**Place (Finish)**: Where a player finished. Whoever finishes later places higher; the last player standing wins (place 1) and finishes the tournament. A re-entry or a late player after a knock-out moves that knocked-out player's place down. Determines rating points. Places run from 1 to the number of players, each player counted once however many times they re-entered; no two players share a place.

**Result**: A player's place and points in a finished tournament. Fixed when the tournament finishes (ADR-0008); until then places follow the order of knock-outs.

**Place Correction**: The admin puts a player of a finished tournament on the place they really finished in; the players between the old and the new place move by one, and everyone's points and the club rating are counted again. In a live tournament a mistaken knock-out is undone instead.
_Avoid_: Edit result, override

### Rating & Leaderboard

**Rating**: A player's cumulative score across tournaments. Calculated from places (1st = most points, out = 0) and bounties (KO format; not yet).

**Club Rating**: The points each player has scored in the club's finished tournaments of a season, added up; the most first, and equal points share a position. Only the club's own tournaments count. Worked out on every request, so a place correction shows at once.

**Rating Level**: Hierarchical: Club Rating → City Rating → Russia/CIS Rating. Separate leaderboards.

**Season (Period)**: A half of the year: 1 January – 30 June or 1 July – 31 December, midnight to midnight in the league's time (UTC+7). The club rating starts again every season. A tournament belongs to the season its scheduled start falls in, however late it finishes. Earlier seasons stay viewable.

**Points**: Rating points for a place. The league's default formula: 10 × (√(players ÷ place) − 1), rounded to a whole point; the winner of a bigger field gets more (4 of 2, 20 of 9, 50 of 36) and the last place always 0. League-wide, one formula in the MVP; stored with each result, so a later formula does not rewrite old seasons.

### Cashier & Financial

**Cashier (Касса)**: The financial ledger of a tournament: its transactions and their summary by kind of operation (buy-in, re-entry, add-on), by payment method, and in all. Exported to CSV for Excel. Money only comes in: sport poker has no prizes to pay out. Worked out from the transactions on every request (ADR-0009).

**Transaction**: A single payment of a tournament: a buy-in, a re-entry or an add-on, at the price the tournament's rules set, paid in cash or by card and taken by a named admin. Recorded by the action itself (check-in, late seat, re-entry, add-on), never typed in by hand. Only ever added, never changed or deleted. A free operation (price 0) makes none.
_Avoid_: Payment record, entry (for the money)

**Payment Method**: Cash (наличные) or card (карта). Every transaction has one.

**Storno (сторно)**: A transaction of the opposite amount that reverses a mistaken one; the original stays in the history, marked reversed. A transaction is reversed at most once, and a storno is never reversed. Reversing money does not change the game: a mistaken knock-out is undone in the game.

**Payment Method Change**: Putting right a payment taken the wrong way: a storno of it and the same payment taken again the other way, in one go.

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

**Telegram Bot**: The players' entry point in Telegram: consent, Telegram Link, the player's club and its schedule (`/start`, `/schedule`, `/club`); signing up for tournaments, rating and reminders come next. Answers private chats only.

**Web Cabinet (ЛК)**: Web-based personal account. Player sees their profile, history, rating. Login via phone/VK/Telegram.

**Admin Panel**: Web dashboard for admins to run tournaments, manage players, track cash.

**Dealer Cabinet**: Minimal screen for dealers showing their table, seating, rotation alerts, dispute-raise button.

**Hall Board (Табло)**: A full-screen page on a TV in the club's hall: the blind level and ante, the countdown, the next level, the players left and re-entries made, the average stack and the time to the next break, in the club's colours with the club's and the league's marks. No player names. Opens without login by the tournament's Board Link; every admin change reaches it in under a second over a WebSocket, and it reconnects by itself (ADR-0007).
_Avoid_: Tabletop

**Board Link**: `/board/<board token>`, the address of a tournament's hall board. The board token (`board_token` in code) is twelve random characters, so the link cannot be guessed from the tournament's number. The admin sees the link on the tournament's running page.

**WebSocket**: Real-time sync from the backend to the Hall Board (later also the bot): after every change the board is sent afresh.

---

## Architecture Overview

**Layers:**

- **Backend API** (FastAPI, Python): Manages tournaments, players, ratings, cash. Exposes REST + WebSocket.
- **Telegram Bot** (aiogram, Python): Primary player entry point. The `bot` service runs the backend's code (`app/bot/`) by long polling and works with the database directly; where each player has got to is stored in `telegram_users`, so a restart loses nothing (ADR-0010).
- **Web Frontend** (React, TS): Admin Panel, Player Cabinet, Dealer Cabinet, Hall Board (`/board/<board token>`).
- **Database** (PostgreSQL): Multi-tenant via shared tables with a `club_id` column; access is enforced by the `AdminClub` dependency on every `/api/clubs/{club_id}/...` route (ADR-0003). Accessed via SQLAlchemy 2 with sync sessions (ADR-0002); Alembic migrations run automatically on backend start.
- **Players**: League-wide `players` (one per phone), each club's list in `club_players`, and `registrations` of a club's players for its tournaments (ADR-0005).
- **Running a tournament**: the game lives in the tournament row (status, blind clock) and in its registrations (seat, finish order, re-entries, add-ons); the blind clock is worked out from the time, with no background job (ADR-0006).
- **Cashier**: every paid action writes a row to `transactions` (`app/transactions.py`); a storno is another row pointing at the one it reverses. The cashier's summary and the CSV are worked out from the rows on every request (`app/cashier.py`, ADR-0009).
- **Results and rating**: the last knock-out fixes every player's place and points in their registration; a place correction rewrites them. The club rating adds the points up per season on every request, with no table of its own (ADR-0008).
- **Realtime**: after committing a change, the backend tells the tournament's watchers "it has changed" (`app/realtime.py`, in-process); each connected hall board reads the board afresh and gets it over its WebSocket. One backend process only for now (ADR-0007).
- **Integrations**: iiko (cashier), ЮДС (loyalty), Telegram API, VK ID (auth).

**MVP (Phase 1):**
- Core tournament engine (register, seat, blind timer, results)
- Telegram bot for players (register, see rating, get reminders)
- Admin web panel (manage tournament, track cash)
- Hall board (browser-based timer on the hall's TV)
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

6. **Realtime is a hard requirement**: the Hall Board must show every admin change in <1s. WebSocket mandatory.

---

## Running the Project

Requires Docker (Docker Desktop on Windows/macOS). Repo layout: `backend/` (FastAPI + Alembic), `frontend/` (React + Vite), `docker-compose.yml` at the root.

```bash
# Start everything: PostgreSQL, backend (applies migrations on start), frontend, Telegram bot
docker compose up --build
```

- Frontend: http://localhost:5173 (admin login; API and database status in the footer)
- Hall board: http://localhost:5173/board/<board token>, no login; the admin panel shows the link on a tournament's running page ("Проведение")
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

### Telegram bot

The `bot` service starts with the rest once the backend is healthy (migrations applied). It needs a token: create a bot with @BotFather in Telegram and put it in a `.env` file at the repo root (git-ignored):

```bash
TELEGRAM_BOT_TOKEN=123456789:AA...
```

Then `docker compose up -d bot` (or `docker compose restart bot` after changing the bot's code: unlike the backend it does not reload by itself). Without a token the bot logs how to get one and stops. Watch it with `docker compose logs -f bot`. One bot process per token: Telegram gives the updates to one polling process only.

---

## Links & References

- **Spec**: See GitHub Issues tagged `ready-for-agent`
- **Architecture Decisions**: See `docs/adr/`
- **Setup**: See `CLAUDE.md`
- **GitHub Repo**: (To be set up on GitHub)

---

**Last updated**: 2026-09-29  
**Owner**: Matt Getsov
