const partnerApplication = document.getElementById("partner-application");
const partnerNameField = document.getElementById("full-name");
const partnerCompanyField = document.getElementById("company");
const partnerTypeField = document.getElementById("partner-type");
const partnerCompanyRequirement = document.getElementById("partner-company-requirement");
const partnerErrors = document.getElementById("partner-errors");
const partnerPasswordVisibility = document.getElementById("partner-show-password");

const syncPartnerCompanyRequirement = () => {
  const companyRequired = partnerTypeField.value === "COMPANY";
  partnerCompanyField.required = companyRequired;
  partnerCompanyField.minLength = companyRequired ? 2 : 0;
  partnerCompanyRequirement.textContent = companyRequired ? "(required)" : "(optional for individuals)";
};
partnerTypeField.addEventListener("change", syncPartnerCompanyRequirement);
syncPartnerCompanyRequirement();

partnerPasswordVisibility.addEventListener("change", () => {
  const fieldType = partnerPasswordVisibility.checked ? "text" : "password";
  document.getElementById("partner-password").type = fieldType;
  document.getElementById("partner-password-confirm").type = fieldType;
});

partnerApplication.addEventListener("focus", () => {
  // Run after the section anchor scroll, so the focused field stays in view.
  window.requestAnimationFrame(() => {
    partnerNameField.focus({ preventScroll: true });
    partnerNameField.scrollIntoView({ block: "center", behavior: "instant" });
  });
});
window.addEventListener("load", () => {
  window.requestAnimationFrame(() => {
    if (partnerErrors) partnerErrors.focus();
    else if (window.location.hash === "#partner-application") partnerNameField.focus();
  });
}, { once: true });
