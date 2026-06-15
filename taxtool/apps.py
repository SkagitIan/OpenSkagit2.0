import json
from django.apps import AppConfig


class TaxtoolConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "taxtool"
    agencies: dict = {}

    def ready(self):
        from django.conf import settings
        path = settings.BASE_DIR / "data" / "skagit_agencies.json"
        if path.exists():
            TaxtoolConfig.agencies = json.loads(path.read_text())
