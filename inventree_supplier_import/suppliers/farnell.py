"""Farnell / Element14 supplier adapter."""

import requests


class FarnellSupplier:
    NAME = "Farnell"
    BASE_URL = "https://api.element14.com/catalog/products"

    def __init__(self, api_key: str, store: str = "fr.farnell.com"):
        self.api_key = api_key
        self.store = store

    def fetch_part(self, sku: str) -> dict | None:
        """Fetch part by Farnell stock number using term=id:<sku>."""
        params = {
            "term": f"id:{sku}",
            "storeInfo.id": self.store,
            "resultsSettings.offset": 0,
            "resultsSettings.numberOfResults": 1,
            "resultsSettings.responseGroup": "large",
            "callInfo.responseDataFormat": "JSON",
            "callInfo.apiKey": self.api_key,
        }
        resp = requests.get(self.BASE_URL, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        products = (
            data.get("keywordSearchReturn", {})
                .get("products", [])
        )
        if not products:
            return None

        p = products[0]

        price_breaks = []
        for pb in p.get("prices", []):
            try:
                price_breaks.append({
                    "quantity": int(pb.get("from", 1)),
                    "price": float(pb.get("cost", 0)),
                    "currency": pb.get("currency", "EUR"),
                })
            except (ValueError, TypeError):
                continue

        return {
            "name": p.get("translatedManufacturerPartNumber") or p.get("sku", sku),
            "description": p.get("displayName", ""),
            "manufacturer": p.get("vendorName", ""),
            "supplier_sku": p.get("sku", sku),
            "supplier_name": self.NAME,
            "datasheet": (p.get("datasheets") or [{}])[0].get("url", ""),
            "image": (p.get("imageUrl") or ""),
            "category_path": p.get("categoryNamePath", ""),
            "stock": p.get("stock", {}).get("level", ""),
            "price_breaks": price_breaks,
        }