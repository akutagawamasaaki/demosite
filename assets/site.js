window.adobeDataLayer = window.adobeDataLayer || [];

const pageMeta = document.body.dataset;
const EDGE_HISTORY_STORAGE_KEY = "adobeEdgeDebugHistory";
const ACCOUNT_STORAGE_KEY = "demoAccountState";
const ACCOUNT_NAMESPACE = "_acssandboxgdctwo";
const debugState = {
  edgeRequests: []
};
const accountUiState = {
  isFormOpen: false,
  error: ""
};
let nextRequestSequence = 1;

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

const isAdobeEdgeRequest = (url) =>
  typeof url === "string" &&
  (url.includes("/ee/") || url.includes("/ee?") || url.includes("/interact") || url.includes("edge.adobedc.net"));

const trimEntries = (entries) => entries.slice(0, 20);

const getEventType = (payloadOrEntry) => {
  if (payloadOrEntry && payloadOrEntry.important && typeof payloadOrEntry.important.eventType === "string") {
    return payloadOrEntry.important.eventType;
  }

  if (payloadOrEntry && Array.isArray(payloadOrEntry.events)) {
    const first = payloadOrEntry.events[0];
    return (first && (first.eventType || (first.xdm && first.xdm.eventType))) || null;
  }

  return (payloadOrEntry && payloadOrEntry.eventType) || null;
};

const getEventSuffix = (eventType) => {
  if (typeof eventType !== "string" || !eventType) {
    return null;
  }

  const parts = eventType.split(".");
  return parts[parts.length - 1] || eventType;
};

const formatDebugValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return null;
  }

  if (Array.isArray(value)) {
    const joined = value.map((entry) => formatDebugValue(entry)).filter(Boolean).join(" / ");
    return joined || null;
  }

  if (typeof value === "object") {
    return JSON.stringify(value);
  }

  return String(value);
};

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

  if (cloned.query && cloned.query.personalization) {
    delete cloned.query.personalization;
    delete cloned.query.configId;
    delete cloned.query.requestId;
    if (Object.keys(cloned.query).length === 0) {
      delete cloned.query;
    }
  }

  if (cloned.query) {
    delete cloned.query.configId;
    delete cloned.query.requestId;
    if (Object.keys(cloned.query).length === 0) {
      delete cloned.query;
    }
  }

  if (cloned.meta) {
    delete cloned.meta;
  }

  if (cloned.query && cloned.query.identity) {
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

      if (event.query && event.query.personalization) {
        delete event.query.personalization;
        if (Object.keys(event.query).length === 0) {
          delete event.query;
        }
      }

      if (event.xdm && event.xdm.device) {
        delete event.xdm.device.screenHeight;
        delete event.xdm.device.screenWidth;
        delete event.xdm.device.screenOrientation;
      }

      if (event.xdm) {
        delete event.xdm.environment;
        delete event.xdm.placeContext;
        delete event.xdm.implementationDetails;
        delete event.xdm.timestamp;
      }
      delete event.timestamp;

      return event;
    });
  }

  return removeUndefinedDeep(cloned);
};

const extractImportantFields = (payload, parsedUrl) => {
  const firstEvent = payload && Array.isArray(payload.events) ? payload.events[0] : null;
  const xdm = (firstEvent && firstEvent.xdm) || {};
  const web = xdm.web || {};
  const webPageDetails = web.webPageDetails || {};
  const webReferrer = web.webReferrer || {};
  const commerce = xdm.commerce || {};
  const identityMap = xdm.identityMap || {};
  const implementationDetails = xdm.implementationDetails || {};
  const productListItems = Array.isArray(xdm.productListItems) ? xdm.productListItems : [];
  const account = (xdm[ACCOUNT_NAMESPACE] && xdm[ACCOUNT_NAMESPACE].account) || {};

  return {
    eventType: (firstEvent && (firstEvent.eventType || (firstEvent.xdm && firstEvent.xdm.eventType))) || null,
    pageName: webPageDetails.name || null,
    pageUrl: webPageDetails.URL || null,
    webReferrer: webReferrer.URL || null,
    pageView: (commerce.pageViews && commerce.pageViews.value) || null,
    productViews: (commerce.productViews && commerce.productViews.value) || null,
    purchases: (commerce.purchases && commerce.purchases.value) || null,
    purchaseId: (commerce.order && commerce.order.purchaseID) || null,
    productListItems: productListItems.map((item) =>
      [item.name, item.SKU ? `SKU:${item.SKU}` : null, item.quantity ? `Qty:${item.quantity}` : null]
        .filter(Boolean)
        .join(" ")
    ),
    identityMap: Object.entries(identityMap).map(([namespace, items]) => {
      const ids = Array.isArray(items)
        ? items.map((item) => item && item.id).filter(Boolean).join(", ")
        : "";
      return ids ? `${namespace}: ${ids}` : namespace;
    }),
    implementation: [implementationDetails.name, implementationDetails.version].filter(Boolean).join(" "),
    accountStatus: account.status || null,
    accountDisplayName: account.displayName || null
  };
};

const escapeHtml = (value) =>
  String(value).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

const formatLabelSegment = (segment) => {
  if (!segment) {
    return "";
  }

  if (/^\d+$/.test(segment)) {
    return `#${segment}`;
  }

  if (segment === "URL" || segment === "SKU" || segment === "ID") {
    return segment;
  }

  return segment
    .replace(/([a-z0-9])([A-Z])/g, "$1 $2")
    .replace(/[_-]/g, " ")
    .replace(/\b\w/g, (char) => char.toUpperCase());
};

const formatFieldLabel = (path) => {
  const filtered = path.filter(Boolean).filter((segment) => segment !== "events" && segment !== "0" && segment !== "xdm");
  const normalized = filtered.join(".");
  const aliases = {
    "web.webPageDetails.URL": "URL",
    "web.webPageDetails.name": "Page Name",
    "web.webPageDetails.viewName": "View Name",
    "web.webReferrer.URL": "Referrer",
    "commerce.pageViews.value": "Page Views / Value",
    "commerce.productViews.value": "Product Views",
    "commerce.purchases.value": "Purchases",
    "commerce.order.purchaseID": "Purchase ID",
    [`${ACCOUNT_NAMESPACE}.account.status`]: "Account Status",
    [`${ACCOUNT_NAMESPACE}.account.displayName`]: "Account Display Name",
    "_experience.analytics.customDimensions.eVars.eVar1": "E Var1",
    "_experience.analytics.customDimensions.props.prop1": "Prop1",
    "marketing.trackingCode": "Tracking Code"
  };

  if (aliases[normalized]) {
    return aliases[normalized];
  }

  return filtered.map((segment) => formatLabelSegment(segment)).join(" / ");
};

const flattenDisplayFields = (value, path = []) => {
  if (value === null || value === undefined || value === "") {
    return [];
  }

  if (Array.isArray(value)) {
    if (value.length === 0) {
      return [];
    }

    if (value.every((item) => item === null || item === undefined || typeof item !== "object")) {
      return [{ label: formatFieldLabel(path), value: value.join(" / ") }];
    }

    return value.flatMap((item, index) => flattenDisplayFields(item, [...path, String(index)]));
  }

  if (typeof value === "object") {
    return Object.entries(value).flatMap(([key, child]) => flattenDisplayFields(child, [...path, key]));
  }

  return [{ label: formatFieldLabel(path), value: value }];
};

const renderDefinition = (label, value) => {
  const formatted = formatDebugValue(value);
  if (!formatted && formatted !== "0") {
    return "";
  }

  return `
    <div class="debug-definition">
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(formatted)}</dd>
    </div>
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
    const displayFields = flattenDisplayFields(entry.tree || {}).filter(
      (field) => field.label && field.label !== "Event Type"
    );
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
    const eventSuffix = getEventSuffix(important.eventType);
    const itemLabel = pageFile
      ? `${pageFile}${eventSuffix ? ` (${eventSuffix})` : ""}`
      : entry.summary || "/ee request";
    const item = document.createElement("section");
    item.className = "debug-history-item";
    item.innerHTML = `
      <div class="debug-history-item__title">
        <strong>${escapeHtml(entry.sequence || index + 1)}. ${escapeHtml(itemLabel)}</strong>
      </div>
      <dl class="debug-history-item__grid">
        ${displayFields.map((field) => renderDefinition(field.label, field.value)).join("")}
      </dl>
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
      debugState.edgeRequests = trimEntries(
        parsed
          .map((entry) => cloneForDisplay(entry))
          .filter((entry) => getEventType(entry) !== "decisioning.propositionDisplay")
          .map((entry) => ({
            ...entry,
            tree: entry && entry.body ? pruneRequestPayload(entry.body) : entry && entry.tree,
            important:
              entry && entry.body && entry.url
                ? extractImportantFields(entry.body, new URL(entry.url, window.location.origin))
                : entry && entry.important
          }))
      );
      const maxSequence = debugState.edgeRequests.reduce(
        (max, entry) => Math.max(max, Number((entry && entry.sequence) || 0)),
        0
      );
      nextRequestSequence = maxSequence + 1;
    }
  } catch {
    debugState.edgeRequests = [];
    nextRequestSequence = 1;
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

const normalizeAccountName = (value) => {
  if (typeof value !== "string") {
    return "";
  }

  return value.trim();
};

const isValidEmail = (value) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);

const getStoredAccount = () => {
  try {
    const stored = safeJsonParse(window.localStorage.getItem(ACCOUNT_STORAGE_KEY));
    if (stored && stored.isLoggedIn === true) {
      const displayName = normalizeAccountName(stored.displayName);
      if (displayName) {
        return {
          isLoggedIn: true,
          displayName
        };
      }
    }
  } catch {
    // Ignore storage failures and fall back to guest state.
  }

  return {
    isLoggedIn: false,
    displayName: ""
  };
};

const setStoredAccount = (account) => {
  try {
    window.localStorage.setItem(ACCOUNT_STORAGE_KEY, JSON.stringify(account));
  } catch {
    // Ignore storage failures and keep the UI responsive.
  }
};

const clearStoredAccount = () => {
  try {
    window.localStorage.removeItem(ACCOUNT_STORAGE_KEY);
  } catch {
    // Ignore storage failures and clear the in-memory state only.
  }
};

const buildIdentityMap = ({ account, includeEmailIdentity = true, authenticatedState = "authenticated" } = {}) => {
  if (!includeEmailIdentity || !account || !account.isLoggedIn || !account.displayName) {
    return undefined;
  }

  return {
    Email: [
      {
        id: account.displayName,
        authenticatedState,
        primary: true
      }
    ]
  };
};

const getAccountContext = ({ includeDisplayName = true, account = getStoredAccount(), statusOverride } = {}) => {
  const accountContext = {
    status: statusOverride || (account.isLoggedIn ? "logged_in" : "logged_out")
  };

  if (includeDisplayName && account.isLoggedIn && account.displayName) {
    accountContext.displayName = account.displayName;
  }

  return {
    [ACCOUNT_NAMESPACE]: {
      account: accountContext
    }
  };
};

const pushAnalyticsEvent = (payload, options = {}) => {
  const currentAccount = options.account || getStoredAccount();
  const identityMap = buildIdentityMap({
    account: currentAccount,
    includeEmailIdentity: options.includeEmailIdentity
  });

  window.adobeDataLayer.push({
    ...payload,
    ...getAccountContext({ ...options, account: currentAccount }),
    ...(identityMap ? { identityMap } : {})
  });
};

const buildPageDetails = () => ({
  URL: window.location.href,
  name: pageMeta.pageName || document.title,
  viewName: document.title
});

const waitForAlloy = async (attempts = 20) => {
  for (let index = 0; index < attempts; index += 1) {
    if (typeof window.alloy === "function") {
      return window.alloy;
    }

    await new Promise((resolve) => {
      window.setTimeout(resolve, 250);
    });
  }

  return null;
};

const sendAlloyEvent = async (
  eventType,
  {
    includeDisplayName = true,
    account = getStoredAccount(),
    includeEmailIdentity = true,
    authenticatedState = "authenticated",
    statusOverride
  } = {}
) => {
  const alloy = await waitForAlloy();
  if (!alloy) {
    return;
  }

  try {
    await alloy("sendEvent", {
      xdm: {
        eventType,
        web: {
          webPageDetails: buildPageDetails(),
          webReferrer: {
            URL: document.referrer || ""
          }
        },
        ...getAccountContext({ includeDisplayName, account, statusOverride }),
        ...(buildIdentityMap({ account, includeEmailIdentity, authenticatedState })
          ? { identityMap: buildIdentityMap({ account, includeEmailIdentity, authenticatedState }) }
          : {})
      }
    });
  } catch {
    // Keep the demo UI functional even if direct Web SDK dispatch fails.
  }
};

const renderLoginUi = () => {
  document.querySelectorAll("[data-login-root]").forEach((root) => {
    const storedAccount = getStoredAccount();

    if (storedAccount.isLoggedIn) {
      root.innerHTML = `
        <div class="account-nav">
          <span class="account-nav__greeting">こんにちは、${escapeHtml(storedAccount.displayName)}</span>
          <button class="account-nav__logout" type="button">Log out</button>
        </div>
      `;
      root.querySelector(".account-nav__logout").addEventListener("click", () => {
        const accountBeforeLogout = storedAccount;
        accountUiState.isFormOpen = false;
        accountUiState.error = "";
        clearStoredAccount();
        renderLoginUi();
        pushAnalyticsEvent(
          {
            event: "logout"
          },
          { includeDisplayName: false, account: accountBeforeLogout, statusOverride: "logged_out" }
        );
        sendAlloyEvent("demo.logout", {
          includeDisplayName: false,
          account: accountBeforeLogout,
          authenticatedState: "loggedOut",
          statusOverride: "logged_out"
        });
      });
      return;
    }

    if (!accountUiState.isFormOpen) {
      root.innerHTML = `
        <div class="account-nav">
          <button class="account-nav__button" type="button">Log in</button>
        </div>
      `;
      root.querySelector(".account-nav__button").addEventListener("click", () => {
        accountUiState.isFormOpen = true;
        accountUiState.error = "";
        renderLoginUi();
      });
      return;
    }

    root.innerHTML = `
      <form class="account-nav" data-login-form novalidate>
        <div class="account-nav__panel">
          <div class="account-nav__field">
            <label for="account-name-input">Email</label>
            <input id="account-name-input" name="displayName" type="email" autocomplete="email" inputmode="email" />
          </div>
          <button class="account-nav__submit" type="submit">Submit</button>
          ${accountUiState.error ? `<div class="account-nav__error">${escapeHtml(accountUiState.error)}</div>` : ""}
        </div>
      </form>
    `;

    const form = root.querySelector("[data-login-form]");
    const input = root.querySelector("#account-name-input");
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const displayName = normalizeAccountName(input.value);
      if (!displayName) {
        accountUiState.error = "メールアドレスを入力してください。";
        renderLoginUi();
        return;
      }
      if (!isValidEmail(displayName)) {
        accountUiState.error = "有効なメールアドレスを入力してください。";
        renderLoginUi();
        return;
      }

      const nextAccount = {
        isLoggedIn: true,
        displayName
      };
      setStoredAccount(nextAccount);
      accountUiState.isFormOpen = false;
      accountUiState.error = "";
      renderLoginUi();
      pushAnalyticsEvent({
        event: "login_success"
      }, { account: nextAccount });
      sendAlloyEvent("demo.loginSuccess", { account: nextAccount });
    });

    input.focus();
  });
};

const captureEdgeRequest = ({ url, body }) => {
  const parsedUrl = new URL(url, window.location.origin);
  const payload = safeJsonParse(body);
  if (
    payload &&
    Array.isArray(payload.events) &&
    payload.events.some((entry) => {
      const eventType = (entry && entry.eventType) || (entry && entry.xdm && entry.xdm.eventType);
      return eventType === "decisioning.propositionDisplay";
    })
  ) {
    return;
  }
  const eventTypes =
    payload && Array.isArray(payload.events) && payload.events.length > 0
      ? payload.events.map((entry) => entry.eventType || "(unknown)").join(", ")
      : null;

  debugState.edgeRequests = trimEntries([
    {
      sequence: nextRequestSequence++,
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
  const url = typeof resource === "string" ? resource : resource && resource.url;
  const body = (init && init.body) || (resource && resource.body);

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
renderLoginUi();

pushAnalyticsEvent({
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
sendAlloyEvent("demo.accountStateView");

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
