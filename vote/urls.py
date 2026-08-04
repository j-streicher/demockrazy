from django.urls import include, path, register_converter

from . import views


class PollIdentifierConverter:
    """Umfragekennungen, genau so eng wie das frühere ``[a-zA-Z0-9]+``.

    Djangos eingebautes ``slug`` wäre kein Ersatz: es lässt zusätzlich ``-`` und
    ``_`` zu und würde damit Kennungen annehmen, die es nicht gibt --
    ``mk_identifier()`` zieht nur aus ``string.ascii_letters + string.digits``.
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
