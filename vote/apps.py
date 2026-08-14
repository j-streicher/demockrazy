from django.apps import AppConfig


class VoteConfig(AppConfig):
    name = "vote"

    def ready(self):
        # `demockrazy.checks` registers its checks on import. The import has to happen somewhere
        # after the settings are loaded -- and `vote` is the only app of our own, there is no
        # project AppConfig. So here, even though the check is about the database configuration and
        # not about the voting logic.
        from demockrazy import checks  # noqa: F401
