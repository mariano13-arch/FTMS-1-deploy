from django.core.management.base import BaseCommand, CommandError

from transport_requests.models import IntegrationClient
from transport_requests.source_integration import (
    TRUSTED_SOURCE_SYSTEMS,
    create_integration_client,
    rotate_integration_credential,
)


class Command(BaseCommand):
    help = "Create, rotate, activate, or deactivate an HMS/RMS integration client."

    def add_arguments(self, parser):
        parser.add_argument("name")
        parser.add_argument("--source-system", choices=sorted(TRUSTED_SOURCE_SYSTEMS))
        actions = parser.add_mutually_exclusive_group()
        actions.add_argument("--rotate", action="store_true")
        actions.add_argument("--activate", action="store_true")
        actions.add_argument("--deactivate", action="store_true")

    def handle(self, *args, **options):
        name = options["name"].strip()
        if not name:
            raise CommandError("Client name must not be blank.")
        client = IntegrationClient.objects.filter(name=name).first()

        if options["rotate"]:
            if client is None:
                raise CommandError("Integration client does not exist.")
            client, credential = rotate_integration_credential(client)
            self.stdout.write(f"Credential (shown once): {credential}")
            self.stdout.write(self.style.SUCCESS(f"Rotated integration client {client.name}."))
            return

        if options["activate"] or options["deactivate"]:
            if client is None:
                raise CommandError("Integration client does not exist.")
            client.is_active = options["activate"]
            client.save(update_fields=["is_active", "updated_at"])
            state = "Activated" if client.is_active else "Deactivated"
            self.stdout.write(self.style.SUCCESS(f"{state} integration client {client.name}."))
            return

        if client is not None:
            raise CommandError("Integration client already exists; use --rotate if required.")
        source_system = options["source_system"]
        if source_system is None:
            raise CommandError("--source-system is required when creating a client.")
        client, credential = create_integration_client(
            name=name,
            source_system=source_system,
        )
        self.stdout.write(f"Credential (shown once): {credential}")
        self.stdout.write(self.style.SUCCESS(f"Created integration client {client.name}."))
