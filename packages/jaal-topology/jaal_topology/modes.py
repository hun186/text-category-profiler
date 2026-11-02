"""Shared four-mode Jaal network layout contract.

This module has no dependency on the TextClassification application.
Network and hierarchy, full and structural collapse, preserve edge direction.
"""
from copy import deepcopy

def layout_options(base_options, mode):
    """Return independent vis.js options; never mutate the original settings.

    The network may contain cross-links and more than one parent. Hierarchical
    layout is a directed *view* of those same edges, not a rewritten tree.
    """
    if mode not in ("network", "hierarchical", "network-collapsed",
                    "hierarchical-collapsed"):
        raise ValueError("Unsupported Jaal layout mode")
    collapsed = mode.endswith("-collapsed")
    hierarchical = mode.startswith("hierarchical")
    options = deepcopy(base_options)
    if hierarchical:
        options.setdefault("layout", {})["hierarchical"] = {
            "enabled": True,
            "direction": "UD",
            "sortMethod": "directed",
            # Circle labels sit outside node dimensions, so hierarchy's
            # spacing engine cannot avoid collisions. Boxes reserve the
            # rendered label width and height as actual node geometry.
            "levelSeparation": 260,
            "nodeSpacing": 285,
            "treeSpacing": 370,
            "blockShifting": True,
            "edgeMinimization": True,
            "parentCentralization": True,
        }
        options.setdefault("nodes", {}).update({
            "shape": "box",
            "widthConstraint": {"maximum": 178},
            "margin": 12,
            "borderWidth": 1,
        })
        options["physics"] = {"enabled": False}
        options.setdefault("edges", {})["smooth"] = {
            "enabled": True,
            "type": "cubicBezier",
            "forceDirection": "vertical",
            "roundness": 0.28,
        }
    else:
        # visdcc forwards updates via net.setOptions(), which MERGES with
        # previous vis-network options. Omitting hierarchy/physics/smooth
        # would leave the tree layout enabled after switching back.
        options.setdefault("layout", {})["hierarchical"] = {"enabled": False}
        # visdcc calls setOptions() which MERGES previous options; reset
        # wrapping explicitly so original Jaal network labels stay unaltered.
        options.setdefault("nodes", {}).update({
            "shape": deepcopy(base_options.get("nodes", {}).get("shape", "dot")),
            "widthConstraint": deepcopy(
                base_options.get("nodes", {}).get("widthConstraint", False)
            ),
            "margin": deepcopy(base_options.get("nodes", {}).get("margin", 0)),
            "borderWidth": deepcopy(base_options.get("nodes", {}).get("borderWidth", 1)),
        })
        if collapsed:
            # Structural bubbles are real original nodes, with no duplicate
            # virtual IDs and no automatic physics-based spatial clustering.
            options.setdefault("nodes", {}).update({
                "shape": "box", "widthConstraint": {"maximum": 178},
                "margin": 10,
            })
        baseline_physics = base_options.get("physics", {})
        if isinstance(baseline_physics, dict):
            options.setdefault("physics", {})["enabled"] = baseline_physics.get(
                "enabled", True
            )
        else:
            options["physics"] = {"enabled": bool(baseline_physics)}
        baseline_smooth = base_options.get("edges", {}).get("smooth")
        options.setdefault("edges", {})["smooth"] = (
            deepcopy(baseline_smooth) if baseline_smooth is not None else
            # Explicit vis-network defaults needed to reverse cubicBezier.
            {"enabled": True, "type": "dynamic",
             "forceDirection": "none", "roundness": 0.5}
        )
    return options
