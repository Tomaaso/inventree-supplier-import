# inventree-supplier-import

Plugin InvenTree pour importer des composants directement depuis un SKU fournisseur.

**Fournisseurs supportés** : Mouser, DigiKey, Farnell / Element14, RS Components

---

## Fonctionnalités

- **Import unitaire** : panel sur chaque page Part pour créer un composant depuis un SKU
- **Import CSV en masse** : page dédiée pour uploader un fichier CSV avec plusieurs SKU
- Génération automatique d'IPN (ex. `LAB-0042`)
- Création de la Part InvenTree + SupplierPart + price breaks
- Catégorie **"À classer"** créée automatiquement si inexistante

---

## Installation

```bash
pip install git+https://github.com/your-lab/inventree-supplier-import.git
```

Ou depuis le répertoire local :

```bash
cd inventree-supplier-import
pip install -e .
```

Puis dans InvenTree :  
**Admin → Plugins → Activer `SupplierImportPlugin`**

---

## Configuration des clés API

Dans **Admin → Plugins → SupplierImport → Settings** :

| Paramètre | Description |
|---|---|
| `IPN_PREFIX` | Préfixe IPN, ex. `LAB` → génère `LAB-0001` |
| `MOUSER_API_KEY` | Clé API Mouser (obtenir sur [mouser.fr/api-search](https://www.mouser.fr/api-hub/)) |
| `DIGIKEY_CLIENT_ID` | Client ID DigiKey (portail API DigiKey) |
| `DIGIKEY_CLIENT_SECRET` | Client Secret DigiKey |
| `FARNELL_API_KEY` | Clé API Farnell / Element14 |
| `RS_API_KEY` | Clé API RS Components |

### Obtenir les clés API

**Mouser**  
→ [https://www.mouser.fr/api-hub/](https://www.mouser.fr/api-hub/)  
S'enregistrer, créer une application, récupérer la clé "Part Search API".

**DigiKey**  
→ [https://developer.digikey.com/](https://developer.digikey.com/)  
Créer une organisation, puis une "Production App". Récupérer `Client ID` et `Client Secret`.  
⚠️ L'auth est OAuth2 client credentials (pas d'OAuth interactif nécessaire pour la recherche).

**Farnell / Element14**  
→ [https://partner.element14.com/](https://partner.element14.com/)  
S'inscrire comme partenaire, récupérer la clé API "Product Search".

**RS Components**  
→ [https://fr.rs-online.com/web/generalDisplay.html?id=footer/api-terms](https://fr.rs-online.com/web/generalDisplay.html?id=footer/api-terms)  
Contacter RS pour l'accès API (moins automatisé que les autres).

---

## Utilisation

### Import unitaire

Ouvrir n'importe quelle page **Parts** dans InvenTree.  
Le panel **"Import from Supplier SKU"** apparaît dans le bas de la page.

1. Sélectionner le fournisseur
2. Saisir le SKU
3. Cliquer sur **Import**

### Import CSV

Naviguer vers `/plugin/supplier-import/import-page/`

Format CSV attendu :

```csv
supplier,sku
mouser,667-ERJ-3EKF1001V
digikey,311-1.00KCRCT-ND
farnell,1469817
rs,123-4567
```

Un bouton **"Download template"** est disponible sur la page d'import.

---

## Prérequis

- InvenTree >= 0.13
- Python >= 3.10
- Les fournisseurs doivent être créés dans InvenTree (Admin → Companies) avec exactement les noms : `Mouser`, `DigiKey`, `Farnell`, `RS Components`

---

## Structure du projet

```
inventree-supplier-import/
├── setup.cfg
├── README.md
└── inventree_supplier_import/
    ├── __init__.py
    ├── plugin.py          # Plugin principal, panels, URLs, vues
    ├── importer.py        # Logique de création Part/SupplierPart/PriceBreaks
    └── suppliers/
        ├── __init__.py
        ├── mouser.py
        ├── digikey.py
        ├── farnell.py
        └── rs.py
```
