from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Product:
    sku: str            # f"{scraper.name}:{external_id}" — globally unique
    supplier: str       # human-facing supplier name (e.g. "모모스커피")
    name: str
    origin: Optional[str]      # country (best-effort)
    process: Optional[str]     # Washed / Natural / Honey / ...
    price_krw: Optional[int]   # KRW, as listed on the page (might not be /kg)
    unit_g: Optional[int]      # grams in the listed unit (None if unknown)
    url: str
    in_stock: bool

    @property
    def price_per_kg(self) -> Optional[int]:
        if self.price_krw is None or not self.unit_g:
            return None
        return round(self.price_krw / self.unit_g * 1000)

    def to_dict(self) -> dict:
        return asdict(self)
