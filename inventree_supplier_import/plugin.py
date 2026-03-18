"""
InvenTree Supplier Import Plugin
---------------------------------
Adds two panels to InvenTree:
  - Single SKU import (any supplier page)
  - Bulk CSV import (dedicated plugin page)

Settings (configured in InvenTree plugin admin):
  IPN_PREFIX       : e.g. "LAB"
  MOUSER_API_KEY   : Mouser search API key
  DIGIKEY_CLIENT_ID / DIGIKEY_CLIENT_SECRET
  FARNELL_API_KEY
  RS_API_KEY
"""

import csv
import io
import json
import logging

from django.http import JsonResponse
from django.views import View
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt

from plugin import InvenTreePlugin
from plugin.mixins import PanelMixin, SettingsMixin, UrlsMixin

from .importer import create_part_from_supplier_data
from .suppliers.mouser import MouserSupplier
from .suppliers.digikey import DigiKeySupplier
from .suppliers.farnell import FarnellSupplier
from .suppliers.rs import RSSupplier

logger = logging.getLogger("inventree")

PLUGIN_VERSION = "1.0.0"


class SupplierImportPlugin(PanelMixin, SettingsMixin, UrlsMixin, InvenTreePlugin):

    NAME = "SupplierImport"
    SLUG = "supplier-import"
    TITLE = "Supplier Part Importer"
    DESCRIPTION = "Import parts from Mouser, DigiKey, Farnell and RS Components via SKU"
    VERSION = PLUGIN_VERSION
    AUTHOR = "Your Lab"

    # ------------------------------------------------------------------ #
    #  Plugin settings (visible in InvenTree > Admin > Plugins)           #
    # ------------------------------------------------------------------ #
    SETTINGS = {
        "IPN_PREFIX": {
            "name": "IPN Prefix",
            "description": "Prefix used for auto-generated IPN (e.g. LAB → LAB-0001)",
            "default": "LAB",
        },
        "MOUSER_API_KEY": {
            "name": "Mouser API Key",
            "description": "Mouser part search API key",
            "default": "",
            "protected": True,
        },
        "DIGIKEY_CLIENT_ID": {
            "name": "DigiKey Client ID",
            "description": "DigiKey OAuth2 client ID",
            "default": "",
            "protected": True,
        },
        "DIGIKEY_CLIENT_SECRET": {
            "name": "DigiKey Client Secret",
            "description": "DigiKey OAuth2 client secret",
            "default": "",
            "protected": True,
        },
        "FARNELL_API_KEY": {
            "name": "Farnell API Key",
            "description": "Farnell / Element14 API key",
            "default": "",
            "protected": True,
        },
        "RS_API_KEY": {
            "name": "RS Components API Key",
            "description": "RS Components API key",
            "default": "",
            "protected": True,
        },
    }

    # ------------------------------------------------------------------ #
    #  Helper: build the right supplier adapter from a name string        #
    # ------------------------------------------------------------------ #
    def _get_supplier(self, supplier_name: str):
        name = supplier_name.lower().strip()
        if name == "mouser":
            key = self.get_setting("MOUSER_API_KEY")
            return MouserSupplier(api_key=key)
        elif name == "digikey":
            return DigiKeySupplier(
                client_id=self.get_setting("DIGIKEY_CLIENT_ID"),
                client_secret=self.get_setting("DIGIKEY_CLIENT_SECRET"),
            )
        elif name in ("farnell", "element14"):
            return FarnellSupplier(api_key=self.get_setting("FARNELL_API_KEY"))
        elif name in ("rs", "rs components", "radiospares", "rs_components"):
            return RSSupplier(api_key=self.get_setting("RS_API_KEY"))
        return None

    # ------------------------------------------------------------------ #
    #  Custom URLs                                                         #
    # ------------------------------------------------------------------ #
    def setup_urls(self):
        from django.urls import path
        return [
            path("import-sku/", self.ImportSkuView.as_view(plugin=self), name="import-sku"),
            path("import-csv/", self.ImportCsvView.as_view(plugin=self), name="import-csv"),
            path("import-page/", self.ImportPageView.as_view(plugin=self), name="import-page"),
        ]

    # ------------------------------------------------------------------ #
    #  Panel injection                                                     #
    # ------------------------------------------------------------------ #
    def get_custom_panels(self, view, request):
        """Inject the single-SKU panel on every Part detail page."""
        panels = []

        if view.__class__.__name__ == "PartDetail":
            panels.append({
                "title": "Import from Supplier SKU",
                "icon": "fa-download",
                "content": self._render_single_panel(),
            })

        return panels

    def _render_single_panel(self) -> str:
        """HTML + JS for the single-SKU import panel."""
        return """
<div id="supplier-import-panel" style="padding: 16px; max-width: 560px;">
  <h5 style="margin-bottom: 12px;">Import a part from a supplier SKU</h5>

  <div style="margin-bottom: 10px;">
    <label for="si-supplier" style="font-weight:600">Supplier</label>
    <select id="si-supplier" class="form-control" style="margin-top:4px">
      <option value="mouser">Mouser</option>
      <option value="digikey">DigiKey</option>
      <option value="farnell">Farnell</option>
      <option value="rs">RS Components</option>
    </select>
  </div>

  <div style="margin-bottom: 10px;">
    <label for="si-sku" style="font-weight:600">SKU / Part Number</label>
    <input id="si-sku" class="form-control" type="text" placeholder="e.g. 667-ERJ-3EKF1001V"
           style="margin-top:4px"/>
  </div>

  <button id="si-submit" class="btn btn-primary" onclick="siImportSku()">
    <i class="fas fa-download"></i> Import
  </button>

  <div id="si-result" style="margin-top: 14px; display:none;"></div>
</div>

<script>
function siImportSku() {
  const supplier = document.getElementById('si-supplier').value;
  const sku = document.getElementById('si-sku').value.trim();
  const resultDiv = document.getElementById('si-result');

  if (!sku) {
    resultDiv.innerHTML = '<div class="alert alert-warning">Please enter a SKU.</div>';
    resultDiv.style.display = 'block';
    return;
  }

  document.getElementById('si-submit').disabled = true;
  resultDiv.innerHTML = '<div class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Importing...</div>';
  resultDiv.style.display = 'block';

  fetch('/plugin/supplier-import/import-sku/', {
    method: 'POST',
    headers: {'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken')},
    body: JSON.stringify({supplier, sku}),
  })
  .then(r => r.json())
  .then(data => {
    document.getElementById('si-submit').disabled = false;
    if (data.success) {
      resultDiv.innerHTML = `
        <div class="alert alert-success">
          <strong>✓ Part created!</strong><br>
          IPN: <code>${data.ipn}</code> &nbsp;
          <a href="/part/${data.part_pk}/" target="_blank">Open part →</a>
        </div>`;
    } else {
      resultDiv.innerHTML = `<div class="alert alert-danger"><strong>Error:</strong> ${data.error}</div>`;
    }
  })
  .catch(err => {
    document.getElementById('si-submit').disabled = false;
    resultDiv.innerHTML = `<div class="alert alert-danger">Request failed: ${err}</div>`;
  });
}

function getCookie(name) {
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? v[2] : null;
}
</script>
"""

    # ------------------------------------------------------------------ #
    #  Views                                                               #
    # ------------------------------------------------------------------ #
    @method_decorator(csrf_exempt, name="dispatch")
    class ImportSkuView(View):
        plugin = None

        def post(self, request, *args, **kwargs):
            try:
                body = json.loads(request.body)
                supplier_name = body.get("supplier", "").strip()
                sku = body.get("sku", "").strip()
            except Exception:
                return JsonResponse({"success": False, "error": "Invalid JSON body"}, status=400)

            if not supplier_name or not sku:
                return JsonResponse({"success": False, "error": "supplier and sku are required"}, status=400)

            supplier = self.plugin._get_supplier(supplier_name)
            if supplier is None:
                return JsonResponse({"success": False, "error": f"Unknown supplier: {supplier_name}"}, status=400)

            part_data = supplier.fetch_part(sku)
            if part_data is None:
                return JsonResponse({"success": False, "error": f"SKU '{sku}' not found at {supplier_name}"})

            prefix = self.plugin.get_setting("IPN_PREFIX") or "LAB"
            result = create_part_from_supplier_data(request.plugin_api, part_data, prefix)
            return JsonResponse(result)

    @method_decorator(csrf_exempt, name="dispatch")
    class ImportCsvView(View):
        plugin = None

        def post(self, request, *args, **kwargs):
            csv_file = request.FILES.get("csv_file")
            if not csv_file:
                return JsonResponse({"success": False, "error": "No file uploaded"}, status=400)

            text = csv_file.read().decode("utf-8-sig")
            reader = csv.DictReader(io.StringIO(text))

            # Accept headers: supplier, sku  (case-insensitive)
            results = []
            prefix = self.plugin.get_setting("IPN_PREFIX") or "LAB"

            for row in reader:
                # Normalise header names
                row = {k.lower().strip(): v.strip() for k, v in row.items()}
                supplier_name = row.get("supplier", "")
                sku = row.get("sku", "")

                if not supplier_name or not sku:
                    results.append({
                        "sku": sku or "?",
                        "supplier": supplier_name or "?",
                        "success": False,
                        "error": "Missing supplier or sku column",
                    })
                    continue

                supplier = self.plugin._get_supplier(supplier_name)
                if supplier is None:
                    results.append({
                        "sku": sku,
                        "supplier": supplier_name,
                        "success": False,
                        "error": f"Unknown supplier: {supplier_name}",
                    })
                    continue

                try:
                    part_data = supplier.fetch_part(sku)
                    if part_data is None:
                        results.append({
                            "sku": sku,
                            "supplier": supplier_name,
                            "success": False,
                            "error": "SKU not found",
                        })
                        continue

                    result = create_part_from_supplier_data(request.plugin_api, part_data, prefix)
                    results.append({
                        "sku": sku,
                        "supplier": supplier_name,
                        **result,
                    })
                except Exception as e:
                    results.append({
                        "sku": sku,
                        "supplier": supplier_name,
                        "success": False,
                        "error": str(e),
                    })

            total = len(results)
            ok = sum(1 for r in results if r.get("success"))
            return JsonResponse({"total": total, "imported": ok, "failed": total - ok, "results": results})

    class ImportPageView(View):
        plugin = None

        def get(self, request, *args, **kwargs):
            from django.http import HttpResponse
            html = """
<!doctype html>
<html>
<head>
  <title>Supplier CSV Import</title>
  <link rel="stylesheet"
        href="https://cdn.jsdelivr.net/npm/bootstrap@4.6.2/dist/css/bootstrap.min.css">
  <link rel="stylesheet"
        href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/5.15.4/css/all.min.css">
  <style>
    body { padding: 32px; background: #f8f9fa; }
    .card { max-width: 700px; }
    .result-row-ok  { background: #d4edda; }
    .result-row-err { background: #f8d7da; }
    pre { font-size: 0.82em; }
  </style>
</head>
<body>
<div class="card shadow-sm">
  <div class="card-header bg-primary text-white">
    <i class="fas fa-file-csv"></i> Bulk CSV Import — Supplier Parts
  </div>
  <div class="card-body">

    <p class="text-muted">
      Upload a CSV file with two columns: <code>supplier</code> and <code>sku</code>.<br>
      Accepted supplier values: <strong>mouser, digikey, farnell, rs</strong>
    </p>

    <div class="mb-3">
      <label class="font-weight-bold">CSV file</label>
      <input type="file" id="csv-file" accept=".csv" class="form-control-file mt-1"/>
    </div>

    <button class="btn btn-primary" onclick="uploadCsv()">
      <i class="fas fa-upload"></i> Import CSV
    </button>
    <button class="btn btn-outline-secondary ml-2" onclick="downloadTemplate()">
      <i class="fas fa-download"></i> Download template
    </button>

    <div id="progress" style="display:none; margin-top:16px">
      <div class="alert alert-info">
        <i class="fas fa-spinner fa-spin"></i> Importing, please wait…
      </div>
    </div>

    <div id="summary" style="display:none; margin-top:16px"></div>
    <div id="results-table" style="margin-top:12px"></div>
  </div>
</div>

<script>
function getCookie(name) {
  const v = document.cookie.match('(^|;) ?' + name + '=([^;]*)(;|$)');
  return v ? v[2] : null;
}

function downloadTemplate() {
  const content = 'supplier,sku\\nmouser,667-ERJ-3EKF1001V\\ndigikey,311-1.00KCRCT-ND\\nfarnell,1469817\\nrs,123-4567\\n';
  const a = document.createElement('a');
  a.href = 'data:text/csv,' + encodeURIComponent(content);
  a.download = 'import_template.csv';
  a.click();
}

function uploadCsv() {
  const fileInput = document.getElementById('csv-file');
  const file = fileInput.files[0];
  if (!file) { alert('Please select a CSV file.'); return; }

  const formData = new FormData();
  formData.append('csv_file', file);

  document.getElementById('progress').style.display = 'block';
  document.getElementById('summary').style.display = 'none';
  document.getElementById('results-table').innerHTML = '';

  fetch('/plugin/supplier-import/import-csv/', {
    method: 'POST',
    headers: {'X-CSRFToken': getCookie('csrftoken')},
    body: formData,
  })
  .then(r => r.json())
  .then(data => {
    document.getElementById('progress').style.display = 'none';
    const summDiv = document.getElementById('summary');
    summDiv.style.display = 'block';
    summDiv.innerHTML = `
      <div class="alert ${data.failed === 0 ? 'alert-success' : 'alert-warning'}">
        <strong>Done!</strong>
        ${data.imported}/${data.total} parts imported successfully.
        ${data.failed > 0 ? `<br>${data.failed} error(s) — see table below.` : ''}
      </div>`;

    // Build results table
    let rows = data.results.map(r => `
      <tr class="${r.success ? 'result-row-ok' : 'result-row-err'}">
        <td>${r.supplier}</td>
        <td><code>${r.sku}</code></td>
        <td>${r.success ? '✓' : '✗'}</td>
        <td>${r.ipn || ''}</td>
        <td>${r.part_pk ? '<a href="/part/' + r.part_pk + '/" target="_blank">Open →</a>' : ''}</td>
        <td><small>${r.error || ''}</small></td>
      </tr>`).join('');

    document.getElementById('results-table').innerHTML = `
      <table class="table table-sm table-bordered">
        <thead class="thead-light">
          <tr>
            <th>Supplier</th><th>SKU</th><th>Status</th>
            <th>IPN</th><th>Link</th><th>Details</th>
          </tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>`;
  })
  .catch(err => {
    document.getElementById('progress').style.display = 'none';
    document.getElementById('summary').innerHTML =
      `<div class="alert alert-danger">Request failed: ${err}</div>`;
    document.getElementById('summary').style.display = 'block';
  });
}
</script>
</body>
</html>
"""
            return HttpResponse(html)
