document.addEventListener("DOMContentLoaded", () => {
  const toggle = document.querySelector(".menu-toggle");
  const app = document.querySelector(".app");
  const backdrop = document.querySelector(".backdrop");
  if (toggle && app) {
    toggle.addEventListener("click", () => app.classList.toggle("sidebar-open"));
  }
  if (backdrop && app) {
    backdrop.addEventListener("click", () => app.classList.remove("sidebar-open"));
  }
});
