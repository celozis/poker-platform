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

What is the league's to decide (which clubs there are, their names, who owns each) has no screen yet: the developer does it at the league's request.

**Network**: The set of all clubs in the league.

**Club Branding**: A club's logo and two colours (primary, accent). The Admin Panel is dressed in the admin's club branding; the league mark is always shown next to it.

**Club Settings (настройки клуба)**: What the club's Owner sets for the club: its Club Branding, the hall board's background, its address and the contact for players (the admins' phone or Telegram). The club's name is not among them: players across the league know the club by it, so only the league changes it.

**Sport Poker Notice (дисклеймер)**: «Спортивный покер. Игра не на деньги: взнос организационный, денежных призов нет. 18+». Shown at the bottom of the hall board and the Web Cabinet, and in the bot's greeting.

**Tenant**: A club, as the unit of data isolation. Club-owned rows carry `club_id`; an admin reaches only their own club's data (ADR-0003).

### Players & Identity

**Player**: A person who plays tournaments. Has a profile (phone, name, Telegram/VK ID), status (Guest → Regular → VIP, per ЮДС loyalty system), and rating. One player per phone number across the whole league: a person who plays in several clubs is the same player everywhere (ADR-0005).

**Club Player List**: The players who have been to a club, chose it as their club in the bot, or signed up for one of its tournaments. An admin sees, searches and registers only their own club's players. Entering a phone the league already knows adds that player to the club instead of creating a second one; the existing name is kept.

**Consent (согласие на обработку персональных данных)**: The player's agreement to the processing of personal data under 152-ФЗ. The admin ticks it when adding a player; without it no player is added. In the bot the player gives it themselves, before anything else; without it the bot goes no further.

**Site Registration (регистрация на сайте)**: A person whose phone the league does not know registers in the Web Cabinet: first name, surname, Nickname (optional) and Consent, then the Login Code. They choose no club: they see every club's schedule and join a club's list on first signing up for its tournament.

**Telegram Link (привязка Telegram)**: A player's Telegram account tied to their player by the phone they share with the bot. Only the user's own contact counts, as Telegram confirms that number is theirs. A phone the league knows links to that player, keeping the name the club typed; a new phone makes a new player named as in Telegram. One Telegram account per player: the account that last shared the phone.

**Player's Name**: First name and surname, entered as two fields on the site and in the admin's player form; a name from Telegram, or one typed before, is kept as it came. Only staff change it, so the club always knows who the player really is.

**Nickname (ник)**: A name a player chooses to be known by in public, instead of their real name. Optional. Given when registering on the site, typed by the admin, or set and changed by the player in the Web Cabinet at any time.

**Public Name (публичное имя)**: How a player is shown to other players and on the club's screens: their Nickname if they have one; otherwise the first word of their name in full and the first letter of the second word ("Иван П."), or the one word if the name has only one (a Telegram name of one word is most likely a nickname already). Staff in the Admin Panel see the full name and phone.
_Avoid_: Display name, short name

**Player's Club (in the bot)**: The club the player chose in the bot: the bot shows its schedule, and the player joins its Club Player List. The player can change it (`/club`).

**Player's Clubs (in the web cabinet)**: Every club whose Club Player List the player is on, in the order they joined them; the cabinet shows the rating and schedule of each.

**Schedule (расписание)**: A club's tournaments a player can still sign up for, the ten soonest, with date, time (league time) and buy-in: those that have not started and are not cancelled, and those going on while their Late Registration is open (marked as going on). One the admin has neither started nor cancelled drops out once its check-in closes, 12 hours after its start. Each has a button to sign up or, once signed up (marked in the schedule), to drop out; no drop-out button once the tournament is going on or the player has come.

**Status**: Player's loyalty tier (auto-calculated from number of games, ЮДС integration). Affects discount on buy-in.

**Registration**: A club player signed up for a tournament, at most once per tournament. States: Registered → Checked In → In Game (seated) → Out (finished with a place). Players sign up until the tournament is started, however late that is, and afterwards only during Late Registration; they drop out only before the start. The admin registers them, or they sign up themselves in the bot, by the same rules; in the bot a player who has come (checked in, so paid) cannot drop out: the admin gives the buy-in back.

**Check-in**: Marking on the day that a registered player has come to the club; the player pays the buy-in then. Open from 12 hours before the tournament's start time to 12 hours after it, and closed once the tournament is started: a player who comes later is seated through Late Registration, which checks them in. A mistaken check-in can be taken back while check-in is open, which gives the buy-in back by a storno. Clubs have no time zone yet, which is why this is a window around the start rather than a calendar day.

### Tournaments

**Tournament**: A structured poker game event at a specific club on a specific date/time. Has: name, start time, buy-in, starting stack, seats per table, blind structure, rules (re-entry, add-on, late registration). States: Created (`scheduled` in code) → Running ⇄ Paused → Finished, or Created → Cancelled. A tournament is **started** when the admin starts it, not when its start time comes; a finished one is never started again. Only a tournament that has not started can be edited or cancelled; a cancelled one stays on the list, marked as cancelled.
_Avoid_: "In Progress" (say Running)

**Live Tournament**: One that is Running or Paused: players are knocked out, re-enter, take add-ons and sit down.

**Seat Limit (лимит мест)**: The most players a tournament takes, if the admin sets one; no limit unless set. Counts players, not entries: a re-entry takes no new place. Once it is reached, a player signing up in the bot or the cabinet goes on the Waitlist; an admin may still register a player over it (the club puts out one more table).

**Waitlist (лист ожидания)**: The players who signed up for a tournament already at its Seat Limit, in the order they signed up. When a place frees up, the first of them is registered by itself and told so in the bot; one who can no longer come drops out, and the next moves up.

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

**Club Rating**: The points each player has scored in the club's finished tournaments of a season, added up; the most first, and equal points share a position. Only the club's own tournaments count. Worked out on every request, so a place correction shows at once. In the bot (`/rating`) a player sees their position and points in the current season and the club's top ten.

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

**Login Code**: A six-digit one-time code for passwordless login by phone number, to the Admin Panel or to the Web Cabinet: a code for one does not open the other, even for an admin who also plays. Valid for 5 minutes, burns after 5 wrong tries, and a new one is sent at most once a minute. In the prototype it is written to the backend log instead of being sent by SMS.

**Admin Session**: What a successful login creates: an HttpOnly cookie holding a random token, stored hashed on the server for 7 days. Logout deletes it on the server.

**Player Session**: The same for a player logged in to the Web Cabinet, in a cookie of its own that only the cabinet's addresses get. It opens nothing of the Admin Panel, and an Admin Session nothing of the cabinet.

**Action Log (журнал действий)**: What was done at the club, entry by entry: when, who did it (the admin, or «игрок» for what the player did themselves in the bot), what was done, to which player, and the details (from which seat to which, how much was paid or given back, which level the clock moved from and to). A tournament's log is what was done to it, from the first sign-up to a place corrected after the end; the admin reads it the latest first and can narrow it to one player, to settle a dispute. Written by the action itself, so an action is in the log if and only if it was done; an entry is never changed or deleted (ADR-0014). What is done to the club rather than to a tournament (its Team and Club Settings) will go in the club's log, an entry without a tournament; there is no such action yet.
_Avoid_: Audit trail, history (the Cashier's operations are the history of the money)

**Floor Manager (Флор-менеджер)**: Oversees the game floor: resolves disputes, calls dealer rotations, enforces rules.

**Dealer (Диллер)**: Sits at a table, manages the game state, collects antes, and reports results.

**Bar Staff (Бар)**: Handles food/drink orders from the table.

**Owner (Владелец клуба)**: Logs in to the Admin Panel as an admin does and can do all an admin can; alone sees the club's Reports. Belongs to exactly one club, like an admin (an admin with the role `owner`, ADR-0013). Manages the club's Team. Configuring club branding is not there yet.

**Team (команда клуба)**: The club's admins as the Owner sees them: the Owner adds an admin (name, phone) and removes one. Owners themselves are added by the league, not by another owner, since an owner sees the club's money; an owner cannot remove themselves.

**Club Report (Отчёт клуба)**: What the Owner sees of the club's tournaments that start in a period they pick (days from and to, league time, up to a year): the money (the Cashier's totals added up: by kind of operation and by payment method, and the tournaments held, those started), the attendance (the players who came to each tournament held, added up week by week, Monday to Sunday, and the players per tournament on average), and the best ten players by points and by tournaments played (the Club Rating of the period). Exported to CSV for Excel. Worked out on every request.

**Network Owner**: Views consolidated stats across all clubs in the network.

### Tech Terms

**Telegram Bot**: The players' entry point in Telegram: consent, Telegram Link, the player's club and its schedule with signing up and dropping out, the club rating (`/start`, `/schedule`, `/rating`, `/club`), and the Reminder and Result Notice it sends by itself. Answers private chats only.

**Reminder (напоминание)**: The bot's message to a registered player whose Telegram is linked, a set time before the tournament's start (`BOT_REMINDER_MINUTES`, two hours unless set): which tournament, when, the buy-in to bring, and how to drop out. Sent once, and only to those who registered before that time and have not come yet: one who signs up at the last moment, or is already at the club, needs no reminder. None for a tournament started or cancelled meanwhile; a tournament moved to another start is reminded of again.

**Result Notice**: The bot's message to a player whose Telegram is linked once their tournament has finished: their place of how many and the points it gives in the club rating. Sent once, and only for a tournament finished within the last day, so a player who links their Telegram later is not sent old results. A place corrected afterwards is not sent again.

**Web Cabinet (ЛК)**: The player's own page on the site's root address, laid out for a phone first. The player logs in by phone and Login Code (any player the league knows; an unknown phone goes through Site Registration first) and sees their profile (name, phone, their clubs, whether Telegram is linked), their position and points in the rating of each of their clubs this season, the Schedule of each of their clubs (marked where they are signed up), and the finished tournaments they played in any club, the latest first: date, tournament, club, place of how many, points, re-entries and add-ons. Which player is shown comes from the Player Session alone: no address takes a player's id (ADR-0012). VK/Telegram login is not there yet.

**Admin Panel**: Web dashboard for admins to run tournaments, manage players, track cash. The club's Owner logs in to it too and has one more section, the Club Report (`Отчёты`).

**Dealer Cabinet**: Minimal screen for dealers showing their table, seating, rotation alerts, dispute-raise button.

**Hall Board (Табло)**: A full-screen page on a TV in the club's hall: the blind level and ante, the countdown, the next level, the players left and re-entries made, the average stack and the time to the next break, in the club's colours with the club's and the league's marks. No player names, except on its Seating Screen.

**Seating Screen (рассадка на ТВ)**: The hall board's second view, which the admin switches the TV to: who sits at which table and seat, by Public Name. Mostly for the start of a tournament, so players find their seats without asking at the desk. Opens without login by the tournament's Board Link; every admin change reaches it in under a second over a WebSocket, and it reconnects by itself (ADR-0007).
_Avoid_: Tabletop

**Board Link**: `/board/<board token>`, the address of a tournament's hall board. The board token (`board_token` in code) is twelve random characters, so the link cannot be guessed from the tournament's number. The admin sees the link on the tournament's running page.

**WebSocket**: Real-time sync from the backend to the Hall Board, where after every change the board is sent afresh, and to the Admin Panel's registrations and running pages, which are sent just `changed` and read what they show afresh; a sign-up in the bot shows up there at once (ADR-0011).

---

## Architecture Overview

**Layers:**

- **Backend API** (FastAPI, Python): Manages tournaments, players, ratings, cash. Exposes REST + WebSocket.
- **Telegram Bot** (aiogram, Python): Primary player entry point. The `bot` service runs the backend's code (`app/bot/`) by long polling and works with the database directly; where each player has got to is stored in `telegram_users`, so a restart loses nothing (ADR-0010).
- **Web Frontend** (React, TS): Web Cabinet (the site's root), Admin Panel (`/admin`), Hall Board (`/board/<board token>`); Dealer Cabinet later.
- **Database** (PostgreSQL): Multi-tenant via shared tables with a `club_id` column; access is enforced by the `AdminClub` dependency on every `/api/clubs/{club_id}/...` route (ADR-0003). Accessed via SQLAlchemy 2 with sync sessions (ADR-0002); Alembic migrations run automatically on backend start.
- **Players**: League-wide `players` (one per phone), each club's list in `club_players`, and `registrations` of a club's players for its tournaments (ADR-0005).
- **Running a tournament**: the game lives in the tournament row (status, blind clock) and in its registrations (seat, finish order, re-entries, add-ons); the blind clock is worked out from the time, with no background job (ADR-0006).
- **Cashier**: every paid action writes a row to `transactions` (`app/transactions.py`); a storno is another row pointing at the one it reverses. The cashier's summary and the CSV are worked out from the rows on every request (`app/cashier.py`, ADR-0009).
- **Web Cabinet**: `/api/cabinet` (`app/cabinet.py`): login, logout and the whole cabinet in one `GET`, for the player of the Player Session. Sending and checking login codes and making session tokens are shared with the admin login (`app/auth.py`); the club schedule with the bot (`app/schedule.py`); the club rating's `club_standings` with the admin panel and the bot (ADR-0012).
- **Action log**: every action writes a row to `action_log` in the database transaction that makes the change (`app/action_log.py`, which depends on no routes, like `app/transactions.py`); the admin reads a tournament's at `/api/clubs/{club_id}/tournaments/{id}/log`, optionally `?player_id=` (`app/tournament_log.py`). There is no route that changes or deletes an entry (ADR-0014).
- **Owner's reports**: `/api/clubs/{club_id}/reports` and `.csv` (`app/reports.py`), behind `OwnerClub`, which lets through only the club's own owner (ADR-0013). The money comes from `transactions` with the cashier's `kind_totals` and `method_totals`, the best players from the rating's `club_standings`.
- **Results and rating**: the last knock-out fixes every player's place and points in their registration; a place correction rewrites them. The club rating adds the points up per season on every request, with no table of its own (ADR-0008).
- **Realtime**: a change of a tournament, in the backend or the bot, sends PostgreSQL `NOTIFY tournament_changed` in its own transaction, delivered once it commits; every backend process `LISTEN`s and wakes its watchers (`app/realtime.py`). Each connected hall board then reads the board afresh and gets it over its WebSocket (ADR-0007); an admin panel page gets `changed` over `/api/clubs/{club_id}/tournaments/{id}/ws` and reads afresh (ADR-0011).
- **Bot notifications**: the bot process looks every 30 seconds for reminders and results due and sends them; each registration keeps when they were sent (`app/bot/notifications.py`, ADR-0011).
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

- Player's web cabinet: http://localhost:5173 (login by a player's phone)
- Admin panel: http://localhost:5173/admin (admin or owner login; API and database status in the footer)
- Hall board: http://localhost:5173/board/<board token>, no login; the admin panel shows the link on a tournament's running page ("Проведение")
- Backend API: http://localhost:8000 (health check: `/api/health`, docs: `/docs`)
- PostgreSQL: `localhost:5433`, user/password `poker`/`poker`, databases `poker` (dev) and `poker_test` (tests). Host port 5433 avoids clashing with a locally installed PostgreSQL.

### Test clubs and admin login

```bash
# With the stack running (`docker compose up`, which applies migrations first),
# create (or refresh) the two test clubs with an admin and an owner each; safe to run again
docker compose exec backend python -m app.seed
```

| Club | Role | Name | Phone |
|---|---|---|---|
| Покер-клуб «Обь» | Admin | Анна Соколова | +7 999 000-00-01 |
| Покер-клуб «Обь» | Owner | Олег Владимиров | +7 999 000-00-11 |
| Покер-клуб «Енисей» | Admin | Дмитрий Орлов | +7 999 000-00-02 |
| Покер-клуб «Енисей» | Owner | Ирина Белова | +7 999 000-00-12 |

To log in, enter the phone on http://localhost:5173/admin (an owner the same way; the owner has the "Отчёты" section) and read the code from the backend log (no SMS is sent in the prototype). A player logs in to their cabinet on http://localhost:5173 the same way, with the phone the club or the bot has for them:

```bash
docker compose logs backend | grep "Код входа"
```

### Demo data

```bash
# Deletes every tournament and every player not linked to Telegram, then fills the dev database
# with a third club («Томь»), more staff, 60 players and 25 tournaments of every kind: finished
# (this season and the one before), going on now in every club (two at once in «Обь»), waiting
# for the start, coming, cancelled. Run again for a fresh set around the current time.
docker compose exec backend python -m app.demo
```

It plays everything through the API with the clock set back (`app/demo.py`), so places, points, cashiers, action logs and blind clocks are the system's own; a few players of «Обь» sign up and drop out by the bot's own rules, so the logs of «Турбо-серия» and «Кубок новичков» show «игрок» too. Demo players' phones are +7 913 500-00-01 … -60. More staff: Сергей Лебедев +7 999 000-00-21 (admin, «Обь»), Ольга Кравец +7 999 000-00-22 (admin, «Енисей»), Павел Громов +7 999 000-00-03 (admin, «Томь»), Наталья Широкова +7 999 000-00-13 (owner, «Томь»). A Telegram-linked player plays in the tournaments of «Енисей», so the bot sends them a result and a reminder.

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

Then `docker compose up -d bot` (or `docker compose restart bot` after changing the bot's code: unlike the backend it does not reload by itself). Without a token the bot logs how to get one and stops. Watch it with `docker compose logs -f bot`. One bot process per token: Telegram gives the updates to one polling process only. How long before the start the bot reminds players is `BOT_REMINDER_MINUTES` in the same `.env` (120 unless set).

---

## Links & References

- **Spec**: See GitHub Issues tagged `ready-for-agent`
- **Architecture Decisions**: See `docs/adr/`
- **Setup**: See `CLAUDE.md`
- **GitHub Repo**: (To be set up on GitHub)

---

**Last updated**: 2026-09-29  
**Owner**: Matt Getsov
