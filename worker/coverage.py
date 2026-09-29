"""Observed unavailable intervals, independent of the technical index.

These boundaries describe when a poll observed availability, not the exact
instant a device failed or recovered. Nothing is inferred between samples.
"""
import uuid


class CoverageTracker:
    def __init__(self):
        self.open = {}
        self.started_ticks = {}
        self.last_usable = {}

    def observe(self, result, scope, tick, timestamp, emit, boundary='observed_at_poll'):
        name = result.detector
        gap = self.open.get(name)
        if result.status in ('available', 'partial'):
            if gap:
                self.close(name, tick, timestamp, 'measurements_resumed', emit)
            self.last_usable[name] = timestamp
            return
        if gap is None:
            gap = {
                'version': 1, 'gap_id': str(uuid.uuid4()), 'detector': name,
                'scope': scope, 'status': result.status, 'detail': result.detail,
                'started_at': timestamp, 'last_usable_at': self.last_usable.get(name),
                'ended_at': None, 'duration_seconds': None, 'end_reason': None,
                'boundary': boundary,
            }
            emit('coverage_gap_opened', gap)
            self.open[name] = gap
            self.started_ticks[name] = tick
        elif (gap['status'], gap['detail']) != (result.status, result.detail):
            updated = {**gap, 'status': result.status, 'detail': result.detail}
            emit('coverage_gap_updated', updated)
            self.open[name] = updated

    def close(self, name, tick, timestamp, reason, emit):
        closed = {**self.open[name], 'ended_at': timestamp,
                  'duration_seconds': round(max(0, tick - self.started_ticks[name]), 3),
                  'end_reason': reason}
        emit('coverage_gap_closed', closed)
        del self.open[name]
        del self.started_ticks[name]

    def finish(self, tick, timestamp, emit):
        for name in list(self.open):
            self.close(name, tick, timestamp, 'monitoring_stopped', emit)

    def snapshot(self):
        return [dict(gap) for gap in self.open.values()]
