// Keep feedback and the first request field reachable after navigation.
const tenantRequestSection = document.getElementById("maintenance-request");
const tenantResidentName = document.getElementById("resident_name");
const tenantFeedback = document.querySelector("[data-tenant-feedback]");

tenantRequestSection?.addEventListener("focus", () => {
  tenantResidentName?.focus({ preventScroll: true });
});

if (tenantFeedback) {
  // Let native fragment navigation finish before placing focus on feedback.
  window.addEventListener("load", () => {
    window.requestAnimationFrame(() => tenantFeedback.focus());
  }, { once: true });
} else if (window.location.hash === "#maintenance-request") {
  tenantResidentName?.focus();
}
