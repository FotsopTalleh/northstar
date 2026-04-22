/**
 * notifications.js — Bell icon, fetch, display, mark-read
 */

let _notifOpen = false;

async function initNotifications() {
  const bell = document.getElementById("notif-bell");
  const dropdown = document.getElementById("notif-dropdown");
  if (!bell || !dropdown) return;

  await fetchNotifications();

  bell.addEventListener("click", async (e) => {
    e.stopPropagation();
    // On mobile: navigate to dedicated notifications page
    if (window.innerWidth <= 768) {
      window.location.href = "/notifications.html";
      return;
    }
    _notifOpen = !_notifOpen;
    dropdown.classList.toggle("open", _notifOpen);
    if (_notifOpen) await fetchNotifications();
  });

  document.addEventListener("click", () => {
    _notifOpen = false;
    dropdown.classList.remove("open");
  });

  dropdown.addEventListener("click", (e) => e.stopPropagation());

  const markAllBtn = document.getElementById("notif-mark-all");
  if (markAllBtn) {
    markAllBtn.addEventListener("click", async () => {
      await apiFetch("/api/notifications/read-all", "PATCH");
      await fetchNotifications();
    });
  }
}

async function fetchNotifications() {
  try {
    const notifs = await apiFetch("/api/notifications");
    if (!notifs) return;
    renderNotifications(notifs);
    const unread = notifs.filter(n => !n.read).length;
    const badge = document.getElementById("notif-count");
    if (badge) {
      badge.textContent = unread > 0 ? (unread > 9 ? "9+" : unread) : "";
      badge.style.display = unread > 0 ? "flex" : "none";
    }
  } catch (_) {}
}

function renderNotifications(notifs) {
  const list = document.getElementById("notif-list");
  if (!list) return;
  if (!notifs.length) {
    list.innerHTML = `<div class="notif-item"><p style="color:var(--text-muted);text-align:center;">No notifications yet</p></div>`;
    return;
  }
  list.innerHTML = notifs.slice(0, 20).map(n => {
    const typeIcon = {
      clan_invite:             "users",
      battle_challenge:        "swords",
      overtaken:               "trending-down",
      clan_behind:             "alert-triangle",
      clan_losing:             "shield-alert",
      daily_summary:           "sun",
      peer_activity:           "activity",
      no_tasks_reminder:       "clipboard-list",
      plan_not_locked:         "lock-open",
      tasks_pending_reminder:  "clock",
      reached_top:             "trophy",
    }[n.type] || "bell";

    const typeColor = {
      clan_invite:             "var(--accent-light)",
      battle_challenge:        "var(--danger)",
      overtaken:               "var(--warning)",
      clan_behind:             "var(--danger)",
      clan_losing:             "var(--danger)",
      daily_summary:           "var(--gold)",
      peer_activity:           "var(--success)",
      no_tasks_reminder:       "var(--warning)",
      plan_not_locked:         "var(--warning)",
      tasks_pending_reminder:  "var(--accent-light)",
      reached_top:             "var(--gold)",
    }[n.type] || "var(--text-muted)";

    let actions = "";

    // Clan invite — Accept / Decline
    if (n.type === "clan_invite" && !n.read) {
      actions = `<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
        <button class="btn btn-success-custom" style="padding:6px 14px;font-size:0.8rem;flex:1;min-width:80px" onclick="event.stopPropagation(); respondInvite('${n.notification_id}', 'accept', this)">Accept</button>
        <button class="btn btn-ghost"         style="padding:6px 14px;font-size:0.8rem;flex:1;min-width:80px" onclick="event.stopPropagation(); respondInvite('${n.notification_id}', 'decline', this)">Decline</button>
      </div>`;
    }

    // Battle challenge — Accept / Decline
    if (n.type === "battle_challenge" && !n.read) {
      actions = `<div style="display:flex;gap:8px;margin-top:8px;flex-wrap:wrap">
        <button class="btn btn-danger-custom" style="padding:6px 14px;font-size:0.8rem;flex:1;min-width:80px" onclick="event.stopPropagation(); respondBattle('${n.notification_id}', 'accept', this)">Accept Battle</button>
        <button class="btn btn-ghost"         style="padding:6px 14px;font-size:0.8rem;flex:1;min-width:80px" onclick="event.stopPropagation(); respondBattle('${n.notification_id}', 'decline', this)">Decline</button>
      </div>`;
    }

    return `
    <div class="notif-item ${n.read ? "" : "unread"}" data-id="${n.notification_id}" onclick="markRead('${n.notification_id}', this)">
      <div style="display:flex;align-items:flex-start;gap:10px">
        <div style="width:32px;height:32px;border-radius:50%;background:rgba(108,99,255,0.1);display:flex;align-items:center;justify-content:center;flex-shrink:0">
          <i data-lucide="${typeIcon}" style="width:15px;height:15px;color:${typeColor}"></i>
        </div>
        <div style="flex:1">
          <p style="margin:0;font-size:.88rem">${n.message}</p>
          ${actions}
          <div class="notif-time">${timeAgo(n.created_at)}</div>
        </div>
      </div>
    </div>
    `;
  }).join("");
  if (window.lucide) window.lucide.createIcons({ root: list });
}

async function respondInvite(notifId, action, btn) {
  setButtonLoading(btn, true);
  try {
    await apiFetch("/api/clans/respond-invite", "POST", { notification_id: notifId, action });
    showToast(action === "accept" ? "Clan joined!" : "Invite declined", "success");
    await fetchNotifications();
    if (action === "accept" && window.location.pathname.includes("clan.html")) {
      window.location.reload();
    }
  } catch (err) {
    showToast(err.message, "error");
    setButtonLoading(btn, false, action === "accept" ? "Accept" : "Decline");
  }
}

async function respondBattle(notifId, action, btn) {
  setButtonLoading(btn, true);
  try {
    await apiFetch("/api/battles/respond", "POST", { notification_id: notifId, action });
    showToast(
      action === "accept" ? "Battle accepted! The war begins." : "Challenge declined.",
      action === "accept" ? "success" : "info"
    );
    await fetchNotifications();
  } catch (err) {
    showToast(err.message, "error");
    setButtonLoading(btn, false, action === "accept" ? "Accept Battle" : "Decline");
  }
}

async function markRead(notifId, el) {
  try {
    await apiFetch(`/api/notifications/${notifId}/read`, "PATCH");
    el.classList.remove("unread");
    await fetchNotifications();
  } catch (_) {}
}
