// options.js - only optional dev token storage (no apiKey)
document.addEventListener('DOMContentLoaded', () => {
  const devTokenInput = document.getElementById('devToken');
  const saveBtn = document.getElementById('saveBtn');
  const clearBtn = document.getElementById('clearBtn');
  const msg = document.getElementById('msg');

  // Load existing dev token (if any)
  chrome.storage.local.get(['devToken'], (items) => {
    if (items.devToken) devTokenInput.value = items.devToken;
  });

  saveBtn.addEventListener('click', () => {
    const val = (devTokenInput.value || '').trim();
    if (!val) {
      chrome.storage.local.remove(['devToken'], () => {
        msg.textContent = 'Cleared saved development token.';
      });
      return;
    }
    chrome.storage.local.set({ devToken: val }, () => {
      msg.textContent = 'Saved development token (optional). Note: normal users should sign in via popup.';
    });
  });

  clearBtn.addEventListener('click', () => {
    chrome.storage.local.remove(['devToken'], () => {
      devTokenInput.value = '';
      msg.textContent = 'Cleared saved development token.';
    });
  });
});