# sales/forms.py
from __future__ import annotations
from django import forms
from django.forms import formset_factory
from sales.models import FreightQuotation, Setting

def _get_setting(key: str, default=None):
    row = Setting.objects.filter(key=key).only("value").first()
    return row.value if row and row.value not in (None, "") else default

def _choices_from_setting(key: str, fallback: list[tuple[str, str]]):
    """
    Baca daftar choices dari Setting (comma separated), contoh:
      CURRENCY_LIST: IDR,USD,EUR
    Kembalikan list[(code, label)].
    """
    raw = _get_setting(key, None)
    if not raw:
        return fallback
    items = [x.strip() for x in raw.split(",") if x.strip()]
    return [(x, x) for x in items] if items else fallback


class FreightHeaderForm(forms.ModelForm):
    """
    Header sederhana dengan Bootstrap widgets + ChoiceField eksplisit agar TIDAK kosong.
    Currency/PaymentTerm dianggap konstanta (choices).
    """
    # ---- Choices konstanta (bisa ditimpa dari Setting) ----
    CURRENCY_CHOICES = _choices_from_setting(
        "CURRENCY_LIST",
        [("IDR", "IDR"), ("USD", "USD"), ("EUR", "EUR")]
    )
    PAYMENT_CHOICES = _choices_from_setting(
        "PAYMENT_TERM_LIST",
        [("CASH", "CASH"), ("COD", "COD"), ("NET7", "NET 7"), ("NET14", "NET 14"), ("NET30", "NET 30")]
    )

    currency = forms.ChoiceField(choices=CURRENCY_CHOICES, widget=forms.Select(attrs={"class": "form-select", "id": "id_currency"}))
    payment_term = forms.ChoiceField(choices=PAYMENT_CHOICES, widget=forms.Select(attrs={"class": "form-select", "id": "id_payment_term"}))

    class Meta:
        model = FreightQuotation
        fields = [
            "valid_until", "customer", "currency", "payment_term",
            "transport_mode", "service_option", "notes",
        ]
        widgets = {
            "valid_until": forms.DateInput(attrs={"type": "date", "class": "form-control", "id": "id_valid_until"}),
            "customer": forms.Select(attrs={"class": "form-select", "id": "id_customer"}),
            "transport_mode": forms.Select(attrs={"class": "form-select", "id": "id_transport_mode"}),
            "service_option": forms.Select(attrs={"class": "form-select", "id": "id_service_option"}),
            "notes": forms.Textarea(attrs={"class": "form-control", "id": "id_notes", "rows": 3}),
        }


# ---------- STEP Lines: form ringan per baris ----------
class CargoLineForm(forms.Form):
    origin = forms.ModelChoiceField(queryset=None, required=True, widget=forms.Select(attrs={"class": "form-select"}))
    destination = forms.ModelChoiceField(queryset=None, required=True, widget=forms.Select(attrs={"class": "form-select"}))
    description = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": "form-control"}))
    qty = forms.IntegerField(min_value=1, initial=1, required=True, widget=forms.NumberInput(attrs={"class": "form-control"}))
    weight_kg = forms.DecimalField(max_digits=12, decimal_places=3, required=False, widget=forms.NumberInput(attrs={"class": "form-control"}))
    volume_cbm = forms.DecimalField(max_digits=12, decimal_places=3, required=False, widget=forms.NumberInput(attrs={"class": "form-control"}))
    price = forms.DecimalField(max_digits=14, decimal_places=2, required=False, widget=forms.NumberInput(attrs={"class": "form-control"}))
    amount = forms.DecimalField(max_digits=14, decimal_places=2, required=False, widget=forms.NumberInput(attrs={"class": "form-control"}))

    def __init__(self, *args, **kwargs):
        origin_qs = kwargs.pop("origin_qs")
        dest_qs = kwargs.pop("dest_qs")
        super().__init__(*args, **kwargs)
        self.fields["origin"].queryset = origin_qs
        self.fields["destination"].queryset = dest_qs


CargoFormSet = formset_factory(CargoLineForm, extra=1, can_delete=True)
