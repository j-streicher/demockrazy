from django.apps import AppConfig


class VoteConfig(AppConfig):
    name = "vote"

    def ready(self):
        # `demockrazy.checks` registriert seine Checks beim Import. Der Import muss irgendwo
        # passieren, nachdem die Settings geladen sind -- und `vote` ist die einzige eigene App,
        # es gibt kein Projekt-AppConfig. Deshalb hier, obwohl der Check die Datenbank-
        # konfiguration betrifft und nicht die Abstimmungslogik.
        from demockrazy import checks  # noqa: F401
