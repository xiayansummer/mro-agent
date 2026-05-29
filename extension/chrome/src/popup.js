import { registerExtension } from "./api.js";
import { getSettings } from "./config.js";

const pairingCodeInput = document.querySelector("#pairingCode");
const pairButton = document.querySelector("#pairButton");
const heartbeatButton = document.querySelector("#heartbeatButton");
const resetButton = document.querySelector("#resetButton");
const openJdLoginButton = document.querySelector("#openJdLoginButton");
const openZkhLoginButton = document.querySelector("#openZkhLoginButton");
const messageEl = document.querySelector("#message");
const stateBadge = document.querySelector("#stateBadge");
const pairingSection = document.querySelector("#pairingSection");
const boundSection = document.querySelector("#boundSection");
const deviceNameEl = document.querySelector("#deviceName");
const lastHeartbeatEl = document.querySelector("#lastHeartbeat");

let settings = await getSettings();
render();

pairButton.addEventListener("click", async () => {
  const code = pairingCodeInput.value.trim();
  if (!code) {
    renderMessage("请输入配对码。", "error");
    return;
  }

  pairButton.disabled = true;
  renderMessage("正在绑定...", "");
  try {
    const result = await registerExtension(settings.apiBase, code, settings.deviceName);
    await chrome.storage.local.set({
      extToken: result.extToken,
      sessionId: result.sessionId,
      apiBase: settings.apiBase,
      deviceName: settings.deviceName,
    });
    settings = await getSettings();
    pairingCodeInput.value = "";
    render();
    renderMessage("绑定成功，已保存扩展令牌。", "ok");
    await sendHeartbeatNow();
  } catch (error) {
    renderMessage(error.message || "绑定失败。", "error");
  } finally {
    pairButton.disabled = false;
  }
});

heartbeatButton.addEventListener("click", async () => {
  await sendHeartbeatNow();
});

resetButton.addEventListener("click", async () => {
  await chrome.storage.local.remove(["extToken", "sessionId", "lastHeartbeatAt"]);
  settings = await getSettings();
  render();
  renderMessage("已解除本机绑定。", "ok");
});

openJdLoginButton.addEventListener("click", async () => {
  await openPlatformLogin("jd");
});

openZkhLoginButton.addEventListener("click", async () => {
  await openPlatformLogin("zkh");
});

async function sendHeartbeatNow() {
  heartbeatButton.disabled = true;
  renderMessage("正在上报状态...", "");
  try {
    const response = await chrome.runtime.sendMessage({ type: "MRO_SEND_HEARTBEAT" });
    if (!response?.ok) throw new Error(response?.error || "状态上报失败");
    settings = await getSettings();
    render();
    renderMessage("状态已上报。", "ok");
  } catch (error) {
    renderMessage(error.message || "状态上报失败。", "error");
  } finally {
    heartbeatButton.disabled = false;
  }
}

function render() {
  deviceNameEl.textContent = settings.deviceName || "-";
  lastHeartbeatEl.textContent = settings.lastHeartbeatAt
    ? new Date(settings.lastHeartbeatAt).toLocaleString()
    : "-";

  if (settings.extToken) {
    stateBadge.textContent = "已绑定";
    stateBadge.className = "badge ok";
    pairingSection.classList.add("hidden");
    boundSection.classList.remove("hidden");
  } else {
    stateBadge.textContent = "未绑定";
    stateBadge.className = "badge";
    pairingSection.classList.remove("hidden");
    boundSection.classList.add("hidden");
  }
}

function renderMessage(text, type) {
  messageEl.textContent = text;
  messageEl.className = `message ${type || ""}`;
}

async function openPlatformLogin(platform) {
  try {
    const response = await chrome.runtime.sendMessage({
      type: "MRO_OPEN_PLATFORM_LOGIN",
      platform,
    });
    if (!response?.ok) throw new Error(response?.error || "打开登录页失败");
    renderMessage("已打开平台登录页。登录完成后请重新上报状态。", "ok");
  } catch (error) {
    renderMessage(error.message || "打开登录页失败。", "error");
  }
}
