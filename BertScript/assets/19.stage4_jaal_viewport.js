/* Stage 4 iframe adapter: delegate projection to the pinned portable Jaal
 * runtime, then remember the live visdcc component. Only an explicit click
 * fits the current visible dataset; no label, graph, options or physics writes.
 */
(function (root) {
  "use strict";
  let current = null;
  const CAPTURE = "\n;globalThis.dash_clientside.stage4_jaal_viewport.capture.call(this);";
  function capture() {
    current = this;
  }
  function project_and_capture(...args) {
    const upstream = root.dash_clientside.jaal_visible_labels;
    const command = upstream.apply(...args);
    return typeof command === "string" && command ? command + CAPTURE : command;
  }
  function fit(clicks) {
    if (!clicks) return root.dash_clientside.no_update;
    const graph = root.document && root.document.getElementById("graph");
    const c = current;
    const net = c && c.net;
    const host = net && net.body && net.body.container;
    if (!graph || !host || !graph.contains(host) ||
        !c.nn || typeof c.nn.get !== "function" || typeof net.fit !== "function") {
      return "圖形尚未就緒，請稍後再試。";
    }
    const ids = c.nn.get().filter(node => !node.hidden).map(node => node.id);
    if (!ids.length) return "目前沒有可見節點，請調整篩選條件。";
    try {
      net.fit({nodes: ids, animation: false});
      return "已重新定位（" + ids.length + " 個可見節點）";
    } catch (_error) {
      return "無法重新定位，請確認圖形仍在顯示。";
    }
  }
  root.dash_clientside = root.dash_clientside || {};
  root.dash_clientside.stage4_jaal_viewport = {capture, project_and_capture, fit};
  if (typeof module !== "undefined" && module.exports) {
    module.exports = root.dash_clientside.stage4_jaal_viewport;
  }
})(typeof window !== "undefined" ? window : globalThis);
