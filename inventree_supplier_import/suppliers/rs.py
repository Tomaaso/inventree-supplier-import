"""RS Components supplier adapter."""

import requests


class RSSupplier:
    NAME = "RS Components"
    BASE_URL = "https://api.rs-online.com/searchProducts/v3/products"

    def __init__(self, api_key: str, locale: str = "fr"):
        self.api_key = api_key
        self.locale = locale

    def fetch_part(self, sku: str) -> dict | None:
        """Fetch part data from RS Components API by SKU (stock number)."""
        headers = {
            "Accept": "application/json",
            "Accept-Language": self.locale,
            "Authorization": self.api_key,
        }
        params = {"stockNumber": sku}
        resp = requests.get(
            f"{self.BASE_URL}/stockNumber/{sku}",
            headers=headers,
            timeout=10,
        )

        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        products = data.get("products", [])
        if not products:
            return None

        p = products[0]

        price_breaks = []
        for pb in p.get("pricingAndAvailability", {}).get("priceBreaks", []):
            try:
                price_breaks.append({
                    "quantity": int(pb.get("quantity", 1)),
                    "price": float(pb.get("price", 0)),
                    "currency": pb.get("currency", "EUR"),
                })
            except (ValueError, TypeError):
                continue

        return {
            "name": p.get("partNumber", sku),
            "description": p.get("description", ""),
            "manufacturer": p.get("brand", {}).get("name", ""),
            "supplier_sku": p.get("stockNumber", sku),
            "supplier_name": self.NAME,
            "datasheet": p.get("dataSheets", [{}])[0].get("url", "") if p.get("dataSheets") else "",
            "image": p.get("imageURL", ""),
            "category_path": p.get("productHierarchy", [{}])[-1].get("name", "") if p.get("productHierarchy") else "",
            "stock": p.get("pricingAndAvailability", {}).get("stockAvailable", ""),
            "price_breaks": price_breaks,
        }
