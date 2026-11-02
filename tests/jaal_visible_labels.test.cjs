"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {apply} = require("../BertScript/assets/16.jaal_visible_labels.js");

function renderLabels(mode, ids, languages = [], translations = {}) {
  const items = ids.map(id => ({id, label: id, title: id, depth: 1, size: 7}));
  const dataset = {
    get() { return items.map(n => ({...n})); },
    update(changes) {
      for (const change of changes) {
        const existing = items.find(n => n.id === change.id);
        assert.ok(existing);
        Object.assign(existing, change);
      }
    }
  };
  const code = apply(mode, {nodes: items, edges: []}, languages, translations);
  assert.equal(typeof code, "string");
  assert.ok(code.includes("this.nn"));
  // The actual visdcc.Network implementation evals the 'run' prop from
  // its own component method; reproduce its 'this.nn' binding explicitly.
  new Function(code).call({nn: dataset});
  return items;
}

test("hierarchy actually writes short multiline labels to live vis DataSet", () => {
  const full = "CN Intelligence And Espionage Against TW";
  const [node] = renderLabels("hierarchical", [full]);
  assert.ok(node.label.includes("\n"), node.label);
  assert.ok(node.label.split("\n").length <= 3);
  assert.ok(node.label.split("\n").every(line => line.length <= 17));
  assert.equal(node.id, full);
  assert.equal(node.title, full);
  assert.equal(node.depth, 1);
  assert.equal(node.size, 7);
});

test("network restores full labels including content omitted in hierarchy", () => {
  const names = ["TW Affairs", "TW-" + "VeryLongSubject".repeat(8)];
  const items = renderLabels("hierarchical", names);
  assert.ok(items[1].label.endsWith("…"));
  const restored = renderLabels("network", names);
  assert.deepEqual(restored.map(n => n.label), names);
});

test("no executable source injection from an untrusted node identifier", () => {
  const dangerous = 'Label"); throw new Error("injection"); //';
  const rawCode = apply("hierarchical", {nodes: [{id: dangerous}]});
  assert.ok(!rawCode.includes(dangerous));
  const [result] = renderLabels("hierarchical", [dangerous]);
  assert.equal(result.id, dangerous);
});

test("empty input or unexpected mode emits no command", () => {
  assert.equal(apply("hierarchical", null), "");
  assert.equal(apply("hierarchical", {nodes: {}}), "");
  assert.equal(apply("other", {nodes: []}), "");
});

test("Chinese switch uses CT and gracefully falls back to English for missing or blank", () => {
  const ids = ["AI Action Plan", "Missing English Category", "Whitespace CT"];
  const labels = renderLabels("network", ids, ["zh"], {
    "AI Action Plan": "AI行動計劃",
    "Whitespace CT": "   ",
  });
  assert.deepEqual(labels.map(node => node.label),
    ["AI行動計劃", "Missing English Category", "Whitespace CT"]);
  assert.deepEqual(labels.map(node => node.id), ids);
  assert.deepEqual(labels.map(node => node.title), ids);
  assert.deepEqual(renderLabels("network", ids, [], {"AI Action Plan": "AI行動計劃"})
    .map(node => node.label), ids);
});

test("Chinese rendering in hierarchy wraps visible CT but does not change ID or tooltip", () => {
  const id = "CN Intelligence And Espionage Against TW";
  const zh = "中國情報間諜活動與臺灣相關事件長中文名稱";
  const translated = renderLabels("hierarchical", [id], ["zh"], {[id]: zh});
  assert.equal(translated[0].id, id);
  assert.equal(translated[0].title, id);
  assert.ok(translated[0].label.startsWith("中國"));
  assert.ok(translated[0].label.includes("\\n"));
  assert.notEqual(translated[0].label, id);
  assert.ok(translated[0].label.split("\\n").length <= 3);
});

test("language toggle changes static run source without embedding untrusted CT", () => {
  const data = {nodes: [{id:"Dangerous"}],edges: []};
  const chinese = '錯誤"); throw Error("injection");';
  for (const mode of ["network", "hierarchical",
                       "network-collapsed", "hierarchical-collapsed"]) {
    const en = apply(mode, data, [], {Dangerous: chinese});
    const zh = apply(mode, data, ["zh"], {Dangerous: chinese});
    assert.notEqual(en, zh, mode);
    assert.ok(!zh.includes(chinese), "translations must not appear in executable JS");
    assert.ok(!zh.includes("injection"));
  }
  assert.equal(apply("network", data, ["zh"], {"__proto__":"weird"}) !== "", true);
});
