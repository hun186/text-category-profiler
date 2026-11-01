"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {apply} = require("../BertScript/assets/16.jaal_visible_labels.js");

function renderLabels(mode, ids) {
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
  const code = apply(mode, {nodes: items, edges: []});
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
