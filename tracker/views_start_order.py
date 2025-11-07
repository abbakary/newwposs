"""
Views for quick order start workflow and started orders management.
Allows users to quickly start an order with plate number, then complete the order.
"""

import json
import logging
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils import timezone
from django.db import transaction

from .models import Order, Customer, Vehicle, Branch, ServiceType, ServiceAddon, InventoryItem
from .utils import get_user_branch

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

    If an order with status='created' already exists for this plate, return that order instead of creating a duplicate.
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

        # Check for existing started order for this plate (status='created')
        # If one exists and hasn't been updated yet, return it instead of creating a duplicate
        existing_vehicle = Vehicle.objects.filter(plate_number__iexact=plate_number, customer__branch=user_branch).select_related('customer').first()
        if existing_vehicle:
            # Check if there's already a created order for this vehicle
            existing_order = Order.objects.filter(
                vehicle=existing_vehicle,
                status='created'
            ).order_by('-created_at').first()

            if existing_order and not use_existing and not existing_customer_id:
                # Return existing order instead of creating a duplicate
                return JsonResponse({
                    'success': True,
                    'order_id': existing_order.id,
                    'order_number': existing_order.order_number,
                    'plate_number': plate_number,
                    'started_at': existing_order.started_at.isoformat(),
                    'existing_order': True,
                    'message': 'Existing order found for this plate'
                }, status=200)

            if not use_existing and not existing_customer_id:
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

            # Create the order only if one doesn't already exist for this vehicle
            existing_order = Order.objects.filter(
                vehicle=vehicle,
                status='created'
            ).first()

            if existing_order:
                order = existing_order
            else:
                # Create new order
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

    # Get all started orders for this branch (status='created')
    # Note: We include all orders with status='created', including those with temporary customers
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
    # Include all started orders for accurate counts
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

        
        elif action == 'complete_order':
            # Mark order as completed
            order.status = 'completed'
            order.completed_at = timezone.now()
            order.save()
            
            return redirect('tracker:started_orders_dashboard')
    
    active_tab = request.GET.get('tab', 'overview')

    context = {
        'order': order,
        'customer': order.customer,
        'vehicle': order.vehicle,
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
def overrun_reports(request: HttpRequest):
    """Page showing reported order overruns and KPIs to help staff analyze delays."""
    from django.db.models import Count, Avg, F

    user_branch = get_user_branch(request.user)
    qs = Order.objects.all()
    if user_branch:
        qs = qs.filter(branch=user_branch)

    overruns = qs.filter(overrun_reason__isnull=False).order_by('-overrun_reported_at')
    total_overruns = overruns.count()

    # Average delay minutes: compute from estimated_duration and actual_duration where available
    delays = overruns.annotate(delay_minutes=(F('actual_duration') - F('estimated_duration'))).filter(delay_minutes__isnull=False)
    avg_delay = delays.aggregate(avg=Avg('delay_minutes'))['avg'] if delays.exists() else 0

    completed_late = overruns.filter(status='completed').count()

    # Top reasons
    top_reasons = overruns.values('overrun_reason').annotate(count=Count('id')).order_by('-count')[:10]

    # Recent overruns with computed delay minutes fallback
    recent = []
    for o in overruns[:50]:
        try:
            delay = None
            if o.actual_duration and o.estimated_duration:
                delay = max(0, int(o.actual_duration) - int(o.estimated_duration))
        except Exception:
            delay = None
        recent.append({
            'id': o.id,
            'order_number': o.order_number,
            'overrun_reason': o.overrun_reason,
            'overrun_reported_by': o.overrun_reported_by,
            'overrun_reported_at': o.overrun_reported_at,
            'delay_minutes': delay,
        })

    context = {
        'total_overruns': total_overruns,
        'avg_delay': avg_delay or 0,
        'completed_late': completed_late,
        'unique_reasons': top_reasons.count() if hasattr(top_reasons, 'count') else len(top_reasons),
        'top_reasons': top_reasons,
        'recent_overruns': recent,
    }

    return render(request, 'tracker/overrun_reports.html', context)




@login_required
@require_http_methods(["GET"])
def api_started_orders_kpis(request):
    """API endpoint to get KPI stats for started orders dashboard (for AJAX updates)."""
    try:
        user_branch = get_user_branch(request.user)

        # Include all started orders for accurate KPI counts
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
