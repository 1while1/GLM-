(() => {
  "use strict";

  if (window.top !== window.self) {
    return;
  }

  if (window.__GLM_GRABBER_INJECTED__) {
    return;
  }
  window.__GLM_GRABBER_INJECTED__ = true;

  const DEFAULT_CONFIG = {
    target: { plan: "Pro", period: "quarter", expected_price_text: "", button_selector: "" },
    timing: {
      start_at: null,
      normal_check_interval_ms: 200,
      armed_check_interval_ms: 20,
      armed_before_seconds: 0,
      armed_after_seconds: 120,
      click_cooldown_ms: 80,
      max_click_attempts: 0,
      crowd_retry_clicks_before_reload: 15,
      recovery_reload_interval_ms: 1500,
      server_time_offset_ms: 0,
      t0_reload: false
    },
    safety: {
      auto_continue_notice: true,
      force_unlock: true,
      stop_before_payment: true,
      pause_on_unknown: true
    }
  };

  const config = merge(DEFAULT_CONFIG, window.__GLM_GRABBER_CONFIG__ || {});
  const state = {
    stopped: false,
    paused: false,
    requestInFlight: false,
    clickAttempts: 0,
    crowdClickAttempts: 0,
    lastClickAt: 0,
    lastState: "INIT",
    lastDiagnosticAt: 0,
    lastManualWaitAt: 0,
    lastScrollAt: 0,
    t0ReloadRequested: false,
    t0ReloadRequestedAt: 0,
    periodClickAttempts: 0,
    observerScheduled: false
  };

  const PERIOD_TEXT = {
    month: "连续包月",
    quarter: "连续包季",
    year: "连续包年"
  };
  const BUY_TEXT_PATTERN = /特惠订阅|立即订阅|即刻订阅|订阅|抢购|购买|开通/;
  const LOCKED_BUY_TEXT_PATTERN = /暂时售罄|售罄|补货|开抢|开售|即将开售|即将开始|待开抢|待售/;
  const CROWDED_RETRY_TEXT_PATTERN = /抢购人数过多|人数过多|刷新再试|请刷新|稍后再试|系统繁忙|访问人数过多/;

  installNetworkHooks();
  installObserver();
  setInterval(tick, config.timing.normal_check_interval_ms);
  setInterval(tick, config.timing.armed_check_interval_ms);
  report("injector_ready", { target: config.target });
  tick();

  function tick() {
    if (state.stopped || state.paused) return;
    const signals = collectSignals();
    if (!signals.recoveryReload && state.crowdClickAttempts > 0) {
      state.crowdClickAttempts = 0;
    }
    const nextState = classify(signals);
    if (nextState !== state.lastState) {
      state.lastState = nextState;
      report("state", { state: nextState, signals: summarizeSignals(signals) });
    }
    reportDiagnostic(signals);
    act(nextState, signals);
  }

  function act(nextState, signals) {
    if (nextState === "PAYMENT_HANDOFF") {
      stop("payment_handoff", signals);
      return;
    }
    if (nextState === "CAPTCHA_REQUIRED" || nextState === "LOGIN_REQUIRED") {
      reportManualWait(nextState.toLowerCase(), signals);
      return;
    }
    if (nextState === "TARGET_MISMATCH") {
      pause(nextState.toLowerCase(), signals);
      return;
    }
    if (waitingForT0Reload()) return;
    if (shouldRequestT0Reload(signals)) {
      state.t0ReloadRequested = true;
      state.t0ReloadRequestedAt = Date.now();
      report("t0_reload_requested", { target: summarizeSignals(signals).targetSummary });
      return;
    }
    if (signals.buyButton || signals.targetCard || signals.periodButton) {
      scrollNearTarget(signals.buyButton || signals.targetCard || signals.periodButton);
    }
    if (nextState === "CONFIRM_NOTICE" && config.safety.auto_continue_notice) {
      clickControlled(signals.confirmButton, "confirm_notice");
      return;
    }
    if (!signals.periodSelected && signals.periodButton && state.periodClickAttempts < 3) {
      state.periodClickAttempts += 1;
      report("period_select_attempt", {
        period: config.target.period,
        text: compact(signals.periodButton.innerText || "")
      });
      signals.periodButton.click();
      return;
    }
    if (nextState === "READY") {
      clickControlled(signals.buyButton, signals.recoveryReload ? "crowded_retry" : "target_ready");
    }
  }

  function collectSignals() {
    const text = document.body ? document.body.innerText || "" : "";
    const target = findTargetCard();
    const payment = /支付|二维码|收银台|订单号|确认支付/i.test(text) || /pay|checkout/i.test(location.href);
    const captcha = hasVisibleCaptcha();
    const loginButton = findVisibleButton(/^登录\s*\/\s*注册$|^登录$|账号密码登录|手机号登录|获取验证码/);
    const login = Boolean(loginButton) || /账号密码登录|手机号登录|获取验证码|请输入手机号|请输入密码/i.test(text);
    const confirmButton = findVisibleButton(/已知悉，继续订阅|继续订阅|我知道了/);
    const confirmNotice = Boolean(confirmButton) && !payment && !captcha;

    return {
      text,
      payment,
      captcha,
      login,
      confirmNotice,
      confirmButton,
      requestInFlight: state.requestInFlight,
      recoveryReload: hasCrowdedRefreshMessage(target.card, text),
      targetReady: Boolean(target.card && target.periodSelected && target.buyButton && !target.mismatch),
      targetCardFound: Boolean(target.card),
      targetButtonFound: Boolean(target.buyButton),
      targetMismatch: target.mismatch,
      targetCard: target.card,
      buyButton: target.buyButton,
      periodSelected: target.periodSelected,
      periodButton: target.periodButton,
      targetSummary: target.summary
    };
  }

  function classify(signals) {
    if (signals.payment) return "PAYMENT_HANDOFF";
    if (signals.captcha) return "CAPTCHA_REQUIRED";
    if (signals.login) return "LOGIN_REQUIRED";
    if (signals.targetMismatch) return "TARGET_MISMATCH";
    if (signals.requestInFlight) return "REQUEST_IN_FLIGHT";
    if (signals.recoveryReload && inArmedWindow() && state.crowdClickAttempts >= crowdRetryClicksBeforeReload()) return "RECOVERY_RELOAD";
    if (signals.confirmNotice) return "CONFIRM_NOTICE";
    if (signals.targetReady && inArmedWindow()) return "READY";
    if (signals.targetReady) return "WAITING_FOR_TIME";
    if (signals.recoveryReload && inArmedWindow() && signals.periodButton && !signals.periodSelected) return "TARGET_CARD_FOUND";
    if (signals.recoveryReload && inArmedWindow()) return "RECOVERY_RELOAD";
    if (signals.recoveryReload) return "WAITING_FOR_TIME";
    if (signals.targetCardFound) return "TARGET_CARD_FOUND";
    return "UNKNOWN";
  }

  function findTargetCard() {
    const plan = config.target.plan;
    const periodText = PERIOD_TEXT[config.target.period] || config.target.period;
    const manual = findManualTarget(plan);
    const match = manual || findPlanCard(plan) || findPlanByHeading(plan);
    const period = findPeriodControl(periodText);
    const mismatch = Boolean(match.card && config.target.expected_price_text && !(match.card.innerText || "").includes(config.target.expected_price_text));

    return {
      card: match.card,
      buyButton: match.button,
      periodSelected: period.selected,
      periodButton: period.button,
      mismatch,
      summary: match.card ? {
        plan,
        period: config.target.period,
        cardText: compact((match.card.innerText || "").slice(0, 300)),
        buttonText: match.button ? compact(match.button.innerText || "") : "",
        buttonLocked: Boolean(match.button && looksLikeLockedBuyControl(match.button)),
        periodSelected: period.selected,
        periodFound: Boolean(period.button)
      } : { plan, period: config.target.period, found: false }
    };
  }

  function findManualTarget(plan) {
    const selector = compact(config.target.button_selector || "");
    if (!selector) return null;
    let matches = [];
    try {
      matches = Array.from(document.querySelectorAll(selector)).filter(visible);
    } catch (error) {
      report("manual_selector_error", { selector, message: String(error && error.message || error) });
      return null;
    }
    const button = matches.find((candidate) => findContainingPlanCard(candidate, plan)) || null;
    if (!button) return null;
    const card = findContainingPlanCard(button, plan);
    if (!card) return null;
    highlightManualTarget(button);
    return { card, button };
  }

  function findContainingPlanCard(button, plan) {
    let current = button;
    for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
      const text = compact(current.innerText || current.textContent || "");
      if (text.includes(plan) && !containsOtherPlan(text, plan)) return current;
    }
    return null;
  }

  function hasVisibleCaptcha() {
    const visibleText = visiblePageText();
    if (/拖动下方拼图|滑块|拼图|安全验证/i.test(visibleText)) return true;
    return Array.from(document.querySelectorAll("iframe, [class*='captcha'], [id*='captcha'], [class*='verify'], [id*='verify']"))
      .some((el) => inViewport(el) && area(el) > 2500);
  }

  function hasCrowdedRefreshMessage(card, pageText) {
    const cardText = compact(card && (card.innerText || card.textContent || "") || "");
    const visibleText = cardText || compact(pageText || "");
    return CROWDED_RETRY_TEXT_PATTERN.test(visibleText);
  }

  function visiblePageText() {
    return Array.from(document.querySelectorAll("body *"))
      .filter((el) => inViewport(el) && area(el) > 0)
      .map((el) => compact(el.innerText || el.textContent || ""))
      .filter((text) => text && text.length < 300)
      .join(" ");
  }

  function findPlanCard(plan) {
    const cards = Array.from(document.querySelectorAll("[class*='package-card'], [class*='plan'], [class*='card'], [class*='package'], [class*='pricing']"))
      .filter((el) => visible(el) && cardLooksLikePlan(el, plan));
    const headingCard = findCardFromPlanHeading(plan);
    if (headingCard) cards.push(headingCard);
    if (cards.length === 0) return null;
    const card = uniqueElements(cards).sort((a, b) => cardScore(a, plan) - cardScore(b, plan))[0];
    return { card, button: findBuyControlIn(card) };
  }

  function findCardFromPlanHeading(plan) {
    const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, div, span"))
      .filter((el) => visible(el) && looksLikePlanHeading(el, plan));
    let best = null;
    let bestScore = Number.POSITIVE_INFINITY;
    for (const heading of headings) {
      let current = heading;
      for (let depth = 0; current && depth < 8; depth += 1, current = current.parentElement) {
        const text = compact(current.innerText || current.textContent || "");
        if (!cardLooksLikePlan(current, plan)) continue;
        const rect = current.getBoundingClientRect();
        const score = depth * 80 + Math.abs(rect.width - 456) + Math.abs(rect.height - 430) * 0.3 + text.length * 0.01;
        if (score < bestScore) {
          best = current;
          bestScore = score;
        }
      }
    }
    return best;
  }

  function findPlanByHeading(plan) {
    const headings = Array.from(document.querySelectorAll("h1, h2, h3, h4, div, span"))
      .filter((el) => visible(el) && looksLikePlanHeading(el, plan));
    const buttons = Array.from(document.querySelectorAll("button, [role='button']"))
      .filter((el) => visible(el) && /特惠订阅|订阅/.test(el.innerText || el.textContent || ""));
    let best = { card: null, button: null, score: Number.POSITIVE_INFINITY };
    for (const heading of headings) {
      const headingRect = heading.getBoundingClientRect();
      const headingCenterX = headingRect.left + headingRect.width / 2;
      for (const button of buttons) {
        const buttonRect = button.getBoundingClientRect();
        const buttonCenterX = buttonRect.left + buttonRect.width / 2;
        const verticalDistance = buttonRect.top - headingRect.bottom;
        const horizontalDistance = Math.abs(buttonCenterX - headingCenterX);
        if (verticalDistance < 0 || verticalDistance > 700) continue;
        if (horizontalDistance > 280) continue;
        const score = verticalDistance + horizontalDistance * 0.6;
        if (score < best.score) {
          best = {
            card: commonAncestor(heading, button),
            button,
            score
          };
        }
      }
    }
    return best;
  }

  function findBuyControlIn(root) {
    const controls = Array.from(root.querySelectorAll("button, [role='button'], a, [class*='btn'], [class*='button']"))
      .filter(visible);
    const candidates = controls.filter(looksLikeActiveBuyControl);
    if (candidates.length > 0) return candidates.sort((a, b) => buyControlScore(a) - buyControlScore(b))[0];
    if (!config.safety.force_unlock) return null;

    const lockedCandidates = controls.filter(looksLikeLockedBuyControl);
    if (lockedCandidates.length === 0) return null;
    return lockedCandidates.sort((a, b) => buyControlScore(a) - buyControlScore(b))[0];
  }

  function findPeriodControl(periodText) {
    const nodes = Array.from(document.querySelectorAll("button, [role='button'], a, li, div, span"))
      .filter((el) => visible(el) && looksLikePeriodControl(el, periodText));
    if (nodes.length === 0) return { selected: false, button: null };
    const button = nodes.sort((a, b) => periodControlScore(a) - periodControlScore(b))[0];
    const selected = nodes.some((el) => {
      const className = String(el.className || "");
      const aria = el.getAttribute("aria-selected") || el.getAttribute("aria-pressed");
      return aria === "true" || /active|selected|current|is-active|checked/.test(className) || nodes.length === 1;
    });
    return { selected, button };
  }

  function clickControlled(button, reason) {
    if (!button || state.stopped || state.paused || state.requestInFlight) return;
    const now = Date.now();
    const maxAttempts = Number(config.timing.max_click_attempts || 0);
    if (maxAttempts > 0 && state.clickAttempts >= maxAttempts) {
      pause("max_click_attempts", { attempts: state.clickAttempts });
      return;
    }
    if (now - state.lastClickAt < config.timing.click_cooldown_ms) return;

    const buttonText = compact(button.innerText || "");
    const crowdedRetry = CROWDED_RETRY_TEXT_PATTERN.test(buttonText);
    state.lastClickAt = now;
    state.clickAttempts += 1;
    if (crowdedRetry) {
      state.crowdClickAttempts += 1;
    } else {
      state.crowdClickAttempts = 0;
    }
    report("click_attempt", {
      reason,
      attempts: state.clickAttempts,
      crowdAttempts: state.crowdClickAttempts,
      text: buttonText
    });

    scrollNearTarget(button, { force: true });
    if (config.safety.force_unlock) unlockButton(button);
    dispatchMouseLikeEvents(button);
    button.click();
  }

  function installNetworkHooks() {
    const originalFetch = window.fetch;
    window.fetch = async function patchedFetch(input, init) {
    const requestInfo = describeRequest(input, init);
      markIfPurchaseRequestStart(requestInfo);
      try {
        const response = await originalFetch.apply(this, arguments);
        reportNetworkResponse(requestInfo, response.status);
        markIfPurchaseRequestEnd(requestInfo, response.status);
        return response;
      } catch (error) {
        markIfPurchaseRequestEnd(requestInfo, 0);
        report("network_error", { request: requestInfo, message: String(error && error.message || error) });
        throw error;
      }
    };

    const originalOpen = XMLHttpRequest.prototype.open;
    const originalSend = XMLHttpRequest.prototype.send;
    XMLHttpRequest.prototype.open = function patchedOpen(method, url) {
      this.__glmGrabberRequest = { method, url: String(url) };
      return originalOpen.apply(this, arguments);
    };
    XMLHttpRequest.prototype.send = function patchedSend(body) {
      const requestInfo = Object.assign({}, this.__glmGrabberRequest || {}, { body: safeBody(body) });
      markIfPurchaseRequestStart(requestInfo);
      this.addEventListener("loadend", () => {
        reportNetworkResponse(requestInfo, this.status);
        markIfPurchaseRequestEnd(requestInfo, this.status);
      });
      return originalSend.apply(this, arguments);
    };
  }

  function markIfPurchaseRequestStart(requestInfo) {
    if (!isLockingPurchaseRequest(requestInfo)) {
      if (isObservedBusinessRequest(requestInfo.url)) report("business_request_seen", { request: requestInfo });
      return;
    }
    state.requestInFlight = true;
    report("purchase_request_start", { request: requestInfo });
  }

  function markIfPurchaseRequestEnd(requestInfo, status) {
    if (!isLockingPurchaseRequest(requestInfo)) return;
    state.requestInFlight = false;
    report("purchase_request_end", { request: requestInfo, status });
  }

  function isLockingPurchaseRequest(requestInfo) {
    const url = String(requestInfo && requestInfo.url || "");
    const method = String(requestInfo && requestInfo.method || "GET").toUpperCase();
    if (method === "GET" && /pricing|productIdInfo|tokenResPack|getTokenMagnitude/i.test(url)) return false;
    return method !== "GET" && /order|subscribe|subscription|purchase|buy|pay/i.test(url);
  }

  function isObservedBusinessRequest(url) {
    return /coding-plan|tokenResPack|productIdInfo|pricing|getTokenMagnitude/i.test(String(url || ""));
  }

  function reportNetworkResponse(requestInfo, status) {
    if (isLockingPurchaseRequest(requestInfo) || isObservedBusinessRequest(requestInfo.url)) {
      report("network_response", { request: requestInfo, status });
    }
  }

  function scrollNearTarget(el, options = {}) {
    if (!el) return;
    const now = Date.now();
    if (!options.force && now - state.lastScrollAt < 1200) return;
    const rect = el.getBoundingClientRect();
    if (!options.force && rect.top >= 120 && rect.bottom <= window.innerHeight - 80) return;
    state.lastScrollAt = now;
    report("scroll_to_target", { text: compact(el.innerText || el.textContent || "").slice(0, 80) });
    el.scrollIntoView({ block: "center", inline: "center", behavior: "instant" });
  }

  function inArmedWindow() {
    if (!config.timing.start_at) return true;
    const targetSeconds = parseTimeToSeconds(config.timing.start_at);
    if (targetSeconds === null) return true;
    const nowSeconds = currentServerSeconds();
    const before = Number(config.timing.armed_before_seconds || 0);
    const after = Number(config.timing.armed_after_seconds || 0);
    return nowSeconds >= targetSeconds - before && nowSeconds <= targetSeconds + after;
  }

  function shouldRequestT0Reload(signals) {
    if (!config.timing.t0_reload || state.t0ReloadRequested || !config.timing.start_at) return false;
    if (!signals.targetCardFound && !signals.targetReady && !signals.recoveryReload) return false;
    const targetSeconds = parseTimeToSeconds(config.timing.start_at);
    if (targetSeconds === null) return false;
    const nowSeconds = currentServerSeconds();
    return nowSeconds >= targetSeconds && nowSeconds <= targetSeconds + Math.max(1, Number(config.timing.armed_after_seconds || 1));
  }

  function waitingForT0Reload() {
    return state.t0ReloadRequested && Date.now() - state.t0ReloadRequestedAt < 1500;
  }

  function currentServerSeconds() {
    const offset = Number(config.timing.server_time_offset_ms || 0);
    const now = new Date(Date.now() + (Number.isFinite(offset) ? offset : 0));
    return now.getHours() * 3600 + now.getMinutes() * 60 + now.getSeconds();
  }

  function crowdRetryClicksBeforeReload() {
    const value = Number(config.timing.crowd_retry_clicks_before_reload);
    if (!Number.isFinite(value) || value < 1) return 15;
    return Math.floor(value);
  }

  function parseTimeToSeconds(value) {
    const parts = String(value).split(":").map((part) => Number(part));
    if (parts.length === 2 && parts.every(Number.isFinite)) {
      return parts[0] * 3600 + parts[1] * 60;
    }
    if (parts.length === 3 && parts.every(Number.isFinite)) {
      return parts[0] * 3600 + parts[1] * 60 + parts[2];
    }
    return null;
  }

  function describeRequest(input, init) {
    const url = typeof input === "string" ? input : input && input.url;
    const method = init && init.method || input && input.method || "GET";
    return { method, url: String(url || ""), body: safeBody(init && init.body) };
  }

  function safeBody(body) {
    if (!body) return "";
    const text = typeof body === "string" ? body : "[non-string-body]";
    return text.slice(0, 500);
  }

  function installObserver() {
    const observer = new MutationObserver(() => {
      if (state.observerScheduled) return;
      state.observerScheduled = true;
      requestAnimationFrame(() => {
        state.observerScheduled = false;
        tick();
      });
    });
    observer.observe(document.documentElement, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ["class", "disabled", "aria-disabled", "style"]
    });
  }

  function pause(reason, details) {
    state.paused = true;
    report("paused", { reason, details: summarizeSignals(details || {}) });
  }

  function stop(reason, details) {
    state.stopped = true;
    report("stopped", { reason, details: summarizeSignals(details || {}) });
  }

  function unlockButton(button) {
    button.setAttribute("data-glm-grabber-force-target", "true");
    const nodes = uniqueElements([
      button,
      ...ancestors(button, 4),
      ...Array.from(button.querySelectorAll("button, [role='button'], [disabled], [aria-disabled], [class*='disabled'], [class*='Disabled'], [class*='disable'], [class*='Disable']"))
    ].filter(Boolean));
    for (const el of nodes) {
      if ("disabled" in el) el.disabled = false;
      el.removeAttribute("disabled");
      el.removeAttribute("aria-disabled");
      removeDisabledClasses(el);
      el.style.pointerEvents = "auto";
      el.style.cursor = "pointer";
      el.style.filter = "none";
      el.style.opacity = "1";
    }
  }

  function dispatchMouseLikeEvents(el) {
    for (const type of ["mouseover", "mousemove", "mousedown", "mouseup"]) {
      el.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }));
    }
  }

  function highlightManualTarget(el) {
    if (el.getAttribute("data-glm-grabber-manual-target") === "true") return;
    el.setAttribute("data-glm-grabber-manual-target", "true");
    el.style.outline = "3px solid #ff2d55";
    el.style.outlineOffset = "3px";
    report("manual_selector_target", { selector: config.target.button_selector, text: compact(el.innerText || el.textContent || "") });
  }

  function removeDisabledClasses(el) {
    const disabledClasses = Array.from(el.classList || [])
      .filter((name) => /disabled|disable|forbid|sold|grey|gray/i.test(name));
    for (const name of disabledClasses) {
      el.classList.remove(name);
    }
  }

  function ancestors(el, depth) {
    const nodes = [];
    let current = el && el.parentElement;
    for (let index = 0; current && index < depth; index += 1) {
      nodes.push(current);
      current = current.parentElement;
    }
    return nodes;
  }

  function findVisibleButton(pattern) {
    return Array.from(document.querySelectorAll("button, [role='button']"))
      .find((el) => visible(el) && pattern.test(el.innerText || el.textContent || ""));
  }

  function findButtonIn(root, pattern) {
    return Array.from(root.querySelectorAll("button, [role='button']"))
      .find((el) => visible(el) && pattern.test(el.innerText || el.textContent || ""));
  }

  function includesOwnText(el, text) {
    return (el.innerText || "").includes(text);
  }

  function containsOtherPlan(text, targetPlan) {
    const headingArea = String(text).slice(0, 120);
    return ["Lite", "Pro", "Max"].some((plan) => plan !== targetPlan && headingArea.includes(plan));
  }

  function cardLooksLikePlan(el, plan) {
    const text = compact(el.innerText || el.textContent || "");
    if (!text.includes(plan)) return false;
    if (containsOtherPlan(text, plan) && !text.startsWith(plan)) return false;
    const hasPlanHeading = text.startsWith(plan) || text.slice(0, 80).includes(plan);
    const hasPricingSignal = /￥|¥|续费金额|\/月|用量额度|全量权益|Repo|特惠订阅|订阅|抢购|购买|开通|暂时售罄|售罄|补货/.test(text);
    return hasPlanHeading && hasPricingSignal;
  }

  function cardScore(el, plan) {
    const text = compact(el.innerText || el.textContent || "");
    const rect = el.getBoundingClientRect();
    let score = Math.abs(rect.width - 456) + Math.abs(rect.height - 430) * 0.2;
    if (rect.width >= 260 && rect.width <= 560) score -= 80;
    if (text.startsWith(plan)) score -= 200;
    if (/package-card-box|package-card|plan|pricing|card/.test(String(el.className || ""))) score -= 80;
    if (findBuyControlIn(el)) score -= 120;
    if (containsOtherPlan(text, plan)) score += 400;
    if (text.length > 800) score += 600;
    return score;
  }

  function buyControlScore(el) {
    const className = String(el.className || "");
    let score = compact(el.innerText || el.textContent).length;
    if (el.tagName === "BUTTON") score -= 100;
    if (el.getAttribute("role") === "button") score -= 70;
    if (/buy-btn|package-card-btn/.test(className)) score -= 60;
    if (looksLikeLockedBuyControl(el)) score += 20;
    return score;
  }

  function looksLikeActiveBuyControl(el) {
    const text = compact(el.innerText || el.textContent || "");
    return text.length <= 30 && BUY_TEXT_PATTERN.test(text);
  }

  function looksLikeLockedBuyControl(el) {
    const text = compact(el.innerText || el.textContent || "");
    if (text.length > 60) return false;
    return el.getAttribute("data-glm-grabber-force-target") === "true" ||
      LOCKED_BUY_TEXT_PATTERN.test(text) ||
      CROWDED_RETRY_TEXT_PATTERN.test(text) ||
      looksDisabled(el) && looksLikePurchaseControlShape(el, text);
  }

  function looksDisabled(el) {
    const style = window.getComputedStyle(el);
    const className = String(el.className || "");
    return Boolean(
      el.disabled ||
      el.getAttribute("disabled") !== null ||
      el.getAttribute("aria-disabled") === "true" ||
      /disabled|disable|forbid|sold|grey|gray/i.test(className) ||
      style.pointerEvents === "none" ||
      Number(style.opacity || "1") < 0.85 ||
      looksGreyedOut(style)
    );
  }

  function looksGreyedOut(style) {
    return isLowSaturationColor(style.backgroundColor, 45) ||
      isLowSaturationColor(style.color, 75) ||
      isLowSaturationColor(style.borderColor, 55);
  }

  function isLowSaturationColor(value, tolerance) {
    const match = String(value || "").match(/rgba?\((\d+),\s*(\d+),\s*(\d+)/i);
    if (!match) return false;
    const channels = match.slice(1, 4).map((part) => Number(part));
    if (!channels.every(Number.isFinite)) return false;
    const [red, green, blue] = channels;
    const spread = Math.max(red, green, blue) - Math.min(red, green, blue);
    const brightness = (red + green + blue) / 3;
    return spread <= tolerance && brightness >= 80 && brightness <= 230;
  }

  function looksLikePurchaseControlShape(el, text) {
    const className = String(el.className || "");
    if (el.tagName === "BUTTON" || el.getAttribute("role") === "button") return true;
    if (/buy|subscribe|order|pay|package-card-btn|btn|button/i.test(className)) return true;
    return /(\d{1,2}月\d{1,2}日|\d{1,2}:\d{2}|￥|¥)/.test(text);
  }

  function looksLikePeriodControl(el, periodText) {
    const text = compact(el.innerText || el.textContent || "");
    if (!text.includes(periodText) || text.length > 40) return false;
    if (text.includes("Lite") || text.includes("Pro") || text.includes("Max") || text.includes("订阅")) return false;
    return true;
  }

  function periodControlScore(el) {
    const className = String(el.className || "");
    let score = compact(el.innerText || el.textContent).length;
    if (el.tagName === "BUTTON") score -= 100;
    if (el.getAttribute("role") === "button") score -= 70;
    if (/active|selected|current|tab|radio|checked/.test(className)) score -= 40;
    return score;
  }

  function looksLikePlanHeading(el, plan) {
    const text = compact(el.innerText || el.textContent || "");
    if (!text || text.length > 80) return false;
    if (text === plan) return true;
    if (!text.startsWith(plan + " ")) return false;
    return !["Lite", "Pro", "Max"].some((other) => other !== plan && text.includes(other));
  }

  function commonAncestor(a, b) {
    let current = a;
    while (current && !current.contains(b)) {
      current = current.parentElement;
    }
    return current || a.parentElement || a;
  }

  function uniqueElements(elements) {
    return Array.from(new Set(elements.filter(Boolean)));
  }

  function visible(el) {
    const rect = el.getBoundingClientRect();
    const style = window.getComputedStyle(el);
    return rect.width > 0 && rect.height > 0 && style.visibility !== "hidden" && style.display !== "none";
  }

  function inViewport(el) {
    if (!visible(el)) return false;
    const rect = el.getBoundingClientRect();
    return rect.bottom > 0 && rect.right > 0 && rect.top < window.innerHeight && rect.left < window.innerWidth;
  }

  function area(el) {
    const rect = el.getBoundingClientRect();
    return rect.width * rect.height;
  }

  function summarizeSignals(signals) {
    return {
      payment: Boolean(signals.payment),
      captcha: Boolean(signals.captcha),
      login: Boolean(signals.login),
      requestInFlight: Boolean(signals.requestInFlight),
      recoveryReload: Boolean(signals.recoveryReload),
      crowdClickAttempts: state.crowdClickAttempts,
      targetReady: Boolean(signals.targetReady),
      targetCardFound: Boolean(signals.targetCardFound),
      targetButtonFound: Boolean(signals.targetButtonFound),
      targetMismatch: Boolean(signals.targetMismatch),
      periodSelected: Boolean(signals.periodSelected),
      targetSummary: signals.targetSummary || undefined
    };
  }

  function reportDiagnostic(signals) {
    const now = Date.now();
    if (now - state.lastDiagnosticAt < 2000) return;
    state.lastDiagnosticAt = now;
    if (!signals.targetReady) {
      report("diagnostic", summarizeSignals(signals));
    }
  }

  function reportManualWait(reason, signals) {
    const now = Date.now();
    if (now - state.lastManualWaitAt < 2000) return;
    state.lastManualWaitAt = now;
    report("waiting_manual_action", { reason, signals: summarizeSignals(signals) });
  }

  function report(event, data) {
    const payload = {
      source: "glm-grabber",
      event,
      data: data || {},
      url: location.href,
      title: document.title,
      ts: new Date().toISOString()
    };
    window.postMessage(payload, "*");
    if (window.__GLM_GRABBER_REPORT__) {
      window.__GLM_GRABBER_REPORT__(payload);
    }
  }

  function compact(text) {
    return String(text).replace(/\s+/g, " ").trim();
  }

  function merge(base, override) {
    const output = Array.isArray(base) ? base.slice() : Object.assign({}, base);
    for (const [key, value] of Object.entries(override || {})) {
      if (value && typeof value === "object" && !Array.isArray(value) && base[key]) {
        output[key] = merge(base[key], value);
      } else {
        output[key] = value;
      }
    }
    return output;
  }
})();
