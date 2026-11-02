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

  function reconcileDataset(dataset, rows) {
    // Unlike hidden nodes, absent nodes reserve no hierarchical layout space.
    const expected = new Set(rows.map(row => String(row.id)));
    const remove = dataset.getIds().filter(id => !expected.has(String(id)));
    if (remove.length) dataset.remove(remove);
    if (rows.length) dataset.update(rows); // Adds missing IDs and refreshes styles.
  }

  const REFLOW_MS = 460;

  function validPosition(point) {
    return point && Number.isFinite(point.x) && Number.isFinite(point.y);
  }

  function cancelReflow(state) {
    if (!state) return;
    state.reflowToken = (state.reflowToken || 0) + 1;
    if (state.reflowFrame != null && typeof root.cancelAnimationFrame === "function") {
      root.cancelAnimationFrame(state.reflowFrame);
    }
    state.reflowFrame = null;
  }

  function prefersReducedMotion() {
    return typeof root.matchMedia === "function" &&
      root.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }

  function ancestorOrigin(model, id, previous) {
    // A newly exposed node starts near the closest *previously visible*
    // ancestor, so even a deep Search overlay does not pop in from (0, 0).
    const todo = [...(model.parents.get(id) || [])];
    const seen = new Set([id]);
    while (todo.length) {
      const parent = todo.shift();
      if (seen.has(parent)) continue;
      seen.add(parent);
      if (validPosition(previous[parent])) return previous[parent];
      for (const ancestor of model.parents.get(parent) || []) todo.push(ancestor);
    }
    return null;
  }

  function batchMove(net, positions) {
    // visdcc's vis-network redraws *synchronously* for every moveNode()
    // when physics is disabled. Mutate its already-existing in-memory
    // canvas node coordinates together, then redraw exactly once per frame.
    // If this expected internal bridge is unavailable, retain native layout
    // rather than causing hundreds of redraws or guessing an unsafe API.
    const bodies = net && net.body && net.body.nodes;
    if (!bodies || typeof net.redraw !== "function" ||
        positions.some(node => !bodies[node.id])) return false;
    for (const node of positions) {
      bodies[node.id].x = node.x;
      bodies[node.id].y = node.y;
    }
    net.redraw();
    return true;
  }

  function animateReflow(instance, before) {
    const state = instance.__jaalStructural;
    const net = instance.net;
    // Old browsers and reduced-motion users keep the native final layout.
    if (!before || typeof root.requestAnimationFrame !== "function" ||
        prefersReducedMotion() || typeof net.getPositions !== "function" ||
        !net.body || !net.body.nodes || typeof net.redraw !== "function") return;
    const targets = net.getPositions();
    const motion = [];
    for (const id of instance.nn.getIds().map(String)) {
      const to = targets[id];
      const from = validPosition(before[id]) ? before[id] :
        ancestorOrigin(state.model, id, before);
      if (!validPosition(to) || !validPosition(from)) continue;
      if (Math.abs(to.x - from.x) < 0.5 &&
          Math.abs(to.y - from.y) < 0.5) continue;
      motion.push({id, from, to});
    }
    if (!motion.length) return;

    // Restore every node in a single canvas redraw before browser paint.
    // New children appear at a parent's old position; surviving nodes do
    // not teleport. If the internal node map changed, retain native layout.
    if (!batchMove(net, motion.map(node => ({
      id: node.id, x: node.from.x, y: node.from.y,
    })))) return;
    const token = state.reflowToken;
    let firstTimestamp = null;
    function frame(timestamp) {
      if (state.reflowToken !== token ||
          state.mode !== "hierarchical-collapsed") return;
      if (firstTimestamp == null) firstTimestamp = timestamp;
      const fraction = Math.max(0, Math.min(1, (timestamp - firstTimestamp) / REFLOW_MS));
      // Cubic ease-out maintains one continuous spatial trajectory rather
      // than handing each frame back to LayoutEngine's instant relayout.
      const t = 1 - Math.pow(1 - fraction, 3);
      const positions = motion.map(node => ({
        id: node.id,
        x: node.from.x + (node.to.x - node.from.x) * t,
        y: node.from.y + (node.to.y - node.from.y) * t,
      }));
      if (!batchMove(net, positions)) {
        cancelReflow(state);
        return;
      }
      if (fraction < 1) state.reflowFrame = root.requestAnimationFrame(frame);
      else state.reflowFrame = null;
    }
    state.reflowFrame = root.requestAnimationFrame(frame);
  }

  function displayClassLabel(id, preferChinese) {
    const labels = root.dash_clientside && root.dash_clientside.jaal_visible_labels;
    return labels && typeof labels.resolve === "function"
      ? labels.resolve(id, preferChinese) : id;
  }

  function project(instance) {
    const state = instance.__jaalStructural;
    if (!state || !COLLAPSED.has(state.mode)) return;
    const source = instance.props && instance.props.data;
    if (!source || !instance.nn || !instance.ee) return;
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
    const projectedNodes = source.nodes.map(base => {
      const id = String(base.id);
      const count = state.model.uniqueDescendants(id);
      const bubble = count > 0 && !state.expanded.has(id) &&
        !searchAncestors.has(id);
      return {
        ...base,
        hidden: !shown.has(id) || (!searchActive && Boolean(base.hidden)),
        label: displayName(displayClassLabel(id, state.preferChinese)) + (bubble ? "\n" + count : ""),
      };
    });
    const projectedEdges = source.edges.map(base => ({
      ...base,
      hidden: !shown.has(String(base.from)) ||
        !shown.has(String(base.to)) ||
        !(state.expanded.has(String(base.from)) ||
          (searchActive && searchAncestors.has(String(base.from)))) ||
        Boolean(base.hidden),
    }));
    if (state.mode === "hierarchical-collapsed") {
      // Completely exclude unseen nodes from the hierarchical layout.
      // Remove edges first; reinsert nodes before their connecting edges.
      const nodes = projectedNodes.filter(node => !node.hidden);
      const edges = projectedEdges.filter(edge => !edge.hidden);
      const current = new Set(instance.nn.getIds().map(String));
      const desired = new Set(nodes.map(node => String(node.id)));
      // Capturing the displayed positions BEFORE changing DataSets prevents
      // the hierarchy engine from teleporting existing nodes on each click.
      // The final layout remains the existing directed, box-node hierarchy.
      const enteringCompact = !state.compactActive;
      const net = instance.net;
      const before = !enteringCompact && net &&
        typeof net.getPositions === "function" ? net.getPositions() : null;
      cancelReflow(state);
      const wantedEdges = new Set(edges.map(edge => String(edge.id)));
      const removedEdges = instance.ee.getIds().filter(id => !wantedEdges.has(String(id)));
      if (removedEdges.length) instance.ee.remove(removedEdges);
      reconcileDataset(instance.nn, nodes);
      reconcileDataset(instance.ee, edges);
      state.compactActive = true;
      if (enteringCompact && net &&
          typeof net.fit === "function" && nodes.length) {
        net.fit({nodes: nodes.map(node => node.id), animation: false});
      } else if (!enteringCompact) {
        animateReflow(instance, before);
      }
    } else {
      // Preserve the existing natural network-cluster layout.
      // Recover IDs physically removed in a preceding collapsed hierarchy.
      reconcileDataset(instance.nn, projectedNodes);
      reconcileDataset(instance.ee, projectedEdges);
      state.compactActive = false;
      cancelReflow(state);
    }
  }

  function restore() {
    const state = this.__jaalStructural;
    if (!state || !COLLAPSED.has(state.mode)) return;
    cancelReflow(state);
    state.mode = null;
    const source = this.props && this.props.data;
    if (!source || !this.nn || !this.ee) return;
    // Restore the exact Jaal source nodes and edges after compact mode.
    reconcileDataset(this.nn, source.nodes.map(node => ({
      ...node, hidden: Boolean(node.hidden),
    })));
    reconcileDataset(this.ee, source.edges.map(edge => ({
      ...edge, hidden: Boolean(edge.hidden),
    })));
    state.compactActive = false;
  }

  function activate(mode, preferChinese) {
    if (!COLLAPSED.has(mode) || !this.nn || !this.ee || !this.net) return;
    const source = this.props && this.props.data;
    if (!source || !Array.isArray(source.nodes) || !Array.isArray(source.edges)) return;
    const key = signature(source);
    let state = this.__jaalStructural;
    if (!state || state.key !== key) {
      cancelReflow(state);
      const model = graphModel(source);
      state = {key, mode, model, expanded: new Set(model.roots), preferChinese: Boolean(preferChinese)};
      this.__jaalStructural = state;
    } else {
      state.mode = mode;
      state.preferChinese = Boolean(preferChinese);
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
