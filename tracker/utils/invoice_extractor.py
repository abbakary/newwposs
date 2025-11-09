"""
Simple OCR + regex-based invoice extractor using pytesseract and OpenCV.
This is a pragmatic extractor intended for Phase-1: reasonably-structured invoices
(like the Superdoll example). It returns a dict with header fields and a list of items.

If pytesseract or OpenCV are not installed, falls back to regex-based extraction on plain text.
"""
from PIL import Image
import io
import re
import logging
from decimal import Decimal

try:
    import pytesseract
except Exception:
    pytesseract = None

try:
    import cv2
    import numpy as np
except Exception:
    cv2 = None
    np = None

logger = logging.getLogger(__name__)

# Check if dependencies are available
OCR_AVAILABLE = pytesseract is not None and cv2 is not None


def _image_from_bytes(file_bytes):
    return Image.open(io.BytesIO(file_bytes)).convert('RGB')


def preprocess_image_pil(img_pil):
    """Convert PIL image -> OpenCV -> simple preprocessing -> back to PIL"""
    if cv2 is None or np is None:
        return img_pil
    arr = np.array(img_pil)
    # Convert to gray
    gray = cv2.cvtColor(arr, cv2.COLOR_RGB2GRAY)
    # Resize if too small
    h, w = gray.shape[:2]
    if w < 1000:
        scale = 1000.0 / w
        gray = cv2.resize(gray, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LINEAR)
    # Denoise and threshold
    blur = cv2.medianBlur(gray, 3)
    _, th = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    # Convert back to PIL
    return Image.fromarray(th)


def ocr_image(img_pil):
    """Extract text from image using pytesseract OCR.

    Args:
        img_pil: PIL Image object

    Returns:
        Extracted text string

    Raises:
        RuntimeError: If pytesseract is not available
    """
    if pytesseract is None:
        raise RuntimeError('pytesseract is not available. Please install: pip install pytesseract')
    if cv2 is None:
        raise RuntimeError('OpenCV is not available. Please install: pip install opencv-python')

    try:
        # Simple config: treat as single column text but allow some detection
        config = '--psm 6'
        text = pytesseract.image_to_string(img_pil, config=config)
        return text
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        raise RuntimeError(f'OCR extraction failed: {str(e)}')


def extract_header_fields(text):
    # Helper to find first match group with flexible spacing
    def find(pattern, flags=re.I | re.MULTILINE):
        m = re.search(pattern, text, flags)
        if m:
            result = m.group(1).strip() if m.lastindex and m.lastindex >= 1 else m.group(0).strip()
            return ' '.join(result.split()) if result else None
        return None

    invoice_no = find(r'(?:PI|P\.?I\.?|Invoice|Invoice\s*(?:Number|No)|PI\s*No)[\s:\-]*([A-Z0-9\-\/]+)')
    code_no = find(r'(?:Code\s*(?:No|Number)|Code\s*#)[\s:\-]*([A-Z0-9\-\/]+)')
    date_str = find(r'(?:Date|Invoice\s*Date)[\s:\-]*([0-3]?\d[\s/\-][01]?\d[\s/\-]\d{2,4})')
    customer_name = find(r'(?:Customer\s*Name|Customer|Bill\s*To|Buyer|TO)[\s:\-]*([A-Z][^\n\r\:]{3,150})')
    address = find(r'(?:Address|Addr\.|Add)[\s:\-]*([^\n\r]{5,200})')
    phone = find(r'(?:Tel|Telephone|Phone|Mobile)[\s:\-]*(\+?[0-9\s\-\(\)\.]{7,25})')
    email = find(r'(?:Email|E-mail)[\s:\-]*([^\s\n\r:@]+@[^\s\n\r:]+)')
    reference = find(r'(?:Reference|Ref\.?|FOR)[\s:\-]*([A-Z0-9\s\-\/]{3,50})')

    # Totals
    net = find(r'(?:Net\s*Value|Net|Subtotal)[\s:\-]*(?:TSH)?\s*([0-9\,]+\.?\d{0,2})')
    vat = find(r'(?:VAT|Tax|GST)[\s:\-]*(?:TSH)?\s*([0-9\,]+\.?\d{0,2})')
    gross = find(r'(?:Gross\s*Value|Gross|Total\s*Amount|Total)[\s:\-]*(?:TSH)?\s*([0-9\,]+\.?\d{0,2})')

    def to_decimal(s):
        try:
            if s:
                cleaned = re.sub(r'[^\d\.\,\-]', '', str(s)).strip()
                return Decimal(cleaned.replace(',', ''))
        except Exception:
            return None

    return {
        'invoice_no': invoice_no,
        'code_no': code_no,
        'date': date_str,
        'customer_name': customer_name,
        'address': address,
        'phone': phone,
        'email': email,
        'reference': reference,
        'net_value': to_decimal(net) if net else None,
        'vat': to_decimal(vat) if vat else None,
        'gross_value': to_decimal(gross) if gross else None,
    }


def extract_line_items(text):
    """Very simple heuristic to extract lines that look like: Sr  ItemCode  Description  Qty  Rate  Value
    We will scan lines and pick those containing at least two numbers and one large number-looking value.
    """
    items = []
    lines = [l.strip() for l in text.splitlines() if l.strip()]
    # Try to find the table header index by looking for 'Item' and 'Qty' and 'Value'
    header_idx = None
    for idx, line in enumerate(lines[:30]):
        if re.search(r'\b(Item|Description)\b', line, re.I) and re.search(r'\bQty\b', line, re.I):
            header_idx = idx
            break
    # If header found, parse subsequent lines
    start = header_idx + 1 if header_idx is not None else 0
    for line in lines[start:]:
        # stop if footer keywords
        if re.search(r'\b(Net Value|Total|Gross Value|VAT|Payment)\b', line, re.I):
            break
        # Find numbers with decimal or commas
        numbers = re.findall(r'[0-9\,]+\.?\d*', line)
        if len(numbers) >= 2:
            # Heuristic mapping
            # Try to capture item code as first short number
            item_code = None
            qty = None
            rate = None
            value = None
            # If line starts with serial and item code
            parts = re.split(r'\s{2,}|\t', line)
            # fallback: split by spaces
            if len(parts) < 3:
                parts = line.split()
            # Find last numeric token as value
            numeric_tokens = re.findall(r'([0-9\,]+\.?\d*)', line)
            if numeric_tokens:
                value = numeric_tokens[-1]
            # qty is likely a small integer near end
            if len(numeric_tokens) >= 2:
                qty = numeric_tokens[-2]
            # try to find item code as first token with 3-6 digits
            m = re.search(r'\b(\d{3,6})\b', line)
            if m:
                item_code = m.group(1)
            # description: remove numeric tokens from line
            desc = re.sub(r'[0-9\,]+\.?\d*', '', line).strip()
            # Clean values
            def clean_num(s):
                try:
                    return Decimal(s.replace(',', ''))
                except Exception:
                    return None
            items.append({
                'item_code': item_code,
                'description': desc[:255],
                'qty': Decimal(qty.replace(',', '')) if qty and re.match(r'^[0-9\,]+\.?\d*$', qty) else None,
                'rate': clean_num(rate) if rate else None,
                'value': clean_num(value) if value else None,
            })
    return items


def extract_from_bytes(file_bytes):
    """Main entry: take raw bytes, preprocess, OCR, parse and return result dict.

    If OCR dependencies are not available, returns a success response with empty data
    so the user can manually enter invoice details.

    Args:
        file_bytes: Raw bytes of uploaded file (PDF or image)

    Returns:
        dict with keys: success, header, items, raw_text, message, ocr_available
    """
    # Check if OCR is actually available
    if not OCR_AVAILABLE:
        logger.warning("OCR dependencies not available. Returning empty extraction for manual entry.")
        return {
            'success': False,
            'error': 'ocr_unavailable',
            'message': 'OCR extraction is not available in this environment. Please manually enter invoice details.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Try to open the file as an image
    try:
        img = _image_from_bytes(file_bytes)
    except Exception as e:
        logger.warning(f"Failed to open uploaded file as image: {e}")
        return {
            'success': False,
            'error': 'invalid_image',
            'message': f'Could not open file as image: {str(e)}',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Preprocess the image
    try:
        proc = preprocess_image_pil(img)
    except Exception as e:
        logger.warning(f"Image preprocessing failed: {e}")
        proc = img

    # Try OCR
    try:
        text = ocr_image(proc)
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return {
            'success': False,
            'error': 'ocr_failed',
            'message': f'OCR extraction failed: {str(e)}. Please manually enter invoice details.',
            'ocr_available': False,
            'header': {},
            'items': [],
            'raw_text': ''
        }

    # Extract structured data from OCR text
    try:
        header = extract_header_fields(text)
        items = extract_line_items(text)
    except Exception as e:
        logger.warning(f"Failed to parse extracted text: {e}")
        header = {}
        items = []

    result = {
        'success': True,
        'header': header,
        'items': items,
        'raw_text': text,
        'ocr_available': True
    }
    return result
