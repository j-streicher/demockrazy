from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(url="vote/", permanent=False)),
    path("vote/", include("vote.urls")),
    path("admin/", admin.site.urls),
    # Ohne Slash und ohne Namespace: der Pfad wird von Monitoring konfiguriert, nicht per reverse().
    path("healthz", views.healthz),
]
