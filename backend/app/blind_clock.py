"""The blind timer: which item of the blind structure (a level or a break) is being played and how
much of it is left. Pure, no database: the tournament stores the item and either when it ends
(running) or how much of it was left (paused), and the clock works out the rest from the time.

Nothing ticks on the server. Whoever asks gets the clock `at(now)`, which has moved on through
every item that has ended since, so the timer goes on by itself without a background job."""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True)
class BlindClock:
    # How long each item of the structure lasts, in play order.
    durations: Sequence[timedelta]
    # The index of the item being played.
    item: int
    # When the item ends, while the clock runs.
    ends_at: datetime | None = None
    # How much of the item is left, while the clock is paused.
    remaining: timedelta | None = None

    @classmethod
    def started(cls, durations: Sequence[timedelta], now: datetime) -> "BlindClock":
        return cls(durations, 0, ends_at=now + durations[0])

    @property
    def running(self) -> bool:
        return self.ends_at is not None

    @property
    def _last(self) -> int:
        return len(self.durations) - 1

    def at(self, now: datetime) -> "BlindClock":
        """The clock as it is at `now`: every item that has ended since is behind it. The last
        level has nowhere to move on to, so it goes on with no time left."""
        item, ends_at = self.item, self.ends_at
        if ends_at is None:
            return self
        while now >= ends_at and item < self._last:
            item += 1
            ends_at += self.durations[item]
        return replace(self, item=item, ends_at=ends_at)

    def time_left(self, now: datetime) -> timedelta:
        current = self.at(now)
        if current.ends_at is None:
            assert current.remaining is not None
            return current.remaining
        return max(current.ends_at - now, timedelta(0))

    def paused(self, now: datetime) -> "BlindClock":
        current = self.at(now)
        return replace(current, ends_at=None, remaining=current.time_left(now))

    def resumed(self, now: datetime) -> "BlindClock":
        return replace(self, ends_at=now + self.time_left(now), remaining=None)

    def can_move(self, step: int, now: datetime) -> bool:
        return 0 <= self.at(now).item + step <= self._last

    def moved(self, step: int, now: datetime) -> "BlindClock":
        """The item `step` places away (1 forward, -1 back), from its start; a paused clock
        stays paused."""
        item = self.at(now).item + step
        assert 0 <= item <= self._last, "check can_move first"
        duration = self.durations[item]
        if self.running:
            return replace(self, item=item, ends_at=now + duration, remaining=None)
        return replace(self, item=item, ends_at=None, remaining=duration)
