"""
Core import logic: creates Part, SupplierPart and PriceBreaks in InvenTree
using Django ORM directly (plugin interne — pas besoin de l'API REST).
"""

import re
import logging

logger = logging.getLogger("inventree")

UNCLASSIFIED_CATEGORY_NAME = "A classer"


def get_or_create_unclassified_category():
    from part.models import PartCategory
    cat, _ = PartCategory.objects.get_or_create(name=UNCLASSIFIED_CATEGORY_NAME)
    return cat.pk


def generate_ipn(prefix: str) -> str:
    from part.models import Part
    parts = Part.objects.filter(IPN__startswith=f"{prefix}-")
    pattern = re.compile(rf"^{re.escape(prefix)}-(\d+)$")
    max_num = 0
    for part in parts:
        m = pattern.match(part.IPN or "")
        if m:
            max_num = max(max_num, int(m.group(1)))
    return f"{prefix}-{str(max_num + 1).zfill(4)}"


def get_supplier_pk(supplier_name: str):
    from company.models import Company
    try:
        company = Company.objects.get(name__iexact=supplier_name, is_supplier=True)
        return company.pk
    except Company.DoesNotExist:
        logger.warning(f"[SupplierImport] Supplier '{supplier_name}' not found.")
        return None
    except Company.MultipleObjectsReturned:
        return Company.objects.filter(name__iexact=supplier_name, is_supplier=True).first().pk


def get_manufacturer_pk(manufacturer_name: str):
    from company.models import Company
    try:
        company = Company.objects.get(name__iexact=manufacturer_name, is_manufacturer=True)
        return company.pk
    except Exception:
        return None


def create_part_from_supplier_data(request, part_data: dict, ipn_prefix: str) -> dict:
    """
    Crée Part + SupplierPart + PriceBreaks via ORM Django.
    Retourne dict: success, ipn, part_pk, error
    """
    try:
        from part.models import Part, PartCategory
        from company.models import Company, SupplierPart, SupplierPriceBreak

        # 1. Catégorie
        category_pk = get_or_create_unclassified_category()
        category = PartCategory.objects.get(pk=category_pk)

        # 2. IPN
        ipn = generate_ipn(ipn_prefix)

        # 3. Créer la Part
        part = Part.objects.create(
            name=part_data["name"],
            description=part_data.get("description", "") or "",
            IPN=ipn,
            category=category,
            active=True,
            purchaseable=True,
        )

        # Image distante (optionnel, ne bloque pas si ça échoue)
        if part_data.get("image"):
            try:
                part.remote_image = part_data["image"]
                part.save()
            except Exception:
                pass

        # 4. Fournisseur
        supplier_pk = get_supplier_pk(part_data["supplier_name"])
        if supplier_pk is None:
            return {
                "success": False,
                "ipn": ipn,
                "part_pk": part.pk,
                "error": f"Fournisseur '{part_data['supplier_name']}' introuvable dans InvenTree (Companies). Part créée (IPN: {ipn}) mais sans SupplierPart.",
            }
        supplier = Company.objects.get(pk=supplier_pk)

        # 5. Fabricant (optionnel)
        manufacturer = None
        if part_data.get("manufacturer"):
            mfr_pk = get_manufacturer_pk(part_data["manufacturer"])
            if mfr_pk:
                manufacturer = Company.objects.get(pk=mfr_pk)

        # 6. SupplierPart
        sp = SupplierPart.objects.create(
            part=part,
            supplier=supplier,
            SKU=part_data["supplier_sku"],
            manufacturer=manufacturer,
            MPN=part_data["name"] if manufacturer else "",
            link=part_data.get("datasheet", "") or "",
            note=f"Imported from {part_data['supplier_name']}",
        )

        # 7. PriceBreaks
        for pb in part_data.get("price_breaks", []):
            try:
                SupplierPriceBreak.objects.create(
                    part=sp,
                    quantity=pb["quantity"],
                    price=str(pb["price"]),
                    price_currency=pb.get("currency", "EUR"),
                )
            except Exception as e:
                logger.warning(f"[SupplierImport] PriceBreak skipped: {e}")

        return {"success": True, "ipn": ipn, "part_pk": part.pk, "error": None}

    except Exception as e:
        logger.exception(f"[SupplierImport] Error creating part: {e}")
        return {"success": False, "ipn": None, "part_pk": None, "error": str(e)}