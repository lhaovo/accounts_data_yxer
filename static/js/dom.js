export function $(id) {
  const el = document.getElementById(id);
  if (!el) {
    throw new Error(`Missing required element: #${id}`);
  }
  return el;
}

export function $all(selector, root = document) {
  return [...root.querySelectorAll(selector)];
}

export function on(id, eventName, handler) {
  $(id).addEventListener(eventName, handler);
}

export function setHidden(el, hidden) {
  el.classList.toggle("hidden", hidden);
}

export function checkedValues(selector) {
  return $all(`${selector}:checked`).map((cb) => cb.value);
}

export function setButtonDisabled(ids, disabled) {
  for (const id of ids) {
    $(id).disabled = disabled;
  }
}
