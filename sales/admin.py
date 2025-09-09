from django.contrib import admin
from .models import FreightQuotation, FreightCargo, FreightCharge

class FreightCargoInline(admin.TabularInline):
    model = FreightCargo
    extra = 0

@admin.register(FreightQuotation)
class FreightQuotationAdmin(admin.ModelAdmin):
    list_display = ("id","number","date","customer","transport_mode","service_option","multi_destination","currency")
    inlines = [FreightCargoInline]


@admin.register(FreightCargo)
class FreightChargeAdmin(admin.ModelAdmin):
    list_display = ("id","description","qty","weight_kg","price","amount","origin","destination")
    list_editable = ("qty", "price", "origin","destination")
    


@admin.register(FreightCharge)
class FreightChargeAdmin(admin.ModelAdmin):
    list_display = ("id","cargo","description","qty","rate","amount")





