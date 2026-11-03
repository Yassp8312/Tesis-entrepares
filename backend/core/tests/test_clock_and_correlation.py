from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone, tzinfo
from uuid import UUID

import pytest

from core.clock import FixedClock, SystemClock, as_utc
from core.correlation import OperationContext
from core.identifiers import new_id


@pytest.mark.parametrize("offset", [-5, 0, 3])
def test_fixed_clock_preserves_instant_and_precision_as_utc(offset):
    instant = datetime(2026, 10, 24, 8, 30, 45, 123456, tzinfo=timezone(timedelta(hours=offset)))
    clock = FixedClock(instant)
    assert clock.now() == instant
    assert clock.now().tzinfo is UTC
    assert clock.now().microsecond == 123456


class UndefinedOffset(tzinfo):
    def utcoffset(self, dt):
        return None


@pytest.mark.parametrize(
    "instant",
    [datetime(2026, 10, 24), datetime(2026, 10, 24, tzinfo=UndefinedOffset())],
)
def test_fixed_clock_rejects_ambiguous_instants(instant):
    with pytest.raises(ValueError, match="sin zona"):
        FixedClock(instant)


def test_time_conversion_rejects_a_calendar_date_string():
    with pytest.raises(TypeError):
        as_utc("2026-10-24")


def test_system_clock_is_aware_utc():
    assert SystemClock().now().tzinfo is UTC


def test_identifiers_are_independent_uuid4_values():
    first, second = new_id(), new_id()
    assert isinstance(first, UUID) and first.version == 4
    assert isinstance(second, UUID) and second.version == 4
    assert first != second


def test_operation_rechecks_injected_clock_without_changing_correlation():
    class AdvancingClock:
        instant = datetime(2026, 10, 24, tzinfo=UTC)

        def now(self):
            return self.instant

    clock = AdvancingClock()
    context = OperationContext.start(clock=clock)
    correlation = context.correlation_id
    before = context.now()
    clock.instant += timedelta(seconds=1)
    assert context.now() == before + timedelta(seconds=1)
    assert context.correlation_id == correlation
    assert context.correlation_id.version == 4


def test_separate_operations_keep_their_own_clock_and_correlation():
    first_clock = FixedClock(datetime(2026, 10, 24, tzinfo=UTC))
    second_clock = FixedClock(datetime(2026, 10, 25, tzinfo=UTC))
    first = OperationContext.start(clock=first_clock)
    second = OperationContext.start(clock=second_clock)
    assert first.correlation_id != second.correlation_id
    assert first.now() == first_clock.now()
    assert second.now() == second_clock.now()
    with pytest.raises(FrozenInstanceError):
        first.correlation_id = second.correlation_id
    with pytest.raises(FrozenInstanceError):
        first_clock.instant = second_clock.instant


def test_operation_rejects_untyped_correlation_and_naive_clock():
    clock = FixedClock(datetime(2026, 10, 24, tzinfo=UTC))
    with pytest.raises(TypeError):
        OperationContext(correlation_id="identificador-del-cliente", clock=clock)

    class NaiveClock:
        def now(self):
            return datetime(2026, 10, 24)

    with pytest.raises(ValueError):
        OperationContext.start(clock=NaiveClock()).now()
