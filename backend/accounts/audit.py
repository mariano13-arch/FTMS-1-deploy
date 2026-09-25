from __future__ import annotations

from collections.abc import Mapping

from django.contrib.auth import get_user_model

from .models import AuditEvent

SENSITIVE_FRAGMENTS = (
    "password",
    "token",
    "secret",
    "recovery_code",
    "recovery-code",
    "session",
    "csrf",
    "authorization",
    "credential",
    "smtp",
    "tomtom",
    "database",
    "uploaded",
    "file",
)


def _safe_json(value):
    if isinstance(value, Mapping):
        return {
            str(key): _safe_json(item)
            for key, item in value.items()
            if not any(fragment in str(key).lower() for fragment in SENSITIVE_FRAGMENTS)
        }
    if isinstance(value, (list, tuple)):
        return [_safe_json(item) for item in value[:50]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        if isinstance(value, str):
            return value[:500]
        return value
    return str(value)[:500]


def _client_ip(request):
    if request is None:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidate = forwarded.split(",", 1)[0].strip() if forwarded else request.META.get("REMOTE_ADDR")
    return candidate or None


def _user_agent(request):
    if request is None:
        return ""
    return request.META.get("HTTP_USER_AGENT", "")[:240]


def _target_parts(target):
    if target is None:
        return "", "", ""
    target_type = type(target).__name__
    target_id = getattr(target, "pk", "") or getattr(target, "id", "")
    label = ""
    username = getattr(target, "username", "")
    if username:
        label = username
    elif hasattr(target, "get_full_name"):
        label = target.get_full_name().strip()
    return target_type, str(target_id or ""), str(label or target)[:180]


def record_audit_event(
    *,
    action,
    actor=None,
    actor_type=None,
    target=None,
    target_type="",
    target_id="",
    target_label="",
    outcome=AuditEvent.Outcome.SUCCESS,
    source=AuditEvent.Source.WEB,
    request=None,
    changes=None,
    metadata=None,
):
    if actor_type is None:
        actor_type = (
            AuditEvent.ActorType.STAFF if actor is not None else AuditEvent.ActorType.UNKNOWN
        )
    if target is not None:
        inferred_type, inferred_id, inferred_label = _target_parts(target)
        target_type = target_type or inferred_type
        target_id = target_id or inferred_id
        target_label = target_label or inferred_label
    if actor is not None and not isinstance(actor, get_user_model()):
        actor = None
        actor_type = AuditEvent.ActorType.UNKNOWN
    return AuditEvent.objects.create(
        actor=actor,
        actor_type=actor_type,
        action=action,
        target_type=target_type[:80],
        target_id=str(target_id)[:80],
        target_label=str(target_label)[:180],
        outcome=outcome,
        source=source,
        ip_address=_client_ip(request),
        user_agent=_user_agent(request),
        changes=_safe_json(changes or {}),
        metadata=_safe_json(metadata or {}),
    )


def permission_diff(before, after):
    before_set = {f"{module}.{action}" for module, action in before}
    after_set = {f"{module}.{action}" for module, action in after}
    return {
        "added": sorted(after_set - before_set),
        "removed": sorted(before_set - after_set),
    }
