/**
 * dashboard.js — Daily task management: plan creation, task add, lock, complete, fail
 */

let _plan = null;
let _tasks = [];
let _pendingXP = 0;

document.addEventListener("DOMContentLoaded", async () => {
  requireLogin();
  const user = getUser();
  if (!user) { window.location.href = "/"; return; }

  // Render username in navbar
  const uEl = document.getElementById("nav-username");
  if (uEl) uEl.textContent = user.username;
  const avEl = document.getElementById("nav-avatar");
  if (avEl) avEl.innerHTML = renderAvatar(user.username, user.avatar_color, "avatar-sm");

  await initNotifications();
  await loadDashboard();

  // Add planned task
  document.getElementById("form-add-planned")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("input-planned-title");
    const btn   = e.target.querySelector("button[type=submit]");
    const title = input.value.trim();
    if (!title) return;
    setButtonLoading(btn, true);
    input.disabled = true;
    await addTask(title, "planned");
    input.value = "";
    input.disabled = false;
    setButtonLoading(btn, false);
  });

  // Add unplanned task
  document.getElementById("form-add-unplanned")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("input-unplanned-title");
    const btn   = e.target.querySelector("button[type=submit]");
    const title = input.value.trim();
    if (!title) return;
    setButtonLoading(btn, true);
    input.disabled = true;
    await addTask(title, "unplanned");
    input.value = "";
    input.disabled = false;
    setButtonLoading(btn, false);
  });

  // Schedule for tomorrow
  document.getElementById("form-schedule-tomorrow")?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = document.getElementById("input-tomorrow-title");
    const btn   = e.target.querySelector("button[type=submit]");
    const title = input.value.trim();
    if (!title) return;
    setButtonLoading(btn, true);
    input.disabled = true;
    await scheduleTomorrow(title);
    input.value = "";
    input.disabled = false;
    setButtonLoading(btn, false);
  });

  // Lock plan
  document.getElementById("btn-lock-plan")?.addEventListener("click", lockPlan);

  // Logout
  document.getElementById("btn-logout")?.addEventListener("click", () => {
    clearToken();
    window.location.href = "/";
  });
});

async function loadDashboard() {
  const pList = document.getElementById("list-planned");
  const uList = document.getElementById("list-unplanned");
  if (pList) pList.innerHTML = `<div class="skeleton" style="height:56px;margin-bottom:10px"></div><div class="skeleton" style="height:56px;margin-bottom:10px"></div>`;
  if (uList) uList.innerHTML = `<div class="skeleton" style="height:56px;margin-bottom:10px"></div>`;

  try {
    // Ensure a plan exists for today
    await apiFetch("/api/plans/create", "POST");
    const data = await apiFetch("/api/plans/today");
    if (!data) return;
    _plan = data.plan;
    _tasks = data.tasks || [];
    renderAll();
  } catch (err) {
    showToast("Failed to load dashboard: " + err.message, "error");
  }
}

function renderAll() {
  renderDateHeader();
  renderStatsStrip();
  renderPlanStatus();
  renderTaskList("planned");
  renderTaskList("unplanned");
}

function renderDateHeader() {
  const el = document.getElementById("today-date");
  if (el) el.textContent = new Date().toLocaleDateString(undefined, { weekday: "long", month: "long", day: "numeric" });
}

function renderStatsStrip() {
  const planned   = _tasks.filter(t => t.type === "planned");
  const unplanned = _tasks.filter(t => t.type === "unplanned");
  const done      = _tasks.filter(t => t.status === "completed");
  const failed    = _tasks.filter(t => t.status === "failed");
  const user      = getUser();

  setEl("stat-total",    `${done.length}/${_tasks.length}`);
  setEl("stat-planned",  `${planned.filter(t=>t.status==="completed").length}/${planned.length}`);
  setEl("stat-unplanned",`${unplanned.filter(t=>t.status==="completed").length}/${unplanned.length}`);
  setEl("stat-xp",       user ? user.total_xp : 0);
}

function setEl(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

function renderPlanStatus() {
  const lockBtn    = document.getElementById("btn-lock-plan");
  const lockedBanner = document.getElementById("plan-locked-banner");
  const addSection = document.getElementById("section-add-planned");

  const isLocked = _plan?.locked;

  if (lockBtn) lockBtn.style.display = isLocked ? "none" : "flex";
  if (lockedBanner) lockedBanner.style.display = isLocked ? "flex" : "none";
  if (addSection) addSection.style.display = isLocked ? "none" : "block";
}

function renderTaskList(type) {
  const listEl = document.getElementById(`list-${type}`);
  if (!listEl) return;
  const tasks = _tasks.filter(t => t.type === type);

  if (!tasks.length) {
    listEl.innerHTML = `<div class="empty-state" style="padding:24px">
      <div class="empty-icon"><i data-lucide="${type === "planned" ? "clipboard-list" : "zap"}" style="width:36px;height:36px;color:var(--text-muted)"></i></div>
      <p style="color:var(--text-muted);font-size:.9rem;">No ${type} tasks yet</p>
    </div>`;
    if (window.lucide) window.lucide.createIcons({ root: listEl });
    return;
  }

  listEl.innerHTML = tasks.map(t => renderTaskItem(t)).join("");
  if (window.lucide) window.lucide.createIcons({ root: listEl });
}

function renderTaskItem(task) {
  const isDone      = task.status === "completed";
  const isFailed    = task.status === "failed";
  const isCarried   = task.status === "carried_over";
  const isPending   = task.status === "pending";
  const isLocked    = _plan?.locked;

  const checkState = isDone ? "checked" : (isFailed || isCarried ? "failed-check" : "");
  const checkIcon  = isDone
    ? '<i data-lucide="check" style="width:14px;height:14px"></i>'
    : (isFailed
        ? '<i data-lucide="x" style="width:14px;height:14px"></i>'
        : (isCarried ? '<i data-lucide="calendar-clock" style="width:14px;height:14px"></i>' : ""));

  const xpChip = task.xp_awarded != null
    ? `<span class="xp-chip ${task.xp_awarded >= 0 ? 'positive' : 'negative'}">${fmtXP(task.xp_awarded)} XP</span>`
    : `<span class="xp-chip provisional" style="opacity:.6">${task.type === "planned" ? "+7" : "+3"} XP</span>`;

  // Planned tasks: Done button only available AFTER plan is locked
  // Unplanned tasks: always completable
  const canComplete = task.type === "unplanned" || (task.type === "planned" && isLocked);

  const actions = isPending ? `
    <div class="d-flex gap-2 flex-wrap">
      ${canComplete ? `<button class="btn btn-success-custom" style="padding:5px 12px;font-size:.8rem;display:flex;align-items:center;gap:4px" onclick="completeTask('${task.task_id}')"><i data-lucide="check" style="width:14px;height:14px"></i> Done</button>` : `<span style="font-size:.75rem;color:var(--text-muted);display:flex;align-items:center;gap:4px"><i data-lucide="lock" style="width:13px;height:13px"></i> Lock plan to complete</span>`}
      ${task.type === "planned" && isLocked ? `<button class="btn btn-danger-custom" style="padding:5px 12px;font-size:.8rem;display:flex;align-items:center;gap:4px" onclick="failTask('${task.task_id}')"><i data-lucide="x" style="width:14px;height:14px"></i> Fail</button>` : ""}
      ${task.type === "planned" && isLocked ? `<button class="btn btn-ghost" style="padding:5px 12px;font-size:.8rem;display:flex;align-items:center;gap:4px;color:var(--warning);border-color:var(--warning)" onclick="carryOverTask('${task.task_id}')"><i data-lucide="calendar-clock" style="width:14px;height:14px"></i> Carry (−2 XP)</button>` : ""}
    </div>
  ` : (isCarried ? `<span style="font-size:.75rem;color:var(--warning);display:flex;align-items:center;gap:4px"><i data-lucide="calendar-clock" style="width:13px;height:13px"></i> Moved to tomorrow</span>` : "");

  return `
    <div class="task-item ${task.status} ${task.type}" id="task-${task.task_id}">
      <div class="task-checkbox ${checkState}">${checkIcon}</div>
      <span class="task-title">${escHtml(task.title)}</span>
      <span class="task-type-badge ${task.type}">${task.type}</span>
      ${xpChip}
      ${actions}
    </div>
  `;
}

function escHtml(str) {
  return String(str).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}

async function addTask(title, type) {
  try {
    const task = await apiFetch("/api/tasks/add", "POST", { title, type });
    _tasks.push(task);
    renderTaskList(type);
    renderStatsStrip();
    showToast(`Task added!`, "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function completeTask(taskId) {
  try {
    const result = await apiFetch(`/api/tasks/${taskId}/complete`, "PATCH");
    // Update local state
    const idx = _tasks.findIndex(t => t.task_id === taskId);
    if (idx !== -1) {
      _tasks[idx].status = "completed";
      _tasks[idx].xp_awarded = result.xp_delta;
    }
    // Update stored user XP
    const user = getUser();
    if (user) {
      user.total_xp = result.new_total_xp;
      setUser(user);
    }
    renderAll();
    showToast(`+${result.xp_delta} XP earned!`, "success");
    // Animate XP stat
    const xpEl = document.getElementById("stat-xp");
    if (xpEl) { xpEl.classList.remove("xp-pop"); void xpEl.offsetWidth; xpEl.classList.add("xp-pop"); }
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function failTask(taskId) {
  try {
    const result = await apiFetch(`/api/tasks/${taskId}/fail`, "PATCH");
    const idx = _tasks.findIndex(t => t.task_id === taskId);
    if (idx !== -1) {
      _tasks[idx].status = "failed";
      _tasks[idx].xp_awarded = result.xp_delta;
    }
    const user = getUser();
    if (user) { user.total_xp = result.new_total_xp; setUser(user); }
    renderAll();
    showToast(`${result.xp_delta} XP deducted`, "error");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function lockPlan() {
  const btn = document.getElementById("btn-lock-plan");
  setButtonLoading(btn, true);
  try {
    await apiFetch("/api/plans/lock", "POST");
    if (_plan) _plan.locked = true;
    renderAll();
    showToast("Plan locked! Stay committed.", "success");
  } catch (err) {
    showToast(err.message, "error");
    setButtonLoading(btn, false);
  }
}

async function scheduleTomorrow(title) {
  try {
    const result = await apiFetch("/api/tasks/schedule-tomorrow", "POST", { title });
    const msg = document.getElementById("tomorrow-count-msg");
    if (msg) msg.textContent = `✓ "${result.title}" scheduled for ${result.scheduled_for}`;
    showToast(`Task scheduled for tomorrow!`, "success");
  } catch (err) {
    showToast(err.message, "error");
  }
}

async function carryOverTask(taskId) {
  const confirmed = confirm("Carry this task to tomorrow? This costs −2 XP.");
  if (!confirmed) return;
  try {
    const result = await apiFetch(`/api/tasks/${taskId}/carry-over`, "POST");
    // Update local state
    const idx = _tasks.findIndex(t => t.task_id === taskId);
    if (idx !== -1) {
      _tasks[idx].status = "carried_over";
      _tasks[idx].xp_awarded = result.xp_delta;
    }
    // Update stored user XP
    const user = getUser();
    if (user) {
      user.total_xp = result.new_total_xp;
      setUser(user);
    }
    renderAll();
    showToast(`Task moved to ${result.scheduled_for} (${result.xp_delta} XP)`, "error");
  } catch (err) {
    showToast(err.message, "error");
  }
}
