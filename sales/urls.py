from django.urls import path
from .wizard_v2 import freight_create_wizard_v2
from . import views

from .wizard_clean import freight_create_wizard_clean        # ← tambahkan ini
from .views_detail_clean import freight_detail_clean         # ← dan ini
from .wizard_clean import freight_create_wizard_clean, freight_detail_clean, ping_wizard
from . import aux_api

app_name = "sales"

urlpatterns = [
    path("quotations/freight/<int:pk>/charges/", views.freight_manage_charges, name="freight_charges"),
    path('quotations/freight/new/', views.freight_create_wizard, name='freight_new'),
    # FREIGHT
    path("quotations/freight/", views.freight_list, name="freight_list"),
  #  path("quotations/freight/<int:pk>/edit/", views.freight_edit, name="freight_edit"),
    path("quotations/freight/<int:pk>/view/", views.freight_view, name="freight_view"),
    # AJAX
    path("quotations/freight/service-options/", views.freight_service_options, name="freight_service_options"),
    path("quotations/freight/actions/bulk/", views.freight_bulk_action, name="freight_bulk_action") ,
    path("quotations/freight/<int:pk>/pdf/", views.freight_pdf, name="freight_pdf"),
    path("quotations/freight/<int:pk>/email/", views.freight_send_email, name="freight_email"),
    #path("sales/orders/freight/<int:pk>/generate/", views.freight_generate_order, name="freight_generate_order"),
    
   # --- Freight Order  ---
    path("orders/freight/", views.freight_order_list, name="freight_order_list"),
    path("orders/freight/<int:pk>/", views.freight_order_view, name="freight_order_view"),
    path("orders/freight/<int:pk>/generate/", views.freight_generate_order, name="freight_generate_order"),


      path("quotations/freight/api/wizard-state/", aux_api.wizard_state, name="freight_wizard_state"),
    path("quotations/freight/api/locations/", aux_api.location_options, name="freight_location_options"),


]