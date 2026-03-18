# inventree-supplier-import

Plugin InvenTree **(>= 1.0)** pour importer des composants depuis un SKU fournisseur.

**Fournisseurs supportés** : Mouser, DigiKey, Farnell / Element14, RS Components

---

## Fonctionnalités

- **Panel unitaire** sur chaque page Part — saisie SKU + bouton Import
- **Page CSV** dédiée (`/plugin/supplier-import/csv-page/`) — import en masse
- Génération automatique d'IPN (`LAB-0001`, `LAB-0002`…)
- Création automatique : Part + SupplierPart + Price Breaks
- Catégorie **"À classer"** créée si elle n'existe pas

---

## Installation depuis GitHub

Dans InvenTree : **Admin → Plugins → Install plugin**

| Champ | Valeur |
|---|---|
| Package Name | `inventree-supplier-import` |
| Source URL | `git+https://github.com/Tomaaso/inventree-supplier-import.git` |
| Version | *(laisser vide)* |

---

## Configuration

Dans **Admin → Plugins → SupplierImport → Settings** :

| Paramètre | Description |
|---|---|
| `IPN_PREFIX` | Préfixe IPN, ex. `LAB` → `LAB-0001` |
| `MOUSER_API_KEY` | Clé API Mouser |
| `DIGIKEY_CLIENT_ID` | Client ID DigiKey (OAuth2) |
| `DIGIKEY_CLIENT_SECRET` | Client Secret DigiKey |
| `FARNELL_API_KEY` | Clé API Farnell / Element14 |
| `RS_API_KEY` | Clé API RS Components |

### ⚠️ Activer l'interface plugin

Dans **Admin → Settings → Plugin Settings** :
- ✅ **Enable interface integration** (`ENABLE_PLUGINS_INTERFACE`)

Sans ce flag, le panel n'apparaîtra pas sur les pages Part.

### Fournisseurs InvenTree requis

Les fournisseurs doivent exister dans InvenTree (Admin → Companies) avec exactement ces noms :
`Mouser`, `DigiKey`, `Farnell`, `RS Components`

---

## Utilisation

### Import unitaire
Ouvrir une page **Part** → panel **"Import Fournisseur"** dans la sidebar.

### Import CSV
Naviguer vers `/plugin/supplier-import/csv-page/`

Format CSV :
```csv
supplier,sku
mouser,667-ERJ-3EKF1001V
digikey,311-1.00KCRCT-ND
farnell,1469817
rs,123-4567
```

---

## Structure

```
inventree-supplier-import/
├── setup.py
├── setup.cfg
├── MANIFEST.in
├── static/
│   └── SupplierImportPanel.js   ← UI panel (vanilla JS, pas de build requis)
└── inventree_supplier_import/
    ├── plugin.py       ← UserInterfaceMixin + URLs + vues
    ├── importer.py     ← Logique IPN / Part / SupplierPart / PriceBreaks
    └── suppliers/
        ├── mouser.py
        ├── digikey.py
        ├── farnell.py
        └── rs.py
```

---

## Prérequis

- InvenTree **>= 1.0.0**
- Python >= 3.10
