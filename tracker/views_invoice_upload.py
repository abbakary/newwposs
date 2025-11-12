"""
Invoice upload and extraction endpoints.
Handles two-step process: extract preview → create/update records
"""

import json
import logging
from decimal import Decimal
from datetime import datetime
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction

from .models import Order, Customer, Vehicle, Invoice, InvoiceLineItem, InvoicePayment, Branch
from .utils import get_user_branch
from .services import OrderService, CustomerService, VehicleService

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def api_extract_invoice_preview(request):
    """
    Step 1: Extract invoice data from uploaded PDF for preview.
    Returns extracted customer, order, and payment information.
    Does NOT create any records yet.
    
    POST fields:
      - file: PDF file to extract
      - selected_order_id (optional): Started order ID to link to
      - plate (optional): Vehicle plate number
      
    Returns:
      - success: true/false
      - header: Customer and payment info {invoice_no, customer_name, address, date, subtotal, tax, total}
      - items: Line items [{description, qty, value}]
      - raw_text: Full extracted text for reference
      - message: Error/status message
    """
    user_branch = get_user_branch(request.user)
    
    # Validate file upload
    uploaded = request.FILES.get('file')
    if not uploaded:
        return JsonResponse({
            'success': False,
            'message': 'No file uploaded'
        })
    
    try:
        file_bytes = uploaded.read()
    except Exception as e:
        logger.error(f"Failed to read uploaded file: {e}")
        return JsonResponse({
            'success': False,
            'message': 'Failed to read uploaded file'
        })
    
    # Extract text from PDF
    try:
        from tracker.utils.pdf_text_extractor import extract_from_bytes as extract_pdf_text
        extracted = extract_pdf_text(file_bytes, uploaded.name)
    except Exception as e:
        logger.error(f"PDF extraction error: {e}")
        return JsonResponse({
            'success': False,
            'message': f'Failed to extract invoice data: {str(e)}',
            'error': str(e)
        })
    
    # If extraction failed - still return partial data for manual completion
    if not extracted.get('success'):
        logger.info(f"Extraction failed: {extracted.get('error')} - {extracted.get('message')}")
        return JsonResponse({
            'success': False,
            'message': extracted.get('message', 'Could not extract data from PDF. Please enter invoice details manually.'),
            'error': extracted.get('error'),
            'raw_text': extracted.get('raw_text', ''),
            'header': extracted.get('header', {}),
            'items': extracted.get('items', [])
        })
    
    # Return extracted preview data
    header = extracted.get('header') or {}
    items = extracted.get('items') or []

    return JsonResponse({
        'success': True,
        'message': 'Invoice data extracted successfully',
        'header': {
            'invoice_no': header.get('invoice_no'),
            'code_no': header.get('code_no'),
            'customer_name': header.get('customer_name'),
            'phone': header.get('phone'),
            'email': header.get('email'),
            'address': header.get('address'),
            'reference': header.get('reference'),
            'date': header.get('date'),
            'subtotal': float(header.get('subtotal') or 0),
            'tax': float(header.get('tax') or 0),
            'total': float(header.get('total') or 0),
            'payment_method': header.get('payment_method'),
            'delivery_terms': header.get('delivery_terms'),
            'remarks': header.get('remarks'),
            'attended_by': header.get('attended_by'),
            'kind_attention': header.get('kind_attention'),
            'seller_name': header.get('seller_name'),
            'seller_address': header.get('seller_address'),
            'seller_phone': header.get('seller_phone'),
            'seller_email': header.get('seller_email'),
            'seller_tax_id': header.get('seller_tax_id'),
            'seller_vat_reg': header.get('seller_vat_reg'),
        },
        'items': [
            {
                'description': item.get('description', ''),
                'qty': int(item.get('qty', 1)) if isinstance(item.get('qty'), (int, float)) else 1,
                'unit': item.get('unit'),
                'code': item.get('code'),
                'value': float(item.get('value') or 0)
            }
            for item in items
        ],
        'raw_text': extracted.get('raw_text', '')
    })


@login_required
@require_http_methods(["POST"])
def api_create_invoice_from_upload(request):
    """
    Step 2: Create/update customer, order, and invoice from extracted invoice data.
    This is called after user confirms extracted data.
    
    POST fields:
      - selected_order_id (optional): Existing started order to update
      - plate (optional): Vehicle plate number
      
      Customer fields:
      - customer_name: Customer full name
      - customer_phone: Customer phone number
      - customer_email (optional): Customer email
      - customer_address (optional): Customer address
      - customer_type: personal|company|ngo|government
      
      Invoice fields:
      - invoice_number: Invoice number from invoice
      - invoice_date: Invoice date
      - subtotal: Subtotal amount
      - tax_amount: Tax/VAT amount
      - total_amount: Total amount
      - notes (optional): Additional notes
      
      Line items (arrays):
      - item_description[]: Item description
      - item_qty[]: Item quantity
      - item_price[]: Item unit price
      
    Returns:
      - success: true/false
      - invoice_id: Created invoice ID
      - order_id: Created/updated order ID
      - customer_id: Created/updated customer ID
      - redirect_url: URL to view created invoice
    """
    user_branch = get_user_branch(request.user)
    
    try:
        with transaction.atomic():
            # Collect basic customer fields
            customer_name = request.POST.get('customer_name', '').strip()
            customer_phone = request.POST.get('customer_phone', '').strip()
            customer_email = request.POST.get('customer_email', '').strip() or None
            customer_address = request.POST.get('customer_address', '').strip() or None
            customer_type = request.POST.get('customer_type', 'personal')
            plate = (request.POST.get('plate') or '').strip().upper() or None

            # Require minimum customer info
            if not customer_name or not customer_phone:
                return JsonResponse({
                    'success': False,
                    'message': 'Customer name and phone are required'
                })

            org_name = (request.POST.get('organization_name') or '').strip() or None
            tax_num = (request.POST.get('tax_number') or '').strip() or None

            # Use centralized service which does proper deduplication
            # This method will:
            # 1. Check if customer exists by name+phone+organization+tax (with phone normalization)
            # 2. If found, update contact info and return existing customer
            # 3. If NOT found, create new customer
            try:
                customer_obj, created = CustomerService.create_or_get_customer(
                    branch=user_branch,
                    full_name=customer_name,
                    phone=customer_phone,
                    email=customer_email,
                    address=customer_address,
                    customer_type=customer_type,
                    organization_name=org_name,
                    tax_number=tax_num,
                    create_if_missing=True
                )

                if not customer_obj:
                    return JsonResponse({
                        'success': False,
                        'message': 'Failed to create or find customer'
                    })

                if created:
                    logger.info(f"Created new customer from invoice upload: {customer_obj.id} - {customer_name}")
                else:
                    logger.info(f"Found existing customer for invoice upload: {customer_obj.id} - {customer_name}")

            except Exception as e:
                logger.error(f"Error in customer creation/lookup for invoice: {e}")
                return JsonResponse({
                    'success': False,
                    'message': f'Error processing customer: {str(e)}'
                })

            # Get or create vehicle if plate provided
            vehicle = None
            if plate:
                try:
                    vehicle = VehicleService.create_or_get_vehicle(customer=customer_obj, plate_number=plate)
                    logger.info(f"Vehicle linked to customer {customer_obj.id}: {plate}")
                except Exception as e:
                    logger.warning(f"Failed to create/get vehicle for customer {customer_obj.id}: {e}")
                    vehicle = None

            # Get existing started order if provided
            selected_order_id = request.POST.get('selected_order_id')
            order = None
            if selected_order_id:
                try:
                    order = Order.objects.get(id=int(selected_order_id), branch=user_branch)
                    logger.info(f"Found existing order {order.id} to update")
                except Exception as e:
                    logger.warning(f"Could not find existing order {selected_order_id}: {e}")
                    pass

            # If no existing order, create new one
            if not order:
                try:
                    order = OrderService.create_order(
                        customer=customer_obj,
                        order_type='service',
                        branch=user_branch,
                        vehicle=vehicle,
                        description='Created from invoice upload'
                    )
                    logger.info(f"Created new order {order.id} for customer {customer_obj.id}")
                except Exception as e:
                    logger.error(f"Failed to create order for customer {customer_obj.id}: {e}")
                    return JsonResponse({
                        'success': False,
                        'message': f'Failed to create order: {str(e)}'
                    })
            else:
                # Update existing started order to ensure it's linked to the correct customer
                if order.customer_id != customer_obj.id:
                    order.customer = customer_obj
                    logger.info(f"Updated order {order.id} customer from {order.customer_id} to {customer_obj.id}")
                if vehicle and order.vehicle_id != vehicle.id:
                    order.vehicle = vehicle
                    logger.info(f"Updated order {order.id} vehicle to {vehicle.id}")
                order.save(update_fields=['customer', 'vehicle'] if vehicle else ['customer'])
            
            # Create or reuse invoice (enforce one invoice per order)
            inv = None
            if order:
                try:
                    inv = Invoice.objects.filter(order=order).first()
                except Exception:
                    inv = None
            if inv is None:
                inv = Invoice()
            inv.branch = user_branch
            inv.order = order
            inv.customer = customer_obj

            # Parse invoice date
            invoice_date_str = request.POST.get('invoice_date', '')
            try:
                inv.invoice_date = datetime.strptime(invoice_date_str, '%Y-%m-%d').date() if invoice_date_str else timezone.localdate()
            except Exception:
                inv.invoice_date = timezone.localdate()

            # Set invoice fields
            inv.reference = request.POST.get('invoice_number', '').strip() or f"INV-{timezone.now().strftime('%Y%m%d%H%M%S')}"

            # Collect all notes/remarks
            notes_parts = []
            if request.POST.get('notes', '').strip():
                notes_parts.append(request.POST.get('notes', '').strip())
            if request.POST.get('remarks', '').strip():
                notes_parts.append(request.POST.get('remarks', '').strip())
            if request.POST.get('delivery_terms', '').strip():
                notes_parts.append(f"Delivery: {request.POST.get('delivery_terms', '').strip()}")
            inv.notes = ' | '.join(notes_parts) if notes_parts else ''

            # Set additional fields
            inv.attended_by = request.POST.get('attended_by', '').strip() or None
            inv.kind_attention = request.POST.get('kind_attention', '').strip() or None
            inv.remarks = request.POST.get('remarks', '').strip() or None

            # Seller information (if provided via POST from extraction preview)
            inv.seller_name = (request.POST.get('seller_name') or '').strip() or None
            inv.seller_address = (request.POST.get('seller_address') or '').strip() or None
            inv.seller_phone = (request.POST.get('seller_phone') or '').strip() or None
            inv.seller_email = (request.POST.get('seller_email') or '').strip() or None
            inv.seller_tax_id = (request.POST.get('seller_tax_id') or '').strip() or None
            inv.seller_vat_reg = (request.POST.get('seller_vat_reg') or '').strip() or None

            # Parse amounts (support multiple possible field names)
            def _dec(val):
                s = str(val or '0')
                try:
                    return Decimal(s.replace(',', ''))
                except Exception:
                    return Decimal('0')

            subtotal = _dec(request.POST.get('subtotal') or request.POST.get('net_value'))
            tax_amount = _dec(request.POST.get('tax_amount') or request.POST.get('tax') or request.POST.get('vat'))
            total_amount = _dec(request.POST.get('total_amount') or request.POST.get('total') or request.POST.get('gross_value'))

            inv.subtotal = subtotal
            inv.tax_amount = tax_amount
            inv.total_amount = total_amount or (subtotal + tax_amount)
            inv.created_by = request.user

            if not getattr(inv, 'invoice_number', None):
                inv.generate_invoice_number()
            inv.save()

            # Save uploaded document if provided (optional in two-step flow)
            try:
                uploaded_file = request.FILES.get('file')
                if uploaded_file:
                    from django.core.files.base import ContentFile
                    try:
                        uploaded_file.seek(0)
                        bytes_ = uploaded_file.read()
                    except Exception:
                        bytes_ = None
                    if bytes_:
                        filename = uploaded_file.name or f"invoice_{inv.invoice_number}.pdf"
                        inv.document.save(filename, ContentFile(bytes_), save=True)
            except Exception:
                # Non-fatal
                pass

            # Create line items with extracted fields
            item_descriptions = request.POST.getlist('item_description[]')
            item_qtys = request.POST.getlist('item_qty[]')
            item_prices = request.POST.getlist('item_price[]')
            item_codes = request.POST.getlist('item_code[]')
            item_units = request.POST.getlist('item_unit[]')

            # Aggregate duplicates by code (fallback to description) before creating lines
            bucket = {}
            total_items = 0
            for idx, desc in enumerate(item_descriptions):
                if not desc or not desc.strip():
                    continue
                total_items += 1
                try:
                    code = item_codes[idx].strip() if idx < len(item_codes) and item_codes[idx] else ''
                    key = code or desc.strip().lower()
                    qty = int(item_qtys[idx] or 1) if idx < len(item_qtys) else 1
                    try:
                        price = Decimal(str(item_prices[idx] or '0').replace(',', '')) if idx < len(item_prices) else Decimal('0')
                    except Exception:
                        price = Decimal('0')
                    unit = item_units[idx].strip() if idx < len(item_units) and item_units[idx] else None
                    if key not in bucket:
                        bucket[key] = {
                            'code': code or None,
                            'description': desc.strip(),
                            'qty': 0,
                            'unit': unit,
                            'unit_price': price,
                        }
                    bucket[key]['qty'] += max(1, qty)
                    # Prefer first non-zero price; otherwise keep existing
                    if (bucket[key]['unit_price'] or Decimal('0')) == Decimal('0') and price:
                        bucket[key]['unit_price'] = price
                    if not bucket[key]['unit'] and unit:
                        bucket[key]['unit'] = unit
                except Exception as e:
                    logger.warning(f"Failed to stage line item aggregation: {e}")

            # Create line items without triggering per-item save() to avoid invoice total recalculation
            try:
                to_create = []
                for v in bucket.values():
                    qty = Decimal(str(v['qty'] or 1))
                    price = Decimal(str(v['unit_price'] or Decimal('0')))
                    line_total = qty * price
                    to_create.append(InvoiceLineItem(
                        invoice=inv,
                        code=v['code'],
                        description=v['description'],
                        quantity=qty,
                        unit=v['unit'],
                        unit_price=price,
                        tax_rate=Decimal('0'),
                        line_total=line_total,
                        tax_amount=Decimal('0'),
                    ))
                if to_create:
                    InvoiceLineItem.objects.bulk_create(to_create)
            except Exception as e:
                logger.warning(f"Failed to bulk create aggregated line items: {e}")

            # IMPORTANT: Preserve extracted Net, VAT, Gross values for uploaded invoices
            inv.subtotal = subtotal
            inv.tax_amount = tax_amount
            inv.total_amount = total_amount or (subtotal + tax_amount)
            inv.save(update_fields=['subtotal', 'tax_amount', 'total_amount'])

            # Create payment record if total > 0
            if inv.total_amount > 0:
                try:
                    payment = InvoicePayment()
                    payment.invoice = inv
                    payment.amount = Decimal('0')  # Default to unpaid (amount 0)

                    # Map extracted payment method or use form value or default
                    extracted_method = request.POST.get('payment_method', '').strip().lower() or 'on_delivery'
                    payment_method_map = {
                        'cash': 'cash',
                        'cheque': 'cheque',
                        'chq': 'cheque',
                        'bank': 'bank_transfer',
                        'transfer': 'bank_transfer',
                        'card': 'card',
                        'mpesa': 'mpesa',
                        'credit': 'on_credit',
                        'delivery': 'on_delivery',
                        'cod': 'on_delivery',
                        'on_delivery': 'on_delivery',
                    }

                    # Try to match the extracted method to a valid choice
                    payment.payment_method = 'on_delivery'  # Default
                    for key, val in payment_method_map.items():
                        if key in extracted_method:
                            payment.payment_method = val
                            break

                    payment.payment_date = None
                    payment.reference = None
                    payment.save()
                except Exception as e:
                    logger.warning(f"Failed to create payment record: {e}")
            
            # Update started order with invoice data
            try:
                order = OrderService.update_order_from_invoice(
                    order=order,
                    customer=customer_obj,
                    vehicle=vehicle,
                    description=order.description
                )
            except Exception as e:
                logger.warning(f"Failed to update order from invoice: {e}")
            
            # Response
            return JsonResponse({
                'success': True,
                'message': 'Invoice created and order updated successfully',
                'invoice_id': inv.id,
                'invoice_number': inv.invoice_number,
                'order_id': order.id,
                'customer_id': customer_obj.id,
                'redirect_url': f'/tracker/invoices/{inv.id}/'
            })
    
    except Exception as e:
        logger.error(f"Error creating invoice from upload: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'message': f'Error: {str(e)}'
        })
