"""
Core import logic: creates Part, SupplierPart and PriceBreaks in InvenTree
from normalized supplier data dicts.
"""

import re
import logging

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin

logger = logging.getLogger("inventree")

UNCLASSIFIED_CATEGORY_NAME = "À classer"


def get_or_create_unclassified_category(api):
    """Return the pk of the 'À classer' category, creating it if needed."""
    response = api.get("/api/part/category/", params={"name": UNCLASSIFIED_CATEGORY_NAME})
    results = response.json() if hasattr(response, "json") else response

    if isinstance(results, dict):
        results = results.get("results", [])

    for cat in results:
        if cat.get("name") == UNCLASSIFIED_CATEGORY_NAME:
            return cat["pk"]

    # Create it
    resp = api.post("/api/part/category/", data={"name": UNCLASSIFIED_CATEGORY_NAME})
    created = resp.json() if hasattr(resp, "json") else resp
    return created["pk"]


def generate_ipn(api, prefix: str) -> str:
    """
    Generate the next IPN following the pattern PREFIX-NNNN.
    Scans existing parts to find the highest sequential number.
    """
    response = api.get("/api/part/", params={"IPN": f"{prefix}-", "limit": 9999})
    data = response.json() if hasattr(response, "json") else response
    results = data.get("results", []) if isinstance(data, dict) else data

    max_num = 0
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    for part in results:
        ipn = part.get("IPN", "")
        m = pattern.match(ipn)
        if m:
            max_num = max(max_num, int(m.group(1)))

    return f"{prefix}-{str(max_num + 1).zfill(4)}"


def get_or_create_supplier(api, supplier_name: str) -> int | None:
    """Return the pk of a Company matching supplier_name, or None."""
    response = api.get("/api/company/", params={"name": supplier_name, "is_supplier": True})
    data = response.json() if hasattr(response, "json") else response
    results = data.get("results", []) if isinstance(data, dict) else data

    for company in results:
        if company.get("name", "").lower() == supplier_name.lower():
            return company["pk"]

    logger.warning(f"[SupplierImport] Supplier '{supplier_name}' not found in InvenTree companies.")
    return None


def create_part_from_supplier_data(api, part_data: dict, ipn_prefix: str) -> dict:
    """
    Given normalized supplier data, create:
      1. Part
      2. SupplierPart
      3. PriceBreaks

    Returns a result dict with keys: success, ipn, part_pk, error
    """
    try:
        category_pk = get_or_create_unclassified_category(api)
        ipn = generate_ipn(api, ipn_prefix)

        # 1. Create the Part
        part_payload = {
            "name": part_data["name"],
            "description": part_data.get("description", ""),
            "IPN": ipn,
            "category": category_pk,
            "active": True,
            "purchaseable": True,
        }
        if part_data.get("image"):
            part_payload["remote_image"] = part_data["image"]

        part_resp = api.post("/api/part/", data=part_payload)
        part = part_resp.json() if hasattr(part_resp, "json") else part_resp
        part_pk = part["pk"]

        # 2. Get supplier company pk
        supplier_pk = get_or_create_supplier(api, part_data["supplier_name"])
        if supplier_pk is None:
            return {
                "success": False,
                "ipn": ipn,
                "part_pk": part_pk,
                "error": f"Supplier '{part_data['supplier_name']}' not found. Part created (IPN: {ipn}) but no SupplierPart linked.",
            }

        # Handle manufacturer (optional)
        manufacturer_pk = None
        if part_data.get("manufacturer"):
            mfr_resp = api.get("/api/company/", params={"name": part_data["manufacturer"], "is_manufacturer": True})
            mfr_data = mfr_resp.json() if hasattr(mfr_resp, "json") else mfr_resp
            mfr_results = mfr_data.get("results", []) if isinstance(mfr_data, dict) else mfr_data
            for mfr in mfr_results:
                if mfr.get("name", "").lower() == part_data["manufacturer"].lower():
                    manufacturer_pk = mfr["pk"]
                    break

        # 3. Create SupplierPart
        sp_payload = {
            "part": part_pk,
            "supplier": supplier_pk,
            "SKU": part_data["supplier_sku"],
            "link": part_data.get("datasheet", ""),
            "note": f"Imported from {part_data['supplier_name']}",
        }
        if manufacturer_pk:
            sp_payload["manufacturer"] = manufacturer_pk
            sp_payload["MPN"] = part_data["name"]

        sp_resp = api.post("/api/company/part/", data=sp_payload)
        sp = sp_resp.json() if hasattr(sp_resp, "json") else sp_resp
        sp_pk = sp["pk"]

        # 4. Create PriceBreaks
        for pb in part_data.get("price_breaks", []):
            api.post("/api/company/part/price/", data={
                "part": sp_pk,
                "quantity": pb["quantity"],
                "price": str(pb["price"]),
                "price_currency": pb.get("currency", "EUR"),
            })

        return {"success": True, "ipn": ipn, "part_pk": part_pk, "error": None}

    except Exception as e:
        logger.exception(f"[SupplierImport] Error creating part from {part_data.get('supplier_sku')}: {e}")
        return {"success": False, "ipn": None, "part_pk": None, "error": str(e)}
