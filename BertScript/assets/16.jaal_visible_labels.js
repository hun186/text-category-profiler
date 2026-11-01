/* Same-origin embedded Jaal: ensure the *visdcc canvas DataSet* uses
 * readable labels, not merely server-side Dash graph.data.
 *
 * visdcc.Network is a wrapper around vis.js, with an internal this.nn DataSet
 * and a public "run" property evaluated on Network.render. Never interpolate
 * user-controlled ClassLabels into executable code. The static code projects
 * the unchanged node IDs already in the rendered DataSet.
 */
(function (root) {
  "use strict";

  const HIERARCHICAL_RUN = String.raw`(function () {
    var ds = this.nn;
    if (!ds || typeof ds.get !== "function" || typeof ds.update !== "function") return;
    function displayLabel(value) {
      var remaining = String(value).replace(/\s+/g, " ").trim();
      var lines = [];
      while (remaining && lines.length < 3) {
        if (remaining.length <= 17) {
          lines.push(remaining);
          remaining = "";
          break;
        }
        var cut = remaining.lastIndexOf(" ", 17);
        if (cut < 1) cut = 17;
        lines.push(remaining.slice(0, cut).trim());
        remaining = remaining.slice(cut).trim();
      }
      if (remaining && lines.length) {
        var last = lines.length - 1;
        lines[last] = lines[last].slice(0, 16) + "…";
      }
      return lines.join("\n");
    }
    var changes = ds.get().map(function (node) {
      return {id: node.id, label: displayLabel(node.id)};
    });
    if (changes.length) ds.update(changes);
  }).call(this);`;

  const NETWORK_RUN = String.raw`(function () {
    var ds = this.nn;
    if (!ds || typeof ds.get !== "function" || typeof ds.update !== "function") return;
    var changes = ds.get().map(function (node) {
      return {id: node.id, label: String(node.id)};
    });
    if (changes.length) ds.update(changes);
  }).call(this);`;

  function apply(mode, graphData) {
    // No initial graph-data prop, no unsafe dynamically constructed JS.
    if (!graphData || !Array.isArray(graphData.nodes)) return "";
    if (mode === "hierarchical") return HIERARCHICAL_RUN;
    if (mode === "network") return NETWORK_RUN;
    return "";
  }

  root.dash_clientside = root.dash_clientside || {};
  root.dash_clientside.jaal_visible_labels = {
    apply: apply,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {apply: apply};
  }
})(typeof window !== "undefined" ? window : globalThis);
