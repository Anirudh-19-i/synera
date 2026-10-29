// Session store: a browser can hold one login per role (this powers "presenter mode").
const KEY = "pl_sessions";
const ACT = "pl_active";

function read() {
  try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch { return {}; }
}

let sessions = read();
let active = localStorage.getItem(ACT) || null;
if (active && !sessions[active]) active = Object.keys(sessions)[0] || null;

function persist() {
  localStorage.setItem(KEY, JSON.stringify(sessions));
  active ? localStorage.setItem(ACT, active) : localStorage.removeItem(ACT);
}

export const getSessions = () => ({ ...sessions });
export const getActive = () => active;

export function setSession(role, s, makeActive = true) {
  sessions[role] = s;
  if (makeActive || !active) active = role;
  persist();
}
export function setActive(role) {
  if (sessions[role]) { active = role; persist(); }
}
export function dropSession(role) {
  delete sessions[role];
  if (active === role) active = Object.keys(sessions)[0] || null;
  persist();
}

function message(data, status) {
  const d = data && data.detail;
  if (Array.isArray(d)) return d.map((x) => x.msg).join(", ");
  return d || `Request failed (${status})`;
}

export async function api(path, { method = "GET", json, form, as } = {}) {
  const role = as || active;
  const tok = sessions[role]?.token;
  const headers = {};
  if (tok) headers.authorization = `Bearer ${tok}`;
  const opt = { method, headers };
  if (json) {
    headers["content-type"] = "application/json";
    opt.body = JSON.stringify(json);
  }
  if (form) opt.body = form;
  const r = await fetch(path, opt);
  const data = await r.json().catch(() => null);
  if (r.status === 401 && tok) {
    dropSession(role);
    window.dispatchEvent(new Event("pl-auth"));
  }
  if (!r.ok) throw new Error(message(data, r.status));
  return data;
}

export async function downloadFile(path, as, filename) {
  const tok = sessions[as || active]?.token;
  const r = await fetch(path, { headers: tok ? { authorization: `Bearer ${tok}` } : {} });
  if (!r.ok) {
    const d = await r.json().catch(() => null);
    throw new Error(message(d, r.status));
  }
  const url = URL.createObjectURL(await r.blob());
  const el = document.createElement("a");
  el.href = url;
  el.download = filename;
  document.body.appendChild(el);
  el.click();
  el.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}
