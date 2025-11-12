"""
ETA and actual duration calculation utilities for orders.

Provides functions to calculate:
- Estimated duration from selected services
- Actual elapsed time from created to completed
- Variance/overrun between ETA and actual time
- Time formatting for display
"""

from datetime import timedelta
from decimal import Decimal
from typing import Optional, Dict, Tuple
from django.utils import timezone


def calculate_estimated_duration(services: list, addon_services: list = None) -> int:
    """
    Calculate total estimated duration from selected services.
    
    Args:
        services: List of ServiceType objects or service names that have estimated_minutes
        addon_services: Optional list of ServiceAddon objects
        
    Returns:
        Total minutes as integer, defaults to 30 if no services or invalid
    """
    if not services:
        return 30  # Default service duration
    
    total_minutes = 0
    
    # Handle ServiceType objects or dicts with estimated_minutes
    for service in services:
        if hasattr(service, 'estimated_minutes'):
            total_minutes += int(service.estimated_minutes or 0)
        elif isinstance(service, dict) and 'estimated_minutes' in service:
            total_minutes += int(service['estimated_minutes'] or 0)
    
    # Add any addon services (for sales orders)
    if addon_services:
        for addon in addon_services:
            if hasattr(addon, 'estimated_minutes'):
                total_minutes += int(addon.estimated_minutes or 0)
            elif isinstance(addon, dict) and 'estimated_minutes' in addon:
                total_minutes += int(addon['estimated_minutes'] or 0)
    
    return total_minutes if total_minutes > 0 else 30


def calculate_actual_duration(created_at, completed_at) -> Optional[int]:
    """
    Calculate actual elapsed time from order creation to completion.
    
    Args:
        created_at: DateTime when order was created
        completed_at: DateTime when order was completed
        
    Returns:
        Elapsed minutes as integer, or None if either timestamp missing
    """
    if not created_at or not completed_at:
        return None
    
    elapsed = completed_at - created_at
    # Convert to minutes and round up
    total_seconds = elapsed.total_seconds()
    minutes = int(total_seconds / 60)
    return minutes if minutes >= 0 else None


def calculate_variance(estimated_minutes: int, actual_minutes: int) -> Dict[str, any]:
    """
    Calculate variance between estimated and actual duration.
    
    Args:
        estimated_minutes: Estimated duration in minutes
        actual_minutes: Actual elapsed duration in minutes
        
    Returns:
        Dictionary with variance metrics:
        {
            'difference': minutes difference (positive = overrun),
            'percentage': percentage difference,
            'is_overrun': boolean if exceeded estimate,
            'status': 'on_time', 'early', or 'overrun'
        }
    """
    if not estimated_minutes or not actual_minutes:
        return {
            'difference': None,
            'percentage': None,
            'is_overrun': False,
            'status': 'unknown'
        }
    
    difference = actual_minutes - estimated_minutes
    percentage = (difference / estimated_minutes * 100) if estimated_minutes > 0 else 0
    
    if difference > 0:
        status = 'overrun'
    elif difference < 0:
        status = 'early'
    else:
        status = 'on_time'
    
    return {
        'difference': difference,
        'percentage': round(percentage, 2),
        'is_overrun': difference > 0,
        'status': status
    }


def format_duration(minutes: Optional[int]) -> str:
    """
    Format duration in minutes to readable string.
    
    Args:
        minutes: Duration in minutes
        
    Returns:
        Formatted string like "2h 30m" or "45m"
    """
    if not minutes:
        return "—"
    
    if minutes < 0:
        return "—"
    
    hours = minutes // 60
    mins = minutes % 60
    
    if hours > 0 and mins > 0:
        return f"{hours}h {mins}m"
    elif hours > 0:
        return f"{hours}h"
    else:
        return f"{mins}m"


def get_order_time_metrics(order) -> Dict[str, any]:
    """
    Get comprehensive time metrics for an order.
    
    Args:
        order: Order model instance
        
    Returns:
        Dictionary with:
        {
            'estimated_duration': int minutes,
            'estimated_formatted': str,
            'actual_duration': int minutes or None,
            'actual_formatted': str,
            'created_at': datetime,
            'completed_at': datetime or None,
            'variance': dict from calculate_variance(),
            'estimated_completion': datetime (created_at + estimated),
            'eta_met': boolean if completed within/before estimate
        }
    """
    estimated_minutes = order.estimated_duration or 30
    actual_minutes = order.actual_duration
    
    # If no actual_duration saved, calculate from timestamps
    if actual_minutes is None and order.completed_at:
        actual_minutes = calculate_actual_duration(order.created_at, order.completed_at)
    
    # Calculate estimated completion time
    estimated_completion = None
    if order.created_at:
        estimated_completion = order.created_at + timedelta(minutes=estimated_minutes)
    
    # Check if ETA was met
    eta_met = True
    if order.completed_at and estimated_completion:
        eta_met = order.completed_at <= estimated_completion
    
    variance = {}
    if actual_minutes:
        variance = calculate_variance(estimated_minutes, actual_minutes)
    
    return {
        'estimated_duration': estimated_minutes,
        'estimated_formatted': format_duration(estimated_minutes),
        'actual_duration': actual_minutes,
        'actual_formatted': format_duration(actual_minutes),
        'created_at': order.created_at,
        'completed_at': order.completed_at,
        'estimated_completion': estimated_completion,
        'variance': variance,
        'eta_met': eta_met,
        'status': order.status
    }
