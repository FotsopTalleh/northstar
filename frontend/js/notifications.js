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
    let actions = "";
    if (n.type === "clan_invite" && !n.read) {
      actions = `<div style="display:flex;gap:8px;margin-top:8px">
        <button class="btn btn-success-custom" style="padding:4px 10px;font-size:0.75rem" onclick="event.stopPropagation(); respondInvite('${n.notification_id}', 'accept', this)">Accept</button>
        <button class="btn btn-ghost" style="padding:4px 10px;font-size:0.75rem;padding:4px 10px" onclick="event.stopPropagation(); respondInvite('${n.notification_id}', 'decline', this)">Decline</button>
      </div>`;
    }
    return `
    <div class="notif-item ${n.read ? "" : "unread"}" data-id="${n.notification_id}" onclick="markRead('${n.notification_id}', this)">
      <p>${n.message}</p>
      ${actions}
      <div class="notif-time">${timeAgo(n.created_at)}</div>
    </div>
    `;
  }).join("");
}

async function respondInvite(notifId, action, btn) {
  setButtonLoading(btn, true);
  try {
    await apiFetch("/api/clans/respond-invite", "POST", { notification_id: notifId, action });
    showToast(action === "accept" ? "Clan joined!" : "Invite declined", "success");
    await fetchNotifications();
    if (action === "accept" && window.location.pathname.includes("clan.html")) {
      window.location.reload(); // Reload immediately to show clan view
    }
  } catch (err) {
    showToast(err.message, "error");
    setButtonLoading(btn, false, action === "accept" ? "Accept" : "Decline");
  }}

async function markRead(notifId, el) {
  try {
    await apiFetch(`/api/notifications/${notifId}/read`, "PATCH");
    el.classList.remove("unread");
    await fetchNotifications();
  } catch (_) {}
}
