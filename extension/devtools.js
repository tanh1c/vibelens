// VibeLens DevTools Panel
// Captures detailed network requests using Chrome DevTools Protocol

let isRecording = false;
let capturedRequests = [];
let filteredRequests = [];
let selectedRequest = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  loadRequests();
});

function initTabs() {
  const toggleBtn = document.getElementById('toggleBtn');
  const analyzeBtn = document.getElementById('analyzeBtn');
  const clearBtn = document.getElementById('clearBtn');
  const filterInput = document.getElementById('filterInput');

  toggleBtn.addEventListener('click', toggleRecording);
  analyzeBtn.addEventListener('click', analyzeWithAI);
  clearBtn.addEventListener('click', clearRequests);
  filterInput.addEventListener('input', filterRequests);
}

async function toggleRecording() {
  const toggleBtn = document.getElementById('toggleBtn');
  const status = document.getElementById('status');
  const analyzeBtn = document.getElementById('analyzeBtn');
  const clearBtn = document.getElementById('clearBtn');

  if (!isRecording) {
    // Start recording directly, relying on devtools.network
    isRecording = true;
    toggleBtn.textContent = 'Stop Recording';
    toggleBtn.classList.remove('btn-primary');
    toggleBtn.classList.add('btn-danger');
    status.textContent = 'Recording';
    status.classList.remove('stopped');
    status.classList.add('recording');
    analyzeBtn.disabled = false;
    clearBtn.disabled = false;
  } else {
    // Stop recording
    isRecording = false;
    toggleBtn.textContent = 'Start Recording';
    toggleBtn.classList.remove('btn-danger');
    toggleBtn.classList.add('btn-primary');
    status.textContent = 'Stopped';
    status.classList.remove('recording');
    status.classList.add('stopped');
  }
}

// DevTools native network listener
if (chrome.devtools && chrome.devtools.network) {
  chrome.devtools.network.onRequestFinished.addListener((request) => {
    if (!isRecording) return;
    handleNetworkRequest(request);
  });
}

function handleNetworkRequest(req) {
  const url = req.request.url;

  // Check if URL should be filtered
  if (shouldFilterUrl(url)) return;

  // Convert headers array to object
  const requestHeaders = {};
  if (req.request.headers) {
    req.request.headers.forEach(h => { requestHeaders[h.name] = h.value; });
  }

  const responseHeaders = {};
  if (req.response.headers) {
    req.response.headers.forEach(h => { responseHeaders[h.name] = h.value; });
  }

  const entry = {
    id: Math.random().toString(36).substring(7),
    url: url,
    method: req.request.method,
    headers: requestHeaders,
    postData: req.request.postData?.text || null,
    timestamp: new Date(req.startedDateTime).getTime(),
    status: req.response.status,
    statusText: req.response.statusText,
    responseHeaders: responseHeaders,
    timing: req.time
  };

  capturedRequests.push(entry);
  renderRequests();
}

function shouldFilterUrl(url) {
  // Filter out chrome extension and non-HTTP URLs
  return !url.startsWith('http://') && !url.startsWith('https://');
}

function filterRequests() {
  const filterText = document.getElementById('filterInput').value.toLowerCase();

  if (!filterText) {
    filteredRequests = [...capturedRequests];
  } else {
    filteredRequests = capturedRequests.filter(r =>
      r.url.toLowerCase().includes(filterText) ||
      r.method.toLowerCase().includes(filterText)
    );
  }

  renderRequests();
}

function renderRequests() {
  const list = document.getElementById('requestList');

  if (filteredRequests.length === 0) {
    list.innerHTML = '<div class="no-requests">No requests captured yet. Click "Start Recording" to begin.</div>';
    return;
  }

  list.innerHTML = filteredRequests.map((req, index) => {
    const statusClass = getStatusClass(req.status);
    return `
      <div class="request-item" data-index="${index}">
        <span class="method ${req.method}">${req.method}</span>
        <span class="url">${truncateUrl(req.url)}</span>
        <span class="status-code ${statusClass}">${req.status || '...'}</span>
        <span class="time">${req.timing ? Math.round(req.timing) + 'ms' : ''}</span>
      </div>
    `;
  }).join('');

  // Add click handlers
  list.querySelectorAll('.request-item').forEach(item => {
    item.addEventListener('click', () => showRequestDetails(parseInt(item.dataset.index)));
  });
}

function getStatusClass(status) {
  if (!status) return '';
  if (status >= 200 && status < 300) return 'success';
  if (status >= 300 && status < 400) return 'redirect';
  return 'error';
}

function truncateUrl(url) {
  try {
    const urlObj = new URL(url);
    return urlObj.pathname + urlObj.search;
  } catch {
    return url.substring(0, 50);
  }
}

function showRequestDetails(index) {
  const req = filteredRequests[index];
  const aiPanel = document.getElementById('aiPanel');
  const aiResponse = document.getElementById('aiResponse');

  selectedRequest = req;

  let details = `=== Request ${req.method} ${req.url} ===\n\n`;
  details += `Status: ${req.status || 'Pending'}\n`;
  details += `Timestamp: ${new Date(req.timestamp).toISOString()}\n\n`;

  details += '--- Headers ---\n';
  for (const [key, value] of Object.entries(req.headers || {})) {
    details += `${key}: ${value}\n`;
  }

  if (req.postData) {
    details += '\n--- Post Data ---\n';
    details += req.postData + '\n';
  }

  if (req.responseHeaders) {
    details += '\n--- Response Headers ---\n';
    for (const [key, value] of Object.entries(req.responseHeaders)) {
      details += `${key}: ${value}\n`;
    }
  }

  aiResponse.textContent = details;
  aiPanel.classList.add('visible');
}

async function analyzeWithAI() {
  const aiResponse = document.getElementById('aiResponse');
  const aiPanel = document.getElementById('aiPanel');

  aiPanel.classList.add('visible');
  aiResponse.textContent = 'Analyzing with AI...';

  try {
    // 1. First, save requests to the bridge server's store so MCP stdio can see them
    await fetch('http://localhost:8000/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requests: capturedRequests.map(r => ({
          url: r.url,
          method: r.method,
          status: r.status,
          headers: r.headers,
          postData: r.postData,
          responseHeaders: r.responseHeaders
        }))
      })
    });

    // 2. Then, ask for analysis
    const response = await fetch('http://localhost:8000/analyze', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        requests: capturedRequests.map(r => ({
          url: r.url,
          method: r.method,
          status: r.status,
          headers: r.headers,
          postData: r.postData
        }))
      })
    });

    const result = await response.json();
    aiResponse.textContent = result.analysis || result.error || JSON.stringify(result, null, 2);
  } catch (error) {
    aiResponse.textContent = 'Error connecting to MCP server. Make sure VibeLens MCP server is running.\n\n' +
      'Run: python -m vibeengine.mcp\n\n' + error.message;
  }
}

function clearRequests() {
  capturedRequests = [];
  filteredRequests = [];
  renderRequests();

  const aiPanel = document.getElementById('aiPanel');
  aiPanel.classList.remove('visible');
}

function loadRequests() {
  // Load from storage if available
  chrome.storage.local.get(['vibeLensRequests'], (result) => {
    if (result.vibeLensRequests) {
      capturedRequests = result.vibeLensRequests;
      filteredRequests = [...capturedRequests];
      renderRequests();
    }
  });
}

// Save requests periodically
let saveInterval = setInterval(() => {
  try {
    if (!chrome.runtime?.id) {
      clearInterval(saveInterval);
      return;
    }
    if (capturedRequests.length > 0) {
      chrome.storage.local.set({ vibeLensRequests: capturedRequests.slice(-500) });
    }
  } catch (error) {
    // If extension context is invalidated, clear the interval to stop errors
    clearInterval(saveInterval);
  }
}, 5000);
