"""
Views for quick order start workflow and started orders management.
Allows users to quickly start an order with plate number, then proceed with document extraction.
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction

from .models import Order, Customer, Vehicle, Branch, DocumentScan, DocumentExtraction, DocumentExtractionItem, ServiceType, ServiceAddon, InventoryItem
from .utils import get_user_branch
from .extraction_utils import process_invoice_extraction

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["POST"])
def api_start_order(request):
    """
    Start order endpoint enhanced:
    Accepts:
      - plate_number (required)
      - order_type (service|sales|inquiry)
      - use_existing_customer (optional boolean)
      - existing_customer_id (optional int)
      - service_selection (optional list of service names)
      - estimated_duration (optional int minutes)

    If plate exists in current branch and use_existing_customer is not provided, the endpoint will return existing_customer info
    so the frontend can ask the user whether to reuse existing customer or continue as new.
    """
    try:
        data = json.loads(request.body)
        plate_number = (data.get('plate_number') or '').strip().upper()
        order_type = data.get('order_type', 'service')
        use_existing = data.get('use_existing_customer', False)
        existing_customer_id = data.get('existing_customer_id')
        service_selection = data.get('service_selection') or []
        estimated_duration = data.get('estimated_duration')

        if not plate_number:
            return JsonResponse({'success': False, 'error': 'Vehicle plate number is required'}, status=400)

        if order_type not in ['service', 'sales', 'inquiry']:
            return JsonResponse({'success': False, 'error': 'Invalid order type'}, status=400)

        user_branch = get_user_branch(request.user)

        # Check for existing vehicle/customer in this branch
        existing_vehicle = Vehicle.objects.filter(plate_number__iexact=plate_number, customer__branch=user_branch).select_related('customer').first()
        if existing_vehicle and not use_existing and not existing_customer_id:
            # Inform frontend that a customer exists for this plate
            return JsonResponse({
                'success': True,
                'existing_customer': {
                    'id': existing_vehicle.customer.id,
                    'full_name': existing_vehicle.customer.full_name,
                    'phone': existing_vehicle.customer.phone,
                },
                'existing_vehicle': {
                    'id': existing_vehicle.id,
                    'plate': existing_vehicle.plate_number,
                    'make': existing_vehicle.make,
                    'model': existing_vehicle.model,
                }
            }, status=200)

        from .services import CustomerService, VehicleService

        with transaction.atomic():
            # Decide which customer to use
            if use_existing and existing_customer_id:
                customer = get_object_or_404(Customer, id=existing_customer_id, branch=user_branch)
                # Try to find a matching vehicle record for this plate under that customer
                vehicle = VehicleService.create_or_get_vehicle(
                    customer=customer,
                    plate_number=plate_number
                )
            else:
                # Create or get temporary customer record for this branch using the service
                # This avoids duplicate "Pending - T XXX" records
                try:
                    customer, _ = CustomerService.create_or_get_customer(
                        branch=user_branch,
                        full_name=f"Plate {plate_number}",
                        phone=f"PLATE_{plate_number}",  # Use plate as identifier instead of "TEMP_"
                        customer_type='personal',
                    )
                except Exception:
                    # Fallback if service fails
                    customer, _ = Customer.objects.get_or_create(
                        branch=user_branch,
                        phone=f"PLATE_{plate_number}",
                        defaults={'full_name': f'Plate {plate_number}', 'customer_type': 'personal'}
                    )

                vehicle = VehicleService.create_or_get_vehicle(
                    customer=customer,
                    plate_number=plate_number
                )

            # Calculate estimated duration from selected services if provided
            try:
                if service_selection and order_type == 'service':
                    svc_objs = ServiceType.objects.filter(name__in=service_selection, is_active=True)
                    from .models import ServiceAddon
                    add_objs = ServiceAddon.objects.filter(name__in=service_selection)
                    total_minutes = sum(int(s.estimated_minutes or 0) for s in svc_objs) + sum(int(a.estimated_minutes or 0) for a in add_objs)
                    if total_minutes:
                        estimated_duration = total_minutes
            except Exception:
                pass

            # Build description
            desc = f"Order started for {plate_number}"
            if service_selection:
                desc += ": " + ", ".join(service_selection)

            # Create the order
            order = Order.objects.create(
                customer=customer,
                vehicle=vehicle,
                branch=user_branch,
                type=order_type,
                status='created',
                started_at=timezone.now(),
                description=desc,
                priority='medium',
                estimated_duration=estimated_duration if estimated_duration else None,
            )

        return JsonResponse({'success': True, 'order_id': order.id, 'order_number': order.order_number, 'plate_number': plate_number, 'started_at': order.started_at.isoformat()}, status=201)

    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error starting order: {str(e)}")
        return JsonResponse({'success': False, 'error': f'Server error: {str(e)}'}, status=500)


@login_required
@require_http_methods(["POST"])
def api_check_plate(request):
    """Check if a plate number exists under the current branch and return customer/vehicle info."""
    try:
        data = json.loads(request.body)
        plate_number = (data.get('plate_number') or '').strip().upper()
        if not plate_number:
            return JsonResponse({'found': False})

        user_branch = get_user_branch(request.user)
        vehicle = Vehicle.objects.filter(plate_number__iexact=plate_number, customer__branch=user_branch).select_related('customer').first()
        if not vehicle:
            return JsonResponse({'found': False})

        return JsonResponse({'found': True, 'customer': {'id': vehicle.customer.id, 'full_name': vehicle.customer.full_name, 'phone': vehicle.customer.phone}, 'vehicle': {'id': vehicle.id, 'plate': vehicle.plate_number, 'make': vehicle.make, 'model': vehicle.model}})
    except Exception as e:
        logger.error(f"Error checking plate: {e}")
        return JsonResponse({'found': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["GET"])
def api_service_types(request):
    """Return list of active service types, addons, and inventory items for UI."""
    try:
        svc_qs = ServiceType.objects.filter(is_active=True).order_by('name')
        service_types = [{'name': s.name, 'estimated_minutes': s.estimated_minutes or 0} for s in svc_qs]

        addon_qs = ServiceAddon.objects.filter(is_active=True).order_by('name')
        service_addons = [{'name': a.name, 'estimated_minutes': a.estimated_minutes or 0} for a in addon_qs]

        items_qs = InventoryItem.objects.select_related('brand').filter(is_active=True).order_by('brand__name', 'name')
        inventory_items = []
        for item in items_qs:
            brand_name = item.brand.name if item.brand else 'Unbranded'
            inventory_items.append({
                'id': item.id,
                'name': item.name,
                'brand': brand_name,
                'quantity': item.quantity or 0,
                'price': float(item.price or 0)
            })

        logger.debug(f"api_service_types: Returning {len(inventory_items)} inventory items")
        return JsonResponse({
            'service_types': service_types,
            'service_addons': service_addons,
            'inventory_items': inventory_items
        })
    except Exception as e:
        logger.error(f"Error fetching service types: {e}", exc_info=True)
        return JsonResponse({
            'service_types': [],
            'service_addons': [],
            'inventory_items': []
        }, status=500)


@login_required
def started_orders_dashboard(request):
    """
    Display all started orders (status='created') for the current branch.
    Shows orders that have been initiated but not yet completed.
    Grouped by plate number for easy continuation.
    
    GET params:
    - status: Filter by order status (default: 'created')
    - sort_by: Sort orders by 'started_at', 'plate_number', 'order_type' (default: '-started_at')
    - search: Search by plate number or customer name
    """
    user_branch = get_user_branch(request.user)
    status_filter = request.GET.get('status', 'created')
    sort_by = request.GET.get('sort_by', '-started_at')
    search_query = request.GET.get('search', '').strip()
    
    # Get all started orders for this branch
    orders = Order.objects.filter(
        branch=user_branch,
        status=status_filter
    ).select_related('customer', 'vehicle')
    
    # Apply search filter
    if search_query:
        orders = orders.filter(
            vehicle__plate_number__icontains=search_query
        ) | orders.filter(
            customer__full_name__icontains=search_query
        )
    
    # Apply sorting
    if sort_by in ['-started_at', 'started_at', 'plate_number', 'type']:
        orders = orders.order_by(sort_by)
    else:
        orders = orders.order_by('-started_at')
    
    # Group orders by plate number
    orders_by_plate = {}
    for order in orders:
        plate = order.vehicle.plate_number if order.vehicle else 'Unknown'
        if plate not in orders_by_plate:
            orders_by_plate[plate] = []
        orders_by_plate[plate].append(order)
    
    # Calculate statistics
    total_started = Order.objects.filter(
        branch=user_branch,
        status='created'
    ).count()
    
    today_started = Order.objects.filter(
        branch=user_branch,
        status='created',
        started_at__date=timezone.now().date()
    ).count()
    
    # Calculate repeated vehicles today (vehicles with 2+ orders started today)
    from django.db.models import Count
    today_orders = Order.objects.filter(
        branch=user_branch,
        status='created',
        started_at__date=timezone.now().date(),
        vehicle__isnull=False
    ).values('vehicle__plate_number').annotate(order_count=Count('id')).filter(order_count__gte=2)
    repeated_vehicles_today = today_orders.count()
    
    context = {
        'orders': orders,
        'orders_by_plate': orders_by_plate,
        'total_started': total_started,
        'today_started': today_started,
        'repeated_vehicles_today': repeated_vehicles_today,
        'search_query': search_query,
        'status_filter': status_filter,
        'sort_by': sort_by,
        'title': 'Started Orders',
    }
    
    return render(request, 'tracker/started_orders_dashboard.html', context)


@login_required
def started_order_detail(request, order_id):
    """
    Show detail view for a started order with options to:
    - Upload/scan document for extraction
    - Manually enter customer details
    - Upload document and auto-populate
    - Edit and complete the order
    
    GET params:
    - tab: Active tab ('overview', 'customer', 'vehicle', 'document', 'order_details')
    """
    user_branch = get_user_branch(request.user)
    order = get_object_or_404(Order, id=order_id, branch=user_branch)
    
    if request.method == 'POST':
        # Handle form submissions for different sections
        action = request.POST.get('action')
        
        if action == 'update_customer':
            # Update customer details
            order.customer.full_name = request.POST.get('full_name', order.customer.full_name)
            order.customer.phone = request.POST.get('phone', order.customer.phone)
            order.customer.email = request.POST.get('email', order.customer.email) or None
            order.customer.address = request.POST.get('address', order.customer.address) or None
            order.customer.customer_type = request.POST.get('customer_type', order.customer.customer_type)
            personal_subtype = request.POST.get('personal_subtype', '').strip()
            if personal_subtype:
                order.customer.personal_subtype = personal_subtype
            order.customer.save()
            
        elif action == 'update_vehicle':
            # Update vehicle details
            if order.vehicle:
                order.vehicle.make = request.POST.get('make', order.vehicle.make)
                order.vehicle.model = request.POST.get('model', order.vehicle.model)
                order.vehicle.vehicle_type = request.POST.get('vehicle_type', order.vehicle.vehicle_type)
                order.vehicle.save()

        elif action == 'update_order_details':
            # Update selected services, add-ons, items, and estimated duration
            try:
                services = request.POST.getlist('services') or []
                est = request.POST.get('estimated_duration') or None
                item_id = request.POST.get('item_id') or None
                item_quantity = request.POST.get('item_quantity') or None

                # Handle item/brand update for sales orders
                if order.type == 'sales' and item_id:
                    try:
                        from .models import InventoryItem
                        item = InventoryItem.objects.select_related('brand').get(id=int(item_id))
                        order.item_name = item.name
                        order.brand = item.brand.name if item.brand else 'Unbranded'
                        if item_quantity:
                            try:
                                order.quantity = int(item_quantity)
                            except (ValueError, TypeError):
                                pass
                    except InventoryItem.DoesNotExist:
                        logger.warning(f"Inventory item {item_id} not found when updating order {order.id}")
                    except Exception as e:
                        logger.error(f"Error updating item for order {order.id}: {e}")

                # Handle services/add-ons update
                if services:
                    # Append services to description (simple storage)
                    svc_text = ', '.join(services)
                    base_desc = order.description or ''
                    # Remove previous Services/Add-ons lines if exists
                    lines = [l for l in base_desc.split('\n') if not (l.strip().lower().startswith('services:') or l.strip().lower().startswith('add-ons:') or l.strip().lower().startswith('tire services:'))]

                    # For sales orders, append as add-ons; for service orders, append as services
                    if order.type == 'sales':
                        lines.append(f"Tire Services: {svc_text}")
                    else:
                        lines.append(f"Services: {svc_text}")

                    order.description = '\n'.join([l for l in lines if l.strip()])

                # Update estimated duration
                if est:
                    try:
                        order.estimated_duration = int(est)
                    except Exception:
                        pass

                order.save()
                # Redirect to refresh page and show changes
                return redirect('tracker:started_order_detail', order_id=order.id)
            except Exception as e:
                logger.error(f"Error updating order details: {e}")

        elif action == 'upload_document':
            # Handle document upload and extraction
            if 'document' in request.FILES:
                doc_file = request.FILES['document']
                doc_type = request.POST.get('document_type', 'invoice')
                
                with transaction.atomic():
                    doc_scan = DocumentScan.objects.create(
                        order=order,
                        vehicle_plate=order.vehicle.plate_number if order.vehicle else '',
                        customer_phone=order.customer.phone,
                        file=doc_file,
                        document_type=doc_type,
                        uploaded_by=request.user,
                        file_name=doc_file.name,
                        file_size=doc_file.size,
                        file_mime_type=doc_file.content_type,
                        extraction_status='processing'
                    )
                    
                    # Process extraction
                    try:
                        extracted_data = process_invoice_extraction(doc_scan)
                        
                        if 'error' not in extracted_data:
                            # Persist extraction with invoice metadata
                            from decimal import Decimal, InvalidOperation
                            def _to_decimal_safe(v):
                                try:
                                    if v is None:
                                        return None
                                    if isinstance(v, (int, float, Decimal)):
                                        return Decimal(str(v))
                                    s = str(v).replace(',', '').strip()
                                    return Decimal(s)
                                except (InvalidOperation, Exception):
                                    return None
                            # Ensure JSON-safe payload in case extractor returns Decimals
                            def _to_json_safe(value):
                                if isinstance(value, Decimal):
                                    try:
                                        return float(value)
                                    except Exception:
                                        return str(value)
                                if isinstance(value, (list, tuple)):
                                    return [_to_json_safe(v) for v in value]
                                if isinstance(value, dict):
                                    return {k: _to_json_safe(v) for k, v in value.items()}
                                return value

                            json_safe_extracted = _to_json_safe(extracted_data)

                            extraction = DocumentExtraction.objects.create(
                                document=doc_scan,
                                extracted_customer_name=extracted_data.get('customer_name') or extracted_data.get('extracted_customer_name'),
                                extracted_customer_phone=extracted_data.get('customer_phone') or extracted_data.get('extracted_customer_phone'),
                                extracted_customer_email=extracted_data.get('customer_email') or extracted_data.get('extracted_customer_email'),
                                extracted_customer_address=extracted_data.get('address') or extracted_data.get('extracted_customer_address'),
                                extracted_vehicle_plate=extracted_data.get('plate_number') or extracted_data.get('extracted_vehicle_plate'),
                                extracted_order_description=extracted_data.get('service_description') or extracted_data.get('extracted_order_description'),
                                extracted_item_name=extracted_data.get('item_name'),
                                extracted_brand=extracted_data.get('brand'),
                                extracted_quantity=extracted_data.get('quantity') or extracted_data.get('extracted_quantity'),
                                extracted_amount=extracted_data.get('amount') or extracted_data.get('extracted_amount'),
                                code_no=extracted_data.get('code_no') or extracted_data.get('customer_code'),
                                reference=extracted_data.get('reference'),
                                net_value=_to_decimal_safe(extracted_data.get('net_value') or extracted_data.get('net')),
                                vat_amount=_to_decimal_safe(extracted_data.get('vat_amount') or extracted_data.get('vat')),
                                gross_value=_to_decimal_safe(extracted_data.get('gross_value') or extracted_data.get('gross')),
                                extracted_data_json=json_safe_extracted,
                                confidence_overall=extracted_data.get('confidence_overall', 80),
                            )

                            # Persist line items if present
                            try:
                                items = extracted_data.get('items') or extracted_data.get('structured_data', {}).get('items')
                                if items and isinstance(items, list):
                                    from decimal import Decimal
                                    for idx, it in enumerate(items, start=1):
                                        code = it.get('code') or it.get('item_code') or None
                                        desc = it.get('description') or it.get('desc') or it.get('description_full') or str(it.get('description') or '')
                                        qty = it.get('qty') or it.get('quantity')
                                        unit = it.get('unit') or it.get('type')
                                        rate = it.get('rate')
                                        value = it.get('value')
                                        # Normalize numeric fields
                                        def _to_decimal(v):
                                            try:
                                                if v is None:
                                                    return None
                                                if isinstance(v, (int, float, Decimal)):
                                                    return Decimal(str(v))
                                                v_clean = str(v).replace(',', '').strip()
                                                return Decimal(v_clean)
                                            except Exception:
                                                return None

                                        qty_d = _to_decimal(qty)
                                        rate_d = _to_decimal(rate)
                                        value_d = _to_decimal(value)

                                        DocumentExtractionItem.objects.create(
                                            extraction=extraction,
                                            line_no=idx,
                                            code=code,
                                            description=desc,
                                            qty=qty_d,
                                            unit=unit,
                                            rate=rate_d,
                                            value=value_d,
                                        )
                            except Exception as e:
                                logger.warning(f"Failed to save extracted items: {e}")

                            doc_scan.extraction_status = 'completed'
                            doc_scan.extracted_at = timezone.now()
                        else:
                            doc_scan.extraction_status = 'failed'
                            doc_scan.extraction_error = extracted_data.get('error')

                        doc_scan.save()
                    except Exception as e:
                        doc_scan.extraction_status = 'failed'
                        doc_scan.extraction_error = str(e)
                        doc_scan.save()
                        logger.error(f"Error extracting document: {str(e)}")
        
        elif action == 'complete_order':
            # Mark order as completed
            order.status = 'completed'
            order.completed_at = timezone.now()
            order.save()
            
            return redirect('tracker:started_orders_dashboard')
    
    # Get related documents and extractions
    documents = DocumentScan.objects.filter(order=order).order_by('-uploaded_at')
    extractions = DocumentExtraction.objects.filter(
        document__order=order
    ).order_by('-extracted_at')
    
    # Get latest extraction for preview
    latest_extraction = extractions.first()
    
    active_tab = request.GET.get('tab', 'overview')
    
    context = {
        'order': order,
        'customer': order.customer,
        'vehicle': order.vehicle,
        'documents': documents,
        'extractions': extractions,
        'latest_extraction': latest_extraction,
        'active_tab': active_tab,
        'title': f'Order {order.order_number}',
    }
    
    return render(request, 'tracker/started_order_detail.html', context)


@require_http_methods(["POST"])
@login_required
def api_record_overrun_reason(request, order_id):
    """Record an overrun/delay reason for an order (AJAX).
    Expects JSON: { "reason": "text" }
    Saves overrun_reason, overrun_reported_at, overrun_reported_by on the Order.
    Returns { success: true }
    """
    try:
        data = json.loads(request.body)
        reason = (data.get('reason') or '').strip()
        if not reason:
            return JsonResponse({'success': False, 'error': 'Reason is required'}, status=400)
        user_branch = get_user_branch(request.user)
        order = get_object_or_404(Order, id=order_id, branch=user_branch)
        order.overrun_reason = reason
        order.overrun_reported_at = timezone.now()
        order.overrun_reported_by = request.user
        order.save(update_fields=['overrun_reason','overrun_reported_at','overrun_reported_by'])
        return JsonResponse({'success': True})
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    except Exception as e:
        logger.error(f"Error recording overrun reason for order {order_id}: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@require_http_methods(["POST"])
def api_apply_extraction_to_order(request):
    """
    API endpoint to apply extracted data to an order.

    POST body:
    {
        "order_id": 123,
        "extraction_id": 456,
        "apply_fields": ["customer_name", "customer_phone", "service_description", "vehicle_plate"]
    }
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        extraction_id = data.get('extraction_id')
        apply_fields = data.get('apply_fields', [])

        user_branch = get_user_branch(request.user)
        order = get_object_or_404(Order, id=order_id, branch=user_branch)
        extraction = get_object_or_404(DocumentExtraction, id=extraction_id)

        with transaction.atomic():
            # Ensure customer exists; if not, create from extraction
            customer = order.customer
            if not customer:
                cust_name = extraction.extracted_customer_name or extraction.extracted_data_json.get('customer_name') or f'Customer {order.order_number}'
                cust_phone = extraction.extracted_customer_phone or extraction.extracted_data_json.get('customer_phone') or ''
                customer = Customer.objects.create(
                    branch=user_branch,
                    full_name=cust_name,
                    phone=cust_phone,
                    customer_type='personal'
                )
                order.customer = customer
            else:
                # Update existing customer fields
                if 'customer_name' in apply_fields and (extraction.extracted_customer_name or extraction.extracted_data_json.get('customer_name')):
                    customer.full_name = extraction.extracted_customer_name or extraction.extracted_data_json.get('customer_name')
                if 'customer_phone' in apply_fields and (extraction.extracted_customer_phone or extraction.extracted_data_json.get('customer_phone')):
                    customer.phone = extraction.extracted_customer_phone or extraction.extracted_data_json.get('customer_phone')
                if 'customer_email' in apply_fields and (extraction.extracted_customer_email or extraction.extracted_data_json.get('customer_email')):
                    customer.email = extraction.extracted_customer_email or extraction.extracted_data_json.get('customer_email')
                customer.save()

            # Ensure vehicle exists or match by plate
            vehicle = order.vehicle
            extracted_plate = (extraction.extracted_vehicle_plate or extraction.extracted_data_json.get('plate_number') or extraction.extracted_data_json.get('vehicle_plate') or '').strip()
            if 'vehicle_plate' in apply_fields and extracted_plate:
                # Normalize plate for lookup
                plate_norm = extracted_plate.upper()
                # Try to find existing vehicle in branch
                existing_vehicle = Vehicle.objects.filter(plate_number__iexact=plate_norm, customer__branch=user_branch).select_related('customer').first()
                if existing_vehicle:
                    vehicle = existing_vehicle
                    # attach to customer if different
                    if vehicle.customer != customer:
                        vehicle.customer = customer
                        vehicle.save()
                    order.vehicle = vehicle
                else:
                    # Create vehicle and attach
                    vehicle = Vehicle.objects.create(
                        customer=customer,
                        plate_number=plate_norm,
                        make=(extraction.extracted_vehicle_make or extraction.extracted_data_json.get('vehicle_make') or ''),
                        model=(extraction.extracted_vehicle_model or extraction.extracted_data_json.get('vehicle_model') or ''),
                        vehicle_type=(extraction.extracted_data_json.get('vehicle_type') or '')
                    )
                    order.vehicle = vehicle

            # Update vehicle fields if we have a vehicle object
            if order.vehicle and order.vehicle.id:
                v = order.vehicle
                if 'vehicle_make' in apply_fields and (extraction.extracted_vehicle_make or extraction.extracted_data_json.get('vehicle_make')):
                    v.make = extraction.extracted_vehicle_make or extraction.extracted_data_json.get('vehicle_make')
                if 'vehicle_model' in apply_fields and (extraction.extracted_vehicle_model or extraction.extracted_data_json.get('vehicle_model')):
                    v.model = extraction.extracted_vehicle_model or extraction.extracted_data_json.get('vehicle_model')
                v.save()

            # Apply order data fields
            if 'service_description' in apply_fields and (extraction.extracted_order_description or extraction.extracted_data_json.get('service_description')):
                order.description = extraction.extracted_order_description or extraction.extracted_data_json.get('service_description')
            if 'item_name' in apply_fields and (extraction.extracted_item_name or extraction.extracted_data_json.get('item_name')):
                order.item_name = extraction.extracted_item_name or extraction.extracted_data_json.get('item_name')
            if 'brand' in apply_fields and (extraction.extracted_brand or extraction.extracted_data_json.get('brand')):
                order.brand = extraction.extracted_brand or extraction.extracted_data_json.get('brand')
            if 'quantity' in apply_fields and (extraction.extracted_quantity or extraction.extracted_data_json.get('quantity')):
                try:
                    order.quantity = int(extraction.extracted_quantity or extraction.extracted_data_json.get('quantity'))
                except (ValueError, TypeError):
                    pass
            # Amount handling if needed - storing to order.net_value if field exists
            if 'amount' in apply_fields and (extraction.extracted_amount or extraction.extracted_data_json.get('amount')):
                try:
                    from decimal import Decimal
                    amt = extraction.extracted_amount or extraction.extracted_data_json.get('amount')
                    if hasattr(order, 'gross_value'):
                        order.gross_value = Decimal(str(amt)).quantize(Decimal('0.01'))
                    elif hasattr(order, 'amount'):
                        order.amount = Decimal(str(amt)).quantize(Decimal('0.01'))
                except Exception:
                    pass

            order.save()

        return JsonResponse({
            'success': True,
            'message': 'Extraction data applied to order successfully',
            'order_id': order.id
        })

    except Exception as e:
        logger.error(f"Error applying extraction: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["POST"])
def api_auto_fill_from_extraction(request):
    """
    API endpoint to auto-fill order fields based on latest extraction.
    Returns the extracted data for the client to preview before applying.
    
    POST body:
    {
        "order_id": 123
    }
    
    Response:
    {
        "success": true,
        "data": {
            "customer_name": "John Doe",
            "customer_phone": "+255123456789",
            "service_description": "Oil Change",
            "estimated_minutes": 30,
            ...
        }
    }
    """
    try:
        data = json.loads(request.body)
        order_id = data.get('order_id')
        
        user_branch = get_user_branch(request.user)
        order = get_object_or_404(Order, id=order_id, branch=user_branch)
        
        # Get latest extraction for this order
        extraction = DocumentExtraction.objects.filter(
            document__order=order
        ).order_by('-extracted_at').first()
        
        if not extraction:
            return JsonResponse({
                'success': False,
                'error': 'No extraction data found for this order'
            }, status=404)
        
        # Build response with extracted data
        response_data = {
            'customer_name': extraction.extracted_customer_name,
            'customer_phone': extraction.extracted_customer_phone,
            'customer_email': extraction.extracted_customer_email,
            'vehicle_plate': extraction.extracted_vehicle_plate,
            'vehicle_make': extraction.extracted_vehicle_make,
            'vehicle_model': extraction.extracted_vehicle_model,
            'service_description': extraction.extracted_order_description,
            'item_name': extraction.extracted_item_name,
            'brand': extraction.extracted_brand,
            'quantity': extraction.extracted_quantity,
            'amount': extraction.extracted_amount,
            'matched_service': extraction.extracted_data_json.get('matched_service'),
            'estimated_minutes': extraction.extracted_data_json.get('estimated_minutes'),
        }
        
        # Remove None/empty values
        response_data = {k: v for k, v in response_data.items() if v}
        
        return JsonResponse({
            'success': True,
            'data': response_data,
            'extraction_id': extraction.id,
            'confidence': extraction.confidence_overall,
        })
    
    except Exception as e:
        logger.error(f"Error auto-filling from extraction: {str(e)}")
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


@login_required
@require_http_methods(["GET"])
def api_started_orders_kpis(request):
    """API endpoint to get KPI stats for started orders dashboard (for AJAX updates)."""
    try:
        user_branch = get_user_branch(request.user)
        
        total_started = Order.objects.filter(
            branch=user_branch,
            status='created'
        ).count()
        
        today_started = Order.objects.filter(
            branch=user_branch,
            status='created',
            started_at__date=timezone.now().date()
        ).count()
        
        # Calculate repeated vehicles today (vehicles with 2+ orders started today)
        from django.db.models import Count
        today_orders = Order.objects.filter(
            branch=user_branch,
            status='created',
            started_at__date=timezone.now().date(),
            vehicle__isnull=False
        ).values('vehicle__plate_number').annotate(order_count=Count('id')).filter(order_count__gte=2)
        repeated_vehicles_today = today_orders.count()
        
        return JsonResponse({
            'success': True,
            'total_started': total_started,
            'today_started': today_started,
            'repeated_vehicles_today': repeated_vehicles_today
        })
    except Exception as e:
        logger.error(f"Error fetching started orders KPIs: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=500)
