# Login State Tracking Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a shared pseudo-login UI, persist login state across pages, and send login-related Web SDK context for page views plus login/logout events.

**Architecture:** Keep the site static and implement the feature in the existing shared frontend assets. Add a small header mount point to each page, centralize login state and analytics enrichment inside `assets/site.js`, and verify behavior with a browser-based acceptance test plus manual `/ee` inspection.

**Tech Stack:** Static HTML, shared CSS, vanilla JavaScript, Python http server, Playwright for browser verification

---

### Task 1: Add a failing browser acceptance test for login state UX

**Files:**
- Create: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`
- Test: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`

- [ ] **Step 1: Write the failing test**
Create a Playwright-driven Python test that opens `index.html`, expects a `Log in` control in the shared header, logs in with an account display name, verifies the greeting text, navigates to another page, and verifies the state persists.

- [ ] **Step 2: Run test to verify it fails**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: FAIL because the login UI and persistence do not exist yet.

- [ ] **Step 3: Add minimal test harness support**
If needed for local serving, add only the smallest helper code inside the test file to start a temporary HTTP server and launch Playwright.

- [ ] **Step 4: Run test again to confirm the failure is still feature-related**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: FAIL on missing login controls or missing persisted greeting, not on test harness errors.

### Task 2: Add shared header mount points and styling for login UI

**Files:**
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/index.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/product-a.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/product-b.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/product-c.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/order1.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/order2.html`
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/assets/styles.css`
- Test: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`

- [ ] **Step 1: Add a login UI mount point to each shared header**
Insert a dedicated element in the header navigation area for the login component without changing the existing primary navigation labels or order.

- [ ] **Step 2: Add failing expectation for the rendered header states**
Extend the acceptance test to expect the guest state, expanded input state, logged-in greeting state, and logout control.

- [ ] **Step 3: Run test to verify it fails**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: FAIL because the component still has no rendering logic.

- [ ] **Step 4: Add minimal CSS for the login UI**
Style the inline login panel so it fits within the current header system on desktop and wraps cleanly on smaller widths.

### Task 3: Implement login state storage and shared header behavior

**Files:**
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/assets/site.js`
- Test: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`

- [ ] **Step 1: Add a failing persistence assertion**
Update the acceptance test to verify that a login on `index.html` persists after navigation to another page and after a reload.

- [ ] **Step 2: Run test to verify it fails**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: FAIL because no state is stored or restored yet.

- [ ] **Step 3: Implement minimal login state behavior**
Add a small login state module inside `site.js` to read/write `localStorage`, render guest vs. logged-in header states, validate trimmed input, and support logout.

- [ ] **Step 4: Run test to verify it passes**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: PASS.

### Task 4: Enrich analytics payloads and debug display with account fields

**Files:**
- Modify: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/assets/site.js`
- Test: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`

- [ ] **Step 1: Add a failing analytics assertion**
Extend the browser test to inspect `window.adobeDataLayer` and verify that page views include `_acssandboxgdctwo.account.status`, login success adds `_acssandboxgdctwo.account.displayName`, and logout resets status to `logged_out`.

- [ ] **Step 2: Run test to verify it fails**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: FAIL because the analytics payloads do not yet carry the new account context.

- [ ] **Step 3: Implement minimal analytics enrichment**
Update page view generation and login/logout event pushes in `site.js` so they emit the account context only for the scoped events in the spec. Update the debug panel’s important field extraction so account status and display name are visible when present in `/ee` payloads.

- [ ] **Step 4: Run test to verify it passes**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: PASS.

### Task 5: Final verification

**Files:**
- Test: `/Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite/tests/test_login_state.py`

- [ ] **Step 1: Run the acceptance test suite**
Run: `cd /Users/makutaga/Library/CloudStorage/OneDrive-Adobe/Apps/codex/demosite && python3 -m unittest tests.test_login_state`
Expected: PASS.

- [ ] **Step 2: Manually verify the static site**
Serve the site locally and check the login UI on Home, Product, and Order pages, including logout and mobile wrap behavior.

- [ ] **Step 3: Manually verify Adobe request visibility**
Open the debug window, log in, browse pages, and confirm the `/ee` request payloads or debug summaries expose account status and display name.
