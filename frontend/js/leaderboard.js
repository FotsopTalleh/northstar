/**
 * leaderboard.js — 5 tabs: daily, weekly, monthly, yearly, global
 */

const LB_PERIODS = ["daily", "weekly", "monthly", "yearly", "global"];
let _activePeriod = "daily";

document.addEventListener("DOMContentLoaded", async () => {
  requireLogin();
  const user = getUser();
  const uEl = document.getElementById("nav-username");
  if (uEl && user) uEl.textContent = user.username;
  const avEl = document.getElementById("nav-avatar");
  if (avEl && user) avEl.innerHTML = renderAvatar(user.username, user.avatar_color, "avatar-sm");

  await initNotifications();

  // Tab click
  LB_PERIODS.forEach(period => {
    const btn = document.getElementById(`tab-${period}`);
    if (btn) btn.addEventListener("click", () => switchPeriod(period));
  });

  document.getElementById("btn-logout")?.addEventListener("click", () => { clearToken(); window.location.href = "/"; });

  await switchPeriod("daily");
});

async function switchPeriod(period) {
  _activePeriod = period;
  LB_PERIODS.forEach(p => {
    document.getElementById(`tab-${p}`)?.classList.toggle("active", p === period);
  });
  await loadLeaderboard(period);
}

async function loadLeaderboard(period) {
  const container = document.getElementById("lb-container");
  container.innerHTML = `
    <div class="skeleton" style="height:60px;margin-bottom:8px"></div>
    <div class="skeleton" style="height:60px;margin-bottom:8px"></div>
    <div class="skeleton" style="height:60px;margin-bottom:8px"></div>
    <div class="skeleton" style="height:60px;margin-bottom:8px"></div>
  `;

  try {
    const entries = await apiFetch(`/api/leaderboard/${period}`);
    if (!entries || !entries.length) {
      container.innerHTML = `<div class="empty-state"><div class="empty-icon"><i data-lucide="wind" style="width:36px;height:36px;color:var(--text-muted)"></i></div><h3>No entries yet</h3><p>Be the first on the ${period} leaderboard!</p></div>`;
      if (window.lucide) window.lucide.createIcons({ root: container });
      return;
    }
    renderLeaderboard(entries);
  } catch (err) {
    container.innerHTML = `<div class="empty-state"><div class="empty-icon"><i data-lucide="alert-triangle" style="width:36px;height:36px;color:var(--danger)"></i></div><h3>Failed to load</h3><p>${err.message}</p></div>`;
    if (window.lucide) window.lucide.createIcons({ root: container });
  }
}

function renderLeaderboard(entries) {
  const container = document.getElementById("lb-container");
  const currentUser = getUser();

  // Podium (top 3)
  let html = "";
  if (entries.length >= 3) html += renderPodium(entries);

  const rankBadges = [
    '<i data-lucide="trophy" style="width:20px;height:20px;color:var(--gold);margin-top:-2px"></i>',
    '<i data-lucide="medal" style="width:20px;height:20px;color:#c0c0c0;margin-top:-2px"></i>',
    '<i data-lucide="medal" style="width:20px;height:20px;color:#cd7f32;margin-top:-2px"></i>'
  ];

  // Full list
  html += `<div id="lb-list">`;
  entries.forEach(entry => {
    const isMe = currentUser && entry.user_id === currentUser.user_id;
    const rankClass = entry.rank === 1 ? "rank-1" : entry.rank === 2 ? "rank-2" : entry.rank === 3 ? "rank-3" : "";
    const badges = (entry.badges || []).slice(0, 3).map(b =>
      `<span title="${b.name}" style="display:inline-flex;margin-right:4px"><i data-lucide="${b.icon || 'award'}" style="width:16px;height:16px;color:var(--gold)"></i></span>`
    ).join("");

    html += `
      <div class="lb-entry fade-in ${isMe ? "border-accent" : ""}" style="${isMe ? "border-color:var(--accent);background:rgba(108,99,255,0.06)" : ""}">
        <span class="lb-rank ${rankClass}">${entry.rank <= 3 ? rankBadges[entry.rank-1] : `#${entry.rank}`}</span>
        ${renderAvatar(entry.username, entry.avatar_color)}
        <div style="flex:1">
          <div class="lb-username">${escHtmlLB(entry.username)} ${isMe ? '<span style="color:var(--accent);font-size:.75rem">(you)</span>' : ""}</div>
          <div>${badges}</div>
        </div>
        <span class="lb-xp">${entry.xp >= 0 ? "+" : ""}${entry.xp} XP</span>
      </div>
    `;
  });
  html += `</div>`;
  container.innerHTML = html;
  if (window.lucide) window.lucide.createIcons({ root: container });
}

function renderPodium(entries) {
  const order = [entries[1], entries[0], entries[2]];  // 2nd, 1st, 3rd visual order
  const sizes  = ["p2", "p1", "p3"];
  const labels = ["2nd", "1st", "3rd"];

  return `
    <div class="podium mb-4">
      ${order.map((e, i) => e ? `
        <div class="podium-place">
          ${renderAvatar(e.username, e.avatar_color, "avatar-lg")}
          <div style="font-size:.85rem;font-weight:600;color:var(--text-secondary)">${escHtmlLB(e.username)}</div>
          <div class="podium-block ${sizes[i]}">${labels[i]}</div>
          <div style="font-size:.8rem;color:var(--text-muted)">${e.xp >= 0 ? "+" : ""}${e.xp} XP</div>
        </div>` : ""
      ).join("")}
    </div>
  `;
}

function escHtmlLB(str) {
  return String(str || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
