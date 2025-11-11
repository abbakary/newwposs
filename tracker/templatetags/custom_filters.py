from django import template
from decimal import Decimal, DivisionByZero
from django.utils import timezone
from datetime import timedelta
import math
from typing import Union, Optional
from django import template

register = template.Library()

@register.filter(name='div')
def div(value, arg):
    """
    Divides the value by the argument.
    Usage: {{ value|div:arg }}
    Returns 0 if division by zero occurs.
    """
    try:
        if value is None or arg is None:
            return 0
        return float(value) / float(arg)
    except (ValueError, ZeroDivisionError, TypeError):
        return 0

@register.filter(name='mul')
def mul(value, arg):
    """
    Multiplies the value by the argument.
    Usage: {{ value|mul:arg }}
    Returns 0 if multiplication fails.
    """
    try:
        if value is None or arg is None:
            return 0
        return float(value) * float(arg)
    except (ValueError, TypeError):
        return 0

@register.filter(name='timesince_days')
def timesince_days(value):
    """
    Returns the number of days between the given date and now.
    Usage: {{ date|timesince_days }}
    """
    if not value:
        return 0
    
    try:
        now = timezone.now()
        if timezone.is_naive(value):
            value = timezone.make_aware(value)
        delta = now - value
        return delta.days
    except (TypeError, ValueError):
        return 0

@register.filter(name='replace')
def replace(value, arg):
    """
    Replaces all occurrences of a substring with another substring.
    Usage: {{ value|replace:"old:new" }}
    """
    if not value:
        return value

    try:
        if ':' in arg:
            old, new = arg.split(':', 1)
            return str(value).replace(old, new)
        return str(value).replace(arg, '')
    except (ValueError, AttributeError):
        return value

@register.filter(name='dict_get')
def dict_get(d, key):
    """
    Safely get a value from a dictionary using a key.
    Usage: {{ my_dict|dict_get:key_name }}
    Returns None if the key doesn't exist or if there's an error.
    """
    try:
        if d and hasattr(d, 'get'):
            return d.get(key)
        return None
    except Exception:
        return None

@register.filter(name='to_css_class')
def to_css_class(value):
    """
    Convert a value to a CSS-friendly class suffix.
    - Lowercases, trims, replaces underscores with hyphens.
    - Maps known order statuses to friendly names used in CSS.
      created -> pending
      assigned -> in-progress
      in_progress -> in-progress
      completed -> completed
      cancelled -> cancelled
    Priority values (low|medium|high|urgent) pass through unchanged.
    """
    if not value:
        return ''
        
    # Convert to string and clean up
    value = str(value).lower().strip()
    
    # Map specific values to their CSS class equivalents
    status_mapping = {
        'created': 'pending',
        'assigned': 'in-progress',
        'in_progress': 'in-progress',
        'inprogress': 'in-progress',
        'overdue': 'overdue',
        'completed': 'completed',
        'cancelled': 'cancelled',
        'pending': 'pending',
        'low': 'low',
        'medium': 'medium',
        'high': 'high',
        'urgent': 'urgent'
    }

    # Return mapped value if it exists, otherwise clean the string
    return status_mapping.get(value, value.replace('_', '-'))

@register.filter(name='customer_status')
def customer_status(customer):
    """
    Return 'new' if first-time or registered today, else 'returning'.
    Usage: {{ customer|customer_status }}
    """
    try:
        if not customer:
            return ''
        today = timezone.localdate()
        # Consider new if registered today or total_visits <= 1
        if getattr(customer, 'registration_date', None) and customer.registration_date.date() == today:
            return 'new'
        visits = getattr(customer, 'total_visits', 0) or 0
        return 'new' if visits <= 1 else 'returning'
    except Exception:
        return ''

@register.filter(name='abs')
def absolute_value(value):
    """
    Returns the absolute value of a number.
    Usage: {{ value|abs }}
    """
    try:
        return abs(float(value))
    except (ValueError, TypeError):
        return value
    except Exception:
        return ''

@register.filter(name='order_last_update')
def order_last_update(order):
    """
    Returns the most recent timestamp for an order in priority:
    completed_at > cancelled_at > started_at > assigned_at > created_at
    Returns timezone-aware datetime
    """
    try:
        if not order:
            return None
            
        from django.utils import timezone
        
        for attr in ['completed_at', 'cancelled_at', 'started_at', 'assigned_at', 'created_at']:
            val = getattr(order, attr, None)
            if val:
                # Ensure the datetime is timezone-aware
                if timezone.is_naive(val):
                    return timezone.make_aware(val, timezone=timezone.get_current_timezone())
                return val
                
        # If no timestamp found, return current time as fallback
        return timezone.now()
        
    except Exception as e:
        import logging
        logging.error(f"Error in order_last_update: {str(e)}")
        return timezone.now() if 'timezone' in locals() else None

@register.filter(name='margin_percentage')
def margin_percentage(price: Union[float, int, str, Decimal],
                    cost_price: Union[float, int, str, Decimal, None] = None) -> float:
    """
    Calculate the margin percentage between price and cost price.
    If called with two arguments: {{ price|margin_percentage:cost_price }}
    If called with one argument (expects a tuple/dict): {{ item|margin_percentage }}
    """
    try:
        # Handle case where price is a dictionary/object with price and cost_price attributes
        if cost_price is None and hasattr(price, 'get'):
            # Handle dict-like objects
            price_val = float(price.get('price', 0))
            cost_val = float(price.get('cost_price', 0))
        elif cost_price is None and hasattr(price, 'price') and hasattr(price, 'cost_price'):
            # Handle object with price and cost_price attributes
            price_val = float(price.price)
            cost_val = float(price.cost_price)
        else:
            # Handle two separate values
            price_val = float(price)
            cost_val = float(cost_price) if cost_price is not None else 0

        if price_val <= 0 or cost_val <= 0:
            return 0

        margin = ((price_val - cost_val) / price_val) * 100
        return round(margin, 2)
    except (ValueError, TypeError, AttributeError):
        return 0
    except Exception:
        return ''

@register.filter(name='safe_filesize')
def safe_filesize(file_field):
    """
    Safely get the file size of a FileField, returning 'Unknown' if the file doesn't exist.
    Usage: {{ file_field|safe_filesize|filesizeformat }}
    """
    try:
        if file_field and file_field.name:
            return file_field.size
        return 0
    except (FileNotFoundError, OSError):
        return 0
    except Exception:
        return 0

@register.filter(name='format_minutes')
def format_minutes(value: Optional[Union[int, float, str]]):
    """
    Format minutes as a compact human string: 90 -> "1h 30m", 60 -> "1h", 5 -> "5m"
    """
    try:
        if value is None:
            return ''
        total = int(max(0, float(value)))
        hours = total // 60
        mins = total % 60
        if hours and mins:
            return f"{hours}h {mins}m"
        if hours:
            return f"{hours}h"
        return f"{mins}m"
    except (ValueError, TypeError):
        return ''

@register.filter(name='eta_status_label')
def eta_status_label(order_or_tuple):
    """
    Determine ETA performance label given (estimated_minutes, actual_minutes) or an order.
    Active (in-progress/created) orders use elapsed minutes as "actual".
    Returns one of: "On estimate", "Within 10%", "Exceeded estimate", "No estimate".
    """
    try:
        est = None
        act = None
        obj = order_or_tuple
        # Accept a tuple/list
        if isinstance(obj, (tuple, list)) and len(obj) >= 2:
            est, act = obj[0], obj[1]
        else:
            est = getattr(obj, 'estimated_duration', None)
            act = getattr(obj, 'actual_duration', None)
            # Derive elapsed for active orders when actual is not yet set
            if act is None and hasattr(obj, 'status') and getattr(obj, 'status') in {'created', 'in_progress'}:
                try:
                    start = getattr(obj, 'started_at', None) or getattr(obj, 'created_at', None)
                    if start:
                        from django.utils import timezone
                        dt = timezone.localtime(start) if timezone.is_aware(start) else start
                        delta = timezone.now() - dt
                        act = int(max(0, delta.total_seconds() // 60))
                except Exception:
                    act = None
        if not est:
            return 'No estimate'
        if act is None:
            return ''
        est = float(est)
        act = float(act)
        if act <= est:
            return 'On estimate'
        if act <= est * 1.10:
            return 'Within 10%'
        return 'Exceeded estimate'
    except Exception:
        return ''

@register.filter(name='eta_status_badge')
def eta_status_badge(order_or_tuple):
    """
    Return Bootstrap badge class for ETA performance.
    - On estimate -> bg-success
    - Within 10% -> bg-warning text-dark
    - Exceeded estimate -> bg-danger
    - No estimate/unknown -> bg-secondary
    """
    label = eta_status_label(order_or_tuple)
    if label == 'On estimate':
        return 'bg-success'
    if label == 'Within 10%':
        return 'bg-warning text-dark'
    if label == 'Exceeded estimate':
        return 'bg-danger'
    return 'bg-secondary'


@register.filter(name='elapsed_minutes')
def elapsed_minutes(order) -> int:
    """Compute elapsed minutes since start/created for an order."""
    try:
        start = getattr(order, 'started_at', None) or getattr(order, 'created_at', None)
        if not start:
            return 0
        from django.utils import timezone
        dt = timezone.localtime(start) if timezone.is_aware(start) else start
        delta = timezone.now() - dt
        return int(max(0, delta.total_seconds() // 60))
    except Exception:
        return 0


@register.filter(name='extract_services')
def extract_services(description: str) -> list:
    """Extract service names from order description."""
    if not description:
        return []

    services = []
    lines = description.split('\n')
    for line in lines:
        line_lower = line.strip().lower()
        # Look for lines starting with common service labels
        prefixes = ['selected services:', 'services:', 'tire services:', 'add-ons:']
        for prefix in prefixes:
            if line_lower.startswith(prefix):
                # Extract service names after the colon
                services_text = line.split(':', 1)[1].strip() if ':' in line else ''
                if services_text:
                    service_list = [s.strip() for s in services_text.split(',') if s.strip()]
                    services.extend(service_list)

    return services


@register.filter(name='format_eta_status')
def format_eta_status(order) -> str:
    """
    Format ETA status for display (On estimate, Within 10%, Exceeded estimate).
    Handles both completed and active orders.
    """
    try:
        if not order.estimated_duration:
            return "No ETA"

        # Use actual_duration if available (completed order), otherwise calculate elapsed
        if order.actual_duration:
            actual_minutes = order.actual_duration
        else:
            # Calculate elapsed time from started_at or created_at
            start_time = order.started_at or order.created_at
            if not start_time:
                return "No start time"
            from django.utils import timezone
            elapsed_seconds = (timezone.now() - start_time).total_seconds()
            actual_minutes = int(elapsed_seconds // 60)

        estimated = int(order.estimated_duration)

        # Determine status
        if actual_minutes <= estimated:
            return "On estimate"
        elif actual_minutes <= estimated * 1.10:
            return "Within 10%"
        else:
            return "Exceeded estimate"
    except Exception:
        return "Unknown"


@register.filter(name='get_remaining_eta_minutes')
def get_remaining_eta_minutes(order) -> int:
    """
    Calculate remaining minutes until ETA is reached.
    Returns 0 if already exceeded or no ETA.
    """
    try:
        if not order.estimated_duration or order.completed_at:
            return 0

        start_time = order.started_at or order.created_at
        if not start_time:
            return 0

        from django.utils import timezone
        from datetime import timedelta

        eta_time = start_time + timedelta(minutes=int(order.estimated_duration))
        remaining_seconds = (eta_time - timezone.now()).total_seconds()

        return max(0, int(remaining_seconds // 60))
    except Exception:
        return 0
