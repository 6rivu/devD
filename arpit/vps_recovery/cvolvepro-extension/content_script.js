// content_script.js - LinkedIn job capture tailored to #job-details structure
(() => {
  const LOG = (s, ...args) => console.log('CVOLVEPRO:', s, ...args);

  LOG('content script injected on', location.href);

  const MIN_TEXT_LEN = 80;

  // Primary candidate selector (based on your pasted DOM)
  const PRIMARY_SELECTOR = '#job-details';
  // Fallback: any common LD/description containers
  const FALLBACK_SELECTORS = [
    '.jobs-unified-job-details__job-description',
    '.show-more-less-html__markup',
    '.jobs-description__content',
    '[data-test-job-description]',
    '.job-description'
  ];

  function cleanText(t) {
    // normalize whitespace and collapse multiple newlines
    return t
      .replace(/\r/g, ' ')
      .replace(/\n{3,}/g, '\n\n')
      .replace(/[ \t]{2,}/g, ' ')
      .trim();
  }

  function extractFromJobDetails(el) {
    if (!el) return { html: '', text: '' };

    // Prefer the inner content wrapper (your DOM shows <div class="mt4"> inside #job-details)
    const contentWrapper = el.querySelector('.mt4') || el;
    // clone to avoid modifying page
    const clone = contentWrapper.cloneNode(true);

    // Remove empty comments and script/style nodes
    clone.querySelectorAll('script, style').forEach(n => n.remove());

    // Convert to HTML string
    let html = clone.innerHTML || '';

    // Some LinkedIn markup wraps things in <span><p>..</p></span> — convert nested <p> into line breaks
    // (but keep <ul>/<li> intact)
    // We'll produce a clean text version by parsing HTML and using innerText
    let text = '';
    try {
      const tmp = document.createElement('div');
      tmp.innerHTML = html;
      text = tmp.innerText || '';
    } catch (e) {
      text = (contentWrapper.innerText || '');
    }

    text = cleanText(text);
    html = html.trim();

    return { html, text };
  }

  function tryFindJobElement() {
    // 1) primary id-based
    const primary = document.querySelector(PRIMARY_SELECTOR);
    if (primary && (primary.innerText || '').trim().length >= MIN_TEXT_LEN) {
      LOG('found job element by PRIMARY_SELECTOR', PRIMARY_SELECTOR, 'len=', (primary.innerText || '').trim().length);
      return primary;
    }
    // 2) fallback selectors
    for (const s of FALLBACK_SELECTORS) {
      try {
        const el = document.querySelector(s);
        if (el && (el.innerText || '').trim().length >= MIN_TEXT_LEN) {
          LOG('found job element by fallback selector', s, 'len=', (el.innerText || '').trim().length);
          return el;
        }
      } catch (e) {
        // ignore invalid selector errors
      }
    }
    // 3) scan for an element with id 'job-details' even if short (sometimes collapsed)
    const alt = document.getElementById('job-details');
    if (alt && (alt.innerText || '').trim().length > 20) {
      LOG('found alt #job-details with shorter length=', (alt.innerText || '').trim().length);
      return alt;
    }
    // 4) widest fallback: largest text container (last resort)
    const all = Array.from(document.querySelectorAll('div, section, article'));
    let best = null, bestLen = 0;
    for (const n of all) {
      try {
        const len = (n.innerText || '').trim().length;
        if (len > bestLen) { bestLen = len; best = n; }
      } catch (e) {}
    }
    if (best && bestLen >= MIN_TEXT_LEN) {
      LOG('found job element by scanning large nodes len=', bestLen);
      return best;
    }
    return null;
  }

  function persist(html, text) {
    try {
      chrome.storage.local.set({ latest_job_html: html, latest_job_text: text, latest_job_at: Date.now() }, () => {
        LOG('persisted latest_job_html/text to chrome.storage.local (textLen=', (text||'').length, ')');
      });
    } catch (e) {
      console.warn('CVOLVEPRO: storage set failed', e);
    }
  }

  function captureAndPersist() {
    const el = tryFindJobElement();
    const { html, text } = extractFromJobDetails(el);
    if (!text || text.length < MIN_TEXT_LEN) {
      LOG('capture attempt produced too-short text (len=', (text||'').length, ') — not persisting');
      return { html: '', text: '' };
    }
    persist(html, text);
    return { html, text };
  }

  // Add a visible floating button (idempotent)
  function addFloatingButton() {
    if (document.getElementById('cvolvepro-generate-btn')) return;
    const btn = document.createElement('button');
    btn.id = 'cvolvepro-generate-btn';
    btn.textContent = 'Generate CV';
    Object.assign(btn.style, {
      position: 'fixed', bottom: '18px', right: '18px', zIndex: 2147483647,
      padding: '10px 12px', borderRadius: '8px', backgroundColor: '#2274A5',
      color: '#fff', border: 'none', cursor: 'pointer', boxShadow: '0 3px 8px rgba(0,0,0,0.2)'
    });
    document.body.appendChild(btn);
    btn.addEventListener('click', () => {
      const { html, text } = captureAndPersist();
      if (!text) {
        alert('CVolve Pro: Could not capture the job description. Make sure the job details panel is open and try again.');
        return;
      }
      try { chrome.runtime.sendMessage({ action: 'JD_FOUND', jobDescriptionHtml: html, jobDescriptionText: text }); } catch (e) {}
      alert('Job details captured. Open the CVolve Pro popup to generate the CV.');
    });
  }

  // MutationObserver + polling to reliably detect when the job details are added/updated
  function watchForJobDetails() {
    let observer;
    function checkNow() {
      const el = tryFindJobElement();
      if (el) {
        addFloatingButton();
        const { html, text } = extractFromJobDetails(el);
        if (text && text.length >= MIN_TEXT_LEN) persist(html, text);
        return true;
      }
      return false;
    }

    if (checkNow()) return;

    try {
      observer = new MutationObserver((mutations, obs) => {
        if (checkNow()) obs.disconnect();
      });
      observer.observe(document, { childList: true, subtree: true });
    } catch (e) {
      LOG('observer creation failed', e);
    }

    // Poll fallback for cases where MutationObserver misses
    const start = Date.now();
    const POLL_MS = 800;
    const TIMEOUT_MS = 20_000;
    const id = setInterval(() => {
      if (checkNow() || Date.now() - start > TIMEOUT_MS) clearInterval(id);
    }, POLL_MS);
  }

  // SPA navigation watcher (LinkedIn uses pushState)
  function watchUrlChanges() {
    let last = location.href;
    const onChange = () => {
      if (location.href !== last) {
        LOG('URL changed', last, '->', location.href);
        last = location.href;
        setTimeout(watchForJobDetails, 400);
      }
    };
    const _push = history.pushState;
    history.pushState = function () { _push.apply(this, arguments); onChange(); };
    const _replace = history.replaceState;
    history.replaceState = function () { _replace.apply(this, arguments); onChange(); };
    window.addEventListener('popstate', onChange);
    // extra interval check as safety net
    setInterval(onChange, 1000);
  }

  // message listener for popup or background
  chrome.runtime.onMessage.addListener((msg, sender, sendResp) => {
    try {
      if (!msg || !msg.action) return;
      if (msg.action === 'GET_JOB_DESC') {
        const res = captureAndPersist();
        sendResp({ jobDescriptionHtml: res.html, jobDescription: res.text });
        return true; // keep channel open
      }
      if (msg.action === 'FORCE_CAPTURE_JD') {
        const res = captureAndPersist();
        sendResp({ ok: !!res.text });
        return true;
      }
    } catch (e) {
      console.error('CVOLVEPRO: onMessage error', e);
    }
  });

  // start watchers
  watchForJobDetails();
  watchUrlChanges();

  LOG('content script initialized — watching for #job-details and related containers');
})();