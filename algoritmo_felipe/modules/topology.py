import json
import logging
import os
from typing import Tuple, Any

from yafs.topology import Topology

logger = logging.getLogger(__name__)


def load_topology(script_dir: str, topology_file: str) -> Tuple[Topology, Any, int, str]:
    """Load topology JSON, build a Topology object, and return metadata.

    Returns (topology, topology_json, num_fog_nodes, topology_path).
    """
    topology_path = os.path.join(script_dir, f"topologies/{topology_file}.json")
    logger.info("Loading topology from %s...", topology_path)

    with open(topology_path, "r") as f:
        topology_json = json.load(f)

    topology = Topology()
    topology.load_all_node_attr(topology_json)

    num_fog_nodes = sum(
        1 for entity in topology_json.get("entity", []) if entity.get("model") == "fog"
    )
    logger.info("Topology has %d fog nodes.", num_fog_nodes)

    return topology, topology_json, num_fog_nodes, topology_path
