window.adobeDataLayer = window.adobeDataLayer || [];

const pageMeta = document.body.dataset;
const EDGE_HISTORY_STORAGE_KEY = "adobeEdgeDebugHistory";
const debugState = {
  edgeRequests: []
};

const safeJsonParse = (value) => {
  if (typeof value !== "string" || !value) {
    return value;
  }

  try {
    return JSON.parse(value);
  } catch {
    return value;
  }
};

const cloneForDisplay = (value) => {
  if (value === undefined) {
    return null;
  }

  try {
    return JSON.parse(JSON.stringify(value));
  } catch {
    return String(value);
  }
};

const formatPrettyJson = (value) => JSON.stringify(value, null, 2);

const isAdobeEdgeRequest = (url) =>
  typeof url === "string" &&
  (url.includes("/ee/") || url.includes("/ee?") || url.includes("/interact") || url.includes("edge.adobedc.net"));

const trimEntries = (entries) => entries.slice(0, 20);

const extractImportantFields = (payload, parsedUrl) => {
  const firstEvent = Array.isArray(payload?.events) ? payload.events[0] : null;
  const xdm = firstEvent?.xdm || {};
  const web = xdm.web || {};
  const webPageDetails = web.webPageDetails || {};
  const commerce = xdm.commerce || {};
  const identityMap = xdm.identityMap || {};
  const implementationDetails = xdm.implementationDetails || {};

  return {
    timestamp: firstEvent?.timestamp || null,
    eventType: firstEvent?.eventType || null,
    requestId: parsedUrl.searchParams.get("requestId") || parsedUrl.searchParams.get("requestid") || null,
    configId: parsedUrl.searchParams.get("configId") || parsedUrl.searchParams.get("configid") || null,
    pageName: webPageDetails.name || null,
    pageUrl: webPageDetails.URL || null,
    pageView: commerce.pageViews?.value || null,
    productViews: commerce.productViews?.value || null,
    purchases: commerce.purchases?.value || null,
    identityNamespaces: Object.keys(identityMap),
    implementation: {
      name: implementationDetails.name || null,
      version: implementationDetails.version || null,
      environment: implementationDetails.environment || null
    }
  };
};

const shouldIgnoreEdgeRequest = (payload) =>
  Array.isArray(payload?.events) &&
  payload.events.some((entry) => entry?.xdm?._experience?.decisioning);

let debugPanelElements = null;

const renderDebugPanel = () => {
  if (!debugPanelElements) {
    return;
  }

  debugPanelElements.requestCount.textContent = String(debugState.edgeRequests.length);
  debugPanelElements.history.innerHTML = "";

  if (debugState.edgeRequests.length === 0) {
    const empty = document.createElement("p");
    empty.className = "debug-panel__empty";
    empty.textContent = "Waiting for Adobe Edge /ee requests...";
    debugPanelElements.history.appendChild(empty);
    return;
  }

  debugState.edgeRequests.forEach((entry, index) => {
    const item = document.createElement("section");
    item.className = "debug-history-item";
    item.innerHTML = `
      <div class="debug-history-item__title">
        <strong>${index + 1}. ${entry.summary || "/ee request"}</strong>
        <span>${entry.capturedAt}</span>
      </div>
      <div class="debug-history-item__meta">
        <span>${entry.transport}</span>
        <span>${entry.url}</span>
      </div>
      <pre>${formatPrettyJson(entry.important)}</pre>
    `;
    debugPanelElements.history.appendChild(item);
  });
};

const persistEdgeRequests = () => {
  try {
    window.localStorage.setItem(EDGE_HISTORY_STORAGE_KEY, JSON.stringify(debugState.edgeRequests));
  } catch {
    // Ignore storage failures and keep the panel functional in-memory.
  }
};

const restoreEdgeRequests = () => {
  try {
    const stored = window.localStorage.getItem(EDGE_HISTORY_STORAGE_KEY);
    const parsed = safeJsonParse(stored);
    if (Array.isArray(parsed)) {
      debugState.edgeRequests = trimEntries(parsed.map((entry) => cloneForDisplay(entry)));
    }
  } catch {
    debugState.edgeRequests = [];
  }
};

const clearEdgeRequests = () => {
  debugState.edgeRequests = [];
  try {
    window.localStorage.removeItem(EDGE_HISTORY_STORAGE_KEY);
  } catch {
    // Ignore storage failures and clear the in-memory history only.
  }
  renderDebugPanel();
};

const captureEdgeRequest = ({ transport, url, body }) => {
  const parsedUrl = new URL(url, window.location.origin);
  const payload = safeJsonParse(body);
  if (shouldIgnoreEdgeRequest(payload)) {
    return;
  }

  const eventTypes =
    Array.isArray(payload?.events) && payload.events.length > 0
      ? payload.events.map((entry) => entry.eventType || "(unknown)").join(", ")
      : null;

  debugState.edgeRequests = trimEntries([
    {
      capturedAt: new Date().toISOString(),
      transport,
      summary: eventTypes || parsedUrl.pathname,
      url: parsedUrl.toString(),
      important: extractImportantFields(payload, parsedUrl)
    },
    ...debugState.edgeRequests
  ]);
  persistEdgeRequests();
  renderDebugPanel();
};

const createDebugPanel = () => {
  const shell = document.createElement("aside");
  shell.className = "debug-panel";
  shell.innerHTML = `
    <div class="debug-panel__drawer">
      <div class="debug-panel__header">
        <div>
          <strong>Launch / Edge debug</strong>
          <p>/ee リクエスト履歴をページ上で継続確認できます。</p>
        </div>
        <button class="debug-panel__clear" type="button">Clear history</button>
      </div>
      <div class="debug-panel__metrics">
        <div class="debug-metric">
          <span>/ee Requests</span>
          <strong data-debug-request-count>0</strong>
        </div>
      </div>
      <div class="debug-history" data-debug-history></div>
    </div>
  `;

  document.body.appendChild(shell);

  debugPanelElements = {
    requestCount: shell.querySelector("[data-debug-request-count]"),
    history: shell.querySelector("[data-debug-history]")
  };

  shell.querySelector(".debug-panel__clear").addEventListener("click", clearEdgeRequests);

  renderDebugPanel();
};

const originalFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const [resource, init] = args;
  const url = typeof resource === "string" ? resource : resource?.url;
  const body = init?.body || resource?.body;

  if (isAdobeEdgeRequest(url)) {
    captureEdgeRequest({
      transport: "fetch",
      url,
      body
    });
  }

  return originalFetch(...args);
};

const originalXhrOpen = XMLHttpRequest.prototype.open;
const originalXhrSend = XMLHttpRequest.prototype.send;

XMLHttpRequest.prototype.open = function patchedOpen(method, url, ...rest) {
  this.__debugUrl = url;
  return originalXhrOpen.call(this, method, url, ...rest);
};

XMLHttpRequest.prototype.send = function patchedSend(body) {
  if (isAdobeEdgeRequest(this.__debugUrl)) {
    captureEdgeRequest({
      transport: "xhr",
      url: this.__debugUrl,
      body
    });
  }

  return originalXhrSend.call(this, body);
};

restoreEdgeRequests();

window.adobeDataLayer.push({
  event: "demo.pageView",
  page: {
    name: pageMeta.pageName || document.title,
    category: pageMeta.pageCategory || "demo",
    siteSection: pageMeta.siteSection || "marketing-demo"
  },
  experience: {
    platform: "web",
    locale: "ja-JP"
  }
});

document.querySelectorAll("[data-analytics-event]").forEach((element) => {
  element.addEventListener("click", () => {
    const payload = {
      event: element.dataset.analyticsEvent,
      interaction: {
        label: element.dataset.analyticsLabel || element.textContent.trim(),
        destination: element.getAttribute("href") || null
      }
    };

    if (element.dataset.productName) {
      payload.product = {
        name: element.dataset.productName
      };
      localStorage.setItem("selectedProduct", element.dataset.productName);
    }

    window.adobeDataLayer.push(payload);
  });
});

document.querySelectorAll("[data-prefill-product]").forEach((input) => {
  const storedProduct = localStorage.getItem("selectedProduct");
  if (storedProduct && !input.value) {
    input.value = storedProduct;
  }
});

const activateFlash = (target, message) => {
  if (!target) return;
  target.textContent = message;
  target.classList.add("is-visible");
};

document.querySelectorAll("[data-lead-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const payload = {
      event: "demo.leadSubmitted",
      form: Object.fromEntries(formData.entries())
    };
    window.adobeDataLayer.push(payload);

    const product = formData.get("product");
    if (typeof product === "string" && product) {
      localStorage.setItem("selectedProduct", product);
    }

    activateFlash(
      document.querySelector("[data-form-feedback]"),
      "リクエストを受け付けました。次の注文ページでコンバージョン計測も確認できます。"
    );
  });
});

document.querySelectorAll("[data-order-form]").forEach((form) => {
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const addons = formData.getAll("addons");
    const payload = {
      event: "demo.purchase",
      commerce: {
        product: formData.get("product"),
        plan: formData.get("plan"),
        addons,
        value: formData.get("price")
      }
    };
    window.adobeDataLayer.push(payload);

    activateFlash(
      document.querySelector("[data-order-feedback]"),
      "デモ注文を完了しました。AA/CJA 側で購入イベントとプラン属性を確認できます。"
    );
  });
});

createDebugPanel();
