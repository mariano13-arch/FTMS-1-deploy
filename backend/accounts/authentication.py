from rest_framework.authentication import SessionAuthentication

from .roles import resolve_role
from .session_security import enforce_authenticated_session


class StaffSessionAuthentication(SessionAuthentication):
    def authenticate(self, request):
        authenticated = super().authenticate(request)
        if authenticated is not None and resolve_role(authenticated[0]) is not None:
            enforce_authenticated_session(request._request, authenticated[0])
        return authenticated

    def authenticate_header(self, request):
        return "Session"
