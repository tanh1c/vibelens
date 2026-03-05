// VibeLens Popup Script
// Giao tiếp với background.js để capture requests

let isRecording = false;
let requests = [];

document.addEventListener('DOMContentLoaded', () => {
  loadSettings();
  setupListeners();
  syncWithBackground();
});

function setupListeners() {
  document.getElementById('recordBtn').addEventListener('click', toggleRecording);
  document.getElementById('analyzeBtn').addEventListener('click', analyzeWithAI);
  document.getElementById('clearBtn').addEventListener('click', clearAll);
  document.getElementById('saveMcpBtn').addEventListener('click', saveMcpUrl);

  // Search & Filter
  document.getElementById('searchInput').addEventListener('input', renderRequestsList);
  document.querySelectorAll('.filter-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.filter-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      renderRequestsList();
    });
  });

  // Detail tabs
  document.querySelectorAll('.detail-tab').forEach(tab => {
    tab.addEventListener('click', (e) => {
      document.querySelectorAll('.detail-tab').forEach(t => t.classList.remove('active'));
      e.target.classList.add('active');
      if (selectedRequest) showDetailTab(e.target.dataset.detail, selectedRequest);
    });
  });
}

async function toggleRecording() {
  const btn = document.getElementById('recordBtn');

  if (!isRecording) {
    // Start recording - gửi message cho background.js
    try {
      // Lấy active tab từ cửa sổ trình duyệt chính (không phải cửa sổ popup)
      // Tìm cửa sổ "normal" gần nhất (không phải popup window của VibeLens)
      const allWindows = await chrome.windows.getAll({ windowTypes: ['normal'] });
      let targetTab = null;

      for (const win of allWindows) {
        const tabs = await chrome.tabs.query({ active: true, windowId: win.id });
        if (tabs.length > 0 && !tabs[0].url.startsWith('chrome-extension://')) {
          targetTab = tabs[0];
          break;
        }
      }

      if (!targetTab) {
        alert('Không tìm thấy tab trình duyệt nào để record.\\nHãy mở một trang web trước rồi bấm Record.');
        return;
      }

      const response = await chrome.runtime.sendMessage({
        type: 'START_RECORDING',
        tabId: targetTab.id
      });
      console.log('VibeLens: Recording started', response);

      if (response && response.status === 'error') {
        alert('Failed to start recording: ' + response.message + '\n\nMake sure "debugger" permission is enabled in chrome://extensions/');
        return;
      }

      isRecording = true;
      btn.textContent = 'Stop Recording';
      btn.classList.remove('btn-primary');
      btn.classList.add('btn-danger');
      document.getElementById('analyzeBtn').disabled = false;
      document.getElementById('clearBtn').disabled = false;
      updateStatusBadge(true);

      // Bắt đầu polling để lấy requests từ background
      startPolling();
    } catch (error) {
      console.error('Failed to start recording:', error);
      alert('Failed to start recording: ' + error.message);
    }
  } else {
    // Stop recording
    try {
      const response = await chrome.runtime.sendMessage({ type: 'STOP_RECORDING' });
      console.log('VibeLens: Recording stopped', response);

      isRecording = false;
      btn.textContent = 'Start Recording';
      btn.classList.remove('btn-danger');
      btn.classList.add('btn-primary');
      updateStatusBadge(false);

      // Dừng polling
      stopPolling();

      // Sync một lần nữa để lấy requests cuối cùng
      await syncWithBackground();
    } catch (error) {
      console.error('Failed to stop recording:', error);
    }
  }
}

let pollingInterval = null;

function startPolling() {
  // Poll mỗi 1 giây để lấy requests từ background
  pollingInterval = setInterval(syncWithBackground, 1000);
}

function stopPolling() {
  if (pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
}

async function syncWithBackground() {
  try {
    const response = await chrome.runtime.sendMessage({ type: 'GET_REQUESTS' });
    if (response) {
      // Cập nhật recording state
      if (response.isRecording !== undefined && response.isRecording !== isRecording) {
        isRecording = response.isRecording;
        updateRecordingUI();
      }

      if (response.requests) {
        requests = response.requests;
        updateStats();
        renderRequestsList();
      }
    }
  } catch (error) {
    // Background chưa sẵn sàng, bỏ qua
  }
}

function updateRecordingUI() {
  const btn = document.getElementById('recordBtn');
  if (isRecording) {
    btn.textContent = 'Stop Recording';
    btn.classList.remove('btn-primary');
    btn.classList.add('btn-danger');
    document.getElementById('analyzeBtn').disabled = false;
    document.getElementById('clearBtn').disabled = false;
    updateStatusBadge(true);
    startPolling();
  } else {
    btn.textContent = 'Start Recording';
    btn.classList.remove('btn-danger');
    btn.classList.add('btn-primary');
    updateStatusBadge(false);
    stopPolling();
  }
}

function updateStatusBadge(recording) {
  const badge = document.getElementById('statusBadge');
  const text = document.getElementById('statusText');

  if (recording) {
    badge.className = 'status-badge recording';
    text.textContent = 'Recording';
  } else {
    badge.className = 'status-badge idle';
    text.textContent = 'Idle';
  }
}

function updateStats() {
  document.getElementById('requestCount').textContent = requests.length;

  const apiCount = requests.filter(r =>
    r.url.includes('/api/') || r.url.includes('api.')
  ).length;
  document.getElementById('apiCount').textContent = apiCount;

  const errorCount = requests.filter(r => r.status >= 400).length;
  document.getElementById('errorCount').textContent = errorCount;
}
let selectedRequest = null;
let activeFilter = 'all';

function getFilteredRequests() {
  const searchTerm = (document.getElementById('searchInput')?.value || '').toLowerCase();
  const activeTab = document.querySelector('.filter-tab.active');
  const filter = activeTab ? activeTab.dataset.filter : 'all';

  let filtered = [...requests];

  // Filter by category
  if (filter === 'api') {
    filtered = filtered.filter(r =>
      r.url && (r.url.includes('/api/') || r.url.includes('api.') ||
        (r.method && r.method !== 'GET') ||
        (r.headers && r.headers['Content-Type'] && r.headers['Content-Type'].includes('json')))
    );
  } else if (filter === 'errors') {
    filtered = filtered.filter(r => r.status >= 400);
  }

  // Filter by search
  if (searchTerm) {
    filtered = filtered.filter(r => {
      const url = (r.url || '').toLowerCase();
      const method = (r.method || '').toLowerCase();
      const status = String(r.status || '');
      return url.includes(searchTerm) || method.includes(searchTerm) || status.includes(searchTerm);
    });
  }

  return filtered;
}

function renderRequestsList() {
  const container = document.getElementById('requestsList');
  const countEl = document.getElementById('requestListCount');
  const filtered = getFilteredRequests();

  countEl.textContent = `${filtered.length} / ${requests.length} items`;

  if (filtered.length === 0) {
    container.innerHTML = '<div class="no-requests">No matching requests</div>';
    return;
  }

  // Show recent first, max 100
  const displayRequests = filtered.slice(-100).reverse();

  container.innerHTML = displayRequests.map((req, idx) => {
    const method = req.method || 'GET';
    const url = req.url || '';
    const status = req.status;
    const statusClass = status >= 400 ? 'status-error' : status >= 300 ? 'status-redirect' : 'status-success';
    const methodClass = `method-${method.toLowerCase()}`;
    const isSelected = selectedRequest && selectedRequest.requestId === req.requestId && selectedRequest.url === req.url;

    // Shortened URL
    let displayUrl = url;
    try {
      const urlObj = new URL(url);
      displayUrl = urlObj.pathname + (urlObj.search || '');
      if (displayUrl.length > 50) {
        displayUrl = displayUrl.substring(0, 50) + '...';
      }
    } catch (e) {
      displayUrl = url.length > 50 ? url.substring(0, 50) + '...' : url;
    }

    return `
      <div class="request-item ${isSelected ? 'selected' : ''}" data-idx="${idx}">
        <span class="request-method ${methodClass}">${method}</span>
        <span class="request-url" title="${url}">${displayUrl}</span>
        ${status ? `<span class="request-status ${statusClass}">${status}</span>` : ''}
      </div>
    `;
  }).join('');

  // Event delegation — click trên request item
  container.querySelectorAll('.request-item').forEach(el => {
    el.addEventListener('click', () => {
      const idx = parseInt(el.dataset.idx, 10);
      selectRequest(idx);
    });
  });
}

function selectRequest(idx) {
  const filtered = getFilteredRequests();
  const displayRequests = filtered.slice(-100).reverse();
  selectedRequest = displayRequests[idx];

  // Update selected style
  document.querySelectorAll('.request-item').forEach((el, i) => {
    el.classList.toggle('selected', i === idx);
  });

  // Show detail panel
  const panel = document.getElementById('detailPanel');
  panel.classList.add('visible');

  // Show active detail tab
  const activeTab = document.querySelector('.detail-tab.active');
  showDetailTab(activeTab ? activeTab.dataset.detail : 'headers', selectedRequest);
}

function showDetailTab(tab, req) {
  const content = document.getElementById('detailContent');
  if (!req) return;

  switch (tab) {
    case 'headers':
      content.innerHTML = renderHeaders(req);
      break;
    case 'payload':
      content.innerHTML = renderPayload(req);
      break;
    case 'response':
      content.innerHTML = renderResponse(req);
      break;
    case 'overview':
      content.innerHTML = renderOverview(req);
      break;
  }
}

function renderHeaders(req) {
  let html = '<div class="detail-label">Request Headers</div>';
  if (req.headers && Object.keys(req.headers).length > 0) {
    html += Object.entries(req.headers).map(([key, val]) =>
      `<div class="detail-row"><span class="detail-key">${escHtml(key)}</span><span class="detail-value">${escHtml(String(val))}</span></div>`
    ).join('');
  } else {
    html += '<div style="color:#525252;font-size:11px">No request headers captured</div>';
  }

  html += '<div class="detail-label" style="margin-top:12px">Response Headers</div>';
  if (req.responseHeaders && Object.keys(req.responseHeaders).length > 0) {
    html += Object.entries(req.responseHeaders).map(([key, val]) =>
      `<div class="detail-row"><span class="detail-key">${escHtml(key)}</span><span class="detail-value">${escHtml(String(val))}</span></div>`
    ).join('');
  } else {
    html += '<div style="color:#525252;font-size:11px">No response headers captured</div>';
  }

  return html;
}

function renderPayload(req) {
  if (!req.postData) {
    return '<div style="color:#525252;font-size:11px;padding:10px">No payload (GET request or no body)</div>';
  }

  let body = req.postData;
  try {
    const parsed = JSON.parse(body);
    body = JSON.stringify(parsed, null, 2);
  } catch (e) { /* not JSON */ }

  return `<div class="detail-label">Request Body</div><pre>${escHtml(body)}</pre>`;
}

function renderResponse(req) {
  if (!req.responseBody) {
    return '<div style="color:#525252;font-size:11px;padding:10px">No response body captured</div>';
  }

  let body = req.responseBody;
  try {
    const parsed = JSON.parse(body);
    body = JSON.stringify(parsed, null, 2);
  } catch (e) { /* not JSON */ }

  // Truncate if too long
  if (body.length > 3000) {
    body = body.substring(0, 3000) + '\n\n... (truncated)';
  }

  return `<div class="detail-label">Response Body (${req.status || '?'})</div><pre>${escHtml(body)}</pre>`;
}

function renderOverview(req) {
  const rows = [
    ['URL', req.url],
    ['Method', req.method],
    ['Status', `${req.status || '?'} ${req.statusText || ''}`],
    ['Type', req.type || req.mimeType || 'N/A'],
    ['Document', req.documentURL || 'N/A'],
    ['Timing', req.timing ? `${Math.round(req.timing.receiveHeadersEnd)}ms` : 'N/A'],
    ['Size', req.encodedDataLength ? `${(req.encodedDataLength / 1024).toFixed(1)}KB` : 'N/A'],
    ['Completed', req.completed ? 'Yes' : 'No'],
  ];

  return rows.map(([key, val]) =>
    `<div class="detail-row"><span class="detail-key">${key}</span><span class="detail-value">${escHtml(String(val || 'N/A'))}</span></div>`
  ).join('');
}

function escHtml(str) {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

async function analyzeWithAI() {
  const mcpUrl = document.getElementById('mcpUrl').value;
  console.log('VibeLens: Analyzing with AI, MCP URL:', mcpUrl, 'Requests:', requests.length);

  // Đảm bảo lấy requests mới nhất từ storage
  if (requests.length === 0) {
    await syncWithBackground();
  }

  if (requests.length === 0) {
    alert('No requests to analyze. Start recording and browse some websites first.');
    return;
  }

  try {
    // 1. First, sync requests to bridge server (replace old ones)
    console.log('VibeLens: Syncing requests to bridge server...');
    const syncResponse = await fetch(`${mcpUrl}/requests`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests: requests })
    });

    if (!syncResponse.ok) {
      throw new Error(`Sync failed: ${syncResponse.status} ${syncResponse.statusText}`);
    }

    const syncResult = await syncResponse.json();
    console.log('VibeLens: Sync result:', syncResult);

    // 2. Then analyze with AI
    console.log('VibeLens: Calling AI analyze...');
    const response = await fetch(`${mcpUrl}/analyze`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests: requests })
    });

    if (!response.ok) {
      throw new Error(`Analyze failed: ${response.status} ${response.statusText}`);
    }

    const result = await response.json();
    console.log('VibeLens: Analyze result:', result);

    // Show result in alert
    if (result.analysis) {
      alert(result.analysis);
    } else if (result.error) {
      alert('Error: ' + result.error);
    } else {
      alert(JSON.stringify(result, null, 2));
    }
  } catch (error) {
    console.error('VibeLens: Analyze error:', error);
    alert('Error connecting to MCP server: ' + error.message + '\n\nMake sure the MCP server is running:\npython -m vibeengine.mcp.server');
  }
}

async function clearAll() {
  try {
    await chrome.runtime.sendMessage({ type: 'CLEAR_REQUESTS' });
    requests = [];
    updateStats();
    renderRequestsList();
    document.getElementById('analyzeBtn').disabled = true;
    document.getElementById('clearBtn').disabled = true;
  } catch (error) {
    console.error('Failed to clear:', error);
  }
}

function saveMcpUrl() {
  const url = document.getElementById('mcpUrl').value;
  chrome.storage.local.set({ vibeLensMcpUrl: url });
  alert('MCP URL saved: ' + url);
}

function loadSettings() {
  chrome.storage.local.get(['vibeLensMcpUrl', 'vibeLensRequests', 'vibeLensRecording'], (result) => {
    if (result.vibeLensMcpUrl) {
      document.getElementById('mcpUrl').value = result.vibeLensMcpUrl;
    }
    if (result.vibeLensRequests) {
      requests = result.vibeLensRequests;
      updateStats();
      renderRequestsList();
      // Enable analyze button nếu có requests
      if (requests.length > 0) {
        document.getElementById('analyzeBtn').disabled = false;
        document.getElementById('clearBtn').disabled = false;
      }
    }
    // Sync recording state từ storage
    if (result.vibeLensRecording !== undefined) {
      isRecording = result.vibeLensRecording;
      updateRecordingUI();
    }
  });
}
