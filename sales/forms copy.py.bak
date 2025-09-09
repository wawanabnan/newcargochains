from django import forms
from .models import FreightQuotation, TransportMode, ModeService, ServiceOption

PAYMENT_TERM_CHOICES = [
    ("CASH",  "Cash / Tunai"),
    ("COD",   "Cash on Delivery"),
    ("NET30", "Net 30"),
    ("NET45", "Net 45"),
    ("NET60", "Net 60"),
]

class FreightHeaderForm(forms.ModelForm):
    transport_mode = forms.ChoiceField(
        choices=[], required=True, widget=forms.Select(attrs={"class":"form-select"})
    )
    # CharField + validasi ke DB → anti “invalid_choice”
    service_option = forms.CharField(
        required=True, widget=forms.TextInput(attrs={"class":"form-control d-none"})  # hidden; dipasok dari <select> custom
    )
    payment_term = forms.ChoiceField(
        choices=PAYMENT_TERM_CHOICES, required=True, widget=forms.Select(attrs={"class":"form-select"})
    )

    class Meta:
        model  = FreightQuotation
        fields = ["valid_until","customer","currency","payment_term","transport_mode","service_option","notes"]
        widgets = {
            "valid_until": forms.DateInput(attrs={"type":"date","class":"form-control"}),
            "customer":    forms.Select(attrs={"class":"form-select"}),
            "currency":    forms.TextInput(attrs={"class":"form-control"}),
            "notes": forms.Textarea(attrs={"id": "id_notes", "class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["transport_mode"].choices = list(
            TransportMode.objects.values_list("code","name")
        )
        if not self.initial.get("payment_term"):
            self.fields["payment_term"].initial = "NET30"

    def clean_service_option(self):
        """Terima kode (D2D/P2P/…) atau nama ('Port to Port'), normalisasi ke KODE
        dan validasi bahwa kombinasi (mode, service) ada di ModeService."""
        raw = (self.cleaned_data.get("service_option") or "").strip()
        mode = (self.data.get("transport_mode") or self.cleaned_data.get("transport_mode") or "").strip()
        if not raw or not mode:
            raise forms.ValidationError("Service option wajib diisi.")

        # cocok sebagai kode
        if ModeService.objects.filter(mode__code__iexact=mode, service__code__iexact=raw).exists():
            return raw.upper()

        # cocok sebagai nama
        try:
            svc = ServiceOption.objects.get(name__iexact=raw)
            if ModeService.objects.filter(mode__code__iexact=mode, service=svc).exists():
                return svc.code
        except ServiceOption.DoesNotExist:
            pass

        raise forms.ValidationError("Service option tidak valid untuk mode tersebut.")
