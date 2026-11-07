import json
from pathlib import Path
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.catalog.importer import import_feed


class Command(BaseCommand):
    help = "Полный импорт выбранного ЖК Domoplaner (атомарно)"

    def add_arguments(self, parser):
        parser.add_argument("--file", type=Path, help="Сохранённый полный фид")
        parser.add_argument("--observed-at", help="Время получения снимка ISO 8601 с часовым поясом")
        parser.add_argument("--allow-empty", action="store_true", help="Подтвердить пустой полный каталог")

    def handle(self, *args, **options):
        try:
            if options["file"]:
                observed = parse_datetime(options["observed_at"] or "")
                if observed is None:
                    raise ValueError("Snapshot observation time required")
                data = json.loads(options["file"].read_text(encoding="utf-8-sig"))
            else:
                if options["observed_at"] or not settings.DOMOPLANER_FEED_URL:
                    raise ValueError("Feed URL required; observed-at only applies to file")
                with urlopen(settings.DOMOPLANER_FEED_URL, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8-sig"))
                observed = timezone.now()
            import_feed(data, observed_at=observed, allow_empty=options["allow_empty"])
        except Exception as error:
            # Network and validation errors can contain private URLs and source payloads.
            raise CommandError(
                f"Импорт отменён ({type(error).__name__}); проверьте конфигурацию и структуру фида. "
                "Для --file обязательно --observed-at с часовым поясом. Подробности доступа скрыты."
            ) from None
        self.stdout.write(self.style.SUCCESS("Полный импорт выбранного ЖК завершён."))
