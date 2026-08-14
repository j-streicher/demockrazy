from django.contrib import admin
from django.urls import include, path
from django.views.generic.base import RedirectView

from . import views

urlpatterns = [
    path("", RedirectView.as_view(url="vote/", permanent=False)),
    path("vote/", include("vote.urls")),
    path("admin/", admin.site.urls),
    # No slash and no namespace: the path is configured by monitoring, not built with reverse().
    path("healthz", views.healthz),
]
