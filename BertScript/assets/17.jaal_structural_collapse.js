/* Jaal same-port structural collapse, with one node per original ClassLabel.
 * This uses the actual visdcc React instance DataSets (this.nn/this.ee),
 * not a copy of the graph or synthetic vis-network clusters.
 * Only from/to edges in the already-loaded taxonomy graph count as
 * hierarchical relationships. Never mutate node ids or authoritative files.
 */
(function (root) {
  "use strict";

  const COLLAPSED = new Set(["network-collapsed", "hierarchical-collapsed"]);

  function displayName(input) {
    let rest = String(input).replace(/\s+/g, " ").trim();
    const lines = [];
    while (rest && lines.length < 3) {
      if (rest.length <= 17) { lines.push(rest); break; }
      let at = rest.lastIndexOf(" ", 17);
      if (at < 1) at = 17;
      lines.push(rest.slice(0, at).trim());
      rest = rest.slice(at).trim();
    }
    if (rest.length > 17 && lines.length === 3) {
      lines[2] = lines[2].slice(0, 16) + "…";
    }
    return lines.join("\n");
  }

  function graphModel(data) {
    if (!data || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
      throw new Error("Jaal structural collapse requires loaded nodes and edges");
    }
    const ids = new Set(data.nodes.map(n => String(n.id)));
    const child = new Map(Array.from(ids, id => [id, new Set()]));
    const incoming = new Map(Array.from(ids, id => [id, 0]));
    const parents = new Map(Array.from(ids, id => [id, new Set()]));
    for (const edge of data.edges) {
      const a = String(edge.from), b = String(edge.to);
      if (!ids.has(a) || !ids.has(b) || child.get(a).has(b)) continue;
      child.get(a).add(b);
      incoming.set(b, incoming.get(b) + 1);
      parents.get(b).add(a);
    }
    const ordered = Array.from(ids).sort();
    const roots = ordered.filter(id => incoming.get(id) === 0);
    const reached = new Set();
    function mark(seed) {
      const stack = [seed];
      while (stack.length) {
        const id = stack.pop();
        if (reached.has(id)) continue;
        reached.add(id);
        for (const next of child.get(id)) stack.push(next);
      }
    }
    for (const id of roots) mark(id);
    // Disconnected directed cycles have no zero-indegree root; seed once
    // deterministically so they remain visible and traversal stays finite.
    for (const id of ordered) {
      if (!reached.has(id)) { roots.push(id); mark(id); }
    }
    const counts = new Map();
    function uniqueDescendants(start) {
      if (counts.has(start)) return counts.get(start);
      const seen = new Set([start]);
      const stack = [...child.get(start)];
      while (stack.length) {
        const next = stack.pop();
        if (seen.has(next)) continue;
        seen.add(next);
        for (const after of child.get(next)) stack.push(after);
      }
      const count = seen.size - 1;
      counts.set(start, count);
      return count;
    }
    return {ids, child, parents, roots, counts, uniqueDescendants};
  }

  function signature(data) {
    const nodes = data.nodes.map(n => String(n.id)).sort();
    const edges = data.edges.map(e => String(e.from) + "\u0000" + String(e.to)).sort();
    return JSON.stringify([nodes, edges]);
  }

  function visibleIds(model, expanded) {
    const visible = new Set();
    const stack = [...model.roots];
    while (stack.length) {
      const id = stack.pop();
      if (!model.ids.has(id) || visible.has(id)) continue;
      visible.add(id);
      // Never create duplicate visual nodes for multiple-parent paths.
      if (expanded.has(id)) {
        for (const next of model.child.get(id)) stack.push(next);
      }
    }
    return visible;
  }

  function project(instance) {
    const state = instance.__jaalStructural;
    if (!state || !COLLAPSED.has(state.mode)) return;
    const source = instance.props && instance.props.data;
    if (!source || !instance.nn || !instance.ee) return;
    const baseNodes = new Map(source.nodes.map(n => [String(n.id), n]));
    const baseEdges = new Map(source.edges.map(e => [String(e.id), e]));
    let shown = visibleIds(state.model, state.expanded);
    // Upstream Jaal Search hides every non-matching node. A deep match
    // must remain reachable in collapsed mode: show the unique matching
    // IDs and their ancestor paths (including parents normally hidden
    // by Search), while never duplicating nodes on multiple-parent paths.
    const searchActive = source.nodes.some(n => Boolean(n.hidden));
    state.searchActive = searchActive;
    let searchAncestors = new Set();
    if (searchActive) {
      const matches = source.nodes.filter(n => !n.hidden).map(n => String(n.id));
      const stack = [...matches];
      shown = new Set();
      while (stack.length) {
        const id = stack.pop();
        if (shown.has(id)) continue;
        shown.add(id);
        for (const parent of state.model.parents.get(id) || []) {
          searchAncestors.add(parent);
          stack.push(parent);
        }
      }
    }
    instance.nn.update(instance.nn.get().map(node => {
      const id = String(node.id);
      const base = baseNodes.get(id) || {};
      const count = state.model.uniqueDescendants(id);
      const bubble = count > 0 && !state.expanded.has(id) &&
        !searchAncestors.has(id);
      return {
        id: node.id,
        hidden: !shown.has(id) || (!searchActive && Boolean(base.hidden)),
        label: displayName(id) + (bubble ? "\n" + count : ""),
      };
    }));
    instance.ee.update(instance.ee.get().map(edge => {
      const base = baseEdges.get(String(edge.id)) || {};
      return {
        id: edge.id,
        hidden: !shown.has(String(edge.from)) ||
          !shown.has(String(edge.to)) ||
          !(state.expanded.has(String(edge.from)) ||
            (searchActive && searchAncestors.has(String(edge.from)))) ||
          Boolean(base.hidden),
      };
    }));
  }

  function restore() {
    const state = this.__jaalStructural;
    if (!state || !COLLAPSED.has(state.mode)) return;
    state.mode = null;
    const source = this.props && this.props.data;
    if (!source || !this.nn || !this.ee) return;
    const baseNodes = new Map(source.nodes.map(n => [String(n.id), n]));
    const baseEdges = new Map(source.edges.map(e => [String(e.id), e]));
    this.nn.update(this.nn.get().map(n => {
      const origin = baseNodes.get(String(n.id)) || {};
      return {id: n.id, hidden: Boolean(origin.hidden)};
    }));
    this.ee.update(this.ee.get().map(e => {
      const origin = baseEdges.get(String(e.id)) || {};
      return {id: e.id, hidden: Boolean(origin.hidden)};
    }));
  }

  function activate(mode) {
    if (!COLLAPSED.has(mode) || !this.nn || !this.ee || !this.net) return;
    const source = this.props && this.props.data;
    if (!source || !Array.isArray(source.nodes) || !Array.isArray(source.edges)) return;
    const key = signature(source);
    let state = this.__jaalStructural;
    if (!state || state.key !== key) {
      const model = graphModel(source);
      state = {key, mode, model, expanded: new Set(model.roots)};
      this.__jaalStructural = state;
    } else {
      state.mode = mode;
    }
    if (!this.__jaalStructuralClickHook) {
      const component = this;
      this.net.on("click", function (event) {
        const current = component.__jaalStructural;
        if (!current || !COLLAPSED.has(current.mode) || current.searchActive) return;
        const id = event && event.nodes && event.nodes.length ?
          String(event.nodes[0]) : null;
        if (!id || !current.model.ids.has(id) ||
            current.model.uniqueDescendants(id) === 0) return;
        if (current.expanded.has(id)) current.expanded.delete(id);
        else current.expanded.add(id);
        project(component);
      });
      this.__jaalStructuralClickHook = true;
    }
    project(this);
  }

  root.dash_clientside = root.dash_clientside || {};
  root.dash_clientside.jaal_structural_collapse = {
    activate, restore, graphModel, visibleIds, displayName,
  };
  if (typeof module !== "undefined" && module.exports) {
    module.exports = {activate, restore, graphModel, visibleIds, displayName};
  }
})(typeof window !== "undefined" ? window : globalThis);
