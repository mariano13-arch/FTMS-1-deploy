from rest_framework.authentication import SessionAuthentication


class StaffSessionAuthentication(SessionAuthentication):
    def authenticate_header(self, request):
        return "Session"
