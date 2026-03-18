/**
 * SupplierImportPanel.js
 * Panel "Import Fournisseur" pour InvenTree >= 1.0
 *
 * Appelé par InvenTree via :
 *   renderSupplierImportPanel(target, context)
 *
 * `context` contient :
 *   - context.context.api_url    : URL POST import SKU
 *   - context.context.csv_page_url : URL page CSV
 *   - context.host               : base URL InvenTree
 */

function renderSupplierImportPanel(target, context) {
  const apiUrl = (context.context && context.context.api_url) || '/plugin/supplier-import/import-sku/';
  const csvUrl = (context.context && context.context.csv_page_url) || '/plugin/supplier-import/csv-page/';

  // Injection du HTML dans le panel
  target.innerHTML = `
    <div style="padding: 16px; max-width: 560px; font-family: inherit;">
      <div style="margin-bottom: 14px; display: flex; gap: 8px; align-items: center;">
        <a href="${csvUrl}" target="_blank"
           style="font-size: 0.85em; color: #666; text-decoration: none;">
          📄 Import en masse (CSV) →
        </a>
      </div>

      <div style="margin-bottom: 10px;">
        <label style="font-weight: 600; display: block; margin-bottom: 4px;">Fournisseur</label>
        <select id="si-supplier" style="width: 100%; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px;">
          <option value="mouser">Mouser</option>
          <option value="digikey">DigiKey</option>
          <option value="farnell">Farnell</option>
          <option value="rs">RS Components</option>
        </select>
      </div>

      <div style="margin-bottom: 12px;">
        <label style="font-weight: 600; display: block; margin-bottom: 4px;">SKU / Référence fournisseur</label>
        <input id="si-sku" type="text" placeholder="ex : 667-ERJ-3EKF1001V"
               style="width: 100%; padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px;"/>
      </div>

      <button id="si-btn"
              style="padding: 8px 18px; background: #1c7ed6; color: white; border: none;
                     border-radius: 4px; cursor: pointer; font-size: 0.95em;">
        ⬇ Importer le composant
      </button>

      <div id="si-result" style="margin-top: 14px;"></div>
    </div>
  `;

  // Gestion du clic
  const btn = target.querySelector('#si-btn');
  btn.addEventListener('click', () => {
    const supplier = target.querySelector('#si-supplier').value;
    const sku = target.querySelector('#si-sku').value.trim();
    const resultDiv = target.querySelector('#si-result');

    if (!sku) {
      resultDiv.innerHTML = '<div style="color: #e67700; padding: 8px; background: #fff3bf; border-radius: 4px;">Veuillez saisir un SKU.</div>';
      return;
    }

    btn.disabled = true;
    btn.textContent = '⏳ Import en cours…';
    resultDiv.innerHTML = '';

    // Récupération du CSRF token
    const csrfToken = getCsrfToken();

    fetch(apiUrl, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken,
      },
      body: JSON.stringify({ supplier, sku }),
    })
      .then(r => r.json())
      .then(data => {
        btn.disabled = false;
        btn.textContent = '⬇ Importer le composant';
        if (data.success) {
          resultDiv.innerHTML = `
            <div style="padding: 10px; background: #d3f9d8; border-radius: 4px; color: #2b8a3e;">
              ✅ <strong>Composant créé !</strong>
              IPN : <code>${data.ipn}</code>
              &nbsp;—&nbsp;
              <a href="/part/${data.part_pk}/" target="_blank" style="color: #2b8a3e;">
                Ouvrir la fiche →
              </a>
            </div>`;
        } else {
          resultDiv.innerHTML = `
            <div style="padding: 10px; background: #ffe3e3; border-radius: 4px; color: #c92a2a;">
              ❌ <strong>Erreur :</strong> ${data.error || 'Erreur inconnue'}
            </div>`;
        }
      })
      .catch(err => {
        btn.disabled = false;
        btn.textContent = '⬇ Importer le composant';
        resultDiv.innerHTML = `
          <div style="padding: 10px; background: #ffe3e3; border-radius: 4px; color: #c92a2a;">
            ❌ Requête échouée : ${err}
          </div>`;
      });
  });
}

function getCsrfToken() {
  // 1. Depuis les cookies (méthode standard Django)
  const match = document.cookie.match('(^|;) ?csrftoken=([^;]*)(;|$)');
  if (match) return match[2];
  // 2. Depuis le meta tag si disponible
  const meta = document.querySelector('meta[name="csrf-token"]');
  if (meta) return meta.getAttribute('content');
  return '';
}
