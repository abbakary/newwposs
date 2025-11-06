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
def invoice_create(request, order_id=None):
    """Create a new invoice, optionally linked to an existing order"""
    order = None
    customer = None
    vehicle = None
    
    if order_id:
        order = get_object_or_404(Order, pk=order_id)
        customer = order.customer
        vehicle = order.vehicle
    
    if request.method == 'POST':
        try:
            form = InvoiceForm(request.POST, user=request.user)
        except TypeError:
            # Fallback for older code / forms that don't accept user kwarg
            form = InvoiceForm(request.POST)
        if form.is_valid():
            cd = form.cleaned_data
            # Resolve or create customer
            customer_obj = None
            try:
                if cd.get('existing_customer'):
                    customer_obj = cd.get('existing_customer')
                else:
                    name = (cd.get('customer_full_name') or '').strip()
                    phone = (cd.get('customer_phone') or '').strip()
                    whatsapp = (cd.get('customer_whatsapp') or '').strip()
                    email = (cd.get('customer_email') or '').strip()
                    address = (cd.get('customer_address') or '').strip()
                    org = (cd.get('customer_organization_name') or '').strip()
                    tax = (cd.get('customer_tax_number') or '').strip()
                    ctype = cd.get('customer_type') or None

                    if name:
                        from django.db import IntegrityError
                        from .utils import get_user_branch as _get_user_branch
                        branch = _get_user_branch(request.user)
                        personal_sub = cd.get('customer_personal_subtype') or None
                        try:
                            customer_obj = Customer.objects.create(
                                full_name=name,
                                phone=phone or '',
                                whatsapp=whatsapp or None,
                                email=email or None,
                                address=address or None,
                                organization_name=org or None,
                                tax_number=tax or None,
                                customer_type=ctype or None,
                                personal_subtype=personal_sub,
                                branch=branch,
                            )
                        except IntegrityError:
                            # If unique constraint prevents creation, try to fetch an existing record matching key fields
                            customer_obj = Customer.objects.filter(branch=branch, full_name__iexact=name, phone=phone).first()
                            if not customer_obj:
                                # As a last resort, attempt to get by name only
                                customer_obj = Customer.objects.filter(branch=branch, full_name__iexact=name).first()
            except Exception as e:
                logger.warning(f"Failed to resolve or create customer while creating invoice: {e}")

            # Fallback to provided customer from order if none resolved
            if not customer_obj:
                customer_obj = customer

            invoice = form.save(commit=False)
            invoice.branch = get_user_branch(request.user)
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
            # If this invoice was created from an order and service selection/ETA provided, update the order for tracking
            try:
                if order:
                    # Keep order's customer in sync with the customer chosen/created on the invoice
                    try:
                        if customer_obj and order.customer_id != getattr(customer_obj, 'id', None):
                            order.customer = customer_obj
                    except Exception:
                        pass
                    sel = request.POST.get('service_selection')
                    est = request.POST.get('estimated_duration')
                    if sel:
                        # expected JSON array from client
                        try:
                            names = json.loads(sel)
                        except Exception:
                            # fallback to comma-separated
                            names = [s.strip() for s in str(sel).split(',') if s.strip()]
                        if names:
                            # Append services/add-ons to order.description (not shown on invoice)
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
                logger.warning(f"Failed to update order with service selection/ETA: {e}")

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
    return render(request, 'tracker/invoice_print.html', {
        'invoice': invoice,
    })


@login_required
@require_http_methods(["GET","POST"])
def invoice_pdf(request, pk):
    """Generate and download invoice as PDF"""
    invoice = get_object_or_404(Invoice, pk=pk)
    
    try:
        from django.template.loader import render_to_string
        from weasyprint import HTML, CSS
        import io
        
        html_string = render_to_string('tracker/invoice_print.html', {'invoice': invoice})
        html = HTML(string=html_string)
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
