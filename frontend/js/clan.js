/**
 * clan.js — Clan profile, member management, battle initiation
 */

document.addEventListener("DOMContentLoaded", async () => {
  requireLogin();
  const user = getUser();
  const uEl = document.getElementById("nav-username");
  if (uEl && user) uEl.textContent = user.username;
  const avEl = document.getElementById("nav-avatar");
  if (avEl && user) avEl.innerHTML = renderAvatar(user.username, user.avatar_color, "avatar-sm");

  await initNotifications();
  document.getElementById("btn-logout")?.addEventListener("click", () => { clearToken(); window.location.href = "/"; });

  // Load full profile from API to get clan_id
  try {
    const me = await apiFetch("/api/users/me");
    if (me && me.clan_id) {
      await loadClan(me.clan_id);
    } else {
      showNoClan();
    }
  } catch (err) {
    showToast("Error loading clan: " + err.message, "error");
  }

  // Create clan form
  document.getElementById("form-create-clan")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button");
    const name = document.getElementById("clan-name-input").value.trim();
    const desc = document.getElementById("clan-desc-input").value.trim();
    if (!name) return;
    setButtonLoading(btn, true);
    try {
      const clan = await apiFetch("/api/clans/create", "POST", { name, description: desc });
      const u = getUser(); if (u) { u.clan_id = clan.clan_id; setUser(u); }
      showToast("Clan created!", "success");
      await loadClan(clan.clan_id);
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setButtonLoading(btn, false);
    }
  });

  // Invite user
  document.getElementById("form-invite")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button");
    const userId = document.getElementById("invite-user-id").value.trim();
    const me = getUser();
    if (!userId || !me?.clan_id) return;
    setButtonLoading(btn, true);
    try {
      await apiFetch("/api/clans/invite", "POST", { clan_id: me.clan_id, user_id: userId });
      showToast("Invitation sent!", "success");
      document.getElementById("invite-user-id").value = "";
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setButtonLoading(btn, false);
    }
  });

  // Leave clan
  document.getElementById("btn-leave-clan")?.addEventListener("click", async () => {
    if (!confirm("Are you sure you want to leave the clan?")) return;
    try {
      await apiFetch("/api/clans/leave", "POST");
      const u = getUser(); if (u) { u.clan_id = null; setUser(u); }
      showToast("You left the clan", "info");
      showNoClan();
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Transfer leadership
  document.getElementById("form-transfer")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const newLeaderId = document.getElementById("transfer-user-id").value.trim();
    if (!newLeaderId) return;
    try {
      await apiFetch("/api/clans/transfer-leadership", "POST", { new_leader_id: newLeaderId });
      showToast("Leadership transferred!", "success");
      document.getElementById("transfer-user-id").value = "";
      const me = getUser(); if (me?.clan_id) await loadClan(me.clan_id);
    } catch (err) {
      showToast(err.message, "error");
    }
  });

  // Challenge battle
  document.getElementById("form-battle")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const btn = e.target.querySelector("button");
    const targetClanId = document.getElementById("battle-target-id").value.trim();
    const duration = document.getElementById("battle-duration").value;
    if (!targetClanId) return;
    setButtonLoading(btn, true);
    try {
      await apiFetch("/api/battles/challenge", "POST", { target_clan_id: targetClanId, duration });
      showToast("Battle challenge sent!", "success");
      document.getElementById("battle-target-id").value = "";
    } catch (err) {
      showToast(err.message, "error");
    } finally {
      setButtonLoading(btn, false);
    }
  });
});

async function kickMember(userId) {
  if (!confirm("Are you sure you want to kick this user from the clan?")) return;
  try {
    await apiFetch("/api/clans/kick", "POST", { user_id: userId });
    showToast("User kicked.", "info");
    const me = getUser(); if (me?.clan_id) await loadClan(me.clan_id);
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function loadClan(clanId) {
  try {
    const clan = await apiFetch(`/api/clans/${clanId}`);
    renderClanView(clan);
  } catch (err) {
    showToast("Could not load clan: " + err.message, "error");
  }
}

function showNoClan() {
  document.getElementById("clan-view")?.classList.add("d-none");
  document.getElementById("no-clan-view")?.classList.remove("d-none");
}

function renderClanView(clan) {
  document.getElementById("no-clan-view")?.classList.add("d-none");
  document.getElementById("clan-view")?.classList.remove("d-none");

  setElClan("clan-title", clan.name);
  setElClan("clan-desc", clan.description || "No description");
  const leaderEl = document.getElementById("clan-leader");
  if (leaderEl) leaderEl.innerHTML = `<i data-lucide="crown" class="icon-sm" style="margin-right:4px"></i>${clan.leader_username}`;
  setElClan("clan-members-count", `${clan.member_count || 0}/10 members`);
  setElClan("clan-status", clan.status?.toUpperCase() || "");
  setElClan("clan-id-raw", clan.clan_id || "—");

  // Members list
  const membersEl = document.getElementById("clan-members-list");
  const me = getUser();
  const amILeader = clan.leader_username === me?.username;

  if (membersEl && clan.members) {
    membersEl.innerHTML = clan.members.map(m => `
      <div class="lb-entry">
        ${renderAvatar(m.username, m.avatar_color)}
        <div style="flex:1">
          <div class="lb-username">${esc(m.username)} ${m.is_leader ? '<i data-lucide="crown" style="width:16px;height:16px;color:var(--gold);margin-left:4px"></i>' : ""}</div>
          <div style="display:flex;gap:4px;margin-top:2px">${(m.badges || []).slice(0, 3).map(b => `<span title="${b.name}" style="display:inline-flex"><i data-lucide="${b.icon || 'award'}" style="width:16px;height:16px;color:var(--gold)"></i></span>`).join("")}</div>
        </div>
        <span class="lb-xp">${m.total_xp} XP</span>
        ${amILeader && !m.is_leader ? `<button onclick="kickMember('${m.user_id}')" class="btn btn-ghost" style="padding:4px 8px;font-size:0.75rem;margin-left:8px;border-color:var(--danger);color:var(--danger)"><i data-lucide="user-minus" style="width:14px;height:14px"></i></button>` : ""}
      </div>
    `).join("");
  }

  // Battle history
  const bEl = document.getElementById("battle-history-list");
  if (bEl && clan.battle_history) {
    if (!clan.battle_history.length) {
      bEl.innerHTML = `<p style="color:var(--text-muted);font-size:.9rem">No battles yet</p>`;
    } else {
      bEl.innerHTML = clan.battle_history.map(b => `
        <div class="lb-entry">
          <span style="display:inline-flex;align-items:center;justify-content:center;width:32px;height:32px;color:var(--text-secondary)">
            <i data-lucide="${b.status === 'completed' ? 'flag' : b.status === 'active' ? 'swords' : 'hourglass'}" style="width:20px;height:20px"></i>
          </span>
          <div style="flex:1">
            <div style="font-weight:600">${b.clan_a_id} vs ${b.clan_b_id}</div>
            <div style="font-size:.8rem;color:var(--text-muted)">${b.duration} · ${b.status}</div>
          </div>
          ${b.winner_clan_id ? `<span style="color:var(--gold);font-size:.85rem;display:flex;align-items:center;gap:4px">Winner: ${b.winner_clan_id === clan.clan_id ? '<span style="color:var(--accent-light);font-weight:bold">YOUR CLAN</span> <i data-lucide="trophy" style="width:16px;height:16px;color:var(--gold)"></i>' : "Opponent"}</span>` : ""}
        </div>
      `).join("");
    }
  }
  if (window.lucide) window.lucide.createIcons();
}

function setElClan(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}
function esc(str) { return String(str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;"); }

function copyClanId() {
  const raw = document.getElementById("clan-id-raw");
  if (!raw || raw.textContent === "loading..." || raw.textContent === "—") return;
  navigator.clipboard.writeText(raw.textContent)
    .then(() => showToast("Clan ID copied!", "success"))
    .catch(() => showToast("Could not copy — try manually.", "error"));
}
