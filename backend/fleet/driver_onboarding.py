import logging
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_encode

logger = logging.getLogger(__name__)


class DriverUsernameConflict(Exception):
    pass


def create_driver_with_account(serializer):
    user_model = get_user_model()
    driver_code = serializer.validated_data["driver_code"].strip().upper()
    if user_model.objects.filter(username__iexact=driver_code).exists():
        raise DriverUsernameConflict

    try:
        with transaction.atomic():
            driver = serializer.save(linked_user=None)
            user = user_model(
                username=driver.driver_code,
                first_name=driver.first_name,
                last_name=driver.last_name,
                email=driver.email,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            user.set_unusable_password()
            user.save()
            driver.linked_user = user
            driver.save(update_fields=["linked_user", "updated_at"])
    except IntegrityError as error:
        if user_model.objects.filter(username__iexact=driver_code).exists():
            raise DriverUsernameConflict from error
        raise

    return driver


def _setup_url(user):
    base_url = settings.DRIVER_MOBILE_ACCOUNT_SETUP_URL
    parts = urlsplit(base_url)
    query = dict(parse_qsl(parts.query, keep_blank_values=True))
    query.update(
        {
            "uid": urlsafe_base64_encode(force_bytes(user.pk)),
            "token": default_token_generator.make_token(user),
        }
    )
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query), parts.fragment))


def send_driver_setup_email(driver):
    if not driver.email:
        return "NOT_SENT_MISSING_EMAIL"

    try:
        if not settings.DRIVER_MOBILE_ACCOUNT_SETUP_URL:
            return "NOT_SENT_ERROR"
        display_name = " ".join(
            part
            for part in (driver.first_name, driver.middle_name, driver.last_name)
            if part
        )
        lines = [
            f"Hello {display_name},",
            "",
            "An FTMS Driver Mobile account has been created for you.",
            f"Username: {driver.driver_code}",
            "",
            "Choose your password using this temporary, single-use setup link:",
            _setup_url(driver.linked_user),
        ]
        if settings.DRIVER_MOBILE_APP_DOWNLOAD_URL:
            lines.extend(
                [
                    "",
                    "Driver Mobile installation link:",
                    settings.DRIVER_MOBILE_APP_DOWNLOAD_URL,
                ]
            )
        lines.extend(
            [
                "",
                "If you did not expect this account, contact your FTMS administrator.",
            ]
        )
        delivered = send_mail(
            "Set up your FTMS Driver Mobile account",
            "\n".join(lines),
            None,
            [driver.email],
            fail_silently=False,
        )
    except Exception as error:
        logger.error(
            "Driver setup email delivery failed for driver_id=%s error_type=%s",
            driver.pk,
            type(error).__name__,
        )
        return "NOT_SENT_ERROR"
    return "SENT" if delivered else "NOT_SENT_ERROR"
