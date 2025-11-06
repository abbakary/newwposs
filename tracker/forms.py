import os
import re
import random
import json
import os
from django import forms
from django.contrib.auth.models import User, Group
from .models import Customer, Order, Vehicle, InventoryItem, Profile, InventoryAdjustment, Branch, ServiceType, ServiceAddon, Invoice, InvoiceLineItem, InvoicePayment


class InventoryItemForm(forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = "__all__"
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter full name'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+256 XXX XXX XXX'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'email@example.com'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Enter address'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'organization_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Organization name'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tax number/TIN'}),
            'personal_subtype': forms.Select(attrs={'class': 'form-select'}),
            'current_status': forms.Select(attrs={'class': 'form-select'}),
        }

    def clean(self):
        cleaned = super().clean()
        t = cleaned.get("customer_type")
        if t in {"government","ngo","company"}:
            if not cleaned.get("organization_name"):
                self.add_error("organization_name","Required for organizational customers")
            if not cleaned.get("tax_number"):
                self.add_error("tax_number","Required for organizational customers")
        elif t == "personal":
            if not cleaned.get("personal_subtype"):
                self.add_error("personal_subtype","Please specify if you are the owner or driver")
        return cleaned

class CustomerBasicForm(forms.Form):
    """Step 1: Basic customer information - used for quick customer creation"""
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter customer full name',
            'required': True
        })
    )
    phone = forms.CharField(
        max_length=20,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+255 XXX XXX XXX or 0X XXX XXX XXX',
            'required': True,
            'pattern': '^(\+255\s?\d{3}\s?\d{3}\s?\d{3}|0[67]\d{2}\s?\d{3}\s?\d{3})$',
            'title': 'Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX',
            'maxlength': '13'
        })
    )

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        # Tanzania format: +255 XXX XXX XXX or 0X XXX XXX XXX
        intl = re.compile(r'^\+255\s?\d{3}\s?\d{3}\s?\d{3}$')
        local = re.compile(r'^0[67]\d{2}\s?\d{3}\s?\d{3}$')
        if not (intl.match(value) or local.match(value)):
            raise forms.ValidationError('Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX')
        return value

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@example.com (optional)'
        })
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter customer address (optional)'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Additional notes (optional)'
        })
    )

class CustomerStep1Form(forms.Form):
    """Step 1: Basic customer information and type"""
    full_name = forms.CharField(
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter full name',
            'required': True
        })
    )
    phone = forms.CharField(
        max_length=25,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+255 XXX XXX XXX or 0X XXX XXX XXX',
            'required': True,
            'pattern': '^(\+255\s?\d{3}\s?\d{3}\s?\d{3}|0[67]\d{2}\s?\d{3}\s?\d{3})$',
            'title': 'Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX',
            'maxlength': '13'
        })
    )
    whatsapp = forms.CharField(
        required=False,
        max_length=25,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': '+255 XXX XXX XXX (if different from phone)',
            'pattern': '^(\+255\s?\d{3}\s?\d{3}\s?\d{3}|0[67]\d{2}\s?\d{3}\s?\d{3})$',
            'title': 'Enter a valid Tanzania WhatsApp number: +255 XXX XXX XXX or 0X XXX XXX XXX',
            'maxlength': '13'
        })
    )

    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        # Tanzania format: +255 XXX XXX XXX or 0X XXX XXX XXX
        intl = re.compile(r'^\+255\s?\d{3}\s?\d{3}\s?\d{3}$')
        local = re.compile(r'^0[67]\d{2}\s?\d{3}\s?\d{3}$')
        if not (intl.match(value) or local.match(value)):
            raise forms.ValidationError('Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX')
        return value
    
    def clean_whatsapp(self):
        value = (self.cleaned_data.get('whatsapp') or '').strip()
        if value:
            # Tanzania format: +255 XXX XXX XXX or 0X XXX XXX XXX
            intl = re.compile(r'^\+255\s?\d{3}\s?\d{3}\s?\d{3}$')
            local = re.compile(r'^0[67]\d{2}\s?\d{3}\s?\d{3}$')
            if not (intl.match(value) or local.match(value)):
                raise forms.ValidationError('Enter a valid Tanzania WhatsApp number: +255 XXX XXX XXX or 0X XXX XXX XXX')
        return value or None

    email = forms.EmailField(
        required=False,
        widget=forms.EmailInput(attrs={
            'class': 'form-control',
            'placeholder': 'email@example.com'
        })
    )
    address = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Enter address'
        })
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Additional notes'
        })
    )
    
    # Customer type fields
    customer_type = forms.ChoiceField(
        choices=Customer.TYPE_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select', 'required': True})
    )
    organization_name = forms.CharField(
        required=False,
        max_length=255,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Organization/Company name'
        })
    )
    tax_number = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Tax number/TIN'
        })
    )
    personal_subtype = forms.ChoiceField(
        choices=[('', 'Select...')] + Customer.PERSONAL_SUBTYPE,
        required=False,
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            choices = list(self.fields['customer_type'].choices)
        except Exception:
            choices = []
        if choices and (not choices[0] or choices[0][0] != ''):
            self.fields['customer_type'].choices = [('', 'Select customer type')] + choices
        self.fields['customer_type'].initial = ''

    def clean(self):
        cleaned = super().clean()
        customer_type = cleaned.get('customer_type')
        
        # Field-level requirements based on customer type
        if customer_type in ['government', 'ngo', 'company']:
            if not cleaned.get('organization_name'):
                self.add_error('organization_name', 'Organization name is required for this customer type')
            if not cleaned.get('tax_number'):
                self.add_error('tax_number', 'Tax number is required for this customer type')
        elif customer_type == 'personal':
            if not cleaned.get('personal_subtype'):
                self.add_error('personal_subtype', 'Please specify if you are the owner or driver')
        
        # Duplicate checks (exact match) scoped to current branch when available.
        # Creation flow also performs branch-scoped duplicate checks in the view.
        try:
            from .models import Customer
            branch = getattr(getattr(self, 'instance', None), 'branch', None)
            if not branch:
                return cleaned
            full_name = (cleaned.get('full_name') or '').strip()
            phone = (cleaned.get('phone') or '').strip()
            org = cleaned.get('organization_name')
            tax = cleaned.get('tax_number')
            qs = Customer.objects.filter(branch=branch)
            if customer_type == 'personal':
                if full_name and phone and qs.filter(full_name=full_name, phone=phone, customer_type='personal').exists():
                    self.add_error(None, 'A personal customer with this full name and phone already exists in this branch.')
            elif customer_type in ['government', 'ngo', 'company']:
                if full_name and phone and org and tax and qs.filter(
                    full_name=full_name,
                    phone=phone,
                    organization_name=org,
                    tax_number=tax,
                    customer_type=customer_type,
                ).exists():
                    self.add_error(None, 'An organizational customer with the same name, phone, organization and tax number already exists in this branch.')
        except Exception:
            pass

        return cleaned

class CustomerStep2Form(forms.Form):
    """Step 2: Service intent"""
    INTENT_CHOICES = [
        ("service", "I need a service"),
        ("sales", "I want to buy something"),
        ("inquiry", "Just an inquiry")
    ]
    
    intent = forms.ChoiceField(
        choices=INTENT_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

class CustomerStep3Form(forms.Form):
    """Step 3: Service Type Selection"""
    SERVICE_TYPE_CHOICES = [
        ("tire_sales", "Tire Sales"),
        ("car_service", "Car Service")
    ]

    service_type = forms.ChoiceField(
        choices=SERVICE_TYPE_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )

class CustomerStep4Form(forms.Form):
    """Step 4: Final confirmation and additional notes"""
    additional_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Any additional notes or special requests...'
        })
    )

class CustomerEditForm(forms.ModelForm):
    """Form for editing existing customers"""
    class Meta:
        model = Customer
        fields = ['full_name', 'phone', 'whatsapp', 'email', 'address', 'notes', 
                 'customer_type', 'organization_name', 'tax_number', 'personal_subtype']
        widgets = {
            'full_name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={
                'class': 'form-control', 
                'placeholder': '+255 XXX XXX XXX or 0X XXX XXX XXX',
                'pattern': '^(\+255\s?\d{3}\s?\d{3}\s?\d{3}|0[67]\d{2}\s?\d{3}\s?\d{3})$',
                'title': 'Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX',
                'maxlength': '16'
            }),
            'whatsapp': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': '+255 XXX XXX XXX (if different from phone)',
                'pattern': '^(\+255\s?\d{3}\s?\d{3}\s?\d{3}|0[67]\d{2}\s?\d{3}\s?\d{3})$',
                'title': 'Enter a valid Tanzania WhatsApp number: +255 XXX XXX XXX or 0X XXX XXX XXX',
                'maxlength': '16'
            }),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'address': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 2}),
            'customer_type': forms.Select(attrs={'class': 'form-select'}),
            'organization_name': forms.TextInput(attrs={'class': 'form-control'}),
            'tax_number': forms.TextInput(attrs={'class': 'form-control'}),
            'personal_subtype': forms.Select(attrs={'class': 'form-select'}),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Set required fields
        self.fields['full_name'].required = True
        self.fields['phone'].required = True
        self.fields['customer_type'].required = True
        
        # Update choices for customer type
        self.fields['customer_type'].choices = [('', 'Select customer type')] + Customer.TYPE_CHOICES
        
        # Update choices for personal subtype
        self.fields['personal_subtype'].choices = [('', 'Select...')] + Customer.PERSONAL_SUBTYPE
    
    def clean_phone(self):
        value = (self.cleaned_data.get('phone') or '').strip()
        # Tanzania format: +255 XXX XXX XXX or 0X XXX XXX XXX
        intl = re.compile(r'^\+255\s?\d{3}\s?\d{3}\s?\d{3}$')
        local = re.compile(r'^0[67]\d{2}\s?\d{3}\s?\d{3}$')
        if not (intl.match(value) or local.match(value)):
            raise forms.ValidationError('Enter a valid Tanzania phone number: +255 XXX XXX XXX or 0X XXX XXX XXX')
        return value
    
    def clean_whatsapp(self):
        value = (self.cleaned_data.get('whatsapp') or '').strip()
        if value:
            # Tanzania format: +255 XXX XXX XXX or 0X XXX XXX XXX
            intl = re.compile(r'^\+255\s?\d{3}\s?\d{3}\s?\d{3}$')
            local = re.compile(r'^0[67]\d{2}\s?\d{3}\s?\d{3}$')
            if not (intl.match(value) or local.match(value)):
                raise forms.ValidationError('Enter a valid Tanzania WhatsApp number: +255 XXX XXX XXX or 0X XXX XXX XXX')
        return value or None
    
    def clean(self):
        cleaned = super().clean()
        customer_type = cleaned.get('customer_type')
        
        # Field-level requirements based on customer type
        if customer_type in ['government', 'ngo', 'company']:
            if not cleaned.get('organization_name'):
                self.add_error('organization_name', 'Organization name is required for this customer type')
            if not cleaned.get('tax_number'):
                self.add_error('tax_number', 'Tax number is required for this customer type')
        elif customer_type == 'personal':
            if not cleaned.get('personal_subtype'):
                self.add_error('personal_subtype', 'Please specify if you are the owner or driver')
        
        # Duplicate checks (exact match) restricted to the same branch
        try:
            full_name = (cleaned.get('full_name') or '').strip()
            phone = (cleaned.get('phone') or '').strip()
            org = cleaned.get('organization_name')
            tax = cleaned.get('tax_number')
            from .models import Customer
            qs = Customer.objects.all()
            b = getattr(self.instance, 'branch', None)
            if b:
                qs = qs.filter(branch=b)
            if customer_type == 'personal':
                if full_name and phone and qs.filter(full_name=full_name, phone=phone, customer_type='personal').exists():
                    self.add_error(None, 'A personal customer with this full name and phone already exists in this branch.')
            elif customer_type in ['government', 'ngo', 'company']:
                if full_name and phone and org and tax and qs.filter(
                    full_name=full_name,
                    phone=phone,
                    organization_name=org,
                    tax_number=tax,
                    customer_type=customer_type,
                ).exists():
                    self.add_error(None, 'An organizational customer with the same name, phone, organization and tax number already exists in this branch.')
        except Exception:
            pass

        return cleaned

class BrandForm(forms.ModelForm):
    """Form for creating and updating brands"""
    class Meta:
        from .models import Brand
        model = Brand
        fields = ['name', 'description', 'website', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter brand name',
                'required': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Enter brand description (optional)'
            }),
            'website': forms.URLInput(attrs={
                'class': 'form-control',
                'placeholder': 'https://example.com (optional)'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch'
            })
        }
    
    def clean_name(self):
        """Ensure brand name is unique (case-insensitive)"""
        name = self.cleaned_data.get('name')
        if name:
            from .models import Brand
            qs = Brand.objects.filter(name__iexact=name)
            if self.instance and self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)
            if qs.exists():
                raise forms.ValidationError('A brand with this name already exists.')
        return name

class VehicleForm(forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ["plate_number", "make", "model", "vehicle_type"]
        widgets = {
            'plate_number': forms.TextInput(attrs={
                'class': 'form-control text-uppercase',
                'placeholder': 'e.g., UAH 123A'
            }),
            'make': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Toyota, Honda'
            }),
            'model': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Camry, Civic'
            }),
            'vehicle_type': forms.Select(attrs={'class': 'form-select'}, choices=[
                ('', 'Select vehicle type'),
                ('sedan', 'Sedan'),
                ('suv', 'SUV'),
                ('truck', 'Truck'),
                ('van', 'Van'),
                ('motorcycle', 'Motorcycle'),
                ('bus', 'Bus'),
                ('other', 'Other')
            ])
        }

class OrderForm(forms.ModelForm):
    # Choices will be populated dynamically from ServiceType in __init__
    service_selection = forms.MultipleChoiceField(
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input',
            'style': 'display: none;'
        })
    )
    
    # Choices will be populated dynamically from ServiceAddon in __init__
    tire_services = forms.MultipleChoiceField(
        choices=(),
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={
            'class': 'form-check-input',
            'style': 'display: none;'
        })
    )

    class Meta:
        model = Order
        fields = [
            "type",
            "vehicle",
            "priority",
            "description",
            "estimated_duration",
            "item_name",
            "brand",
            "quantity",
            "tire_type",
            "inquiry_type",
            "questions",
            "contact_preference",
            "follow_up_date",
        ]
        widgets = {
            "type": forms.Select(attrs={'class': 'form-select'}),
            "vehicle": forms.Select(attrs={'class': 'form-select'}),
            "priority": forms.Select(attrs={'class': 'form-select'}),
            "description": forms.Textarea(attrs={'class': 'form-control', 'rows': 4, 'placeholder': 'Describe the issue or service needed'}),
            "estimated_duration": forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            "item_name": forms.Select(attrs={'class': 'form-select'}),
            "brand": forms.Select(attrs={'class': 'form-select'}),
            "quantity": forms.NumberInput(attrs={'class': 'form-control', 'min': 1}),
            "tire_type": forms.Select(attrs={'class': 'form-select'}),
            "inquiry_type": forms.Select(attrs={'class': 'form-select'}),
            "questions": forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
            "contact_preference": forms.Select(attrs={'class': 'form-select'}),
            "follow_up_date": forms.DateInput(attrs={"type": "date", 'class': 'form-control'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Default estimated duration for service orders
        if not self.fields["estimated_duration"].initial:
            self.fields["estimated_duration"].initial = 50

        # Dynamic service types from DB, attach durations mapping for front-end
        try:
            svc_qs = ServiceType.objects.filter(is_active=True).order_by('name')
            svc_choices = [(s.name, s.name) for s in svc_qs]
            durations_map = {s.name: int(s.estimated_minutes or 0) for s in svc_qs}
            self.fields['service_selection'].choices = svc_choices
            # Attach mapping for JS to consume
            self.fields['service_selection'].widget.attrs['data-service-durations'] = json.dumps(durations_map)
        except Exception:
            # Keep empty choices on error
            self.fields['service_selection'].choices = []

        # Dynamic service addons from DB, attach durations mapping for front-end
        try:
            addon_qs = ServiceAddon.objects.filter(is_active=True).order_by('name')
            addon_choices = [(a.name, a.name) for a in addon_qs]
            addon_durations_map = {a.name: int(a.estimated_minutes or 0) for a in addon_qs}
            self.fields['tire_services'].choices = addon_choices
            # Attach mapping for JS to consume
            self.fields['tire_services'].widget.attrs['data-addon-durations'] = json.dumps(addon_durations_map)
        except Exception:
            # Keep empty choices on error
            self.fields['tire_services'].choices = []

        # Dynamic item choices with brand info from inventory
        try:
            # Get all active inventory items with their brands
            items = InventoryItem.objects.select_related('brand').filter(is_active=True).order_by('brand__name', 'name')
            
            # Create combined item choices (value = item_id, label = "Brand - Item Name")
            item_choices = [('', 'Select item')]
            item_brand_map = {}
            
            for item in items:
                if item.name:
                    brand_name = item.brand.name if item.brand else 'Unbranded'
                    label = f"{brand_name} - {item.name}"
                    item_choices.append((item.id, label))
                    item_brand_map[str(item.id)] = {
                        'name': item.name,
                        'brand': brand_name,
                        'quantity': item.quantity
                    }
            
            self.fields["item_name"].widget = forms.Select(
                attrs={
                    'class': 'form-select',
                    'data-items': json.dumps(item_brand_map)
                }, 
                choices=item_choices
            )
            
            # Hide brand field since it will be auto-filled
            self.fields["brand"].widget = forms.HiddenInput()
            
        except Exception as e:
            print(f"Error initializing OrderForm: {str(e)}")
            item_choices = [('', 'Select item')]
            self.fields["item_name"].widget = forms.Select(attrs={'class': 'form-select'}, choices=item_choices)
            self.fields["brand"].widget = forms.HiddenInput()
        
        # Tire type is fixed to 'New' and hidden
        self.fields["tire_type"].initial = "New"
        self.fields["tire_type"].widget = forms.HiddenInput()
        
        # Inquiry type choices
        self.fields["inquiry_type"].widget = forms.Select(
            attrs={'class': 'form-select'},
            choices=[
                ('', 'Select inquiry type'),
                ("Pricing", "Pricing"),
                ("Services", "Services"),
                ("Appointment Booking", "Appointment Booking"),
                ("General", "General")
            ]
        )
        
        # Contact preference choices
        self.fields["contact_preference"].widget = forms.Select(
            attrs={'class': 'form-select'},
            choices=[
                ('', 'Select preference'),
                ("phone", "Phone"),
                ("email", "Email"),
                ("whatsapp", "WhatsApp")
            ]
        )

    def clean(self):
        cleaned = super().clean()
        t = cleaned.get("type")
        
        if t == "sales":
            item_id = cleaned.get("item_name")
            if not item_id:
                self.add_error("item_name", "Item selection is required for Sales orders")
            else:
                # Get item details and set brand
                try:
                    item = InventoryItem.objects.select_related('brand').get(id=item_id)
                    cleaned["item_name"] = item.name
                    cleaned["brand"] = item.brand.name if item.brand else "Unbranded"
                except InventoryItem.DoesNotExist:
                    self.add_error("item_name", "Selected item not found")
                except Exception as e:
                    # Handle case where item exists but brand is missing
                    try:
                        item = InventoryItem.objects.get(id=item_id)
                        cleaned["item_name"] = item.name
                        cleaned["brand"] = "Unbranded"
                    except InventoryItem.DoesNotExist:
                        self.add_error("item_name", "Selected item not found")

            q = cleaned.get("quantity")
            if not q or q < 1:
                self.add_error("quantity", "Quantity must be at least 1")
            # Always set tire_type to New (hidden field)
            cleaned["tire_type"] = "New"
            
            # Calculate estimated duration from selected tire services
            tire_services = cleaned.get("tire_services") or []
            if tire_services:
                try:
                    addons = ServiceAddon.objects.filter(name__in=tire_services, is_active=True)
                    total_minutes = sum(int(a.estimated_minutes or 0) for a in addons)
                    # If there's already an estimated duration, add to it
                    current_duration = cleaned.get("estimated_duration") or 0
                    try:
                        current_duration = int(current_duration)
                    except (ValueError, TypeError):
                        current_duration = 0
                    cleaned["estimated_duration"] = current_duration + total_minutes
                except Exception:
                    pass

        elif t == "service":
            # Provide sensible defaults to avoid failing submission when user selects Service
            dur = cleaned.get("estimated_duration")
            try:
                dur = int(dur) if dur is not None and str(dur) != '' else None
            except (TypeError, ValueError):
                dur = None
            if not dur or dur <= 0:
                cleaned["estimated_duration"] = 50
            services = cleaned.get("service_selection") or []
            desc = (cleaned.get("description") or "").strip()
            if services:
                # Map selected codes/names to labels (name is used as label)
                try:
                    selected_labels = [str(s) for s in services]
                    desc_services = "Selected services: " + ", ".join(selected_labels)
                except Exception:
                    desc_services = "Selected services provided"
                desc = (desc + ("\n" if desc else "") + desc_services).strip()
            if not desc:
                desc = "Service order"
            cleaned["description"] = desc
            # Always set tire_type to New (hidden field)
            cleaned["tire_type"] = "New"
            
            # Calculate estimated duration from selected services
            if services:
                try:
                    service_types = ServiceType.objects.filter(name__in=services, is_active=True)
                    total_minutes = sum(int(s.estimated_minutes or 0) for s in service_types)
                    cleaned["estimated_duration"] = total_minutes
                except Exception:
                    pass

        elif t == "inquiry":
            if not cleaned.get("inquiry_type"):
                self.add_error("inquiry_type", "Inquiry type is required")
            if not cleaned.get("questions"):
                self.add_error("questions", "Please provide your questions")
                
        return cleaned

class CustomerSearchForm(forms.Form):
    """Form for searching existing customers"""
    search_query = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by name, phone, email, or customer code...',
            'id': 'customer-search'
        })
    )

class InquiryResponseForm(forms.Form):
    """Form for responding to customer inquiries"""
    response = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Enter your response to the customer...'
        })
    )
    
    follow_up_required = forms.BooleanField(
        required=False,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    
    follow_up_date = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={'type': 'date', 'class': 'form-control'})
    )

class BrandChoiceField(forms.ModelChoiceField):
    """Custom ModelChoiceField for brand selection with improved display"""
    def label_from_instance(self, obj):
        return obj.name

class InventoryItemForm(forms.ModelForm):
    """Form for creating and updating inventory items"""
    class Meta:
        model = InventoryItem
        fields = ["name", "brand", "description", "quantity", "price", "cost_price", 
                 "sku", "barcode", "reorder_level", "location", "is_active"]
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter item name',
                'autofocus': True
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control', 
                'rows': 2,
                'placeholder': 'Enter item description (optional)'
            }),
            'quantity': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': 0,
                'step': '1'
            }),
            'price': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': 0,
                'placeholder': '0.00'
            }),
            'cost_price': forms.NumberInput(attrs={
                'class': 'form-control', 
                'step': '0.01', 
                'min': 0,
                'placeholder': '0.00'
            }),
            'sku': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'SKU (auto-generated if blank)'
            }),
            'barcode': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Barcode (optional)'
            }),
            'reorder_level': forms.NumberInput(attrs={
                'class': 'form-control', 
                'min': 0,
                'step': '1'
            }),
            'location': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g., Aisle 5, Shelf B'
            }),
            'is_active': forms.CheckboxInput(attrs={
                'class': 'form-check-input',
                'role': 'switch'
            }),
        }
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # Set default quantity to 0 if not set
        if not self.instance.pk and not self.data.get('quantity'):
            self.fields['quantity'].initial = 0
        
        # Only show active brands in the dropdown
        from .models import Brand
        self.fields['brand'] = BrandChoiceField(
            queryset=Brand.objects.filter(is_active=True).order_by('name'),
            empty_label="Select a brand (optional)",
            widget=forms.Select(attrs={
                'class': 'form-select',
                'data-control': 'select2',
                'data-placeholder': 'Select a brand (optional)',
                'data-allow-clear': 'true',
                'data-tags': 'true',
                'data-token-separators': '[\",\"]',
                'data-create-option': 'true',
                'data-ajax--url': '/api/brands/create/'
            }),
            required=False
        )
        

        
        # Set default values for new items
        if not self.instance.pk:
            self.fields['is_active'].initial = True
            self.fields['reorder_level'].initial = 5
    
    def clean_sku(self):
        """Generate SKU if not provided"""
        sku = self.cleaned_data.get('sku')
        if sku is not None:
            sku = sku.strip()
        if not sku and self.cleaned_data.get('name') and self.cleaned_data.get('brand'):
            # Generate a simple SKU: first 3 chars of brand + first 3 chars of name + random 4 digits
            brand = str(self.cleaned_data['brand'])[:3].upper()
            name = ''.join([c for c in self.cleaned_data['name'] if c.isalnum()])[:3].upper()
            sku = f"{brand}-{name}-{random.randint(1000, 9999)}"
        return sku or ''
    
    def clean_price(self):
        """Ensure price is not negative"""
        price = self.cleaned_data.get('price', 0)
        if price < 0:
            raise forms.ValidationError("Price cannot be negative.")
        return price
    
    def clean_quantity(self):
        """Ensure quantity is not negative"""
        quantity = self.cleaned_data.get('quantity', 0)
        if quantity < 0:
            raise forms.ValidationError("Quantity cannot be negative.")
        return quantity

    def save(self, commit=True):
        # Generate SKU if not provided
        if not self.cleaned_data.get('sku') and self.cleaned_data.get('name') and self.cleaned_data.get('brand'):
            brand = str(self.cleaned_data['brand'])[:3].upper()
            name = ''.join([c for c in self.cleaned_data['name'] if c.isalnum()])[:3].upper()
            self.instance.sku = f"{brand}-{name}-{random.randint(1000, 9999)}"
        
        return super().save(commit)

class AdminUserCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Password", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    password2 = forms.CharField(label="Confirm Password", widget=forms.PasswordInput(attrs={'class': 'form-control'}))
    group_manager = forms.BooleanField(
        required=False,
        label="Manager role",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.filter(is_active=True).order_by('name'),
        required=False,
        label="Assigned Branch",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser"]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input', 'checked': True}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_superuser': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('password1')
        p2 = cleaned.get('password2')
        if p1 and p2 and p1 != p2:
            self.add_error('password2', 'Passwords do not match')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data['password1'])
        if commit:
            user.save()
        mgr, _ = Group.objects.get_or_create(name="manager")
        if self.cleaned_data.get('group_manager'):
            user.groups.add(mgr)
        # Ensure profile and assign branch
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.branch = self.cleaned_data.get('branch')
        profile.save()
        return user

class AdminUserForm(forms.ModelForm):
    group_manager = forms.BooleanField(
        required=False,
        label="Manager role",
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    new_password = forms.CharField(
        required=False,
        label="New Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    confirm_password = forms.CharField(
        required=False,
        label="Confirm New Password",
        widget=forms.PasswordInput(attrs={'class': 'form-control'})
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.filter(is_active=True).order_by('name'),
        required=False,
        label="Assigned Branch",
        widget=forms.Select(attrs={'class': 'form-select'})
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "is_active", "is_staff", "is_superuser"]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'readonly': True}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_staff': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
            'is_superuser': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            mgr = Group.objects.get(name="manager")
            self.fields['group_manager'].initial = self.instance and self.instance.pk and self.instance.groups.filter(id=mgr.id).exists()
        except Group.DoesNotExist:
            pass
        # Prefill branch from profile if exists
        try:
            if self.instance and self.instance.pk and hasattr(self.instance, 'profile'):
                self.fields['branch'].initial = getattr(self.instance.profile, 'branch', None)
        except Exception:
            pass

    def clean(self):
        cleaned = super().clean()
        p1 = cleaned.get('new_password')
        p2 = cleaned.get('confirm_password')
        if p1 or p2:
            if p1 != p2:
                self.add_error('confirm_password', 'Passwords do not match')
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        if commit:
            user.save()
        mgr, _ = Group.objects.get_or_create(name="manager")
        if self.cleaned_data.get('group_manager'):
            user.groups.add(mgr)
        else:
            user.groups.remove(mgr)
        # Assign branch on profile
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.branch = self.cleaned_data.get('branch')
        profile.save()
        p1 = self.cleaned_data.get('new_password')
        if p1:
            user.set_password(p1)
            user.save()
        return user

class InventoryAdjustmentForm(forms.ModelForm):
    """Form for making inventory adjustments (add/remove stock)"""
    item = forms.ModelChoiceField(
        queryset=InventoryItem.objects.filter(is_active=True).order_by('name'),
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True,
            'data-placeholder': 'Select an item',
            'data-allow-clear': 'true'
        })
    )
    
    adjustment_type = forms.ChoiceField(
        choices=InventoryAdjustment.ADJUSTMENT_TYPES,
        widget=forms.Select(attrs={
            'class': 'form-select',
            'required': True
        })
    )
    
    quantity = forms.IntegerField(
        min_value=1,
        widget=forms.NumberInput(attrs={
            'class': 'form-control',
            'placeholder': 'Enter quantity',
            'required': True
        })
    )
    
    reference = forms.CharField(
        required=False,
        max_length=64,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Reference number (optional)'
        })
    )
    
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 2,
            'placeholder': 'Reason for adjustment (optional)'
        })
    )
    
    class Meta:
        model = InventoryAdjustment
        fields = ['item', 'adjustment_type', 'quantity', 'reference', 'notes']
    
    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Set default adjustment type
        self.fields['adjustment_type'].initial = 'addition'
        
        # Set the queryset for the item field
        self.fields['item'].queryset = InventoryItem.objects.filter(is_active=True).order_by('name')
    
    def clean(self):
        cleaned_data = super().clean()
        item = cleaned_data.get('item')
        adjustment_type = cleaned_data.get('adjustment_type')
        quantity = cleaned_data.get('quantity', 0)
        
        # For removal or damage, check if enough stock is available
        if item and adjustment_type in ['removal', 'damage']:
            if quantity > item.quantity:
                self.add_error('quantity', f'Not enough stock. Only {item.quantity} available.')
        
        return cleaned_data
    
    def save(self, commit=True):
        instance = super().save(commit=False)
        
        # Set the user who made the adjustment
        if self.user:
            instance.adjusted_by = self.user
        
        # Calculate quantities
        instance.previous_quantity = instance.item.quantity
        
        # For removal or damage, make quantity negative
        if instance.adjustment_type in ['removal', 'damage']:
            instance.quantity = -abs(instance.quantity)
        
        # Calculate new quantity
        instance.new_quantity = instance.previous_quantity + instance.quantity
        
        if commit:
            # Save the adjustment
            instance.save()
            
            # Update the item's quantity
            instance.item.quantity = instance.new_quantity
            instance.item.save(update_fields=['quantity'])
        
        return instance


class SystemSettingsForm(forms.Form):
    company_name = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Company/Workshop name'})
    )
    default_priority = forms.ChoiceField(
        choices=[('low','Low'),('medium','Medium'),('high','High'),('urgent','Urgent')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )
    enable_unbranded_alias = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    allow_order_without_vehicle = forms.BooleanField(
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'})
    )
    sms_provider = forms.ChoiceField(
        choices=[('none','None'),('zapier','Zapier Webhook'),('twilio','Twilio')],
        widget=forms.Select(attrs={'class': 'form-select'})
    )

class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ['photo']
        widgets = {
            'photo': forms.ClearableFileInput(attrs={
                'class': 'form-control',
                'accept': 'image/*',
                'onchange': 'previewImage(this)'
            })
        }
    
    first_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'First name'
        })
    )
    last_name = forms.CharField(
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control', 
            'placeholder': 'Last name'
        })
    )
    
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        if user:
            self.fields['first_name'].initial = user.first_name
            self.fields['last_name'].initial = user.last_name
    
    def clean_photo(self):
        photo = self.cleaned_data.get('photo')
        if photo:
            # Validate file size (2MB max)
            max_size = 2 * 1024 * 1024
            if photo.size > max_size:
                raise forms.ValidationError('Image file too large (max 2MB)')
            
            # Validate file type
            valid_extensions = ['.jpg', '.jpeg', '.png', '.gif']
            ext = os.path.splitext(photo.name)[1].lower()
            if ext not in valid_extensions:
                raise forms.ValidationError('Unsupported file type. Please upload a valid image file.')
        return photo
    
    def save(self, user=None, commit=True):
        """Save profile and uploaded photo safely.
        - Update user's first/last name if provided
        - Save new photo first, then delete the old one to avoid file-handle issues
        """
        # Update user fields if user is provided
        if user is not None:
            user.first_name = self.cleaned_data.get('first_name', '')
            user.last_name = self.cleaned_data.get('last_name', '')
            user.save()

        # Prepare instance via ModelForm machinery
        profile = super(ProfileForm, self).save(commit=False)

        # Keep reference to old photo to delete later (only if changed)
        old_photo = None
        if profile.pk:
            try:
                old_photo = type(profile).objects.only('photo').get(pk=profile.pk).photo
            except type(profile).DoesNotExist:
                old_photo = None

        if commit:
            # Saving here will persist the new uploaded file if provided
            profile.save()
            # Delete old photo after successful save and only if it changed
            if 'photo' in self.changed_data and old_photo and old_photo.name and (
                not profile.photo or old_photo.name != profile.photo.name
            ):
                old_photo.delete(save=False)

        return profile


from django.db import IntegrityError

# Build default choices for customer type fields at import time, with safe fallback
try:
    from .models import Customer as _Customer
    CUSTOMER_TYPE_CHOICES = [('', '---')] + list(getattr(_Customer, 'TYPE_CHOICES', []))
    PERSONAL_SUBTYPE_CHOICES = [('', '---')] + list(getattr(_Customer, 'PERSONAL_SUBTYPE', []))
except Exception:
    CUSTOMER_TYPE_CHOICES = [('', '---')]
    PERSONAL_SUBTYPE_CHOICES = [('', '---')]

class InvoiceForm(forms.ModelForm):
    # Inline customer fields to allow creating or selecting a customer while creating an invoice
    existing_customer = forms.ModelChoiceField(queryset=None, required=False, widget=forms.Select(attrs={'class': 'form-select'}))
    customer_full_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer full name'}))
    customer_phone = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Phone number'}))
    customer_whatsapp = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'WhatsApp number (optional)'}))
    customer_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'Email (optional)'}))
    customer_address = forms.CharField(required=False, widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Address (optional)'}))
    customer_organization_name = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Organization (optional)'}))
    customer_tax_number = forms.CharField(required=False, widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Tax/ID number (optional)'}))
    customer_type = forms.ChoiceField(required=False, choices=CUSTOMER_TYPE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))
    customer_personal_subtype = forms.ChoiceField(required=False, choices=PERSONAL_SUBTYPE_CHOICES, widget=forms.Select(attrs={'class': 'form-select'}))

    class Meta:
        model = Invoice
        fields = ['reference', 'due_date', 'tax_rate', 'attended_by', 'kind_attention', 'remarks', 'notes', 'terms']
        widgets = {
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Customer PO or reference'}),
            'due_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'tax_rate': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0', 'max': '100'}),
            'attended_by': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Attended By'}),
            'kind_attention': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Kind Attention'}),
            'remarks': forms.Textarea(attrs={'class': 'form-control', 'rows': 2, 'placeholder': 'Remarks'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Additional notes'}),
            'terms': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Payment terms and conditions'}),
        }

    def __init__(self, *args, **kwargs):
        # Accept an optional user kwarg to scope existing_customer queryset to the user's branch
        user = kwargs.pop('user', None)
        super(InvoiceForm, self).__init__(*args, **kwargs)
        try:
            from .models import Customer
            from .utils import get_user_branch
            if user is not None:
                branch = get_user_branch(user)
                if branch:
                    self.fields['existing_customer'].queryset = Customer.objects.filter(branch=branch).order_by('full_name')
                else:
                    self.fields['existing_customer'].queryset = Customer.objects.none()
            else:
                self.fields['existing_customer'].queryset = Customer.objects.none()
        except Exception:
            # If importing models fails for any reason, ensure the field still renders as empty
            try:
                self.fields['existing_customer'].queryset = []
            except Exception:
                pass

    def clean(self):
        cleaned = super().clean()
        # Ensure that either an existing customer is chosen or at least a name is provided
        existing = cleaned.get('existing_customer')
        name = (cleaned.get('customer_full_name') or '').strip()
        phone = (cleaned.get('customer_phone') or '').strip()
        ctype = cleaned.get('customer_type')
        psub = cleaned.get('customer_personal_subtype')

        # Basic presence validation
        if not existing and not name:
            self.add_error('customer_full_name', 'Please select an existing customer or provide a customer name.')

        # If organizational customer, ensure org name and tax number are provided
        if ctype in {'government', 'ngo', 'company'}:
            org = (cleaned.get('customer_organization_name') or '').strip()
            tax = (cleaned.get('customer_tax_number') or '').strip()
            if not org:
                self.add_error('customer_organization_name', 'Organization name is required for organization customers')
            if not tax:
                self.add_error('customer_tax_number', 'Tax number is required for organization customers')

        # If personal, ensure personal_subtype is provided
        if ctype == 'personal' and not psub:
            self.add_error('customer_personal_subtype', 'Please specify personal subtype (owner or driver)')

        return cleaned


class InvoiceLineItemForm(forms.ModelForm):
    class Meta:
        model = InvoiceLineItem
        fields = ['description', 'item_type', 'inventory_item', 'quantity', 'unit', 'unit_price']
        widgets = {
            'description': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Item description'}),
            'item_type': forms.Select(attrs={'class': 'form-select'}),
            'inventory_item': forms.Select(attrs={'class': 'form-select'}),
            'quantity': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0.01'}),
            'unit': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g., PCS, UNT, HR'}),
            'unit_price': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
        }


class InvoicePaymentForm(forms.ModelForm):
    class Meta:
        model = InvoicePayment
        fields = ['payment_method', 'amount', 'payment_date', 'reference', 'notes']
        widgets = {
            'payment_method': forms.Select(attrs={'class': 'form-select'}),
            'amount': forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'min': '0'}),
            'payment_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'reference': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Cheque number, transaction ID, etc.'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Payment notes'}),
        }
