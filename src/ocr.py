import os
import uuid
import boto3
from pathlib import Path
from dataclasses import dataclass, field


@dataclass
class ReceiptItem:
    name: str
    price: float


@dataclass
class ReceiptResult:
    items: list[ReceiptItem]
    total: float | None
    tax: float | None
    vendor: str | None
    image_url: str


def upload_to_s3(image_path: Path | str) -> tuple[str, str]:
    """Upload receipt image to S3, return (s3_key, public_url)."""
    bucket = os.environ["S3_BUCKET"]
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    s3 = boto3.client(
        "s3",
        region_name=region,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )

    image_path = Path(image_path)
    suffix = image_path.suffix or ".jpg"
    s3_key = f"receipts/{uuid.uuid4().hex}{suffix}"

    s3.upload_file(
        str(image_path),
        bucket,
        s3_key,
        ExtraArgs={"ContentType": _content_type(suffix)},
    )

    image_url = f"https://{bucket}.s3.{region}.amazonaws.com/{s3_key}"
    return s3_key, image_url


def analyze_receipt(s3_key: str) -> dict:
    """Call Textract AnalyzeExpense on an S3 object, return raw response."""
    bucket = os.environ["S3_BUCKET"]
    region = os.environ.get("AWS_DEFAULT_REGION", "us-east-1")

    textract = boto3.client(
        "textract",
        region_name=region,
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
    )

    return textract.analyze_expense(
        Document={"S3Object": {"Bucket": bucket, "Name": s3_key}}
    )


def parse_response(response: dict, image_url: str) -> ReceiptResult:
    """Extract items, totals, and vendor from a Textract AnalyzeExpense response."""
    items: list[ReceiptItem] = []
    total: float | None = None
    tax: float | None = None
    vendor: str | None = None

    for doc in response.get("ExpenseDocuments", []):
        # Summary fields: TOTAL, TAX, VENDOR_NAME, etc.
        for field in doc.get("SummaryFields", []):
            field_type = field.get("Type", {}).get("Text", "")
            value_text = field.get("Amount", field.get("ValueDetection", {})).get("Text", "")

            if field_type == "TOTAL":
                total = _parse_price(value_text)
            elif field_type in ("TAX", "TAX_AMOUNT"):
                tax = _parse_price(value_text)
            elif field_type == "VENDOR_NAME":
                vendor = value_text.strip() or None

        # Line items
        for group in doc.get("LineItemGroups", []):
            for line_item in group.get("LineItems", []):
                name: str | None = None
                price: float | None = None

                for expense_field in line_item.get("LineItemExpenseFields", []):
                    f_type = expense_field.get("Type", {}).get("Text", "")
                    f_value = expense_field.get("ValueDetection", {}).get("Text", "")

                    if f_type == "ITEM":
                        name = f_value.strip() or None
                    elif f_type == "PRICE":
                        price = _parse_price(f_value)

                if name and price is not None:
                    items.append(ReceiptItem(name=name, price=price))

    return ReceiptResult(
        items=items,
        total=total,
        tax=tax,
        vendor=vendor,
        image_url=image_url,
    )


def process_receipt(image_path: Path | str) -> ReceiptResult:
    """Full pipeline: upload to S3, analyze with Textract, parse results."""
    s3_key, image_url = upload_to_s3(image_path)
    response = analyze_receipt(s3_key)
    return parse_response(response, image_url)


# ── helpers ──────────────────────────────────────────────────────────────────

def _parse_price(text: str) -> float | None:
    """Strip currency symbols and parse a price string to float."""
    cleaned = text.replace("$", "").replace("€", "").replace("£", "").replace(",", "").strip()
    try:
        return float(cleaned)
    except ValueError:
        return None


def _content_type(suffix: str) -> str:
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".heic": "image/heic",
    }.get(suffix.lower(), "image/jpeg")


# ── CLI (testing) ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python src/ocr.py <path-to-receipt-image>")
        sys.exit(1)

    from dotenv import load_dotenv
    load_dotenv()

    result = process_receipt(sys.argv[1])

    print(f"Vendor : {result.vendor or '(unknown)'}")
    print(f"Image  : {result.image_url}")
    print(f"Items  :")
    for item in result.items:
        print(f"  {item.name:<35} €{item.price:.2f}")
    print(f"Tax    : {f'€{result.tax:.2f}' if result.tax is not None else '(none)'}")
    print(f"Total  : {f'€{result.total:.2f}' if result.total is not None else '(none)'}")
