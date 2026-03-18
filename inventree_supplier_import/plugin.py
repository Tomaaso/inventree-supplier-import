"""
InvenTree Supplier Import Plugin - compatible InvenTree >= 1.0
"""

import csv
import io
import json
import logging

from django.http import HttpResponse, JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.urls import path

from plugin import InvenTreePlugin
from plugin.mixins import SettingsMixin, UrlsMixin, UserInterfaceMixin, NavigationMixin

from .importer import create_part_from_supplier_data
from .suppliers.mouser import MouserSupplier
from .suppliers.digikey import DigiKeySupplier
from .suppliers.farnell import FarnellSupplier
from .suppliers.rs import RSSupplier

logger = logging.getLogger('inventree')
PLUGIN_VERSION = '2.1.0'


class SupplierImportPlugin(InvenTreePlugin, NavigationMixin, UserInterfaceMixin, SettingsMixin, UrlsMixin):

    NAME = 'SupplierImport'
    SLUG = 'supplier-import'
    TITLE = 'Import Fournisseur'
    DESCRIPTION = 'Import parts from Mouser, DigiKey, Farnell and RS Components via SKU'
    VERSION = PLUGIN_VERSION
    AUTHOR = 'Your Lab'
    MIN_VERSION = '1.0.0'
    NAVIGATION = [
        {'name': 'Import Fournisseur', 'link': 'plugin:supplier-import:import-page', 'icon': 'fas fa-download'},
    ]
    NAVIGATION_TAB_NAME = 'Import Fournisseur'
    NAVIGATION_TAB_ICON = 'fas fa-download'

    SETTINGS = {
        'IPN_PREFIX': {'name': 'IPN Prefix', 'description': 'Prefix IPN (ex: LAB -> LAB-0001)', 'default': 'LAB'},
        'MOUSER_API_KEY': {'name': 'Mouser API Key', 'default': '', 'protected': True},
        'DIGIKEY_CLIENT_ID': {'name': 'DigiKey Client ID', 'default': '', 'protected': True},
        'DIGIKEY_CLIENT_SECRET': {'name': 'DigiKey Client Secret', 'default': '', 'protected': True},
        'FARNELL_API_KEY': {'name': 'Farnell API Key', 'default': '', 'protected': True},
        'RS_API_KEY': {'name': 'RS Components API Key', 'default': '', 'protected': True},
    }

    def get_ui_navigation_items(self, request, context: dict, **kwargs):
        return [{
            'key': 'supplier-import-nav',
            'title': 'Import Fournisseur',
            'icon': 'ti:download:outline',
            'link': f'/plugin/{self.SLUG}/import-page/',
        }]

    def setup_urls(self):
        plugin = self
        return [
            path('import-page/', lambda request: _import_page_view(request, plugin), name='import-page'),
            path('import-sku/', csrf_exempt(lambda request: _import_sku_view(request, plugin)), name='import-sku'),
            path('import-csv/', csrf_exempt(lambda request: _import_csv_view(request, plugin)), name='import-csv'),
        ]

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


def _import_page_view(request, plugin):
    slug = plugin.SLUG
    html = (
        '<!doctype html><html lang="fr"><head><meta charset="utf-8">'
        '<title>Import Fournisseur</title>'
        '<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css">'
        '<style>body{padding:2rem;background:#f8f9fa}.main-card{max-width:800px;margin:auto}'
        '.result-ok{background:#d1e7dd}.result-err{background:#f8d7da}</style>'
        '</head><body><div class="main-card"><div class="card shadow-sm">'
        '<div class="card-header bg-primary text-white"><h5 class="mb-0">Import de composants fournisseurs</h5></div>'
        '<div class="card-body">'
        '<ul class="nav nav-tabs mb-4">'
        '<li class="nav-item"><button class="nav-link active" id="btn-single" onclick="showTab(\'single\')">Import unitaire (SKU)</button></li>'
        '<li class="nav-item"><button class="nav-link" id="btn-csv" onclick="showTab(\'csv\')">Import en masse (CSV)</button></li>'
        '</ul>'
        '<div id="tab-single">'
        '<div class="mb-3"><label class="form-label fw-semibold">Fournisseur</label>'
        '<select id="si-supplier" class="form-select">'
        '<option value="mouser">Mouser</option><option value="digikey">DigiKey</option>'
        '<option value="farnell">Farnell</option><option value="rs">RS Components</option>'
        '</select></div>'
        '<div class="mb-3"><label class="form-label fw-semibold">SKU</label>'
        '<input id="si-sku" type="text" class="form-control" placeholder="ex: 667-ERJ-3EKF1001V"></div>'
        '<button class="btn btn-primary" onclick="importSku()">Importer le composant</button>'
        '<div id="si-result" class="mt-3"></div>'
        '</div>'
        '<div id="tab-csv" style="display:none">'
        '<p class="text-muted">CSV avec colonnes <code>supplier</code> et <code>sku</code>. '
        'Valeurs : mouser, digikey, farnell, rs</p>'
        '<div class="mb-3"><input type="file" id="csv-file" accept=".csv" class="form-control"></div>'
        '<div class="d-flex gap-2 mb-3">'
        '<button class="btn btn-primary" onclick="importCsv()">Importer</button>'
        '<button class="btn btn-outline-secondary" onclick="dlTemplate()">Template CSV</button>'
        '</div>'
        '<div id="csv-progress" class="d-none"><div class="alert alert-info">Import en cours...</div></div>'
        '<div id="csv-summary"></div><div id="csv-results" class="mt-3"></div>'
        '</div></div></div></div>'
    )

    js = f"""
<script>
const SLUG = '{slug}';
function csrf(){{const m=document.cookie.match('(^|;) ?csrftoken=([^;]*)(;|$)');return m?m[2]:'';}}
function showTab(t){{
  document.getElementById('tab-single').style.display=t==='single'?'':'none';
  document.getElementById('tab-csv').style.display=t==='csv'?'':'none';
  document.getElementById('btn-single').classList.toggle('active',t==='single');
  document.getElementById('btn-csv').classList.toggle('active',t==='csv');
}}
function importSku(){{
  const supplier=document.getElementById('si-supplier').value;
  const sku=document.getElementById('si-sku').value.trim();
  const res=document.getElementById('si-result');
  if(!sku){{res.innerHTML='<div class="alert alert-warning">Saisir un SKU.</div>';return;}}
  res.innerHTML='<div class="alert alert-info">Import en cours...</div>';
  fetch('/plugin/'+SLUG+'/import-sku/',{{
    method:'POST',
    headers:{{'Content-Type':'application/json','X-CSRFToken':csrf()}},
    body:JSON.stringify({{supplier,sku}})
  }}).then(r=>r.json()).then(d=>{{
    if(d.success){{
      res.innerHTML='<div class="alert alert-success">Composant cree ! IPN: <code>'+d.ipn+'</code> &mdash; <a href="/part/'+d.part_pk+'/" target="_blank">Ouvrir</a></div>';
    }}else{{
      res.innerHTML='<div class="alert alert-danger">Erreur: '+( d.error||'inconnue')+'</div>';
    }}
  }}).catch(e=>{{res.innerHTML='<div class="alert alert-danger">'+e+'</div>';}});
}}
function dlTemplate(){{
  const c='supplier,sku\\nmouser,667-ERJ-3EKF1001V\\ndigikey,311-1.00KCRCT-ND\\nfarnell,1469817\\nrs,123-4567\\n';
  const a=document.createElement('a');a.href='data:text/csv,'+encodeURIComponent(c);a.download='template.csv';a.click();
}}
function importCsv(){{
  const file=document.getElementById('csv-file').files[0];
  if(!file){{alert('Selectionner un CSV');return;}}
  const fd=new FormData();fd.append('csv_file',file);
  document.getElementById('csv-progress').classList.remove('d-none');
  document.getElementById('csv-summary').innerHTML='';
  document.getElementById('csv-results').innerHTML='';
  fetch('/plugin/'+SLUG+'/import-csv/',{{method:'POST',headers:{{'X-CSRFToken':csrf()}},body:fd}})
  .then(r=>r.json()).then(data=>{{
    document.getElementById('csv-progress').classList.add('d-none');
    document.getElementById('csv-summary').innerHTML=
      '<div class="alert '+(data.failed===0?'alert-success':'alert-warning')+'">'+
      data.imported+'/'+data.total+' composes importes.'+(data.failed>0?' '+data.failed+' erreur(s).':'')+'</div>';
    const rows=data.results.map(r=>
      '<tr class="'+(r.success?'result-ok':'result-err')+'"><td>'+r.supplier+'</td><td><code>'+r.sku+'</code></td>'+
      '<td>'+(r.success?'OK':'ERR')+'</td><td>'+(r.ipn||'')+'</td>'+
      '<td>'+(r.part_pk?'<a href="/part/'+r.part_pk+'/" target="_blank">Ouvrir</a>':'')+'</td>'+
      '<td><small>'+(r.error||'')+'</small></td></tr>').join('');
    if(rows)document.getElementById('csv-results').innerHTML=
      '<table class="table table-sm table-bordered"><thead class="table-light">'+
      '<tr><th>Fourn.</th><th>SKU</th><th>Statut</th><th>IPN</th><th>Lien</th><th>Detail</th></tr>'+
      '</thead><tbody>'+rows+'</tbody></table>';
  }}).catch(e=>{{
    document.getElementById('csv-progress').classList.add('d-none');
    document.getElementById('csv-summary').innerHTML='<div class="alert alert-danger">'+e+'</div>';
  }});
}}
</script></body></html>"""
    return HttpResponse(html + js)


def _import_sku_view(request, plugin):
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=405)
    try:
        body = json.loads(request.body)
        supplier_name = body.get('supplier', '').strip()
        sku = body.get('sku', '').strip()
    except Exception:
        return JsonResponse({'success': False, 'error': 'Invalid JSON'}, status=400)
    if not supplier_name or not sku:
        return JsonResponse({'success': False, 'error': 'supplier and sku required'}, status=400)
    supplier = plugin.get_supplier(supplier_name)
    if supplier is None:
        return JsonResponse({'success': False, 'error': f'Unknown supplier: {supplier_name}'}, status=400)
    part_data = supplier.fetch_part(sku)
    if part_data is None:
        return JsonResponse({'success': False, 'error': f"SKU '{sku}' not found at {supplier_name}"})
    prefix = plugin.get_setting('IPN_PREFIX') or 'LAB'
    result = create_part_from_supplier_data(request, part_data, prefix)
    return JsonResponse(result)


def _import_csv_view(request, plugin):
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
            results.append({'sku': sku or '?', 'supplier': supplier_name or '?', 'success': False, 'error': 'Missing supplier or sku'})
            continue
        supplier = plugin.get_supplier(supplier_name)
        if supplier is None:
            results.append({'sku': sku, 'supplier': supplier_name, 'success': False, 'error': f'Unknown supplier: {supplier_name}'})
            continue
        try:
            part_data = supplier.fetch_part(sku)
            if part_data is None:
                results.append({'sku': sku, 'supplier': supplier_name, 'success': False, 'error': 'SKU not found'})
                continue
            result = create_part_from_supplier_data(request, part_data, prefix)
            results.append({'sku': sku, 'supplier': supplier_name, **result})
        except Exception as e:
            results.append({'sku': sku, 'supplier': supplier_name, 'success': False, 'error': str(e)})
    total = len(results)
    ok = sum(1 for r in results if r.get('success'))
    return JsonResponse({'total': total, 'imported': ok, 'failed': total - ok, 'results': results})
