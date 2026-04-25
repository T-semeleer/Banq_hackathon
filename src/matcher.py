import os
import json
from dataclasses import dataclass, field
from typing import Optional

import anthropic

_SYSTEM_PROMPT = """You are a receipt splitting assistant for a restaurant bill splitting app.
You receive two inputs:
1. Raw receipt text extracted via OCR from a receipt
2. A voice memo transcript where someone describes who ordered which items

Your job is to:
- Parse the receipt text to identify all line items with prices
- Detect tax (BTW/VAT/tax) and tip/service charge amounts
- Use the voice transcript to assign each item to a person using fuzzy matching
  (people say "the chicken thing", match it to "Grilled Chicken")
- Split shared items equally among the people who shared them
- Distribute tax proportionally based on each person's subtotal
- Distribute tip proportionally based on each person's subtotal
- Place items you cannot confidently match in the "unassigned" list
- Categorise the receipt into exactly one of these bunq categories based on the
  establishment name and the items on the receipt:
  • FOOD_AND_DRINK   — restaurants, cafes, bars, fast food, takeaway, delivery, coffee shops,
                       items like meals, drinks, alcohol, coffee, pizza, sushi, burger
  • GROCERIES        — supermarkets (Albert Heijn, Jumbo, Lidl, Aldi, etc.), grocery stores,
                       items like fruit, vegetables, dairy, bread, meat, cleaning products
  • TRANSPORT        — trains (NS), buses, trams, metro, taxis, Uber, petrol stations,
                       parking, ferry, flights, OV-chipkaart
  • ENTERTAINMENT    — cinema (Pathé), theatre, concerts, events, streaming services,
                       museums, theme parks, sports, gaming
  • SHOPPING         — clothing, electronics, furniture, home goods, department stores,
                       online retail (bol.com, Coolblue, Amazon), shoes, accessories
  • HEALTH_AND_BEAUTY — pharmacy (Etos, Kruidvat), doctor, gym, beauty salon, cosmetics,
                       vitamins, medicines, dental, optician
  • BILLS_AND_UTILITIES — electricity, gas, water, internet, phone/mobile (Vodafone, KPN),
                          rent, insurance, subscriptions (Netflix, Spotify)

Rules:
- "I" or "me" in the transcript refers to the person who recorded the memo — call them "You"
- Items mentioned without a clear owner go to "unassigned"
- If the transcript says "split evenly", "split equally", "divide equally", or similar with no names, split everything equally between "You" and "Person 2"
- If the transcript says "split X ways" or "between N people" with no names, create N people: "You", "Person 2", "Person 3", etc. and split all items equally
- If a price is not explicitly on the receipt, estimate 0.00
- Always output valid JSON, no explanatory text outside the JSON block
- Output compact JSON (no extra whitespace or indentation)
- Round all monetary values to 2 decimal places"""

_USER_TEMPLATE = """RECEIPT TEXT (from OCR):
---
{ocr_text}
---

VOICE TRANSCRIPT:
---
{transcript}
---

Output ONLY a JSON object with this exact structure (category must be one of:
FOOD_AND_DRINK, GROCERIES, TRANSPORT, ENTERTAINMENT, SHOPPING, HEALTH_AND_BEAUTY, BILLS_AND_UTILITIES):
{{
  "category": "FOOD_AND_DRINK",
  "people": [
    {{
      "name": "string",
      "items": [{{"name": "string", "price": 0.00}}],
      "subtotal": 0.00,
      "tax_share": 0.00,
      "tip_share": 0.00,
      "total_owed": 0.00
    }}
  ],
  "unassigned": [{{"name": "string", "price": 0.00}}],
  "total": 0.00,
  "tax": 0.00,
  "tip": 0.00
}}"""


@dataclass
class ReceiptItem:
    name: str
    price: float


@dataclass
class PersonShare:
    name: str
    items: list[ReceiptItem]
    subtotal: float
    tax_share: float
    tip_share: float
    total_owed: float


@dataclass
class SplitResult:
    people: list[PersonShare]
    unassigned: list[ReceiptItem]
    total: float
    tax: float
    tip: float
    category: str = "OTHER"


_GROCERY_KW = {
    "apple","banana","orange","pear","grape","strawberry","blueberry","kiwi",
    "watermelon","lemon","raspberry","milk","cheese","yogurt","bread","butter",
    "egg","meat","chicken","fish","vegetable","salad","rice","pasta","cereal",
    "juice","water","soda","coffee","tea","snack","chips","chocolate","sugar",
    "flour","sauce","oil","vinegar","soup","frozen","detergent","shampoo",
}
_RESTAURANT_KW = {
    "burger","pizza","sushi","taco","steak","wine","beer","cocktail","dessert",
    "appetizer","entree","main course","starter","grill","fries","sandwich",
    "wrap","noodle","ramen","curry","dal","kebab","schnitzel","risotto",
    "carbonara","bolognese","tiramisu","bruschetta","antipasto","draft",
    "sparkling","still water","espresso","latte","cappuccino","mojito",
}

_CATEGORY_KEYWORDS: dict[str, set] = {
    "GROCERIES":           _GROCERY_KW,
    "FOOD_AND_DRINK":      _RESTAURANT_KW,
    "TRANSPORT":           {"train","bus","tram","metro","taxi","uber","parking","fuel","petrol","flight","ferry","ticket","ovchip","ov-chip"},
    "ENTERTAINMENT":       {"cinema","movie","concert","ticket","game","museum","theme park","streaming","netflix","spotify","event"},
    "SHOPPING":            {"shirt","dress","shoe","jacket","bag","laptop","phone","book","furniture","clothing","accessory"},
    "HEALTH_AND_BEAUTY":   {"medicine","vitamin","supplement","shampoo","soap","cream","pharmacy","dental","prescription","cosmetic"},
    "BILLS_AND_UTILITIES":  {"electricity","gas","water bill","internet","subscription","insurance","rent","mobile","phone plan"},
}


def categorize_from_items(item_names: list[str]) -> str:
    """Keyword-match item names to a bunq category. Falls back to FOOD_AND_DRINK."""
    text = " ".join(item_names).lower()
    scores: dict[str, int] = {cat: 0 for cat in _CATEGORY_KEYWORDS}
    for cat, kws in _CATEGORY_KEYWORDS.items():
        for kw in kws:
            if kw in text:
                scores[cat] += 1
    best = max(scores, key=lambda c: scores[c])
    return best if scores[best] > 0 else "FOOD_AND_DRINK"


def match(ocr_text: str, transcript: str) -> SplitResult:
    """Send OCR text + audio transcript to Claude Sonnet and return a structured split."""
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8192,
        system=_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": _USER_TEMPLATE.format(
                    ocr_text=ocr_text.strip(),
                    transcript=transcript.strip(),
                ),
            }
        ],
    )

    if response.stop_reason == "max_tokens":
        raise ValueError("Receipt is too large to process — try with fewer items.")

    text = response.content[0].text.strip()
    # Extract the JSON object regardless of surrounding prose or markdown fences
    start = text.find('{')
    end = text.rfind('}')
    if start == -1 or end == -1 or end <= start:
        raise ValueError(f"No JSON object found in model response: {text[:200]!r}")
    text = text[start:end + 1]
    raw = json.loads(text)
    return _parse(raw)


def _parse(raw: dict) -> SplitResult:
    people = [
        PersonShare(
            name=p["name"],
            items=[ReceiptItem(**i) for i in p["items"]],
            subtotal=p["subtotal"],
            tax_share=p["tax_share"],
            tip_share=p["tip_share"],
            total_owed=p["total_owed"],
        )
        for p in raw.get("people", [])
    ]
    unassigned = [ReceiptItem(**i) for i in raw.get("unassigned", [])]
    return SplitResult(
        people=people,
        unassigned=unassigned,
        total=raw.get("total", 0.0),
        tax=raw.get("tax", 0.0),
        tip=raw.get("tip", 0.0),
        category=raw.get("category") or "FOOD_AND_DRINK",
    )


def result_to_dict(result: SplitResult) -> dict:
    """Serialise SplitResult to a plain dict (ready for JSON / DynamoDB)."""
    return {
        "people": [
            {
                "name": p.name,
                "items": [{"name": i.name, "price": i.price} for i in p.items],
                "subtotal": p.subtotal,
                "tax_share": p.tax_share,
                "tip_share": p.tip_share,
                "total_owed": p.total_owed,
                "bunqme_url": None,
                "payment_status": "pending",
            }
            for p in result.people
        ],
        "unassigned": [{"name": i.name, "price": i.price} for i in result.unassigned],
        "total": result.total,
        "tax": result.tax,
        "tip": result.tip,
        "category": result.category,
        "status": "review",
    }


if __name__ == "__main__":
    import sys
    from dotenv import load_dotenv

    load_dotenv()

    # Quick smoke test with hardcoded sample data
    sample_ocr = """
    THE BISTRO
    Table 4 - 3 guests
    Grilled Chicken       14.50
    Caesar Salad          11.00
    Pasta Carbonara       13.50
    Draft Beer             5.00
    Sparkling Water        3.50
    -------------------------
    Subtotal              47.50
    BTW (21%)              9.98
    Total                 57.48
    """

    sample_transcript = (
        "I had the grilled chicken and a sparkling water. "
        "Sarah had the caesar salad. Tom got the pasta and a beer."
    )

    if len(sys.argv) == 3:
        sample_ocr = open(sys.argv[1]).read()
        sample_transcript = open(sys.argv[2]).read()

    result = match(sample_ocr, sample_transcript)
    print(json.dumps(result_to_dict(result), indent=2))
