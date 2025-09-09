from django.shortcuts import render, get_object_or_404
from django.db.models import Prefetch
from .models import FreightQuotation, FreightCargo

def freight_detail_clean(request, pk):
    q = get_object_or_404(
        FreightQuotation.objects.select_related("customer").prefetch_related(
            Prefetch("cargos", queryset=FreightCargo.objects.select_related("origin","destination"))
        ),
        pk=pk,
    )
    return render(request, "sales/freight/detail_clean.html", {"q": q})
