// popup.js - updated: uses chrome.tabs.sendMessage + scripting.executeScript fallback
document.addEventListener('DOMContentLoaded', () => {
  // Elements (same as before)
  const signinToggle = document.getElementById('signinToggle');
  const signinChevron = document.getElementById('signinChevron');
  const signinForm = document.getElementById('signinForm');
  const loginBtn = document.getElementById('loginBtn');
  const guestBtn = document.getElementById('guestBtn');
  const logoutBtn = document.getElementById('logoutBtn');
  const buyBtn = document.getElementById('buyBtn');
  const signedInBox = document.getElementById('signedInBox');

  const emailInput = document.getElementById('email');
  const passwordInput = document.getElementById('password');
  const userEmailEl = document.getElementById('userEmail');
  const creditsEl = document.getElementById('credits');

  const resumeUpload = document.getElementById('resumeUpload');
  const resumeNameEl = document.getElementById('resumeName');

  const jobDescEl = document.getElementById('jobDesc');
  const targetEl = document.getElementById('targetMatch');
  const genBtn = document.getElementById('generateBtn');
  const statusEl = document.getElementById('status');

  const modelSelect = document.getElementById('modelSelect');
  const languageSelect = document.getElementById('languageSelect');

  const openOptions = document.getElementById('openOptions');
  const openSite = document.getElementById('openSite');

  // --- NEW: CL UI elements ---
  const genCLBtn = document.getElementById('generateCLBtn');
  const clWrapper = document.getElementById('clWrapper');
  const coverLetterPreview = document.getElementById('coverLetterPreview');
  const saveCLBtn = document.getElementById('saveCLBtn');
  const downloadCLBtn = document.getElementById('downloadCLBtn');

  // Actions
  const ACTION_GET_TOKEN = 'GET_AUTH_TOKEN';
  const ACTION_SAVE_TOKEN = 'SAVE_TOKEN';
  const ACTION_CLEAR_AUTH = 'CLEAR_AUTH';
  const ACTION_GENERATE = 'GENERATE_CV_AUTH';
  const ACTION_GENERATE_CL = 'GENERATE_CL_AUTH';

  const API_BASE = 'https://cvolvepro.com';

  function setStatus(txt, isError = false) {
    if (!statusEl) return;
    statusEl.textContent = txt || '';
    statusEl.style.color = isError ? '#c00' : '#333';
  }

  function showSignedOutUI() {
    if (signinForm) signinForm.style.display = 'none';
    if (signinChevron) signinChevron.textContent = '▾';
    if (signinToggle) signinToggle.style.display = '';
    if (signedInBox) signedInBox.style.display = 'none';
    if (userEmailEl) userEmailEl.textContent = '-';
    if (creditsEl) creditsEl.textContent = '-';
  }
  function showSignedInUI(email, credits) {
    if (signinToggle) signinToggle.style.display = 'none';
    if (signinForm) signinForm.style.display = 'none';
    if (signedInBox) signedInBox.style.display = 'block';
    if (userEmailEl) userEmailEl.textContent = email || '-';
    if (creditsEl) creditsEl.textContent = (typeof credits === 'number') ? credits : (credits ?? '…');
  }

  // init dropdowns (if any)
  (function initModelLanguage(){
    if (modelSelect && modelSelect.children.length === 0) {
      const opts = [{ v: 'premium', t: 'Premium' }, { v: 'premium_classic', t: 'Premium Classic' }];
      opts.forEach(o => { const el = document.createElement('option'); el.value = o.v; el.text = o.t; modelSelect.appendChild(el); });
    }
    if (languageSelect && languageSelect.children.length === 0) {
      const langs = [{ v: 'English', t: 'English' }, { v: 'Hindi', t: 'Hindi' }, { v: 'Spanish', t: 'Spanish' }];
      langs.forEach(l => { const el = document.createElement('option'); el.value = l.v; el.text = l.t; languageSelect.appendChild(el); });
    }
  })();

  if (signinToggle) {
    signinToggle.addEventListener('click', () => {
      const visible = signinForm && signinForm.style.display === 'block';
      if (signinForm) signinForm.style.display = visible ? 'none' : 'block';
      if (signinChevron) signinChevron.textContent = visible ? '▾' : '▴';
    });
  }

  // --- NEW: rehydrate persisted resume and JD on popup open ---
  function populateResumeFromBgOrStore() {
    try {
      chrome.runtime.sendMessage({ action: 'GET_RESUME' }, (resp) => {
        if (chrome.runtime.lastError) {
          chrome.storage.local.get(['resumeBase64','resumeName'], (items) => {
            if (items && items.resumeName && resumeNameEl) resumeNameEl.textContent = '📄 ' + items.resumeName;
          });
          return;
        }
        if (resp && resp.ok && resp.resumeName) {
          if (resumeNameEl) resumeNameEl.textContent = '📄 ' + resp.resumeName;
          if (resp.resumeBase64) chrome.storage.local.set({ resumeBase64: resp.resumeBase64, resumeName: resp.resumeName }, () => {});
        } else {
          chrome.storage.local.get(['resumeBase64','resumeName'], (items) => {
            if (items && items.resumeName && resumeNameEl) resumeNameEl.textContent = '📄 ' + items.resumeName;
          });
        }
      });
    } catch (e) {
      chrome.storage.local.get(['resumeBase64','resumeName'], (items) => {
        if (items && items.resumeName && resumeNameEl) resumeNameEl.textContent = '📄 ' + items.resumeName;
      });
    }
  }

  //
  // NEW: Robust content script messaging helpers
  //

  // Ask active tab's content script for JD (preferred)
  function askActiveTabForJD(callback) {
    try {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (!tabs || !tabs.length) {
          callback(null);
          return;
        }
        const tabId = tabs[0].id;
        chrome.tabs.sendMessage(tabId, { action: 'GET_JOB_DESC' }, (resp) => {
          if (chrome.runtime.lastError) {
            console.warn('askActiveTabForJD runtime.lastError', chrome.runtime.lastError.message);
            callback(null);
            return;
          }
          callback(resp || null);
        });
      });
    } catch (e) {
      console.error('askActiveTabForJD error', e);
      callback(null);
    }
  }

  // If content script doesn't respond, inject a one-off capture to read #job-details directly
  function captureViaExecuteScript(cb) {
    try {
      chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
        if (!tabs || !tabs.length) { cb(null); return; }
        const tabId = tabs[0].id;
        // execute a function inside the page to capture job description
        chrome.scripting.executeScript({
          target: { tabId: tabId },
          func: () => {
            try {
              const sel = document.getElementById('job-details') ||
                          document.querySelector('.jobs-unified-job-details__job-description') ||
                          document.querySelector('.show-more-less-html__markup') ||
                          document.querySelector('[data-test-job-description]') ||
                          document.querySelector('.jobs-description__content');
              if (!sel) return { html: '', text: '' };
              const html = sel.innerHTML || '';
              const text = (sel.innerText || '').trim();
              return { html, text };
            } catch (e) {
              return { html: '', text: '' };
            }
          }
        }, (injectionResults) => {
          if (chrome.runtime.lastError) {
            console.warn('captureViaExecuteScript lastError', chrome.runtime.lastError.message);
            cb(null); return;
          }
          if (!injectionResults || !injectionResults[0] || !injectionResults[0].result) { cb(null); return; }
          cb(injectionResults[0].result);
        });
      });
    } catch (e) {
      console.error('captureViaExecuteScript err', e);
      cb(null);
    }
  }

  // New: unified getter: try tab message -> executeScript -> storage fallback
  function getJobFromContentScript(cb) {
    askActiveTabForJD((resp) => {
      if (resp && (resp.jobDescription || resp.jobDescriptionText || resp.jobDescriptionHtml)) {
        return cb(resp.jobDescription || resp.jobDescriptionText || resp.jobDescriptionHtml || '');
      }
      // try injection fallback
      captureViaExecuteScript((oneOffResp) => {
        if (oneOffResp && oneOffResp.text && oneOffResp.text.trim().length > 20) {
          // persist for later
          chrome.storage.local.set({ latest_job_text: oneOffResp.text, latest_job_html: oneOffResp.html, latest_job_at: Date.now() }, () => {});
          return cb(oneOffResp.text || '');
        }
        // last fallback: storage
        chrome.storage.local.get(['latest_job_text','latest_job_html'], (items) => {
          const txt = items && (items.latest_job_text || items.latest_job_html);
          cb(txt || '');
        });
      });
    });
  }

  // Modified tryAutoCaptureJD: uses new robust getter
  function tryAutoCaptureJD() {
    function setJDFromResp(resp) {
      if (!resp) return false;
      try {
        const html = resp.jobDescriptionHtml || resp.jobDescription || resp.jobDescriptionText || '';
        if (html && html.trim().length > 20 && jobDescEl) {
          let plain = html;
          try { const parser = new DOMParser(); plain = parser.parseFromString(html, 'text/html').body.innerText; } catch (e) {}
          if (plain && plain.trim().length > 20) {
            jobDescEl.value = plain.trim();
            return true;
          }
        }
      } catch (e) {}
      return false;
    }

    // Use the robust getter
    getJobFromContentScript((textOrHtml) => {
      if (!textOrHtml) return;
      let plain = textOrHtml;
      // If it looks like HTML, try to parse
      if (/<[a-z][\s\S]*>/i.test(plain)) {
        try { const parser = new DOMParser(); plain = parser.parseFromString(plain, 'text/html').body.innerText; } catch (e) {}
      }
      if (plain && plain.trim().length > 20 && jobDescEl) jobDescEl.value = plain.trim();
    });
  }

  // Keep popup synced with storage changes (including resume name)
  if (chrome && chrome.storage && chrome.storage.onChanged) {
    chrome.storage.onChanged.addListener((changes, area) => {
      if (area !== 'local') return;
      if (changes.auth_user) {
        const user = changes.auth_user.newValue || {};
        showSignedInUI(user.email || user.name || 'user', changes.credits ? changes.credits.newValue : '…');
      }
      if (changes.authToken && !changes.authToken.newValue) showSignedOutUI();
      if (changes.resumeName && resumeNameEl) resumeNameEl.textContent = '📄 ' + (changes.resumeName.newValue || '');
      if (changes.credits && creditsEl) creditsEl.textContent = changes.credits.newValue;
    });
  }

  // On startup: fetch token & rehydrate resume/JD
  function refreshAuthFromBg() {
    return new Promise((resolve) => {
      try {
        chrome.runtime.sendMessage({ action: ACTION_GET_TOKEN }, (resp) => {
          if (chrome.runtime.lastError) {
            chrome.storage.local.get(['authToken','auth_user','credits','resumeName'], (items) => {
              if (items && items.authToken) {
                showSignedInUI((items.auth_user && (items.auth_user.email || items.auth_user.name)) || '…', items.credits ?? '…');
              } else showSignedOutUI();
              if (items.resumeName && resumeNameEl) resumeNameEl.textContent = '📄 ' + items.resumeName;
              resolve(items);
            });
            return;
          }
          if (resp && resp.ok) {
            if (resp.auth_user) {
              chrome.storage.local.set({ auth_user: resp.auth_user }, () => {});
              showSignedInUI(resp.auth_user.email || resp.auth_user.name || 'user', resp.credits ?? '…');
            } else {
              if (resp.token) {
                showSignedInUI('…', resp.credits ?? '…');
                chrome.storage.local.set({ authToken: resp.token }, () => {});
              } else showSignedOutUI();
            }
            if (resp.auth_expires) chrome.storage.local.set({ auth_expires: resp.auth_expires });
            if (typeof resp.credits === 'number') chrome.storage.local.set({ credits: resp.credits });
            resolve(resp);
          } else {
            showSignedOutUI();
            resolve(null);
          }
        });
      } catch (e) {
        showSignedOutUI();
        resolve(null);
      }
    });
  }

  refreshAuthFromBg().then(() => {
    // rehydrate resume and JD after auth refresh
    populateResumeFromBgOrStore();
    tryAutoCaptureJD();
  }).catch(() => { populateResumeFromBgOrStore(); tryAutoCaptureJD(); });

  // Login flow (unchanged)
  if (loginBtn) {
    loginBtn.addEventListener('click', async () => {
      const email = (emailInput && emailInput.value || '').trim();
      const password = (passwordInput && passwordInput.value || '').trim();
      if (!email || !password) { setStatus('Enter email and password.', true); return; }
      setStatus('Signing in…');
      try {
        const resp = await fetch(API_BASE + '/api/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
          body: JSON.stringify({ email, password })
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          const detail = data && (data.detail || data.error || data.message) ? (data.detail || data.error || data.message) : (resp.statusText || 'Invalid credentials');
          setStatus('Sign in failed: ' + detail, true); return;
        }
        const token = data.token || data.access_token;
        if (!token) { setStatus('Sign in succeeded but server returned no token.', true); return; }
        const user = { email: data.email || email, name: data.name || null };

        chrome.runtime.sendMessage({ action: ACTION_SAVE_TOKEN, token, user }, (bgResp) => {
          if (chrome.runtime.lastError) {
            chrome.storage.local.set({ authToken: token, auth_user: user, credits: (typeof data.credits === 'number') ? data.credits : null }, () => {
              setStatus('Signed in (local fallback).');
              showSignedInUI(user.email, typeof data.credits === 'number' ? data.credits : '…');
            });
            return;
          }
          if (bgResp && bgResp.ok) {
            chrome.storage.local.set({ authToken: token, auth_user: user, auth_expires: data.expires_at || data.expires || null, credits: (typeof data.credits === 'number') ? data.credits : null }, () => {
              setStatus('Signed in.' );
              showSignedInUI(user.email, typeof data.credits === 'number' ? data.credits : '…');
            });
          } else {
            chrome.storage.local.set({ authToken: token, auth_user: user }, () => {
              setStatus('Signed in (partial). Background failed to persist token.' );
              showSignedInUI(user.email, typeof data.credits === 'number' ? data.credits : '…');
            });
          }
        });
      } catch (err) {
        console.error('login err', err);
        setStatus('Sign in error: ' + (err.message || err), true);
      }
    });
  }

  if (guestBtn) guestBtn.addEventListener('click', () => { showSignedInUI('guest', 0); setStatus('Guest mode (no credits). Sign in for full features.'); });

  if (logoutBtn) {
    logoutBtn.addEventListener('click', () => {
      if (!confirm('Sign out from CVolve Pro?')) return;
      chrome.runtime.sendMessage({ action: ACTION_CLEAR_AUTH }, (resp) => {
        chrome.storage.local.remove(['authToken','auth_user','auth_expires','credits'], () => {
          showSignedOutUI();
          setStatus('Signed out.');
        });
      });
    });
  }

  if (buyBtn) buyBtn.addEventListener('click', () => { window.open(API_BASE, '_blank'); });

  // Resume upload -> store base64 + notify background
  if (resumeUpload) {
    resumeUpload.addEventListener('change', () => {
      const file = resumeUpload.files && resumeUpload.files[0];
      if (!file) {
        if (resumeNameEl) resumeNameEl.textContent = '';
        chrome.storage.local.remove(['resumeBase64','resumeName']);
        try { chrome.runtime.sendMessage({ action: 'CLEAR_RESUME' }, () => {}); } catch (e) {}
        return;
      }
      if (file.size > 10 * 1024 * 1024) { setStatus('File too large (max 10 MB).', true); resumeUpload.value = ''; return; }
      if (resumeNameEl) resumeNameEl.textContent = '📄 ' + file.name;

      const reader = new FileReader();
      reader.onload = () => {
        const dataUrl = reader.result || '';
        const base64 = dataUrl.split(',')[1] || '';
        chrome.storage.local.set({ resumeBase64: base64, resumeName: file.name }, () => {
          setStatus('Resume saved for upload.');
          // notify background for faster access
          try { chrome.runtime.sendMessage({ action: 'SAVE_RESUME', resumeBase64: base64, resumeName: file.name }, () => {}); } catch (e) {}
        });
      };
      reader.onerror = (e) => { console.error('file read error', e); setStatus('Failed to read file.', true); };
      reader.readAsDataURL(file);
    });
  }

  // --- NEW: Cover letter UI helpers ---
  function showCoverLetterUI(text) {
    try {
      // convert pipes to newlines for preview
      let previewText = (text || '').replace(/\s*\|\s*/g, '\n');
      if (coverLetterPreview) coverLetterPreview.value = previewText || '';
      if (clWrapper) clWrapper.style.display = (previewText && previewText.length) ? 'block' : 'none';
    } catch (e) { console.error('showCoverLetterUI err', e); }
  }

  if (saveCLBtn) {
    saveCLBtn.addEventListener('click', async () => {
      const txt = coverLetterPreview && coverLetterPreview.value;
      if (!txt || txt.trim().length < 10) { setStatus('No cover letter to copy.', true); return; }
      try {
        await navigator.clipboard.writeText(txt);
        setStatus('Cover letter copied to clipboard.');
      } catch (e) {
        console.error('clipboard err', e);
        setStatus('Copy failed — select and copy manually.', true);
      }
    });
  }

  if (downloadCLBtn) {
    downloadCLBtn.addEventListener('click', () => {
      const txt = coverLetterPreview && coverLetterPreview.value;
      if (!txt || txt.trim().length < 10) { setStatus('No cover letter to download.', true); return; }

      // Prefer server-generated docx if available in storage
      chrome.storage.local.get(['last_cl_docx','last_cl_ext','last_cl_filename'], (items) => {
        if (items && items.last_cl_docx) {
          const b64 = items.last_cl_docx;
          const filename = items.last_cl_filename || `cvolvepro_coverletter_${Date.now()}.docx`;
          try {
            const blob = base64ToBlob(b64, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
            const url = URL.createObjectURL(blob);
            chrome.downloads.download({ url, filename, saveAs: true }, () => {
              setStatus('Cover letter download started (server docx).');
            });
            return;
          } catch (err) {
            console.error('download server docx err', err);
            // fallback to text docx below
          }
        }

        // Fallback: create simple text-based file (not a true docx) — but name as .docx so user can open in Word (Word will usually import plain text)
        try {
          const blob = new Blob([txt], { type: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document' });
          const filename = `cvolvepro_coverletter_${Date.now()}.docx`;
          const url = URL.createObjectURL(blob);
          chrome.downloads.download({ url, filename, saveAs: true }, () => {
            setStatus('Cover letter download started.');
          });
        } catch (e) {
          console.error('fallback download err', e);
          setStatus('Failed to prepare cover letter download.', true);
        }
      });
    });
  }

  // Prevent double click / concurrent generates
  let generating = false;

  // --- NEW: Generate Cover Letter handler ---
  if (genCLBtn) {
    genCLBtn.addEventListener('click', () => {
      setStatus('Preparing cover letter request…');

      const typedJD = (jobDescEl && jobDescEl.value || '').trim();
      function proceedWithJD(jd) {
        const jdEffective = (typedJD && typedJD.length > 20) ? typedJD : (jd || '');
        if (!jdEffective || jdEffective.length < 20) { setStatus('Please paste a job description or open a job posting page.', true); return; }

        setStatus('Sending cover letter request to server…');

        chrome.storage.local.get(['authToken','resumeBase64','resumeName'], (items) => {
          const storedToken = items && items.authToken;
          const payload = {
            job_description: jdEffective,
            language: (languageSelect && languageSelect.value) ? languageSelect.value : 'English',
            tone: 'professional'
          };

          if (items && items.resumeBase64) {
            payload.resume_base64 = items.resumeBase64;
            payload.resume_filename = items.resumeName || 'resume.pdf';
          }

          payload.include_fullname = true;

          function callGenerateCL(token) {
            if (!token) { setStatus('Please sign in first.', true); return; }
            chrome.runtime.sendMessage({ action: ACTION_GENERATE_CL, token, payload }, (resp) => {
              if (chrome.runtime.lastError) { console.error('runtime sendMessage err', chrome.runtime.lastError); setStatus('Background error: ' + (chrome.runtime.lastError.message || 'unknown'), true); return; }
              if (!resp) { setStatus('No response from background.', true); return; }
              if (!resp.ok) { setStatus('Cover letter generation failed: ' + (resp.error || JSON.stringify(resp.payload) || 'Unknown'), true); return; }

              const json = resp.payload || {};
              // Extract best text key
              const clText = json.cover_letter || json.cl_text || json.coverletter || (json.data && json.data.cover_letter) || null;

              // if server returned docx_base64, store it for download
              if (json.docx_base64) {
                // store in local storage for later download
                chrome.storage.local.set({
                  last_cl_docx: json.docx_base64,
                  last_cl_ext: json.file_ext || 'docx',
                  last_cl_filename: `cvolvepro_coverletter_${Date.now()}.docx`
                }, () => {});
              } else {
                // clear previous server docx if any
                chrome.storage.local.remove(['last_cl_docx','last_cl_ext','last_cl_filename'], () => {});
              }

              if (clText) {
                // convert any pipes to newlines for preview
                const preview = (clText || '').replace(/\s*\|\s*/g, '\n');
                showCoverLetterUI(preview);
                setStatus('Cover letter ready.');
                if (typeof json.credits === 'number') { creditsEl.textContent = json.credits; chrome.storage.local.set({ credits: json.credits }); }
              } else {
                setStatus('No cover letter text returned by server.', true);
              }
            });
          }

          if (storedToken) callGenerateCL(storedToken);
          else chrome.runtime.sendMessage({ action: ACTION_GET_TOKEN }, (resp) => {
            const tokenFromBg = resp && (resp.token || resp.authToken);
            if (tokenFromBg) { chrome.storage.local.set({ authToken: tokenFromBg }, () => callGenerateCL(tokenFromBg)); }
            else setStatus('Please sign in first.', true);
          });
        });
      }

      const typed = (jobDescEl && jobDescEl.value || '').trim();
      if (typed && typed.length > 20) proceedWithJD(typed);
      else getJobFromContentScript((captured) => proceedWithJD(captured));
    });
  }

  if (genBtn) {
    genBtn.addEventListener('click', () => {
      if (generating) return setStatus('Generation already in progress. Please wait...');
      setStatus('Preparing to send job to server…');

      // Get JD robustly (use stored value if popup textarea empty)
      const typedJD = (jobDescEl && jobDescEl.value || '').trim();

      function proceedWithJD(jd) {
        const jdEffective = (typedJD && typedJD.length > 20) ? typedJD : (jd || '');
        if (!jdEffective || jdEffective.length < 20) { setStatus('Please paste a job description or open a job posting page.', true); return; }

        generating = true;
        const target = parseInt((targetEl && targetEl.value) || '90', 10);

        // read auth/resume from storage/background
        chrome.storage.local.get(['authToken','resumeBase64','resumeName'], (items) => {
          const storedToken = items && items.authToken;
          const payload = { job_description: jdEffective, target_match: target };

          if (items && items.resumeBase64) {
            payload.resume_base64 = items.resumeBase64;
            payload.resume_filename = items.resumeName || 'resume.pdf';
          }

          payload.sections = { "Professional Summary": true, "Key Skills": true, "Work Experience": true, "Education": true };
          payload.quantitative_focus = "Medium";
          payload.action_verb_intensity = "Moderate";
          payload.keyword_matching = "Balanced";

          let modelVal = 'premium_classic';
          if (modelSelect) {
            const rawModel = (modelSelect && modelSelect.value) ? modelSelect.value : '';
            const normalizedModel = (rawModel || '').toString().trim().toLowerCase().replace(/\s+/g, '_');
            if (normalizedModel === 'premium') modelVal = 'premium';
            else if (normalizedModel === 'premium_classic' || normalizedModel === 'premiumclassic') modelVal = 'premium_classic';
          }
          payload.model = modelVal;

          payload.language = (languageSelect && languageSelect.value) ? languageSelect.value : 'English';
          payload.output_format = 'docx';

          function callGenerate(token) {
            if (!token) { setStatus('Please sign in first.', true); generating = false; return; }
            setStatus('Sending job to server…');

            chrome.runtime.sendMessage({ action: ACTION_GENERATE, token, payload }, (resp) => {
              generating = false;
              if (chrome.runtime.lastError) { console.error('runtime sendMessage err', chrome.runtime.lastError); setStatus('Extension background error: ' + (chrome.runtime.lastError.message || 'unknown'), true); return; }
              if (!resp) { setStatus('No response from background.', true); return; }
              if (!resp.ok) { setStatus('Generation failed: ' + (resp.error || JSON.stringify(resp.payload) || 'Unknown'), true); return; }

              const json = resp.payload || {};
              if (json.docx_base64) {
                try {
                  const blob = base64ToBlob(json.docx_base64, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document');
                  const filename = `cvolvepro_cv_${Date.now()}.docx`;
                  const url = URL.createObjectURL(blob);
                  chrome.downloads.download({ url, filename, saveAs: true }, () => {
                    setStatus('✅ CV downloaded!');
                    if (typeof json.credits === 'number') { creditsEl.textContent = json.credits; chrome.storage.local.set({ credits: json.credits }); }
                    else { chrome.runtime.sendMessage({ action: 'GET_AUTH_TOKEN' }, () => {}); }
                  });
                } catch (err) { console.error('download err', err); setStatus('Error creating DOCX file.', true); }
                return;
              }

              if (json.pdf_base64) {
                try {
                  const blob = base64ToBlob(json.pdf_base64, 'application/pdf');
                  const filename = `cvolvepro_cv_${Date.now()}.pdf`;
                  const url = URL.createObjectURL(blob);
                  chrome.downloads.download({ url, filename, saveAs: true }, () => {
                    setStatus('✅ CV downloaded!');
                    if (typeof json.credits === 'number') { creditsEl.textContent = json.credits; chrome.storage.local.set({ credits: json.credits }); }
                    else { chrome.runtime.sendMessage({ action: 'GET_AUTH_TOKEN' }, () => {}); }
                  });
                } catch (err) { console.error('download err', err); setStatus('Error creating PDF file.', true); }
                return;
              }

              if (json.download_url) {
                const ext = (json.file_ext || '').toLowerCase();
                const filename = `cvolvepro_cv_${Date.now()}.${ext === 'docx' ? 'docx' : 'pdf'}`;
                chrome.downloads.download({ url: json.download_url, filename, saveAs: true }, () => {
                  setStatus('✅ CV download started!');
                  if (typeof json.credits === 'number') { creditsEl.textContent = json.credits; chrome.storage.local.set({ credits: json.credits }); }
                });
                return;
              }

              setStatus('Generation succeeded but no file returned.', true);
            });
          }

          if (storedToken) {
            callGenerate(storedToken);
          } else {
            chrome.runtime.sendMessage({ action: ACTION_GET_TOKEN }, (resp) => {
              if (chrome.runtime.lastError) { setStatus('Please sign in first.', true); generating = false; return; }
              const tokenFromBg = resp && (resp.token || resp.authToken);
              if (tokenFromBg) {
                const candidateUser = (resp && resp.auth_user) ? resp.auth_user : (items && items.auth_user ? items.auth_user : null);
                const toSet = { authToken: tokenFromBg };
                if (candidateUser) toSet.auth_user = candidateUser;
                chrome.storage.local.set(toSet, () => { callGenerate(tokenFromBg); });
              } else { setStatus('Please sign in first.', true); generating = false; }
            });
          }
        });
      }

      // try message-first then storage fallback
      const typed = (jobDescEl && jobDescEl.value || '').trim();
      if (typed && typed.length > 20) proceedWithJD(typed);
      else getJobFromContentScript((captured) => proceedWithJD(captured));
    });
  }

  function base64ToBlob(base64, mime) {
    const sliceSize = 512;
    const byteCharacters = atob(base64);
    const byteArrays = [];
    for (let offset = 0; offset < byteCharacters.length; offset += sliceSize) {
      const slice = byteCharacters.slice(offset, offset + sliceSize);
      const byteNumbers = new Array(slice.length);
      for (let i = 0; i < slice.length; i++) byteNumbers[i] = slice.charCodeAt(i);
      const byteArray = new Uint8Array(byteNumbers);
      byteArrays.push(byteArray);
    }
    return new Blob(byteArrays, { type: mime });
  }

  if (openOptions) {
    openOptions.addEventListener('click', () => {
      if (chrome.runtime.openOptionsPage) chrome.runtime.openOptionsPage();
      else window.open(chrome.runtime.getURL('options.html'));
    });
  }
  if (openSite) {
    openSite.addEventListener('click', () => { window.open(API_BASE, '_blank'); });
  }

  // Close sign-in form when clicking outside
  document.addEventListener('click', (e) => {
    try {
      const isInside = (signinToggle && signinToggle.contains(e.target)) || (signinForm && signinForm.contains(e.target));
      if (!isInside && signinForm && signinForm.style.display === 'block' && signinToggle && signinToggle.style.display !== 'none') {
        signinForm.style.display = 'none';
        if (signinChevron) signinChevron.textContent = '▾';
      }
    } catch (ex) {}
  });
});