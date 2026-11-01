"use strict";
// No-browser regression for the embedded Jaal height handshake.
// Run with: node --test tests/jaal_autoheight.test.cjs
const assert = require("node:assert/strict");
const {readFileSync} = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = readFileSync(
  path.resolve(__dirname, "../BertScript/assets/15.jaal_embedded_autoheight.js"),
  "utf8"
);

function createFixture({route = "/jaal-original/abc/", visible = true,
                        embedded = true, correctFrame = true} = {}) {
  let bottom = 715;
  const frame = {
    style: {height: "800px"},
    classList: {contains: (value) => correctFrame && value === "jaal-original-iframe"}
  };
  const root = {
    isConnected: true,
    getBoundingClientRect: () => ({bottom})
  };
  const frames = [];
  const events = {};
  let onResize = null;
  let onMutation = null;
  let watcherDisconnected = false;
  const window = {
    parent: {},
    location: {pathname: route},
    frameElement: frame,
    scrollY: 0,
    requestAnimationFrame: (fn) => { frames.push(fn); },
    addEventListener: (event, fn) => { events[event] = fn; }
  };
  if (!embedded) window.parent = window;
  const document = {
    readyState: "complete",
    getElementById: (id) => id === "jaal-original-content" && visible ? root : null,
    documentElement: {},
    addEventListener: (event, fn) => { events["doc_" + event] = fn; }
  };
  class ResizeObserver {
    constructor(fn) { onResize = fn; }
    observe(observed) { assert.equal(observed, root); }
  }
  class MutationObserver {
    constructor(fn) { onMutation = fn; }
    observe(observed) { assert.equal(observed, document.documentElement); }
    disconnect() { watcherDisconnected = true; }
  }
  vm.runInNewContext(source, {window, document, ResizeObserver, MutationObserver});
  return {
    frame,
    window,
    events,
    root,
    get scheduled() { return frames.length; },
    flush() {
      while (frames.length) frames.shift()();
    },
    changeBottom(value) { bottom = value; onResize?.(); },
    hydrate() { visible = true; onMutation?.(); },
    get watcherDisconnected() { return watcherDisconnected; }
  };
}

test("measures actual Jaal content, not original 1100px iframe", () => {
  const f = createFixture();
  assert.equal(f.frame.style.height, "800px"); // functional fallback
  f.flush();
  assert.equal(f.frame.style.height, "731px"); // 715 + 16px padding
  f.changeBottom(910);
  f.flush();
  assert.equal(f.frame.style.height, "926px");
  f.changeBottom(695); // after the left panel collapses
  f.flush();
  assert.equal(f.frame.style.height, "711px");
  f.changeBottom(930); // after it expands again
  f.flush();
  assert.equal(f.frame.style.height, "946px");
});

test("clamps pathological sizes, coalesces notifications and avoids loops", () => {
  const f = createFixture();
  f.flush();
  f.changeBottom(2000);
  f.changeBottom(2100);
  assert.equal(f.scheduled, 1);
  f.flush();
  assert.equal(f.frame.style.height, "1600px");
  f.changeBottom(102);
  f.flush();
  assert.equal(f.frame.style.height, "640px");
  f.changeBottom(102); // unchanged: no extra writes
  f.flush();
  assert.equal(f.frame.style.height, "640px");
});

test("waits for Dash layout hydration and then stops observing DOM mutations", () => {
  const f = createFixture({visible: false});
  assert.equal(f.scheduled, 0);
  f.hydrate();
  assert.equal(f.watcherDisconnected, true);
  f.flush();
  assert.equal(f.frame.style.height, "731px");
});

test("does not touch standalone or top-level Dash pages", () => {
  for (const options of [
    {route: "/dash/"},
    {embedded: false},
    {correctFrame: false}
  ]) {
    const f = createFixture(options);
    assert.equal(f.scheduled, 0);
    assert.equal(f.frame.style.height, "800px");
  }
});
