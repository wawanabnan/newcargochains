from django.contrib import admin
from django.urls import path, include
from account.views import dashboard_view

urlpatterns = [
    path("admin/", admin.site.urls),
    path("sales/",   include(("sales.urls", "sales"),   namespace="sales")),
    path("account/", include(("account.urls", "account"), namespace="account")),
    path("", dashboard_view, name="home"),  # root → dashboard
]