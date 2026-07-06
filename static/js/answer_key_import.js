const SAMPLE = {
  answer_key: [
    {
      question_number: 1,
      correct_option: 3,
      points: 2,
      group_number: 1,
      explanation: "光合成の過程で放出される気体はどれか、という設問。③酸素が正答。",
      _confidence: 1.0,
    },
    {
      question_number: 2,
      group_number: 1,
      points: 2,
      _comment: "正答表のこの箇所が不鮮明で読み取れなかったため、正答は未入力にしてある。教員に確認が必要。",
      _confidence: 0.4,
    },
  ],
};

const alertBox = document.getElementById("alert-box");
const jsonFile = document.getElementById("json-file");
const jsonInput = document.getElementById("json-input");
const sampleBtn = document.getElementById("btn-sample");
const previewBtn = document.getElementById("btn-preview");
const clearBtn = document.getElementById("btn-clear");
const stepPreview = document.getElementById("step-preview");
const summaryEl = document.getElementById("preview-summary");
const previewListEl = document.getElementById("preview-list");
const checkAllBtn = document.getElementById("btn-check-all");
const uncheckAllBtn = document.getElementById("btn-uncheck-all");
const commitBtn = document.getElementById("btn-commit");

const OPTION_SYMBOLS = ["①", "②", "③", "④", "⑤"];

let previewRows = [];

function showAlert(message) {
  alertBox.innerHTML = `<div class="alert alert-error">${escapeHtml(message)}</div>`;
}

function escapeHtml(value) {
  if (value == null) return "";
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

jsonFile.addEventListener("change", () => {
  const file = jsonFile.files[0];
  if (!file) return;
  const reader = new FileReader();
  reader.onload = (e) => { jsonInput.value = e.target.result; };
  reader.readAsText(file, "utf-8");
});

sampleBtn.addEventListener("click", (e) => {
  e.preventDefault();
  jsonInput.value = JSON.stringify(SAMPLE, null, 2);
});

clearBtn.addEventListener("click", () => {
  jsonInput.value = "";
  jsonFile.value = "";
  stepPreview.style.display = "none";
  alertBox.innerHTML = "";
  previewRows = [];
});

previewBtn.addEventListener("click", async () => {
  alertBox.innerHTML = "";
  let payload;
  try {
    payload = JSON.parse(jsonInput.value);
  } catch (err) {
    showAlert("JSON のパースに失敗しました: " + err.message);
    return;
  }
  try {
    const res = await fetch(`/batch/${window.BATCH_ID}/answer_key/import/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || "プレビューに失敗しました");
    previewRows = body.rows.map((row) => ({ ...row, checked: row.default_checked }));
    renderPreview();
    stepPreview.style.display = "block";
  } catch (err) {
    showAlert(err.message);
  }
});

function renderPreview() {
  const total = previewRows.length;
  const validCount = previewRows.filter((r) => r.valid).length;
  summaryEl.textContent = total - validCount > 0
    ? `${total}件中 ${validCount}件が有効、${total - validCount}件にエラー`
    : `${total}件中 ${validCount}件が有効`;
  previewListEl.innerHTML = previewRows.map(rowHtml).join("");
  updateCommitSummary();
}

function updateCommitSummary() {
  const n = previewRows.filter((r) => r.checked).length;
  commitBtn.textContent = n > 0 ? `インポート実行（${n}件）` : "インポート実行";
}

function fieldHtml(row, field, label, inputType) {
  const value = row.cleaned[field];
  if (field === "correct_option") {
    const options = ['<option value="">―</option>'].concat(
      OPTION_SYMBOLS.map((sym, i) => `<option value="${i + 1}" ${value === i + 1 ? "selected" : ""}>${sym}</option>`)
    );
    return `
      <div class="field"><label>${label}</label>
        <select class="ak-preview-field" data-idx="${row.index}" data-field="${field}">${options.join("")}</select>
      </div>
    `;
  }
  return `
    <div class="field"><label>${label}</label>
      <input type="${inputType}" class="ak-preview-field" data-idx="${row.index}" data-field="${field}"
             value="${value == null ? "" : escapeHtml(value)}">
    </div>
  `;
}

function rowHtml(row) {
  if (!row.cleaned) {
    return `
      <div class="card import-row">
        <div class="card-header"><strong>#${row.index + 1}</strong> <span class="badge badge-danger">エラー</span></div>
        <div class="alert alert-error">${row.errors.map(escapeHtml).join("<br>")}</div>
      </div>
    `;
  }

  const badges = [];
  if (!row.valid) badges.push('<span class="badge badge-danger">エラー</span>');
  const conf = row.confidence;
  if (typeof conf === "number" && conf < 0.8) {
    badges.push(`<span class="badge badge-warning">確信度 ${Math.round(conf * 100)}%</span>`);
  }
  if (row.no_change) badges.push('<span class="badge">変更なし</span>');
  else if (row.existing) badges.push('<span class="badge badge-update">更新</span>');
  else badges.push('<span class="badge badge-new">新規</span>');

  const qLabel = row.cleaned.question_number != null ? `Q${row.cleaned.question_number}` : `#${row.index + 1}`;

  return `
    <div class="card import-row">
      <div class="card-header">
        <input type="checkbox" class="import-check" data-idx="${row.index}" ${row.checked ? "checked" : ""} ${row.valid ? "" : "disabled"}>
        <strong>${qLabel}</strong>
        ${badges.join(" ")}
      </div>
      ${row.comment ? `<p class="hint">${escapeHtml(row.comment)}</p>` : ""}
      <div class="field-row">
        ${fieldHtml(row, "question_number", "設問番号", "number")}
        ${fieldHtml(row, "group_number", "大問", "number")}
        ${fieldHtml(row, "correct_option", "正答", "text")}
        ${fieldHtml(row, "points", "配点", "number")}
      </div>
      <div class="field-row">
        ${fieldHtml(row, "explanation", "解説", "text")}
        ${fieldHtml(row, "memo", "メモ", "text")}
      </div>
      ${row.existing ? `<p class="hint">現在の登録: 正答${row.existing.correct_option != null ? OPTION_SYMBOLS[row.existing.correct_option - 1] : "―"} / 配点${row.existing.points != null ? row.existing.points : "―"}</p>` : ""}
      ${row.errors.length ? `<div class="alert alert-error">${row.errors.map(escapeHtml).join("<br>")}</div>` : ""}
    </div>
  `;
}

previewListEl.addEventListener("change", (e) => {
  const idx = Number(e.target.dataset.idx);
  if (Number.isNaN(idx)) return;
  const row = previewRows[idx];

  if (e.target.classList.contains("import-check")) {
    row.checked = e.target.checked;
    updateCommitSummary();
    return;
  }
  if (e.target.classList.contains("ak-preview-field")) {
    const field = e.target.dataset.field;
    const raw = e.target.value;
    row.cleaned[field] = raw === "" ? null : (field === "explanation" || field === "memo" ? raw : Number(raw));
    renderPreview();
  }
});

checkAllBtn.addEventListener("click", () => {
  previewRows.forEach((r) => { if (r.valid) r.checked = true; });
  renderPreview();
});

uncheckAllBtn.addEventListener("click", () => {
  previewRows.forEach((r) => { r.checked = false; });
  renderPreview();
});

commitBtn.addEventListener("click", async () => {
  const checkedRows = previewRows.filter((r) => r.checked && r.cleaned);
  if (checkedRows.length === 0) {
    showAlert("インポートする行が選択されていません。");
    return;
  }
  if (!window.confirm(`${checkedRows.length}件をインポートします。よろしいですか？`)) return;
  try {
    const res = await fetch(`/batch/${window.BATCH_ID}/answer_key/import/commit`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: checkedRows.map((r) => r.cleaned) }),
    });
    const body = await res.json();
    if (!res.ok) throw new Error(body.error || "インポートに失敗しました");
    alertBox.innerHTML = `<div class="alert alert-success">${body.applied}件の正答キーを反映しました。<a href="/batch/${window.BATCH_ID}/answer_key">正答・配点画面で確認する</a></div>`;
    stepPreview.style.display = "none";
    jsonInput.value = "";
    jsonFile.value = "";
    previewRows = [];
  } catch (err) {
    showAlert(err.message);
  }
});
