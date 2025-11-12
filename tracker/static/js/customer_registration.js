(function(){
  // Helper to perform AJAX POST for wizard steps
  function ajaxPostForm(form, onSuccess, onError){
    var formData = new FormData(form);
    var xhr = new XMLHttpRequest();
    xhr.open('POST', window.location.href);
    xhr.setRequestHeader('X-Requested-With','XMLHttpRequest');

    // Set CSRF token header from cookie for Django
    function getCookie(name){
      var cookieValue = null;
      if (document.cookie && document.cookie !== ''){
        var cookies = document.cookie.split(';');
        for (var i=0;i<cookies.length;i++){
          var cookie = cookies[i].trim();
          if (cookie.substring(0, name.length+1) === (name + '=')){
            cookieValue = decodeURIComponent(cookie.substring(name.length+1));
            break;
          }
        }
      }
      return cookieValue;
    }
    var csrftoken = getCookie('csrftoken');
    if(csrftoken){ try{ xhr.setRequestHeader('X-CSRFToken', csrftoken); }catch(e){} }

    xhr.onreadystatechange = function(){
      if(xhr.readyState !== 4) return;
      console.debug('Customer reg AJAX response', xhr.status, xhr.responseText.slice(0,200));
      if(xhr.status >=200 && xhr.status < 300){
        try{
          var data = JSON.parse(xhr.responseText);
        }catch(e){
          if(onError) onError('Invalid server response');
          return;
        }
        if(data.redirect_url){ window.location.href = data.redirect_url; return; }
        if(onSuccess) onSuccess(data);
      }else{
        if(onError) onError('Server error: ' + xhr.status);
      }
    };
    xhr.send(formData);
  }

  function loadStep(step){
    var url = window.location.pathname + '?step=' + step + '&load_step=1';
    fetch(url, {headers: {'X-Requested-With':'XMLHttpRequest'}})
      .then(function(r){ return r.json(); })
      .then(function(data){
        if(data.form_html){
          var container = document.getElementById('registrationWizard');
          container.innerHTML = data.form_html;
          // Re-bind handlers
          bindWizard();
        }
      }).catch(function(e){ console.error('Failed to load step', e); });
  }

  function bindWizard(){
    console.debug('bindWizard: called');
    var form = document.getElementById('customerRegistrationForm');
    if(!form){ console.debug('bindWizard: no form (customerRegistrationForm) found'); }
    // Update progress UI helper
    function updateProgress(){
      var stepInput = document.getElementById('currentStep');
      var displayEl = document.getElementById('currentStepDisplay');
      var step = 1;
      if(stepInput){ step = parseInt(stepInput.value || '1', 10); }
      else if(displayEl){ step = parseInt(displayEl.textContent||'1',10); }
      var total = 4;
      var pct = Math.round((step/total)*100);
      var bar = document.getElementById('registrationProgressBar');
      if(bar){ bar.style.width = pct + '%'; bar.setAttribute('aria-valuenow', step); }
      if(displayEl){ displayEl.textContent = step; }
      var indicators = document.querySelectorAll('#registrationSteps .step-indicator');
      indicators.forEach(function(el, idx){
        var active = (idx+1) === step;
        el.classList.toggle('bg-primary', active);
        el.classList.toggle('bg-secondary', !active);
      });
    }

    if(!form) return;
    var stepInput = document.getElementById('currentStep');
    var step = parseInt(stepInput.value || '1', 10);
    // Ensure progress updates on bind
    updateProgress();

    // Next for step 1
    var nextBtn = document.getElementById('nextStepBtn');
    console.debug('bindWizard: nextBtn=', !!nextBtn);
    if(nextBtn){
      if(!nextBtn.dataset.bound){
        nextBtn.dataset.bound = '1';
        nextBtn.addEventListener('click', function(e){
          e.preventDefault();
          try{
            // ensure save_only is 0
            var saveOnly = document.getElementById('saveOnly'); if(saveOnly) saveOnly.value='0';
            ajaxPostForm(form, function(data){
              try{
                // Check if customer already exists and redirect_url is provided
                if(data && data.redirect_url && !data.success){
                  // Customer exists - show modal with options instead of immediate redirect
                  showExistingCustomerModal(data.redirect_url, data.message || 'Customer already exists');
                  return;
                }
                // If server returned form_html with errors, render it
                if(data && data.form_html && (!data.success)){
                  document.getElementById('registrationWizard').innerHTML = data.form_html; bindWizard();
                  return;
                }
                // If server returned form_html for the next step, render it
                if(data && data.form_html && data.success){
                  document.getElementById('registrationWizard').innerHTML = data.form_html; bindWizard();
                  return;
                }
                // Otherwise explicitly load next step
                var cur = parseInt((document.getElementById('currentStep')||{value:1}).value||1,10);
                var next = Math.min(cur+1,4);
                loadStep(next);
              }catch(err){ console.error('Error handling next response', err); }
            }, function(err){ console.error('AJAX error', err); alert('Request failed: ' + err); });
          }catch(err){ console.error('Next click handler error', err); }
        });
      }
    }

    // Save customer quick
    var saveBtn = document.getElementById('saveCustomerBtn');
    if(saveBtn){
      if(!saveBtn.dataset.bound){
        saveBtn.dataset.bound = '1';
        saveBtn.addEventListener('click', function(e){
          e.preventDefault();
          var saveOnly = document.getElementById('saveOnly'); if(saveOnly) saveOnly.value='1';
          ajaxPostForm(form, function(data){
            if(data.redirect_url){ window.location.href = data.redirect_url; }
            else if(data.success && data.message){ alert(data.message); }
          }, function(err){ alert(err); });
        });
      }
    }

    // Back buttons
    var backBtn2 = document.getElementById('backFromStep2');
    if(backBtn2){ backBtn2.addEventListener('click', function(){ loadStep(1); }); }
    var backBtn3 = document.getElementById('backFromStep3');
    if(backBtn3){ backBtn3.addEventListener('click', function(){ loadStep(2); }); }
    var backBtn4 = document.getElementById('backFromStep4');
    if(backBtn4){ backBtn4.addEventListener('click', function(){ loadStep(3); }); }

    // Next from step 2
    var next2 = document.getElementById('nextStep2');
    if(next2){ next2.addEventListener('click', function(e){ e.preventDefault(); ajaxPostForm(form, function(data){ try{ if(data && data.form_html && (!data.success)){ document.getElementById('registrationWizard').innerHTML = data.form_html; bindWizard(); return; } if(data && data.form_html && data.success){ document.getElementById('registrationWizard').innerHTML = data.form_html; bindWizard(); return; } var cur = parseInt((document.getElementById('currentStep')||{value:2}).value||2,10); var next = Math.min(cur+1,4); loadStep(next); }catch(err){ console.error('Error handling step2 response', err); } }, function(err){ console.error('AJAX error', err); alert('Request failed: ' + err); }); }); }

    // Next from step3
    var next3 = document.getElementById('nextServiceBtn');
    if(next3){ next3.addEventListener('click', function(e){ 
      e.preventDefault(); 
      // Store vehicle data before submitting
      storeVehicleData();
      ajaxPostForm(form, function(data){ 
        try{ 
          if(data && data.form_html && (!data.success)){ 
            document.getElementById('registrationWizard').innerHTML = data.form_html; 
            bindWizard(); 
            return; 
          } 
          if(data && data.form_html && data.success){ 
            document.getElementById('registrationWizard').innerHTML = data.form_html; 
            bindWizard(); 
            // Restore vehicle data in step 4
            setTimeout(function() {
              restoreVehicleData();
              if (typeof updateVehicleSummary === 'function') {
                updateVehicleSummary();
              }
            }, 200);
            return; 
          } 
          var cur = parseInt((document.getElementById('currentStep')||{value:3}).value||3,10); 
          var next = Math.min(cur+1,4); 
          loadStep(next); 
        }catch(err){ console.error('Error handling step3 response', err); } 
      }, function(err){ console.error('AJAX error', err); alert('Request failed: ' + err); }); 
    }); }

    function initCustomerTypeFields(){
      var customerType = document.getElementById('id_customer_type');
      if(!customerType) return;
      var personalField = document.getElementById('personal-subtype-field');
      var organizationField = document.getElementById('organization-field');
      var taxField = document.getElementById('tax-field');
      function toggleFields(){
        var val = customerType.value;
        if(personalField) personalField.style.display = 'none';
        if(organizationField) organizationField.style.display = 'none';
        if(taxField) taxField.style.display = 'none';
        if(val === 'personal'){
          if(personalField) personalField.style.display = 'block';
        }else if(['company','government','ngo'].indexOf(val) !== -1){
          if(organizationField) organizationField.style.display = 'block';
          if(taxField) taxField.style.display = 'block';
        }
      }
      customerType.addEventListener('change', toggleFields);
      toggleFields();
    }

    function applyIntentSelection(intentValue){
      var hiddenIntent = document.getElementById('registrationIntent');
      if(hiddenIntent) hiddenIntent.value = intentValue;
      document.querySelectorAll('input[name="intent"]').forEach(function(radio){
        radio.checked = (radio.value === intentValue);
      });
      document.querySelectorAll('.intent-card').forEach(function(card){ card.classList.remove('border-primary','bg-light'); });
      var targetCard = document.querySelector('.intent-card input[value="'+intentValue+'"]');
      if(targetCard && targetCard.closest('.intent-card')){
        var card = targetCard.closest('.intent-card');
        card.classList.add('border-primary','bg-light');
      }
      var nextIntentBtn = document.getElementById('nextStep2');
      if(nextIntentBtn) nextIntentBtn.disabled = false;
    }

    window.selectIntent = function(intentValue){
      applyIntentSelection(intentValue);
    };

    function initIntentCards(){
      var radios = document.querySelectorAll('input[name="intent"]');
      if(!radios.length) return;
      var selectedValue = '';
      radios.forEach(function(radio){
        if(radio.checked && !selectedValue){
          selectedValue = radio.value;
        }
      });
      if(selectedValue){
        applyIntentSelection(selectedValue);
      }
    }

    window.selectServiceType = function(serviceValue){
      document.querySelectorAll('.service-card').forEach(function(card){ card.classList.remove('border-primary','bg-light'); });
      var radio = document.querySelector('input[name="service_type"][value="'+serviceValue+'"]');
      if(radio){ radio.checked = true; }
      var selectedCard = radio && radio.closest('.service-card');
      if(selectedCard){ selectedCard.classList.add('border-primary','bg-light'); }
      var nextServiceBtn = document.getElementById('nextServiceBtn');
      if(nextServiceBtn) nextServiceBtn.disabled = false;
    };

    function initServiceEtaHandlers(){
      var etaInput = document.getElementById('estimated_duration');
      var hint = document.getElementById('cr_total_eta_hint');
      var serviceSelector = 'input[type="checkbox"][name="service_selection"]';
      var boxes = document.querySelectorAll(serviceSelector);
      if(!boxes.length && !etaInput && !hint) return;
      function toggleWrapperState(cb){
        var wrapper = cb && cb.closest('.form-check');
        if(!wrapper || wrapper.dataset.cardClickBound === '1') return;
        wrapper.dataset.cardClickBound = '1';
        wrapper.addEventListener('click', function(e){
          if(e.target === cb || e.target.closest('label')) return;
          e.preventDefault();
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event('change', {bubbles: true}));
        });
      }
      function updateServiceEta(){
        var total = 0;
        Array.prototype.forEach.call(document.querySelectorAll(serviceSelector), function(cb){
          if(cb && cb.checked){
            var minutes = parseInt(cb.getAttribute('data-minutes') || '0', 10);
            if(!isNaN(minutes)) total += minutes;
          }
        });
        if(etaInput){
          etaInput.value = total > 0 ? String(total) : '0';
        }
        if(hint){
          if(total > 0){
            hint.style.display = '';
            hint.textContent = 'Estimated total time: ' + total + ' mins';
          }else{
            hint.style.display = 'none';
            hint.textContent = '';
          }
        }
        if(typeof updateStep3CombinedEta === 'function'){
          updateStep3CombinedEta();
        }
      }
      Array.prototype.forEach.call(boxes, function(cb){
        if(cb){
          toggleWrapperState(cb);
          cb.addEventListener('change', updateServiceEta);
        }
      });
      updateServiceEta();
    }

    function initTireServiceEtaHandlers(){
      var etaInput = document.getElementById('estimated_duration_sales');
      var hint = document.getElementById('cr_tire_services_total_eta_hint');
      var addonSelector = 'input[type="checkbox"][name="tire_services"]';
      var boxes = document.querySelectorAll(addonSelector);
      if(!boxes.length && !etaInput && !hint) return;
      function toggleWrapperState(cb){
        var wrapper = cb && cb.closest('.form-check');
        if(!wrapper || wrapper.dataset.cardClickBound === '1') return;
        wrapper.dataset.cardClickBound = '1';
        wrapper.addEventListener('click', function(e){
          if(e.target === cb || e.target.closest('label')) return;
          e.preventDefault();
          cb.checked = !cb.checked;
          cb.dispatchEvent(new Event('change', {bubbles: true}));
        });
      }
      function updateTireServicesEta(){
        var total = 0;
        Array.prototype.forEach.call(document.querySelectorAll(addonSelector), function(cb){
          if(cb && cb.checked){
            var minutes = parseInt(cb.getAttribute('data-minutes') || '0', 10);
            if(!isNaN(minutes)) total += minutes;
          }
        });
        if(etaInput){
          etaInput.value = total > 0 ? String(total) : '0';
        }
        if(hint){
          if(total > 0){
            hint.style.display = '';
            hint.textContent = 'Estimated total time: ' + total + ' mins';
          }else{
            hint.style.display = 'none';
            hint.textContent = '';
          }
        }
        if(typeof updateStep3CombinedEta === 'function'){
          updateStep3CombinedEta();
        }
      }
      Array.prototype.forEach.call(boxes, function(cb){
        if(cb){
          toggleWrapperState(cb);
          cb.addEventListener('change', updateTireServicesEta);
        }
      });
      updateTireServicesEta();
    }

    function initSalesItemAutofill(){
      var itemEl = document.getElementById('id_item_name');
      if(!itemEl) return;
      var brandEl = document.getElementById('id_brand');
      var rawItems = itemEl.getAttribute('data-items') || '{}';
      var itemsData = {};
      try{ itemsData = JSON.parse(rawItems); }catch(e){ itemsData = {}; }
      itemEl.addEventListener('change', function(){
        var itemData = itemsData[this.value];
        if(brandEl){
          brandEl.value = itemData && itemData.brand ? itemData.brand : '';
        }
      });
      if(itemEl.value && brandEl && itemsData[itemEl.value]){
        brandEl.value = itemsData[itemEl.value].brand || '';
      }
    }

    function initStep3EtaSync(){
      var serviceEta = document.getElementById('estimated_duration');
      var salesEta = document.getElementById('estimated_duration_sales');
      var salesHint = document.getElementById('cr_tire_services_total_eta_hint');
      var serviceHint = document.getElementById('cr_total_eta_hint');
      var serviceBoxes = document.querySelectorAll('input[type="checkbox"][name="service_selection"]');
      var addonBoxes = document.querySelectorAll('input[type="checkbox"][name="tire_services"]');
      var estimatedInput = document.querySelector('input[name="estimated_duration"]');

      function syncHints(total){
        if(serviceHint){
          if(total > 0){
            serviceHint.style.display = '';
            serviceHint.textContent = 'Estimated total time: ' + total + ' mins';
          }else{
            serviceHint.style.display = 'none';
            serviceHint.textContent = '';
          }
        }
        if(salesHint){
          if(total > 0){
            salesHint.style.display = '';
            salesHint.textContent = 'Estimated total time: ' + total + ' mins';
          }else{
            salesHint.style.display = 'none';
            salesHint.textContent = '';
          }
        }
      }

      function computeTotal(){
        var total = 0;
        Array.prototype.forEach.call(serviceBoxes, function(cb){
          if(cb && cb.checked){
            var minutes = parseInt(cb.getAttribute('data-minutes') || '0', 10);
            if(!isNaN(minutes)) total += minutes;
          }
        });
        Array.prototype.forEach.call(addonBoxes, function(cb){
          if(cb && cb.checked){
            var minutes = parseInt(cb.getAttribute('data-minutes') || '0', 10);
            if(!isNaN(minutes)) total += minutes;
          }
        });
        return total;
      }

      function updateAll(){
        var total = computeTotal();
        if(serviceEta){ serviceEta.value = total > 0 ? String(total) : '0'; }
        if(salesEta){ salesEta.value = total > 0 ? String(total) : '0'; }
        if(estimatedInput && estimatedInput !== serviceEta && estimatedInput !== salesEta){
          estimatedInput.value = total > 0 ? String(total) : '0';
        }
        syncHints(total);
      }

      window.updateStep3CombinedEta = updateAll;

      Array.prototype.forEach.call(serviceBoxes, function(cb){ if(cb){ cb.addEventListener('change', updateAll); } });
      Array.prototype.forEach.call(addonBoxes, function(cb){ if(cb){ cb.addEventListener('change', updateAll); } });
      updateAll();
    }

    initCustomerTypeFields();
    initIntentCards();
    initServiceEtaHandlers();
    initTireServiceEtaHandlers();
    initSalesItemAutofill();
    initStep3EtaSync();

    // If step4, bind order form interactions similar to order_create
    if(step === 4){
      var typeEl = document.querySelector('[name="type"]') || document.getElementById('id_type');
      function updateSections(){
        var t = (typeEl && (typeEl.value || (typeEl.options && typeEl.options[typeEl.selectedIndex] && typeEl.options[typeEl.selectedIndex].value))) || '';
        var s1 = document.getElementById('section-service'); if(s1) s1.style.display = (t==='service')? 'block':'none';
        var s2 = document.getElementById('section-sales'); if(s2) s2.style.display = (t==='sales')? 'block':'none';
        var s3 = document.getElementById('section-consultation'); if(s3) s3.style.display = (t==='consultation')? 'block':'none';
      }
      if(typeEl){ typeEl.addEventListener('change', updateSections); updateSections(); }

      // Auto-select brand when item changes using data-brands mapping
      var itemEl = document.getElementById('id_item_name');
      var brandEl = document.getElementById('id_brand');
      if(itemEl && brandEl){
        var mapping = {};
        try{ mapping = JSON.parse(itemEl.getAttribute('data-brands') || '{}'); }catch(e){ mapping = {}; }
        itemEl.addEventListener('change', function(){ var bn = mapping[this.value]; if(!bn) return; for(var i=0;i<brandEl.options.length;i++){ if(brandEl.options[i].text === bn || brandEl.options[i].value === bn){ brandEl.selectedIndex = i; break; } } });
      }

      // Vehicle select enabling when customer vehicles available (not needed here)
    }

  }

  // Initialize on DOM ready
  document.addEventListener('DOMContentLoaded', function(){ bindWizard(); });

  // Vehicle data preservation functions
  function storeVehicleData() {
    try {
      var vehicleData = {
        plate_number: (document.getElementById('id_plate_number') || {}).value || '',
        make: (document.getElementById('id_make') || {}).value || '',
        model: (document.getElementById('id_model') || {}).value || '',
        vehicle_type: (document.getElementById('id_vehicle_type') || {}).value || ''
      };
      sessionStorage.setItem('customerRegVehicleData', JSON.stringify(vehicleData));
    } catch(e) { console.debug('Failed to store vehicle data', e); }
  }
  
  function restoreVehicleData() {
    try {
      var stored = sessionStorage.getItem('customerRegVehicleData');
      if (!stored) return;
      
      var vehicleData = JSON.parse(stored);
      
      // Restore form fields if they exist
      var plateEl = document.getElementById('id_plate_number');
      var makeEl = document.getElementById('id_make');
      var modelEl = document.getElementById('id_model');
      var typeEl = document.getElementById('id_vehicle_type');
      
      if (plateEl) plateEl.value = vehicleData.plate_number || '';
      if (makeEl) makeEl.value = vehicleData.make || '';
      if (modelEl) modelEl.value = vehicleData.model || '';
      if (typeEl) typeEl.value = vehicleData.vehicle_type || '';
      
      // Update summary display
      if (typeof updateVehicleSummary === 'function') {
        updateVehicleSummary();
      }
      
      // Clear stored data
      sessionStorage.removeItem('customerRegVehicleData');
    } catch(e) { console.debug('Failed to restore vehicle data', e); }
  }

  // Expose a flag so inline progressive enhancement knows AJAX is active
  window.__CUSTOMER_REG_AJAX = true;

  // Function to show existing customer modal with options
  window.showExistingCustomerModal = function(customerDetailUrl, message) {
    // Extract customer ID from URL
    var customerIdMatch = customerDetailUrl.match(/\/customers\/(\d+)\//);
    var customerId = customerIdMatch ? customerIdMatch[1] : null;

    if (!customerId) {
      // Fallback to direct redirect if can't extract ID
      window.location.href = customerDetailUrl;
      return;
    }

    // Create and show modal
    var modalHtml = `
      <div class="modal fade" id="existingCustomerModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header bg-info text-white">
              <h5 class="modal-title">
                <i class="fa fa-user-check me-2"></i>Customer Already Exists
              </h5>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <p class="mb-3"><i class="fa fa-info-circle me-2 text-info"></i>${message}</p>
              <p class="text-muted mb-0">What would you like to do?</p>
            </div>
            <div class="modal-footer bg-light">
              <button type="button" class="btn btn-light" data-bs-dismiss="modal">Cancel</button>
              <a href="${customerDetailUrl}" class="btn btn-info">
                <i class="fa fa-user me-1"></i>View Profile
              </a>
              <a href="/tracker/customers/${customerId}/order/new/" class="btn btn-primary">
                <i class="fa fa-plus-circle me-1"></i>Create Order
              </a>
            </div>
          </div>
        </div>
      </div>
    `;

    // Remove existing modal if any
    var existing = document.getElementById('existingCustomerModal');
    if (existing) {
      existing.remove();
    }

    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Show the modal
    try {
      var modal = new bootstrap.Modal(document.getElementById('existingCustomerModal'));
      modal.show();
    } catch(e) {
      console.error('Error showing existing customer modal:', e);
      window.location.href = customerDetailUrl;
    }
  };
})();
