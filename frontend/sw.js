/**
 * sw.js — XPForge Service Worker
 *
 * Strategy:
 *  - Static assets (HTML/CSS/JS): Cache-first, update in background
 *  - GET /api/*: Network-first, fall back to cache
 *  - POST/PATCH /api/*: Network-first, queue to IndexedDB on failure
 *  - Background Sync: Replay queued mutations when back online
 */

const CACHE_NAME    = "xpforge-v2";
const OFFLINE_CACHE = "xpforge-offline-pages";

const STATIC_ASSETS = [
  "/",
  "/dashboard.html",
  "/leaderboard.html",
  "/clan.html",
  "/profile.html",
  "/about.html",
  "/notifications.html",
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
    self.registration.sync.register("xpforge-sync").catch(() => {});

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
const IDB_NAME  = "xpforge-offline";
const IDB_STORE = "queue";

function openIDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = (e) => e.target.result.createObjectStore(IDB_STORE, { autoIncrement: true });
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
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
  const db   = await openIDB();
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
