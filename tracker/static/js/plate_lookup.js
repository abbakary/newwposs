/**
 * Plate Number Lookup - Smart Customer Detection
 * Detects when a plate number is entered/selected and checks if it belongs to an existing customer
 */

(function() {
  'use strict';

  // Store for tracking pending lookups
  const pendingLookups = {};
  const foundCustomers = {};

  /**
   * Get CSRF token from cookies
   */
  function getCSRFToken() {
    let token = null;
    if (document.cookie && document.cookie !== '') {
      const cookies = document.cookie.split(';');
      for (let i = 0; i < cookies.length; i++) {
        const cookie = cookies[i].trim();
        if (cookie.substring(0, 10) === 'csrftoken=') {
          token = decodeURIComponent(cookie.substring(10));
          break;
        }
      }
    }
    return token || document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
  }

  /**
   * Check if a plate number exists for another customer
   */
  function checkPlateNumber(plateNumber) {
    if (!plateNumber || plateNumber.trim() === '') {
      clearPlateFoundMessage();
      return;
    }

    const normalizedPlate = plateNumber.trim().toUpperCase();

    // Avoid duplicate lookups
    if (pendingLookups[normalizedPlate]) {
      return;
    }

    pendingLookups[normalizedPlate] = true;

    const csrfToken = getCSRFToken();

    fetch('/tracker/api/orders/check-plate/', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
        'X-Requested-With': 'XMLHttpRequest'
      },
      body: JSON.stringify({
        plate_number: normalizedPlate
      })
    })
    .then(response => response.json())
    .then(data => {
      delete pendingLookups[normalizedPlate];

      if (data.found && data.customer) {
        foundCustomers[normalizedPlate] = data;
        showPlateFoundModal(data.customer, data.vehicle);
      } else {
        clearPlateFoundMessage();
      }
    })
    .catch(error => {
      delete pendingLookups[normalizedPlate];
      console.error('Error checking plate:', error);
    });
  }

  /**
   * Show modal when a plate is found for an existing customer
   */
  function showPlateFoundModal(customer, vehicle) {
    // Remove existing modal if any
    const existing = document.getElementById('plateFoundModal');
    if (existing) {
      existing.remove();
    }

    const modalHtml = `
      <div class="modal fade" id="plateFoundModal" tabindex="-1" aria-hidden="true">
        <div class="modal-dialog modal-dialog-centered">
          <div class="modal-content">
            <div class="modal-header bg-success text-white">
              <h5 class="modal-title">
                <i class="fa fa-car me-2"></i>Vehicle Found!
              </h5>
              <button type="button" class="btn-close btn-close-white" data-bs-dismiss="modal"></button>
            </div>
            <div class="modal-body">
              <div class="alert alert-info mb-3">
                <i class="fa fa-info-circle me-2"></i>
                This plate number is already registered to an existing customer.
              </div>
              
              <div class="card mb-3">
                <div class="card-header bg-light">
                  <h6 class="mb-0">Customer Information</h6>
                </div>
                <div class="card-body">
                  <div class="mb-2">
                    <small class="text-muted d-block">Name</small>
                    <strong>${escapeHtml(customer.full_name)}</strong>
                  </div>
                  <div class="mb-2">
                    <small class="text-muted d-block">Phone</small>
                    <strong>${escapeHtml(customer.phone)}</strong>
                  </div>
                </div>
              </div>

              <div class="card">
                <div class="card-header bg-light">
                  <h6 class="mb-0">Vehicle Information</h6>
                </div>
                <div class="card-body">
                  <div class="row">
                    <div class="col-md-6">
                      <small class="text-muted d-block">Plate</small>
                      <strong>${escapeHtml(vehicle.plate)}</strong>
                    </div>
                    <div class="col-md-6">
                      <small class="text-muted d-block">Make/Model</small>
                      <strong>${vehicle.make ? escapeHtml(vehicle.make) : '—'} ${vehicle.model ? escapeHtml(vehicle.model) : ''}</strong>
                    </div>
                  </div>
                </div>
              </div>
            </div>
            <div class="modal-footer bg-light">
              <button type="button" class="btn btn-light" data-bs-dismiss="modal">Use Different Customer</button>
              <a href="/tracker/customers/${customer.id}/" class="btn btn-info" target="_blank">
                <i class="fa fa-user me-1"></i>View Customer Profile
              </a>
              <a href="/tracker/customers/${customer.id}/order/new/" class="btn btn-success">
                <i class="fa fa-plus-circle me-1"></i>Create Order for This Customer
              </a>
            </div>
          </div>
        </div>
      </div>
    `;

    // Add modal to body
    document.body.insertAdjacentHTML('beforeend', modalHtml);

    // Show the modal
    try {
      const modal = new bootstrap.Modal(document.getElementById('plateFoundModal'));
      modal.show();
    } catch(e) {
      console.error('Error showing plate found modal:', e);
    }
  }

  /**
   * Clear the plate found message
   */
  function clearPlateFoundMessage() {
    const modal = document.getElementById('plateFoundModal');
    if (modal) {
      try {
        bootstrap.Modal.getInstance(modal)?.hide();
      } catch(e) {}
      setTimeout(() => modal.remove(), 500);
    }
  }

  /**
   * Escape HTML to prevent XSS
   */
  function escapeHtml(text) {
    const map = {
      '&': '&amp;',
      '<': '&lt;',
      '>': '&gt;',
      '"': '&quot;',
      "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
  }

  /**
   * Initialize plate lookup for vehicle-related inputs
   */
  function initPlateLookup() {
    // Listen for plate number input in order forms
    const plateInputs = document.querySelectorAll(
      'input[name*="plate"], input[id*="plate"], input[placeholder*="plate"], input[placeholder*="Plate"]'
    );

    plateInputs.forEach(input => {
      // Use change event with debouncing for plate lookups
      let debounceTimer;
      input.addEventListener('change', function() {
        clearTimeout(debounceTimer);
        debounceTimer = setTimeout(() => {
          checkPlateNumber(this.value);
        }, 300);
      });

      // Also listen on blur for better UX
      input.addEventListener('blur', function() {
        setTimeout(() => {
          checkPlateNumber(this.value);
        }, 100);
      });
    });

    // Listen for vehicle selection changes in order forms
    const vehicleSelects = document.querySelectorAll(
      'select[name="vehicle"], select[id*="vehicle"]'
    );

    vehicleSelects.forEach(select => {
      select.addEventListener('change', function() {
        // Get the selected option's data-plate attribute if available
        const selectedOption = this.options[this.selectedIndex];
        if (selectedOption && selectedOption.getAttribute('data-plate')) {
          const plate = selectedOption.getAttribute('data-plate');
          // Don't check if it's the same customer we're working with
          // This is handled by the backend
        }
      });
    });
  }

  /**
   * Initialize on DOM ready
   */
  document.addEventListener('DOMContentLoaded', function() {
    initPlateLookup();

    // Re-initialize if new plate inputs are added dynamically
    const observer = new MutationObserver(function(mutations) {
      mutations.forEach(function(mutation) {
        if (mutation.addedNodes.length) {
          // Check if any new plate inputs were added
          const addedInputs = Array.from(mutation.addedNodes).filter(node => {
            if (node.nodeType === 1) {
              return node.matches && (
                node.matches('input[name*="plate"]') || 
                node.matches('input[id*="plate"]') ||
                (node.querySelectorAll && node.querySelectorAll('input[name*="plate"]').length > 0)
              );
            }
            return false;
          });

          if (addedInputs.length > 0) {
            initPlateLookup();
          }
        }
      });
    });

    // Watch for new elements
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
  });

  // Expose to window for debugging
  window.plateLookup = {
    checkPlate: checkPlateNumber,
    clearMessage: clearPlateFoundMessage
  };
})();
