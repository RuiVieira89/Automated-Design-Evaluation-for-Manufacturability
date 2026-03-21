"""
Dependency graph for check scheduling.

Uses networkx DAG to manage feature dependencies and determine check execution order.
"""

from typing import List, Dict, Set, Optional, Tuple
import networkx as nx


class DependencyGraph:
    """
    Directed acyclic graph (DAG) for check scheduling.

    Nodes represent features or checks. Edges represent dependencies.
    Topological sort determines check execution order.
    """

    def __init__(self):
        """Initialize empty graph."""
        self.graph = nx.DiGraph()

    def add_node(self, node_id: str, node_type: str = "feature", **kwargs) -> None:
        """
        Add a node to the graph.

        Args:
            node_id: Unique node identifier
            node_type: 'feature', 'check', or 'assembly'
            **kwargs: Additional node attributes
        """
        self.graph.add_node(node_id, node_type=node_type, **kwargs)

    def add_edge(self, source: str, target: str, reason: str = "") -> None:
        """
        Add dependency edge (source must complete before target).

        Args:
            source: Node that must complete first
            target: Node that depends on source
            reason: Explanation of dependency
        """
        if not self.graph.has_node(source):
            self.add_node(source)
        if not self.graph.has_node(target):
            self.add_node(target)

        self.graph.add_edge(source, target, reason=reason)

    def get_execution_order(self) -> List[str]:
        """
        Get topological sort (execution order).

        Returns:
            List of node IDs in execution order

        Raises:
            ValueError: If graph contains a cycle
        """
        try:
            return list(nx.topological_sort(self.graph))
        except nx.NetworkXError as e:
            raise ValueError(f"Dependency graph contains cycle: {e}")

    def get_dependencies(self, node_id: str) -> Set[str]:
        """
        Get all nodes that must complete before the given node.

        Args:
            node_id: The node to check

        Returns:
            Set of node IDs that this node depends on
        """
        return set(nx.ancestors(self.graph, node_id))

    def get_dependents(self, node_id: str) -> Set[str]:
        """
        Get all nodes that depend on the given node.

        Args:
            node_id: The node to check

        Returns:
            Set of node IDs that depend on this node
        """
        return set(nx.descendants(self.graph, node_id))

    def is_acyclic(self) -> bool:
        """Check if graph is acyclic."""
        return nx.is_directed_acyclic_graph(self.graph)

    def get_critical_path(self) -> List[str]:
        """
        Get longest path (critical path).

        Returns:
            List of node IDs forming the critical path
        """
        if not self.is_acyclic():
            return []

        # For a DAG, find the longest path
        longest_path = []
        for node in self.graph.nodes():
            path = nx.dag_longest_path(self.graph, default_weight=1)
            if len(path) > len(longest_path):
                longest_path = path
        return longest_path

    def get_levels(self) -> Dict[str, int]:
        """
        Get topological level of each node (0 = no dependencies).

        Returns:
            Dictionary mapping node ID to level
        """
        levels = {}
        in_degree = dict(self.graph.in_degree())

        current_level = 0
        processed = set()

        while len(processed) < len(self.graph):
            # Find all nodes at current level (no unprocessed dependencies)
            level_nodes = [
                node for node in self.graph.nodes()
                if node not in processed and in_degree[node] == 0
            ]

            if not level_nodes:
                break

            for node in level_nodes:
                levels[node] = current_level
                processed.add(node)

            # Update in_degree for next iteration
            for node in level_nodes:
                for successor in self.graph.successors(node):
                    in_degree[successor] -= 1

            current_level += 1

        return levels

    def visualize_description(self) -> str:
        """
        Get a text description of the graph.

        Returns:
            String describing nodes and edges
        """
        lines = ["Dependency Graph:"]
        lines.append(f"  Nodes: {len(self.graph.nodes())}")
        lines.append(f"  Edges: {len(self.graph.edges())}")
        lines.append(f"  Acyclic: {self.is_acyclic()}")
        lines.append("\nExecution order:")
        try:
            for i, node in enumerate(self.get_execution_order(), 1):
                node_type = self.graph.nodes[node].get('node_type', 'unknown')
                lines.append(f"  {i}. {node} ({node_type})")
        except ValueError as e:
            lines.append(f"  ERROR: {e}")
        return "\n".join(lines)


class CheckScheduler:
    """
    Schedules check execution based on dependency graph.

    Handles cascading failures (failed dependency suppresses dependent checks).
    """

    def __init__(self, dependency_graph: DependencyGraph):
        """
        Initialize scheduler.

        Args:
            dependency_graph: DependencyGraph instance
        """
        self.graph = dependency_graph
        self.execution_order = dependency_graph.get_execution_order()
        self.failed_checks: Set[str] = set()

    def mark_failed(self, check_id: str) -> None:
        """
        Mark a check as failed.

        Updates dependent checks to be skipped.

        Args:
            check_id: ID of failed check
        """
        self.failed_checks.add(check_id)

    def should_run(self, check_id: str) -> bool:
        """
        Determine if a check should run.

        Returns False if any dependency failed.

        Args:
            check_id: ID of check to evaluate

        Returns:
            True if check should run, False if skipped
        """
        dependencies = self.graph.get_dependencies(check_id)
        return not (dependencies & self.failed_checks)

    def get_next_runnable(self) -> Optional[str]:
        """
        Get next check that should run.

        Returns:
            Check ID, or None if all checks completed or blocked
        """
        for check_id in self.execution_order:
            if check_id not in self.failed_checks and self.should_run(check_id):
                return check_id
        return None