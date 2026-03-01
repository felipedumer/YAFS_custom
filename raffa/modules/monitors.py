import logging
import random

from yafs.core import Sim

logger = logging.getLogger(__name__)


def schedule_random_fog_removals(simulator: Sim, interval: int, wait_removal_time: int, max_removals: int, nodes_per_removal: int):
    """Remove fog nodes every `interval` simulation time units.

    This uses the existing `Sim.remove_node` (no core changes). If no fog nodes
    remain, the process stops early.

    Args:
        nodes_per_removal: How many fog nodes to remove at each interval tick.
    """


    def current_fog_nodes():
        fog_ids = []
        for node_id in simulator.topology.G.nodes():
            node = simulator.topology.get_node(node_id)
            model_tag = node.get("model") or node.get("mytag")
            if model_tag == "fog":
                fog_ids.append(node_id)
        return fog_ids

    def _loop():
        yield simulator.env.timeout(wait_removal_time)
        removals = 0
        while removals < max_removals:
            yield simulator.env.timeout(interval)
            candidates = current_fog_nodes()
            # Never remove the last remaining fog node to keep the topology alive
            if len(candidates) <= 1:
                logging.info(
                    "Stopping removals: only %d fog node left at t=%s",
                    len(candidates),
                    simulator.env.now,
                )
                return

            # Remove up to nodes_per_removal, but keep at least 1 fog node and respect max_removals
            count = min(nodes_per_removal, len(candidates) - 1, max_removals - removals)
            chosen = random.sample(candidates, count)
            for node_id in chosen:
                node = simulator.topology.get_node(node_id)
                node_label = node.get("label", node_id)
                logging.info(
                    "Removing fog node %s (id=%s) at t=%s",
                    node_label,
                    node_id,
                    simulator.env.now,
                )
                simulator.remove_node(node_id)
                removals += 1

    simulator.env.process(_loop())


def schedule_random_fog_restorations(simulator: Sim, interval: int, wait_restoration_time: int, nodes_per_restoration: int, max_restorations: int = None):
    """Restore previously-removed fog nodes every `interval` simulation time units.

    Uses `Sim.restore_node()` to re-add nodes from `simulator.removed_nodes`.
    Stops when `max_restorations` have been performed (if set) or no removed nodes remain.

    Args:
        nodes_per_restoration: How many fog nodes to restore at each interval tick.
    """

    def _loop():
        yield simulator.env.timeout(wait_restoration_time)
        restorations = 0
        while max_restorations is None or restorations < max_restorations:
            yield simulator.env.timeout(interval)
            if not simulator.removed_nodes:
                logging.info(
                    "Stopping restorations: no removed nodes left at t=%s",
                    simulator.env.now,
                )
                return

            # Restore up to nodes_per_restoration, respecting max_restorations and available removed nodes
            remaining = max_restorations - restorations if max_restorations is not None else nodes_per_restoration
            count = min(nodes_per_restoration, len(simulator.removed_nodes), remaining)
            for _ in range(count):
                entry = simulator.restore_node()  # random pick
                if entry is None:
                    return

                logging.info(
                    "Restored node %s (id=%s) at t=%s",
                    entry["attrs"].get("label", entry["id"]),
                    entry["id"],
                    simulator.env.now,
                )
                restorations += 1

    simulator.env.process(_loop())


def start_node_count_monitor(simulator: Sim, interval: int):
    """Sample the number of active nodes over simulation time and return the log list."""

    records = []
    tracked_models = ["fog", "proxy", "cloud", "end"]

    def snapshot():
        model_counts = {model: 0 for model in tracked_models}
        other_nodes = 0

        for node_id in simulator.topology.G.nodes():
            node = simulator.topology.get_node(node_id)
            model = node.get("model") or node.get("mytag") or "unknown"
            if model in model_counts:
                model_counts[model] += 1
            else:
                other_nodes += 1

        records.append(
            {
                "time": simulator.env.now,
                "total_nodes": len(simulator.topology.G.nodes()),
                "cloud_nodes": model_counts["cloud"],
                "proxy_nodes": model_counts["proxy"],
                "fog_nodes": model_counts["fog"],
                "end_nodes": model_counts["end"],
                "other_nodes": other_nodes,
            }
        )

    def _loop():
        snapshot()
        while True:
            yield simulator.env.timeout(interval)
            snapshot()

    simulator.env.process(_loop())
    return records
