from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import count


@dataclass(frozen=True)
class AuditEntry:
    seq: int
    timestamp: str
    actor: str
    action: str
    entity_type: str
    entity_id: str
    details: dict = field(default_factory=dict)


class AuditLog:
    """Append-only audit trail."""

    def __init__(self):
        self._entries = []
        self._seq = count(1)

    def record(self, actor, action, entity_type, entity_id, details=None):
        entry = AuditEntry(next(self._seq),
                           datetime.now(timezone.utc).isoformat(),
                           actor or "system", action, entity_type,
                           entity_id, dict(details or {}))
        self._entries.append(entry)
        return entry

    def entries(self, entity_type=None, entity_id=None):
        return [e for e in self._entries
                if (entity_type is None or e.entity_type == entity_type)
                and (entity_id is None or e.entity_id == entity_id)]
