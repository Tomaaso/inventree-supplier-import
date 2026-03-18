"""DigiKey supplier adapter (API v4)."""

import requests


class DigiKeySupplier:
    NAME = "DigiKey"
    AUTH_URL = "https://api.digikey.com/v1/oauth2/token"
    BASE_URL = "https://api.digikey.com/products/v4"

    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self._token = None

    def _get_token(self) -> str:
        """Fetch or reuse OAuth2 client credentials token."""
        if self._token:
            return self._token
        resp = requests.post(
            self.AUTH_URL,
            data={
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        self._token = resp.json()["access_token"]
        return self._token

    def fetch_part(self, sku: str) -> dict | None:
        """Fetch part data from DigiKey API v4 by SKU."""
        token = self._get_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "X-DIGIKEY-Client-Id": self.client_id,
            "X-DIGIKEY-Locale-Site": "FR",
            "X-DIGIKEY-Locale-Language": "en",
            "X-DIGIKEY-Locale-Currency": "EUR",
        }
        url = f"{self.BASE_URL}/search/{sku}/details"
        resp = requests.get(url, headers=headers, timeout=10)

        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()

        product = data.get("Product", data)

        price_breaks = []
        for pb in product.get("StandardPricing", []):
            try:
                price_breaks.append({
                    "quantity": int(pb.get("BreakQuantity", 1)),
                    "price": float(pb.get("UnitPrice", 0)),
                    "currency": "EUR",
                })
            except (ValueError, TypeError):
                continue

        category = product.get("Category", {})
        category_path = category.get("Name", "") if isinstance(category, dict) else str(category)

        return {
            "name": product.get("ManufacturerProductNumber", sku),
            "description": product.get("Description", {}).get("ProductDescription", ""),
            "manufacturer": product.get("Manufacturer", {}).get("Name", ""),
            "supplier_sku": product.get("DigiKeyPartNumber", sku),
            "supplier_name": self.NAME,
            "datasheet": product.get("DatasheetUrl", ""),
            "image": product.get("PrimaryPhoto", ""),
            "category_path": category_path,
            "stock": product.get("QuantityAvailable", ""),
            "price_breaks": price_breaks,
        }
