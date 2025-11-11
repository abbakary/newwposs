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
        RuntimeError: If no PDF extraction library is available or text extraction fails
    """
    text = ""
    fitz_error = None
    pdf2_error = None

    # Try PyMuPDF first (fitz) - best for text extraction
    if fitz is not None:
        try:
            pdf_doc = fitz.open(stream=file_bytes, filetype="pdf")
            for page in pdf_doc:
                page_text = page.get_text()
                if page_text:
                    text += page_text
            pdf_doc.close()

            if text and text.strip():
                logger.info(f"Successfully extracted {len(text)} characters from PDF using PyMuPDF")
                return text
            else:
                logger.warning("PyMuPDF extracted empty text from PDF")
                fitz_error = "No text found in PDF (PyMuPDF)"
        except Exception as e:
            logger.warning(f"PyMuPDF extraction failed: {e}")
            fitz_error = str(e)
            text = ""

    # Fallback to PyPDF2
    text = ""
    if PyPDF2 is not None:
        try:
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            if len(pdf_reader.pages) == 0:
                pdf2_error = "PDF has no pages"
            else:
                for page in pdf_reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text

                if text and text.strip():
                    logger.info(f"Successfully extracted {len(text)} characters from PDF using PyPDF2")
                    return text
                else:
                    logger.warning("PyPDF2 extracted empty text from PDF")
                    pdf2_error = "No text found in PDF (PyPDF2)"
        except Exception as e:
            logger.warning(f"PyPDF2 extraction failed: {e}")
            pdf2_error = str(e)

    # If we get here, extraction failed with both libraries
    if not fitz and not PyPDF2:
        error_msg = 'No PDF extraction library available. Install PyMuPDF or PyPDF2.'
    elif fitz_error and pdf2_error:
        error_msg = f'PDF extraction failed - PyMuPDF: {fitz_error}. PyPDF2: {pdf2_error}'
    elif fitz_error:
        error_msg = fitz_error
    else:
        error_msg = pdf2_error or 'Unknown PDF extraction error'

    raise RuntimeError(error_msg)


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

    # Detect seller block at top of document (company header) and strip it from normalized_text
    seller_name = None
    seller_address = None
    seller_phone = None
    seller_email = None
    seller_tax_id = None
    seller_vat_reg = None

    try:
        # Look at the first few lines for company header
        top_block = cleaned_lines[:8] if len(cleaned_lines) >= 1 else []
        split_idx = None
        for i, l in enumerate(top_block):
            # Stop seller block when we hit typical invoice/customer markers
            if re.search(r'Proforma|Invoice\b|PI\b|Customer\b|Bill\s*To|Date\b|Customer\s*Reference|Invoice\s*No|Code', l, re.I):
                split_idx = i
                break
        if split_idx is None:
            # if no explicit marker, assume first 1-2 lines may be seller header
            split_idx = min(2, len(top_block))
        seller_lines = top_block[:split_idx]
        if seller_lines:
            # Seller name is usually first line
            seller_name = seller_lines[0].strip() if seller_lines[0].strip() else None
            if len(seller_lines) > 1:
                seller_address = ' '.join([ln.strip() for ln in seller_lines[1:] if ln.strip()])

            # Try to extract phone and email and tax numbers from seller_lines block
            seller_block_text = '\n'.join(seller_lines)
            phone_match = re.search(r'(?:Tel\.?|Telephone|Phone)[:\s]*([\+\d][\d\s\-/\(\)\,]{4,}\d)', seller_block_text, re.I)
            if phone_match:
                seller_phone = phone_match.group(1).strip()
            email_match = re.search(r'([\w\.-]+@[\w\.-]+\.\w+)', seller_block_text)
            if email_match:
                seller_email = email_match.group(1).strip()
            tax_match = re.search(r'(?:Tax\s*ID|Tax\s*No\.?|Tax\s*Number)[:\s]*([A-Z0-9\-\/]*)', seller_block_text, re.I)
            if tax_match:
                seller_tax_id = tax_match.group(1).strip()
            vat_match = re.search(r'(?:VAT\s*Reg\.?|VAT\s*No\.?|VAT)[:\s]*([A-Z0-9\-\/]*)', seller_block_text, re.I)
            if vat_match:
                seller_vat_reg = vat_match.group(1).strip()

            # Remove seller block from normalized_text so subsequent extraction focuses on invoice content
            try:
                normalized_text = normalized_text.replace(seller_block_text, '', 1)
                # Rebuild lines after removal
                lines = normalized_text.split('\n')
            except Exception:
                pass
    except Exception:
        # If detection fails, continue without stripping
        seller_name = seller_name or None

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
        stop_patterns = stop_at_patterns or r'Tel|Fax|Del|Ref|Date|Kind|Attended|Type|Payment|Delivery|Reference|PI|Cust|Qty|Rate|Value|Address|Customer|Code'

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

    # Extract Code No - IMPROVED PATTERNS
    code_no = None
    
    # Strategy 1: Look for "Code No:" pattern with various formats
    code_patterns = [
        r'Code\s*No\s*[:=]\s*([^\n]+?)(?=\n|$)',
        r'Code\s*#\s*[:=]\s*([^\n]+?)(?=\n|$)',
        r'Code\s*No\.?\s*[:=]?\s*([A-Z0-9\-]+)',
        r'Code\s*[:=]\s*([^\n]+?)(?=\n|$)',
    ]
    
    for pattern in code_patterns:
        m = re.search(pattern, normalized_text, re.I | re.MULTILINE)
        if m:
            code_no = m.group(1).strip()
            # Clean up - remove any trailing field labels
            code_no = re.sub(r'\s+(?:Customer|Date|Reference|PI|Tel|Phone|Address)\b.*$', '', code_no, flags=re.I).strip()
            if code_no and len(code_no) > 1:
                break
    
    # Strategy 2: If no explicit Code No found, look for standalone codes in the header section
    if not code_no:
        # Look for patterns like "Code: ABC123" or "Code No. XYZ456"
        header_section = '\n'.join(cleaned_lines[:20])  # First 20 lines for header
        code_matches = re.findall(r'(?:Code\s*(?:No|#)?\s*[:=]?\s*)([A-Z0-9\-]{3,20})', header_section, re.I)
        if code_matches:
            code_no = code_matches[0].strip()

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

    # Extract customer name - improved pattern matching for Superdoll format
    customer_name = None

    # Strategy 1: Look for "Customer Name" label and extract ONLY what comes after it
    # The key is to extract ONLY the customer name, not the label itself
    # Handle formats like: "Customer Name : VALUE" or "Customer Name VALUE"
    m = re.search(r'Customer\s+Name\s*[:=]?\s*([A-Z][^\n]*?)(?=\n|$)', normalized_text, re.I | re.MULTILINE)
    if m:
        customer_name = m.group(1).strip()

        # Remove "Customer Name" or "Customer" if it appears at the beginning or end (due to scrambled OCR)
        customer_name = re.sub(r'^Customer\s*Name?\s*[:=]?\s*', '', customer_name, flags=re.I).strip()
        customer_name = re.sub(r'\s+Customer\s*Name?.*$', '', customer_name, flags=re.I).strip()

        # Remove other field labels that might have been included at the end
        customer_name = re.sub(r'\s+(?:Reference|Ref\.?|Address|Tel|Phone|Fax|Email|Attended|Kind|Code|PI|Date|Cust|Del\.|Type|Qty|Rate|Value)\b.*$', '', customer_name, flags=re.I).strip()

        # Validate: customer name should have company indicators or be reasonably formatted
        if customer_name and len(customer_name) > 3 and customer_name.upper() not in ['REFERENCE', 'ADDRESS', 'TEL', 'FAX', 'EMAIL']:
            # Must not be a field label
            if not re.match(r'^(?:Address|Tel|Fax|Email|Phone|Reference)\b', customer_name, re.I):
                pass
            else:
                customer_name = None
        else:
            customer_name = None

    # Strategy 2: Look for lines that have customer name pattern - company names usually have LTD, CO, INC, etc.
    if not customer_name:
        lines_data = normalized_text.split('\n')
        for i, line in enumerate(lines_data):
            if re.search(r'Customer\s*Name\s*:?', line, re.I):
                # The customer name is in this line or the next few lines
                for j in range(i, min(i + 4, len(lines_data))):
                    candidate = lines_data[j].strip()
                    # Skip the label itself
                    candidate = re.sub(r'^Customer\s*Name\s*:?\s*', '', candidate, flags=re.I).strip()
                    # Check if it looks like a customer name (has company indicators or multiple words)
                    if candidate and is_likely_customer_name(candidate) and len(candidate) > 3:
                        customer_name = candidate
                        break
                if customer_name:
                    break

    # Strategy 3: Alternative patterns if above fails
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

    # Extract address - specifically look for P.O.BOX format
    address = None

    # Split text into lines for easier processing (don't filter empty - preserve structure)
    lines = [line.strip() for line in normalized_text.split('\n')]
    lines = [l for l in lines if l]  # Now filter empty lines

    # Pattern 1: Find P.O.BOX with the box number - handle various formats
    pob_match = None
    pob_line_idx = None
    pob_text = None

    for idx, line in enumerate(lines):
        # Match P.O.BOX or P O BOX or POB patterns
        if re.search(r'P\.?\s*O\.?\s*B|P\.?O\.?\s*BOX|POB|P\.O', line, re.I):
            # Try to extract the box number
            box_match = re.search(r'(?:P\.?\s*O\.?\s*B|P\.?O\.?\s*BOX|POB|P\.O).*?(\d{3,})', line, re.I)
            if box_match:
                pob_number = box_match.group(1)
                pob_line_idx = idx
                pob_text = line
                # Construct the address starting with P.O.BOX
                address_parts = [f"P.O.BOX {pob_number}"]

                # Collect following lines for city/country/additional address
                for j in range(idx + 1, min(idx + 7, len(lines))):
                    next_line = lines[j].strip()

                    # Stop at empty lines or field labels
                    if not next_line:
                        continue

                    if re.match(r'^(?:Tel|Fax|Attended|Kind|Reference|PI|Code|Type|Date|Email|Phone|Del|Customer|Cust|Ref|Invoice|Proforma)', next_line, re.I):
                        break

                    # Keep location lines - cities, countries, postal codes
                    if re.search(r'\b(DAR|DAR-ES-SALAAM|SALAAM|NAIROBI|KAMPALA|KIGALI|MOMBASA|MOSHI|ARUSHA|DODOMA)\b', next_line, re.I):
                        address_parts.append(next_line)
                    elif re.search(r'\b(TANZANIA|KENYA|UGANDA|RWANDA|BURUNDI|CONGO|MALAWI|ZAMBIA)\b', next_line, re.I):
                        address_parts.append(next_line)
                    elif len(next_line) > 2 and (next_line.isupper() or re.match(r'^[A-Z][A-Z\s\-\.,]*$', next_line)):
                        # Likely an address line (all caps or title case)
                        address_parts.append(next_line)
                    elif len(next_line) < 3:  # Very short, might be separator
                        continue
                    else:
                        break  # Stop at other content

                address = ' '.join(address_parts).strip()
                if len(address) > 8:  # Must have more than just P.O.BOX
                    break
                else:
                    address = None  # Reset if too short

    # Pattern 2: If P.O.BOX not found, look for explicit "Address" label
    if not address:
        for idx, line in enumerate(lines):
            # Look for "Address:" or "Address" at end of line
            if re.search(r'\bAddress\s*[:=]?\s*$', line, re.I) or re.search(r'\bAddress\s*[:=]\s*([^\n]+)', line, re.I):
                address_parts = []

                # Check if there's content after "Address:" on the same line
                match = re.search(r'\bAddress\s*[:=]\s*([^\n]+)', line, re.I)
                if match and match.group(1).strip():
                    address_parts.append(match.group(1).strip())

                # Collect following lines for full address (up to 6 lines)
                for j in range(idx + 1, min(idx + 7, len(lines))):
                    next_line = lines[j].strip()

                    # Stop at empty lines or field labels
                    if not next_line:
                        break

                    if re.match(r'^(?:Tel|Fax|Attended|Kind|Reference|PI|Code|Type|Date|Email|Phone|Del|Customer|Cust|Remarks|Payment|Delivery|Ref|Invoice|Proforma)', next_line, re.I):
                        break

                    # Add address lines
                    address_parts.append(next_line)

                if address_parts:
                    address = ' '.join(address_parts).strip()
                    if address:
                        break

        # Fallback: Look for city/country combinations if still no address
        if not address:
            for idx, line in enumerate(lines):
                # Look for major city names (common in East Africa)
                if re.search(r'\b(DAR|DAR-ES-SALAAM|NAIROBI|KAMPALA|KIGALI|MOMBASA|MOSHI|ARUSHA|DODOMA)\b', line, re.I):
                    address_parts = [line]

                    # Check next line(s) for country or additional address
                    for j in range(idx + 1, min(idx + 4, len(lines))):
                        next_line = lines[j].strip()

                        # Stop at empty or label lines
                        if not next_line or re.match(r'^(?:Tel|Fax|Email|Phone|Address|Reference|Code|Type|Date|Attended|Kind|Cust|Ref)', next_line, re.I):
                            break

                        # Include country or address lines
                        if re.search(r'\b(TANZANIA|KENYA|UGANDA|RWANDA|BURUNDI|CONGO|MALAWI|ZAMBIA)\b', next_line, re.I):
                            address_parts.append(next_line)
                            break
                        elif len(next_line) > 2 and (next_line.isupper() or re.search(r'\d', next_line)):
                            # Address line or postal code
                            address_parts.append(next_line)
                        else:
                            break

                    address = ' '.join(address_parts).strip()
                    if address:
                        break

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

    # Extract phone/tel - look for "Tel:" or "Tel " specifically
    phone = None

    # Use the same lines array as address extraction for consistency
    for idx, line in enumerate(lines):
        # Look for "Tel" on a line (with optional colon/equals)
        if re.search(r'\bTel\b', line, re.I):
            # Extract what comes after "Tel"
            # Try multiple patterns to be flexible
            tel_match = re.search(r'\bTel\s*[:=]?\s*([^\n]+?)(?:\s*(?:Fax|Email|Del|Attended|Kind|Reference)|$)', line, re.I)
            if tel_match:
                phone_candidate = tel_match.group(1).strip()

                # Clean up: remove trailing field labels
                phone_candidate = re.sub(r'\s+(?:Fax|Email|Del|Attended|Kind|Reference)\s*.*$', '', phone_candidate, flags=re.I).strip()

                # Must have some actual content
                if phone_candidate and len(phone_candidate) > 1:
                    # Remove leading/trailing non-alphanumeric except for +, -, /, spaces, ()
                    phone_candidate = re.sub(r'^[^\w\+\-\(]|[^\w\)]$', '', phone_candidate).strip()

                    # Accept if it has digits or is long enough to be a phone
                    if re.search(r'\d', phone_candidate) and len(phone_candidate) > 2:
                        phone = phone_candidate
                        break

    # Fallback: sometimes customer phone is a standalone number-like line (e.g., 2180007/2861940)
    if not phone:
        try:
            candidate_lines = []
            for ln in lines:
                if re.search(r'\d{3,}\s*[/\-]\s*\d{3,}', ln):
                    # Exclude typical non-phone rows
                    if re.search(r'PI\b|Invoice|Gross|Net|VAT|TSH|Qty|Rate|Value|Code|Sr\b|No\.', ln, re.I):
                        continue
                    candidate_lines.append(ln.strip())
            if candidate_lines:
                # Choose the first plausible line
                phone = candidate_lines[0]
        except Exception:
            pass

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

    # Extract PI No. / Invoice Number - IMPROVED PATTERNS
    invoice_no = None
    
    # Strategy 1: Look for "PI No." pattern with various formats
    pi_patterns = [
        r'PI\s*(?:No|Number|#)\s*[:=]\s*([^\n]+?)(?=\n|$)',
        r'PI\s*No\.?\s*[:=]?\s*([A-Z0-9\-]+)',
        r'PI\s*[:=]\s*([^\n]+?)(?=\n|$)',
        r'Proforma\s*Invoice\s*(?:No|Number|#)\s*[:=]\s*([^\n]+?)(?=\n|$)',
        r'Proforma\s*Invoice\s*[:=]\s*([^\n]+?)(?=\n|$)',
    ]
    
    for pattern in pi_patterns:
        m = re.search(pattern, normalized_text, re.I | re.MULTILINE)
        if m:
            invoice_no = m.group(1).strip()
            # Clean up trailing whitespace and field names
            invoice_no = re.sub(r'\s+(?:Date|Cust|Ref|Del|Code|Customer|Address|Tel)\b.*$', '', invoice_no, flags=re.I).strip()
            if invoice_no and len(invoice_no) > 1:
                break

    # Strategy 2: Fallback to "Invoice Number" pattern if PI No not found
    if not invoice_no:
        invoice_patterns = [
            r'Invoice\s*(?:No|Number|#)\s*[:=]\s*([^\n]+?)(?=\n|$)',
            r'Invoice\s*No\.?\s*[:=]?\s*([A-Z0-9\-]+)',
            r'Invoice\s*[:=]\s*([^\n]+?)(?=\n|$)',
        ]
        
        for pattern in invoice_patterns:
            m = re.search(pattern, normalized_text, re.I | re.MULTILINE)
            if m:
                invoice_no = m.group(1).strip()
                invoice_no = re.sub(r'\s+(?:Date|Cust|Ref|Del|Code)\b.*$', '', invoice_no, flags=re.I).strip()
                if invoice_no and len(invoice_no) > 1:
                    break

    # Strategy 3: Look for standalone invoice numbers in header section
    if not invoice_no:
        header_section = '\n'.join(cleaned_lines[:15])  # First 15 lines for header
        # Look for patterns like INV-123, PI-456, etc.
        inv_matches = re.findall(r'(?:PI|INV|Invoice)[\s\-]*([A-Z0-9\-]{3,20})', header_section, re.I)
        if inv_matches:
            invoice_no = inv_matches[0].strip()

    # Extract Date (multiple formats)
    date_str = None
    # Look for date patterns - prioritize those near labels
    date_patterns = [
        (r'(?:Invoice\s*)?Date\s*[:=]?\s*(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', True),  # "Date: DD/MM/YYYY"
        (r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})', False),  # Any date pattern (fallback)
    ]

    for pattern, is_priority in date_patterns:
        m = re.search(pattern, normalized_text, re.I)
        if m:
            date_str = m.group(1)
            if is_priority:
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

    # Extract Tax Rate (percentage) - look for patterns like "18.00%" or "18%"
    tax_rate = None
    tax_rate_pattern = re.compile(r'VAT.*?(\d+(?:\.\d+)?)\s*%|Tax\s*Rate.*?(\d+(?:\.\d+)?)\s*%', re.I)
    tax_rate_match = tax_rate_pattern.search(normalized_text)
    if tax_rate_match:
        rate_str = tax_rate_match.group(1) or tax_rate_match.group(2)
        try:
            tax_rate = Decimal(rate_str)
        except (ValueError, TypeError):
            tax_rate = None

    # Fallback: if we have subtotal and tax, calculate the tax rate
    if not tax_rate and subtotal and tax and subtotal > 0:
        try:
            tax_rate = (tax / subtotal) * Decimal('100')
        except (ValueError, TypeError, Exception):
            tax_rate = None

    # Gross Value / Total
    total = to_decimal(find_amount([
        r'Gross\s*Value',
        r'Total\s*Amount',
        r'Grand\s*Total',
        r'Total\s*(?::|\s)'
    ]))

    # Extract payment method - careful pattern to extract payment terms
    payment_method = None
    payment_pattern = re.compile(r'(?:Payment|Payment\s*Method|Payment\s*Type)\s*[:=]?\s*([^\n:{{]+?)(?=\n|$)', re.I | re.MULTILINE)
    payment_match = payment_pattern.search(normalized_text)

    if payment_match:
        payment_method = payment_match.group(1).strip()
        # Clean up
        payment_method = re.sub(r'\s+(?:Delivery|Remarks|Net|Gross|Due|NOTE)\b.*$', '', payment_method, flags=re.I).strip()

        if payment_method and len(payment_method) > 1:
            # Normalize the payment method
            payment_lower = payment_method.lower()
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

            normalized = None
            for key, val in payment_map.items():
                if key in payment_lower:
                    normalized = val
                    break

            if normalized:
                payment_method = normalized
            # Keep original if no mapping found
        else:
            payment_method = None

    # Extract delivery terms - improved pattern
    delivery_terms = None
    delivery_pattern = re.compile(r'(?:Delivery|Delivery\s*Terms)\s*[:=]?\s*([^\n:{{]+?)(?=\n|$)', re.I | re.MULTILINE)
    delivery_match = delivery_pattern.search(normalized_text)

    if delivery_match:
        delivery_terms = delivery_match.group(1).strip()
        # Clean up
        delivery_terms = re.sub(r'\s+(?:Remarks|Notes|NOTE|Net|Gross|Payment)\b.*$', '', delivery_terms, flags=re.I).strip()
        if not delivery_terms or len(delivery_terms) < 2:
            delivery_terms = None

    # Extract remarks/notes - improved pattern
    remarks = None
    remarks_pattern = re.compile(r'(?:Remarks|Notes|NOTE)\s*[:=]?\s*(.+?)(?=\n(?:Payment|Delivery|Net|Gross|NOTE|Authorized|Qty|Code)\b|$)', re.I | re.MULTILINE | re.DOTALL)
    remarks_match = remarks_pattern.search(normalized_text)

    if remarks_match:
        remarks = remarks_match.group(1).strip()
        # Clean up - remove extra spaces, newlines, and trailing labels
        remarks = ' '.join(remarks.split())
        remarks = re.sub(r'(?:\d+\s*:|^NOTE\s*\d+\s*:)', '', remarks, flags=re.I).strip()
        remarks = re.sub(r'(?:Payment|Delivery|Due|See|Qty|Code|SR)\b.*$', '', remarks, flags=re.I).strip()
        if not remarks or len(remarks) < 2:
            remarks = None

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

    # Extract line items with improved detection for various table formats
    # Strategy: Group lines by item (main description line followed by continuation lines)
    # Then parse structured data from each item group
    items = []
    item_section_started = False
    item_header_idx = -1

    # Collect all lines to process
    line_data = []
    for idx, line in enumerate(lines):
        line_stripped = line.strip()
        if not line_stripped:
            continue
        line_data.append((idx, line_stripped))

    # Find header section
    for list_idx, (idx, line_stripped) in enumerate(line_data):
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
            item_header_idx = list_idx
            continue

        # Stop at totals/summary section
        if item_section_started and list_idx > item_header_idx + 1:
            if re.search(r'(?:Net\s*Value|Gross\s*Value|Grand\s*Total|Total\s*:|Payment|Delivery|Remarks|NOTE)', line_stripped, re.I):
                break

        # Parse item lines (after header starts)
        if item_section_started and list_idx > item_header_idx:
            if not line_stripped:
                continue

            # Extract all numbers from the line
            numbers = re.findall(r'[0-9\,]+\.?\d*', line_stripped)
            float_numbers = []
            if numbers:
                for n in numbers:
                    try:
                        cleaned = n.replace(',', '').strip()
                        if cleaned and cleaned != '.' and cleaned != '':
                            float_numbers.append(float(cleaned))
                    except (ValueError, AttributeError):
                        # Skip numbers that can't be converted
                        continue

            # Detect unit/type indicators (PCS, NOS, UNT, HR, KG, etc.)
            unit_match = re.search(r'\b(NOS|PCS|KG|HR|LTR|PIECES?|UNITS?|BOX|CASE|SETS?|PC|KIT|UNT)\b', line_stripped, re.I)
            unit_value = unit_match.group(1).upper() if unit_match else None

            # Check if this line is likely a main item row (Sr No, Code, Description, amounts)
            # It should have: some text (description) and numbers (qty, rate, value)
            is_likely_item_row = len(line_stripped) > 5 and numbers and re.search(r'[A-Za-z]', line_stripped)

            # Skip if this appears to be a continuation line (lines that are just units or percentages)
            is_continuation_only = (unit_value or re.match(r'^\d+(?:\.\d+)?%?\s*$', line_stripped)) and len(float_numbers) <= 2

            if is_likely_item_row and not is_continuation_only:
                try:
                    # Extract item code - typically appears as the first numeric field after Sr No
                    item_code = None
                    description_text = line_stripped

                    # Item codes can be 3-10 digits (examples: 21004, 21019, 2132004135, 3373119002)
                    # They typically appear after the Sr No and before the description
                    code_match = re.search(r'^[\s\d]*\s+(\d{3,10})\s+', line_stripped)
                    if code_match:
                        item_code = code_match.group(1)
                        # Remove the Sr No and code from description for cleaner extraction
                        description_text = re.sub(r'^\s*\d+\s+\d{3,10}\s+', '', line_stripped).strip()
                    else:
                        # Fallback: find first numeric value that looks like a code
                        # This handles cases where spacing is different
                        first_code_match = re.search(r'\b(\d{3,10})\b', line_stripped)
                        if first_code_match:
                            item_code = first_code_match.group(1)

                    # Extract description (text portion, typically before large numeric values like rates/amounts)
                    # Look for the last sequence of letters/words before significant numbers
                    full_description = ''
                    words = description_text.split()
                    for i, word in enumerate(words):
                        # Stop when we hit a large number (amounts typically > 1000 or have comma/decimal)
                        if re.match(r'^\d+[\,\.]\d+', word) or (len(word) > 8 and re.match(r'^\d+', word)):
                            # Stop here - everything before is description
                            full_description = ' '.join(words[:i]).strip()
                            break
                        # Also check for unit keywords which typically come after description
                        elif re.match(r'^(PCS|NOS|KG|HR|LTR|PIECES|UNITS|KIT|BOX|CASE|SETS|PC|UNT)$', word, re.I):
                            # Unit found - description is everything before
                            full_description = ' '.join(words[:i]).strip()
                            break

                    # If we didn't find a stopping point, use all words with letters
                    if not full_description:
                        desc_words = [w for w in words if re.search(r'[A-Za-z]', w)]
                        if desc_words:
                            full_description = ' '.join(desc_words[:min(10, len(desc_words))]).strip()
                        else:
                            full_description = words[0] if words else ''

                    # Clean up description
                    full_description = re.sub(r'\s+', ' ', full_description).strip()
                    full_description = full_description[:255]

                    # Skip if no meaningful description
                    if not full_description or len(full_description) < 2:
                        continue

                    # Parse quantities and amounts from the extracted numbers
                    item = {
                        'description': full_description,
                        'qty': 1,
                        'unit': unit_value,
                        'value': None,
                        'rate': None,
                        'code': item_code,
                    }

                    # Parse numeric values based on count and patterns
                    max_num = max(float_numbers) if float_numbers else 0

                    if len(float_numbers) == 1:
                        # Single number: the value
                        item['value'] = to_decimal(str(float_numbers[0]))
                    elif len(float_numbers) == 2:
                        # Two numbers: likely qty and value
                        if float_numbers[0] < 100 and float_numbers[0] == int(float_numbers[0]):
                            item['qty'] = int(float_numbers[0])
                            item['value'] = to_decimal(str(float_numbers[1]))
                        elif float_numbers[1] < 100 and float_numbers[1] == int(float_numbers[1]):
                            item['qty'] = int(float_numbers[1])
                            item['value'] = to_decimal(str(float_numbers[0]))
                        else:
                            # Neither obvious, largest is value
                            item['value'] = to_decimal(str(max_num))
                    elif len(float_numbers) >= 3:
                        # Multiple numbers: typically Sr#, Code, Qty, Rate, Value
                        item['value'] = to_decimal(str(max_num))

                        # Find quantity: small integer less than 100
                        qty_candidate = None
                        for fn in float_numbers:
                            if fn == int(fn) and 0 < fn < 100 and fn != max_num:
                                qty_candidate = int(fn)
                                break

                        if qty_candidate:
                            item['qty'] = qty_candidate
                            if qty_candidate > 0 and max_num > 0:
                                item['rate'] = to_decimal(str(max_num / qty_candidate))

                    # Only add if we have meaningful data
                    if item.get('description') and (item.get('value') or item.get('qty', 1) > 1):
                        items.append(item)

                except Exception as e:
                    logger.warning(f"Error parsing item line: {line_stripped}, {e}")

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
        'tax_rate': tax_rate,
        'total': total,
        'items': items,
        'payment_method': payment_method,
        'delivery_terms': delivery_terms,
        'remarks': remarks,
        'attended_by': attended_by,
        'kind_attention': kind_attention,
        # Seller (supplier) information extracted from top of document when available
        'seller_name': seller_name,
        'seller_address': seller_address,
        'seller_phone': seller_phone,
        'seller_email': seller_email,
        'seller_tax_id': seller_tax_id,
        'seller_vat_reg': seller_vat_reg
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
            'message': 'File is empty. Please upload a valid PDF file.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Detect file type
    is_pdf = filename.lower().endswith('.pdf') or file_bytes[:4] == b'%PDF'
    is_image = filename.lower().endswith(('.jpg', '.jpeg', '.png', '.gif', '.tiff', '.bmp'))

    text = ""

    # Validate file format
    if is_image:
        return {
            'success': False,
            'error': 'image_file_not_supported',
            'message': 'Image files are not supported. Please convert to PDF or enter details manually.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    if not is_pdf:
        return {
            'success': False,
            'error': 'unsupported_file_type',
            'message': 'Please upload a PDF file.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Extract text from PDF
    try:
        text = extract_text_from_pdf(file_bytes)
    except Exception as e:
        logger.error(f"PDF text extraction failed: {e}")
        return {
            'success': False,
            'error': 'pdf_extraction_failed',
            'message': f'Could not extract text from PDF. Please enter invoice details manually.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Validate that we got text
    if not text or not text.strip():
        logger.warning("PDF text extraction returned empty text")
        return {
            'success': False,
            'error': 'no_text_extracted',
            'message': 'No readable text found in PDF (possibly a scanned image). Please enter invoice details manually.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Parse extracted text to structured invoice data
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
            'tax_rate': parsed.get('tax_rate'),
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
            try:
                value = 0
                if item.get('value'):
                    try:
                        value = float(item.get('value'))
                    except (ValueError, TypeError):
                        value = 0

                rate = None
                if item.get('rate'):
                    try:
                        rate = float(item.get('rate'))
                    except (ValueError, TypeError):
                        rate = None

                items.append({
                    'description': item.get('description', ''),
                    'qty': item.get('qty', 1),
                    'unit': item.get('unit'),
                    'code': item.get('code'),
                    'value': value,
                    'rate': rate,
                })
            except Exception as e:
                logger.warning(f"Error processing item data: {e}")
                continue

        # Check if we extracted any meaningful data
        has_customer = bool(header.get('customer_name'))
        has_items = len(items) > 0
        has_amounts = any([header.get('subtotal'), header.get('tax'), header.get('total')])

        if has_customer or has_items or has_amounts:
            logger.info(f"Successfully extracted invoice data: customer={has_customer}, items={has_items}, amounts={has_amounts}")
            return {
                'success': True,
                'header': header,
                'items': items,
                'raw_text': text,
                'ocr_available': False,
                'message': 'Invoice data extracted successfully'
            }
        else:
            logger.warning("PDF text extracted but no invoice data found after parsing")
            return {
                'success': False,
                'error': 'parsing_failed',
                'message': 'Could not extract structured data from PDF. Please enter invoice details manually.',
                'ocr_available': False,
                'header': {},
                'items': [],
                'raw_text': text
            }
    except Exception as e:
        logger.error(f"Invoice data parsing failed: {e}", exc_info=True)
        return {
            'success': False,
            'error': 'parsing_failed',
            'message': 'Could not extract structured data from PDF. Please enter invoice details manually.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': text
        }