window.adobeDataLayer = window.adobeDataLayer || [];

const pageMeta = document.body.dataset;
const debugState = {
  dataLayerEvents: [],
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

const trimEntries = (entries) => entries.slice(0, 6);

let debugPanelElements = null;

const renderDebugPanel = () => {
  if (!debugPanelElements) {
    return;
  }

  const latestEvent = debugState.dataLayerEvents[0];
  const latestEdgeRequest = debugState.edgeRequests[0];

  debugPanelElements.eventCount.textContent = String(debugState.dataLayerEvents.length);
  debugPanelElements.requestCount.textContent = String(debugState.edgeRequests.length);
  debugPanelElements.eventName.textContent = latestEvent?.event || "No event yet";
  debugPanelElements.requestName.textContent = latestEdgeRequest?.summary || "No /ee request yet";
  debugPanelElements.eventPayload.textContent = latestEvent
    ? formatPrettyJson(latestEvent)
    : "Waiting for adobeDataLayer events...";
  debugPanelElements.requestPayload.textContent = latestEdgeRequest
    ? formatPrettyJson(latestEdgeRequest)
    : "Waiting for Adobe Edge /ee requests...";
}

const pushDataLayerEvent = (payload) => {
  debugState.dataLayerEvents = trimEntries([
    {
      capturedAt: new Date().toISOString(),
      ...cloneForDisplay(payload)
    },
    ...debugState.dataLayerEvents
  ]);
  renderDebugPanel();
};

const captureEdgeRequest = ({ transport, url, body }) => {
  const parsedUrl = new URL(url, window.location.origin);
  const payload = safeJsonParse(body);
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
      query: Object.fromEntries(parsedUrl.searchParams.entries()),
      body: cloneForDisplay(payload)
    },
    ...debugState.edgeRequests
  ]);
  renderDebugPanel();
};

const createDebugPanel = () => {
  const shell = document.createElement("aside");
  shell.className = "debug-panel";
  shell.innerHTML = `
    <button class="debug-panel__toggle" type="button" aria-expanded="false">Launch Debug</button>
    <div class="debug-panel__drawer" hidden>
      <div class="debug-panel__header">
        <div>
          <strong>Launch / Edge debug</strong>
          <p>adobeDataLayer と /ee リクエストの最新値を画面内で確認できるのだ。</p>
        </div>
      </div>
      <div class="debug-panel__metrics">
        <div class="debug-metric">
          <span>Data Layer</span>
          <strong data-debug-event-count>0</strong>
        </div>
        <div class="debug-metric">
          <span>Edge Requests</span>
          <strong data-debug-request-count>0</strong>
        </div>
      </div>
      <section class="debug-block">
        <div class="debug-block__title">
          <strong>Latest adobeDataLayer event</strong>
          <span data-debug-event-name>No event yet</span>
        </div>
        <pre data-debug-event-payload>Waiting for adobeDataLayer events...</pre>
      </section>
      <section class="debug-block">
        <div class="debug-block__title">
          <strong>Latest /ee request</strong>
          <span data-debug-request-name>No /ee request yet</span>
        </div>
        <pre data-debug-request-payload>Waiting for Adobe Edge /ee requests...</pre>
      </section>
    </div>
  `;

  document.body.appendChild(shell);

  const toggle = shell.querySelector(".debug-panel__toggle");
  const drawer = shell.querySelector(".debug-panel__drawer");

  toggle.addEventListener("click", () => {
    const isOpen = !drawer.hidden;
    drawer.hidden = isOpen;
    toggle.setAttribute("aria-expanded", String(!isOpen));
    toggle.textContent = isOpen ? "Launch Debug" : "Close Debug";
  });

  debugPanelElements = {
    eventCount: shell.querySelector("[data-debug-event-count]"),
    requestCount: shell.querySelector("[data-debug-request-count]"),
    eventName: shell.querySelector("[data-debug-event-name]"),
    requestName: shell.querySelector("[data-debug-request-name]"),
    eventPayload: shell.querySelector("[data-debug-event-payload]"),
    requestPayload: shell.querySelector("[data-debug-request-payload]")
  };

  renderDebugPanel();
};

const originalPush = window.adobeDataLayer.push.bind(window.adobeDataLayer);
window.adobeDataLayer.push = (...entries) => {
  entries.forEach((entry) => pushDataLayerEvent(entry));
  return originalPush(...entries);
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
