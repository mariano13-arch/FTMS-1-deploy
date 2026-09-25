import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


def build_password_reset_url(user):
    parts = urlsplit(settings.STAFF_PASSWORD_RESET_URL)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        raise ValueError("STAFF_PASSWORD_RESET_URL must be an absolute HTTP(S) URL.")
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


def send_password_reset_email(user):
    try:
        if not settings.STAFF_PASSWORD_RESET_URL:
            return False
        body = "\n".join([
            "A password reset was requested for your FTMS staff account.", "",
            "Choose a new password using this expiring link:", build_password_reset_url(user), "",
            "If you did not request this, you can ignore this email.",
        ])
        return bool(
            send_mail(
                "Reset your FTMS password",
                body,
                None,
                [user.email],
                fail_silently=False,
            )
        )
    except Exception as error:
        logger.error(
            "Password reset email delivery failed for user_id=%s error_type=%s",
            user.pk,
            type(error).__name__,
        )
        return False
