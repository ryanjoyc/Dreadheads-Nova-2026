"""Order traffic by time slot, forecasts, and rush (spike) detection.

Plain Python does every calculation here. Traffic is read through
`analytics.scoped_lines`, which pages the `/order-lines` and `/stores` query functions.
Order volume counts distinct orders, as the README requires.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time, timedelta
from statistics import mean
from typing import Any

from sqlalchemy.orm import Session

from nova_backend.analytics import scoped_lines
from nova_backend.schemas import OrderScope

RUSH_RATIO = 1.5  # A rush slot expects at least 1.5x the typical active slot...
MIN_RUSH_ORDERS = 2.0  # ...and at least this many orders.
BUSY_DAY_RATIO = 1.25  # A past day "had" the rush if the window ran 1.25x typical.
DAY_MINUTES = 24 * 60


def label(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def minute_of(value: time) -> int:
    return value.hour * 60 + value.minute


def day_traffic(
    session: Session, scope: OrderScope, day: date, slot_minutes: int
) -> dict[int, int]:
    """Distinct orders per slot on one store-local day, keyed by the slot's start minute."""
    params = scope.model_copy(
        update={
            "on_date": None,
            "date_start": day,
            "date_end": day + timedelta(days=1),
            "time_start": None,
            "time_end": None,
        }
    )
    placed = {
        line["order_id"]: line["placed_at_local"] for line, _ in scoped_lines(session, params)
    }
    counts: dict[int, int] = defaultdict(int)
    for moment in placed.values():
        minute = moment.hour * 60 + moment.minute
        counts[minute - minute % slot_minutes] += 1
    return dict(counts)


@dataclass
class Forecast:
    day: date
    slot_minutes: int
    history: dict[date, dict[int, int]] = field(default_factory=dict)
    expected: dict[int, float] = field(default_factory=dict)
    typical: float = 0.0
    threshold: float = MIN_RUSH_ORDERS

    def window_stats(self, start: int, end: int, multiplier: float = 1.0) -> dict[str, Any]:
        slots = list(range(start, end, self.slot_minutes))
        expected = [self.expected.get(s, 0.0) * multiplier for s in slots]
        peak = max(range(len(slots)), key=expected.__getitem__)
        busy_bar = self.typical * len(slots) * BUSY_DAY_RATIO
        busy_days = sum(
            1
            for counts in self.history.values()
            if sum(counts.get(s, 0) for s in slots) >= busy_bar
        )
        consistency = busy_days / len(self.history) if self.history else 0.0
        if len(self.history) < 3:
            confidence = "low"
        elif consistency >= 0.75:
            confidence = "high"
        elif consistency >= 0.5:
            confidence = "medium"
        else:
            confidence = "low"
        return {
            "start": label(start),
            "end": label(end),
            "peak_at": label(slots[peak]),
            "expected_orders": round(sum(expected), 1),
            "expected_peak_orders": round(expected[peak], 1),
            "intensity": round(expected[peak] / self.typical, 2) if self.typical else 0.0,
            "consistency": round(consistency, 2),
            "busy_days": busy_days,
            "confidence": confidence,
        }

    def rush_windows(self) -> list[tuple[int, int]]:
        """Contiguous runs of slots whose forecast meets the rush threshold."""
        windows: list[list[int]] = []
        for slot in sorted(self.expected):
            if self.expected[slot] >= self.threshold:
                if windows and windows[-1][1] == slot:
                    windows[-1][1] = slot + self.slot_minutes
                else:
                    windows.append([slot, slot + self.slot_minutes])
        return [(start, end) for start, end in windows]


def forecast(
    session: Session, scope: OrderScope, day: date, slot_minutes: int, weeks: int
) -> Forecast:
    """Average traffic per slot over the same weekday in the previous `weeks` weeks.

    Days with no recorded orders (before the data starts, or closed) are skipped.
    """
    result = Forecast(day=day, slot_minutes=slot_minutes)
    for back in range(1, weeks + 1):
        past = day - timedelta(weeks=back)
        counts = day_traffic(session, scope, past, slot_minutes)
        if counts:
            result.history[past] = counts
    if not result.history:
        return result
    slots = sorted({slot for counts in result.history.values() for slot in counts})
    result.expected = {
        slot: mean(counts.get(slot, 0) for counts in result.history.values()) for slot in slots
    }
    active = [value for value in result.expected.values() if value > 0]
    result.typical = mean(active) if active else 0.0
    result.threshold = max(result.typical * RUSH_RATIO, MIN_RUSH_ORDERS)
    return result


def day_spikes(counts: dict[int, int], slot_minutes: int) -> dict[str, Any]:
    """Summarize one past day's actual traffic and the slots that spiked on that day."""
    active = [value for value in counts.values() if value > 0]
    typical = mean(active) if active else 0.0
    bar = max(typical * RUSH_RATIO, MIN_RUSH_ORDERS)
    return {
        "total_orders": sum(counts.values()),
        "typical_orders_per_slot": round(typical, 2),
        "orders_by_slot": {label(s): counts[s] for s in sorted(counts)},
        "spike_slots": [label(s) for s in sorted(counts) if counts[s] >= bar],
    }
