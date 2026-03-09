// VibeLens Background Service Worker
let isRecording = false;
let activeTabId = null;
let capturedRequests = [];
let mcpServerUrl = 'http://localhost:8000';
let recordingDomain = null;
let lastSyncTime = 0;
let pendingSync = false;

// ─── Multi-Domain & Auth Tracking ───
let trackedDomains = new Set();      // Tất cả domain đang theo dõi
let redirectChains = {};             // requestId → [url1, url2, ...]
let capturedCookies = {};            // domain → [{name, value, ...}]
let currentSessionId = null;         // Database session id

// Load state từ storage khi khởi động
async function loadState() {
  return new Promise((resolve) => {
    chrome.storage.local.get(['vibeLensRecording', 'vibeLensRequests', 'vibeLensMcpUrl'], (result) => {
      if (result.vibeLensRecording) {
        isRecording = result.vibeLensRecording;
        console.log('VibeLens: Restored recording state:', isRecording);
      }
      if (result.vibeLensRequests) {
        capturedRequests = result.vibeLensRequests;
        console.log('VibeLens: Restored', capturedRequests.length, 'requests');
      }
      if (result.vibeLensMcpUrl) {
        mcpServerUrl = result.vibeLensMcpUrl;
      }
      if (result.vibeLensSessionId) {
        currentSessionId = result.vibeLensSessionId;
      }
      resolve();
    });
  });
}

function saveState() {
  chrome.storage.local.set({
    vibeLensRecording: isRecording,
    vibeLensRequests: capturedRequests,
    vibeLensMcpUrl: mcpServerUrl,
    vibeLensSessionId: currentSessionId
  });
}

// Khởi động và load state
loadState().then(() => {
  console.log('VibeLens Background Service Worker loaded - Recording:', isRecording);
});

// ─── Floating Panel Window ───
// Khi click icon extension → mở popup.html dạng cửa sổ nổi (không tự đóng khi click ra ngoài)
let panelWindowId = null;

chrome.action.onClicked.addListener(async (tab) => {
  // Nếu panel đã mở, focus vào nó
  if (panelWindowId !== null) {
    try {
      const existingWindow = await chrome.windows.get(panelWindowId);
      if (existingWindow) {
        chrome.windows.update(panelWindowId, { focused: true });
        return;
      }
    } catch (e) {
      // Window đã bị đóng, tạo mới
      panelWindowId = null;
    }
  }

  // Tạo cửa sổ nổi mới
  const panelWindow = await chrome.windows.create({
    url: chrome.runtime.getURL('popup.html'),
    type: 'popup',
    width: 420,
    height: 680,
    top: 80,
    left: Math.max(0, (await chrome.windows.getCurrent()).width - 440),
  });

  panelWindowId = panelWindow.id;

  // Theo dõi khi user đóng panel
  chrome.windows.onRemoved.addListener((windowId) => {
    if (windowId === panelWindowId) {
      panelWindowId = null;
    }
  });
});

// Lắng nghe messages từ popup hoặc devtools
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.type === 'START_RECORDING') {
    startRecording(message.tabId).then(result => {
      sendResponse(result);
    });
    return true;
  } else if (message.type === 'STOP_RECORDING') {
    stopRecording().then(result => {
      sendResponse(result);
    });
    return true;
  } else if (message.type === 'GET_REQUESTS') {
    sendResponse({ requests: capturedRequests, isRecording: isRecording });
  } else if (message.type === 'SET_MCP_URL') {
    mcpServerUrl = message.url;
    saveState();
    sendResponse({ status: 'updated', url: mcpServerUrl });
  } else if (message.type === 'SEND_TO_AI') {
    sendToAI(capturedRequests).then(result => {
      sendResponse({ result });
    });
    return true;
  } else if (message.type === 'CLEAR_REQUESTS') {
    capturedRequests = [];
    saveState();
    sendResponse({ status: 'cleared' });
  } else if (message.type === 'GET_STATUS') {
    sendResponse({ isRecording: isRecording, count: capturedRequests.length });
  }
});

// Bắt đầu recording với debugger API
async function startRecording(tabId) {
  try {
    // Nếu không có tabId, lấy active tab
    if (!tabId) {
      const tabs = await chrome.tabs.query({ active: true, currentWindow: true });
      if (tabs.length === 0) {
        return { status: 'error', message: 'No active tab' };
      }
      tabId = tabs[0].id;
    }

    // Lấy domain của tab đang record
    const tab = await chrome.tabs.get(tabId);
    try {
      const tabUrl = new URL(tab.url);
      recordingDomain = tabUrl.hostname;
      // Khởi tạo multi-domain tracking với domain chính
      trackedDomains = new Set([recordingDomain]);
    } catch (e) {
      recordingDomain = null;
      trackedDomains = new Set();
    }

    // Create a new session in DB
    try {
      const res = await fetch(mcpServerUrl + '/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ domain: recordingDomain, name: `Record: ${recordingDomain}` })
      });
      const data = await res.json();
      currentSessionId = data.session_id;
    } catch (e) {
      console.error('VibeLens: Failed to create session on bridge', e);
    }

    // Attach debugger
    await chrome.debugger.attach({ tabId }, '1.3');

    // Enable Network domain với full options
    await chrome.debugger.sendCommand({ tabId }, 'Network.enable', {
      maxTotalBufferSize: 10000000,  // 10MB buffer
      maxResourceBufferSize: 5000000, // 5MB per resource
    });

    // Enable ExtraInfo events để bắt cookies và auth headers
    await chrome.debugger.sendCommand({ tabId }, 'Network.setExtraHTTPHeaders', {
      headers: { 'X-VibeLens-Capture': 'true' } // Dummy header để kích hoạt ExtraInfo
    });
    await chrome.debugger.sendCommand({ tabId }, 'Network.enable', {
      extraInfoEnabled: true
    });

    // Listen for network events
    chrome.debugger.onEvent.addListener(onNetworkEvent);

    isRecording = true;
    activeTabId = tabId;
    capturedRequests = [];
    redirectChains = {};
    capturedCookies = {};
    saveState();

    // Capture initial cookies từ domain chính
    await captureCurrentCookies(recordingDomain);

    console.log('VibeLens: Recording started on tab', tabId, '| Domain:', recordingDomain, '| Tracked domains:', [...trackedDomains]);
    return { status: 'recording', isRecording: true, domain: recordingDomain };

  } catch (error) {
    console.error('VibeLens: Failed to start recording:', error);
    return { status: 'error', message: error.message };
  }
}

// Dừng recording
async function stopRecording() {
  try {
    if (activeTabId) {
      // Disable Network domain
      await chrome.debugger.sendCommand({ tabId: activeTabId }, 'Network.disable');
      // Detach debugger
      await chrome.debugger.detach({ tabId: activeTabId });
    }

    chrome.debugger.onEvent.removeListener(onNetworkEvent);

    // Final sync before stopping
    await syncToBridge(capturedRequests);

    isRecording = false;
    activeTabId = null;
    recordingDomain = null;
    trackedDomains = new Set();
    redirectChains = {};
    saveState();

    console.log('VibeLens: Recording stopped, captured', capturedRequests.length, 'requests');
    return { status: 'stopped', count: capturedRequests.length, isRecording: false };

  } catch (error) {
    console.error('VibeLens: Failed to stop recording:', error);
    return { status: 'error', message: error.message };
  }
}

// ─── Capture Cookies từ Chrome API ───
async function captureCurrentCookies(domain) {
  try {
    const cookies = await chrome.cookies.getAll({ domain: domain });
    capturedCookies[domain] = cookies.map(c => ({
      name: c.name,
      value: c.value,
      domain: c.domain,
      path: c.path,
      secure: c.secure,
      httpOnly: c.httpOnly,
      expirationDate: c.expirationDate,
    }));
    console.log(`VibeLens: Captured ${cookies.length} cookies from ${domain}`);
  } catch (e) {
    console.log('VibeLens: Cannot capture cookies for', domain, e);
  }
}

// Xử lý network events từ debugger
function onNetworkEvent(source, method, params) {
  if (!isRecording) return;
  if (source.tabId !== activeTabId) return;

  switch (method) {
    case 'Network.requestWillBeSent':
      handleRequestWillBeSent(params);
      break;
    case 'Network.responseReceived':
      handleResponseReceived(params);
      break;
    case 'Network.loadingFinished':
      handleLoadingFinished(params);
      break;
    case 'Network.dataReceived':
      handleDataReceived(params);
      break;
    // ─── ExtraInfo events cho cookie/auth capture ───
    case 'Network.requestWillBeSentExtraInfo':
      handleRequestExtraInfo(params);
      break;
    case 'Network.responseReceivedExtraInfo':
      handleResponseExtraInfo(params);
      break;
  }
}

function shouldCaptureUrl(url) {
  // Luôn bỏ qua các URL nội bộ
  if (url.startsWith('chrome-extension://')) return false;
  if (url.startsWith('chrome://')) return false;
  if (url.startsWith('data:')) return false;
  if (url.startsWith('blob:')) return false;
  if (url.startsWith('devtools://')) return false;

  // Multi-domain tracking: bắt request thuộc BẤT KỲ domain nào đã theo dõi
  if (trackedDomains.size > 0) {
    try {
      const reqUrl = new URL(url);
      // Check tất cả tracked domains
      for (const domain of trackedDomains) {
        if (reqUrl.hostname === domain || reqUrl.hostname.endsWith('.' + domain)) {
          return true;
        }
      }
      return false;
    } catch (e) {
      return false;
    }
  }

  return true;
}

// Auto-detect redirect → thêm domain mới vào tracking
function trackRedirectDomain(url) {
  try {
    const reqUrl = new URL(url);
    const domain = reqUrl.hostname;
    if (!trackedDomains.has(domain)) {
      trackedDomains.add(domain);
      console.log(`VibeLens: 🔗 Auto-tracking new domain: ${domain} (redirect detected)`);
      // Capture cookies của domain mới
      captureCurrentCookies(domain);
    }
  } catch (e) { /* ignore */ }
}

function handleRequestWillBeSent(params) {
  const request = params.request;

  // Detect redirect → auto-track domain mới
  if (params.redirectResponse) {
    // Đây là redirect! Track domain mới + lưu redirect chain
    trackRedirectDomain(request.url);
    if (!redirectChains[params.requestId]) {
      redirectChains[params.requestId] = [];
    }
    redirectChains[params.requestId].push({
      url: params.redirectResponse.url || 'unknown',
      status: params.redirectResponse.status,
      headers: params.redirectResponse.headers,
    });
  }

  // Khi có redirect tới domain mới, cần check lại
  if (!shouldCaptureUrl(request.url)) {
    // Nếu request đang redirect, auto-track domain
    if (params.redirectResponse) {
      trackRedirectDomain(request.url);
    } else {
      return;
    }
  }

  const existing = capturedRequests.find(r => r.requestId === params.requestId);

  if (existing) {
    // Update existing request
    existing.url = request.url;
    existing.method = request.method;
    existing.timestamp = params.timestamp * 1000;
    existing.headers = request.headers;
    existing.postData = request.postData;
    existing.initiator = request.initiator;
    existing.type = params.type;
  } else {
    // Create new request
    const newRequest = {
      requestId: params.requestId,
      documentId: params.documentId,
      url: request.url,
      method: request.method,
      timestamp: params.timestamp * 1000,
      wallTime: params.wallTime * 1000,
      headers: request.headers,
      postData: request.postData,
      initiator: request.initiator,
      type: params.type,
      documentURL: params.documentURL,
      // Response info (will be filled later)
      status: null,
      statusText: '',
      responseHeaders: null,
      responseBody: null,
      timing: null,
      encodedDataLength: 0,
      completed: false,
      // ─── New fields ───
      cookies: null,           // Request cookies
      setCookies: null,        // Response Set-Cookie
      redirectChain: null,     // Redirect history
      securityDetails: null,   // TLS/SSL info
    };
    capturedRequests.push(newRequest);
  }

  saveState();
}

// ─── ExtraInfo: Cookie & Token Capture ───
function handleRequestExtraInfo(params) {
  const req = capturedRequests.find(r => r.requestId === params.requestId);
  if (!req) return;

  // Capture request cookies (sent by browser)
  if (params.headers && params.headers['Cookie']) {
    req.cookies = params.headers['Cookie'];
    // Update headers with full cookie info
    req.headers = { ...req.headers, ...params.headers };
  }

  // Capture associated cookies objects
  if (params.associatedCookies) {
    req.associatedCookies = params.associatedCookies
      .filter(c => !c.blockedReasons || c.blockedReasons.length === 0)
      .map(c => ({
        name: c.cookie.name,
        value: c.cookie.value,
        domain: c.cookie.domain,
        path: c.cookie.path,
        httpOnly: c.cookie.httpOnly,
        secure: c.cookie.secure,
      }));
  }
}

function handleResponseExtraInfo(params) {
  const req = capturedRequests.find(r => r.requestId === params.requestId);
  if (!req) return;

  // Capture Set-Cookie from response (the actual cookie being set)
  if (params.headers) {
    const setCookieHeaders = [];
    for (const [key, val] of Object.entries(params.headers)) {
      if (key.toLowerCase() === 'set-cookie') {
        setCookieHeaders.push(val);
      }
    }
    if (setCookieHeaders.length > 0) {
      req.setCookies = setCookieHeaders;
    }

    // Merge extra response headers
    req.responseHeaders = { ...req.responseHeaders, ...params.headers };
  }

  // Capture security details (TLS)
  if (params.securityDetails) {
    req.securityDetails = {
      protocol: params.securityDetails.protocol,
      cipher: params.securityDetails.cipher,
      issuer: params.securityDetails.issuer,
      subjectName: params.securityDetails.subjectName,
    };
  }
}

function handleResponseReceived(params) {
  const req = capturedRequests.find(r => r.requestId === params.requestId);
  if (req) {
    req.status = params.response.status;
    req.statusText = params.response.statusText;
    req.responseHeaders = { ...req.responseHeaders, ...params.response.headers };
    req.timing = params.response.timing;
    req.mimeType = params.response.mimeType;
    req.encodedDataLength = params.response.encodedDataLength;
    req.remoteIPAddress = params.response.remoteIPAddress;
    req.remotePort = params.response.remotePort;
    req.protocol = params.response.protocol;
    req.securityState = params.response.securityState;

    // Lưu redirect chain nếu có
    if (redirectChains[params.requestId]) {
      req.redirectChain = redirectChains[params.requestId];
    }
  }
  saveState();
}

function handleLoadingFinished(params) {
  const req = capturedRequests.find(r => r.requestId === params.requestId);
  if (req) {
    req.completed = true;
    req.encodedDataLength = params.encodedDataLength;
  }

  // Get response body if available
  getResponseBody(params.requestId);

  saveState();
}

function handleDataReceived(params) {
  const req = capturedRequests.find(r => r.requestId === params.requestId);
  if (req) {
    req.dataLength = params.dataLength;
    req.encodedDataLength = params.encodedDataLength;
  }
}
// ─── Smart Response Storage ───
// Phân loại body theo MIME type và lưu thông minh:
// - JSON: lưu full (quan trọng nhất cho API analysis)
// - HTML: lưu 10KB đầu + tóm tắt structure
// - JS/CSS/Image/Font: bỏ qua (không hữu ích cho AI)
// - Text khác: lưu 15KB đầu

const SKIP_MIME_TYPES = [
  'javascript', 'css', 'image/', 'font/', 'video/', 'audio/',
  'woff', 'woff2', 'png', 'jpg', 'jpeg', 'gif', 'svg', 'ico',
  'webp', 'mp4', 'webm', 'ogg',
];

function shouldStoreBody(req) {
  const mime = (req.mimeType || '').toLowerCase();
  const url = (req.url || '').toLowerCase();

  // Luôn bỏ qua file tĩnh
  if (SKIP_MIME_TYPES.some(t => mime.includes(t) || url.includes('.' + t))) {
    return false;
  }

  return true;
}

function smartTrimBody(body, mimeType) {
  const mime = (mimeType || '').toLowerCase();

  // JSON: lưu full (thường nhỏ và quan trọng nhất)
  if (mime.includes('json')) {
    try {
      // Reformat JSON cho dễ đọc, max 100KB
      const parsed = JSON.parse(body);
      const formatted = JSON.stringify(parsed, null, 2);
      if (formatted.length > 100000) {
        return formatted.substring(0, 100000) + '\n\n... [JSON TRUNCATED - original: ' + body.length + ' chars]';
      }
      return formatted;
    } catch (e) {
      // Không parse được nhưng vẫn giữ
      return body.length > 100000 ? body.substring(0, 100000) + '\n... [TRUNCATED]' : body;
    }
  }

  // HTML: lưu 10KB + tóm tắt structure
  if (mime.includes('html')) {
    if (body.length <= 10000) return body;

    const preview = body.substring(0, 10000);
    // Extract title và meta tags
    const titleMatch = body.match(/<title[^>]*>(.*?)<\/title>/i);
    const title = titleMatch ? titleMatch[1] : 'N/A';
    const formCount = (body.match(/<form/gi) || []).length;
    const inputCount = (body.match(/<input/gi) || []).length;
    const linkCount = (body.match(/<a\s/gi) || []).length;

    return preview + `\n\n--- [HTML SUMMARY] ---\nTitle: ${title}\nFull size: ${body.length} chars\nForms: ${formCount}, Inputs: ${inputCount}, Links: ${linkCount}\n`;
  }

  // XML: lưu 20KB
  if (mime.includes('xml')) {
    return body.length > 20000 ? body.substring(0, 20000) + '\n... [XML TRUNCATED]' : body;
  }

  // Text khác: lưu 15KB
  return body.length > 15000 ? body.substring(0, 15000) + '\n... [TRUNCATED - ' + body.length + ' chars total]' : body;
}

async function getResponseBody(requestId) {
  try {
    const req = capturedRequests.find(r => r.requestId === requestId);
    if (!req || req.responseBody !== null) return;

    // Skip nếu MIME type không cần lưu
    if (!shouldStoreBody(req)) {
      req.responseBody = `[SKIPPED - ${req.mimeType || 'binary'} content not stored]`;
      return;
    }

    const result = await chrome.debugger.sendCommand(
      { tabId: activeTabId },
      'Network.getResponseBody',
      { requestId: requestId }
    );

    if (result && result.body) {
      let body = result.base64Encoded ? atob(result.body) : result.body;
      req.responseBody = smartTrimBody(body, req.mimeType);
      req.responseBodySize = result.body.length;
      saveState();
    }
  } catch (error) {
    // Response body might not be available for some requests
  }
}

// Sync với bridge server (dùng PUT để replace thay vì append)
async function syncToBridge(requests) {
  if (!requests || requests.length === 0) return;

  const now = Date.now();
  if (now - lastSyncTime < 3000 && !pendingSync) return;
  if (pendingSync) return;

  pendingSync = true;
  try {
    // Dùng PUT để replace hoàn toàn
    const response = await fetch(mcpServerUrl + '/requests', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        session_id: currentSessionId,
        requests: requests,
        meta: {
          trackedDomains: [...trackedDomains],
          capturedCookies: capturedCookies,
          recordingDomain: recordingDomain,
        }
      })
    });
    const result = await response.json();
    lastSyncTime = now;
    console.log('VibeLens: Synced', requests.length, 'requests to bridge server (total:', result.count, ')');
  } catch (error) {
    console.log('VibeLens: Bridge sync error:', error.message);
  } finally {
    pendingSync = false;
  }
}

// Gửi requests lên AI
async function sendToAI(requests) {
  try {
    const response = await fetch(mcpServerUrl + '/requests', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ requests: requests })
    });
    return await response.json();
  } catch (error) {
    return { error: error.message };
  }
}

// Auto-sync khi có requests mới
setInterval(() => {
  if (isRecording && capturedRequests.length > 0) {
    syncToBridge(capturedRequests);
  }
}, 5000);
