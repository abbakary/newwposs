from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.db.models import Q
from datetime import timedelta
import uuid


class Branch(models.Model):
    """Business branch/location for multi-region scoping."""
    name = models.CharField(max_length=128, unique=True)
    code = models.CharField(max_length=32, unique=True)
    region = models.CharField(max_length=128, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["code"], name="idx_branch_code"),
            models.Index(fields=["region"], name="idx_branch_region"),
        ]

    def __str__(self) -> str:
        r = f" ({self.region})" if self.region else ""
        return f"{self.name}{r}"


class Customer(models.Model):
    TYPE_CHOICES = [
        ("government", "Government"),
        ("ngo", "NGO"),
        ("company", "Private Company"),
        ("personal", "Personal"),
    ]
    PERSONAL_SUBTYPE = [("owner", "Owner"), ("driver", "Driver")]
    STATUS_CHOICES = [
        ("arrived", "Arrived"),
        ("in_service", "In Service"),
        ("completed", "Completed"),
        ("departed", "Departed"),
    ]

    code = models.CharField(max_length=32, unique=True, editable=False)
    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='customers')
    full_name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20)
    whatsapp = models.CharField(max_length=20, blank=True, null=True, help_text="WhatsApp number (if different from phone)")
    email = models.EmailField(blank=True, null=True)
    address = models.TextField(blank=True, null=True)

    # keep this as "notes" so your forms work, but mark as deprecated
    notes = models.TextField(
        blank=True,
        null=True,
        help_text='General notes about the customer (deprecated, use CustomerNote model instead)'
    )

    customer_type = models.CharField(max_length=20, choices=TYPE_CHOICES, null=True, blank=True)
    organization_name = models.CharField(max_length=255, blank=True, null=True)
    tax_number = models.CharField(max_length=64, blank=True, null=True)
    personal_subtype = models.CharField(max_length=16, choices=PERSONAL_SUBTYPE, blank=True, null=True)

    registration_date = models.DateTimeField(default=timezone.now)
    arrival_time = models.DateTimeField(blank=True, null=True)
    current_status = models.CharField(max_length=20, choices=STATUS_CHOICES, default="arrived")

    total_visits = models.PositiveIntegerField(default=0)
    total_spent = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    last_visit = models.DateTimeField(blank=True, null=True)

    def save(self, *args, **kwargs):
        if not self.code:
            self.code = f"CUST{str(uuid.uuid4())[:8].upper()}"
            while Customer.objects.filter(code=self.code).exists():
                self.code = f"CUST{str(uuid.uuid4())[:8].upper()}"
        if not self.arrival_time:
            self.arrival_time = timezone.now()
        super().save(*args, **kwargs)

    def get_icon_for_customer_type(self):
        """Return appropriate icon class based on customer type"""
        if not self.customer_type:
            return 'user'
        
        icon_map = {
            'government': 'landmark',
            'ngo': 'hands-helping',
            'company': 'building',
            'personal': 'user',
        }
        return icon_map.get(self.customer_type, 'user')
        
    def __str__(self):
        return f"{self.full_name} ({self.code})"

    class Meta:
        indexes = [
            models.Index(fields=["full_name"], name="idx_cust_name"),
            models.Index(fields=["phone"], name="idx_cust_phone"),
            models.Index(fields=["email"], name="idx_cust_email"),
            models.Index(fields=["registration_date"], name="idx_cust_reg"),
            models.Index(fields=["last_visit"], name="idx_cust_lastvisit"),
            models.Index(fields=["customer_type"], name="idx_cust_type"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["branch", "full_name", "phone", "organization_name", "tax_number"],
                name="uniq_customer_identity",
            )
        ]


class Vehicle(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="vehicles")
    plate_number = models.CharField(max_length=32)
    make = models.CharField(max_length=64, blank=True, null=True)
    model = models.CharField(max_length=64, blank=True, null=True)
    vehicle_type = models.CharField(max_length=64, blank=True, null=True)

    def __str__(self):
        return f"{self.plate_number} - {self.make or ''} {self.model or ''}"

    class Meta:
        indexes = [
            models.Index(fields=["customer"], name="idx_vehicle_customer"),
            models.Index(fields=["plate_number"], name="idx_vehicle_plate"),
        ]


class Order(models.Model):
    TYPE_CHOICES = [("service", "Service"), ("sales", "Sales"), ("inquiry", "Inquiries")]
    STATUS_CHOICES = [
        ("created", "New"),
        ("in_progress", "In Progress"),
        ("overdue", "Overdue"),
        ("completed", "Completed"),
        ("cancelled", "Cancelled"),
    ]
    PRIORITY_CHOICES = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("urgent", "Urgent")]

    order_number = models.CharField(max_length=32, unique=True, editable=False)
    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='orders')
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="orders")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name="orders")
    type = models.CharField(max_length=16, choices=TYPE_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="created")
    priority = models.CharField(max_length=16, choices=PRIORITY_CHOICES, default="medium")

    description = models.TextField(blank=True, null=True)
    estimated_duration = models.PositiveIntegerField(blank=True, null=True, help_text="Minutes")
    actual_duration = models.PositiveIntegerField(blank=True, null=True)

    # Sales fields
    item_name = models.CharField(max_length=64, blank=True, null=True)
    brand = models.CharField(max_length=64, blank=True, null=True)
    quantity = models.PositiveIntegerField(blank=True, null=True)
    tire_type = models.CharField(max_length=32, blank=True, null=True)

    # Consultation fields
    inquiry_type = models.CharField(max_length=64, blank=True, null=True)
    questions = models.TextField(blank=True, null=True)
    contact_preference = models.CharField(max_length=16, blank=True, null=True)
    follow_up_date = models.DateField(blank=True, null=True)

    # Timestamps and assignment
    created_at = models.DateTimeField(default=timezone.now)
    started_at = models.DateTimeField(blank=True, null=True)
    completed_at = models.DateTimeField(blank=True, null=True)
    cancelled_at = models.DateTimeField(blank=True, null=True)

    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="assigned_orders")

    # Completion evidence and signer
    signature_file = models.ImageField(upload_to='order_signatures/', blank=True, null=True)
    completion_attachment = models.FileField(upload_to='order_attachments/', blank=True, null=True)
    signed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='orders_signed')
    signed_at = models.DateTimeField(blank=True, null=True)
    # completion_date is kept for historical compatibility; completed_at is canonical timestamp used across views

    # Overrun / delay reporting (when order exceeds estimated duration)
    overrun_reason = models.TextField(blank=True, null=True, help_text="Reason provided when an order exceeded its ETA and was completed later")
    overrun_reported_at = models.DateTimeField(blank=True, null=True)
    overrun_reported_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='overrun_reports')

    # Additional fields used across the app
    completion_date = models.DateTimeField(blank=True, null=True)
    cancellation_reason = models.TextField(blank=True, null=True)

    # Job card/identification number for quick order lookup (optional)
    job_card_number = models.CharField(max_length=64, blank=True, null=True, unique=True)

    def __str__(self):
        return f"{self.order_number} - {self.customer.full_name}"

    def auto_progress_if_elapsed(self):
        """Automatically move created -> in_progress after 10 minutes."""
        if self.status == 'created' and (timezone.now() - self.created_at) >= timedelta(minutes=10):
            self.status = 'in_progress'
            self.started_at = self.started_at or timezone.now()
            self.save(update_fields=['status', 'started_at'])

    class Meta:
        indexes = [
            models.Index(fields=["order_number"], name="idx_order_number"),
            models.Index(fields=["status"], name="idx_order_status"),
            models.Index(fields=["type"], name="idx_order_type"),
            models.Index(fields=["created_at"], name="idx_order_created"),
        ]

    def _generate_order_number(self) -> str:
        """Generate a unique human-friendly order number."""
        from uuid import uuid4

        prefix = 'ORD'
        base = timezone.now().strftime('%Y%m%d%H%M%S')
        # Retry until unique to avoid collision under concurrent requests
        for _ in range(5):
            candidate = f"{prefix}{base}{uuid4().hex[:4].upper()}"
            if not Order.objects.filter(order_number=candidate).exists():
                return candidate
        # Fallback to full UUID if repeated collisions occur
        return f"{prefix}{uuid4().hex.upper()}"

    def save(self, *args, **kwargs):
        """Ensure order numbers exist and inquiries auto-complete."""
        if not self.order_number:
            self.order_number = self._generate_order_number()
        # If this is an inquiry, make it completed and set completed timestamps
        if self.type == 'inquiry':
            now = timezone.now()
            # Preserve any explicit completed_at if already provided, otherwise set
            if not self.completed_at:
                self.completed_at = now
            if not self.completion_date:
                self.completion_date = now
            # Force status to completed
            self.status = 'completed'
        super().save(*args, **kwargs)


class OrderAttachment(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='order_attachments/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_order_attachments')
    uploaded_at = models.DateTimeField(auto_now_add=True)
    title = models.CharField(max_length=255, blank=True, null=True)

    def filename(self):
        try:
            return self.file.name.split('/')[-1]
        except Exception:
            return self.file.name

    def __str__(self):
        return f"Attachment #{self.id} for {self.order.order_number}"

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['order'], name='idx_order_attachment_order'),
            models.Index(fields=['uploaded_at'], name='idx_order_att_uploaded_at'),
        ]


class Brand(models.Model):
    name = models.CharField(max_length=128, unique=True)
    description = models.TextField(blank=True, null=True)
    website = models.URLField(blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="idx_brand_name"),
            models.Index(fields=["is_active"], name="idx_brand_active"),
        ]

    def __str__(self) -> str:
        return self.name


class InventoryItem(models.Model):
    name = models.CharField(max_length=128)
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True, related_name='items')
    description = models.TextField(blank=True, null=True)
    quantity = models.PositiveIntegerField(default=0)
    price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    sku = models.CharField(max_length=64, blank=True, null=True)
    barcode = models.CharField(max_length=64, blank=True, null=True)
    reorder_level = models.PositiveIntegerField(default=5)
    location = models.CharField(max_length=128, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="idx_inv_name"),
            models.Index(fields=["quantity"], name="idx_inv_qty"),
            models.Index(fields=["is_active"], name="idx_inv_active"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["name", "brand"], name="uniq_item_brand_name")
        ]

    def __str__(self) -> str:
        b = self.brand.name if self.brand else "Unbranded"
        return f"{b} - {self.name}"


class InventoryAdjustment(models.Model):
    ADJUSTMENT_TYPES = (
        ("addition", "Addition"),
        ("removal", "Removal"),
    )
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='adjustments')
    adjustment_type = models.CharField(max_length=16, choices=ADJUSTMENT_TYPES)
    quantity = models.PositiveIntegerField()
    reference = models.CharField(max_length=64, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)
    adjusted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='inventory_adjustments')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['created_at'], name='idx_inv_adj_created'),
            models.Index(fields=['adjustment_type'], name='idx_inv_adj_type'),
        ]

    # Backwards-friendly aliases used by older utility scripts
    @property
    def user(self):
        return self.adjusted_by

    @property
    def date(self):
        return self.created_at

    def __str__(self) -> str:
        return f"{self.get_adjustment_type_display()} {self.quantity} × {self.item}"


class Profile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    branch = models.ForeignKey(Branch, on_delete=models.SET_NULL, null=True, blank=True, related_name='profiles')
    photo = models.ImageField(upload_to='profile_photos/', blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"Profile of {self.user.username}"


class CustomerNote(models.Model):
    customer = models.ForeignKey(
        Customer,
        on_delete=models.CASCADE,
        related_name='note_entries',
        related_query_name='note_entry',
    )
    content = models.TextField()
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='customer_notes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['customer'], name='idx_cnote_customer'),
            models.Index(fields=['created_at'], name='idx_cnote_created'),
        ]

    def __str__(self) -> str:
        return f"Note for {self.customer.full_name} at {timezone.localtime(self.created_at).strftime('%Y-%m-%d %H:%M')}"


class ServiceType(models.Model):
    """Admin-managed service types for 'Service' orders with expected durations."""
    name = models.CharField(max_length=128, unique=True)
    estimated_minutes = models.PositiveIntegerField(default=30, help_text="Expected time in minutes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="idx_service_type_name"),
            models.Index(fields=["is_active"], name="idx_service_type_active"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.estimated_minutes}m)"


class ServiceAddon(models.Model):
    """Admin-managed add-on services for 'Sales' orders (e.g., installation, balancing)."""
    name = models.CharField(max_length=128, unique=True)
    estimated_minutes = models.PositiveIntegerField(default=10, help_text="Expected time in minutes")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]
        indexes = [
            models.Index(fields=["name"], name="idx_service_addon_name"),
            models.Index(fields=["is_active"], name="idx_service_addon_active"),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.estimated_minutes}m)"


class DocumentScan(models.Model):
    """Store uploaded documents (quotations, scanned documents, etc.)"""
    DOCUMENT_TYPE_CHOICES = [
        ('quotation', 'Quotation'),
        ('invoice', 'Invoice'),
        ('receipt', 'Receipt'),
        ('estimate', 'Estimate'),
        ('other', 'Other'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, null=True, blank=True, related_name='document_scans')
    vehicle_plate = models.CharField(max_length=32, blank=True, null=True, db_index=True)
    customer_phone = models.CharField(max_length=20, blank=True, null=True)

    file = models.FileField(upload_to='document_scans/')
    document_type = models.CharField(max_length=32, choices=DOCUMENT_TYPE_CHOICES, default='quotation')

    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='uploaded_documents')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    file_name = models.CharField(max_length=255, blank=True, null=True)
    file_size = models.PositiveIntegerField(blank=True, null=True)
    file_mime_type = models.CharField(max_length=64, blank=True, null=True)

    # Extraction status tracking
    extraction_status = models.CharField(
        max_length=16,
        choices=[
            ('pending', 'Pending'),
            ('processing', 'Processing'),
            ('completed', 'Completed'),
            ('failed', 'Failed'),
        ],
        default='pending'
    )
    extraction_error = models.TextField(blank=True, null=True)
    extracted_at = models.DateTimeField(blank=True, null=True)

    class Meta:
        ordering = ['-uploaded_at']
        indexes = [
            models.Index(fields=['order'], name='idx_docscan_order'),
            models.Index(fields=['vehicle_plate'], name='idx_docscan_plate'),
            models.Index(fields=['customer_phone'], name='idx_docscan_phone'),
            models.Index(fields=['uploaded_at'], name='idx_docscan_uploaded'),
            models.Index(fields=['extraction_status'], name='idx_docscan_extract_status'),
        ]

    def __str__(self) -> str:
        order_str = f"Order {self.order.order_number}" if self.order else f"Plate {self.vehicle_plate}"
        return f"{self.document_type.upper()} - {order_str}"


class DocumentExtraction(models.Model):
    """Store extracted data from documents"""
    document = models.OneToOneField(DocumentScan, on_delete=models.CASCADE, related_name='extraction')

    # Extracted fields (flexible JSON-like storage)
    raw_text = models.TextField(blank=True, null=True)

    # Customer info
    extracted_customer_name = models.CharField(max_length=255, blank=True, null=True)
    extracted_customer_phone = models.CharField(max_length=20, blank=True, null=True)
    extracted_customer_email = models.EmailField(blank=True, null=True)
    extracted_customer_address = models.TextField(blank=True, null=True)

    # Vehicle info
    extracted_vehicle_plate = models.CharField(max_length=32, blank=True, null=True)
    extracted_vehicle_make = models.CharField(max_length=64, blank=True, null=True)
    extracted_vehicle_model = models.CharField(max_length=64, blank=True, null=True)
    extracted_vehicle_type = models.CharField(max_length=64, blank=True, null=True)

    # Order/Service info
    extracted_order_description = models.TextField(blank=True, null=True)
    extracted_service_type = models.CharField(max_length=128, blank=True, null=True)
    extracted_item_name = models.CharField(max_length=128, blank=True, null=True)
    extracted_brand = models.CharField(max_length=128, blank=True, null=True)
    extracted_quantity = models.CharField(max_length=16, blank=True, null=True)
    extracted_tire_type = models.CharField(max_length=64, blank=True, null=True)

    # Pricing info
    extracted_amount = models.CharField(max_length=32, blank=True, null=True)
    extracted_currency = models.CharField(max_length=16, blank=True, null=True)

    # Invoice metadata
    code_no = models.CharField(max_length=64, blank=True, null=True, help_text='Customer / code number from invoice (Code No)')
    reference = models.CharField(max_length=64, blank=True, null=True, help_text='Reference field from invoice (often plate)')
    net_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    vat_amount = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    gross_value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    # Confidence scores (0-100)
    confidence_overall = models.PositiveIntegerField(default=0)
    extracted_data_json = models.JSONField(default=dict, blank=True)

    extracted_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-extracted_at']
        indexes = [
            models.Index(fields=['document'], name='idx_extraction_document'),
            models.Index(fields=['extracted_vehicle_plate'], name='idx_extraction_plate'),
            models.Index(fields=['extracted_customer_phone'], name='idx_extraction_phone'),
        ]

    def __str__(self) -> str:
        return f"Extraction for {self.document.file_name}"


class DocumentExtractionItem(models.Model):
    """Store individual extracted line items for a document extraction."""
    extraction = models.ForeignKey(DocumentExtraction, on_delete=models.CASCADE, related_name='items')
    line_no = models.PositiveIntegerField(null=True, blank=True, help_text='Line number in document (if available)')
    code = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    description = models.TextField(blank=True, null=True)
    qty = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    unit = models.CharField(max_length=16, blank=True, null=True)
    rate = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    value = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)

    class Meta:
        ordering = ['extraction', 'line_no']
        indexes = [
            models.Index(fields=['extraction'], name='idx_extr_item_extraction'),
            models.Index(fields=['code'], name='idx_extr_item_code'),
        ]

    def __str__(self) -> str:
        return f"Item {self.code or ''} - {self.description[:50] if self.description else ''}"


class ServiceTemplate(models.Model):
    """
    Template for common services found in invoices.
    Used to match extracted service descriptions and auto-assign estimation times.
    """
    # Service identification
    name = models.CharField(max_length=255, unique=True, db_index=True, help_text="Service name (e.g., 'Oil Change', 'Tire Rotation')")

    # Keywords that might appear in invoices for this service
    keywords = models.TextField(blank=True, null=True, help_text="Comma-separated keywords for matching (e.g., 'oil, oil change, oil service')")

    # Service details
    description = models.TextField(blank=True, null=True)
    estimated_minutes = models.PositiveIntegerField(default=30, help_text="Estimated time in minutes")
    service_type = models.CharField(
        max_length=16,
        choices=[('service', 'Service'), ('sales', 'Sales'), ('both', 'Both')],
        default='service',
        help_text="Whether this applies to service, sales, or both order types"
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_common = models.BooleanField(default=False, help_text="Mark as common/frequently used")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-is_common', 'name']
        indexes = [
            models.Index(fields=['name'], name='idx_svctemplate_name'),
            models.Index(fields=['is_active'], name='idx_svctemplate_active'),
            models.Index(fields=['is_common'], name='idx_svctemplate_common'),
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.estimated_minutes}m)"

    def matches_keyword(self, text: str) -> bool:
        """Check if given text matches any of the service keywords"""
        if not self.keywords:
            return False
        keywords = [k.strip().lower() for k in self.keywords.split(',')]
        text_lower = text.lower()
        return any(kw in text_lower for kw in keywords)


class InvoicePatternMatcher(models.Model):
    """
    Stores regex patterns for extracting specific fields from invoices.
    Allows flexible matching of various invoice formats.
    """
    FIELD_TYPES = [
        ('plate_number', 'Vehicle Plate Number'),
        ('customer_name', 'Customer Name'),
        ('customer_phone', 'Customer Phone'),
        ('customer_email', 'Customer Email'),
        ('service_description', 'Service Description'),
        ('item_name', 'Item Name'),
        ('quantity', 'Quantity'),
        ('amount', 'Amount'),
        ('date', 'Date'),
        ('reference', 'Reference Number'),
    ]

    # Pattern identification
    name = models.CharField(max_length=255, help_text="Name of this pattern (e.g., 'Plate in parentheses')")
    field_type = models.CharField(max_length=32, choices=FIELD_TYPES, db_index=True)

    # Pattern definition
    regex_pattern = models.TextField(help_text="Regex pattern to extract the field value")
    extract_group = models.PositiveIntegerField(default=1, help_text="Which capture group to extract (1-based)")

    # Pattern scope
    invoice_format = models.CharField(
        max_length=64,
        blank=True,
        null=True,
        help_text="Invoice format this pattern applies to (e.g., 'standard', 'proforma')"
    )

    # Status
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False, help_text="Use this pattern by default")
    priority = models.PositiveIntegerField(default=100, help_text="Lower number = higher priority")

    # Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['priority', '-is_default', 'field_type']
        indexes = [
            models.Index(fields=['field_type', 'is_active'], name='idx_pattern_field_active'),
            models.Index(fields=['priority'], name='idx_pattern_priority'),
        ]
        constraints = [
            models.UniqueConstraint(fields=['name'], name='uniq_pattern_name'),
        ]

    def __str__(self) -> str:
        return f"{self.get_field_type_display()} - {self.name}"


class Invoice(models.Model):
    """Invoice records generated from orders"""
    STATUS_CHOICES = [
        ('draft', 'Draft'),
        ('issued', 'Issued'),
        ('paid', 'Paid'),
        ('cancelled', 'Cancelled'),
    ]

    # Invoice identification
    invoice_number = models.CharField(max_length=32, unique=True, editable=False, db_index=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='draft')

    # Relationships
    branch = models.ForeignKey('Branch', on_delete=models.PROTECT, null=True, blank=True, related_name='invoices')
    order = models.ForeignKey(Order, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name='invoices')
    vehicle = models.ForeignKey(Vehicle, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices')

    # Invoice details
    invoice_date = models.DateField(default=timezone.now)
    due_date = models.DateField(blank=True, null=True)
    reference = models.CharField(max_length=128, blank=True, null=True, help_text="Customer PO or reference number")

    # Amounts
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_rate = models.DecimalField(max_digits=5, decimal_places=2, default=0, help_text="Tax percentage")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # Additional fields
    notes = models.TextField(blank=True, null=True)
    terms = models.TextField(blank=True, null=True)
    attended_by = models.CharField(max_length=128, blank=True, null=True)
    kind_attention = models.CharField(max_length=128, blank=True, null=True)
    remarks = models.TextField(blank=True, null=True)

    # Tracking
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='invoices_created')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-invoice_date', '-invoice_number']
        indexes = [
            models.Index(fields=['invoice_number'], name='idx_invoice_number'),
            models.Index(fields=['customer'], name='idx_invoice_customer'),
            models.Index(fields=['order'], name='idx_invoice_order'),
            models.Index(fields=['status'], name='idx_invoice_status'),
        ]

    def __str__(self) -> str:
        return f"Invoice {self.invoice_number} - {self.customer.full_name}"

    def calculate_totals(self):
        """Recalculate totals from line items"""
        self.subtotal = sum(item.line_total for item in self.line_items.all())
        self.tax_amount = self.subtotal * (self.tax_rate / 100) if self.tax_rate else 0
        self.total_amount = self.subtotal + self.tax_amount
        return self

    def generate_invoice_number(self):
        """Generate sequential invoice number"""
        if not self.invoice_number:
            from datetime import datetime
            today = datetime.now().date()
            count = Invoice.objects.filter(invoice_date__year=today.year).count() + 1
            self.invoice_number = f"INV-{today.year}-{count:05d}"
        return self.invoice_number


class InvoiceLineItem(models.Model):
    """Line items in an invoice"""
    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE, related_name='line_items')

    # Item details
    description = models.CharField(max_length=255)
    item_type = models.CharField(
        max_length=16,
        choices=[('product', 'Product'), ('service', 'Service'), ('custom', 'Custom')],
        default='custom'
    )

    # Reference to inventory item (optional)
    inventory_item = models.ForeignKey(InventoryItem, on_delete=models.SET_NULL, null=True, blank=True)

    # Quantities and pricing
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    unit = models.CharField(max_length=16, blank=True, null=True, help_text="e.g., 'PCS', 'UNT', 'HR'")
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)

    # Calculated
    line_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['invoice', 'created_at']

    def save(self, *args, **kwargs):
        self.line_total = self.quantity * self.unit_price
        super().save(*args, **kwargs)
        # Recalculate invoice totals
        if self.invoice:
            self.invoice.calculate_totals().save()

    def __str__(self) -> str:
        return f"{self.description} x {self.quantity}"


class InvoicePayment(models.Model):
    """Payment information for invoices"""
    PAYMENT_METHOD_CHOICES = [
        ('cash', 'Cash'),
        ('cheque', 'Cheque'),
        ('bank_transfer', 'Bank Transfer'),
        ('card', 'Card'),
        ('mpesa', 'M-Pesa'),
        ('on_delivery', 'Cash on Delivery'),
        ('on_credit', 'On Credit'),
        ('other', 'Other'),
    ]

    invoice = models.OneToOneField(Invoice, on_delete=models.CASCADE, related_name='payment')

    # Payment details
    payment_method = models.CharField(max_length=32, choices=PAYMENT_METHOD_CHOICES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateField(blank=True, null=True)
    reference = models.CharField(max_length=128, blank=True, null=True, help_text="Cheque number, transaction ID, etc.")

    # Additional notes
    notes = models.TextField(blank=True, null=True)

    # Tracking
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Invoice Payment'
        verbose_name_plural = 'Invoice Payments'

    def __str__(self) -> str:
        return f"{self.get_payment_method_display()} - {self.amount}"
