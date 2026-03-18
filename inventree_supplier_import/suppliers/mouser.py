"""Mouser Electronics supplier adapter."""

import requests


class MouserSupplier:
    NAME = "Mouser"
    BASE_URL = "https://api.mouser.com/api/v1"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def fetch_part(self, sku: str) -> dict | None:
        """Fetch part data from Mouser API by SKU."""
        url = f"{self.BASE_URL}/search/partnumber"
        payload = {
            "SearchByPartRequest": {
                "mouserPartNumber": sku,
                "partSearchOptions": "Exact",
            }
        }
        params = {"apiKey": self.api_key}

        resp = requests.post(url, json=payload, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        parts = data.get("SearchResults", {}).get("Parts", [])
        if not parts:
            return None

        part = parts[0]
        price_breaks = []
        for pb in part.get("PriceBreaks", []):
            try:
                price_breaks.append({
                    "quantity": int(pb.get("Quantity", 1)),
                    "price": float(pb.get("Price", "0").replace(",", ".")),
                    "currency": pb.get("Currency", "EUR"),
                })
            except (ValueError, TypeError):
                continue

        return {
            "name": part.get("ManufacturerPartNumber", sku),
            "description": part.get("Description", ""),
            "manufacturer": part.get("Manufacturer", ""),
            "supplier_sku": part.get("MouserPartNumber", sku),
            "supplier_name": self.NAME,
            "datasheet": part.get("DataSheetUrl", ""),
            "image": part.get("ImagePath", ""),
            "category_path": part.get("Category", ""),
            "stock": part.get("AvailabilityInStock", ""),
            "price_breaks": price_breaks,
        }
