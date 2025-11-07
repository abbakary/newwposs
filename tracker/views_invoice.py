"""
Views for invoice creation, management, and printing.
"""

import json
import logging
from decimal import Decimal
from datetime import datetime

from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponse
from django.views.decorators.http import require_http_methods
from django.db import transaction

from .models import Invoice, InvoiceLineItem, InvoicePayment, Order, Customer, Vehicle, InventoryItem
from .forms import InvoiceForm, InvoiceLineItemForm, InvoicePaymentForm
from .utils import get_user_branch

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def api_search_started_orders(request):
    """
    API endpoint to search for started orders by vehicle plate number.
    Used for autocomplete/dropdown in invoice creation form.

    Query parameters:
    - plate: vehicle plate number (required)

    Returns JSON with list of available started orders
    """
    from django.http import JsonResponse
    from .services import OrderService

    plate = (request.GET.get('plate') or '').strip().upper()
    if not plate:
        return JsonResponse({'success': False, 'message': 'Plate number required', 'orders': []})

    try:
        user_branch = get_user_branch(request.user)
        orders = OrderService.find_all_started_orders_for_plate(user_branch, plate)

        orders_data = []
        for order in orders:
            orders_data.append({
                'id': order.id,
                'order_number': order.order_number or f"ORD{order.id}",
                'plate_number': order.vehicle.plate_number if order.vehicle else plate,
                'customer': {
                    'id': order.customer.id,
                    'name': order.customer.full_name,
                    'phone': order.customer.phone
                } if order.customer else None,
                'started_at': order.started_at.isoformat() if order.started_at else order.created_at.isoformat(),
                'type': order.type,
                'status': order.status
            })

        return JsonResponse({
            'success': True,
            'orders': orders_data,
            'count': len(orders_data)
        })
    except Exception as e:
        logger.warning(f"Error searching started orders by plate: {e}")
        return JsonResponse({'success': False, 'message': str(e), 'orders': []})


@login_required
def invoice_create(request, order_id=None):
    """Create a new invoice, optionally linked to an existing started order"""
    from .services import CustomerService, VehicleService, OrderService

    order = None
    customer = None
    vehicle = None
    started_orders = []
    plate_search = request.GET.get('plate', '').strip().upper()

    user_branch = get_user_branch(request.user)

    # If searching by plate, find all started orders for that plate
    if plate_search:
        started_orders = OrderService.find_all_started_orders_for_plate(user_branch, plate_search)

    # If order_id is provided, load that order
    if order_id:
        order = get_object_or_404(Order, pk=order_id, branch=user_branch)
        customer = order.customer
        vehicle = order.vehicle
        # Mark it so we know it's a linked started order
        plate_search = vehicle.plate_number if vehicle else ''

    if request.method == 'POST':
        try:
            form = InvoiceForm(request.POST, user=request.user)
        except TypeError:
            # Fallback for older code / forms that don't accept user kwarg
            form = InvoiceForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data

            # Check if user selected a started order to link to
            selected_order_id = cd.get('selected_order_id') or request.POST.get('selected_order_id')
            if selected_order_id and not order:
                try:
                    order = Order.objects.get(id=selected_order_id, branch=user_branch, status='created')
                except Order.DoesNotExist:
                    messages.error(request, 'Selected started order not found.')
                    return render(request, 'tracker/invoice_create.html', {
                        'form': form,
                        'order': order,
                        'customer': customer,
                        'vehicle': vehicle,
                        'started_orders': started_orders,
                        'plate_search': plate_search,
                    })

            # Resolve or create customer
            customer_obj = None
            try:
                if cd.get('existing_customer'):
                    customer_obj = cd.get('existing_customer')
                else:
                    name = (cd.get('customer_full_name') or '').strip()
                    phone = (cd.get('customer_phone') or '').strip()

                    if name and phone:
                        branch = user_branch
                        try:
                            customer_obj, _ = CustomerService.create_or_get_customer(
                                branch=branch,
                                full_name=name,
                                phone=phone,
                                whatsapp=(cd.get('customer_whatsapp') or '').strip() or None,
                                email=(cd.get('customer_email') or '').strip() or None,
                                address=(cd.get('customer_address') or '').strip() or None,
                                organization_name=(cd.get('customer_organization_name') or '').strip() or None,
                                tax_number=(cd.get('customer_tax_number') or '').strip() or None,
                                customer_type=cd.get('customer_type') or None,
                                personal_subtype=cd.get('customer_personal_subtype') or None,
                            )
                        except Exception as e:
                            logger.warning(f"Failed to create/get customer while creating invoice: {e}")
                            customer_obj = None
            except Exception as e:
                logger.warning(f"Failed to resolve or create customer while creating invoice: {e}")

            # Fallback to provided customer from order if none resolved
            if not customer_obj:
                customer_obj = customer

            # If no order was linked and we have a customer, create a new order for this invoice
            # But only if this is not a temporary customer
            if not order and customer_obj:
                # Check if this is a temporary customer
                is_temp_customer = (hasattr(customer_obj, 'full_name') and str(customer_obj.full_name).startswith('Plate ')) and \
                                   (hasattr(customer_obj, 'phone') and str(customer_obj.phone).startswith('PLATE_'))
                
                if not is_temp_customer:
                    # Get vehicle if available
                    vehicle_plate = request.POST.get('reference')
                    if vehicle_plate:
                        try:
                            vehicle = VehicleService.create_or_get_vehicle(
                                customer=customer_obj,
                                plate_number=vehicle_plate,
                                make='',
                                model='',
                                vehicle_type=''
                            )
                        except Exception as e:
                            logger.warning(f"Failed to create/get vehicle while creating invoice: {e}")
                            vehicle = None
                    else:
                        vehicle = None
                    
                    # Create a new order for this customer
                    try:
                        order_type = request.POST.get('order_type_fixed') or request.POST.get('order_type') or 'service'
                        order = OrderService.create_order(
                            customer=customer_obj,
                            order_type=order_type,
                            branch=user_branch,
                            vehicle=vehicle,
                            description=request.POST.get('order_description', ''),
                            estimated_duration=request.POST.get('estimated_duration')
                        )
                    except Exception as e:
                        logger.warning(f"Failed to create order while creating invoice: {e}")
                        order = None

            invoice = form.save(commit=False)
            invoice.branch = user_branch
            if order:
                invoice.order = order
            invoice.customer = customer_obj
            invoice.vehicle = vehicle
            invoice.created_by = request.user
            invoice.generate_invoice_number()
            # Ensure Terms & Conditions (NOTE) is prefilled if missing
            try:
                if not getattr(invoice, 'terms', None):
                    invoice.terms = (
                        "NOTE 1 : Payment in TSHS accepted at the prevailing rate on the date of payment. "
                        "2 : Proforma Invoice is Valid for 2 weeks from date of Proforma. "
                        "3 : Discount is Valid only for the above Quantity. "
                        "4 : Duty and VAT exemption documents to be submitted with the Purchase Order."
                    )
            except Exception:
                pass
            invoice.save()

            # If this invoice was created from a started order, update the order with finalized details
            try:
                if order:
                    # Use the new OrderService to update the started order with invoice details
                    order = OrderService.update_order_from_invoice(
                        order=order,
                        customer=customer_obj,
                        vehicle=vehicle,
                        description=request.POST.get('order_description') or order.description
                    )

                    # Also handle service selection/ETA if provided
                    sel = request.POST.get('service_selection')
                    est = request.POST.get('estimated_duration')
                    if sel or est:
                        if sel:
                            try:
                                names = json.loads(sel)
                            except Exception:
                                names = [s.strip() for s in str(sel).split(',') if s.strip()]
                            if names:
                                base_desc = order.description or ''
                                svc_text = ', '.join(names)
                                lines = [l for l in base_desc.split('\n') if not (l.strip().lower().startswith('services:') or l.strip().lower().startswith('add-ons:') or l.strip().lower().startswith('tire services:'))]
                                if order.type == 'sales':
                                    lines.append(f"Tire Services: {svc_text}")
                                else:
                                    lines.append(f"Services: {svc_text}")
                                order.description = '\n'.join([l for l in lines if l.strip()])
                        if est:
                            try:
                                order.estimated_duration = int(est)
                            except Exception:
                                pass
                        order.save()
            except Exception as e:
                logger.warning(f"Failed to update order with invoice details: {e}")

            messages.success(request, f'Invoice {invoice.invoice_number} created successfully.')
            return redirect('tracker:invoice_detail', pk=invoice.pk)
    else:
        initial = {}
        if order:
            # Auto-fill reference with vehicle plate if available, fallback to order.order_number
            if vehicle and getattr(vehicle, 'plate_number', None):
                initial['reference'] = vehicle.plate_number
            else:
                initial['reference'] = order.order_number
        try:
            form = InvoiceForm(user=request.user, initial=initial)
        except TypeError:
            form = InvoiceForm(initial=initial)

    return render(request, 'tracker/invoice_create.html', {
        'form': form,
        'order': order,
        'customer': customer,
        'vehicle': vehicle,
    })


@login_required
def invoice_detail(request, pk):
    """View invoice details and manage line items/payments"""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if request.method == 'POST':
        action = request.POST.get('action')
        
        if action == 'add_line_item':
            form = InvoiceLineItemForm(request.POST)
            if form.is_valid():
                line_item = form.save(commit=False)
                line_item.invoice = invoice
                line_item.save()
                messages.success(request, 'Line item added.')
                return redirect('tracker:invoice_detail', pk=invoice.pk)
        
        elif action == 'delete_line_item':
            item_id = request.POST.get('item_id')
            try:
                item = InvoiceLineItem.objects.get(id=item_id, invoice=invoice)
                item.delete()
                invoice.calculate_totals().save()
                messages.success(request, 'Line item deleted.')
            except InvoiceLineItem.DoesNotExist:
                messages.error(request, 'Line item not found.')
            return redirect('tracker:invoice_detail', pk=invoice.pk)
        
        elif action == 'update_payment':
            form = InvoicePaymentForm(request.POST)
            if form.is_valid():
                payment = form.save(commit=False)
                payment.invoice = invoice
                payment.save()
                messages.success(request, 'Payment information updated.')
                return redirect('tracker:invoice_detail', pk=invoice.pk)
        
        elif action == 'update_invoice':
            form = InvoiceForm(request.POST, instance=invoice)
            if form.is_valid():
                form.save()
                messages.success(request, 'Invoice updated.')
                return redirect('tracker:invoice_detail', pk=invoice.pk)
    
    line_item_form = InvoiceLineItemForm()
    payment_form = InvoicePaymentForm()
    invoice_form = InvoiceForm(instance=invoice)
    
    return render(request, 'tracker/invoice_detail.html', {
        'invoice': invoice,
        'line_item_form': line_item_form,
        'payment_form': payment_form,
        'invoice_form': invoice_form,
    })


@login_required
def invoice_list(request, order_id=None):
    """List invoices for an order or all invoices"""
    if order_id:
        invoices = Invoice.objects.filter(order_id=order_id)
        order = get_object_or_404(Order, pk=order_id)
        title = f'Invoices for Order {order.order_number}'
    else:
        invoices = Invoice.objects.all()
        order = None
        title = 'All Invoices'
    
    return render(request, 'tracker/invoice_list.html', {
        'invoices': invoices,
        'order': order,
        'title': title,
    })


@login_required
def invoice_print(request, pk):
    """Display invoice in print-friendly format"""
    invoice = get_object_or_404(Invoice, pk=pk)
    context = {
        'invoice': invoice,
    }
    return render(request, 'tracker/invoice_print.html', context)


@login_required
@require_http_methods(["GET","POST"])
def invoice_pdf(request, pk):
    """Generate and download invoice as PDF"""
    invoice = get_object_or_404(Invoice, pk=pk)

    try:
        from django.template.loader import render_to_string
        from weasyprint import HTML, CSS
        import io
        import os

        logo_left_path = os.path.join(os.path.dirname(__file__), '..', 'tracker', 'static', 'assets', 'images', 'logo', 'stm_logo.png')
        logo_right_path = os.path.join(os.path.dirname(__file__), '..', 'tracker', 'static', 'assets', 'images', 'logo', 'wecare.png')

        context = {
            'invoice': invoice,
            'logo_left_url': f'file://{os.path.abspath(logo_left_path)}',
            'logo_right_url': f'file://{os.path.abspath(logo_right_path)}',
        }

        html_string = render_to_string('tracker/invoice_print.html', context)
        html = HTML(string=html_string, base_url=request.build_absolute_uri('/'))
        pdf = html.write_pdf()

        response = HttpResponse(pdf, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="Invoice_{invoice.invoice_number}.pdf"'
        return response
    except ImportError:
        messages.error(request, 'PDF generation not available. Please install weasyprint.')
        return redirect('tracker:invoice_print', pk=pk)
    except Exception as e:
        logger.error(f"Error generating PDF for invoice {pk}: {e}")
        messages.error(request, 'Error generating PDF.')
        return redirect('tracker:invoice_print', pk=pk)


@login_required
@require_http_methods(["POST"])
def api_upload_and_extract_invoice(request):
    """
    API endpoint to upload an invoice file (PDF or image) and extract data using OCR.

    POST parameters:
    - invoice_file: File upload field with PDF or image

    Returns JSON with extracted invoice data:
    - customer_name
    - customer_phone
    - customer_address
    - reference
    - items (array with description, qty, unit, price)
    - subtotal
    - tax_amount
    - total_amount
    """
    try:
        if 'invoice_file' not in request.FILES:
            return JsonResponse({
                'success': False,
                'error': 'No file uploaded. Please select an invoice file (PDF or image).'
            }, status=400)

        uploaded_file = request.FILES['invoice_file']

        # Validate file size (max 10MB)
        max_size = 10 * 1024 * 1024
        if uploaded_file.size > max_size:
            return JsonResponse({
                'success': False,
                'error': 'File size exceeds 10MB limit.'
            }, status=400)

        # Validate file extension
        allowed_extensions = ['.pdf', '.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tiff']
        file_ext = uploaded_file.name.split('.')[-1].lower()
        if f'.{file_ext}' not in allowed_extensions:
            return JsonResponse({
                'success': False,
                'error': f'Unsupported file type. Allowed types: {", ".join(allowed_extensions)}'
            }, status=400)

        # Reset file pointer to beginning
        uploaded_file.seek(0)

        # Process the file using OCR
        from .utils.invoice_ocr import process_uploaded_invoice_file

        result = process_uploaded_invoice_file(uploaded_file)

        def _make_serializable(obj):
            from decimal import Decimal
            if isinstance(obj, dict):
                return {k: _make_serializable(v) for k, v in obj.items()}
            if isinstance(obj, list):
                return [_make_serializable(v) for v in obj]
            if isinstance(obj, Decimal):
                try:
                    return float(obj)
                except Exception:
                    return str(obj)
            return obj

        if result['success']:
            safe_data = _make_serializable(result.get('data', {}))
            return JsonResponse({
                'success': True,
                'message': 'Invoice processed successfully',
                'data': safe_data
            })
        else:
            return JsonResponse({
                'success': False,
                'error': result.get('error', 'Failed to extract data from invoice')
            }, status=400)

    except Exception as e:
        logger.error(f"Error in api_upload_and_extract_invoice: {e}", exc_info=True)
        return JsonResponse({
            'success': False,
            'error': f'Error processing invoice: {str(e)}'
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_create_invoice_from_extraction(request):
    """
    API endpoint to create an Invoice record from extracted document data (AJAX).
    Expects JSON body with keys: extraction_id, order_id, reference, due_date, tax_rate, attended_by, kind_attention, notes, terms
    Returns JSON: { success: True, invoice_id: <id> }
    """
    try:
        data = json.loads(request.body)
        extraction_id = data.get('extraction_id')
        order_id = data.get('order_id')
        reference = data.get('reference')
        due_date_str = data.get('due_date')
        tax_rate = data.get('tax_rate')
        attended_by = data.get('attended_by')
        kind_attention = data.get('kind_attention')
        notes = data.get('notes')
        terms = data.get('terms')

        user_branch = get_user_branch(request.user)

        # Validate order
        order = None
        if order_id:
            try:
                order = Order.objects.get(id=int(order_id), branch=user_branch)
            except Exception:
                return JsonResponse({'success': False, 'error': 'Order not found'}, status=404)

        # Create invoice instance
        invoice = Invoice()
        invoice.branch = user_branch
        if order:
            invoice.order = order
            # Prefer order's customer/vehicle when available
            invoice.customer = order.customer
            invoice.vehicle = order.vehicle
        # Fill fields from provided data
        if reference:
            invoice.reference = reference
        else:
            if order and order.vehicle and getattr(order.vehicle, 'plate_number', None):
                invoice.reference = order.vehicle.plate_number
            elif order:
                invoice.reference = order.order_number

        if due_date_str:
            try:
                # Accept YYYY-MM-DD or ISO formats
                invoice.due_date = datetime.fromisoformat(due_date_str).date()
            except Exception:
                try:
                    invoice.due_date = datetime.strptime(due_date_str, '%Y-%m-%d').date()
                except Exception:
                    pass

        try:
            invoice.tax_rate = Decimal(str(tax_rate)) if tax_rate is not None and str(tax_rate) != '' else None
        except Exception:
            invoice.tax_rate = None

        invoice.attended_by = attended_by or ''
        invoice.kind_attention = kind_attention or ''
        invoice.notes = notes or ''
        invoice.terms = terms or ''
        invoice.created_by = request.user
        invoice.generate_invoice_number()
        invoice.save()

        return JsonResponse({'success': True, 'invoice_id': invoice.id})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error creating invoice from extraction: {e}", exc_info=True)
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_inventory_for_invoice(request):
    """API endpoint to fetch inventory items for invoice line items"""
    try:
        items = InventoryItem.objects.select_related('brand').filter(is_active=True).order_by('brand__name', 'name')
        data = []
        for item in items:
            brand_name = item.brand.name if item.brand else 'Unbranded'
            data.append({
                'id': item.id,
                'name': item.name,
                'brand': brand_name,
                'quantity': item.quantity or 0,
                'price': float(item.price or 0),
            })
        return JsonResponse({'items': data})
    except Exception as e:
        logger.error(f"Error fetching inventory items: {e}")


@login_required
@require_http_methods(["GET"])
def api_recent_invoices(request):
    """Return JSON list of recent invoices for sidebar"""
    try:
        from .utils import get_user_branch
        from django.urls import reverse
        branch = get_user_branch(request.user)
        qs = Invoice.objects.select_related('customer').order_by('-invoice_date')
        if branch:
            qs = qs.filter(branch=branch)
        invoices = qs[:8]
        data = []
        for inv in invoices:
            try:
                detail = reverse('tracker:invoice_detail', kwargs={'pk': inv.id})
                prn = reverse('tracker:invoice_print', kwargs={'pk': inv.id})
                pdf = reverse('tracker:invoice_pdf', kwargs={'pk': inv.id})
            except Exception:
                detail = f"/invoices/{inv.id}/"
                prn = f"/invoices/{inv.id}/print/"
                pdf = f"/invoices/{inv.id}/pdf/"
            data.append({
                'id': inv.id,
                'invoice_number': inv.invoice_number,
                'customer_name': inv.customer.full_name if inv.customer else '',
                'total_amount': float(inv.total_amount or 0),
                'status': inv.status,
                'detail_url': detail,
                'print_url': prn,
                'pdf_url': pdf,
            })
        return JsonResponse({'invoices': data})
    except Exception as e:
        logger.error(f"Error fetching recent invoices: {e}")
        return JsonResponse({'invoices': []})


@login_required
@require_http_methods(["POST"])
def invoice_finalize(request, pk):
    """Finalize invoice and change status to issued"""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status == 'draft':
        if invoice.line_items.count() == 0:
            messages.error(request, 'Invoice must have at least one line item.')
            return redirect('tracker:invoice_detail', pk=pk)
        
        invoice.status = 'issued'
        invoice.save()
        messages.success(request, f'Invoice {invoice.invoice_number} finalized.')
    
    return redirect('tracker:invoice_detail', pk=pk)


@login_required
@require_http_methods(["POST"])
def invoice_cancel(request, pk):
    """Cancel an invoice"""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    if invoice.status != 'cancelled':
        invoice.status = 'cancelled'
        invoice.save()
        messages.success(request, f'Invoice {invoice.invoice_number} cancelled.')
    
    return redirect('tracker:invoice_detail', pk=pk)
