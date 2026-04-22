/**
 * profile.js — User profile: view stats, badges, XP logs, edit avatar/timezone
 */

document.addEventListener("DOMContentLoaded", async () => {
  requireLogin();
  const u = getUser();
  const uEl = document.getElementById("nav-username");
  if (uEl && u) uEl.textContent = u.username;
  const avEl = document.getElementById("nav-avatar");
  if (avEl && u) avEl.innerHTML = renderAvatar(u.username, u.avatar_color, "avatar-sm");

  await initNotifications();
  document.getElementById("btn-logout")?.addEventListener("click", () => { clearToken(); window.location.href = "/"; });

  await loadProfile();

  // Edit form
  document.getElementById("form-edit-profile")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button");
    const tz    = document.getElementById("edit-timezone").value.trim();
    const color = document.getElementById("edit-avatar-color").value;
    const body  = {};
    if (tz) body.timezone = tz;
    if (color) body.avatar_color = color;
    
    setButtonLoading(btn, true);
    try {
      await apiFetch("/api/users/me", "PATCH", body);
      const stored = getUser();
      if (stored) {
        if (tz) stored.timezone = tz;
        if (color) stored.avatar_color = color;
        setUser(stored);
      }
      showToast("Profile updated!", "success");
      await loadProfile();
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setButtonLoading(btn, false);
    }
  });

  // Notification toggle
  const toggle = document.getElementById("notif-enabled-toggle");
  if (toggle) {
    toggle.addEventListener("change", async () => {
      const enabled = toggle.checked;
      const label = document.getElementById("notif-toggle-label");
      if (label) {
        label.textContent = enabled ? "Notifications On" : "Notifications Off";
      }
      try {
        await apiFetch("/api/users/me", "PATCH", { notifications_enabled: enabled });
        showToast(enabled ? "Notifications enabled" : "Notifications disabled", "success");
      } catch (err) {
        // Revert the toggle if the request failed
        toggle.checked = !enabled;
        if (label) label.textContent = !enabled ? "Notifications On" : "Notifications Off";
        showToast(err.message, "error");
      }
    });
  }
});


async function loadProfile() {
  try {
    const me = await apiFetch("/api/users/me");
    renderProfile(me);
  } catch (err) {
    showToast("Failed to load profile: " + err.message, "error");
  }
}

function renderProfile(user) {
  // Avatar
  const avEl = document.getElementById("profile-avatar");
  if (avEl) avEl.innerHTML = renderAvatar(user.username, user.avatar_color, "avatar-xl");

  // Fields
  setProfileEl("profile-username",  user.username);
  setProfileEl("profile-email",     user.email);
  setProfileEl("profile-timezone",  user.timezone);
  setProfileEl("profile-joined",    user.joined_at ? new Date(user.joined_at).toLocaleDateString() : "—");
  setProfileEl("profile-xp",        `${user.total_xp} XP`);

  // Pre-fill edit form
  const tzInput    = document.getElementById("edit-timezone");
  const colorInput = document.getElementById("edit-avatar-color");
  if (tzInput) tzInput.value = user.timezone || "";
  if (colorInput) colorInput.value = user.avatar_color || "#6C63FF";

  // Sync notification toggle state
  const toggle = document.getElementById("notif-enabled-toggle");
  const label  = document.getElementById("notif-toggle-label");
  const enabled = user.notifications_enabled !== false; // default true
  if (toggle) toggle.checked = enabled;
  if (label)  label.textContent = enabled ? "Notifications On" : "Notifications Off";

  // Badges
  const badgeEl = document.getElementById("profile-badges");
  if (badgeEl) {
    const badges = user.badges || [];
    if (!badges.length) {
      badgeEl.innerHTML = `<p style="color:var(--text-muted);font-size:.9rem">No badges earned yet — stay consistent!</p>`;
    } else {
      badgeEl.innerHTML = badges.map(b => `
        <div class="badge-pill" title="${b.description || b.name}">
          <span class="badge-icon" style="display:inline-flex;margin-right:2px"><i data-lucide="${b.icon || 'award'}" style="width:16px;height:16px;color:${b.icon==='flame'?'#ff8c00':b.icon==='moon'?'var(--text-muted)':b.icon==='swords'?'var(--gold)':b.icon==='lock'?'var(--accent-light)':b.icon==='ghost'?'#bbb':'var(--text-secondary)'}"></i></span>
          <span>${b.name}</span>
          ${b.awarded_at ? `<span style="font-size:.7rem;color:var(--text-muted)">${b.awarded_at}</span>` : ""}
        </div>
      `).join("");
    }
  }

  // XP log
  const logEl = document.getElementById("xp-log-list");
  if (logEl) {
    const logs = user.xp_logs || [];
    if (!logs.length) {
      logEl.innerHTML = `<p style="color:var(--text-muted);font-size:.9rem">No XP activity yet</p>`;
    } else {
      logEl.innerHTML = logs.map(log => `
        <div class="lb-entry" style="padding:10px 16px">
          <span class="xp-chip ${log.xp_delta >= 0 ? 'positive' : 'negative'}">${fmtXP(log.xp_delta)} XP</span>
          <div style="flex:1;font-size:.87rem">${esc(log.reason)}</div>
          <span style="font-size:.75rem;color:var(--text-muted)">${timeAgo(log.timestamp)}</span>
          ${log.is_provisional ? `<span style="font-size:.7rem;color:var(--gold);margin-left:6px">provisional</span>` : ""}
        </div>
      `).join("");
    }
  }
  if (window.lucide) window.lucide.createIcons();
}

function setProfileEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val || "—";
}
function esc(str) { return String(str||"").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;"); }

async function fireTest(type) {
  try {
    await apiFetch("/api/notifications/test", "POST", { type });
    showToast("Test notification sent — check your bell!", "success");
    // Refresh bell badge immediately
    if (typeof fetchNotifications === "function") await fetchNotifications();
  } catch (err) {
    showToast(err.message, "error");
  }
}
