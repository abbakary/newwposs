"""
Centralized service for creating and managing customers, vehicles, and orders.
This ensures consistent deduplication, visit tracking, and code generation across all flows.
"""

import logging
from decimal import Decimal
from datetime import datetime
from typing import Optional, Dict, Tuple, Any

from django.db import transaction, IntegrityError
from django.utils import timezone
from django.contrib.auth.models import User

from tracker.models import Customer, Vehicle, Order, InventoryItem, ServiceType, ServiceAddon, Branch
from tracker.utils import normalize_phone

logger = logging.getLogger(__name__)


class CustomerService:
    """Service for managing customer creation with proper deduplication and visit tracking."""

    @staticmethod
    def find_customer_by_name_and_plate(
        branch: Optional[Branch],
        full_name: str,
        plate_number: str,
    ) -> Optional[Customer]:
        """
        Find an existing customer by composite identifier: (customer name + plate number) within a branch.
        Used for uploaded invoices to decide between existing vs new customers.
        Returns the matching Customer if found, otherwise None.
        """
        try:
            if not branch or not full_name or not plate_number:
                return None
            name = (full_name or "").strip()
            plate = (plate_number or "").strip().upper()
            if not name or not plate:
                return None
            from tracker.models import Vehicle
            vehicle = (
                Vehicle.objects.select_related("customer")
                .filter(
                    plate_number__iexact=plate,
                    customer__branch=branch,
                    customer__full_name__iexact=name,
                )
                .first()
            )
            return vehicle.customer if vehicle else None
        except Exception as e:
            logger.warning(f"Error finding customer by name+plate: {e}")
            return None

    @staticmethod
    def find_customer_by_name_only(
        branch: Optional[Branch],
        full_name: str,
    ) -> Optional[Customer]:
        """
        Find an existing customer by name only within a branch.
        Used as fallback when plate number is not available during extraction.
        Returns the first matching Customer if found, otherwise None.
        """
        try:
            if not branch or not full_name:
                return None
            name = (full_name or "").strip()
            if not name:
                return None
            from tracker.models import Customer as CustomerModel
            customer = (
                CustomerModel.objects.filter(
                    branch=branch,
                    full_name__iexact=name,
                )
                .first()
            )
            return customer
        except Exception as e:
            logger.warning(f"Error finding customer by name only: {e}")
            return None

    @staticmethod
    def find_duplicate_customer(
        branch: Optional[Branch],
        full_name: str,
        phone: str,
        organization_name: Optional[str] = None,
        tax_number: Optional[str] = None,
        customer_type: Optional[str] = None
    ) -> Optional[Customer]:
        """
        Find existing customer matching the given criteria.
        Primary match: branch + full_name + phone (normalized)
        Secondary match: organization_name and tax_number (only if provided AND stored)
        This allows for matching even when extracted data is incomplete.
        Returns the matching customer if found, None otherwise.
        """
        if not branch or not full_name or not phone:
            return None

        try:
            # Normalize phone for comparison
            normalized_phone = normalize_phone(phone)

            # Get all potential matches by name and branch
            candidates = Customer.objects.filter(
                branch=branch,
                full_name__iexact=full_name,
            )

            # Check each candidate for phone match (handling normalized numbers)
            for candidate in candidates:
                candidate_phone = normalize_phone(candidate.phone or '')

                # Primary match: phone (required, normalized)
                phone_match = normalized_phone == candidate_phone
                if not phone_match:
                    continue

                # Secondary match: organization_name and tax_number
                # Only require exact match if BOTH provided in the query
                # If either is missing in the query, don't require them to match
                if organization_name and tax_number:
                    org_match = organization_name == (candidate.organization_name or '')
                    tax_match = tax_number == (candidate.tax_number or '')
                    if not (org_match and tax_match):
                        continue
                elif organization_name:
                    # Only organization_name provided - must match
                    org_match = organization_name == (candidate.organization_name or '')
                    if not org_match:
                        continue
                elif tax_number:
                    # Only tax_number provided - must match
                    tax_match = tax_number == (candidate.tax_number or '')
                    if not tax_match:
                        continue
                # If neither organization_name nor tax_number provided, don't filter on them

                # If customer_type is specified, it must also match (optional)
                if customer_type and candidate.customer_type != customer_type:
                    continue

                # Found a match!
                return candidate

            return None
        except Exception as e:
            logger.warning(f"Error finding duplicate customer: {e}")
            return None

    @staticmethod
    def create_or_get_customer(
        branch: Optional[Branch],
        full_name: str,
        phone: str,
        email: Optional[str] = None,
        whatsapp: Optional[str] = None,
        address: Optional[str] = None,
        notes: Optional[str] = None,
        customer_type: Optional[str] = None,
        organization_name: Optional[str] = None,
        tax_number: Optional[str] = None,
        personal_subtype: Optional[str] = None,
        create_if_missing: bool = True
    ) -> Tuple[Customer, bool]:
        """
        Create or get a customer with proper deduplication.
        If customer exists, updates contact information (address, email, whatsapp).
        Phone numbers are normalized for comparison but stored as-is.

        Args:
            branch: User's branch
            full_name: Customer's full name (required)
            phone: Customer's phone number (required)
            email: Customer's email
            whatsapp: Customer's WhatsApp number
            address: Customer's address
            notes: Customer notes
            customer_type: Type of customer (personal, company, ngo, government)
            organization_name: Organization name (for non-personal customers)
            tax_number: Tax/TIN number (for non-personal customers)
            personal_subtype: Owner or Driver (for personal customers)
            create_if_missing: If False, only try to find existing customer

        Returns:
            Tuple of (Customer, created: bool)
                - Customer: The found or created customer
                - created: True if customer was just created, False if it already existed
        """
        full_name = (full_name or "").strip()
        phone = (phone or "").strip()
        email = (email or "").strip() or None
        whatsapp = (whatsapp or "").strip() or None
        address = (address or "").strip() or None
        notes = (notes or "").strip() or None
        organization_name = (organization_name or "").strip() or None
        tax_number = (tax_number or "").strip() or None

        if not full_name or not phone:
            raise ValueError("Customer full_name and phone are required")

        # Try to find existing customer
        existing = CustomerService.find_duplicate_customer(
            branch=branch,
            full_name=full_name,
            phone=phone,
            organization_name=organization_name,
            tax_number=tax_number,
            customer_type=customer_type
        )

        if existing:
            # Customer already exists - update contact info if provided
            updated = False
            if address and (not existing.address or existing.address != address):
                existing.address = address
                updated = True
            if email and (not existing.email or existing.email != email):
                existing.email = email
                updated = True
            if whatsapp and (not existing.whatsapp or existing.whatsapp != whatsapp):
                existing.whatsapp = whatsapp
                updated = True

            if updated:
                existing.save(update_fields=['address', 'email', 'whatsapp'])

            return existing, False

        if not create_if_missing:
            return None, False

        # Create new customer
        try:
            with transaction.atomic():
                customer = Customer.objects.create(
                    branch=branch,
                    full_name=full_name,
                    phone=phone,
                    email=email,
                    whatsapp=whatsapp,
                    address=address,
                    notes=notes,
                    customer_type=customer_type or "personal",
                    organization_name=organization_name,
                    tax_number=tax_number,
                    personal_subtype=personal_subtype or None,
                    arrival_time=timezone.now(),
                    current_status='arrived',
                    last_visit=timezone.now(),
                    total_visits=1,
                )
                return customer, True
        except IntegrityError as e:
            # If creation fails due to unique constraint, try to fetch existing
            logger.warning(f"IntegrityError creating customer: {e}")
            existing = CustomerService.find_duplicate_customer(
                branch=branch,
                full_name=full_name,
                phone=phone,
                organization_name=organization_name,
                tax_number=tax_number,
                customer_type=customer_type
            )
            if existing:
                # Update contact info for the found customer
                updated = False
                if address and (not existing.address or existing.address != address):
                    existing.address = address
                    updated = True
                if email and (not existing.email or existing.email != email):
                    existing.email = email
                    updated = True
                if whatsapp and (not existing.whatsapp or existing.whatsapp != whatsapp):
                    existing.whatsapp = whatsapp
                    updated = True

                if updated:
                    existing.save(update_fields=['address', 'email', 'whatsapp'])

                return existing, False
            raise

    @staticmethod
    def update_customer_visit(customer: Customer) -> None:
        """
        Update customer's visit tracking information.
        Call this whenever a customer interacts with the system (creates order, etc.)
        """
        if not customer:
            return

        try:
            now = timezone.now()
            customer.last_visit = now
            customer.total_visits = (customer.total_visits or 0) + 1
            customer.arrival_time = now
            customer.current_status = 'arrived'
            customer.save(update_fields=['last_visit', 'total_visits', 'arrival_time', 'current_status'])
        except Exception as e:
            logger.warning(f"Error updating customer visit: {e}")


class VehicleService:
    """Service for managing vehicle creation and association."""

    @staticmethod
    def create_or_get_vehicle(
        customer: Customer,
        plate_number: Optional[str] = None,
        make: Optional[str] = None,
        model: Optional[str] = None,
        vehicle_type: Optional[str] = None
    ) -> Optional[Vehicle]:
        """
        Create or get a vehicle for a customer.
        If plate_number is provided and exists for this customer, return existing vehicle.

        Args:
            customer: The customer who owns the vehicle
            plate_number: Vehicle plate number
            make: Vehicle make/brand
            model: Vehicle model
            vehicle_type: Type of vehicle

        Returns:
            The vehicle object or None if no plate number provided
        """
        if not customer or not plate_number:
            return None

        plate_number = (plate_number or "").strip().upper()
        if not plate_number:
            return None

        try:
            # Try to find existing vehicle for this customer
            vehicle = Vehicle.objects.filter(
                customer=customer,
                plate_number__iexact=plate_number
            ).first()

            if vehicle:
                # Update vehicle details if provided
                updated = False
                if make and not vehicle.make:
                    vehicle.make = make
                    updated = True
                if model and not vehicle.model:
                    vehicle.model = model
                    updated = True
                if vehicle_type and not vehicle.vehicle_type:
                    vehicle.vehicle_type = vehicle_type
                    updated = True
                if updated:
                    vehicle.save()
                return vehicle

            # Create new vehicle
            vehicle = Vehicle.objects.create(
                customer=customer,
                plate_number=plate_number,
                make=make or None,
                model=model or None,
                vehicle_type=vehicle_type or None
            )
            return vehicle
        except Exception as e:
            logger.warning(f"Error creating/getting vehicle: {e}")
            return None


class OrderService:
    """Service for managing order creation with proper customer and vehicle handling."""

    @staticmethod
    def find_started_order_by_plate(
        branch: Optional[Branch],
        plate_number: str,
        status: str = 'created'
    ) -> Optional[Order]:
        """
        Find a started order by vehicle plate number.
        Used to link invoice creation to existing started orders.

        Args:
            branch: User's branch
            plate_number: Vehicle plate number
            status: Order status to filter by (default: 'created')

        Returns:
            The Order if found, None otherwise
        """
        if not branch or not plate_number:
            return None

        plate_number = (plate_number or "").strip().upper()
        try:
            from tracker.models import Vehicle
            vehicle = Vehicle.objects.filter(
                plate_number__iexact=plate_number,
                customer__branch=branch
            ).first()

            if not vehicle:
                return None

            # Find the most recent started order for this vehicle
            order = Order.objects.filter(
                vehicle=vehicle,
                status=status
            ).order_by('-created_at').first()

            return order
        except Exception as e:
            logger.warning(f"Error finding started order by plate: {e}")
            return None

    @staticmethod
    def find_all_started_orders_for_plate(
        branch: Optional[Branch],
        plate_number: str
    ) -> list:
        """
        Find all started orders by vehicle plate number.
        Used to show user list of available orders to link to.

        Args:
            branch: User's branch
            plate_number: Vehicle plate number

        Returns:
            List of Order objects
        """
        if not branch or not plate_number:
            return []

        plate_number = (plate_number or "").strip().upper()
        try:
            from tracker.models import Vehicle
            vehicle = Vehicle.objects.filter(
                plate_number__iexact=plate_number,
                customer__branch=branch
            ).first()

            if not vehicle:
                return []

            # Find all started orders for this vehicle, newest first
            orders = Order.objects.filter(
                vehicle=vehicle,
                status='created'
            ).select_related('customer').order_by('-created_at')

            return list(orders)
        except Exception as e:
            logger.warning(f"Error finding started orders by plate: {e}")
            return []

    @staticmethod
    def update_order_from_invoice(
        order: Order,
        customer: Customer,
        vehicle: Optional[Vehicle] = None,
        description: Optional[str] = None,
        service_selection: Optional[list] = None,
        estimated_duration: Optional[int] = None,
        **kwargs
    ) -> Order:
        """
        Update a started order with finalized details from invoice creation.
        Used to sync customer/vehicle info from invoice back to the order.
        Also handles service selection and ETA calculation if provided.

        Args:
            order: The Order to update
            customer: The Customer (may be existing or newly created)
            vehicle: Optional Vehicle to associate
            description: Updated order description
            service_selection: Optional list of selected service names (for service orders)
            estimated_duration: Optional estimated duration in minutes (overrides auto-calculation)
            **kwargs: Additional fields to update

        Returns:
            The updated Order
        """
        if not order:
            return None

        try:
            with transaction.atomic():
                # Update customer if different
                if order.customer_id != customer.id:
                    order.customer = customer

                # Update vehicle if provided
                if vehicle and order.vehicle_id != vehicle.id:
                    order.vehicle = vehicle

                # Update description if provided
                if description:
                    order.description = description

                # Handle service selection and ETA calculation
                if service_selection and order.type == 'service':
                    # Update description with selected services
                    desc = order.description or ""
                    desc_services = "Selected services: " + ", ".join(service_selection)
                    if desc and not desc.lower().startswith('selected services:'):
                        desc = desc + "\n" + desc_services
                    else:
                        desc = desc_services
                    order.description = desc

                    # Calculate estimated duration from selected services
                    if not estimated_duration:
                        try:
                            from tracker.models import ServiceType
                            service_types = ServiceType.objects.filter(
                                name__in=service_selection,
                                is_active=True
                            )
                            total_minutes = sum(int(s.estimated_minutes or 0) for s in service_types)
                            estimated_duration = total_minutes or 50
                        except Exception:
                            estimated_duration = 50

                # Update any additional fields
                for field, value in kwargs.items():
                    if hasattr(order, field) and value is not None:
                        setattr(order, field, value)

                # Set estimated duration if calculated
                if estimated_duration:
                    order.estimated_duration = estimated_duration

                # Mark as in progress if still created (customer has arrived and service starts)
                if order.status == 'created':
                    order.started_at = order.started_at or timezone.now()

                order.save()

                # Update customer visit tracking
                CustomerService.update_customer_visit(customer)

                return order
        except Exception as e:
            logger.warning(f"Error updating order from invoice: {e}")
            raise

    @staticmethod
    def create_order(
        customer: Customer,
        order_type: str,
        branch: Optional[Branch] = None,
        vehicle: Optional[Vehicle] = None,
        description: Optional[str] = None,
        estimated_duration: Optional[int] = None,
        priority: Optional[str] = None,
        **kwargs
    ) -> Order:
        """
        Create an order with proper validation and defaults.

        Args:
            customer: The customer for this order
            order_type: 'service', 'sales', or 'inquiry'
            branch: User's branch
            vehicle: Associated vehicle (optional)
            description: Order description
            estimated_duration: Estimated duration in minutes
            priority: Order priority (low, medium, high, urgent)
            **kwargs: Additional order fields (item_name, quantity, tire_type, etc.)

        Returns:
            The created Order object
        """
        if not customer:
            raise ValueError("Customer is required")

        if order_type not in ['service', 'sales', 'inquiry']:
            raise ValueError(f"Invalid order type: {order_type}")

        try:
            with transaction.atomic():
                # Build order data
                order_data = {
                    'customer': customer,
                    'vehicle': vehicle,
                    'branch': branch,
                    'type': order_type,
                    'status': 'created',
                    'priority': priority or 'medium',
                    'description': description or f"{order_type.title()} Order",
                    'estimated_duration': estimated_duration,
                }

                # Add type-specific fields
                if order_type == 'sales':
                    order_data['item_name'] = kwargs.get('item_name')
                    order_data['brand'] = kwargs.get('brand')
                    order_data['quantity'] = kwargs.get('quantity')
                    order_data['tire_type'] = kwargs.get('tire_type', 'New')

                elif order_type == 'inquiry':
                    order_data['inquiry_type'] = kwargs.get('inquiry_type')
                    order_data['questions'] = kwargs.get('questions')
                    order_data['contact_preference'] = kwargs.get('contact_preference')
                    order_data['follow_up_date'] = kwargs.get('follow_up_date')

                # Create order
                order = Order.objects.create(**order_data)

                # Update customer visit tracking
                CustomerService.update_customer_visit(customer)

                return order
        except Exception as e:
            logger.error(f"Error creating order: {e}")
            raise

    @staticmethod
    def create_complete_order_flow(
        branch: Optional[Branch],
        customer_data: Dict[str, Any],
        vehicle_data: Optional[Dict[str, Any]] = None,
        order_data: Optional[Dict[str, Any]] = None
    ) -> Tuple[Customer, Optional[Vehicle], Optional[Order]]:
        """
        Complete flow: Create/get customer, create/get vehicle, and create order.
        This is the main entry point for all customer+vehicle+order creation workflows.

        Args:
            branch: User's branch
            customer_data: Dict with customer fields (full_name, phone, email, etc.)
            vehicle_data: Dict with vehicle fields (plate_number, make, model, vehicle_type)
            order_data: Dict with order fields (order_type, description, priority, etc.)

        Returns:
            Tuple of (customer, vehicle, order)
        """
        # Create or get customer
        customer, _ = CustomerService.create_or_get_customer(
            branch=branch,
            full_name=customer_data.get('full_name'),
            phone=customer_data.get('phone'),
            email=customer_data.get('email'),
            whatsapp=customer_data.get('whatsapp'),
            address=customer_data.get('address'),
            notes=customer_data.get('notes'),
            customer_type=customer_data.get('customer_type'),
            organization_name=customer_data.get('organization_name'),
            tax_number=customer_data.get('tax_number'),
            personal_subtype=customer_data.get('personal_subtype'),
        )

        # Create or get vehicle if vehicle data provided
        vehicle = None
        if vehicle_data and vehicle_data.get('plate_number'):
            vehicle = VehicleService.create_or_get_vehicle(
                customer=customer,
                plate_number=vehicle_data.get('plate_number'),
                make=vehicle_data.get('make'),
                model=vehicle_data.get('model'),
                vehicle_type=vehicle_data.get('vehicle_type')
            )

        # Create order if order data provided
        order = None
        if order_data and order_data.get('order_type'):
            order = OrderService.create_order(
                customer=customer,
                branch=branch,
                vehicle=vehicle,
                **order_data
            )

        return customer, vehicle, order
