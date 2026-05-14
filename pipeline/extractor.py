"""Extract fund-NAV table from an uploaded screenshot.

Primary path: Claude vision API (set ANTHROPIC_API_KEY).
Fallback: a sidecar JSON next to the image, e.g. foo.png -> foo.json.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Optional

MODEL = "claude-opus-4-7"

EXTRACTION_PROMPT = """You are an OCR + structuring tool. The image is a single
Chinese-language fund NAV summary table that always has these rows:

  row 1: header with one date cell (YYYYMMDD) and N product-name cells
  row 2: 基金单位净值       (unit NAV, decimal)
  row 3: 今年以来收益率     (YTD return, percent)
  row 4: 单日单位净值变动   (daily NAV change, percent)

Return ONLY a JSON object, no prose, no markdown fences, matching:

{
  "date": "YYYY-MM-DD",
  "products": [
    {"name": "...", "nav": 1.2345, "ytd_return_pct": 1.23, "daily_change_pct": 0.45}
  ]
}

Percent values are numbers WITHOUT the % sign (1.23 means 1.23%, not 0.0123).
Negative values keep their sign. Preserve product order left-to-right."""


@dataclass
class Product:
    name: str
    nav: float
    ytd_return_pct: float
    daily_change_pct: float


@dataclass
class Extraction:
    date: str
    products: list[Product]

    def to_dict(self) -> dict:
        return {"date": self.date, "products": [asdict(p) for p in self.products]}


def _from_dict(d: dict) -> Extraction:
    return Extraction(
        date=d["date"],
        products=[Product(**p) for p in d["products"]],
    )


def _sidecar_path(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def _normalize_date(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 8:
        return f"{digits[:4]}-{digits[4:6]}-{digits[6:]}"
    return raw


def _call_claude(image_path: Path) -> dict:
    import anthropic  # imported lazily; only needed for the API path

    client = anthropic.Anthropic()
    media_type = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg",
                  "webp": "image/webp", "gif": "image/gif"}[image_path.suffix.lower().lstrip(".")]
    b64 = base64.standard_b64encode(image_path.read_bytes()).decode()

    resp = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image", "source": {"type": "base64",
                                             "media_type": media_type, "data": b64}},
                {"type": "text", "text": EXTRACTION_PROMPT},
            ],
        }],
    )
    text = "".join(b.text for b in resp.content if b.type == "text").strip()
    text = re.sub(r"^```(?:json)?|```$", "", text, flags=re.MULTILINE).strip()
    return json.loads(text)


def extract(image_path: str | Path, *, save_json: bool = True) -> Extraction:
    image_path = Path(image_path)
    sidecar = _sidecar_path(image_path)

    if sidecar.exists():
        raw = json.loads(sidecar.read_text(encoding="utf-8"))
    elif os.environ.get("ANTHROPIC_API_KEY"):
        raw = _call_claude(image_path)
    else:
        raise RuntimeError(
            f"No sidecar {sidecar.name} found and ANTHROPIC_API_KEY is unset. "
            "Either set the env var or provide a JSON file next to the image."
        )

    raw["date"] = _normalize_date(raw["date"])
    extraction = _from_dict(raw)

    if save_json and not sidecar.exists():
        sidecar.write_text(json.dumps(extraction.to_dict(), ensure_ascii=False, indent=2),
                           encoding="utf-8")
    return extraction


if __name__ == "__main__":
    import sys
    e = extract(sys.argv[1])
    print(json.dumps(e.to_dict(), ensure_ascii=False, indent=2))
