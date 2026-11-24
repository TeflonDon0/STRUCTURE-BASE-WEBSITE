// Progressive mobile disclosure: without JavaScript every original form stays available.
(() => {
  const compact = window.matchMedia("(max-width: 760px)");
  document.querySelectorAll("body.admin-workspace-page form.dashboard-filter-bar").forEach((form) => {
    if ((form.getAttribute("method") || "get").toLowerCase() !== "get") return;
    const details = document.createElement("details");
    details.className = "mobile-disclosure mobile-filter-panel";
    details.dataset.mobileDisclosure = "";
    details.dataset.activeFilters = String(new URLSearchParams(window.location.search).size > 0);
    const summary = document.createElement("summary");
    summary.textContent = form.getAttribute("aria-label") || "Filter records";
    form.before(details);
    details.append(summary, form);
  });

  const disclosures = document.querySelectorAll("[data-mobile-disclosure]");
  const syncDisclosures = () => {
    disclosures.forEach((details) => {
      details.open = !compact.matches || details.dataset.activeFilters === "true" || details.contains(document.activeElement);
    });
  };
  compact.addEventListener("change", syncDisclosures);
  syncDisclosures();

  const header = document.querySelector(".site-header");
  const placeNavigation = () => {
    if (!header) return;
    const top = Math.max(8, Math.min(header.getBoundingClientRect().bottom + 8, window.innerHeight - 100));
    document.documentElement.style.setProperty("--mobile-nav-top", `${top}px`);
    document.documentElement.style.setProperty("--mobile-header-height", `${header.getBoundingClientRect().height}px`);
  };
  document.getElementById("nav-toggle")?.addEventListener("click", placeNavigation, { capture: true });
  window.addEventListener("resize", placeNavigation, { passive: true });
  placeNavigation();

  const moreNavigation = document.querySelector(".admin-nav-more");
  if (moreNavigation) {
    document.addEventListener("click", (event) => {
      if (!moreNavigation.contains(event.target)) moreNavigation.open = false;
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !moreNavigation.open) return;
      moreNavigation.open = false;
      if (window.matchMedia("(min-width: 861px)").matches) moreNavigation.querySelector("summary")?.focus();
    });
  }

  // Existing reference tables keep all columns and become keyboard-scrollable regions.
  document.querySelectorAll(".document-schema-table").forEach((region) => {
    region.tabIndex = 0;
    region.setAttribute("role", "region");
    region.setAttribute("aria-label", "Document field reference table");
  });
})();
