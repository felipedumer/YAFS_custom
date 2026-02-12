from yafs.placement import Placement
import logging
import csv
import os
import math
import random
import networkx as nx

LATENCY_WEIGHT = 0.7 # Must sum to 1.0
RELIABILITY_WEIGHT = 0.3 # Must sum to 1.0
REPLICATION_THRESHOLD = 0.7 # If the best node has a reliability less than this, we replicate to at least 2 nodes.

logger = logging.getLogger(__name__)

class CustomPlacement(Placement):
    """
    This implementation locates the services of the application in the cheapest cloud regardless of where the sources or sinks are located.

    It only runs once, in the initialization.

    """
    def __init__(self, name, activation_dist=None, logger=None, strategy=None, app_lifetime=2000):
        super(CustomPlacement, self).__init__(name, activation_dist, logger)
        self.strategy = strategy
        self.app_lifetime = app_lifetime  # Mission time for reliability calculation (in sim ticks)

    def _sort_fog_nodes_dijkstra(self, sim, app_name, id_fog_list):
        """Rank fog nodes by the best (minimum) latency (PR) path from any EndDevice of the app.
        Returns a list of (node_id, latency) tuples sorted by latency ascending."""
        id_fog_list = [nid for nid in id_fog_list if sim.topology.G.has_node(nid)]
        if not id_fog_list:
            return []

        try:
            app_id = app_name.split("-")[1]
        except IndexError:
            return [(nid, float("inf")) for nid in id_fog_list]

        sensor_nodes = sim.topology.find_IDs({"model": f"EndDevice-{app_id}"})
        if not sensor_nodes:
            return [(nid, float("inf")) for nid in sorted(id_fog_list)]

        distances = []
        for fog_id in id_fog_list:
            best = float("inf")
            for sensor_id in sensor_nodes:
                try:
                    # Usage of Dijkstra algorithm to find the minimum path based on 'PR' attribute
                    dist = nx.shortest_path_length(
                        sim.topology.G, source=sensor_id, target=fog_id, weight="PR"
                    )

                    # Debug the distance
                    # logging.debug("[LATENCY] App %s: Distance from Sensor %s to Fog %s = %s", app_name, sensor_id, fog_id, dist)

                    best = min(best, dist)
                except nx.NetworkXNoPath:
                    continue
            distances.append((fog_id, best))

        # Shuffle first to randomize tie-breaking among nodes with equal distance,
        # preventing systematic bias toward low node IDs.
        random.shuffle(distances)
        # Stable sort preserves the random order within each distance group.
        distances.sort(key=lambda x: x[1])

        return distances

    def _deploy_end_devices(self, sim, app_name, services, id_cluster):
        """
        Deploy EndDevice modules on their corresponding sensor nodes; fallback to cloud.
        Returns the set of modules deployed here so callers can skip them.
        """
        deployed = set()
        try:
            app_id = int(app_name.split("-")[1])
        except (IndexError, ValueError):
            logging.warning("Could not parse app id from %s; sensor allocation skipped", app_name)
            return deployed

        sensor_nodes = sim.topology.find_IDs({"model": f"EndDevice-{app_id}"})
        if not sensor_nodes:
            logging.warning("No sensor nodes found for app %s; placing sensor modules on cloud", app_name)

        for module in services:
            if module.endswith("EndDevice") and module in self.scaleServices:
                target_nodes = sensor_nodes if sensor_nodes else id_cluster
                for _ in range(0, self.scaleServices[module]):
                    sim.deploy_module(app_name, module, services[module], target_nodes)
                deployed.add(module)
        return deployed

    def _static_strategy(self, sim, app_name):
        #We find the ID-nodo/resource
        cluster_tag = {"model": "cloud"}

        id_cluster = sim.topology.find_IDs(cluster_tag)
        app = sim.apps[app_name]
        services = app.services

        deployed_end_devices = self._deploy_end_devices(sim, app_name, services, id_cluster)

        for module in services:
            if module in deployed_end_devices:
                continue

            if module in self.scaleServices:
                for rep in range(0, self.scaleServices[module]):
                    idDES = sim.deploy_module(app_name,module,services[module],id_cluster)

    def _dijkstra_strategy(self, sim, app_name):
        fog_clusters_id = sim.topology.find_IDs({"model": "fog"})
        cloud_cluster_id = sim.topology.find_IDs({"model": "cloud"})

        app = sim.apps[app_name]
        services = app.services

        deployed_end_devices = self._deploy_end_devices(sim, app_name, services, fog_clusters_id)
        for module in services:
            if module in deployed_end_devices:
                continue

            # Search for fog clusters
            elif module in self.scaleServices:
                target_nodes = fog_clusters_id
                if fog_clusters_id:
                    ranked_with_latency = self._sort_fog_nodes_dijkstra(sim, app_name, fog_clusters_id)
                    ranked_nodes = [nid for nid, _ in ranked_with_latency]
                    target_nodes = ranked_nodes

                # Allocate to cloud if no fog nodes are available
                if not target_nodes:
                    target_nodes = list(cloud_cluster_id)

                # Deploy replicas
                replicas_needed = self.scaleServices[module]
                ranked_targets = target_nodes[:replicas_needed]

                for target in ranked_targets:
                    sim.deploy_module(app_name, module, services[module], [target])
                    
                    # get the node label based on node id
                    node_label = sim.topology.get_node(target).get("label", target)
                    logging.info("Placed %s on node %s", module, node_label)

                # If not enough replicas were placed, use cloud
                remaining = replicas_needed - len(ranked_targets)
                if remaining > 0 and cloud_cluster_id:
                    cloud_target = cloud_cluster_id[0]
                    for _ in range(remaining):
                        sim.deploy_module(app_name, module, services[module], [cloud_target])

                    node_label = sim.topology.get_node(cloud_target).get("label", cloud_target)
                    logging.info("Placed %s on node %s", module, node_label)

    def _roundrobin_strategy(self, sim, app_name):
        fog_clusters_id = sim.topology.find_IDs({"model": "fog"})
        cloud_cluster_id = sim.topology.find_IDs({"model": "cloud"})

        app = sim.apps[app_name]
        services = app.services

        # Deploy sensor-bound modules first
        deployed_end_devices = self._deploy_end_devices(
            sim, app_name, services, fog_clusters_id or cloud_cluster_id
        )

        # Deterministic order for rotation
        target_nodes = list(fog_clusters_id)
        if not target_nodes:
            target_nodes = list(cloud_cluster_id)

        target_nodes.sort()

        if not target_nodes:
            logging.warning("No fog or cloud nodes available for roundrobin placement of %s", app_name)
            return

        # Offset the starting point by app id so multiple CustomPlacement instances
        # (one per app) do not all begin at the same node.
        app_id_int = int(app_name.split("-")[1])

        rr_index = app_id_int % len(target_nodes)

        for module in services:
            if module in deployed_end_devices:
                continue

            if not target_nodes:
                target_nodes = list(cloud_cluster_id)

            replicas_needed = self.scaleServices[module]

            for _ in range(replicas_needed):
                target = target_nodes[rr_index % len(target_nodes)]
                rr_index += 1
                sim.deploy_module(app_name, module, services[module], [target])

                node_label = sim.topology.get_node(target).get("label", target)
                logging.info("Placed %s on node %s", module, node_label)

    def _custom_strategy(self, sim, app_name):
        """
            Implements RAFFA
        """
        fog_clusters_id = sim.topology.find_IDs({"model": "fog"})
        cloud_cluster_id = sim.topology.find_IDs({"model": "cloud"})

        app = sim.apps[app_name]
        services = app.services

        deployed_end_devices = self._deploy_end_devices(sim, app_name, services, fog_clusters_id)
        for module in services:
            if module in deployed_end_devices:
                continue

            # Search for fog clusters
            elif module in self.scaleServices:
                allocation_nodes_mapping = []
                if fog_clusters_id:
                    ranked_with_latency = self._sort_fog_nodes_dijkstra(sim, app_name, fog_clusters_id)
                    latency_map = {nid: lat for nid, lat in ranked_with_latency}
                    ranked_nodes_by_latency = [nid for nid, _ in ranked_with_latency]
                    
                    for node_id in ranked_nodes_by_latency:
                        node_latency = latency_map[node_id]
                        node_label = sim.topology.get_node(node_id).get("label", node_id)
                        node_failures = int(sim.topology.get_node(node_id).get("failures", 0))
                        node_execution_time = int(sim.topology.get_node(node_id).get("execution_time", 0)) / 100 # simulation clock
                        # failure_rate λ = failures / uptime (in simulation ticks)
                        node_failure_rate = node_failures / node_execution_time if node_execution_time > 0 else 0

                        # Get the node's processing speed (instructions per time unit).
                        node_ipt = sim.topology.get_node(node_id).get("IPT", 0)

                        # Get the module's instruction count (app_ipt).
                        app_ipt = 0
                        for app_module in app.data:
                            if module in app_module:
                                app_ipt = app_module[module].get("IPT", 0)
                                break

                        # Mission time = (app_ipt / node_ipt) * app_lifetime
                        # Faster nodes (higher IPT) finish sooner → shorter exposure → higher reliability.
                        ipt_ratio = (app_ipt / node_ipt) if node_ipt > 0 else 1.0
                        mission_time = ipt_ratio * 100 # simulation clock # * self.app_lifetime

                        # R(t) = e^(-failure_rate * mission_time)
                        node_reliability = math.exp(-node_failure_rate * mission_time)
                        logging.info("Node Reliability for %s: %.15f (failure_rate=%.9f, node_ipt=%s, app_ipt=%s, ipt_ratio=%.4f, mission_time=%.2f, failures=%d, uptime=%d)",
                                    node_label, node_reliability, node_failure_rate, node_ipt, app_ipt, ipt_ratio, mission_time, node_failures, node_execution_time)
                        logging.info("Node %s (ID: %s) - Failure Rate Calculated: %.15f", node_label, node_id, node_failure_rate)
                        
                        # (LATENCY_WEIGHT · node_latency) + (RELIABILITY_WEIGHT · (1 − node_reliability))
                        allocation_cost = (LATENCY_WEIGHT * node_latency) + (RELIABILITY_WEIGHT * (1 - node_reliability))

                        logging.info("Allocation cost for node %s: %.15f", node_label, allocation_cost)

                        node_object = {
                            "id": node_id,
                            "label": node_label,
                            "failure_rate": node_failure_rate,
                            "reliability": node_reliability,
                            "latency": node_latency,
                            "allocation_cost": allocation_cost,
                        }

                        allocation_nodes_mapping.append(node_object)

                    # Sort by allocation cost (ascending)
                    allocation_nodes_mapping.sort(key=lambda x: x["allocation_cost"])

                    # Allocate to cloud if no fog nodes are available
                    if not allocation_nodes_mapping:
                        target_nodes = list(cloud_cluster_id)
                    else:
                        target_nodes = [node["id"] for node in allocation_nodes_mapping]    
                    
                    # Deploy replicas - default YAFS behavior - 1 replica
                    replicas_needed = self.scaleServices[module]

                    for node in allocation_nodes_mapping:
                        logging.info("Node %s (ID: %s) - Failure Rate: %.15f", node["label"], node["id"], node["failure_rate"])

                    # Verify the threshold for adaptive replication
                    best_node_reliability = allocation_nodes_mapping[0]["reliability"] if allocation_nodes_mapping else 0
                    if best_node_reliability <= REPLICATION_THRESHOLD and len(allocation_nodes_mapping) > 1:
                        replicas_needed = max(replicas_needed, 2)
                        logging.info("Adaptive replication triggered: Increasing replicas to %d", replicas_needed)

                    ranked_targets = target_nodes[:replicas_needed]

                    for target in ranked_targets:
                        sim.deploy_module(app_name, module, services[module], [target])
                        
                        # get the node label based on node id
                        node_label = sim.topology.get_node(target).get("label", target)
                        logging.info("Placed %s on node %s", module, node_label)

                    # If not enough replicas were placed, use cloud
                    remaining = replicas_needed - len(ranked_targets)
                    if remaining > 0 and cloud_cluster_id:
                        cloud_target = cloud_cluster_id[0]
                        for _ in range(remaining):
                            sim.deploy_module(app_name, module, services[module], [cloud_target])

                        node_label = sim.topology.get_node(cloud_target).get("label", cloud_target)
                        logging.info("Placed %s on node %s", module, node_label)


    def initial_allocation(self, sim, app_name):
        strategy = self.strategy.lower() if self.strategy else ""
        if strategy == "static":
            self._static_strategy(sim, app_name)
        elif strategy == "latency":
            self._dijkstra_strategy(sim, app_name)
        elif strategy == "roundrobin":
            self._roundrobin_strategy(sim, app_name)
        elif strategy == "custom":
            self._custom_strategy(sim, app_name)
        else:
            logging.warning("Unknown CustomPlacement strategy '%s' for app %s", self.strategy, app_name)
