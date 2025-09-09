# Freight Wizard Pack (AdminLTE 4)
Endpoint mengikuti yang lama:

- Start Wizard (Header & Lines in one view): `path('quotations/freight/new/', views.freight_create_wizard, name='freight_new')`
- Redirect Finish -> Charges: `path("quotations/freight/<int:pk>/charges/", views.freight_manage_charges, name="freight_charges")`
- AJAX:
  - Service options: `path("quotations/freight/service-options/", views.freight_service_options, name="freight_service_options")`
  - Location options: `path("quotations/freight/api/locations/", views.freight_location_options, name="freight_location_options")`

## Integrasi cepat
1) Tambah import view-file ini di `sales/views.py` *atau* letakkan sebagai file terpisah dan import di `urls.py`.
   - Jika terpisah: `from .views_freight_wizard import freight_create_wizard, freight_service_options, freight_location_options`
2) Pastikan model: `Location(loc_type=CITY/SEAPORT/AIRPORT)`, `FreightQuotation`, `FreightCargo` tersedia.
3) Pastikan `base.html` AdminLTE 4 aktif.

Selesai. Jalankan alur: Header -> Lines -> Finish -> Manage Charges.
