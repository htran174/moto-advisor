// Robust, no-crash version. Works even if some elements are missing.

document.addEventListener("DOMContentLoaded", init);

function $(sel) { return document.querySelector(sel); }
function byId(id) { return document.getElementById(id); }

const FALLBACK_IMAGE = "/static/stock_images/motorcycle_ride.jpg"; // correct path/spelling

function init() {
  // Elements (some might be null — all code guards against that)
  const tabRecs = byId("tabRecs");
  const tabChat = byId("tabChat");
  const panelRecs = byId("panelRecs");
  const panelChat = byId("panelChat");
  const btnReRun = byId("btnReRun");
  const btnClearHistory = byId("btnClearHistory");
  const cards = byId("cards");
  const loading = byId("loadingMsg");
  const meta = byId("meta");
  const timeline = byId("timeline");
  const timelineWrap = byId("timelineWrap");
  const chatInput = byId("chatInput");
  const chatSend = byId("chatSend");
  const chatLog = byId("chatLog");

  // Tab wiring
  if (tabRecs && tabChat && panelRecs && panelChat) {
    tabRecs.addEventListener("click", () => switchTab("recs"));
    tabChat.addEventListener("click", () => switchTab("chat"));
  }

  function switchTab(which) {
    const isChat = which === "chat";
    if (tabRecs) { tabRecs.classList.toggle("btn-primary", !isChat); tabRecs.classList.toggle("btn-outline", isChat); tabRecs.setAttribute("aria-selected", String(!isChat)); }
    if (tabChat) { tabChat.classList.toggle("btn-primary", isChat); tabChat.classList.toggle("btn-outline", !isChat); tabChat.setAttribute("aria-selected", String(isChat)); }
    if (panelRecs) panelRecs.hidden = isChat;
    if (panelChat) panelChat.hidden = !isChat;
  }

  // Buttons
  if (btnReRun) btnReRun.addEventListener("click", runRecommend);
  if (btnClearHistory) btnClearHistory.addEventListener("click", clearHistory);
  if (chatSend && chatInput) chatSend.addEventListener("click", () => sendChat(chatInput.value));

  // Initial run
  runRecommend();

  // ---- functions ----

  function getProfile() {
    try {
      const raw = sessionStorage.getItem("rr_profile");
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function setLoading(on) {
    if (loading) loading.textContent = on ? "Loading…" : "";
  }

  function updateMeta({ count, k }) {
    const el = meta;
    if (!el) return; // Guard: if #meta doesn’t exist, don’t crash.
    el.textContent = `Showing ${count} item${count === 1 ? "" : "s"} (k=${k ?? "?"}).`;
  }

  function pushTimeline(label, obj) {
    if (!timeline) return;
    const stamp = new Date().toLocaleString();
    timeline.textContent += `[${stamp}] ${label}\n` + JSON.stringify(obj, null, 2) + "\n\n";
  }

  async function runRecommend() {
    const profile = getProfile();
    setLoading(true);
    pushTimeline("REQUEST /api/recommend", profile);

    try {
      const res = await fetch("/api/recommend", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(profile),
      });
      const data = await res.json();
      pushTimeline("RESPONSE /api/recommend", data);

      const items = (data && data.items) || [];
      if (cards) cards.innerHTML = items.map(cardHTML).join("") || `<div class="subtitle">No results. Try adjusting your inputs.</div>`;
      updateMeta({ count: items.length, k: profile.k });

      // Resolve images async (don’t block initial render)
      for (const it of items) {
        resolveImage(it).then((url) => {
          const img = byId(`img_${safeId(it.id || it.name)}`);
          if (img) img.src = url || FALLBACK_IMAGE;
        }).catch(() => {
          const img = byId(`img_${safeId(it.id || it.name)}`);
          if (img) img.src = FALLBACK_IMAGE;
        });
      }
    } catch (err) {
      if (cards) cards.innerHTML = `<div class="subtitle">Error loading recommendations.</div>`;
      pushTimeline("ERROR /api/recommend", { message: String(err) });
    } finally {
      setLoading(false);
    }
  }

  function clearHistory() {
    if (timeline) timeline.textContent = "";
    if (timelineWrap) timelineWrap.open = false;
  }

  async function resolveImage(item) {
    const local = item.local_image || item.image || null;
    try {
      const res = await fetch("/api/images", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ local_image: local, id: item.id }),
      });
      const data = await res.json();
      const first = (data && data.images && data.images[0] && data.images[0].url) || null;
      return first || FALLBACK_IMAGE;
    } catch {
      return FALLBACK_IMAGE;
    }
  }

  function safeId(s) {
    return String(s || "item").replace(/[^a-z0-9_-]/gi, "_");
  }

  function cardHTML(b) {
    const id = safeId(b.id || b.name);
    const reasons = Array.isArray(b.reasons) ? b.reasons.slice(0, 3) : [];
    const specs = [];
    if (b.engine_cc) specs.push(`${b.engine_cc} cc`);
    if (b.abs) specs.push("ABS");
    if (b.seat_height_mm) specs.push(`${b.seat_height_mm} mm seat`);

    return `
      <article class="card section-pad">
        <div style="display:grid; grid-template-columns: 160px 1fr; gap:1rem; align-items:center;">
          <img id="img_${id}" src="${FALLBACK_IMAGE}" alt="${escapeHtml(b.name || 'Bike')}" style="width:160px; height:110px; object-fit:cover; border-radius:10px; border:1px solid var(--border);" />
          <div>
            <h3 style="margin:.1rem 0 .35rem 0;">${escapeHtml(b.name || "Unnamed")}</h3>
            <div class="subtitle" style="margin-bottom:.4rem;">${escapeHtml(b.category || "Motorcycle")}${specs.length ? " • " + specs.join(" • ") : ""}</div>
            ${reasons.length ? `<ul style="margin:.25rem 0 .5rem 1rem; padding:0;">${reasons.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>` : ""}
            ${b.url ? `<a href="${escapeAttr(b.url)}" target="_blank" rel="noopener" class="btn btn-outline" style="text-decoration:none;">Learn more</a>` : ""}
          </div>
        </div>
      </article>
    `;
  }

  function escapeHtml(s) {
    return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;" }[c]));
  }
  function escapeAttr(s) { return escapeHtml(s).replace(/"/g, "&quot;"); }

  // --- Chat (optional demo) ---
  async function sendChat(text) {
    if (!text || !chatLog) return;
    appendChat("you", text);
    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ message: text }),
      });
      const data = await res.json();
      appendChat("bot", data.message || "(ok)");
      if (Array.isArray(data.actions)) {
        for (const a of data.actions) {
          if (a.type === "UPDATE_PROFILE" && a.patch) {
            const prof = Object.assign(getProfile(), a.patch);
            sessionStorage.setItem("rr_profile", JSON.stringify(prof));
          }
          if (a.type === "RECOMMEND") {
            runRecommend();
          }
        }
      }
    } catch (e) {
      appendChat("bot", "Error talking to server.");
    }
  }

  function appendChat(who, text) {
    if (!chatLog) return;
    const wrap = document.createElement("div");
    wrap.style.margin = ".35rem 0";
    wrap.innerHTML = `<strong>${who === "you" ? "You" : "Assistant"}:</strong> ${escapeHtml(text)}`;
    chatLog.appendChild(wrap);
  }
}
