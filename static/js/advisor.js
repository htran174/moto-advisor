// static/js/advisor.js
(() => {
  // ---- Reset session when the server restarts ----
  const bootKey = "rr_boot_id";
  const currentBoot = window.RR_BOOT_ID;
  const lastBoot = sessionStorage.getItem(bootKey);
  if (lastBoot !== currentBoot) {
    sessionStorage.clear();
    sessionStorage.setItem(bootKey, currentBoot);
    console.log("[RideReady] Session reset after app restart");
  }

  const form = document.getElementById("advisorForm") || document.querySelector("[data-advisor-form]");
  if (!form) return;

  // Helpers
  const toNum = (v) => (v === "" || v === undefined || v === null ? undefined : Number(v));

  function readTypes() {
    const boxes = form.querySelectorAll('input[name="bike_types"]:checked');
    return Array.from(boxes).map(b => b.value);
  }

  function readProfileFromForm() {
    const experience = form.querySelector('#experience')?.value || "no_experience";
    const height_cm = toNum(form.querySelector('#height_cm')?.value);
    const budget_usd = toNum(form.querySelector('#budget_usd')?.value);
    const k = toNum(form.querySelector('#k')?.value) ?? 3;
    const bike_types = readTypes();

    const profile = { experience, k };
    if (height_cm !== undefined) profile.height_cm = height_cm;
    if (budget_usd !== undefined) profile.budget_usd = budget_usd;
    if (bike_types.length) profile.bike_types = bike_types;
    return profile;
  }

  function persistProfile(profile) {
    sessionStorage.setItem("rr.profile", JSON.stringify(profile));
  }

  // Make the chip labels toggle their inner checkbox
  form.addEventListener("click", (e) => {
    const chip = e.target.closest(".chip");
    if (chip) {
      const cb = chip.querySelector('input[name="bike_types"]');
      if (cb && e.target !== cb) cb.checked = !cb.checked;
    }
  });

  // Submit -> save profile -> go to results
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    const profile = readProfileFromForm();
    persistProfile(profile);
    window.location.href = "/recommendations";
  });
})();
