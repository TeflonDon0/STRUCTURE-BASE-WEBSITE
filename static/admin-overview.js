// Keep every permitted module available; collapse the secondary index on small screens.
const modulePicker = document.querySelector(".admin-module-picker");
const moduleSection = document.getElementById("admin-modules");
if (modulePicker && moduleSection) {
  const compactOverview = window.matchMedia("(max-width: 760px)");
  const syncModulePicker = () => {
    modulePicker.open = !compactOverview.matches;
  };
  compactOverview.addEventListener("change", syncModulePicker);
  syncModulePicker();
  moduleSection.addEventListener("focus", () => {
    modulePicker.open = true;
  });
  if (window.location.hash === "#admin-modules") modulePicker.open = true;
}
