(function(){
  // Auto-calc amount = qty * price (hanya kalau field ada)
  const qty = document.querySelector('[name="left-qty"]');
  const price = document.querySelector('[name="left-price"]');
  const amount = document.querySelector('[name="left-amount"]');
  function recalc(){
    if(qty && price && amount){
      const q = parseFloat(qty.value || "0");
      const p = parseFloat(price.value || "0");
      if(!isNaN(q) && !isNaN(p)) amount.value = (q * p).toFixed(2);
    }
  }
  if(qty) qty.addEventListener('input', recalc);
  if(price) price.addEventListener('input', recalc);

  // Optional: auto show date picker on focus
  const dateInput = document.querySelector('input[type="date"]');
  if(dateInput && dateInput.showPicker) {
    dateInput.addEventListener('focus', ()=>dateInput.showPicker());
  }
})();
