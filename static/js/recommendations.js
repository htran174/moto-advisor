// static/js/recommendations.js
(function () {
  console.log('[RideReady] recommendations.js loaded');

  // --------- State (session) ---------
  let profile = readJSON('rr.profile') || {
    experience: 'no_experience', height_cm: 170, budget_usd: 6000,
    bike_types: [], riding_style: [], k: 3
  };
  let history = readJSON('rr.history') || [];
  let hasRunOnce = history.length > 0;

  // Curated ids for initial style-first bias (safe if ids missing)
  const STYLE_COMMON = {
    sportbike: ["yamaha_r3", "honda_cbr300", "kawasaki_ninja_400"],
    naked: ["yamaha_mt03", "kawasaki_z400", "ktm_390_duke", "honda_cb300r"],
    cruiser: ["honda_rebel_300", "kawasaki_vulcan_s"],
    standard: ["honda_cb300r", "kawasaki_z400", "yamaha_mt03"],
    adventure: ["kawasaki_versys_x_300", "honda_cb500x_light"],
    touring: ["kawasaki_versys_x_300"],
    dual_sport: ["honda_crf300l"]
  };
  const GLOBAL_COMMON = ["yamaha_r3", "honda_cbr300", "kawasaki_ninja_400", "honda_rebel_300", "yamaha_mt03", "kawasaki_z400"];

  // --------- DOM refs ---------
  const $ = (id) => document.getElementById(id);

  const meta = $('meta');
  const profileSummary = $('profileSummary');

  const btnReRun = $('btnReRun');
  const btnClearHistory = $('btnClearHistory');

  const tabRecs = $('tabRecs');
  const tabChat = $('tabChat');
  const panelRecs = $('panelRecs');
  const panelChat = $('panelChat');

  const visibleList = $('visibleList');
  const timeline = $('timeline');

  const chatBody = $('chatBody');
  const chatForm = $('chatForm');
  const chatInput = $('chatInput');

  const backdrop = $('modalBackdrop');
  const absModal = $('absModal'); const absOk = $('absOk');
  const msrpModal = $('msrpModal'); const msrpCancel = $('msrpCancel'); const msrpProceed = $('msrpProceed');
  let pendingOfficialHref = null;

  // --------- Helpers ---------
  function readJSON(k) { try { return JSON.parse(sessionStorage.getItem(k) || ''); } catch { return null; } }
  function writeJSON(k, v) { sessionStorage.setItem(k, JSON.stringify(v)); }
  function ts() { return new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }); }
  function nowISO() { return new Date().toISOString(); }
  function esc(s) { return (s || '').replace(/[&<>"']/g, m => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' }[m])); }
  function clamp(n, min, max) { return Math.max(min, Math.min(max, n || min)); }
  function summarize(p) {
    const t = (p.bike_types && p.bike_types.length) ? p.bike_types.join(', ') : 'any';
    return `H:${p.height_cm}cm • Budget:$${p.budget_usd} • ${p.experience === 'no_experience' ? 'No exp' : 'Little exp'} • Types:${t} • k=${p.k}`;
  }
  function setSkeletons(n) {
    if (!visibleList) return;
    visibleList.innerHTML = '';
    for (let i = 0; i < n; i++) {
      const sk = document.createElement('div');
      sk.className = 'skeleton';
      visibleList.appendChild(sk);
    }
  }
  function perfLine(item) {
    const top = (item.max_speed_mph != null) ? item.max_speed_mph : '-';
    const zero = (item.zero_to_sixty_s != null) ? item.zero_to_sixty_s : '-';
    return `Top speed — ${top} mph • 0–60 — ${zero} s`;
  }

  // --- Live operation status (in the header area) ---
function ensureStatusNode() {
  // Try to place it next to the hint line; fall back to meta
  let host = document.querySelector('#chatHint') || document.querySelector('#meta');
  if (!host) host = document.querySelector('.container') || document.body;

  let el = document.getElementById('opStatus');
  if (!el) {
    el = document.createElement('div');
    el.id = 'opStatus';
    el.style.cssText = `
      font-size:.92rem; color:var(--muted); margin:.35rem 0;
      display:flex; align-items:center; gap:.4rem;
    `;
    host.insertAdjacentElement('afterend', el);
  }
  return el;
}

function setOpStatus(text, kind='idle') {
  const el = ensureStatusNode();
  // Simple badges by state
  const badge =
    kind === 'working' ? `<span style="display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:var(--link);"></span>`
    : kind === 'ok'     ? `<span style="display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:#22c55e;"></span>`
    : kind === 'error'  ? `<span style="display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:#ef4444;"></span>`
    : `<span style="display:inline-block;width:.6rem;height:.6rem;border-radius:50%;background:#9ca3af;"></span>`;
  el.innerHTML = `${badge} <span>${esc(text)}</span>`;
}

  function card(item) {
    const div = document.createElement('div');
    div.className = 'card';
    div.style.overflow = 'hidden';
    div.style.border = '1px solid var(--border)';
    const officialLinkId = `off_${(item.id || item.name).replace(/[^a-z0-9_]/gi, '')}_${Math.random().toString(36).slice(2)}`;
    div.innerHTML = `
      <div style="height:160px; background:#f5f5f5;">
        <img src="${esc(item.image_url || '/static/motorcycle_ride.jpg')}" alt="${esc(item.name)}"
             style="width:100%; height:160px; object-fit:cover; display:block;">
      </div>
      <div class="section-pad" style="display:grid; gap:.35rem;">
        <div style="display:flex; align-items:center; justify-content:space-between; gap:.5rem;">
          <strong>${esc(item.name)}</strong>
          <div style="display:flex; gap:.5rem; flex-wrap:wrap;">
            ${item.abs === false ? '<span class="chip warn" title="This trim may not include ABS">No ABS</span>' : ''}
          </div>
        </div>
        <div class="subtitle">${esc(item.manufacturer)} • ${esc(item.category)}</div>
        <div style="font-size:.95rem;">${esc(perfLine(item))}</div>
        <ul style="margin:.25rem 0 0 1rem; padding:0; font-size:.95rem;">
          ${(item.reasons || []).slice(0, 3).map(r => `<li>${esc(r)}</li>`).join('')}
        </ul>
        <div>
          <a id="${officialLinkId}" href="${item.official_url}" target="_blank" rel="noopener"
             class="btn btn-outline" style="display:inline-block; text-decoration:none; margin-top:.25rem;">Official Site</a>
        </div>
      </div>
    `;
    setTimeout(() => {
      const a = div.querySelector('#' + officialLinkId);
      if (a) a.addEventListener('click', (e) => {
        if (sessionStorage.getItem('rr.msrpWarned') === '1') return;
        e.preventDefault();
        pendingOfficialHref = a.href;
        openMsrp();
      });
    }, 0);
    return div;
  }

  function renderVisibleFromHistory() {
    if (!visibleList) return;
    const seen = new Set();
    const visible = [];
    const flat = [];
    const sorted = [...history].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    sorted.forEach(snap => snap.items.forEach(it => flat.push({ snap, it })));
    flat.forEach(({ it }) => {
      const key = it.id || it.bike_id || it.name;
      if (!seen.has(key)) { seen.add(key); visible.push(it); }
    });

    visibleList.innerHTML = '';
    if (visible.length === 0) {
      const p = document.createElement('p');
      p.className = 'subtitle';
      p.textContent = 'No saved recommendations yet. Click Re-run or use the Chat tab.';
      visibleList.appendChild(p);
      return;
    }
    visible.forEach(it => visibleList.appendChild(card(it)));
  }

  function renderTimeline() {
    if (!timeline) return;
    timeline.innerHTML = '';
    const sorted = [...history].sort((a, b) => (a.created_at < b.created_at ? 1 : -1));
    sorted.forEach(snap => {
      const wrap = document.createElement('div');
      wrap.className = 'card';
      wrap.style.border = '1px solid var(--border)';
      const date = new Date(snap.created_at).toLocaleString();
      const header = document.createElement('div');
      header.className = 'section-pad';
      header.style.borderBottom = '1px solid var(--border)';
      header.style.background = 'linear-gradient(180deg,#F3F4F6,#FFFFFF)';
      header.innerHTML = `<strong>Snapshot • ${esc(date)}</strong><div class="subtitle">${esc(summarize(snap.profile_used))}</div>`;
      const grid = document.createElement('div');
      grid.className = 'section-pad';
      grid.style.display = 'grid'; grid.style.gap = '1rem';
      snap.items.forEach(it => grid.appendChild(card(it)));
      wrap.appendChild(header);
      wrap.appendChild(grid);
      timeline.appendChild(wrap);
    });
  }

  function updateMeta() {
    if (profileSummary) profileSummary.textContent = summarize(profile);
    if (meta) meta.textContent = `History: ${history.length} snapshot(s) • Latest-first view (de-duplicated)`;
  }

  // --------- API calls ---------
  async function callRecommend() {
    setSkeletons(profile.k || 3);
    const res = await fetch('/api/recommend', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(profile)
    });
    if (!res.ok) {
      if (visibleList) visibleList.innerHTML = '<p class="subtitle">Error fetching recommendations.</p>';
      return [];
    }
    const data = await res.json();
    return data.items || [];
  }

  async function chooseImage(item) {
    try {
      const r = await fetch('/api/images', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          id: item.id,
          query: `${item.manufacturer} ${item.name}`,
          limit: 1,
          mfr_domain: item.mfr_domain,
          local_image: item.local_image
        })
      });
      const j = await r.json();
      return (j.images && j.images[0] && j.images[0].url) || '/static/motorcyle_ride.jpg';
    } catch {
      return '/static/motorcyle_ride.jpg';
    }
  }

  async function createSnapshotFrom(items) {
    const enriched = [];
    for (const it of items) {
      const image_url = await chooseImage(it);
      enriched.push({
        id: it.id || it.name,
        name: it.name,
        manufacturer: it.manufacturer,
        category: it.category,
        engine_cc: it.engine_cc,
        seat_height_mm: it.seat_height_mm,
        wet_weight_kg: it.wet_weight_kg,
        abs: it.abs,
        max_speed_mph: it.max_speed_mph,
        zero_to_sixty_s: it.zero_to_sixty_s,
        reasons: it.reasons || [],
        official_url: it.official_url,
        mfr_domain: it.mfr_domain,
        image_url
      });
    }
    return {
      id: 'rr-run-' + Date.now(),
      created_at: nowISO(),
      profile_used: { ...profile },
      items: enriched
    };
  }

  function preferStyleCommon(items) {
    if (hasRunOnce) return items;
    const types = (profile.bike_types || []);
    const desired = [];
    if (types.length === 0) desired.push(...GLOBAL_COMMON);
    else types.forEach(t => (STYLE_COMMON[t] || []).forEach(id => desired.push(id)));

    if (!desired.length) return items;
    const byId = new Map(items.map(it => [it.id || it.name, it]));
    const preferred = desired.map(id => byId.get(id)).filter(Boolean);
    const remaining = items.filter(it => !desired.includes(it.id || it.name));
    const k = clamp(profile.k || 3, 1, 6);
    const result = preferred.slice(0, k);
    if (result.length < k) result.push(...remaining.slice(0, k - result.length));
    return result;
  }

  async function runAndSave() {
    const raw = await callRecommend();
    const initial = preferStyleCommon(raw);
    const snap = await createSnapshotFrom(initial);
    history.unshift(snap);
    history = history.slice(0, 10);
    writeJSON('rr.history', history);
    renderVisibleFromHistory();
    renderTimeline();
    updateMeta();

    if (!sessionStorage.getItem('rr.absWarned')) {
      const hasNoAbs = (snap.items || []).some(it => it.abs === false);
      if (hasNoAbs) openAbs();
    }
    hasRunOnce = true;

    return snap.items;
  }

  // --------- Chat (plan-based) ---------
  function addBubble(text, who) {
    if (!chatBody) return;
    const div = document.createElement('div');
    div.className = 'bubble ' + (who === 'user' ? 'user' : 'bot');
    div.innerHTML = `<p>${esc(text)}</p><time>${ts()}</time>`;
    chatBody.appendChild(div);
    chatBody.scrollTop = chatBody.scrollHeight;
  }

  chatForm && chatForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const text = (chatInput && chatInput.value || '').trim();
    if (!text) return;
    addBubble(text, 'user');
    if (chatInput) chatInput.value = '';

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, profile })
      });
      const plan = await res.json();
      if (plan.message) addBubble(plan.message, 'bot');

      // Apply actions
      if (Array.isArray(plan.actions)) {
        let recNeeded = false;
        for (const act of plan.actions) {
          if (act.type === 'UPDATE_PROFILE' && act.patch) {
            profile = { ...profile, ...act.patch };
            writeJSON('rr.profile', profile);
            updateMeta();
          } else if (act.type === 'RECOMMEND') {
            recNeeded = true;
          }
        }

        setOpStatus('Re-running recommendations…', 'working');
        let items = [];
        try {
          items = await runAndSave();            // this refreshes the Rec tab + history
          setOpStatus('Done. New snapshot added at the top.', 'ok');
        } catch (e) {
          console.error('[RR] runAndSave threw', e);
          setOpStatus('Failed to refresh recommendations.', 'error');
        }
        if (recNeeded) {
          const items = await runAndSave();          // <- MUST return items
          
          // NEW: echo top 2 items as compact chat cards
          if (items && items.length) {
            await addCardBubbles(items.slice(0, 2));
          } else {
            addBubble('No matches for those settings—try loosening budget or seat height.', 'bot');
          }
        }
      }
    } catch {
      addBubble('Network error. Please try again.', 'bot');
    }
  });

  // --------- Tabs
  function switchTab(which) {
    if (!panelRecs || !panelChat || !tabRecs || !tabChat) return;
    const recs = which === 'recs';
    panelRecs.hidden = !recs;
    panelChat.hidden = recs;
    tabRecs.classList.toggle('active', recs);
    tabChat.classList.toggle('active', !recs);
    tabRecs.style.background = recs ? 'var(--primary)' : 'transparent';
    tabRecs.style.color = recs ? '#fff' : 'var(--text)';
    tabChat.style.background = !recs ? 'var(--primary)' : 'transparent';
    tabChat.style.color = !recs ? '#fff' : 'var(--text)';
  }
  tabRecs && tabRecs.addEventListener('click', () => switchTab('recs'));
  tabChat && tabChat.addEventListener('click', () => switchTab('chat'));

  // --------- One-time popups
  function openBackdrop() { backdrop && (backdrop.style.display = 'block'); }
  function closeBackdrop() { backdrop && (backdrop.style.display = 'none'); }
  function openAbs() { openBackdrop(); absModal && (absModal.style.display = 'block'); }
  function closeAbs() { absModal && (absModal.style.display = 'none'); closeBackdrop(); sessionStorage.setItem('rr.absWarned', '1'); }
  absOk && absOk.addEventListener('click', closeAbs);
  function openMsrp() { openBackdrop(); msrpModal && (msrpModal.style.display = 'block'); }
  function closeMsrp() { msrpModal && (msrpModal.style.display = 'none'); closeBackdrop(); }
  msrpCancel && msrpCancel.addEventListener('click', () => { pendingOfficialHref = null; closeMsrp(); });
  msrpProceed && msrpProceed.addEventListener('click', () => {
    sessionStorage.setItem('rr.msrpWarned', '1');
    const href = pendingOfficialHref; pendingOfficialHref = null;
    closeMsrp();
    if (href) window.open(href, '_blank', 'noopener');
  });

  // --------- Buttons
  btnReRun && btnReRun.addEventListener('click', async () => { await runAndSave(); });
  btnClearHistory && btnClearHistory.addEventListener('click', () => {
    history = [];
    writeJSON('rr.history', history);
    renderVisibleFromHistory();
    renderTimeline();
    updateMeta();
  });

  // Render 1–2 compact recommendation cards inside the chat stream
  async function addCardBubbles(items) {
    if (!items || !items.length || !chatBody) return;

    // Cap to 2 cards as per product spec
    const toShow = items.slice(0, 2);

    for (const it of toShow) {
      // pick an image using your existing helper
      const img = await chooseImage(it);

      // minimal summary line
      const subline = [
        it.manufacturer || '',
        it.category ? `• ${it.category}` : ''
      ].filter(Boolean).join(' ');

      // Optional bullets (keep it light; avoid long text walls)
      const bullets = [];
      if (it.top_speed_mph) bullets.push(`Top speed — ${it.top_speed_mph} mph`);
      if (it.zero_to_sixty_s) bullets.push(`0–60 — ${it.zero_to_sixty_s} s`);

      const bulletsHTML = bullets.length
        ? `<ul style="margin:.4rem 0 0 1rem;padding:0;line-height:1.35;">
            ${bullets.map(b => `<li>${esc(b)}</li>`).join('')}
          </ul>`
        : '';

      // Build the compact “card bubble”
      const div = document.createElement('div');
      div.className = 'bubble bot';
      div.style.padding = '0';  // tighter look for a card
      div.innerHTML = `
        <div class="card" style="display:flex; gap:.75rem; align-items:center; padding:.65rem .7rem;">
          <img src="${esc(img)}" alt="" style="width:88px;height:62px;object-fit:cover;border-radius:8px;border:1px solid var(--border);" />
          <div style="flex:1; min-width:0;">
            <div style="font-weight:700; white-space:nowrap; overflow:hidden; text-overflow:ellipsis;">${esc(it.name || it.label || 'Motorcycle')}</div>
            <div style="color:var(--muted); font-size:.92rem;">${esc(subline)}</div>
            ${bulletsHTML}
            ${it.official_url ? `
              <div style="margin-top:.4rem;">
                <a href="${esc(it.official_url)}" target="_blank" rel="noopener" class="btn btn-outline" style="padding:.35rem .65rem; font-size:.9rem;">Official Site</a>
              </div>` : ``}
          </div>
        </div>
      `;

      chatBody.appendChild(div);
      chatBody.scrollTop = chatBody.scrollHeight;
    }
  }
  // --------- Init
  (async function init() {
    writeJSON('rr.profile', profile);
    updateMeta();
    if (history.length === 0) {
      await runAndSave();
    } else {
      renderVisibleFromHistory();
      renderTimeline();
    }
    // Default to Recommendations tab; Chat will open when user clicks.
    switchTab('recs');
  })();
})();

