import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)

INVITATION_SENT = "SENT"
INVITATION_NOT_SENT = "NOT_SENT_ERROR"


def build_staff_setup_url(user):
    parts = urlsplit(settings.STAFF_ACCOUNT_SETUP_URL)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("STAFF_ACCOUNT_SETUP_URL must be an absolute HTTP(S) URL.")
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    return urlunsplit(
        (parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment)
    )


def send_staff_setup_email(user):
    try:
        if not user.email or not settings.STAFF_ACCOUNT_SETUP_URL:
            return INVITATION_NOT_SENT
        if settings.EMAIL_BACKEND == "django.core.mail.backends.console.EmailBackend":
            return INVITATION_NOT_SENT
        display_name = user.get_full_name().strip() or user.username
        body = "\n".join(
            [
                f"Hello {display_name},",
                "",
                "An FTMS staff account has been created for you.",
                f"Username: {user.username}",
                "",
                "Choose your own password using this temporary setup link:",
                build_staff_setup_url(user),
                "",
                "If you did not expect this account, contact your FTMS administrator.",
            ]
        )
        delivered = send_mail(
            "Set up your FTMS staff account",
            body,
            None,
            [user.email],
            fail_silently=False,
        )
    except Exception as error:
        logger.error(
            "Staff setup email delivery failed for user_id=%s error_type=%s",
            user.pk,
            type(error).__name__,
        )
        return INVITATION_NOT_SENT
    return INVITATION_SENT if delivered else INVITATION_NOT_SENT
