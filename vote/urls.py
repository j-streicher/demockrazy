from django.urls import include, path, register_converter

from . import views


class PollIdentifierConverter:
    """Poll identifiers, exactly as narrow as the former ``[a-zA-Z0-9]+``.

    Django's built-in ``slug`` would not be a replacement: it also allows ``-``
    and ``_`` and would therefore accept identifiers that do not exist --
    ``mk_identifier()`` only draws from ``string.ascii_letters + string.digits``.
    """

    regex = "[a-zA-Z0-9]+"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


register_converter(PollIdentifierConverter, "identifier")

app_name = "vote"

pollpatterns = (
    [
        path("", views.poll, name="poll"),
        path("vote", views.vote, name="vote"),
        path("success", views.success, name="success"),
        path("manage", views.manage, name="manage"),
        path("results", views.results, name="result"),
    ],
    "polls",
)

urlpatterns = [
    path("", views.index, name="index"),
    path("create", views.create, name="create"),
    path("<identifier:poll_identifier>/", include(pollpatterns)),
]
