"""Run all test receipts through the OCR pipeline and print results."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.ocr import process_receipt

RECEIPTS = sorted(Path("test_receipts").glob("*.jpg"))

SEPARATOR = "─" * 55


def run():
    passed = 0
    failed = 0

    for receipt_path in RECEIPTS:
        print(f"\n{SEPARATOR}")
        print(f"Receipt : {receipt_path.name}")
        print(SEPARATOR)

        try:
            result = process_receipt(receipt_path)

            print(f"Vendor  : {result.vendor or '(not detected)'}")
            print(f"Items   :")
            for item in result.items:
                print(f"  {item.name:<40} {item.price:>7.2f}")
            if not result.items:
                print("  (no line items extracted)")
            print(f"Tax     : {f'{result.tax:.2f}' if result.tax is not None else '(none)'}")
            print(f"Total   : {f'{result.total:.2f}' if result.total is not None else '(none)'}")
            print(f"Image   : {result.image_url}")

            # Basic assertions
            assert isinstance(result.items, list), "items must be a list"
            assert result.image_url.startswith("https://"), "image_url must be HTTPS"

            print(f"Result  : PASS ({len(result.items)} items extracted)")
            passed += 1

        except Exception as e:
            print(f"Result  : FAIL — {e}")
            failed += 1

    print(f"\n{SEPARATOR}")
    print(f"Summary : {passed} passed, {failed} failed out of {len(RECEIPTS)} receipts")
    print(SEPARATOR)
    return failed


if __name__ == "__main__":
    sys.exit(run())
