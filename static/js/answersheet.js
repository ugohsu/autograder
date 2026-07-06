document.querySelectorAll(".as-input").forEach((el) => {
  el.addEventListener("change", async () => {
    const field = el.dataset.field;
    const status = el.parentElement.querySelector(".save-status")
      || el.closest(".field-row").querySelector(".save-status");
    flashStatus(status, "保存中…", 0);
    try {
      const res = await fetch(window.location.pathname, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ field, value: el.value }),
      });
      if (!res.ok) throw new Error("save failed");
      flashStatus(status, "保存済み");
    } catch (e) {
      flashStatus(status, "保存失敗");
    }
  });
});

function flashStatus(el, text, ms = 1500) {
  if (!el) return;
  el.textContent = text;
  if (ms) setTimeout(() => { el.textContent = ""; }, ms);
}

const deleteBtn = document.getElementById("btn-delete-answersheet");
if (deleteBtn) {
  deleteBtn.addEventListener("click", async () => {
    const { sheetId, sheetName } = deleteBtn.dataset;
    if (!window.confirm(`「${sheetName}」を削除しますか？元に戻せません。`)) return;
    try {
      const res = await fetch(`/answersheets/${sheetId}`, { method: "DELETE" });
      if (!res.ok) throw new Error("delete failed");
      window.location.href = "/answersheets";
    } catch (e) {
      window.alert("削除に失敗しました。");
    }
  });
}
