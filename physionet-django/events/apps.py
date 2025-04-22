from django.apps import AppConfig
from physionet.settings.base import ENABLE_CLOUD_RESEARCH_ENVIRONMENTS


class EventsConfig(AppConfig):
    name = 'events'

    def ready(self):
        if ENABLE_CLOUD_RESEARCH_ENVIRONMENTS:
            import environment.signals
