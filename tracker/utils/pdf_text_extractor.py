"""
PDF and image text extraction without OCR.
Uses PyMuPDF (fitz) and PyPDF2 for PDF text extraction.
Falls back to pattern matching for invoice data extraction.
"""

import io
import logging
import re
from decimal import Decimal
from datetime import datetime

try:
    import fitz
except ImportError:
    fitz = None

try:
    import PyPDF2
except ImportError:
    PyPDF2 = None

from PIL import Image

logger = logging.getLogger(__name__)


def extract_text_from_pdf(file_bytes) -> str:
    """Extract text from PDF file using PyMuPDF or PyPDF2.
    
    Args:
        file_bytes: Raw bytes of PDF file
        
    Returns:
        Extracted text string
        
    Raises:
        RuntimeError: If no PDF extraction library is available
    """
    text = ""
    
    # Try PyMuPDF first (fitz) - best for text extraction
    if fitz is not None:
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in pdf_doc:
                text += page.get_text()
            pdf_doc.close()
            logger.info(f"Extracted {len(text)} characters from PDF using PyMuPDF")
            return text
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed: {e}")
            text = ""
    
    # Fallback to PyPDF2
    if PyPDF2 is not None:
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            for page in pdf_reader.pages:
                text += page.extract_text()
            logger.info(f"Extracted {len(text)} characters from PDF using PyPDF2")
            return text
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {e}")
            text = ""
    
    if not text:
        raise RuntimeError('No PDF text extraction library available. Install PyMuPDF or PyPDF2.')
    
    return text


def extract_text_from_image(file_bytes) -> str:
    """Extract text from image file.
    Since OCR is not available, this returns empty string.
    Images should be uploaded as PDFs or entered manually.
    
    Args:
        file_bytes: Raw bytes of image file
        
    Returns:
        Empty string (manual entry required for images)
    """
    logger.info("Image file detected. OCR not available. Manual entry required.")
    return ""


def parse_invoice_data(text: str) -> dict:
    """Parse invoice data from extracted text using pattern matching.

    This method uses regex patterns to extract invoice fields from raw text.
    It's designed to work with professional invoice formats, especially:
    - Pro forma invoices with Code No, Customer Name, Address, Tel, Reference
    - Traditional invoices with Invoice Number, Date, Customer, etc.
    - Proforma invoices from suppliers (like Superdoll) with columnar line items

    Args:
        text: Raw extracted text from PDF/image

    Returns:
        dict with extracted invoice data including full customer info, line items, and payment details
    """
    if not text or not text.strip():
        return {
            'invoice_no': None,
            'code_no': None,
            'date': None,
            'customer_name': None,
            'address': None,
            'phone': None,
            'email': None,
            'reference': None,
            'subtotal': None,
            'tax': None,
            'total': None,
            'items': [],
            'payment_method': None,
            'delivery_terms': None,
            'remarks': None,
            'attended_by': None,
            'kind_attention': None
        }

    normalized_text = text.strip()
    lines = normalized_text.split('\n')

    # Clean and normalize lines - keep all non-empty lines for better context
    cleaned_lines = []
    for line in lines:
        cleaned = line.strip()
        # Keep all meaningful lines (not just long ones)
        if cleaned:
            cleaned_lines.append(cleaned)

    # Helper to find field value - try multiple strategies including searching ahead
    def extract_field_value(label_patterns, text_to_search=None, max_distance=10, stop_at_patterns=None):
        """Extract value after a label using flexible pattern matching and distance-based search.

        This handles cases where PDF extraction scrambles text ordering.
        It looks for the label, then finds the most likely value nearby in the text.

        Args:
            label_patterns: Pattern(s) to match the label
            text_to_search: Text to search in (default: normalized_text)
            max_distance: Max lines to search for value
            stop_at_patterns: Patterns that indicate we've hit the next field
        """
        search_text = text_to_search or normalized_text
        patterns = label_patterns if isinstance(label_patterns, list) else [label_patterns]
        stop_patterns = stop_at_patterns or [
            r'Tel|Fax|Del|Ref|Date|Kind|Attended|Type|Payment|Delivery|Reference|PI|Cust|Qty|Rate|Value|Address|Customer|Code'
        ]

        for pattern in patterns:
            # Strategy 1: Look for "Label: Value" or "Label = Value" on same line
            m = re.search(rf'{pattern}\s*[:=]\s*([^\n:{{]+)', search_text, re.I | re.MULTILINE)
            if m and m.group(1).strip():
                value = m.group(1).strip()
                # Don't clean up if it's a multi-word value (company names, addresses)
                # Only clean if the value starts with a stop pattern
                if not re.match(r'^(?:' + '|'.join([p for p in stop_patterns.split('|') if p.strip()]) + r')\b', value, re.I):
                    return value

            # Strategy 2: "Label Value" (space separated, often in scrambled PDFs)
            m = re.search(rf'{pattern}\s+(?![:=])([A-Z][^\n:{{]*?)(?=\n[A-Z]|\s{2,}[A-Z]|\n$|$)', search_text, re.I | re.MULTILINE)
            if m and m.group(1).strip():
                value = m.group(1).strip()
                # Skip if it looks like a label
                if not re.match(r'^(?:' + '|'.join([p for p in stop_patterns.split('|') if p.strip()]) + r')\b', value, re.I) and len(value) > 2:
                    return value

            # Strategy 3: Find label in a line, then look for value on next non-empty line
            lines = search_text.split('\n')
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.I):
                    # Check if value is on same line (after label)
                    m = re.search(rf'{pattern}\s*[:=]?\s*(.+)$', line, re.I)
                    if m:
                        value = m.group(1).strip()
                        if value and value.upper() not in (':', '=', ''):
                            return value

                    # Look for value on next lines (handles multi-line fields)
                    for j in range(1, min(max_distance, len(lines) - i)):
                        next_line = lines[i + j].strip()
                        if not next_line:
                            continue

                        # Stop if it's a clear new label
                        if re.match(r'^(?:' + '|'.join([p for p in stop_patterns.split('|') if p.strip()]) + r')\s*[:=]', next_line, re.I):
                            break

                        # This line is likely the value
                        return next_line

        return None

    # Extract Code No (specific pattern for Superdoll invoices)
    code_no = extract_field_value([
        r'Code\s*No',
        r'Code\s*#',
        r'Code(?:\s|:)'
    ])

    # Helper to validate if text looks like a customer name vs address
    def is_likely_customer_name(text):
        """Check if text looks like a company/person name vs an address."""
        if not text:
            return False
        text_lower = text.lower()

        # Strong address indicators
        address_keywords = ['street', 'avenue', 'road', 'box', 'p.o', 'po box', 'floor', 'apt', 'suite',
                           'district', 'region', 'city', 'zip', 'postal code', 'building']

        # If it has strong address keywords, it's probably not a company name
        for kw in address_keywords:
            if kw in text_lower:
                return False

        # Company indicators (company names usually have these)
        company_indicators = ['ltd', 'inc', 'corp', 'co', 'company', 'llc', 'limited', 'enterprise',
                            'trading', 'group', 'industries', 'services', 'solutions', 'consulting']
        has_company_indicator = any(ind in text_lower for ind in company_indicators)

        # Must be reasonably capitalized/formatted
        is_well_formatted = len(text) > 2 and (text[0].isupper() or text.isupper())

        # Company names should be at least 4 chars, properly capitalized, and possibly have company indicators
        return is_well_formatted and len(text) >= 4 and (has_company_indicator or ' ' not in text or len(text.split()) <= 5)

    def is_likely_address(text):
        """Check if text looks like an address."""
        if not text:
            return False
        text_lower = text.lower()

        # Strong address indicators
        address_indicators = ['street', 'avenue', 'road', 'box', 'p.o', 'po box', 'floor', 'apt', 'suite',
                             'district', 'region', 'city', 'country', 'zip', 'postal', 'dar', 'dar-es',
                             'tanzania', 'nairobi', 'kenya', 'building']

        # Has location name or postal indicators
        has_indicators = any(ind in text_lower for ind in address_indicators)

        # Has numbers (house/building numbers)
        has_numbers = bool(re.search(r'\d+', text))

        # Has multiple parts (usually separated by commas or just multiple words)
        has_multipart = ',' in text or ' ' in text

        # Address must have indicators OR have numbers and multiple parts
        return has_indicators or (has_numbers and has_multipart and len(text) > 5)

    # Extract customer name - more careful pattern matching
    customer_name = None

    # First try the exact "Customer Name" pattern
    m = re.search(r'Customer\s*Name\s*[:=]?\s*([^\n:{{]+?)(?=\n(?:Address|Tel|Attended|Kind|Reference|PI|Code)|$)', normalized_text, re.I | re.MULTILINE | re.DOTALL)
    if m:
        customer_name = m.group(1).strip()
        # Clean up any trailing field indicators
        customer_name = re.sub(r'\s+(?:Address|Tel|Phone|Fax|Email|Attended|Kind|Ref)\b.*$', '', customer_name, flags=re.I).strip()

    # If still not found, try alternative patterns
    if not customer_name:
        customer_name = extract_field_value([
            r'Bill\s*To',
            r'Buyer\s*Name',
            r'Client\s*Name'
        ])

    # Validate customer name - if it looks like an address, clear it and we'll get it from Address field
    if customer_name:
        if is_likely_address(customer_name) and not is_likely_customer_name(customer_name):
            # This looks like an address, not a customer name
            customer_name = None
        elif len(customer_name) > 200:
            # Too long to be a name, probably corrupted
            customer_name = None

    # Extract address - improved to handle multi-line addresses
    address = None
    address_pattern = re.compile(r'Address\s*[:=]?\s*(.+?)(?=\n(?:Tel|Attended|Kind|Reference|PI|Code|Fax|Del\.|Remarks|NOTE|Payment|Delivery)\b|$)', re.I | re.MULTILINE | re.DOTALL)
    address_match = address_pattern.search(normalized_text)

    if address_match:
        address_text = address_match.group(1).strip()
        # Clean up the address text - remove trailing labels/keywords
        address_text = re.sub(r'\s+(?:Tel|Phone|Fax|Attended|Kind|Reference|Ref\.|Date|PI|Code|Type|Payment|Delivery|Remarks|NOTE|Qty|Rate|Value)\b.*', '', address_text, flags=re.I).strip()
        # Keep newlines in address for readability (they're often multi-line)
        address_text = ' '.join(line.strip() for line in address_text.split('\n') if line.strip())
        if address_text and len(address_text) > 2:
            address = address_text

    # Smart fix: If customer_name is empty but address looks like it contains the name
    # Try to split the address and extract name from first line
    if not customer_name and address:
        # Take first line of address if it looks like a name
        first_line = address.split('\n')[0] if '\n' in address else address.split()[0:3]
        potential_name = ' '.join(first_line) if isinstance(first_line, list) else first_line

        if is_likely_customer_name(potential_name):
            customer_name = potential_name
            # Remove the name part from address
            address = re.sub(r'^' + re.escape(potential_name) + r'\s*', '', address).strip()
            if not address or len(address) < 3:
                address = None

    # Extract phone/tel - improved to handle various formats
    phone = None
    phone_pattern = re.compile(r'Tel\s*[:=]?\s*([^\n:{{]+?)(?=\n(?:Fax|Attended|Kind|Reference|Remarks|Date|Del\.|PI)\b|$)', re.I | re.MULTILINE)
    phone_match = phone_pattern.search(normalized_text)

    if phone_match:
        phone = phone_match.group(1).strip()
        # Remove "Fax" part if it appears
        phone = re.sub(r'[\s/]+(?:Fax.*)?$', '', phone, flags=re.I).strip()
        # Validate - phone should have some digits or be a descriptive value like "Sales Point"
        if phone and (re.search(r'\d', phone) or len(phone) > 3):
            # If contains slash or hyphen with numbers, keep first part
            if '/' in phone or '-' in phone:
                parts = re.split(r'[\/-]', phone)
                phone = parts[0].strip()
        else:
            phone = None

    # Extract email - look for email pattern in the text
    email = None
    email_match = re.search(r'([\w\.-]+@[\w\.-]+\.\w+)', normalized_text)
    if email_match:
        email = email_match.group(1)

    # Extract reference - more careful pattern to avoid getting other labels
    reference = None
    ref_pattern = re.compile(r'(?:Reference|Ref\.?)\s*[:=]?\s*([^\n:{{]+?)(?=\n(?:Tel|Code|PI|Date|Del\.|Attended|Kind|Remarks)\b|$)', re.I | re.MULTILINE)
    ref_match = ref_pattern.search(normalized_text)

    if ref_match:
        reference = ref_match.group(1).strip()
        # Clean up
        reference = re.sub(r'\s+(?:Tel|Fax|Date|PI|Code)\b.*$', '', reference, flags=re.I).strip()
        if not reference or reference.upper() == 'NONE' or len(reference) < 2:
            reference = None

    # Extract PI No. / Invoice Number - specifically handle "PI No." format
    invoice_no = None
    pi_pattern = re.compile(r'PI\s*(?:No|Number|#)\s*[:=]?\s*([^\n:{{]+?)(?=\n|$)', re.I | re.MULTILINE)
    pi_match = pi_pattern.search(normalized_text)

    if pi_match:
        invoice_no = pi_match.group(1).strip()
        # Clean up trailing whitespace and field names
        invoice_no = re.sub(r'\s+(?:Date|Cust|Ref|Del|Code)\b.*$', '', invoice_no, flags=re.I).strip()

    # Fallback to "Invoice Number" pattern if PI No not found
    if not invoice_no:
        invoice_no = extract_field_value([
            r'Invoice\s*(?:No|Number)',
            r'Invoice\s*Number'
        ])

    # Extract Date (multiple formats)
    date_str = None
    # Look for date patterns
    date_patterns = [
        r'Date\s*[:=]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        r'Invoice\s*Date\s*[:=]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',  # Fallback: any date pattern
    ]
    for pattern in date_patterns:
        m = re.search(pattern, normalized_text, re.I)
        if m:
            date_str = m.group(1)
            break

    # Parse monetary values helper
    def to_decimal(s):
        try:
            if s:
                # Remove currency symbols and extra characters, keep only numbers, dot, comma
                cleaned = re.sub(r'[^\d\.\,\-]', '', str(s)).strip()
                if cleaned and cleaned not in ('.', ',', '-'):
                    return Decimal(cleaned.replace(',', ''))
        except Exception:
            pass
        return None

    # Extract monetary amounts using flexible patterns (handles scrambled PDFs)
    def find_amount(label_patterns):
        """Find monetary amount after label patterns - works with scrambled PDF text"""
        patterns = (label_patterns if isinstance(label_patterns, list) else [label_patterns])
        for pattern in patterns:
            # Try with colon separator: "Label: Amount"
            m = re.search(rf'{pattern}\s*:\s*(?:TSH|TZS|UGX)?\s*([0-9\,\.]+)', normalized_text, re.I | re.MULTILINE)
            if m:
                return m.group(1)

            # Try with equals: "Label = Amount"
            m = re.search(rf'{pattern}\s*=\s*(?:TSH|TZS|UGX)?\s*([0-9\,\.]+)', normalized_text, re.I | re.MULTILINE)
            if m:
                return m.group(1)

            # Try with space and optional currency on same line
            m = re.search(rf'{pattern}\s+(?:TSH|TZS|UGX)?\s*([0-9\,\.]+)', normalized_text, re.I | re.MULTILINE)
            if m:
                return m.group(1)

            # Try finding amount on next line (for scrambled PDFs)
            lines = normalized_text.split('\n')
            for i, line in enumerate(lines):
                if re.search(pattern, line, re.I):
                    # Check for amount on same line
                    m = re.search(rf'{pattern}\s*[:=]?\s*([0-9\,\.]+)', line, re.I)
                    if m:
                        return m.group(1)

                    # Check next 2 lines for amount
                    for j in range(1, 3):
                        if i + j < len(lines):
                            next_line = lines[i + j].strip()
                            # Look for amount pattern
                            if re.match(r'^(?:TSH|TZS|UGX)?\s*([0-9\,\.]+)', next_line, re.I):
                                m = re.match(r'^(?:TSH|TZS|UGX)?\s*([0-9\,\.]+)', next_line, re.I)
                                if m:
                                    return m.group(1)
        return None

    # Extract Net Value / Subtotal
    subtotal = to_decimal(find_amount([
        r'Net\s*Value',
        r'Net\s*Amount',
        r'Subtotal',
        r'Net\s*:'
    ]))

    # Extract VAT / Tax
    tax = to_decimal(find_amount([
        r'VAT',
        r'Tax',
        r'GST',
        r'Sales\s*Tax'
    ]))

    # Extract Gross Value / Total
    total = to_decimal(find_amount([
        r'Gross\s*Value',
        r'Total\s*Amount',
        r'Grand\s*Total',
        r'Total\s*(?::|\s)'
    ]))

    # Extract payment method
    payment_method = extract_field_value(r'(?:Payment|Payment\s*Method|Payment\s*Type)')
    if payment_method:
        # Clean up the payment method value
        payment_method = re.sub(r'Delivery.*$', '', payment_method, flags=re.I).strip()
        if payment_method and len(payment_method) > 1:
            # Map common payment method strings to standard values
            payment_map = {
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
            }
            for key, val in payment_map.items():
                if key in payment_method.lower():
                    payment_method = val
                    break

    # Extract delivery terms
    delivery_terms = extract_field_value(r'(?:Delivery|Delivery\s*Terms)')
    if delivery_terms:
        delivery_terms = re.sub(r'(?:Remarks|Notes|NOTE).*$', '', delivery_terms, flags=re.I).strip()

    # Extract remarks/notes
    remarks = extract_field_value(r'(?:Remarks|Notes|NOTE)')
    if remarks:
        # Clean up - remove trailing labels and numbers
        remarks = re.sub(r'(?:\d+\s*:|^NOTE\s*\d+\s*:)', '', remarks, flags=re.I).strip()
        remarks = re.sub(r'(?:Payment|Delivery|Due|See).*$', '', remarks, flags=re.I).strip()

    # Extract "Attended By" field - more careful pattern matching
    attended_by = None
    attended_pattern = re.compile(r'Attended\s*(?:By|:)?\s*([^\n:{{]+?)(?=\n(?:Kind|Reference|Tel|Remarks|Payment)\b|$)', re.I | re.MULTILINE)
    attended_match = attended_pattern.search(normalized_text)

    if attended_match:
        attended_by = attended_match.group(1).strip()
        # Clean up
        attended_by = re.sub(r'\s+(?:Kind|Reference|Tel|Remarks|Payment)\b.*$', '', attended_by, flags=re.I).strip()
        if not attended_by or len(attended_by) < 2:
            attended_by = None

    # Extract "Kind Attention" field - handles both "Kind Attention" and "Kind Attn"
    kind_attention = None
    kind_pattern = re.compile(r'Kind\s*(?:Attention|Attn|:)?\s*([^\n:{{]+?)(?=\n(?:Reference|Remarks|Tel|Attended|Payment|Delivery)\b|$)', re.I | re.MULTILINE)
    kind_match = kind_pattern.search(normalized_text)

    if kind_match:
        kind_attention = kind_match.group(1).strip()
        # Clean up
        kind_attention = re.sub(r'\s+(?:Reference|Remarks|Tel|Attended|Payment|Delivery)\b.*$', '', kind_attention, flags=re.I).strip()
        if not kind_attention or len(kind_attention) < 2:
            kind_attention = None

    # Extract line items with improved detection for various formats
    # The algorithm:
    # 1. Find the table header row (contains item-related keywords)
    # 2. Parse all lines after the header until we hit a totals section
    # 3. For each item line, extract: description, code, qty, unit, rate, value
    items = []
    item_section_started = False
    item_header_idx = -1

    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue

        # Detect item section header - line with multiple item-related keywords
        keyword_count = sum([
            1 if re.search(r'\b(?:Sr|S\.N|Serial|No\.?)\b', line_stripped, re.I) else 0,
            1 if re.search(r'\b(?:Item|Code)\b', line_stripped, re.I) else 0,
            1 if re.search(r'\b(?:Description|Desc)\b', line_stripped, re.I) else 0,
            1 if re.search(r'\b(?:Qty|Quantity|Qty\.?|Type)\b', line_stripped, re.I) else 0,
            1 if re.search(r'\b(?:Rate|Price|Unit|UnitPrice)\b', line_stripped, re.I) else 0,
            1 if re.search(r'\b(?:Value|Amount|Total)\b', line_stripped, re.I) else 0,
        ])

        if keyword_count >= 3:
            item_section_started = True
            item_header_idx = idx
            continue

        # Stop at totals/summary section
        if item_section_started and idx > item_header_idx + 1:
            if re.search(r'(?:Net\s*Value|Gross\s*Value|Grand\s*Total|Total\s*:|Payment|Delivery|Remarks|NOTE)', line_stripped, re.I):
                break

        # Parse item lines (after header starts)
        if item_section_started and idx > item_header_idx:
            # Extract all numbers and their positions
            numbers = re.findall(r'[0-9\,]+\.?\d*', line_stripped)

            # Extract text parts by removing numbers
            text_only = re.sub(r'[0-9\,]+\.?\d*', '|', line_stripped)
            text_parts = [p.strip() for p in text_only.split('|') if p.strip()]

            # Skip if this line has no meaningful content
            if not numbers and not text_parts:
                continue

            # Process a line with both text and numbers (typical item row)
            if text_parts and numbers:
                try:
                    # Join text parts as description
                    full_text = ' '.join(text_parts)

                    # Skip if description is too short (likely a header continuation)
                    if len(full_text) < 2:
                        continue

                    # Convert numbers to floats
                    float_numbers = [float(n.replace(',', '')) for n in numbers]

                    # Extract unit (NOS, PCS, HR, etc.) from text first
                    unit_match = re.search(r'\b(NOS|PCS|KG|HR|LTR|PIECES?|UNITS?|BOX|CASE|SETS?|PC|KIT)\b', line_stripped, re.I)
                    unit_value = None
                    if unit_match:
                        unit_value = unit_match.group(1).upper()
                        # Remove unit from full_text to get clean description
                        full_text = re.sub(r'\b' + unit_match.group(1) + r'\b', '', full_text, flags=re.I).strip()

                    # Initialize item
                    item = {
                        'description': full_text[:255] if full_text else ' '.join(text_parts)[:255],
                        'qty': 1,
                        'unit': unit_value,
                        'value': None,
                        'rate': None,
                        'code': None,
                    }

                    # Try to extract item code from the extracted numbers or text
                    # Usually the item code is 3-6 digits and among the first few numbers
                    for fn in float_numbers[:3]:  # Check first 3 numbers
                        if 100 <= fn <= 999999 and fn == int(fn):  # Item codes are typically 3-6 digit integers
                            if 3000 <= fn <= 50000 or 100 <= fn <= 999 or 10000 <= fn <= 99999:
                                item['code'] = str(int(fn))
                                break

                    # Also check if there's a code pattern in the text (like "41003" in "41003 STEERING")
                    if not item['code']:
                        code_match = re.search(r'\b(\d{3,6})\b', full_text)
                        if code_match:
                            item['code'] = code_match.group(1)

                    # Parse quantities and amounts from numbers
                    if len(float_numbers) == 1:
                        # Single number: likely the total value
                        item['value'] = to_decimal(str(float_numbers[0]))
                        item['rate'] = item['value']  # If no qty, rate = value
                    elif len(float_numbers) == 2:
                        # Two numbers: qty and value (or rate and value)
                        # Smaller number is likely qty if it's an integer
                        if float_numbers[0] < 100 and float_numbers[0] == int(float_numbers[0]):
                            item['qty'] = int(float_numbers[0])
                            item['value'] = to_decimal(str(float_numbers[1]))
                            item['rate'] = to_decimal(str(float_numbers[1] / float_numbers[0]))
                        elif float_numbers[1] < 100 and float_numbers[1] == int(float_numbers[1]):
                            item['qty'] = int(float_numbers[1])
                            item['value'] = to_decimal(str(float_numbers[0]))
                            item['rate'] = to_decimal(str(float_numbers[0] / float_numbers[1]))
                        else:
                            # Default: smaller is qty, larger is value
                            if float_numbers[0] < float_numbers[1]:
                                item['qty'] = int(float_numbers[0]) if float_numbers[0] == int(float_numbers[0]) else float_numbers[0]
                                item['value'] = to_decimal(str(float_numbers[1]))
                                item['rate'] = to_decimal(str(float_numbers[1] / float_numbers[0]))
                            else:
                                item['qty'] = int(float_numbers[1]) if float_numbers[1] == int(float_numbers[1]) else float_numbers[1]
                                item['value'] = to_decimal(str(float_numbers[0]))
                                item['rate'] = to_decimal(str(float_numbers[0] / float_numbers[1]))
                    elif len(float_numbers) >= 3:
                        # Multiple numbers: parse as Sr#, Code, Qty, Rate, Value
                        # Typical patterns:
                        # Sr | Code | Qty | Rate | Value (5 numbers)
                        # Or: Code | Qty | Rate | Value (4 numbers, no Sr)
                        # Or: Code | Qty | Value (3 numbers, no Rate)

                        max_num = max(float_numbers)

                        # Find qty: small integer (1-1000)
                        qty_candidate = None
                        qty_index = None
                        for idx, fn in enumerate(float_numbers):
                            if 0.5 < fn < 1000 and (fn == int(fn) or abs(fn - round(fn)) < 0.1):
                                if fn <= max_num / 10:  # Qty should be much smaller than value
                                    qty_candidate = int(round(fn))
                                    qty_index = idx
                                    break

                        if qty_candidate:
                            item['qty'] = qty_candidate

                        # Largest number is the total value
                        item['value'] = to_decimal(str(max_num))

                        # Try to find rate (second largest or calculated from qty)
                        if qty_candidate and qty_candidate > 0:
                            # Calculate rate from value / qty
                            item['rate'] = to_decimal(str(max_num / qty_candidate))
                        else:
                            # If we have qty_index, try to find rate near it
                            if qty_index is not None and qty_index < len(float_numbers) - 1:
                                # Number after qty might be rate
                                potential_rate = float_numbers[qty_index + 1]
                                if potential_rate != max_num:  # Not the value
                                    item['rate'] = to_decimal(str(potential_rate))

                    # Only add if we have at least description and value
                    if item.get('description') and (item.get('value') or item.get('qty')):
                        items.append(item)

                except Exception as e:
                    logger.warning(f"Error parsing item line: {line_stripped}, {e}")

            # Process line with only numbers (continuation of item data)
            elif numbers and not text_parts:
                # Skip standalone number lines (likely part of header or footer)
                if len(items) == 0:
                    continue

                try:
                    float_numbers = [float(n.replace(',', '')) for n in numbers]
                    # Treat largest number as value
                    value = max(float_numbers)
                    if value > 0 and items:
                        # Only update if item doesn't have a value yet
                        if not items[-1].get('value'):
                            items[-1]['value'] = to_decimal(str(value))
                except Exception:
                    pass

    return {
        'invoice_no': invoice_no,
        'code_no': code_no,
        'date': date_str,
        'customer_name': customer_name,
        'phone': phone,
        'email': email,
        'address': address,
        'reference': reference,
        'subtotal': subtotal,
        'tax': tax,
        'total': total,
        'items': items,
        'payment_method': payment_method,
        'delivery_terms': delivery_terms,
        'remarks': remarks,
        'attended_by': attended_by,
        'kind_attention': kind_attention
    }


def extract_from_bytes(file_bytes, filename: str = '') -> dict:
    """Main entry point: extract text from file and parse invoice data.
    
    Supports:
    - PDF files: Uses PyMuPDF/PyPDF2 for text extraction
    - Image files: Requires manual entry (OCR not available)
    
    Args:
        file_bytes: Raw bytes of uploaded file
        filename: Original filename (to detect file type)
        
    Returns:
        dict with keys: success, header, items, raw_text, ocr_available, error, message
    """
    if not file_bytes:
        return {
            'success': False,
            'error': 'empty_file',
            'message': 'File is empty',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }
    
    # Detect file type
    is_pdf = filename.lower().endswith('.pdf') or file_bytes[:4] == b'%PDF'
    is_image = filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp'))
    
    text = ""
    extraction_error = None
    
    # Try to extract text
    if is_pdf:
        try:
            text = extract_text_from_pdf(file_bytes)
        except Exception as e:
            logger.error(f"PDF extraction failed: {e}")
            extraction_error = str(e)
            return {
                'success': False,
                'error': 'pdf_extraction_failed',
                'message': f'Failed to extract text from PDF: {str(e)}. Please enter invoice details manually.',
                'ocr_available': False,
                'header': {},
                'items': [],
                'raw_text': ''
            }
    elif is_image:
        return {
            'success': False,
            'error': 'image_file_not_supported',
            'message': 'Image files require manual entry (OCR not available). Please save as PDF or enter details manually.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }
    else:
        return {
            'success': False,
            'error': 'unsupported_file_type',
            'message': 'Please upload a PDF file (images are not supported without OCR).',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }
    
    # Parse extracted text
    if text:
        try:
            parsed = parse_invoice_data(text)
            # Prepare header with all extracted fields
            header = {
                'invoice_no': parsed.get('invoice_no'),
                'code_no': parsed.get('code_no'),
                'date': parsed.get('date'),
                'customer_name': parsed.get('customer_name'),
                'phone': parsed.get('phone'),
                'email': parsed.get('email'),
                'address': parsed.get('address'),
                'reference': parsed.get('reference'),
                'subtotal': parsed.get('subtotal'),
                'tax': parsed.get('tax'),
                'total': parsed.get('total'),
                'payment_method': parsed.get('payment_method'),
                'delivery_terms': parsed.get('delivery_terms'),
                'remarks': parsed.get('remarks'),
                'attended_by': parsed.get('attended_by'),
                'kind_attention': parsed.get('kind_attention'),
            }

            # Format items with all extracted fields
            items = []
            for item in parsed.get('items', []):
                items.append({
                    'description': item.get('description', ''),
                    'qty': item.get('qty', 1),
                    'unit': item.get('unit'),
                    'code': item.get('code'),
                    'value': float(item.get('value', 0)) if item.get('value') else 0,
                    'rate': float(item.get('rate', 0)) if item.get('rate') else None,
                })

            return {
                'success': True,
                'header': header,
                'items': items,
                'raw_text': text,
                'ocr_available': False,  # Using text extraction, not OCR
                'message': 'Invoice data extracted successfully from PDF'
            }
        except Exception as e:
            logger.warning(f"Failed to parse invoice data: {e}")
            return {
                'success': False,
                'error': 'parsing_failed',
                'message': 'Could not extract structured data from PDF. Please enter invoice details manually.',
                'ocr_available': False,
                'header': {},
                'items': [],
                'raw_text': text
            }
    
    # If no text was extracted
    return {
        'success': False,
        'error': 'no_text_extracted',
        'message': 'No text found in PDF. Please enter invoice details manually.',
        'ocr_available': False,
        'header': {},
        'items': [],
        'raw_text': ''
    }
