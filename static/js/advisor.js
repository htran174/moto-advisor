// static/js/advisor.js
(function () {
  const experience = document.getElementById('experience');
  const height_cm = document.getElementById('height_cm');
  const budget_usd = document.getElementById('budget_usd');
  const kEl = document.getElementById('k');
  const btnGet = document.getElementById('btnGet');

  const typesToggle = document.getElementById('typesToggle');
  const typesMenu = document.getElementById('typesMenu');
  const typesClose = document.getElementById('typesClose');
  const typesClear = document.getElementById('typesClear');
  const typesSummary = document.getElementById('typesSummary');

  function clamp(n, min, max) { return Math.max(min, Math.min(max, n || min)); }

  function getSelectedTypes() {
    const boxes = typesMenu.querySelectorAll('input[type="checkbox"]');
    return Array.from(boxes).filter(b => b.checked).map(b => b.value);
  }
  function setSelectedTypes(arr) {
    const set = new Set(arr || []);
    const boxes = typesMenu.querySelectorAll('input[type="checkbox"]');
    boxes.forEach(b => b.checked = set.has(b.value));
  }
  function updateTypesSummary() {
    const t = getSelectedTypes();
    typesSummary.textContent = t.length ? `Selected: ${t.join(', ')}` : 'None selected (we’ll consider all).';
  }

  typesToggle?.addEventListener('click', () => {
    const open = typesMenu.style.display === 'block';
    typesMenu.style.display = open ? 'none' : 'block';
    typesToggle.setAttribute('aria-expanded', (!open).toString());
  });
  typesClose?.addEventListener('click', () => {
    typesMenu.style.display = 'none';
    typesToggle.setAttribute('aria-expanded', 'false');
    updateTypesSummary();
  });
  typesClear?.addEventListener('click', () => {
    setSelectedTypes([]);
    updateTypesSummary();
  });
  document.addEventListener('click', (e) => {
    if (!typesMenu.contains(e.target) && !typesToggle.contains(e.target)) {
      typesMenu.style.display = 'none';
      typesToggle.setAttribute('aria-expanded', 'false');
    }
  });

  btnGet?.addEventListener('click', () => {
    const profile = {
      experience: experience.value,
      height_cm: clamp(parseInt(height_cm.value || '170', 10), 140, 210),
      budget_usd: clamp(parseInt(budget_usd.value || '6000', 10), 1000, 20000),
      bike_types: getSelectedTypes(),
      riding_style: [],
      k: clamp(parseInt(kEl.value || '3', 10), 1, 6)
    };
    sessionStorage.setItem('rr.profile', JSON.stringify(profile));
    if (!sessionStorage.getItem('rr.history')) {
      sessionStorage.setItem('rr.history', JSON.stringify([]));
    }
    sessionStorage.removeItem('rr.absWarned');
    sessionStorage.removeItem('rr.msrpWarned');
    window.location.href = "/recommendations";
  });

  (function init() {
    try {
      const prev = JSON.parse(sessionStorage.getItem('rr.profile') || '');
      if (prev) {
        experience.value = prev.experience || 'no_experience';
        height_cm.value = prev.height_cm || 170;
        budget_usd.value = prev.budget_usd || 6000;
        kEl.value = prev.k || 3;
        setSelectedTypes(prev.bike_types || []);
        updateTypesSummary();
        return;
      }
    } catch { /* noop */ }
    updateTypesSummary();
  })();
})();
