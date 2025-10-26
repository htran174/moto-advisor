// static/js/recommendations.js
(function () {
  console.log('[RideReady] recommendations.js loaded');

  // Transient chat-driven overrides (used for one run, then cleared)
  let overridePins = null;        // array of catalog ids
  let overrideExternals = null;   // array of external items (no id)

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
  async function callRecommend(pins, externals) {
  setSkeletons(profile.k || 2);

  const payload = { ...profile };
  if (Array.isArray(pins) && pins.length) payload.pin_ids = pins;
  if (Array.isArray(externals) && externals.length) payload.external_items = externals;

  const res = await fetch('/api/recommend', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  if (!res.ok) {
    setOpStatus('Failed to refresh recommendations.', 'error');
    if (visibleList) visibleList.innerHTML = '<p class="subtitle">Network error.</p>';
    throw new Error('recommend API failed');
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
      return (j.images && j.images[0] && j.images[0].url) || '/static/motorcycle_ride.jpg';
    } catch {
      return '/static/motorcycle_ride.jpg';
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
  // Use overrides (from latest chat turn) exactly once
  const pins = overridePins;
  const externals = overrideExternals;
  overridePins = null;
  overrideExternals = null;

  // show progress in the header
  setOpStatus('Re-running recommendations…', 'working');

  const items = await callRecommend(pins, externals);

  // ⬇⬇ important: await the snapshot creation
  const snap = await createSnapshotFrom(items);
  hasRunOnce = true;

  history.unshift(snap);
  writeJSON('rr.history', history);

  // refresh UI
  renderVisibleFromHistory();
  renderTimeline();
  updateMeta();

  setOpStatus('Done. New snapshot added at the top.', 'ok');
  return snap.items;          // chat uses this to show the same two cards
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

    // show user's message
    addBubble(text, 'user');
    if (chatInput) chatInput.value = '';

    try {
      // call backend NLU
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, profile })
      });

      if (!res.ok) {
        addBubble('Network error. Please try again.', 'bot');
        setOpStatus('Failed to refresh recommendations.', 'error');
        return;
      }

      const plan = await res.json();

      // optional bot text
      if (plan.message) addBubble(plan.message, 'bot');

      // reset one-shot overrides
      overridePins = null;
      overrideExternals = null;

      const actions = Array.isArray(plan.actions) ? plan.actions : [];

      // Helper: normalize a single-bike RECOMMEND action into an external item
      const toExternal = (act) => {
        // Pull from either flat fields or nested "details"
        const d = act.details || {};
        const brand = act.brand || act.manufacturer || d.brand || d.manufacturer || '';
        const model = act.model || act.name || d.model || d.name || 'Motorcycle';
        const category = act.category || d.category || act.type_hint || 'sportbike';

        // best-effort ints
        const toInt = (v) => {
          if (v == null) return undefined;
          const n = Number(String(v).replace(/[^\d.]/g, ''));
          return Number.isFinite(n) ? n : undefined;
        };

        const engine_cc = toInt(act.engine_cc ?? d.engine_cc);
        const top_speed_mph = toInt(act.top_speed_mph ?? d.top_speed_mph);
        const zero_to_sixty_s = Number(d.zero_to_sixty_s ?? act.zero_to_sixty_s);

        // description → reasons[0] (our backend is happy with either)
        const desc = act.description || act.notes || d.description || d.notes || '';
        const official_url = act.official_url || d.official_url || '';
        const image_query = act.image_query || d.image_query || [brand, model].filter(Boolean).join(' ');

        return {
          // no id → treated as external
          name: model,
          manufacturer: brand,
          category,
          engine_cc,
          top_speed_mph,
          zero_to_sixty_s,
          reasons: desc ? [desc] : [],
          description: desc,   // also keep it for chat card text
          official_url,
          image_query
        };
      };

      // Apply actions from the plan
      const externals = [];
      for (const act of actions) {
        if (act.type === 'UPDATE_PROFILE' && act.patch) {
          profile = { ...profile, ...act.patch };
          writeJSON('rr.profile', profile);
          updateMeta();
        } else if (act.type === 'RECOMMEND') {
          // Case A: the model returned a list of items at once
          if (Array.isArray(act.items) && act.items.length) {
            // keep only true externals (no local id)
            const extList = act.items
              .filter(x => !(x && x.id))
              .map(x => toExternal(x)); // also normalize shape
            externals.push(...extList);
          }
          // Case B: the model returned a single bike per action
          else if (act.model || (act.details && (act.details.model || act.details.name))) {
            externals.push(toExternal(act));
          }
          // Optional: pinned local ids (if the model ever sends them)
          if (Array.isArray(act.pin_ids) && act.pin_ids.length) {
            overridePins = (overridePins || []).concat(act.pin_ids);
          }
        }
      }

      // Commit the externals as a one-shot override for the next run
      if (externals.length) {
        overrideExternals = externals;
      }

      // Decide if we should refresh recs (only once)
      const shouldRefresh = actions.some(a =>
        a.type === 'RECOMMEND' || a.type === 'UPDATE_PROFILE'
      );

      if (shouldRefresh) {
        let itemsFromRun = [];
        try {
          itemsFromRun = await runAndSave();                 // updates Rec tab + timeline + status line
        } catch (err) {
          console.error('[RR] runAndSave failed', err);
          setOpStatus('Failed to refresh recommendations.', 'error');
          return;
        }

        // echo the top-2 from the snapshot into chat as compact cards
        try {
          await addCardBubbles((itemsFromRun || []).slice(0, 2));
        } catch { /* no-op */ }
      }

    } catch (err) {
      console.error('[RR] chat error', err);
      addBubble('Network error. Please try again.', 'bot');
      setOpStatus('Failed to refresh recommendations.', 'error');
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

    const toShow = items.slice(0, 2);

    for (const it of toShow) {
      const img = await chooseImage(it);
      const subline = [
        it.manufacturer || '',
        it.category ? `• ${it.category}` : ''
      ].filter(Boolean).join(' ');

      // Pull the descriptive text if we have it
      const desc = it.description || it.notes || it.reasons?.[0] || '';

      // Simple performance line
      const perf = [];
      if (it.top_speed_mph) perf.push(`Top speed — ${it.top_speed_mph} mph`);
      if (it.zero_to_sixty_s) perf.push(`0–60 — ${it.zero_to_sixty_s} s`);
      const perfHTML = perf.length
        ? `<div style="font-size:.9rem;color:var(--muted);margin-top:.25rem;">${esc(perf.join(' • '))}</div>`
        : '';

      const div = document.createElement('div');
      div.className = 'bubble bot';
      div.style.padding = '0';
      div.innerHTML = `
        <div class="card" style="display:flex;gap:.75rem;align-items:center;padding:.65rem .7rem;">
          <img src="${esc(img)}" alt="" style="width:88px;height:62px;object-fit:cover;border-radius:8px;border:1px solid var(--border);" />
          <div style="flex:1;min-width:0;">
            <div style="font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${esc(it.name || it.label || 'Motorcycle')}</div>
            <div style="color:var(--muted);font-size:.92rem;">${esc(subline)}</div>
            ${desc ? `<div style="margin-top:.35rem;font-size:.9rem;line-height:1.35;">${esc(desc)}</div>` : ''}
            ${perfHTML}
            ${it.official_url ? `
              <div style="margin-top:.4rem;">
                <a href="${esc(it.official_url)}" target="_blank" rel="noopener"
                  class="btn btn-outline" style="padding:.35rem .65rem;font-size:.9rem;">Official Site</a>
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

