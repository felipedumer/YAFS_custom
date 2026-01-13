import logging
import random

from yafs.core import Sim

logger = logging.getLogger(__name__)


def schedule_random_fog_removals(simulator: Sim, interval: int, max_removals: int):
    """Remove a random fog node every `interval` simulation time units.

    This uses the existing `Sim.remove_node` (no core changes). If no fog nodes
    remain, the process stops early.
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

            node_id = random.choice(candidates)
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
