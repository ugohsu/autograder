document.querySelectorAll(".ak-input").forEach((el) => {
  el.addEventListener("change", async () => {
    const { qnum, field } = el.dataset;
    const row = el.closest("tr");
    const status = row.querySelector(".save-status");
    flashStatus(status, "保存中…", 0);
    try {
      const res = await fetch(`/batch/${window.BATCH_ID}/answer_key/${qnum}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ field, value: el.value }),
      });
      if (!res.ok) throw new Error("save failed");
      const data = await res.json();
      if (field === "correct_option") {
        row.classList.toggle("row-keyed", data.value !== null && data.value !== undefined);
      }
      flashStatus(status, "保存済み");
    } catch (e) {
      flashStatus(status, "保存失敗");
    }
  });
});
