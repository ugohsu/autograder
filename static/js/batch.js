document.querySelectorAll("tr.clickable-row").forEach((row) => {
  row.addEventListener("click", (event) => {
    if (event.target.closest(".no-navigate")) return;
    const href = row.dataset.href;
    if (href) window.location.href = href;
  });
});

function flashStatus(el, text, ms = 1500) {
  if (!el) return;
  el.textContent = text;
  if (ms) setTimeout(() => { el.textContent = ""; }, ms);
}

document.querySelectorAll(".student-id-input").forEach((input) => {
  input.addEventListener("change", async () => {
    const studentId = input.dataset.studentId;
    const status = input.parentElement.querySelector(".save-status");
    flashStatus(status, "保存中…", 0);
    try {
      const res = await fetch(`/batch/${window.BATCH_ID}/student/${studentId}/id`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ student_id: input.value }),
      });
      if (!res.ok) throw new Error("save failed");
      flashStatus(status, "保存済み");
    } catch (e) {
      flashStatus(status, "保存失敗");
    }
  });
});

document.querySelectorAll(".batch-note-input").forEach((input) => {
  input.addEventListener("change", async () => {
    const batchId = input.dataset.batchId;
    const status = input.parentElement.querySelector(".save-status");
    flashStatus(status, "保存中…", 0);
    try {
      const res = await fetch(`/batch/${batchId}/note`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ note: input.value }),
      });
      if (!res.ok) throw new Error("save failed");
      flashStatus(status, "保存済み");
    } catch (e) {
      flashStatus(status, "保存失敗");
    }
  });
});

document.querySelectorAll(".batch-active-qcount-input").forEach((input) => {
  input.addEventListener("change", async () => {
    const batchId = input.dataset.batchId;
    const status = input.parentElement.querySelector(".save-status");
    flashStatus(status, "保存中…", 0);
    try {
      const res = await fetch(`/batch/${batchId}/active_question_count`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active_question_count: input.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.error || "save failed");
      // 試験詳細ページ（要確認数・得点・CSVボタンの有効/無効など、有効問題番号に
      // 連動する表示が多数ある）では、その場で全部を書き換える代わりに再読み込みして
      // 表示を最新の状態に揃える。一覧ページ（試験ごとの行だけ）では不要なので対象外。
      if (window.BATCH_ID != null && String(window.BATCH_ID) === String(batchId)) {
        window.location.reload();
        return;
      }
      flashStatus(status, "保存済み");
    } catch (e) {
      flashStatus(status, e.message === "save failed" ? "保存失敗" : e.message);
    }
  });
});

function markRowReviewed(row) {
  if (!row) return;
  const btn = row.querySelector(".btn-confirm-row");
  if (btn) {
    const badge = document.createElement("span");
    badge.className = "resolved-badge";
    badge.textContent = "確認済み";
    btn.replaceWith(badge);
  }
}

async function saveAnswerOverride(studentId, qnum, option, status) {
  flashStatus(status, "保存中…", 0);
  try {
    const res = await fetch(`/batch/${window.BATCH_ID}/student/${studentId}/answer/${qnum}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ option }),
    });
    if (!res.ok) throw new Error("save failed");
    flashStatus(status, "保存済み");
    return true;
  } catch (e) {
    flashStatus(status, "保存失敗");
    return false;
  }
}

document.querySelectorAll(".answer-override").forEach((select) => {
  select.addEventListener("change", async () => {
    const { studentId, qnum } = select.dataset;
    const row = select.closest(".qrow");
    const status = row.querySelector(".save-status");
    if (await saveAnswerOverride(studentId, qnum, select.value, status)) {
      markRowReviewed(row);
    }
  });
});

document.querySelectorAll(".btn-confirm-row").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const { studentId, qnum } = btn.dataset;
    const row = btn.closest(".qrow");
    const select = row.querySelector(".answer-override");
    const status = row.querySelector(".save-status");
    if (await saveAnswerOverride(studentId, qnum, select.value, status)) {
      markRowReviewed(row);
    }
  });
});

const deleteBtn = document.getElementById("btn-delete-batch");
if (deleteBtn) {
  deleteBtn.addEventListener("click", async () => {
    const { batchId, batchName } = deleteBtn.dataset;
    if (!window.confirm(`「${batchName}」を削除しますか？学生の読み取り結果・画像・解答もすべて削除され、元に戻せません。`)) return;
    try {
      const res = await fetch(`/batch/${batchId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("delete failed");
      window.location.href = "/";
    } catch (e) {
      window.alert("削除に失敗しました。");
    }
  });
}
