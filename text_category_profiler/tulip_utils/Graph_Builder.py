"""Legacy path for a manual, optional Tulip graph demonstration.

The original historical source is preserved at experiments/tulip_graph_builder.py.
The facade delays importing heavy/optional Tulip dependencies until a public
attribute is accessed. External callers of this path are not fully verified.
"""
from importlib import import_module
from pathlib import Path
import runpy


__all__ = (
    "ShowElapsedTime", "ExtractNodes", "find_id_src_tar",
    "find_id_of_viewLabel", "BuildEdges", "NodeLabeltoIdTable",
    "graph_global_references", "BuildGraph", "Compute_degree_of_graph",
    "set_groupID_Property", "ClusterMetaNodeGraph",
    "Create_Node_Link_Diagram_view", "load_params_specified",
    "ApplyLayoutEffect", "ShowViews",
)


def __getattr__(name):
    if name.startswith("_") or name == "main":
        raise AttributeError(name)
    implementation = import_module("experiments.tulip_graph_builder")
    return getattr(implementation, name)


def __dir__():
    return sorted(set(globals()) | set(__all__))


def main():
    """Explicitly run the relocated original historical direct-script demo."""
    experiment = (
        Path(__file__).resolve().parents[2]
        / "experiments" / "tulip_graph_builder.py"
    )
    runpy.run_path(str(experiment), run_name="__main__")


if __name__ == "__main__":
    main()
