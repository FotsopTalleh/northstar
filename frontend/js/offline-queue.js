/**
 * offline-queue.js
 * IndexedDB-backed queue for storing API mutations that failed due to being offline.
 * Used by both the main app (to enqueue) and the service worker (to flush).
 */

const DB_NAME = "xpforge-offline";
const STORE   = "queue";
const DB_VER  = 1;

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VER);
    req.onupgradeneeded = (e) => {
      e.target.result.createObjectStore(STORE, { autoIncrement: true });
    };
    req.onsuccess = (e) => resolve(e.target.result);
    req.onerror   = (e) => reject(e.target.error);
  });
}

/**
 * Enqueue an API action to replay later.
 * @param {{ url: string, method: string, body: any, token: string }} action
 */
async function enqueueAction(action) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).add({ ...action, queuedAt: Date.now() });
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

/**
 * Return all queued actions.
 */
async function getAllQueued() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

/**
 * Return all keys in the queue.
 */
async function getAllKeys() {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readonly");
    const req = tx.objectStore(STORE).getAllKeys();
    req.onsuccess = () => resolve(req.result);
    req.onerror = (e) => reject(e.target.error);
  });
}

/**
 * Remove a queued action by its IDB key.
 */
async function removeQueued(key) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(STORE, "readwrite");
    tx.objectStore(STORE).delete(key);
    tx.oncomplete = resolve;
    tx.onerror = (e) => reject(e.target.error);
  });
}

/**
 * Replay all queued actions against the server.
 * Called by the service worker on Background Sync, or app on reconnect.
 */
async function flushQueue() {
  const items = await getAllQueued();
  const keys  = await getAllKeys();
  let replayed = 0;

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
        await removeQueued(keys[i]);
        replayed++;
      }
    } catch (_) {
      // Network still down — leave in queue
    }
  }
  return replayed;
}
