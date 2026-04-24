/**
 * api.js — Centralized fetch wrapper.
 * All API calls go through apiFetch(). JWT is automatically attached.
 */

const API_BASE = "";  // Same origin via Flask static serving

// ── Theme Management ────────────────────────────────────────────────────────
function initTheme() {
  const theme = localStorage.getItem("xpforge_theme") || "dark";
  document.documentElement.setAttribute("data-theme", theme);
}
initTheme(); // Run immediately

function toggleTheme() {
  const current = document.documentElement.getAttribute("data-theme");
  const next = current === "light" ? "dark" : "light";
  document.documentElement.setAttribute("data-theme", next);
  localStorage.setItem("xpforge_theme", next);
  
  // Sync all theme icons dynamically
  document.querySelectorAll(".theme-icon").forEach(icon => {
    icon.innerHTML = next === "light" 
      ? '<line x1="12" y1="1" x2="12" y2="3"></line><line x1="12" y1="21" x2="12" y2="23"></line><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"></line><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"></line><line x1="1" y1="12" x2="3" y2="12"></line><line x1="21" y1="12" x2="23" y2="12"></line><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"></line><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"></line><circle cx="12" cy="12" r="5"></circle>' 
      : '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"></path>';
    icon.setAttribute('data-lucide', next === "light" ? 'sun' : 'moon');
  });
}

// ── PWA: Service Worker Registration ────────────────────────────────────────
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js")
      .then(reg => {
        // Listen for sync-complete messages from SW
        navigator.serviceWorker.addEventListener("message", (e) => {
          if (e.data?.type === "SYNC_COMPLETE") {
            showToast("🔄 Offline actions synced!", "success");
            if (typeof loadDashboard === "function") loadDashboard();
            if (typeof fetchNotifications === "function") fetchNotifications();
          }
        });

        // Auto-renew push subscription on every page load if the user
        // is logged in and has already granted browser permission.
        // This keeps the subscription fresh after VAPID key rotations.
        if (getToken() && Notification.permission === "granted") {
          subscribeToPush().catch(() => {});
        }
      })
      .catch(err => console.warn("SW registration failed:", err));
  });
}

// ── Online/offline indicator ─────────────────────────────────────────────────
window.addEventListener("online", () => {
  showToast("Back online — syncing...", "info");
  // Trigger background sync manually if supported
  navigator.serviceWorker?.ready.then(reg => {
    if (reg.sync) reg.sync.register("xpforge-sync").catch(() => {});
  });
});
window.addEventListener("offline", () => {
  showToast("You are offline. Changes will sync when reconnected.", "info");
});


function getToken() {
  return localStorage.getItem("jwt_token");
}

function setToken(token) {
  localStorage.setItem("jwt_token", token);
}

function clearToken() {
  localStorage.removeItem("jwt_token");
  localStorage.removeItem("user_data");
}

function getUser() {
  try {
    return JSON.parse(localStorage.getItem("user_data") || "null");
  } catch {
    return null;
  }
}

function setUser(user) {
  localStorage.setItem("user_data", JSON.stringify(user));
}

async function apiFetch(endpoint, method = "GET", body = null) {
  const token = getToken();
  const headers = { "Content-Type": "application/json" };
  if (token) headers["Authorization"] = `Bearer ${token}`;

  const options = { method, headers };
  if (body && method !== "GET") {
    options.body = JSON.stringify(body);
  }

  const response = await fetch(`${API_BASE}${endpoint}`, options);

  if (response.status === 401) {
    clearToken();
    window.location.href = "/";
    return null;
  }

  let data = null;
  try {
    data = await response.json();
  } catch (_) {
    data = {};
  }

  // 202 = queued offline by service worker — treat as optimistic success
  if (response.status === 202 && data?.offline) {
    showToast(data.message || "Saved offline – will sync when reconnected.", "info");
    return data;
  }

  if (!response.ok) {
    throw new Error(data.error || `Request failed with status ${response.status}`);
  }

  return data;
}

// ── Toast notification system ───────────────────────────────────────────────
function showToast(message, type = "info") {
  let container = document.getElementById("toast-container");
  if (!container) {
    container = document.createElement("div");
    container.id = "toast-container";
    container.className = "toast-container";
    document.body.appendChild(container);
  }
  const toast = document.createElement("div");
  toast.className = `toast-item ${type}`;
  const icons = { 
    success: '<i data-lucide="check-circle" style="color:var(--success);width:20px;height:20px"></i>', 
    error: '<i data-lucide="alert-circle" style="color:var(--danger);width:20px;height:20px"></i>', 
    info: '<i data-lucide="info" style="color:var(--accent);width:20px;height:20px"></i>' 
  };
  toast.innerHTML = `<span style="display:flex;align-items:center">${icons[type] || icons.info}</span><span style="flex:1">${message}</span>`;
  container.appendChild(toast);
  if (window.lucide) window.lucide.createIcons({ root: toast });
  setTimeout(() => {
    toast.style.animation = "slideOut 0.3s ease forwards";
    setTimeout(() => toast.remove(), 300);
  }, 3500);
}

// ── Avatar renderer ─────────────────────────────────────────────────────────
function renderAvatar(username, color, sizeClass = "") {
  const initial = (username || "?")[0].toUpperCase();
  return `<div class="avatar ${sizeClass}" style="background:${color || '#6C63FF'}">${initial}</div>`;
}

// ── Relative time ────────────────────────────────────────────────────────────
function timeAgo(isoString) {
  if (!isoString) return "";
  const diff = (Date.now() - new Date(isoString)) / 1000;
  if (diff < 60) return "just now";
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

// ── Guard: redirect to login if not authenticated ────────────────────────────
function requireLogin() {
  if (!getToken()) {
    window.location.href = "/";
  }
}

// ── XP display: format with sign ────────────────────────────────────────────
function fmtXP(n) {
  return n >= 0 ? `+${n}` : `${n}`;
}

// ── Loading state ─────────────────────────────────────────────────────────
function setButtonLoading(btn, isLoading, originalHtml = "") {
  if (!btn) return;
  if (isLoading) {
    btn.dataset.originalHtml = btn.innerHTML;
    btn.innerHTML = `<svg class="spinner" viewBox="0 0 50 50"><circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="5"></circle></svg>`;
    btn.disabled = true;
  } else {
    btn.innerHTML = originalHtml || btn.dataset.originalHtml;
    btn.disabled = false;
  }
}


// ── Push Subscription (shared across all pages) ──────────────────────────────

/**
 * Convert a URL-safe Base64 VAPID public key to a Uint8Array
 * required by PushManager.subscribe().
 */
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const rawData = window.atob(base64);
  const output = new Uint8Array(rawData.length);
  for (let i = 0; i < rawData.length; i++) output[i] = rawData.charCodeAt(i);
  return output;
}

/**
 * Subscribe (or re-subscribe) the current user to Web Push.
 * Returns true on success, false if permission denied or unsupported.
 * Safe to call multiple times — detects VAPID key mismatches and re-subscribes.
 */
async function subscribeToPush() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    console.warn("[Push] Not supported on this browser.");
    return false;
  }
  if (!getToken()) return false; // Must be logged in

  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") {
      console.warn("[Push] Permission not granted:", permission);
      return false;
    }

    const registration = await navigator.serviceWorker.ready;
    let subscription = await registration.pushManager.getSubscription();

    // Fetch current VAPID public key from server
    const res = await apiFetch("/api/users/vapid-key");
    if (!res || !res.vapid_public_key) throw new Error("Could not retrieve VAPID key.");
    const applicationServerKey = urlBase64ToUint8Array(res.vapid_public_key);

    if (subscription) {
      // Detect VAPID key mismatch — unsubscribe and re-subscribe with new key
      const existingKey = subscription.options?.applicationServerKey
        ? btoa(String.fromCharCode(...new Uint8Array(subscription.options.applicationServerKey)))
        : null;
      const newKeyBase64 = res.vapid_public_key.replace(/-/g, "+").replace(/_/g, "/");
      if (existingKey && existingKey !== newKeyBase64) {
        console.info("[Push] VAPID key mismatch — re-subscribing.");
        await subscription.unsubscribe();
        subscription = null;
      }
    }

    if (!subscription) {
      subscription = await registration.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey,
      });
    }

    // toJSON() gives { endpoint, keys } — safe to send
    await apiFetch("/api/users/me/push-subscription", "POST", subscription.toJSON());
    console.log("[Push] Subscription active.");
    return true;
  } catch (err) {
    console.error("[Push] Failed to subscribe:", err);
    return false;
  }
}
