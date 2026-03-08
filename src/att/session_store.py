"""Session store for Layer 3 evaluation state management.

Provides a protocol for session-scoped storage of evaluation results,
and an in-memory implementation as the default backend.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class SessionStore(Protocol):
    """Abstract interface for session-scoped evaluation result storage."""

    def get(self, session_id: str, message_id: str) -> dict[str, Any] | None:
        """Retrieve a stored evaluation result by session and message ID."""
        ...

    def put(self, session_id: str, result: dict[str, Any]) -> None:
        """Store an evaluation result keyed by session and message ID."""
        ...

    def get_ancestors(
        self,
        session_id: str,
        message_id: str,
        max_hops: int,
        parent_message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Walk parent_message_id chain up to max_hops ancestors.

        If parent_message_id is provided, start the chain from that ID
        (useful when the current message is not yet stored).

        Returns a list of ancestor results ordered from nearest to farthest.
        Each entry includes an extra '_hops' key indicating the hop distance.
        """
        ...

    def get_session_results(self, session_id: str) -> list[dict[str, Any]]:
        """Return all stored results for a session, in insertion order."""
        ...

    def clear(self, session_id: str | None = None) -> None:
        """Clear stored results. If session_id is given, clear only that session."""
        ...


class InMemorySessionStore:
    """In-memory implementation of SessionStore.

    Stores evaluation results in a dict keyed by (session_id, message_id).
    Suitable for single-process, non-persistent use cases.
    """

    def __init__(self) -> None:
        # session_id -> message_id -> result
        self._store: dict[str, dict[str, dict[str, Any]]] = defaultdict(dict)
        # session_id -> ordered list of message_ids (insertion order)
        self._order: dict[str, list[str]] = defaultdict(list)

    def get(self, session_id: str, message_id: str) -> dict[str, Any] | None:
        return self._store.get(session_id, {}).get(message_id)

    def put(self, session_id: str, result: dict[str, Any]) -> None:
        message_id = result.get("message_id", "")
        self._store[session_id][message_id] = result
        self._order[session_id].append(message_id)

    def get_ancestors(
        self,
        session_id: str,
        message_id: str,
        max_hops: int,
        parent_message_id: str | None = None,
    ) -> list[dict[str, Any]]:
        ancestors: list[dict[str, Any]] = []
        session_data = self._store.get(session_id, {})

        # Start from explicit parent_message_id if provided (for messages
        # not yet stored), otherwise look up current message's parent.
        if parent_message_id is not None:
            current_id = parent_message_id
            start_hop = 1
        else:
            current_result = session_data.get(message_id)
            if current_result is None:
                return []
            parent = current_result.get("_parent_message_id")
            if not isinstance(parent, str):
                return []
            current_id = parent
            start_hop = 1

        for hop in range(start_hop, max_hops + 1):
            ancestor_result = session_data.get(current_id)
            if ancestor_result is None:
                break

            ancestor_entry = dict(ancestor_result)
            ancestor_entry["_hops"] = hop
            ancestors.append(ancestor_entry)

            # Follow the chain
            next_parent = ancestor_result.get("_parent_message_id")
            if next_parent is None:
                break
            current_id = next_parent

        return ancestors

    def get_session_results(self, session_id: str) -> list[dict[str, Any]]:
        session_data = self._store.get(session_id, {})
        order = self._order.get(session_id, [])
        return [session_data[mid] for mid in order if mid in session_data]

    def clear(self, session_id: str | None = None) -> None:
        if session_id is not None:
            self._store.pop(session_id, None)
            self._order.pop(session_id, None)
        else:
            self._store.clear()
            self._order.clear()
