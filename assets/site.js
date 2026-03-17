window.adobeDataLayer = window.adobeDataLayer || [];

const pageMeta = document.body.dataset;

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
