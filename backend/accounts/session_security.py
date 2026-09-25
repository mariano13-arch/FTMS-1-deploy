from django.conf import settings
from django.contrib.auth import get_user_model, login, logout
from django.contrib.sessions.models import Session
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import AuthenticationFailed

from .models import ActiveUserSession

AUTHENTICATED_AT = "ftms_authenticated_at"
LAST_ACTIVITY_AT = "ftms_last_activity_at"

IDLE_EXPIRED = "Your session expired due to inactivity. Please sign in again."
ABSOLUTE_EXPIRED = "Your session expired. Please sign in again."
SESSION_REPLACED = (
    "Your account was signed in from another browser or device. Please sign in again."
)


def _now_timestamp():
    return timezone.now().timestamp()


def _register_session(user, session_key):
    old_session_key = None
    with transaction.atomic():
        get_user_model().objects.select_for_update().get(pk=user.pk)
        registration, created = ActiveUserSession.objects.get_or_create(
            user=user, defaults={"session_key": session_key}
        )
        if not created and registration.session_key != session_key:
            old_session_key = registration.session_key
            registration.session_key = session_key
            registration.save(update_fields=["session_key", "updated_at"])
    if old_session_key:
        Session.objects.filter(session_key=old_session_key).delete()
    return old_session_key is not None


def establish_authenticated_session(request, user):
    login(request, user)
    now = _now_timestamp()
    request.session[AUTHENTICATED_AT] = now
    request.session[LAST_ACTIVITY_AT] = now
    request.session.set_expiry(0)
    request.session.save()
    return _register_session(user, request.session.session_key)


def _unregister_if_current(user, session_key):
    if session_key:
        ActiveUserSession.objects.filter(
            user=user, session_key=session_key
        ).delete()


def end_authenticated_session(request, user):
    session_key = request.session.session_key
    _unregister_if_current(user, session_key)
    logout(request)


def invalidate_authenticated_sessions(user):
    registration = ActiveUserSession.objects.filter(user=user).only("session_key").first()
    if registration:
        Session.objects.filter(session_key=registration.session_key).delete()
        registration.delete()
        return True
    return False


def _expire(request, user, message):
    session_key = request.session.session_key
    _unregister_if_current(user, session_key)
    request.session.flush()
    raise AuthenticationFailed(message)


def enforce_authenticated_session(request, user):
    session_key = request.session.session_key
    authenticated_at = request.session.get(AUTHENTICATED_AT)
    last_activity_at = request.session.get(LAST_ACTIVITY_AT)

    # Adopt authenticated sessions created before this control was deployed.
    if authenticated_at is None or last_activity_at is None:
        now = _now_timestamp()
        request.session[AUTHENTICATED_AT] = now
        request.session[LAST_ACTIVITY_AT] = now
        request.session.set_expiry(0)
        request.session.save()
        session_key = request.session.session_key
        _register_session(user, session_key)
        return

    registration = ActiveUserSession.objects.filter(user=user).only("session_key").first()
    if registration is None or registration.session_key != session_key:
        _expire(request, user, SESSION_REPLACED)

    now = _now_timestamp()
    if now - float(last_activity_at) >= settings.FTMS_SESSION_IDLE_TIMEOUT_SECONDS:
        _expire(request, user, IDLE_EXPIRED)
    if now - float(authenticated_at) >= settings.FTMS_SESSION_ABSOLUTE_TIMEOUT_SECONDS:
        _expire(request, user, ABSOLUTE_EXPIRED)


def record_meaningful_activity(request):
    request.session[LAST_ACTIVITY_AT] = _now_timestamp()
