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

  // Load profile first so the toggle reflects the real server value
  await loadProfile();

  // Update the browser permission status badge in the notification settings card
  updateNotifPermissionStatus();

  // Auto-subscribe to push AFTER loadProfile has set the toggle to the correct state
  const autoToggle = document.getElementById("notif-enabled-toggle");
  if (autoToggle && autoToggle.checked) {
    subscribeToPush().catch(err => console.warn("Auto-push subscribe failed:", err));
  }

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
      if (label) label.textContent = enabled ? "Notifications On" : "Notifications Off";
      try {
        await apiFetch("/api/users/me", "PATCH", { notifications_enabled: enabled });
        if (enabled) {
          const granted = await subscribeToPush();
          if (!granted) {
            // Browser blocked permission — revert toggle
            toggle.checked = false;
            if (label) label.textContent = "Notifications Off";
            await apiFetch("/api/users/me", "PATCH", { notifications_enabled: false });
            showToast("Notifications blocked by browser. Allow them in your browser settings.", "error");
            return;
          }
        }
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

/**
 * Reflect the real browser notification permission state in the
 * Notification Settings card so users know why they may not be
 * receiving push notifications.
 */
function updateNotifPermissionStatus() {
  const statusEl = document.getElementById("notif-permission-status");
  const enableWrap = document.getElementById("notif-enable-btn-wrap");
  const toggle = document.getElementById("notif-enabled-toggle");
  if (!statusEl) return;

  const perm = ("Notification" in window) ? Notification.permission : "unsupported";

  if (perm === "granted") {
    statusEl.style.display = "flex";
    statusEl.style.background = "rgba(46,213,115,0.12)";
    statusEl.style.color = "var(--success)";
    statusEl.innerHTML = '<i data-lucide="check-circle" style="width:14px;height:14px;margin-right:6px;flex-shrink:0"></i>Browser notifications are active.';
    if (enableWrap) enableWrap.style.display = "none";
  } else if (perm === "denied") {
    statusEl.style.display = "flex";
    statusEl.style.background = "rgba(255,71,87,0.12)";
    statusEl.style.color = "var(--danger)";
    statusEl.innerHTML = '<i data-lucide="alert-circle" style="width:14px;height:14px;margin-right:6px;flex-shrink:0"></i>Blocked by browser. Allow notifications in your browser site settings.';
    if (toggle) { toggle.checked = false; }
    if (enableWrap) enableWrap.style.display = "none";
  } else if (perm === "default") {
    statusEl.style.display = "flex";
    statusEl.style.background = "rgba(255,165,0,0.12)";
    statusEl.style.color = "var(--warning)";
    statusEl.innerHTML = '<i data-lucide="bell-off" style="width:14px;height:14px;margin-right:6px;flex-shrink:0"></i>Permission not granted yet.';
    if (enableWrap) enableWrap.style.display = "block";
  } else {
    statusEl.style.display = "flex";
    statusEl.style.background = "rgba(108,99,255,0.1)";
    statusEl.style.color = "var(--text-muted)";
    statusEl.innerHTML = '<i data-lucide="info" style="width:14px;height:14px;margin-right:6px;flex-shrink:0"></i>Push notifications not supported on this browser.';
    if (toggle) { toggle.checked = false; }
    if (enableWrap) enableWrap.style.display = "none";
  }

  if (window.lucide) window.lucide.createIcons({ root: statusEl });
}
