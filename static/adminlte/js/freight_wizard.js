(function(){
  // ====== Step 1: Service Option dinamis dari endpoint yang SUDAH ada ======
  const mode    = document.querySelector('[name="transport_mode"]');
  const service = document.querySelector('[name="service_option"]');

  function setPlaceholder(sel){
    sel.innerHTML = '';
    const ph = document.createElement('option');
    ph.value = '';
    ph.text  = '-- pilih service --';
    sel.appendChild(ph);
    sel.value = '';
    sel.disabled = true;
  }

  async function reloadServiceOptions(restoreValue){
    const m = (mode?.value || '').toUpperCase();
    if (!service) return;
    setPlaceholder(service);
    if (!m) return;

    try {
      const url  = `/sales/quotations/freight/service-options/?mode=${encodeURIComponent(m)}`;
      const resp = await fetch(url, { credentials:'same-origin' });
      const data = await resp.json();

      // Terima {options:[{value,label}]} atau [[value,label],...]
      const list = Array.isArray(data) ? data : (Array.isArray(data.options) ? data.options : []);
      list.forEach(opt=>{
        const value = (typeof opt === 'object' && opt !== null) ? (opt.value ?? opt[0]) : opt?.[0];
        const label = (typeof opt === 'object' && opt !== null) ? (opt.label ?? opt[1]) : opt?.[1];
        if(!value) return;
        const el = document.createElement('option');
        el.value = String(value);
        el.text  = label != null ? String(label) : String(value);
        service.appendChild(el);
      });

      service.disabled = service.options.length <= 1;

      if (restoreValue) {
        const ok = Array.from(service.options).some(o => o.value === restoreValue);
        if (ok) service.value = restoreValue;
      }
    } catch (e) {
      // biarkan disabled
      console.warn('service-options fetch failed', e);
    }
  }

  if (mode && service) {
    const previous = service.value || '';
    if (!mode.value) {
      setPlaceholder(service);
    } else {
      reloadServiceOptions(previous);
    }
    mode.addEventListener('change', ()=>reloadServiceOptions(''));
  }

  // ====== (Opsional) Step 2: auto amount per baris formset ======
  function hookAmount(prefix){
    const qty = document.querySelector(`[name="${prefix}-qty"]`);
    const price = document.querySelector(`[name="${prefix}-price"]`);
    const amount = document.querySelector(`[name="${prefix}-amount"]`);
    if(!qty || !price || !amount) return;
    function recalc(){
      const q = parseFloat(qty.value || '0');
      const p = parseFloat(price.value || '0');
      if(!isNaN(q) && !isNaN(p)) amount.value = (q*p).toFixed(2);
    }
    qty.addEventListener('input', recalc);
    price.addEventListener('input', recalc);
  }
  for (let i=0; i<20; i++) hookAmount(`cargo-${i}`);
})();
