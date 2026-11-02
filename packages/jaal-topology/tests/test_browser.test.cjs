"use strict";
const test = require("node:test");
const assert = require("node:assert/strict");
const {apply} = require("../jaal_topology/assets/16.jaal_visible_labels.js");
const collapsed = require("../jaal_topology/assets/17.jaal_structural_collapse.js");

test("portable engine exports four active layout commands", () => {
  const g = {nodes: [{id: "Root"}, {id: "Leaf"}],
             edges: [{id: "e1", from: "Root", to: "Leaf"}]};
  for (const mode of ["network", "hierarchical",
                      "network-collapsed", "hierarchical-collapsed"]) {
    const command = apply(mode, g, ["zh"], {Root: "根"});
    assert.equal(typeof command, "string");
    assert.ok(command.includes("this"));
    assert.ok(!command.includes("根"), "CSV text must never enter JS source");
  }
});

test("multi-parent directed graph remains an exact unique-descendant graph", () => {
  const graph = collapsed.graphModel({
    nodes: ["A","B","C","D"].map(id => ({id})),
    edges: [["A","B"],["A","C"],["B","D"],["C","D"]]
      .map(([from,to],i) => ({id:String(i),from,to}))
  });
  assert.equal(graph.uniqueDescendants("A"), 3);
  assert.equal(graph.uniqueDescendants("B"), 1);
  assert.equal(graph.uniqueDescendants("D"), 0);
});
