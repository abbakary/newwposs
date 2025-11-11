/**
 * Order Start Modal - Multi-step form handler
 * Manages order type selection, customer type selection, and extracted data form
 */

class OrderStartModal {
  constructor() {
    this.modal = null;
    this.currentStep = 1;
    this.totalSteps = 3;
    this.formData = {};
    this.init();
  }

  init() {
    this.modal = new bootstrap.Modal(document.getElementById('orderStartModal'), {
      backdrop: 'static',
      keyboard: false
    });

    this.attachEventListeners();
  }

  attachEventListeners() {
    const self = this;

    // Order type selection
    document.querySelectorAll('.order-type-option').forEach(option => {
      option.addEventListener('click', function(e) {
        e.preventDefault();
        const input = this.querySelector('input[type="radio"]');
        input.checked = true;
        self.handleOrderTypeChange();
      });
    });

    // Customer type selection
    document.querySelectorAll('.customer-type-option').forEach(option => {
      option.addEventListener('click', function(e) {
        e.preventDefault();
        const input = this.querySelector('input[type="radio"]');
        input.checked = true;
        self.handleCustomerTypeChange();
      });
    });

    // Form check inputs
    document.querySelectorAll('input[name="customer_type"], input[name="personal_subtype"]').forEach(input => {
      input.addEventListener('change', () => self.handleCustomerTypeChange());
    });

    // Step navigation
    document.getElementById('nextBtn').addEventListener('click', () => self.nextStep());
    document.getElementById('prevBtn').addEventListener('click', () => self.prevStep());
    document.getElementById('submitBtn').addEventListener('click', () => self.submitForm());
    document.getElementById('cancelBtn').addEventListener('click', () => self.resetForm());
  }

  handleOrderTypeChange() {
    const selectedType = document.querySelector('input[name="order_type"]:checked')?.value;
    
    if (!selectedType) {
      this.showError('orderTypeError', 'Please select an order type');
      return;
    }

    // Show/hide vehicle details based on order type
    const vehicleSection = document.querySelector('.vehicle-details-section');
    if (selectedType === 'upload') {
      // Vehicle details are more important for upload
      vehicleSection?.classList.remove('d-none');
    } else if (selectedType === 'inquiry') {
      // Hide vehicle details for inquiry
      vehicleSection?.classList.add('d-none');
    } else {
      vehicleSection?.classList.remove('d-none');
    }

    this.clearError('orderTypeError');
    this.formData.order_type = selectedType;
  }

  handleCustomerTypeChange() {
    const selectedType = document.querySelector('input[name="customer_type"]:checked')?.value;
    const personalSubtypeSection = document.querySelector('.personal-subtype-section');
    const orgDetailsSection = document.querySelector('.org-details-section');

    if (!selectedType) {
      return;
    }

    // Show/hide personal subtype section
    if (selectedType === 'personal') {
      personalSubtypeSection?.classList.remove('d-none');
      orgDetailsSection?.classList.add('d-none');
      this.clearRequiredFields([
        { name: 'organization_name', container: orgDetailsSection },
        { name: 'tax_number', container: orgDetailsSection }
      ]);
    } else {
      personalSubtypeSection?.classList.add('d-none');
      orgDetailsSection?.classList.remove('d-none');
      document.querySelector('input[name="personal_subtype"]').checked = false;
    }

    this.formData.customer_type = selectedType;
  }

  nextStep() {
    // Validate current step
    if (!this.validateStep(this.currentStep)) {
      return;
    }

    if (this.currentStep < this.totalSteps) {
      this.showStep(this.currentStep + 1);
    }
  }

  prevStep() {
    if (this.currentStep > 1) {
      this.showStep(this.currentStep - 1);
    }
  }

  showStep(stepNumber) {
    // Hide all steps
    document.querySelectorAll('.form-step').forEach(step => {
      step.classList.add('d-none');
    });

    // Remove active class from all step badges
    document.querySelectorAll('.step-badge').forEach(badge => {
      badge.classList.remove('active', 'completed');
    });

    // Show current step and previous completed steps
    for (let i = 1; i <= stepNumber; i++) {
      const step = document.getElementById(`step${i}`);
      const badge = document.querySelector(`.step-badge[data-step="${i}"]`);

      if (i < stepNumber) {
        badge?.classList.add('completed');
      } else if (i === stepNumber) {
        step?.classList.remove('d-none');
        badge?.classList.add('active');
      }
    }

    // Update button visibility
    const prevBtn = document.getElementById('prevBtn');
    const nextBtn = document.getElementById('nextBtn');
    const submitBtn = document.getElementById('submitBtn');

    prevBtn.style.display = stepNumber === 1 ? 'none' : 'block';
    nextBtn.style.display = stepNumber === this.totalSteps ? 'none' : 'block';
    submitBtn.style.display = stepNumber === this.totalSteps ? 'block' : 'none';

    this.currentStep = stepNumber;

    // Auto-fill extracted data if available
    if (stepNumber === 3) {
      this.prepareExtractedDataStep();
    }
  }

  validateStep(stepNumber) {
    this.clearAllErrors();

    switch (stepNumber) {
      case 1:
        return this.validateOrderType();
      case 2:
        return this.validateCustomerType();
      case 3:
        return this.validateExtractedData();
      default:
        return true;
    }
  }

  validateOrderType() {
    const selected = document.querySelector('input[name="order_type"]:checked');
    
    if (!selected) {
      this.showError('orderTypeError', 'Please select an order type');
      return false;
    }

    return true;
  }

  validateCustomerType() {
    const selected = document.querySelector('input[name="customer_type"]:checked');
    
    if (!selected) {
      this.showError('customerTypeError', 'Please select a customer type');
      return false;
    }

    const type = selected.value;

    // Validate personal subtype if personal customer
    if (type === 'personal') {
      const subtypeSelected = document.querySelector('input[name="personal_subtype"]:checked');
      if (!subtypeSelected) {
        this.showError('customerTypeError', 'Please specify if you are the owner or driver');
        return false;
      }
      this.formData.personal_subtype = subtypeSelected.value;
    }

    // Validate organization details if organizational customer
    if (['company', 'government', 'ngo'].includes(type)) {
      const orgName = document.querySelector('input[name="organization_name"]').value.trim();
      const taxNumber = document.querySelector('input[name="tax_number"]').value.trim();

      if (!orgName) {
        this.showError('customerTypeError', 'Organization name is required');
        return false;
      }

      if (!taxNumber) {
        this.showError('customerTypeError', 'Tax number/TIN is required');
        return false;
      }

      this.formData.organization_name = orgName;
      this.formData.tax_number = taxNumber;
    }

    this.formData.customer_type = type;
    return true;
  }

  validateExtractedData() {
    const errors = [];

    // Validate required fields
    const name = document.querySelector('input[name="extracted_customer_name"]').value.trim();
    const phone = document.querySelector('input[name="extracted_phone"]').value.trim();

    if (!name) {
      errors.push('Customer name is required');
    }

    if (!phone) {
      errors.push('Phone number is required');
    }

    if (errors.length > 0) {
      this.showError('extractedDataError', errors.join('; '));
      return false;
    }

    return true;
  }

  prepareExtractedDataStep() {
    // This is where you would populate extracted data from an upload
    // For now, leave it empty for user input
    // In the future, you could:
    // 1. Accept extracted data via modal parameter
    // 2. Auto-populate from a document upload
    // 3. Load from API response
  }

  submitForm() {
    if (!this.validateExtractedData()) {
      return;
    }

    // Collect all form data
    const formElement = document.getElementById('orderStartForm');
    const formData = new FormData(formElement);

    // Add custom data
    formData.set('customer_name', document.querySelector('input[name="extracted_customer_name"]').value);
    formData.set('phone', document.querySelector('input[name="extracted_phone"]').value);
    formData.set('email', document.querySelector('input[name="extracted_email"]').value || '');
    formData.set('address', document.querySelector('textarea[name="extracted_address"]').value || '');
    formData.set('description', document.querySelector('textarea[name="extracted_description"]').value || '');
    formData.set('estimated_duration', document.querySelector('input[name="extracted_duration"]').value || '');
    formData.set('priority', document.querySelector('select[name="extracted_priority"]').value || 'medium');
    formData.set('plate_number', document.querySelector('input[name="extracted_plate"]').value || '');
    formData.set('vehicle_make', document.querySelector('input[name="extracted_make"]').value || '');
    formData.set('vehicle_model', document.querySelector('input[name="extracted_model"]').value || '');

    // Show loading state
    const submitBtn = document.getElementById('submitBtn');
    const originalText = submitBtn.innerHTML;
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-2"></span>Creating...';

    // Submit to server
    fetch('/api/orders/create-from-modal/', {
      method: 'POST',
      body: formData
    })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        // Show success message
        this.showSuccessMessage('Order created successfully!');

        // Redirect or close modal
        setTimeout(() => {
          window.location.href = `/tracker/orders/started/${data.order_id}/`;
        }, 1500);
      } else {
        this.showError('extractedDataError', data.error || 'Failed to create order');
        submitBtn.disabled = false;
        submitBtn.innerHTML = originalText;
      }
    })
    .catch(error => {
      this.showError('extractedDataError', 'An error occurred: ' + error.message);
      submitBtn.disabled = false;
      submitBtn.innerHTML = originalText;
    });
  }

  resetForm() {
    document.getElementById('orderStartForm').reset();
    this.formData = {};
    this.currentStep = 1;
    this.showStep(1);
  }

  showError(elementId, message) {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
      errorDiv.querySelector('span').textContent = message;
      errorDiv.style.display = 'block';
    }
  }

  clearError(elementId) {
    const errorDiv = document.getElementById(elementId);
    if (errorDiv) {
      errorDiv.style.display = 'none';
    }
  }

  clearAllErrors() {
    document.querySelectorAll('[id$="Error"]').forEach(error => {
      error.style.display = 'none';
    });
  }

  clearRequiredFields(fields) {
    fields.forEach(field => {
      if (field.container) {
        const input = field.container.querySelector(`[name="${field.name}"]`);
        if (input) {
          input.value = '';
          input.removeAttribute('required');
        }
      }
    });
  }

  showSuccessMessage(message) {
    const alert = document.createElement('div');
    alert.className = 'alert alert-success alert-dismissible fade show';
    alert.role = 'alert';
    alert.innerHTML = `
      <i class="fa fa-check-circle me-2"></i>${message}
      <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
    `;
    document.body.insertBefore(alert, document.body.firstChild);
  }

  open() {
    this.resetForm();
    this.modal.show();
  }

  close() {
    this.modal.hide();
  }
}

// Initialize on document ready
document.addEventListener('DOMContentLoaded', function() {
  window.orderStartModal = new OrderStartModal();

  // Open modal on button click
  const openModalBtn = document.getElementById('openOrderStartModal');
  if (openModalBtn) {
    openModalBtn.addEventListener('click', () => window.orderStartModal.open());
  }
});
