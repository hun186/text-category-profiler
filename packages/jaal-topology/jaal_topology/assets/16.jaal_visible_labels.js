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

  const NETWORK_COLLAPSED_RUN = String.raw`(function () {
    globalThis.dash_clientside.jaal_structural_collapse.activate.call(
      this, "network-collapsed"
    );
  }).call(this);`;

  const HIERARCHICAL_COLLAPSED_RUN = String.raw`(function () {
    globalThis.dash_clientside.jaal_structural_collapse.activate.call(
      this, "hierarchical-collapsed"
    );
  }).call(this);`;

  function resolve(id, preferChinese) {
    const label = String(id);
    const state = root.dash_clientside.jaal_visible_labels;
    const translated = state.translations && Object.prototype.hasOwnProperty.call(
      state.translations, label
    ) ? state.translations[label] : null;
    return preferChinese && typeof translated === "string" && translated.trim()
      ? translated.trim() : label;
  }

  function apply(mode, graphData, selectedLanguages, translations) {
    // Only pre-authored static commands are ever evaluated by visdcc.
    // CSV contents are data in a bounded Dash Store, never executable code.
    if (!graphData || !Array.isArray(graphData.nodes)) return "";
    const preferChinese = Array.isArray(selectedLanguages) &&
      selectedLanguages.includes("zh");
    const state = root.dash_clientside.jaal_visible_labels;
    state.translations = translations && typeof translations === "object" &&
      !Array.isArray(translations) ? translations : {};
    const hierarchy = HIERARCHICAL_RUN.replace(
      "displayLabel(node.id)",
      preferChinese
        ? "displayLabel(globalThis.dash_clientside.jaal_visible_labels.resolve(node.id, true))"
        : "displayLabel(node.id)"
    );
    const network = NETWORK_RUN.replace(
      "String(node.id)",
      preferChinese
        ? "globalThis.dash_clientside.jaal_visible_labels.resolve(node.id, true)"
        : "String(node.id)"
    );
    const restorePrefix = "if (globalThis.dash_clientside && globalThis.dash_clientside.jaal_structural_collapse) globalThis.dash_clientside.jaal_structural_collapse.restore.call(this); var ds = this.nn;";
    if (mode === "hierarchical-collapsed") {
      return preferChinese ? HIERARCHICAL_COLLAPSED_RUN.replace(
        '"hierarchical-collapsed"',
        '"hierarchical-collapsed", true'
      ) : HIERARCHICAL_COLLAPSED_RUN;
    }
    if (mode === "network-collapsed") {
      return preferChinese ? NETWORK_COLLAPSED_RUN.replace(
        '"network-collapsed"',
        '"network-collapsed", true'
      ) : NETWORK_COLLAPSED_RUN;
    }
    if (mode === "hierarchical") return hierarchy.replace(
      "var ds = this.nn;", restorePrefix
    );
    if (mode === "network") return network.replace(
      "var ds = this.nn;", restorePrefix
    );
    return "";
  }

  root.dash_clientside = root.dash_clientside || {};
  root.dash_clientside.jaal_visible_labels = {
    apply: apply,
    resolve: resolve,
  };

  if (typeof module !== "undefined" && module.exports) {
    module.exports = {apply: apply};
  }
})(typeof window !== "undefined" ? window : globalThis);
