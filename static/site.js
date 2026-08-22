const body = document.body;
const nav = document.getElementById("main-nav");
const toggle = document.getElementById("nav-toggle");
const imageInput = document.getElementById("image");
const imagePreview = document.getElementById("image-preview");
const previewWrap = document.getElementById("preview-wrap");
const issueImageInput = document.getElementById("issue_image");
const issueImagePreview = document.getElementById("issue-image-preview");
const issuePreviewWrap = document.getElementById("issue-preview-wrap");
const issuePreviewEmpty = document.getElementById("issue-preview-empty");
const detailMainImage = document.getElementById("detail-main-image");
const prioritySelect = document.getElementById("priority");
const emergencyNote = document.getElementById("emergency-note");
const backToTop = document.getElementById("back-to-top");
const pageTop = document.getElementById("page-top");
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");

document.querySelectorAll("[data-home-filters]").forEach((filters) => {
  const mobileFilters = window.matchMedia("(max-width: 760px)");
  const syncHomeFilters = () => {
    if (mobileFilters.matches && !filters.dataset.userOpened) {
      filters.removeAttribute("open");
      return;
    }
    if (!mobileFilters.matches) {
      filters.setAttribute("open", "");
    }
  };

  filters.addEventListener("toggle", () => {
    if (mobileFilters.matches && filters.open) {
      filters.dataset.userOpened = "true";
    }
  });
  mobileFilters.addEventListener?.("change", syncHomeFilters);
  syncHomeFilters();
});

document.querySelectorAll("[data-listing-filters]").forEach((filters) => {
  const compactFilters = window.matchMedia("(max-width: 860px)");
  const hasActiveFilters = filters.dataset.hasActiveFilters === "true";
  const syncListingFilters = () => {
    if (compactFilters.matches && !hasActiveFilters && !filters.dataset.userOpened) {
      filters.removeAttribute("open");
      return;
    }
    if (!compactFilters.matches || hasActiveFilters) {
      filters.setAttribute("open", "");
    }
  };

  filters.addEventListener("toggle", () => {
    if (compactFilters.matches && filters.open) {
      filters.dataset.userOpened = "true";
    }
  });
  compactFilters.addEventListener?.("change", syncListingFilters);
  syncListingFilters();
});

document.querySelectorAll("[data-open-filter]").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const filters = document.querySelector("[data-listing-filters]");
    if (filters) {
      filters.dataset.userOpened = "true";
      filters.setAttribute("open", "");
      window.requestAnimationFrame(() => {
        const firstField = filters.querySelector("input, select, button, a");
        firstField?.focus({ preventScroll: true });
      });
    }
  });
});

const PUBLIC_HEADER_SCROLL_THRESHOLD = 40;
let scrollStateFrame = null;

const setScrollState = () => {
  body.classList.toggle("has-scrolled", window.scrollY > PUBLIC_HEADER_SCROLL_THRESHOLD);
  if (backToTop) {
    const showBackToTop = window.scrollY > 520;
    backToTop.classList.toggle("is-visible", showBackToTop);
    backToTop.tabIndex = showBackToTop ? 0 : -1;
    backToTop.setAttribute("aria-hidden", String(!showBackToTop));
  }
};

const requestScrollState = () => {
  if (scrollStateFrame !== null) {
    return;
  }

  scrollStateFrame = window.requestAnimationFrame(() => {
    setScrollState();
    scrollStateFrame = null;
  });
};

setScrollState();
window.addEventListener("scroll", requestScrollState, { passive: true });

if (backToTop) {
  backToTop.addEventListener("click", () => {
    window.scrollTo({ top: 0, behavior: reducedMotion.matches ? "auto" : "smooth" });
    window.setTimeout(() => {
      pageTop?.focus({ preventScroll: true });
    }, reducedMotion.matches ? 0 : 320);
  });
}

document.querySelectorAll('a[href^="#"]:not([href="#"])').forEach((link) => {
  link.addEventListener("click", () => {
    const targetId = link.hash.slice(1);
    const target = targetId ? document.getElementById(targetId) : null;
    if (!target) {
      return;
    }
    if (!target.hasAttribute("tabindex")) {
      target.setAttribute("tabindex", "-1");
      target.dataset.anchorFocusTarget = "true";
    }
    window.setTimeout(() => {
      target.focus({ preventScroll: true });
    }, reducedMotion.matches ? 0 : 320);
  });
});

const copyTextToClipboard = async (value) => {
  if (navigator.clipboard && window.isSecureContext) {
    await navigator.clipboard.writeText(value);
    return;
  }

  const fallback = document.createElement("textarea");
  fallback.value = value;
  fallback.setAttribute("readonly", "");
  fallback.style.position = "fixed";
  fallback.style.left = "0";
  fallback.style.top = "0";
  fallback.style.opacity = "0";
  document.body.appendChild(fallback);
  fallback.focus();
  fallback.select();
  fallback.setSelectionRange(0, fallback.value.length);
  const copied = document.execCommand("copy");
  fallback.remove();
  if (!copied) {
    throw new Error("Clipboard access is unavailable.");
  }
};

document.querySelectorAll("[data-partner-marketing-actions]").forEach((actions) => {
  const eventUrl = actions.dataset.eventUrl;
  const csrfToken = actions.dataset.csrf;
  const listingId = actions.dataset.listingId;
  const status = actions.querySelector("[data-partner-action-status]");

  const announce = (message, isError = false) => {
    if (!status) {
      return;
    }
    status.textContent = message;
    status.classList.toggle("form-error", isError);
  };

  const recordEvent = (eventType) => {
    if (!eventUrl || !csrfToken || !listingId) {
      return Promise.resolve();
    }
    const payload = new FormData();
    payload.append("csrf_token", csrfToken);
    payload.append("listing_id", listingId);
    payload.append("event_type", eventType);
    return fetch(eventUrl, {
      method: "POST",
      body: payload,
      credentials: "same-origin",
      keepalive: true,
      headers: { Accept: "application/json" },
    }).then((response) => {
      if (!response.ok) {
        throw new Error("The activity could not be recorded.");
      }
    });
  };

  actions.querySelector("[data-partner-copy]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    button.setAttribute("aria-busy", "true");
    try {
      await copyTextToClipboard(button.dataset.copyValue || "");
      announce("Referral link copied.");
      recordEvent("LINK_COPIED").catch(() => {});
    } catch (error) {
      announce("Copy failed. Select the referral URL and copy it manually.", true);
    } finally {
      button.removeAttribute("aria-busy");
    }
  });

  actions.querySelector("[data-partner-share]")?.addEventListener("click", async (event) => {
    const button = event.currentTarget;
    const shareData = {
      title: button.dataset.shareTitle || document.title,
      text: button.dataset.shareText || "",
      url: button.dataset.shareUrl || window.location.href,
    };
    button.setAttribute("aria-busy", "true");
    try {
      if (navigator.share) {
        await navigator.share(shareData);
        announce("Share completed.");
      } else {
        await copyTextToClipboard(`${shareData.text}\n${shareData.url}`.trim());
        announce("Share text copied. Paste it into your preferred app.");
      }
      recordEvent("SHARE_INITIATED").catch(() => {});
    } catch (error) {
      if (error?.name !== "AbortError") {
        announce("Sharing is unavailable. Copy the referral link instead.", true);
      }
    } finally {
      button.removeAttribute("aria-busy");
    }
  });

  actions.querySelectorAll("[data-partner-track]").forEach((link) => {
    link.addEventListener("click", () => {
      recordEvent(link.dataset.partnerTrack).catch(() => {});
    });
  });
});

if (nav && toggle) {
  const mobileNavQuery = window.matchMedia("(max-width: 860px)");
  let focusBeforeNavOpen = null;

  const syncNavAvailability = (open) => {
    const shouldHideNav = mobileNavQuery.matches && !open;
    nav.toggleAttribute("inert", shouldHideNav);
    nav.setAttribute("aria-hidden", String(shouldHideNav));
  };

  const syncToggleLabel = (open) => {
    body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    syncNavAvailability(open);
  };

  const closeNav = () => {
    const wasOpen = nav.classList.contains("open");
    nav.classList.remove("open");
    syncToggleLabel(false);
    if (wasOpen && focusBeforeNavOpen && document.contains(focusBeforeNavOpen)) {
      focusBeforeNavOpen.focus({ preventScroll: true });
    }
    focusBeforeNavOpen = null;
  };

  toggle.addEventListener("click", () => {
    const wasOpen = nav.classList.contains("open");
    if (!wasOpen) {
      focusBeforeNavOpen = document.activeElement;
    }
    const open = nav.classList.toggle("open");
    syncToggleLabel(open);
    if (open) {
      window.setTimeout(() => {
        nav.querySelector("a, button")?.focus({ preventScroll: true });
      }, 120);
    } else {
      focusBeforeNavOpen = null;
    }
  });

  nav.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      focusBeforeNavOpen = null;
      closeNav();
    });
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      closeNav();
    }
  });

  document.addEventListener("click", (event) => {
    if (!nav.contains(event.target) && !toggle.contains(event.target)) {
      closeNav();
    }
  });

  window.addEventListener("resize", () => {
    if (window.innerWidth > 860) {
      closeNav();
      syncNavAvailability(true);
      return;
    }
    syncNavAvailability(nav.classList.contains("open"));
  });

  mobileNavQuery.addEventListener?.("change", () => {
    syncNavAvailability(nav.classList.contains("open"));
  });

  syncToggleLabel(nav.classList.contains("open"));
}

const markPreviewReady = (wrap) => {
  if (wrap) {
    wrap.classList.remove("is-ready");
    window.requestAnimationFrame(() => {
      wrap.classList.add("is-ready");
    });
  }
};

if (previewWrap && !previewWrap.hidden) {
  markPreviewReady(previewWrap);
}

if (issuePreviewWrap && !issuePreviewWrap.hidden) {
  markPreviewReady(issuePreviewWrap);
}

const bindImagePreview = (input, preview, wrap, emptyState = null) => {
  if (!input || !preview) {
    return;
  }

  input.addEventListener("change", () => {
    const [file] = input.files || [];
    if (!file) {
      if (wrap) {
        wrap.hidden = true;
      }
      if (emptyState) {
        emptyState.hidden = false;
      }
      return;
    }

    const objectUrl = URL.createObjectURL(file);
    preview.src = objectUrl;
    preview.onload = () => URL.revokeObjectURL(objectUrl);

    if (wrap) {
      wrap.hidden = false;
      markPreviewReady(wrap);
    }
    if (emptyState) {
      emptyState.hidden = true;
    }
  });
};

bindImagePreview(imageInput, imagePreview, previewWrap);
bindImagePreview(issueImageInput, issueImagePreview, issuePreviewWrap, issuePreviewEmpty);

if (prioritySelect && emergencyNote) {
  const syncEmergencyNote = () => {
    const isEmergency = prioritySelect.value === "Emergency";
    emergencyNote.hidden = !isEmergency;
    emergencyNote.classList.toggle("is-visible", isEmergency);
  };

  prioritySelect.addEventListener("change", syncEmergencyNote);
  syncEmergencyNote();
}

document.querySelectorAll("[data-password-toggle]").forEach((button) => {
  const targetId = button.getAttribute("aria-controls");
  const input = targetId ? document.getElementById(targetId) : null;
  if (!input) {
    return;
  }

  const syncPasswordToggle = () => {
    const revealed = input.type === "text";
    button.setAttribute("aria-pressed", String(revealed));
    button.setAttribute("aria-label", revealed ? "Hide password" : "Show password");
    button.textContent = revealed ? "Hide" : "Show";
  };

  button.addEventListener("click", () => {
    input.type = input.type === "password" ? "text" : "password";
    syncPasswordToggle();
    input.focus({ preventScroll: true });
    const valueLength = input.value.length;
    input.setSelectionRange(valueLength, valueLength);
  });

  syncPasswordToggle();
});

const dismissFlash = (flash) => {
  if (!flash || flash.classList.contains("is-dismissing")) {
    return;
  }

  flash.classList.add("is-dismissing");

  window.setTimeout(() => {
    const wrap = flash.closest(".flash-wrap");
    const stack = flash.parentElement;
    flash.remove();

    if (wrap && stack && stack.children.length === 0) {
      wrap.remove();
    }
  }, 220);
};

document.querySelectorAll(".flash").forEach((flash) => {
  flash.querySelector(".flash-close")?.addEventListener("click", () => dismissFlash(flash));

  if (flash.dataset.flashCategory === "success") {
    window.setTimeout(() => dismissFlash(flash), 4800);
  }
});

if (detailMainImage) {
  document.querySelectorAll(".gallery-thumb").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.galleryTarget;
      if (!target) {
        return;
      }

      detailMainImage.src = target;
      document.querySelectorAll(".gallery-thumb").forEach((item) => item.classList.remove("is-active"));
      button.classList.add("is-active");
    });
  });
}

const resetSubmitState = (form) => {
  if (!form) {
    return;
  }

  form.classList.remove("is-submitting");
  form.querySelectorAll("[data-original-label]").forEach((button) => {
    button.textContent = button.dataset.originalLabel;
    delete button.dataset.originalLabel;
    button.disabled = false;
    button.removeAttribute("aria-busy");
  });
};

document.querySelectorAll("form").forEach((form) => {
  form.addEventListener(
    "invalid",
    () => {
      resetSubmitState(form);
    },
    true
  );

  form.addEventListener("submit", (event) => {
    const submitter = event.submitter;
    if (!submitter) {
      return;
    }

    const confirmMessage = submitter.dataset.confirmMessage || form.dataset.confirmMessage;
    if (confirmMessage && !window.confirm(confirmMessage)) {
      event.preventDefault();
      return;
    }

    form.classList.add("is-submitting");

    const loadingLabel = submitter.dataset.loadingLabel;
    if (loadingLabel) {
      submitter.disabled = true;
      submitter.setAttribute("aria-busy", "true");
      submitter.dataset.originalLabel = submitter.textContent;
      submitter.textContent = loadingLabel;
    }

    window.setTimeout(() => {
      if (document.visibilityState === "visible") {
        resetSubmitState(form);
      }
    }, 20000);
  });
});

window.addEventListener("pageshow", () => {
  document.querySelectorAll("form.is-submitting").forEach(resetSubmitState);
});

document.querySelectorAll("[data-auto-submit-select]").forEach((select) => {
  select.addEventListener("change", () => {
    const form = select.form;
    if (!form) {
      return;
    }
    if (typeof form.requestSubmit === "function") {
      form.requestSubmit();
      return;
    }
    form.submit();
  });
});

document.querySelectorAll("[data-selection-scope]").forEach((scope) => {
  const checkboxes = Array.from(scope.querySelectorAll("[data-selection-item]"));
  const countLabel = scope.querySelector("[data-selection-count]");
  if (!checkboxes.length || !countLabel) {
    return;
  }

  const syncSelectionCount = () => {
    const selected = checkboxes.filter((checkbox) => checkbox.checked).length;
    countLabel.textContent = `${selected} selected`;
    scope.classList.toggle("has-selection", selected > 0);
  };

  checkboxes.forEach((checkbox) => {
    checkbox.addEventListener("change", syncSelectionCount);
  });
  syncSelectionCount();
});

document.querySelectorAll("[data-document-generator-form]").forEach((form) => {
  const templateSelect = form.querySelector("[data-template-select-url]");
  const previewButton = form.querySelector("[data-document-preview]");
  const previewFeedback = form.querySelector("[data-document-preview-feedback]");
  let hasUnsavedChanges = false;
  let allowNavigation = false;
  let previousTemplate = templateSelect?.value || "";

  const markDirty = (event) => {
    if (event.target !== templateSelect) {
      hasUnsavedChanges = true;
    }
  };

  const renderPreviewFeedback = (message, isError = false) => {
    if (!previewFeedback) {
      return;
    }
    previewFeedback.hidden = false;
    previewFeedback.classList.toggle("is-error", isError);
    previewFeedback.textContent = message;
    if (isError) {
      previewFeedback.setAttribute("role", "alert");
      previewFeedback.focus({ preventScroll: false });
    } else {
      previewFeedback.setAttribute("role", "status");
    }
  };

  form.addEventListener("input", markDirty);
  form.addEventListener("change", markDirty);
  form.addEventListener("submit", (event) => {
    if (!event.defaultPrevented && event.submitter?.matches("[data-document-final-submit]")) {
      allowNavigation = true;
    }
  });

  templateSelect?.addEventListener("change", () => {
    const targetUrl = templateSelect.getAttribute("data-template-select-url");
    if (!targetUrl) {
      return;
    }
    if (hasUnsavedChanges && !window.confirm("Changing the template clears the entries on this page. Continue?")) {
      templateSelect.value = previousTemplate;
      return;
    }
    allowNavigation = true;
    previousTemplate = templateSelect.value;
    window.location = `${targetUrl}?template_key=${encodeURIComponent(templateSelect.value)}`;
  });

  form.querySelectorAll("[data-document-discard-link]").forEach((link) => {
    link.addEventListener("click", (event) => {
      if (hasUnsavedChanges && !window.confirm("Leave this document and discard your unsaved entries?")) {
        event.preventDefault();
        return;
      }
      allowNavigation = true;
    });
  });

  previewButton?.addEventListener("click", async (event) => {
    if (!form.reportValidity()) {
      return;
    }
    event.preventDefault();
    const previewWindow = window.open("", "_blank");
    if (previewWindow) {
      previewWindow.document.title = "Preparing document preview";
      const status = previewWindow.document.createElement("p");
      status.textContent = "Preparing your PDF preview…";
      status.style.cssText = "font: 600 16px system-ui; padding: 2rem; color: #102a43";
      previewWindow.document.body.append(status);
    }

    previewButton.disabled = true;
    previewButton.setAttribute("aria-busy", "true");
    const originalLabel = previewButton.textContent;
    previewButton.textContent = previewButton.dataset.loadingLabel || "Opening preview...";
    renderPreviewFeedback("Preparing a review copy…");

    try {
      const response = await fetch(previewButton.formAction, {
        method: "POST",
        body: new FormData(form),
        headers: { Accept: "application/pdf, application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) {
        let message = "The preview could not be created. Review the required fields and try again.";
        try {
          const payload = await response.json();
          if (Array.isArray(payload.errors) && payload.errors.length) {
            message = payload.errors.join(" ");
          }
        } catch (_error) {
          // Keep the safe fallback for non-JSON server errors.
        }
        previewWindow?.close();
        renderPreviewFeedback(message, true);
        return;
      }

      const previewUrl = URL.createObjectURL(await response.blob());
      if (previewWindow) {
        previewWindow.location.replace(previewUrl);
      } else {
        const fallbackLink = document.createElement("a");
        fallbackLink.href = previewUrl;
        fallbackLink.target = "_blank";
        fallbackLink.rel = "noopener";
        fallbackLink.click();
      }
      window.setTimeout(() => URL.revokeObjectURL(previewUrl), 60000);
      renderPreviewFeedback("Preview opened in a new tab. Your entries remain here for editing.");
    } catch (_error) {
      previewWindow?.close();
      renderPreviewFeedback("The preview service is unavailable right now. Your entries are still here; please try again.", true);
    } finally {
      previewButton.disabled = false;
      previewButton.removeAttribute("aria-busy");
      previewButton.textContent = originalLabel;
    }
  });

  window.addEventListener("beforeunload", (event) => {
    if (!hasUnsavedChanges || allowNavigation) {
      return;
    }
    event.preventDefault();
    event.returnValue = "";
  });
});

document.querySelectorAll("[data-advanced-payload-toggle]").forEach((toggle) => {
  const targetId = toggle.getAttribute("data-advanced-payload-toggle");
  const helperId = toggle.getAttribute("data-advanced-helper-id");
  const target = targetId ? document.getElementById(targetId) : null;
  const helper = helperId ? document.getElementById(helperId) : null;

  if (!target) {
    return;
  }

  const syncAdvancedPayloadState = () => {
    const editable = toggle.checked;
    target.readOnly = !editable;
    target.setAttribute("aria-readonly", String(!editable));
    if (helper) {
      helper.textContent = editable
        ? "The advanced editor is active. The guided fields above will be ignored for this submission."
        : "Leave this off for normal use. When it stays off, the guided fields above fill the document data automatically.";
    }
  };

  toggle.addEventListener("change", syncAdvancedPayloadState);
  syncAdvancedPayloadState();
});

const mapElement = document.getElementById("map");
const mapDataElement = document.getElementById("map-data");

const escapeHtml = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (character) => {
    const entities = {
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    };
    return entities[character] || character;
  });

const buildMapPopupNode = (properties) => {
  const title = escapeHtml(properties.title);
  const district = escapeHtml(properties.district);
  const address = escapeHtml(properties.address);
  const propertyType = escapeHtml(properties.property_type);
  const status = escapeHtml(properties.status);
  const availability = escapeHtml(properties.availability);
  const priceLabel = escapeHtml(properties.price_label);
  const detailUrl = escapeHtml(properties.detail_url);
  const resultsAnchor = escapeHtml(properties.results_anchor);
  const imageUrl = escapeHtml(properties.image_url);
  const isApproximate = properties.map_location_mode === "approximate";
  const isVerified = Number.parseInt(properties.verified_property || "0", 10) === 1;
  const isLandlordVerified = Number.parseInt(properties.verified_landlord || "0", 10) === 1;
  const wrapper = document.createElement("section");

  wrapper.className = "map-popup-card";
  wrapper.setAttribute("role", "dialog");
  wrapper.setAttribute("aria-label", `Quick view for ${properties.title || "listing"}`);

  wrapper.innerHTML = `
    <div class="map-popup-media">
      <img src="${imageUrl}" alt="${title}" class="map-popup-image" loading="lazy" decoding="async">
      <button type="button" class="map-popup-close" aria-label="Close quick view">&times;</button>
    </div>
    <div class="map-popup-copy">
      <div class="map-popup-head">
        <p class="map-popup-eyebrow">${district}</p>
        <div class="map-popup-pill-row">
          <span class="map-popup-pill">${status}</span>
          <span class="map-popup-pill map-popup-pill-muted">${propertyType}</span>
          ${
            availability !== "Available"
              ? `<span class="map-popup-pill map-popup-pill-muted">${availability}</span>`
              : ""
          }
        </div>
      </div>
      <h3>${title}</h3>
      <p class="map-popup-price">${priceLabel}</p>
      <p class="map-popup-note">${address}</p>
      <div class="map-popup-trust">
        ${isVerified ? '<p class="map-popup-status">Property vetted</p>' : ""}
        ${isLandlordVerified ? '<p class="map-popup-status">Landlord vetted</p>' : ""}
        ${isApproximate ? '<p class="map-popup-note map-popup-note-caution">Approximate district marker</p>' : ""}
      </div>
    </div>
    <div class="map-popup-actions">
      <a href="${detailUrl}" class="map-popup-link map-popup-link-primary">View listing</a>
      <a href="${resultsAnchor}" class="map-popup-link map-popup-link-secondary">Find result</a>
    </div>
  `;

  return wrapper;
};

if (mapElement) {
  const token = mapElement.dataset.token || "";
  const mapboxCssUrl = mapElement.dataset.mapboxCss || "";
  const mapboxScriptUrl = mapElement.dataset.mapboxScript || "";
  const longitude = Number.parseFloat(mapElement.dataset.longitude || "3.3792");
  const latitude = Number.parseFloat(mapElement.dataset.latitude || "6.5244");
  const zoom = Number.parseFloat(mapElement.dataset.zoom || "12");
  const focusListingId = new URLSearchParams(window.location.search).get("focus") || "";
  let featureCollection = { type: "FeatureCollection", features: [] };

  if (mapDataElement?.textContent.trim()) {
    try {
      featureCollection = JSON.parse(mapDataElement.textContent);
    } catch (_error) {
      featureCollection = { type: "FeatureCollection", features: [] };
    }
  }

  const renderMapFallback = (message) => {
    mapElement.classList.add("map-unavailable");
    mapElement.innerHTML = `<div class="map-fallback"><p>${message}</p></div>`;
  };

  const loadStylesheet = (href) =>
    new Promise((resolve, reject) => {
      if (!href || document.querySelector(`link[href="${href}"]`)) {
        resolve();
        return;
      }

      const link = document.createElement("link");
      link.rel = "stylesheet";
      link.href = href;
      link.addEventListener("load", resolve, { once: true });
      link.addEventListener("error", reject, { once: true });
      document.head.appendChild(link);
    });

  const loadScript = (src) =>
    new Promise((resolve, reject) => {
      if (window.mapboxgl) {
        resolve();
        return;
      }
      if (!src) {
        reject(new Error("Missing Mapbox script URL."));
        return;
      }

      const existingScript = document.querySelector(`script[src="${src}"]`);
      if (existingScript) {
        existingScript.addEventListener("load", resolve, { once: true });
        existingScript.addEventListener("error", reject, { once: true });
        return;
      }

      const script = document.createElement("script");
      script.src = src;
      script.async = true;
      script.addEventListener("load", resolve, { once: true });
      script.addEventListener("error", reject, { once: true });
      document.head.appendChild(script);
    });

  const initializeMap = () => {
    if (mapElement.dataset.mapInitialized === "true") {
      return;
    }

    mapElement.dataset.mapInitialized = "true";
    window.mapboxgl.accessToken = token;

    // Mapbox requires an empty container. Keeping the loading state in the
    // element allows the map to render but can prevent layer pointer events.
    mapElement.replaceChildren();

    const map = new window.mapboxgl.Map({
      container: "map",
      style: "mapbox://styles/mapbox/light-v11",
      center: [longitude, latitude],
      zoom,
    });

    map.addControl(new window.mapboxgl.NavigationControl(), "top-right");
    map.getCanvas().setAttribute(
      "aria-label",
      "Interactive property map. Select a marker to open a property quick view."
    );

    let activePopup = null;

    const openFeaturePopup = (feature) => {
      if (!feature) {
        return;
      }

      const coordinates = feature.geometry.coordinates.slice();
      if (activePopup) {
        activePopup.remove();
      }

      const popupNode = buildMapPopupNode(feature.properties);
      const popup = new window.mapboxgl.Popup({
        anchor: window.matchMedia("(max-width: 560px)").matches ? "top" : "bottom",
        closeButton: false,
        offset: 18,
        maxWidth: "320px",
      })
        .setLngLat(coordinates)
        .setDOMContent(popupNode)
        .addTo(map);

      const closePopup = () => popup.remove();
      popupNode.querySelector(".map-popup-close")?.addEventListener("click", closePopup);
      popupNode.querySelector(".map-popup-link-secondary")?.addEventListener("click", () => {
        window.setTimeout(closePopup, 0);
      });
      popup.on("close", () => {
        if (activePopup === popup) {
          activePopup = null;
        }
        map.getCanvas().focus({ preventScroll: true });
      });

      activePopup = popup;
      window.requestAnimationFrame(() => {
        popupNode.querySelector(".map-popup-close")?.focus({ preventScroll: true });
      });
    };

    const fitMapToFeatures = (features) => {
      if (!features.length) {
        map.easeTo({ center: [longitude, latitude], zoom });
        return;
      }

      if (features.length === 1) {
        map.easeTo({
          center: features[0].geometry.coordinates,
          zoom: Math.max(zoom, 14),
          duration: 900,
        });
        return;
      }

      const bounds = new window.mapboxgl.LngLatBounds();
      features.forEach((feature) => bounds.extend(feature.geometry.coordinates));
      map.fitBounds(bounds, {
        padding: { top: 64, right: 48, bottom: 64, left: 48 },
        maxZoom: 14,
        duration: 900,
      });
    };

    map.on("load", () => {
      map.addSource("listings", {
        type: "geojson",
        data: featureCollection,
        cluster: true,
        clusterMaxZoom: 14,
        clusterRadius: 48,
      });

      map.addLayer({
        id: "clusters",
        type: "circle",
        source: "listings",
        filter: ["has", "point_count"],
        paint: {
          "circle-color": "#7b3327",
          "circle-radius": [
            "step",
            ["get", "point_count"],
            18,
            5,
            24,
            12,
            30,
          ],
          "circle-stroke-width": 3,
          "circle-stroke-color": "#f4eee6",
          "circle-opacity": 0.92,
        },
      });

      map.addLayer({
        id: "cluster-count",
        type: "symbol",
        source: "listings",
        filter: ["has", "point_count"],
        layout: {
          "text-field": ["get", "point_count_abbreviated"],
          "text-font": ["Open Sans Bold", "Arial Unicode MS Bold"],
          "text-size": 12,
        },
        paint: {
          "text-color": "#fffdf9",
        },
      });

      map.addLayer({
        id: "unclustered-point",
        type: "circle",
        source: "listings",
        filter: ["!", ["has", "point_count"]],
        paint: {
          "circle-color": [
            "case",
            ["==", ["get", "map_location_mode"], "approximate"],
            "#a16f36",
            "#7b3327",
          ],
          "circle-radius": [
            "interpolate",
            ["linear"],
            ["zoom"],
            10,
            8,
            14,
            10,
            18,
            12,
          ],
          "circle-stroke-width": 2,
          "circle-stroke-color": "#fffdf9",
          "circle-opacity": 0.96,
        },
      });

      fitMapToFeatures(featureCollection.features || []);

      if (focusListingId) {
        const focusedFeature = (featureCollection.features || []).find(
          (feature) => feature?.properties?.id === focusListingId
        );
        if (focusedFeature) {
          map.easeTo({
            center: focusedFeature.geometry.coordinates,
            zoom: Math.max(zoom, 14),
            duration: 900,
          });
          window.setTimeout(() => {
            openFeaturePopup(focusedFeature);
          }, 260);
        }
      }

      const interactiveLayers = ["clusters", "unclustered-point"];
      const interactiveFeaturesAt = (point) => {
        const hitRadius = 22;
        return map.queryRenderedFeatures(
          [
            [point.x - hitRadius, point.y - hitRadius],
            [point.x + hitRadius, point.y + hitRadius],
          ],
          { layers: interactiveLayers }
        );
      };

      map.on("click", (event) => {
        const feature = interactiveFeaturesAt(event.point)[0];
        if (!feature) {
          return;
        }

        if (feature.properties?.cluster_id !== undefined) {
          const clusterId = feature.properties.cluster_id;
          map.getSource("listings").getClusterExpansionZoom(clusterId, (error, expansionZoom) => {
            if (error) {
              return;
            }
            map.easeTo({
              center: feature.geometry.coordinates,
              zoom: expansionZoom,
              duration: 700,
            });
          });
          return;
        }

        openFeaturePopup(feature);
      });

      map.on("mousemove", (event) => {
        map.getCanvas().style.cursor = interactiveFeaturesAt(event.point).length ? "pointer" : "";
      });
      map.on("mouseout", () => {
        map.getCanvas().style.cursor = "";
      });
    });
  };

  const loadMap = () => {
    if (!token || token === "YOUR_MAPBOX_TOKEN_HERE") {
      renderMapFallback("Add a valid Mapbox access token to enable the catalogue map.");
      return;
    }

    loadStylesheet(mapboxCssUrl)
      .then(() => loadScript(mapboxScriptUrl))
      .then(() => {
        if (!window.mapboxgl) {
          throw new Error("Mapbox did not initialize.");
        }
        initializeMap();
      })
      .catch(() => {
        renderMapFallback("Map preview is temporarily unavailable. Use the listing cards above or contact the team for location guidance.");
      });
  };

  if ("IntersectionObserver" in window) {
    const mapObserver = new IntersectionObserver(
      (entries, observer) => {
        if (entries.some((entry) => entry.isIntersecting)) {
          observer.disconnect();
          loadMap();
        }
      },
      { rootMargin: "360px 0px" }
    );
    mapObserver.observe(mapElement);
  } else {
    loadMap();
  }
}
