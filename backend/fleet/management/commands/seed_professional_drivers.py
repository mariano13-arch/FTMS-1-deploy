from datetime import date

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from fleet.models import Driver
from fleet.serializers import driver_eligibility

GIVEN_NAMES = (
    "Adrian", "Alberto", "Andres", "Angelo", "Antonio", "Benjamin", "Carlos",
    "Christian", "Daniel", "Eduardo", "Emmanuel", "Enrique", "Francis", "Gabriel",
    "Gerardo", "Hector", "Ignacio", "Jerome", "Joaquin", "Leonardo", "Manuel",
    "Marcelo", "Nathaniel", "Nicolas", "Orlando", "Patricio", "Ramon", "Renato",
    "Ricardo", "Victor",
)
MIDDLE_NAMES = ("Aquino", "Bautista", "Castillo", "Domingo", "Evangelista")
# One intentionally distinct synthetic surname per managed code. Keep this ordered:
# the position is part of the deterministic seed contract.
SURNAMES = (
    "Abad", "Abalos", "Abaya", "Agbayani", "Aguilar", "Alcantara", "Alonzo", "Andrada",
    "Aquino", "Araneta", "Austria", "Bacani", "Balingit", "Baltazar", "Bautista",
    "Belmonte", "Bernardo", "Bonifacio", "Borja", "Briones", "Buenaventura", "Cabrera",
    "Calderon", "Camacho", "Canlas", "Carandang", "Castillo", "Castro", "Catapang",
    "Cayetano", "Concepcion", "Corpus", "Cruz", "Cuevas", "Dalisay", "David", "De Castro",
    "De Guzman", "De Leon", "De Vera", "Del Mundo", "Del Rosario", "Dimaano", "Domingo",
    "Dumlao", "Enriquez", "Escobar", "Espiritu", "Estrella", "Evangelista", "Fabian",
    "Fajardo", "Fernandez", "Flores", "Francisco", "Galang", "Garcia", "Gatchalian",
    "Gonzales", "Gregorio", "Guerrero", "Guevarra", "Gutierrez", "Hilario", "Ignacio",
    "Ilagan", "Jacinto", "Javier", "Labrador", "Lacson", "Lagdameo", "Lansangan",
    "Legaspi", "Lim", "Lorenzo", "Lozada", "Lucero", "Macapagal", "Macaraeg", "Magbanua",
    "Manalo", "Mangubat", "Manrique", "Marcelo", "Marquez", "Matias", "Medina", "Mercado",
    "Miranda", "Monserrat", "Montemayor", "Morales", "Natividad", "Navarro", "Nepomuceno",
    "Nolasco", "Ocampo", "Ong", "Ortega", "Pacheco", "Padilla", "Panganiban", "Pascual",
    "Peñaflor", "Peralta", "Perez", "Pineda", "Puno", "Quijano", "Quintos", "Ramos",
    "Reyes", "Rivera", "Robles", "Roque", "Rosales", "Salazar", "Salonga", "Samson",
    "San Andres", "San Juan", "Sandoval", "Santiago", "Santos", "Sarmiento", "Sebastian",
    "Serrano", "Soriano", "Suarez", "Sumulong", "Tan", "Teodoro", "Tolentino", "Torres",
    "Trinidad", "Tuazon", "Valdez", "Valencia", "Valenzuela", "Vargas", "Velasco",
    "Ventura", "Vergara", "Villanueva", "Villareal", "Yabut", "Yap", "Zamora", "Zarate",
    "Zubiri",
)
PROFILE_COUNT = 150
CODE_PREFIX = "DRV-PH-"
MOBILE_ACCESS_DRIVER_CODE = "DEV-MOBILE-TEST-111"


def professional_profiles():
    profiles = []
    for number, surname in enumerate(SURNAMES, start=1):
        given_name = GIVEN_NAMES[(number - 1) % len(GIVEN_NAMES)]
        middle_name = MIDDLE_NAMES[(number - 1) % len(MIDDLE_NAMES)]
        email_name = f"{given_name}.{middle_name}.{surname}".lower().replace(" ", "")
        profiles.append(
            {
                    "driver_code": f"{CODE_PREFIX}{number:04d}",
                    "external_hr_id": f"FTMS-PH-{number:04d}",
                    "first_name": given_name,
                    "middle_name": middle_name,
                    "last_name": surname,
                    "contact_number": f"+63 000 000 {number:04d}",
                    "email": f"{email_name}@example.com",
                    "employment_status": Driver.EmploymentStatus.ACTIVE,
                    "date_hired": date(2020 + number % 5, number % 12 + 1, number % 27 + 1),
                    "license_number": f"NCR-P-{number:08d}",
                    "license_category": "Professional",
                    "license_codes": ("A, A1, B, B1" if number % 3 else "A, A1, B, B1, B2"),
                    "license_issue_date": date(2024, number % 12 + 1, number % 27 + 1),
                    "license_expiry_date": date(
                        2030 + number % 2, number % 12 + 1, number % 27 + 1
                    ),
                    "medical_certificate_expiry_date": date(2028, number % 12 + 1, number % 27 + 1),
                    "work_shift": (
                        Driver.WorkShift.DAY if number <= 75 else Driver.WorkShift.NIGHT
                    ),
                    "weekly_rest_days": _rest_days(number - 1),
            }
        )
    return profiles


def _rest_days(index):
    weekdays = ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY")
    first = index % len(weekdays)
    # Rotate four non-adjacent offsets to provide 28 combinations while keeping
    # the 302 slots across the managed population at 43–44 per weekday.
    second = (first + 2 + (index // len(weekdays)) % 4) % len(weekdays)
    return [weekdays[first], weekdays[second]]


def has_operational_references(driver):
    return any(
        (
            driver.linked_user_id is not None,
            driver.documents.exists(),
            driver.dispatch_assignments.exists(),
            driver.previous_dispatch_events.exists(),
            driver.new_dispatch_events.exists(),
            driver.dispatch_plans.exists(),
        )
    )


def find_preserved_aljohn():
    candidates = list(
        Driver.objects.filter(
            first_name__iexact="ALJOHN",
            middle_name__iexact="ANDAMON",
            last_name__iexact="MARIANO",
        ).select_related("linked_user")
    )
    non_development = [
        driver
        for driver in candidates
        if not any(
            marker in driver.driver_code.upper()
            for marker in ("DEMO", "DEV", "TEST", "SAMPLE", "DUMMY")
        )
    ]
    if len(non_development) == 1:
        return non_development[0]
    if len(candidates) == 1:
        return candidates[0]
    details = ", ".join(f"pk={item.pk} code={item.driver_code}" for item in candidates)
    raise CommandError(
        "Unable to identify one preserved ALJOHN ANDAMON MARIANO row safely. "
        f"Candidates: {details or 'none'}."
    )


def find_mobile_access_driver():
    candidates = list(
        Driver.objects.filter(driver_code__iexact=MOBILE_ACCESS_DRIVER_CODE).select_related(
            "linked_user"
        )
    )
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]
    details = ", ".join(f"pk={item.pk} code={item.driver_code}" for item in candidates)
    raise CommandError(
        "Unable to identify the protected mobile-access driver safely. "
        f"Candidates: {details}."
    )


class Command(BaseCommand):
    help = "Reconcile 150 deterministic professional synthetic Filipino driver profiles."

    def add_arguments(self, parser):
        parser.add_argument("--replace-development-drivers", action="store_true")
        parser.add_argument("--dry-run", action="store_true")

    @transaction.atomic
    def handle(self, *args, **options):
        profiles = professional_profiles()
        if len(profiles) != PROFILE_COUNT:
            raise CommandError("Professional driver profile definition is incomplete.")
        preserved = find_preserved_aljohn()
        preserved.work_shift = Driver.WorkShift.DAY
        preserved.weekly_rest_days = _rest_days(PROFILE_COUNT)
        mobile_driver = find_mobile_access_driver()
        if mobile_driver is not None and mobile_driver.pk == preserved.pk:
            raise CommandError(
                "The preserved 123-GFD and DEV-MOBILE-TEST-111 drivers must be separate rows."
            )
        if mobile_driver is not None:
            mobile_driver.employment_status = Driver.EmploymentStatus.ACTIVE
            mobile_driver.work_shift = Driver.WorkShift.DAY
            mobile_driver.weekly_rest_days = _rest_days(PROFILE_COUNT + 1)
        managed_codes = {profile["driver_code"] for profile in profiles}
        protected_ids = {preserved.pk}
        if mobile_driver is not None:
            protected_ids.add(mobile_driver.pk)
        legacy = list(
            Driver.objects.exclude(pk__in=protected_ids).exclude(driver_code__in=managed_codes)
        )
        retained = [driver for driver in legacy if has_operational_references(driver)]
        deletable = [driver for driver in legacy if driver not in retained]

        self.stdout.write(f"Current driver count: {Driver.objects.count()}")
        self.stdout.write(
            "Preserved ALJOHN row: "
            f"pk={preserved.pk}, code={preserved.driver_code}, "
            f"linked_user={preserved.linked_user_id}"
        )
        if mobile_driver is not None:
            self.stdout.write(
                "Protected mobile-access driver: "
                f"pk={mobile_driver.pk}, code={mobile_driver.driver_code}, "
                f"linked_user={mobile_driver.linked_user_id}"
            )
        eligibility, reasons = driver_eligibility(preserved)
        self.stdout.write(
            f"Preserved ALJOHN eligibility: {eligibility}"
            + (f" — {'; '.join(reasons)}" if reasons else "")
        )
        self.stdout.write(f"Old development drivers found: {len(legacy)}")
        self.stdout.write(
            "Would delete unreferenced: "
            + (", ".join(driver.driver_code for driver in deletable) or "none")
        )
        self.stdout.write(
            "Would deactivate referenced: "
            + (", ".join(driver.driver_code for driver in retained) or "none")
        )
        self.stdout.write(f"Professional drivers to reconcile: {len(profiles)}")
        self.stdout.write("Operational history to create: none")

        if options["dry_run"]:
            transaction.set_rollback(True)
            self.stdout.write(self.style.WARNING("Dry run only; no changes applied."))
            return

        preserved.save(update_fields=["work_shift", "weekly_rest_days", "updated_at"])
        if mobile_driver is not None:
            mobile_driver.save(
                update_fields=[
                    "employment_status", "work_shift", "weekly_rest_days", "updated_at"
                ]
            )

        if options["replace_development_drivers"]:
            for driver in retained:
                if driver.employment_status != Driver.EmploymentStatus.TERMINATED:
                    driver.employment_status = Driver.EmploymentStatus.TERMINATED
                    driver.save(update_fields=["employment_status", "updated_at"])
            for driver in deletable:
                driver.delete()

        created = updated = 0
        for profile in profiles:
            code = profile["driver_code"]
            defaults = {key: value for key, value in profile.items() if key != "driver_code"}
            _, was_created = Driver.objects.update_or_create(
                driver_code=code,
                defaults=defaults,
            )
            created += int(was_created)
            updated += int(not was_created)

        self.stdout.write(
            self.style.SUCCESS(
                f"Professional drivers reconciled: {created} created, {updated} updated."
            )
        )
        self.stdout.write(
            f"Active/current drivers: "
            f"{Driver.objects.filter(employment_status=Driver.EmploymentStatus.ACTIVE).count()}"
        )
        self.stdout.write(f"Total driver rows: {Driver.objects.count()}")
