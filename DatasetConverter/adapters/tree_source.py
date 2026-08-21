"""Feature-activated access to the legacy class-tree implementation.

The class-tree module still carries pandas, filesystem and path-bootstrap
dependencies.  Keep those dependencies outside the DatasetConverter import
boundary until taxonomy/tree behaviour is actually requested at runtime.
"""

from typing import Any, Iterable


def load_tree_files(**kwargs: Any) -> Any:
    """Load and copy taxonomy tree files using the legacy implementation."""

    from ClassesTree.ClassesTree_utils import SetTreeFiles

    return SetTreeFiles(**kwargs)


def tree_nodes(tree: Iterable[Any]) -> Any:
    """Return the nodes exposed by the legacy tree helper."""

    from ClassesTree.ClassesTree_utils import GetNodes

    return GetNodes(tree)


def subtopics(topics: Iterable[Any], tree: Iterable[Any]) -> Any:
    """Return all descendants for ``topics`` using legacy traversal rules."""

    from ClassesTree.ClassesTree_utils import GetSubTopics

    return GetSubTopics(topics, tree)


def closest_matching_parent(
    tree: Iterable[Any],
    node: Any,
    matching_nodes: Iterable[Any],
    **kwargs: Any,
) -> Any:
    """Find the closest allowed parent while preserving legacy semantics."""

    from ClassesTree.ClassesTree_utils import GetClosestMatchingParent

    return GetClosestMatchingParent(tree, node, matching_nodes, **kwargs)
