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

const removeUndefinedDeep = (value) => {
  if (Array.isArray(value)) {
    return value
      .map((item) => removeUndefinedDeep(item))
      .filter((item) => item !== undefined);
  }

  if (value && typeof value === "object") {
    const next = Object.fromEntries(
      Object.entries(value)
        .map(([key, child]) => [key, removeUndefinedDeep(child)])
        .filter(([, child]) => child !== undefined)
    );
    return Object.keys(next).length > 0 ? next : undefined;
  }

  return value === undefined ? undefined : value;
};

const pruneRequestPayload = (payload) => {
  const cloned = cloneForDisplay(payload);

  if (!cloned || typeof cloned !== "object") {
    return cloned;
  }

  if (cloned.query?.personalization) {
    delete cloned.query.personalization;
    if (Object.keys(cloned.query).length === 0) {
      delete cloned.query;
    }
  }

  if (cloned.query?.identity) {
    delete cloned.query.identity.fetch;
    delete cloned.query.identity.meta;
    if (Object.keys(cloned.query.identity).length === 0) {
      delete cloned.query.identity;
    }
    if (Object.keys(cloned.query).length === 0) {
      delete cloned.query;
    }
  }

  if (Array.isArray(cloned.events)) {
    cloned.events = cloned.events.map((event) => {
      if (!event || typeof event !== "object") {
        return event;
      }

      if (event.xdm?.device) {
        delete event.xdm.device.screenHeight;
        delete event.xdm.device.screenWidth;
        delete event.xdm.device.screenOrientation;
      }

      delete event.xdm?.environment;
      delete event.xdm?.placeContext;
      delete event.xdm?.implementationDetails;
      delete event.timestamp;

      return event;
    });
  }

  return removeUndefinedDeep(cloned);
};

const extractImportantFields = (payload, parsedUrl) => {
  const firstEvent = Array.isArray(payload?.events) ? payload.events[0] : null;
  const xdm = firstEvent?.xdm || {};
  const web = xdm.web || {};
  const webPageDetails = web.webPageDetails || {};
  const webReferrer = web.webReferrer || {};
  const commerce = xdm.commerce || {};
  const identityMap = xdm.identityMap || {};
  const implementationDetails = xdm.implementationDetails || {};
  const productListItems = Array.isArray(xdm.productListItems) ? xdm.productListItems : [];

  return {
    timestamp: firstEvent?.timestamp || null,
    eventType: firstEvent?.eventType || null,
    pageName: webPageDetails.name || null,
    pageUrl: webPageDetails.URL || null,
    webReferrer: webReferrer.URL || null,
    pageView: commerce.pageViews?.value || null,
    productViews: commerce.productViews?.value || null,
    purchases: commerce.purchases?.value || null,
    purchaseId: commerce.order?.purchaseID || null,
    productListItems: productListItems.map((item) => ({
      name: item.name || null,
      sku: item.SKU || null,
      quantity: item.quantity || null,
      priceTotal: item.priceTotal || null
    })),
    identityMap: cloneForDisplay(identityMap),
    implementation: {
      name: implementationDetails.name || null,
      version: implementationDetails.version || null,
      environment: implementationDetails.environment || null
    }
  };
};

const escapeHtml = (value) =>
  String(value).replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");

const renderDefinition = (label, value) =>
  value || value === 0
    ? `
  <div class="debug-definition">
    <dt>${escapeHtml(label)}</dt>
    <dd>${escapeHtml(value)}</dd>
  </div>
`
    : "";

const renderJsonTree = (value, key = null) => {
  if (value === null) {
    return `
      <div class="json-tree__row">
        ${key ? `<span class="json-tree__key">${escapeHtml(key)}</span>` : ""}
        <span class="json-tree__value json-tree__value--null">null</span>
      </div>
    `;
  }

  if (typeof value !== "object") {
    const modifier =
      typeof value === "string"
        ? "json-tree__value--string"
        : typeof value === "number"
          ? "json-tree__value--number"
          : typeof value === "boolean"
            ? "json-tree__value--boolean"
            : "";
    return `
      <div class="json-tree__row">
        ${key ? `<span class="json-tree__key">${escapeHtml(key)}</span>` : ""}
        <span class="json-tree__value ${modifier}">${escapeHtml(value)}</span>
      </div>
    `;
  }

  const entries = Array.isArray(value)
    ? value.map((item, index) => [String(index), item])
    : Object.entries(value);
  const summary = key || (Array.isArray(value) ? "[]" : "{}");

  return `
    <details class="json-tree__node" open>
      <summary class="json-tree__summary">${escapeHtml(summary)}</summary>
      <div class="json-tree__children">
        ${entries.map(([childKey, childValue]) => renderJsonTree(childValue, childKey)).join("")}
      </div>
    </details>
  `;
};

let debugPanelElements = null;

const renderDebugPanel = () => {
  if (!debugPanelElements) {
    return;
  }

  debugPanelElements.history.innerHTML = "";

  if (debugState.edgeRequests.length === 0) {
    const empty = document.createElement("p");
    empty.className = "debug-panel__empty";
    empty.textContent = "Waiting for Adobe Edge /ee requests...";
    debugPanelElements.history.appendChild(empty);
    return;
  }

  debugState.edgeRequests.forEach((entry, index) => {
    const important = entry.important || {};
    const pageFile = (() => {
      if (!important.pageUrl) return null;
      try {
        const pathname = new URL(important.pageUrl).pathname || "/";
        const segments = pathname.split("/").filter(Boolean);
        return segments.length === 0 ? "index.html" : segments[segments.length - 1];
      } catch {
        return important.pageUrl;
      }
    })();
    const itemLabel = [important.eventType, pageFile].filter(Boolean).join(" | ") || entry.summary || "/ee request";
    const item = document.createElement("section");
    item.className = "debug-history-item";
    item.innerHTML = `
      <div class="debug-history-item__title">
        <strong>${index + 1}. ${escapeHtml(itemLabel)}</strong>
        <span>${escapeHtml(important.timestamp || entry.capturedAt)}</span>
      </div>
      <div class="json-tree">
        ${renderJsonTree(entry.tree, "payload")}
      </div>
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

const captureEdgeRequest = ({ url, body }) => {
  const parsedUrl = new URL(url, window.location.origin);
  const payload = safeJsonParse(body);
  if (Array.isArray(payload?.events) && payload.events.some((entry) => entry?.eventType === "decisioning.propositionDisplay")) {
    return;
  }
  const eventTypes =
    Array.isArray(payload?.events) && payload.events.length > 0
      ? payload.events.map((entry) => entry.eventType || "(unknown)").join(", ")
      : null;

  debugState.edgeRequests = trimEntries([
    {
      capturedAt: new Date().toISOString(),
      summary: eventTypes || parsedUrl.pathname,
      url: parsedUrl.toString(),
      query: Object.fromEntries(parsedUrl.searchParams.entries()),
      body: cloneForDisplay(payload),
      tree: pruneRequestPayload(payload),
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
    <div class="debug-panel__drawer is-open">
      <div class="debug-panel__header">
        <button class="debug-panel__toggle" type="button" aria-expanded="true">Debug Window</button>
        <button class="debug-panel__clear" type="button">Clear history</button>
      </div>
      <div class="debug-panel__content" data-debug-content>
        <div class="debug-history" data-debug-history></div>
      </div>
    </div>
  `;

  document.body.appendChild(shell);

  debugPanelElements = {
    history: shell.querySelector("[data-debug-history]")
  };

  shell.querySelector(".debug-panel__clear").addEventListener("click", clearEdgeRequests);
  shell.querySelector(".debug-panel__toggle").addEventListener("click", () => {
    const drawer = shell.querySelector(".debug-panel__drawer");
    const content = shell.querySelector("[data-debug-content]");
    const toggle = shell.querySelector(".debug-panel__toggle");
    const isOpen = drawer.classList.toggle("is-open");
    content.hidden = !isOpen;
    toggle.setAttribute("aria-expanded", String(isOpen));
  });

  renderDebugPanel();
};

const originalFetch = window.fetch.bind(window);
window.fetch = async (...args) => {
  const [resource, init] = args;
  const url = typeof resource === "string" ? resource : resource?.url;
  const body = init?.body || resource?.body;

  if (isAdobeEdgeRequest(url)) {
    captureEdgeRequest({
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
