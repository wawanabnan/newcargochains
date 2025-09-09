// sales/static/sales/js/wizard_header.js
(function () {
  // --- Flatpickr (format dd-mm-yy)
  var el = document.getElementById("id_valid_until");
  if (el && window.flatpickr) {
    // Jika input sudah berisi YYYY-MM-DD (mis. dari server), convert ke dd-mm-yy
    var v = el.value && el.value.trim();
    if (/^\d{4}-\d{2}-\d{2}$/.test(v)) {
      var parts = v.split("-");
      el.value = parts[2].slice(-2) + "-" + parts[1] + "-" + parts[0].slice(-2);
    }
    window.flatpickr(el, {
      dateFormat: "d-m-y",
      allowInput: true,
      defaultDate: (function () {
        if (el.value && el.value.trim() !== "") return el.value;
        var add = parseInt(window.__QUO_VALID_DAYS__ || 7, 10);
        var d = new Date();
        d.setDate(d.getDate() + add);
        var dd = String(d.getDate()).padStart(2, "0");
        var mm = String(d.getMonth() + 1).padStart(2, "0");
        var yy = String(d.getFullYear()).slice(-2);
        var val = dd + "-" + mm + "-" + yy;
        el.value = val;
        return val;
      })()
    });
  }

  // --- TinyMCE height fix (gunakan height, bukan hanya autoresize)
  if (window.tinymce) {
    tinymce.init({
      selector: 'textarea[name="notes"]',
      menubar: false,
      statusbar: true,
      plugins: 'lists link table autoresize',
      toolbar:
        'undo redo | bold italic underline | bullist numlist | link table | removeformat',
      height: 460,
      autoresize_min_height: 460,
      branding: false,
      content_style:
        "body { font-family: system-ui, -apple-system, Segoe UI, Roboto, sans-serif; font-size: 14px; }"
    });
  }
})();
