const test = require("node:test");
const assert = require("node:assert/strict");
const api = require("../BertScript/assets/19.stage4_jaal_viewport.js");

test("projection preserves pinned upstream arguments and adds only static capture code", () => {
  const args = ["network", {nodes: [{id: "untrusted"}]}, [], {}, {}, true];
  globalThis.dash_clientside.jaal_visible_labels = {
    apply(...actual) { assert.deepEqual(actual, args); return "STATIC;"; }
  };
  const run = api.project_and_capture(...args);
  assert.equal(run, "STATIC;\n;globalThis.dash_clientside.stage4_jaal_viewport.capture.call(this);");
  globalThis.dash_clientside.jaal_visible_labels.apply = () => "";
  assert.equal(api.project_and_capture(...args), "");
});

test("fit only on click, visible live IDs including quotient nodes; no mutations", () => {
  const host = {};
  let attached = true;
  globalThis.document = {getElementById: id => id === "graph" ?
    {contains: node => attached && node === host} : null};
  const rows = Object.freeze([Object.freeze({id: "A"}), Object.freeze({id: "hidden", hidden: true}),
    Object.freeze({id: "community:0", hidden: false})]);
  const calls = [];
  const component = {nn: {get: () => rows}, net: {body: {container: host},
    fit: options => calls.push(options)}};
  globalThis.dash_clientside.no_update = Symbol("no_update");
  api.capture.call(component);
  assert.equal(api.fit(0), globalThis.dash_clientside.no_update);
  assert.equal(calls.length, 0);
  assert.match(api.fit(1), /已重新定位/);
  assert.deepEqual(calls, [{nodes: ["A", "community:0"], animation: false}]);
  attached = false;
  assert.match(api.fit(2), /尚未就緒/);
  assert.equal(calls.length, 1);
  attached = true;
  component.nn.get = () => [{id: "B", hidden: true}];
  assert.match(api.fit(3), /沒有可見節點/);
  assert.equal(calls.length, 1);
  component.nn.get = () => [{id: "B"}];
  component.net.fit = () => { throw Error("detached"); };
  assert.match(api.fit(4), /無法重新定位/);
});
