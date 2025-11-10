#!/usr/bin/env python
"""
Debug script to test extraction with actual PDF content
Tests Superdoll Invoice T 964 DNA - the invoice from the user
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from tracker.utils.pdf_text_extractor import parse_invoice_data

# Superdoll Invoice T 964 DNA (single line item)
superdoll_t964_text = """Superdoll Trailer Manufacture Co. (T) Ltd.
P.O. Box 16541 DSM, Tel.+255-22-2860930-2863467, Fax +255-22-2865412/3, Email: stm@superdoll-tz.com,Tax ID No.100-199-157, VAT Reg. No.10-0085-15-E
P.O.BOX 2517
A01218
27/10/2025
PI-1765684
STEERING AXLE
ALIGNMENT
1 41003
NOS
Sr
No.
Item Code Description 
2180007/2861940
Proforma Invoice
Code No
Customer Name SAID SALIM BAKHRESA CO LTD
Address
Tel Fax
Del. Date
PI No.
Date
Cust Ref
Ref Date
Authorised Signatory
27/10/2025
DAR-ES-SALAAM
TANZANIA
1
Qty
Kind Attn Valued Customer
Reference
 100,000.00
Rate
 100,000.00
Value
Payment
Delivery
Net Value
Type 
 100,000.00
ex-stock
Cash/Chq on Delivery
Attended By Sales Point
Remarks Looking forward to your conformed order
TSH TSH
Gross Value
VAT 18,000.00
TSH 118,000.00
:
:
:
: :
:
:
:
:
:
:
:
:
Dear Sir/Madam,
We thank you for your valued enquiry. As desired please find below our detailed best offer
:
:
:
:
:
:
FOR T 964 DNA
4 : Duty and VAT exemption documents to be submitted with the Purchase Order. FRM-STM-SAL-01A
Page 1 of 1"""

def print_extraction_results(test_name, result):
    print("\n" + "=" * 75)
    print(f"TEST: {test_name}")
    print("=" * 75)

    print("\n--- HEADER INFORMATION ---")
    print(f"Invoice No (PI No): {result['invoice_no']}")
    print(f"Code No: {result['code_no']}")
    print(f"Date: {result['date']}")
    print(f"Customer Name: {result['customer_name']}")
    print(f"Address: {result['address']}")
    print(f"Phone: {result['phone']}")
    print(f"Email: {result['email']}")
    print(f"Reference: {result['reference']}")

    print("\n--- MONETARY AMOUNTS ---")
    print(f"Subtotal (Net Value): {result['subtotal']}")
    print(f"Tax (VAT): {result['tax']}")
    print(f"Tax Rate: {result['tax_rate']}")
    print(f"Total (Gross Value): {result['total']}")

    print("\n--- ADDITIONAL FIELDS ---")
    print(f"Payment Method: {result['payment_method']}")
    print(f"Delivery Terms: {result['delivery_terms']}")
    print(f"Remarks: {result['remarks']}")
    print(f"Attended By: {result['attended_by']}")
    print(f"Kind Attention: {result['kind_attention']}")

    print("\n--- LINE ITEMS ({} items extracted) ---".format(len(result['items'])))
    for idx, item in enumerate(result['items'], 1):
        print(f"\nItem {idx}:")
        print(f"  Code: {item.get('code')}")
        print(f"  Description: {item.get('description')}")
        print(f"  Unit: {item.get('unit')}")
        print(f"  Qty: {item.get('qty')}")
        print(f"  Rate: {item.get('rate')}")
        print(f"  Value: {item.get('value')}")

    print("\n--- SELLER INFORMATION ---")
    print(f"Seller Name: {result['seller_name']}")
    print(f"Seller Address: {result['seller_address']}")
    print(f"Seller Phone: {result['seller_phone']}")
    print(f"Seller Email: {result['seller_email']}")
    print(f"Seller Tax ID: {result['seller_tax_id']}")
    print(f"Seller VAT Reg: {result['seller_vat_reg']}")

def print_expected_results():
    print("\n" + "=" * 75)
    print("EXPECTED EXTRACTION RESULTS FOR T 964 DNA")
    print("=" * 75)

    print("\nHeader Information:")
    print("  Code No: A01218")
    print("  Invoice No: PI-1765684")
    print("  Date: 27/10/2025")
    print("  Customer Name: SAID SALIM BAKHRESA CO LTD")
    print("  Address: P.O.BOX 2517 DAR-ES-SALAAM TANZANIA")
    print("  Phone: 2180007/2861940 (extracted)")
    print("  Email: stm@superdoll-tz.com")
    print("  Reference: FOR T 964 DNA")

    print("\nMonetary:")
    print("  Subtotal (Net Value): 100000.00")
    print("  Tax (VAT): 18000.00")
    print("  Total (Gross Value): 118000.00")
    print("  Tax Rate: 18%")

    print("\nAdditional:")
    print("  Payment Method: on_delivery")
    print("  Delivery Terms: ex-stock")
    print("  Remarks: Looking forward to your conformed order")
    print("  Attended By: Sales Point")
    print("  Kind Attention: Valued Customer")

    print("\nLine Items (1 item expected):")
    print("  Item 1:")
    print("    Code: 41003")
    print("    Description: STEERING AXLE ALIGNMENT")
    print("    Unit: NOS")
    print("    Qty: 1")
    print("    Rate: 100000.00")
    print("    Value: 100000.00")

    print("\nSeller Information:")
    print("  Name: Superdoll Trailer Manufacture Co. (T) Ltd.")
    print("  Email: stm@superdoll-tz.com")
    print("  Tax ID: 100-199-157")
    print("  VAT Reg: 10-0085-15-E")

# Parse the invoice data
result = parse_invoice_data(superdoll_t964_text)

# Display results
print_extraction_results("Superdoll Invoice T 964 DNA", result)
print_expected_results()

# Verify critical fields
print("\n" + "=" * 75)
print("VALIDATION CHECK")
print("=" * 75)

issues = []

# Check customer name
if result['customer_name'] != 'SAID SALIM BAKHRESA CO LTD':
    issues.append(f"✗ Customer Name: Expected 'SAID SALIM BAKHRESA CO LTD', got '{result['customer_name']}'")
else:
    print("✓ Customer Name correctly extracted")

# Check address
if result['address'] and 'P.O.BOX 2517' in result['address'] and 'DAR' in result['address']:
    print("✓ Address correctly extracted")
else:
    issues.append(f"✗ Address: Expected 'P.O.BOX 2517 DAR-ES-SALAAM TANZANIA', got '{result['address']}'")

# Check invoice number
if result['invoice_no'] == 'PI-1765684':
    print("✓ Invoice Number correctly extracted")
else:
    issues.append(f"✗ Invoice Number: Expected 'PI-1765684', got '{result['invoice_no']}'")

# Check monetary values
if result['subtotal'] and float(result['subtotal']) == 100000.00:
    print("✓ Subtotal correctly extracted")
else:
    issues.append(f"✗ Subtotal: Expected 100000.00, got {result['subtotal']}")

if result['tax'] and float(result['tax']) == 18000.00:
    print("✓ VAT correctly extracted")
else:
    issues.append(f"✗ VAT: Expected 18000.00, got {result['tax']}")

if result['total'] and float(result['total']) == 118000.00:
    print("✓ Total correctly extracted")
else:
    issues.append(f"✗ Total: Expected 118000.00, got {result['total']}")

# Check line items
if len(result['items']) == 1:
    item = result['items'][0]
    if item.get('code') == '41003' and item.get('qty') == 1 and item.get('value') == 100000.00:
        print("✓ Line item correctly extracted")
    else:
        issues.append(f"✗ Line item data incorrect: {item}")
else:
    issues.append(f"✗ Line items: Expected 1 item, got {len(result['items'])}")

if issues:
    print("\n" + "=" * 75)
    print("ISSUES FOUND:")
    print("=" * 75)
    for issue in issues:
        print(issue)
else:
    print("\n" + "=" * 75)
    print("✓ ALL VALIDATIONS PASSED!")
    print("=" * 75)
