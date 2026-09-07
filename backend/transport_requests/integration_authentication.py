from functools import lru_cache

from django.contrib.auth.hashers import check_password, make_password
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.permissions import BasePermission

from .models import IntegrationClient
from .source_integration import credential_matches


@lru_cache(maxsize=1)
def dummy_credential_hash():
    return make_password("invalid-integration-credential")


class IntegrationBearerAuthentication(BaseAuthentication):
    keyword = b"bearer"

    def authenticate(self, request):
        parts = get_authorization_header(request).split()
        if not parts:
            return None
        if parts[0].lower() != self.keyword or len(parts) != 2:
            raise AuthenticationFailed("Invalid integration authorization header.")
        try:
            credential = parts[1].decode("ascii")
        except UnicodeDecodeError as error:
            raise AuthenticationFailed("Invalid integration credential.") from error
        key_identifier, separator, _ = credential.partition(".")
        client = (
            IntegrationClient.objects.select_related("user")
            .filter(key_identifier=key_identifier)
            .first()
        )
        matches = credential_matches(client, credential) if client is not None else False
        if client is None:
            # Run the configured password hasher for unknown identifiers as well.
            check_password(credential, dummy_credential_hash())
        if (
            not separator
            or client is None
            or not matches
            or not client.is_active
            or not client.user.is_active
        ):
            raise AuthenticationFailed("Invalid integration credential.")
        return client.user, client

    def authenticate_header(self, request):
        return "Bearer"


class IntegrationClientAccess(BasePermission):
    def has_permission(self, request, view):
        return isinstance(request.auth, IntegrationClient) and request.auth.is_active
