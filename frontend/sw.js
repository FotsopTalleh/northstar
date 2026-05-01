/**
 * sw.js — XPForge Service Worker
 *
 * Strategy:
 *  - Static assets (HTML/CSS/JS): Cache-first, update in background
 *  - GET /api/*: Network-first, fall back to cache
 *  - POST/PATCH /api/*: Network-first, queue to IndexedDB on failure
 *  - Background Sync: Replay queued mutations when back online
 *  - Push: Firebase Cloud Messaging (FCM) via importScripts
 */

// ── Firebase Messaging in SW ─────────────────────────────────────────────────
// Import Firebase compat scripts required for SW messaging
importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js");
importScripts("https://www.gstatic.com/firebasejs/10.12.0/firebase-messaging-compat.js");

// Firebase config is injected at SW install time via the FIREBASE_SW_CONFIG
// message, or read from the cache. We initialise lazily on first push.
let _firebaseInitialised = false;
let _messaging = null;

function initFirebaseIfNeeded(config) {
  if (_firebaseInitialised) return;
  try {
    firebase.initializeApp(config);
    _messaging = firebase.messaging();

    // Handle background FCM messages
    _messaging.onBackgroundMessage((payload) => {
      const { title, body, icon, url } = payload.data || payload.notification || {};
      self.registration.showNotification(title || "XPForge", {
        body: body || "New notification",
        icon: icon || "https://api.iconify.design/lucide/zap.svg?color=%236c63ff&width=192&height=192",
        data: { url: url || "/notifications.html" },
        vibrate: [100, 50, 100],
      });
    });

    _firebaseInitialised = true;
    console.log("[SW] Firebase Messaging initialised.");
  } catch (e) {
    console.error("[SW] Firebase init error:", e);
  }
}

// ── Cache config ─────────────────────────────────────────────────────────────
const CACHE_NAME = "xpforge-v8";
const OFFLINE_CACHE = "xpforge-offline-pages";

const STATIC_ASSETS = [
  "/",
  "/dashboard.html",
  "/leaderboard.html",
  "/clan.html",
  "/profile.html",
  "/about.html",
  "/notifications.html",
  "/reset-password.html",
  "/css/style.css",
  "/js/api.js",
  "/js/dashboard.js",
  "/js/leaderboard.js",
  "/js/clan.js",
  "/js/profile.js",
  "/js/notifications.js",
  "/js/offline-queue.js",
  "/manifest.json",
];

// ─── INSTALL ────────────────────────────────────────────
self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(STATIC_ASSETS))
      .then(() => self.skipWaiting())
  );
});

// ─── ACTIVATE ───────────────────────────────────────────
self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.filter(k => k !== CACHE_NAME && k !== OFFLINE_CACHE)
          .map(k => caches.delete(k))
      )
    ).then(() => self.clients.claim())
  );
});

// ─── MESSAGE (from page: pass Firebase config) ────────────────────────────────
self.addEventListener("message", (event) => {
  if (event.data && event.data.type === "FIREBASE_CONFIG") {
    initFirebaseIfNeeded(event.data.config);
  }
  if (event.data && event.data.type === "SYNC_COMPLETE") {
    // relay to all clients
  }
});

// ─── FETCH ──────────────────────────────────────────────
self.addEventListener("fetch", (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // Skip non-GET cross-origin requests (CDN etc.)
  if (url.origin !== self.location.origin && request.method !== "GET") return;

  // API mutations → network-first, queue offline
  if (url.pathname.startsWith("/api/") && request.method !== "GET") {
    event.respondWith(handleMutation(request));
    return;
  }

  // API GETs → network-first, cache fallback
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(networkFirst(request));
    return;
  }

  // Static assets → cache-first
  event.respondWith(cacheFirst(request));
});

// ─── STRATEGIES ─────────────────────────────────────────
async function cacheFirst(request) {
  const cached = await caches.match(request);
  if (cached) return cached;
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    return new Response("<h2>XPForge is offline</h2><p>Please check your connection.</p>",
      { headers: { "Content-Type": "text/html" } });
  }
}

async function networkFirst(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE_NAME);
      cache.put(request, response.clone());
    }
    return response;
  } catch {
    const cached = await caches.match(request);
    if (cached) return cached;
    return new Response(JSON.stringify({ error: "offline", cached: false }),
      { status: 503, headers: { "Content-Type": "application/json" } });
  }
}

async function handleMutation(request) {
  try {
    const response = await fetch(request.clone());
    return response;
  } catch {
    // Offline — store in IndexedDB queue via message to clients
    const body = await request.clone().json().catch(() => null);
    const token = request.headers.get("Authorization") || "";

    // Store the queued action
    await queueAction({
      url: request.url,
      method: request.method,
      body,
      token: token.replace("Bearer ", ""),
    });

    // Register a background sync
    self.registration.sync.register("xpforge-sync").catch(() => { });

    // Return optimistic 202 so the app can proceed
    return new Response(
      JSON.stringify({ offline: true, message: "Saved offline – will sync when connected." }),
      { status: 202, headers: { "Content-Type": "application/json" } }
    );
  }
}

// ─── BACKGROUND SYNC ────────────────────────────────────
self.addEventListener("sync", (event) => {
  if (event.tag === "xpforge-sync") {
    event.waitUntil(flushQueueSW());
  }
});

// ─── INDEXEDDB HELPERS (inline, SW scope) ───────────────
const IDB_NAME = "xpforge-offline";
const IDB_STORE = "queue";

function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = (e) => e.target.result.createObjectStore(IDB_STORE, { autoIncrement: true });
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

async function queueAction(action) {
  const db = await openIDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readwrite");
    tx.objectStore(IDB_STORE).add({ ...action, queuedAt: Date.now() });
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

async function flushQueueSW() {
  const db = await openIDB();
  const items = await new Promise((res, rej) => {
    const tx = db.transaction(IDB_STORE, "readonly");
    const req = tx.objectStore(IDB_STORE).getAll();
    req.onsuccess = () => res(req.result);
    req.onerror = (e) => rej(e.target.error);
  });
  const keys = await new Promise((res, rej) => {
    const tx = db.transaction(IDB_STORE, "readonly");
    const req = tx.objectStore(IDB_STORE).getAllKeys();
    req.onsuccess = () => res(req.result);
    req.onerror = (e) => rej(e.target.error);
  });

  for (let i = 0; i < items.length; i++) {
    const { url, method, body, token } = items[i];
    try {
      const res = await fetch(url, {
        method,
        headers: {
          "Content-Type": "application/json",
          ...(token ? { "Authorization": `Bearer ${token}` } : {}),
        },
        body: body ? JSON.stringify(body) : undefined,
      });
      if (res.ok) {
        const del = db.transaction(IDB_STORE, "readwrite");
        del.objectStore(IDB_STORE).delete(keys[i]);
      }
    } catch (_) { /* still offline */ }
  }

  // Notify all open clients to refresh their UI
  const clients = await self.clients.matchAll({ type: "window" });
  clients.forEach(c => c.postMessage({ type: "SYNC_COMPLETE" }));
}

// ─── PUSH NOTIFICATIONS ─────────────────────────────────
// Handled by Firebase Messaging SDK (onBackgroundMessage above).
// This fallback handles any raw push events not caught by Firebase.
self.addEventListener("push", (event) => {
  // Firebase Messaging intercepts most push events.
  // This is a safety net for non-FCM pushes or if Firebase is not yet initialised.
  if (_firebaseInitialised) return;

  let data = {};
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data = { body: event.data.text() };
    }
  }

  const title = data.title || "XPForge";
  const options = {
    body: data.body || "New notification",
    icon: data.icon || "https://api.iconify.design/lucide/zap.svg?color=%236c63ff&width=192&height=192",
    data: {
      url: data.url || "/notifications.html"
    },
    vibrate: [100, 50, 100]
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener("notificationclick", (event) => {
  event.notification.close();
  
  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : "/notifications.html";

  event.waitUntil(
    self.clients.matchAll({ type: "window", includeUncontrolled: true }).then((clientList) => {
      // If a window tab is already open, focus it and navigate
      for (let i = 0; i < clientList.length; i++) {
        const client = clientList[i];
        if (client.url.includes(self.location.origin) && "focus" in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Otherwise open a new window
      if (self.clients.openWindow) {
        return self.clients.openWindow(targetUrl);
      }
    })
  );
});
