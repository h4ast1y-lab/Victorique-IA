import asyncio
import hashlib
import json
import uuid
from enum import Enum
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timezone

from app.config import settings
from app.memory.database import get_connection


class ActionCategory(str, Enum):
    FREE = "free"
    REQUIRES_AUTH = "requires_auth"
    EXTERNAL = "external"


def _payload_hash(payload: Dict[str, Any]) -> str:
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


class SecurityManager:
    def __init__(self):
        # In-memory store for pending authorizations requested by the model.
        # Authorizations are single-use, expire quickly and are bound to the
        # exact tool + parameters that were shown to the user.
        self.pending_actions: Dict[str, Dict[str, Any]] = {}
        # Futures awaited by Claude Code permission callbacks, keyed by
        # action_id, with the event loop that owns each one.
        self._waiters: Dict[str, Tuple[asyncio.AbstractEventLoop, asyncio.Future]] = {}

    def _complete_waiter(self, action_id: str, approved: bool) -> None:
        """Wakes the Claude Code callback waiting on this action, if any.
        Safe to call from any thread or event loop."""
        entry = self._waiters.pop(action_id, None)
        if not entry:
            return
        loop, future = entry

        def _set():
            if not future.done():
                future.set_result(approved)

        try:
            loop.call_soon_threadsafe(_set)
        except RuntimeError:  # loop already closed
            pass

    def log_action(
        self,
        action_type: str,
        category: ActionCategory,
        resource: str,
        authorized: bool,
        details: str = ""
    ):
        """Persists every relevant security decision to the audit log."""
        try:
            with get_connection() as conn:
                conn.execute(
                    """
                    INSERT INTO audit_logs (action_type, category, resource, authorized, details)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (action_type, category.value, resource, 1 if authorized else 0, details)
                )
        except Exception as e:
            print(f"Failed to log audit event: {e}")

    def _purge_expired(self):
        now = datetime.now(timezone.utc).timestamp()
        expired = [aid for aid, a in self.pending_actions.items() if a["expires_at"] < now]
        for aid in expired:
            action = self.pending_actions.pop(aid, None)
            self._complete_waiter(aid, False)
            if action:
                self.log_action(
                    action_type=action["action_type"],
                    category=ActionCategory(action["category"]),
                    resource=action["resource"],
                    authorized=False,
                    details="Authorization expired before user decision",
                )
        # Hard cap: never let the in-memory queue grow indefinitely.
        if len(self.pending_actions) > 50:
            for aid in list(self.pending_actions.keys())[: len(self.pending_actions) - 50]:
                self.pending_actions.pop(aid, None)
                self._complete_waiter(aid, False)

    def create_authorization_request(
        self,
        action_type: str,
        category: ActionCategory,
        resource: str,
        description: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> str:
        """
        Registers an action that requires user consent.
        Returns a unique action_id, valid only for the configured TTL.
        """
        self._purge_expired()
        action_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc).timestamp()
        ttl = max(30, int(settings.authorization_ttl_seconds))
        self.pending_actions[action_id] = {
            "id": action_id,
            "action_type": action_type,
            "category": category.value,
            "resource": resource,
            "description": description,
            "payload": dict(payload or {}),
            # Internal context (e.g. conversation_id) is never exposed to the
            # client and is not part of the approval hash.
            "context": dict(context or {}),
            "payload_hash": _payload_hash(payload or {}),
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "expires_at": now + ttl,
            "expires_at_iso": datetime.fromtimestamp(now + ttl).isoformat(timespec="seconds"),
        }
        self.log_action(
            action_type=action_type,
            category=category,
            resource=resource,
            authorized=False,
            details=f"Authorization requested (valid for {ttl}s; not executed)",
        )
        return action_id

    def create_waiting_request(
        self,
        action_type: str,
        resource: str,
        description: str,
        payload: Dict[str, Any],
        context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[str, asyncio.Future]:
        """
        Pending authorization for a Claude Code tool call. Instead of running
        a registry tool on approval, it completes the returned future with
        True (approved) or False (rejected, expired or cancelled).
        Must be called from a running event loop.
        """
        loop = asyncio.get_running_loop()
        action_id = self.create_authorization_request(
            action_type=action_type,
            category=ActionCategory.REQUIRES_AUTH,
            resource=resource,
            description=description,
            payload=payload,
            context=context,
        )
        self.pending_actions[action_id]["kind"] = "claude_code"
        future = loop.create_future()
        self._waiters[action_id] = (loop, future)
        return action_id, future

    def cancel_action(self, action_id: str, reason: str) -> None:
        """Drops a pending action without user decision (timeout, stop)."""
        action = self.pending_actions.pop(action_id, None)
        self._complete_waiter(action_id, False)
        if action:
            self.log_action(
                action_type=action["action_type"],
                category=ActionCategory(action["category"]),
                resource=action["resource"],
                authorized=False,
                details=reason,
            )

    def get_pending_action(self, action_id: str) -> Optional[Dict[str, Any]]:
        self._purge_expired()
        return self.pending_actions.get(action_id)

    def list_pending_actions(self) -> list:
        self._purge_expired()
        public_fields = (
            "id", "action_type", "category", "resource", "description",
            "payload", "timestamp", "expires_at", "expires_at_iso", "kind",
        )
        return [
            {k: a.get(k) for k in public_fields}
            for a in self.pending_actions.values()
        ]

    def resolve_action_detailed(
        self, action_id: str, approved: bool
    ) -> Tuple[str, Optional[Dict[str, Any]]]:
        """
        Single-use resolution. Returns (status, action) where status is one of:
        approved, rejected, not_found, expired, tampered.
        """
        self._purge_expired()
        action = self.pending_actions.pop(action_id, None)
        if not action:
            self._complete_waiter(action_id, False)
            return "not_found", None

        now = datetime.now(timezone.utc).timestamp()
        if action["expires_at"] < now:
            self.log_action(
                action_type=action["action_type"],
                category=ActionCategory(action["category"]),
                resource=action["resource"],
                authorized=False,
                details="Authorization expired",
            )
            self._complete_waiter(action_id, False)
            return "expired", None

        if not approved:
            self.log_action(
                action_type=action["action_type"],
                category=ActionCategory(action["category"]),
                resource=action["resource"],
                authorized=False,
                details="User rejected the action",
            )
            self._complete_waiter(action_id, False)
            return "rejected", None

        if _payload_hash(action["payload"]) != action["payload_hash"]:
            self.log_action(
                action_type=action["action_type"],
                category=ActionCategory(action["category"]),
                resource=action["resource"],
                authorized=False,
                details="Payload mismatch; action blocked",
            )
            self._complete_waiter(action_id, False)
            return "tampered", None

        self.log_action(
            action_type=action["action_type"],
            category=ActionCategory(action["category"]),
            resource=action["resource"],
            authorized=True,
            details="User approved the action (single use)",
        )
        self._complete_waiter(action_id, True)
        return "approved", action

    def resolve_action(self, action_id: str, approved: bool) -> Optional[Dict[str, Any]]:
        status, action = self.resolve_action_detailed(action_id, approved)
        return action if status == "approved" else None


security_manager = SecurityManager()
