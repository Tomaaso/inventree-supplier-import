"""
InvenTree Supplier Import Plugin — compatible InvenTree >= 1.0
--------------------------------------------------------------
Utilise UserInterfaceMixin (remplace PanelMixin supprimé en 1.0).

Deux points d'entrée :
  - Panel sur la page Part : import unitaire par SKU
  - Page dédiée CSV      : /plugin/supplier-import/csv-page/

Settings (Admin → Plugins → SupplierImport → Settings) :
  IPN_PREFIX, MOUSER_API_KEY, DIGIKEY_CLIENT_ID,
  DIGIKEY_CLIENT_SECRET, FARNELL_API_KEY, RS_API_KEY
"""

import csv
import io
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from django.urls import path

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin, UrlsMixin, UserInterfaceMixin

from .importer import create_part_from_supplier_data
from .suppliers.mouser import MouserSupplier
from .suppliers.digikey import DigiKeySupplier
from .suppliers.farnell import FarnellSupplier
from .suppliers.rs import RSSupplier

logger = logging.getLogger('inventree')

PLUGIN_VERSION = '2.0.0'


class SupplierImportPlugin(UserInterfaceMixin, SettingsMixin, UrlsMixin, InvenTreePlugin):

    NAME = 'SupplierImport'
    SLUG = 'supplier-import'
    TITLE = 'Supplier Part Importer'
    DESCRIPTION = 'Import parts from Mouser, DigiKey, Farnell and RS Components via SKU'
    VERSION = PLUGIN_VERSION
    AUTHOR = 'Your Lab'
    MIN_VERSION = '1.0.0'

    # ------------------------------------------------------------------ #
    #  Settings                                                            #
    # ------------------------------------------------------------------ #
    SETTINGS = {
        'IPN_PREFIX': {
            'name': 'IPN Prefix',
            'description': 'Prefix used for auto-generated IPN (e.g. LAB → LAB-0001)',
            'default': 'LAB',
        },
        'MOUSER_API_KEY': {
            'name': 'Mouser API Key',
            'description': 'Mouser part search API key',
            'default': '',
            'protected': True,
        },
        'DIGIKEY_CLIENT_ID': {
            'name': 'DigiKey Client ID',
            'description': 'DigiKey OAuth2 client ID',
            'default': '',
            'protected': True,
        },
        'DIGIKEY_CLIENT_SECRET': {
            'name': 'DigiKey Client Secret',
            'description': 'DigiKey OAuth2 client secret',
            'default': '',
            'protected': True,
        },
        'FARNELL_API_KEY': {
            'name': 'Farnell API Key',
            'description': 'Farnell / Element14 API key',
            'default': '',
            'protected': True,
        },
        'RS_API_KEY': {
            'name': 'RS Components API Key',
            'description': 'RS Components API key',
            'default': '',
            'protected': True,
        },
    }

    # ------------------------------------------------------------------ #
    #  UserInterfaceMixin — panel sur la page Part                        #
    # ------------------------------------------------------------------ #
    def get_ui_panels(self, request, context: dict, **kwargs):
        """Injecte le panel d'import SKU sur la page détail d'une Part."""
        panels = []
        if context.get('target_model') == 'part':
            panels.append({
                'key': 'supplier-import-panel',
                'title': 'Import Fournisseur',
                'description': 'Importer depuis un SKU fournisseur',
                'icon': 'ti:download:outline',
                # Fichier JS compilé dans static/
                'source': self.plugin_static_file('SupplierImportPanel.js:renderSupplierImportPanel'),
                # Données passées au JS via context.context
                'context': {
                    'slug': self.SLUG,
                    'api_url': f'/plugin/{self.SLUG}/import-sku/',
                    'csv_page_url': f'/plugin/{self.SLUG}/csv-page/',
                },
            })
        return panels

    # ------------------------------------------------------------------ #
    #  URLs                                                                #
    # ------------------------------------------------------------------ #
    URLS = [
        path('import-sku/', csrf_exempt(lambda request, plugin=None: _import_sku_view(request, plugin)), name='import-sku'),
        path('import-csv/', csrf_exempt(lambda request, plugin=None: _import_csv_view(request, plugin)), name='import-csv'),
        path('csv-page/', lambda request, plugin=None: _csv_page_view(request, plugin), name='csv-page'),
    ]

    def setup_urls(self):
        """Bind URL handlers with plugin instance."""
        plugin = self
        return [
            path('import-sku/', csrf_exempt(lambda request: _import_sku_view(request, plugin)), name='import-sku'),
            path('import-csv/', csrf_exempt(lambda request: _import_csv_view(request, plugin)), name='import-csv'),
            path('csv-page/', lambda request: _csv_page_view(request, plugin), name='csv-page'),
        ]

    # ------------------------------------------------------------------ #
    #  Helper: instancier le bon adapter fournisseur                      #
    # ------------------------------------------------------------------ #
    def get_supplier(self, name: str):
        n = name.lower().strip()
        if n == 'mouser':
            return MouserSupplier(api_key=self.get_setting('MOUSER_API_KEY'))
        if n == 'digikey':
            return DigiKeySupplier(
                client_id=self.get_setting('DIGIKEY_CLIENT_ID'),
                client_secret=self.get_setting('DIGIKEY_CLIENT_SECRET'),
            )
        if n in ('farnell', 'element14'):
            return FarnellSupplier(api_key=self.get_setting('FARNELL_API_KEY'))
        if n in ('rs', 'rs components', 'radiospares', 'rs_components'):
            return RSSupplier(api_key=self.get_setting('RS_API_KEY'))
        return None


# ------------------------------------------------------------------ #
#  Vues standalone (fonctions pour éviter les problèmes de binding)   #
# ------------------------------------------------------------------ #

def _import_sku_view(request, plugin: SupplierImportPlugin):
    """POST {supplier, sku} → crée Part + SupplierPart + PriceBreaks."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        supplier_name = body.get('supplier', '').strip()
        sku = body.get('sku', '').strip()
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)

    if not supplier_name or not sku:
        return JsonResponse({'success': False, 'error': 'supplier and sku are required'}, status=400)

    supplier = plugin.get_supplier(supplier_name)
    if supplier is None:
        return JsonResponse({'success': False, 'error': f'Unknown supplier: {supplier_name}'}, status=400)

    part_data = supplier.fetch_part(sku)
    if part_data is None:
        return JsonResponse({'success': False, 'error': f"SKU '{sku}' not found at {supplier_name}"})

    prefix = plugin.get_setting('IPN_PREFIX') or 'LAB'
    result = create_part_from_supplier_data(request, part_data, prefix)
    return JsonResponse(result)


def _import_csv_view(request, plugin: SupplierImportPlugin):
    """POST multipart/form-data avec csv_file → import en masse."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)

    csv_file = request.FILES.get('csv_file')
    if not csv_file:
        return JsonResponse({'success': False, 'error': 'No file uploaded'}, status=400)

    text = csv_file.read().decode('utf-8-sig')
    reader = csv.DictReader(io.StringIO(text))
    results = []
    prefix = plugin.get_setting('IPN_PREFIX') or 'LAB'

    for row in reader:
        row = {k.lower().strip(): v.strip() for k, v in row.items()}
        supplier_name = row.get('supplier', '')
        sku = row.get('sku', '')

        if not supplier_name or not sku:
            results.append({'sku': sku or '?', 'supplier': supplier_name or '?',
                            'success': False, 'error': 'Missing supplier or sku'})
            continue

        supplier = plugin.get_supplier(supplier_name)
        if supplier is None:
            results.append({'sku': sku, 'supplier': supplier_name,
                            'success': False, 'error': f'Unknown supplier: {supplier_name}'})
            continue

        try:
            part_data = supplier.fetch_part(sku)
            if part_data is None:
                results.append({'sku': sku, 'supplier': supplier_name,
                                'success': False, 'error': 'SKU not found'})
                continue
            result = create_part_from_supplier_data(request, part_data, prefix)
            results.append({'sku': sku, 'supplier': supplier_name, **result})
        except Exception as e:
            results.append({'sku': sku, 'supplier': supplier_name,
                            'success': False, 'error': str(e)})

    total = len(results)
    ok = sum(1 for r in results if r.get('success'))
    return JsonResponse({'total': total, 'imported': ok, 'failed': total - ok, 'results': results})


def _csv_page_view(request, plugin: SupplierImportPlugin):
    """Page HTML autonome pour l'import CSV en masse."""
    slug = plugin.SLUG
    html = f"""<!doctype html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Import CSV Fournisseurs — InvenTree</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">
  <style>
    body {{ padding: 2rem; background: #f8f9fa; }}
    .card {{ max-width: 760px; margin: auto; }}
    .result-ok  {{ background: #d1e7dd; }}
    .result-err {{ background: #f8d7da; }}
    code {{ font-size: 0.85em; }}
  </style>
</head>
<body>
<div class="card shadow-sm">
  <div class="card-header bg-primary text-white fw-bold">
    📦 Import CSV — Composants fournisseurs
  </div>
  <div class="card-body">
    <p class="text-muted mb-3">
      Fichier CSV avec les colonnes <code>supplier</code> et <code>sku</code>.<br>
      Valeurs acceptées pour supplier : <strong>mouser, digikey, farnell, rs</strong>
    </p>

    <div class="mb-3">
      <label class="form-label fw-semibold">Fichier CSV</label>
      <input type="file" id="csv-file" accept=".csv" class="form-control">
    </div>

    <div class="d-flex gap-2 mb-3">
      <button class="btn btn-primary" onclick="uploadCsv()">⬆ Importer</button>
      <button class="btn btn-outline-secondary" onclick="downloadTemplate()">⬇ Template CSV</button>
    </div>

    <div id="progress" class="d-none">
      <div class="alert alert-info">⏳ Import en cours…</div>
    </div>
    <div id="summary"></div>
    <div id="results-table" class="mt-3"></div>
  </div>
</div>

<script>
const SLUG = '{slug}';

function getCookie(name) {{
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? v[2] : null;
}}

function downloadTemplate() {{
  const content = 'supplier,sku\\nmouser,667-ERJ-3EKF1001V\\ndigikey,311-1.00KCRCT-ND\\nfarnell,1469817\\nrs,123-4567\\n';
  const a = document.createElement('a');
  a.href = 'data:text/csv,' + encodeURIComponent(content);
  a.download = 'import_template.csv';
  a.click();
}}

function uploadCsv() {{
  const file = document.getElementById('csv-file').files[0];
  if (!file) {{ alert('Veuillez sélectionner un fichier CSV.'); return; }}

  const formData = new FormData();
  formData.append('csv_file', file);

  document.getElementById('progress').classList.remove('d-none');
  document.getElementById('summary').innerHTML = '';
  document.getElementById('results-table').innerHTML = '';

  fetch(`/plugin/${{SLUG}}/import-csv/`, {{
    method: 'POST',
    headers: {{ 'X-CSRFToken': getCookie('csrftoken') }},
    body: formData,
  }})
  .then(r => r.json())
  .then(data => {{
    document.getElementById('progress').classList.add('d-none');
    const allOk = data.failed === 0;
    document.getElementById('summary').innerHTML = `
      <div class="alert ${{allOk ? 'alert-success' : 'alert-warning'}}">
        <strong>Terminé !</strong>
        ${{data.imported}}/${{data.total}} composants importés.
        ${{data.failed > 0 ? `<br>${{data.failed}} erreur(s) — voir tableau ci-dessous.` : ''}}
      </div>`;

    const rows = data.results.map(r => `
      <tr class="${{r.success ? 'result-ok' : 'result-err'}}">
        <td>${{r.supplier}}</td>
        <td><code>${{r.sku}}</code></td>
        <td>${{r.success ? '✓' : '✗'}}</td>
        <td>${{r.ipn || ''}}</td>
        <td>${{r.part_pk ? `<a href="/part/${{r.part_pk}}/" target="_blank">Ouvrir →</a>` : ''}}</td>
        <td><small class="text-danger">${{r.error || ''}}</small></td>
      </tr>`).join('');

    document.getElementById('results-table').innerHTML = `
      <table class="table table-sm table-bordered">
        <thead class="table-light">
          <tr><th>Fournisseur</th><th>SKU</th><th>Statut</th><th>IPN</th><th>Lien</th><th>Détail</th></tr>
        </thead>
        <tbody>${{rows}}</tbody>
      </table>`;
  }})
  .catch(err => {{
    document.getElementById('progress').classList.add('d-none');
    document.getElementById('summary').innerHTML =
      `<div class="alert alert-danger">Erreur : ${{err}}</div>`;
  }});
}}
</script>
</body>
</html>"""
    return HttpResponse(html)
