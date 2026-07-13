// background.js - improved durable auth/generate + resume persistence
console.log('CVolve Pro background service worker loaded (updated)');

const API_BASE = 'https://cvolvepro.com';
const API_GENERATE_URL = API_BASE + '/api/generate_cv';
const API_GENERATE_CL_URL = API_BASE + '/api/generate_cl';
const FETCH_TIMEOUT_MS = 90_000; // 90s

// Storage helpers (promisified)
function getStorage(keys) {
  return new Promise((resolve) => chrome.storage.local.get(keys, (items) => resolve(items || {})));
}
function setStorage(obj) {
  return new Promise((resolve) => chrome.storage.local.set(obj, () => resolve()));
}
function removeStorage(keys) {
  return new Promise((resolve) => chrome.storage.local.remove(keys, () => resolve()));
}

function makeOk(payload) { return { ok: true, payload }; }
function makeErr(message, payload = null, status = null) { return { ok: false, error: message || 'error', payload, status }; }

async function fetchWithTimeout(url, opts = {}, timeoutMs = FETCH_TIMEOUT_MS) {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    const resp = await fetch(url, { ...opts, signal: controller.signal });
    clearTimeout(id);
    return resp;
  } catch (e) {
    clearTimeout(id);
    throw e;
  }
}

function isGetTokenAction(a) { return a === 'GET_AUTH_TOKEN' || a === 'GET_TOKEN' || a === 'GET_TOKEN_ACTION' || a === 'GET_TOKEN'; }
function isSaveTokenAction(a) { return a === 'SAVE_TOKEN' || a === 'SAVE_TOKEN_ACTION' || a === 'SAVE_TOKEN'; }

// in-memory resume (short-lived but useful to avoid race on popup close)
let inMemoryResume = { resumeBase64: null, resumeName: null };

chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  (async () => {
    try {
      if (!message || !message.action) {
        sendResponse(makeErr('Invalid message'));
        return;
      }
      const action = message.action;

      // GET token / user
      if (isGetTokenAction(action)) {
        const stored = await getStorage(['authToken','auth_user','auth_expires','credits']);
        sendResponse(Object.assign({ ok: true }, {
          token: stored.authToken || null,
          auth_user: stored.auth_user || null,
          auth_expires: stored.auth_expires || null,
          credits: stored.credits ?? null
        }));
        return;
      }

      // SAVE token (background is durable writer)
      if (isSaveTokenAction(action)) {
        const t = message.token || null;
        const user = message.user || null;
        const toStore = {};
        if (t) toStore.authToken = t;
        if (user) toStore.auth_user = user;
        try {
          await setStorage(toStore);
          const after = await getStorage(['authToken','auth_user','credits']);
          sendResponse(makeOk({ saved: !!t, stored: after }));
        } catch (err) {
          console.error('background: SAVE_TOKEN storage error', err);
          sendResponse(makeErr('Failed to persist token', null, 500));
        }
        return;
      }

      // CLEAR auth
      if (action === 'CLEAR_AUTH' || action === 'CLEAR_AUTH_TOKEN') {
        try {
          await removeStorage(['authToken','auth_user','auth_expires','credits']);
          sendResponse(makeOk({ cleared: true }));
        } catch (err) {
          console.error('background: CLEAR_AUTH error', err);
          sendResponse(makeErr('Failed to clear auth', null, 500));
        }
        return;
      }

      // Resume persistence API for popup
      if (action === 'SAVE_RESUME') {
        inMemoryResume.resumeBase64 = message.resumeBase64 || null;
        inMemoryResume.resumeName = message.resumeName || null;
        // also persist to storage (durable)
        try {
          await setStorage({ resumeBase64: inMemoryResume.resumeBase64, resumeName: inMemoryResume.resumeName });
        } catch (e) {
          console.warn('background: failed to persist resume to storage', e);
        }
        sendResponse(makeOk({ saved: !!inMemoryResume.resumeBase64 }));
        return;
      }

      if (action === 'CLEAR_RESUME') {
        inMemoryResume = { resumeBase64: null, resumeName: null };
        try { await removeStorage(['resumeBase64','resumeName']); } catch (e) {}
        sendResponse(makeOk({ cleared: true }));
        return;
      }

      if (action === 'GET_RESUME') {
        if (inMemoryResume.resumeBase64) {
          sendResponse(makeOk({ resumeBase64: inMemoryResume.resumeBase64, resumeName: inMemoryResume.resumeName }));
          return;
        } else {
          const stored = await getStorage(['resumeBase64','resumeName']);
          sendResponse(makeOk({ resumeBase64: stored.resumeBase64 || null, resumeName: stored.resumeName || null }));
          return;
        }
      }

      // GENERATE_CV_AUTH
      if (action === 'GENERATE_CV_AUTH' || action === 'GENERATE_CV') {
        let token = message.token || null;
        if (!token) {
          const stored = await getStorage(['authToken']);
          token = stored.authToken || null;
        }
        if (!token) {
          sendResponse(makeErr('Missing auth token', null, 401));
          return;
        }

        const payload = message.payload || {};
        if (!payload.job_description || typeof payload.job_description !== 'string' || payload.job_description.trim().length < 10) {
          sendResponse(makeErr('Missing or too short job_description', null, 400));
          return;
        }

        if (payload.resume_base64 && payload.resume_base64.length > (12 * 1024 * 1024)) {
          sendResponse(makeErr('Resume too large for browser upload (max ~12MB base64).', null, 413));
          return;
        }

        let fetchResp;
        try {
          fetchResp = await fetchWithTimeout(API_GENERATE_URL, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
              'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify(payload)
          }, FETCH_TIMEOUT_MS);
        } catch (netErr) {
          console.error('background: Network error contacting generate endpoint', netErr);
          sendResponse(makeErr('Network error contacting server: ' + (netErr.message || netErr), null, 0));
          return;
        }

        const rawText = await fetchResp.text().catch(() => null);
        let json = null;
        try {
          json = rawText ? JSON.parse(rawText) : null;
        } catch (err) {
          json = null;
        }

        if (!fetchResp.ok) {
          const messageText = (json && (json.detail || json.error || json.message)) ? (json.detail || json.error || json.message) : (rawText || fetchResp.statusText);
          console.warn('background: server error', fetchResp.status, messageText);
          console.error("SERVER RAW RESPONSE:", rawText);
          sendResponse(makeErr(messageText || 'Server error', json, fetchResp.status));
          return;
        }

        sendResponse(makeOk(json || {}));
        return;
      }

      // GENERATE_CL_AUTH
      if (action === 'GENERATE_CL_AUTH' || action === 'GENERATE_CL') {
        let token = message.token || null;
        if (!token) {
          const stored = await getStorage(['authToken']);
          token = stored.authToken || null;
        }
        if (!token) { sendResponse(makeErr('Missing auth token', null, 401)); return; }

        const payload = message.payload || {};
        if (!payload.job_description || typeof payload.job_description !== 'string' || payload.job_description.trim().length < 10) {
          sendResponse(makeErr('Missing or too short job_description', null, 400));
          return;
        }

        if (payload.resume_base64 && payload.resume_base64.length > (12 * 1024 * 1024)) {
          sendResponse(makeErr('Resume too large for browser upload (max ~12MB base64).', null, 413));
          return;
        }

        let fetchResp;
        try {
          fetchResp = await fetchWithTimeout(API_GENERATE_CL_URL, {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'Accept': 'application/json',
              'Authorization': 'Bearer ' + token
            },
            body: JSON.stringify(payload)
          }, FETCH_TIMEOUT_MS);
        } catch (netErr) {
          console.error('background: Network error contacting generate_cl endpoint', netErr);
          sendResponse(makeErr('Network error contacting server: ' + (netErr.message || netErr), null, 0));
          return;
        }

        const rawText = await fetchResp.text().catch(() => null);
        let json = null;
        try { json = rawText ? JSON.parse(rawText) : null; } catch (err) { json = null; }

        if (!fetchResp.ok) {
          const messageText = (json && (json.detail || json.error || json.message)) ? (json.detail || json.error || json.message) : (rawText || fetchResp.statusText);
          console.warn('background: server error (cl)', fetchResp.status, messageText);
          console.error("SERVER RAW RESPONSE:", rawText);
          sendResponse(makeErr(messageText || 'Server error', json, fetchResp.status));
          return;
        }

        // success: return JSON (payload will be forwarded to popup)
        sendResponse(makeOk(json || {}));
        return;
      }


      sendResponse(makeErr('Unknown action'));
    } catch (ex) {
      console.error('background onMessage error', ex);
      try { sendResponse(makeErr('Background internal error: ' + (ex.message || ex))); } catch (e) {}
    }
  })();
  return true; // async response
});

chrome.runtime.onInstalled.addListener((details) => {
  console.debug('CVolve Pro extension installed/updated', details);
});