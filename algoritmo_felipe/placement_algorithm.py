from yafs.placement import Placement
import logging
import csv
import os
import networkx as nx


class CloudPlacement(Placement):
    """
    This implementation locates the services of the application in the nearest Fog node with available RAM.
    If there is no space (RAM), it tries the Cloud.

    Strategies:
    - 'latency': Minimize propagation delay (PR).
    - 'hops': Minimize number of network hops.
    - 'cost': Minimize infrastructure cost (COST attribute).
    - 'ipt': Maximize processing power (IPT attribute).
    - 'roundRobin': Distribute apps cyclically across nodes.
    - 'custom_proposed_by_felipe': Weighted score of Latency, IPT, COST, and WATT.
    """

    def __init__(self, name, activation_dist=None, logger=None, strategy="latency"):
        super(CloudPlacement, self).__init__(name, activation_dist, logger)
        self.strategy = strategy

    def _sort_fog_nodes(self, sim, app_name, id_fog_list):
        """
        Sorts the list of Fog nodes based on the selected strategy.
        """
        # Filter out nodes that might have been removed dynamically
        id_fog_list = [nid for nid in id_fog_list if sim.topology.G.has_node(nid)]

        if not id_fog_list:
            return []

        # Strategies that require a source sensor
        if self.strategy in ["latency", "hops"]:
            sensor_model = f"{app_name}-Sensor"
            sensor_nodes = sim.topology.find_IDs({"model": sensor_model})

            if not sensor_nodes:
                logging.warning(
                    f"Sensor for {app_name} not found. Fallback to simple sort."
                )
                return sorted(id_fog_list)

            sensor_id = sensor_nodes[0]
            weight = "PR" if self.strategy == "latency" else None

            fog_distances = []
            for fog_id in id_fog_list:
                try:
                    distance = nx.shortest_path_length(
                        sim.topology.G, source=sensor_id, target=fog_id, weight=weight
                    )
                    fog_distances.append((fog_id, distance))
                except nx.NetworkXNoPath:
                    fog_distances.append((fog_id, float("inf")))

            # Sort by distance (ascending)
            fog_distances.sort(key=lambda x: x[1])

            # Logging for debugging
            sensor_label = sim.topology.get_node(sensor_id).get("label", sensor_id)
            formatted_distances = []
            for fid, dist in fog_distances:
                node = (
                    sim.topology.get_node(fid) if sim.topology.G.has_node(fid) else {}
                )
                node_label = node.get("label", fid)
                formatted_distances.append(f"{node_label}: {dist}")
            logging.info(
                f"[{self.strategy.upper()}] App {app_name}: Distances from {sensor_label} to Fog: {', '.join(formatted_distances)}"
            )

            return [x[0] for x in fog_distances]

        # Strategies based on Node Attributes
        elif self.strategy == "cost":
            # Sort by COST (ascending)
            return sorted(
                id_fog_list,
                key=lambda x: sim.topology.get_node(x).get("COST", float("inf")),
            )

        elif self.strategy == "ipt":
            # Sort by IPT (descending - higher is better)
            return sorted(
                id_fog_list,
                key=lambda x: sim.topology.get_node(x).get("IPT", 0),
                reverse=True,
            )

        elif self.strategy == "roundRobin":
            # Sort by ID first to ensure deterministic order before rotation
            sorted_list = sorted(id_fog_list)
            try:
                # Extract App ID (e.g., "Application-1" -> 1)
                app_id = int(app_name.split("-")[1])
                # Rotate list: start at (app_id % len)
                start_index = app_id % len(sorted_list)
                rotated_list = sorted_list[start_index:] + sorted_list[:start_index]
                logging.info(
                    f"[ROUND_ROBIN] App {app_name} (ID {app_id}) starting at node index {start_index} (Node ID {rotated_list[0]})"
                )
                return rotated_list
            except (IndexError, ValueError):
                logging.warning(
                    f"Could not parse App ID from {app_name} for Round Robin. Using default sort."
                )
                return sorted_list

        elif self.strategy == "custom_proposed_by_felipe":
            # 1. Identify Sensor for Latency Calculation
            sensor_model = f"{app_name}-Sensor"
            sensor_nodes = sim.topology.find_IDs({"model": sensor_model})
            sensor_id = sensor_nodes[0] if sensor_nodes else None

            # 2. Collect Metrics for all Fog Nodes
            node_metrics = []
            for fog_id in id_fog_list:
                node = sim.topology.get_node(fog_id)

                # Attributes
                ipt = node.get("IPT", 0)
                cost = node.get("COST", float("inf"))
                watt = node.get("WATT", float("inf"))

                # Latency (Dijkstra)
                latency = float("inf")
                if sensor_id is not None:
                    try:
                        latency = nx.shortest_path_length(
                            sim.topology.G, source=sensor_id, target=fog_id, weight="PR"
                        )
                    except nx.NetworkXNoPath:
                        pass

                node_metrics.append(
                    {
                        "id": fog_id,
                        "ipt": ipt,
                        "cost": cost,
                        "watt": watt,
                        "latency": latency,
                    }
                )

            # 3. Normalize and Score
            # Filter valid nodes for min/max calculation
            valid_metrics = [m for m in node_metrics if m["latency"] != float("inf")]

            if not valid_metrics:
                return sorted(id_fog_list)  # Fallback

            # Helper to safely get min/max
            def get_min_max(key):
                vals = [m[key] for m in valid_metrics]
                return min(vals), max(vals)

            min_ipt, max_ipt = get_min_max("ipt")
            min_cost, max_cost = get_min_max("cost")
            min_watt, max_watt = get_min_max("watt")
            min_lat, max_lat = get_min_max("latency")

            # Weights (Adjustable)
            W_LATENCY = 0.50
            W_IPT = 0.50
            W_COST = 0.0
            W_WATT = 0.0

            scored_nodes = []
            for m in node_metrics:
                if m["latency"] == float("inf"):
                    score = -1.0  # Penalize unreachable nodes
                else:
                    # Normalize (0 to 1)
                    # Higher is better for IPT
                    norm_ipt = (
                        (m["ipt"] - min_ipt) / (max_ipt - min_ipt)
                        if max_ipt > min_ipt
                        else 0.0
                    )

                    # Lower is better for Cost, Watt, Latency (Invert: 1 - norm)
                    norm_cost = (
                        (m["cost"] - min_cost) / (max_cost - min_cost)
                        if max_cost > min_cost
                        else 0.0
                    )
                    norm_watt = (
                        (m["watt"] - min_watt) / (max_watt - min_watt)
                        if max_watt > min_watt
                        else 0.0
                    )
                    norm_lat = (
                        (m["latency"] - min_lat) / (max_lat - min_lat)
                        if max_lat > min_lat
                        else 0.0
                    )

                    # Score Calculation (Higher score is better)
                    score = (
                        (W_IPT * norm_ipt)
                        + (W_COST * (1 - norm_cost))
                        + (W_WATT * (1 - norm_watt))
                        + (W_LATENCY * (1 - norm_lat))
                    )

                scored_nodes.append((m["id"], score))

            # Sort by Score (Descending)
            scored_nodes.sort(key=lambda x: x[1], reverse=True)

            # Log the ranking
            ranking_str = ", ".join(
                [
                    f"{sim.topology.get_node(nid).get('label', nid)}: {score:.2f}"
                    for nid, score in scored_nodes
                ]
            )
            logging.info(f"[CUSTOM] App {app_name} Ranking: {ranking_str}")

            return [x[0] for x in scored_nodes]

        else:
            logging.warning(
                f"Unknown strategy '{self.strategy}'. Defaulting to simple sort."
            )
            return sorted(id_fog_list)

    def initial_allocation(self, sim, app_name):
        # Get Cloud Node
        value_cloud = {"mytag": "cloud"}
        id_cloud_list = sim.topology.find_IDs(value_cloud)
        cloud_node = None
        id_cloud = None
        if id_cloud_list:
            id_cloud = id_cloud_list[0]
            cloud_node = sim.topology.get_node(id_cloud)

        # Get Fog Nodes
        value_fog = {"mytag": "fog"}
        id_fog_list = sim.topology.find_IDs(value_fog)

        # Sort Fog Nodes based on Strategy
        id_fog_list = self._sort_fog_nodes(sim, app_name, id_fog_list)

        app = sim.apps[app_name]
        services = app.services

        # Create a dictionary for easier access to module specifications (RAM, etc.)
        module_specs = {}
        for item in app.data:
            module_specs.update(item)

        for module in services:
            # Handle Sensor Placement (Fixed on the Sensor Node)
            if module.endswith("-Sensor"):
                sensor_nodes = sim.topology.find_IDs({"model": module})
                if sensor_nodes:
                    sim.deploy_module(app_name, module, services[module], sensor_nodes)
                    logging.info(
                        f"Deployed {module} on Sensor Node (ID: {sensor_nodes[0]})"
                    )
                    continue

            if module in self.scaleServices:
                # CUSTOM STRATEGY: Force 2 replicas on different ISPs
                if self.strategy == "custom_proposed_by_felipe":
                    required_ram = module_specs[module].get("RAM", 0)
                    # Deploy the service on two nodes when using the custom strategy
                    target_replicas = 2
                    deployed_nodes = []
                    used_isps = set()

                    # Pass 1: Try to find nodes with different ISPs
                    for id_fog in id_fog_list:
                        if len(deployed_nodes) >= target_replicas:
                            break

                        fog_node = sim.topology.get_node(id_fog)
                        available_ram = fog_node.get("RAM", 0)
                        node_isp = fog_node.get("ISP")

                        # if available_ram >= required_ram and node_isp not in used_isps:
                        if available_ram >= required_ram:
                            sim.deploy_module(
                                app_name, module, services[module], [id_fog]
                            )
                            fog_node["RAM"] -= required_ram
                            deployed_nodes.append(id_fog)
                            used_isps.add(node_isp)
                            logging.info(
                                f"[CUSTOM] Deployed {module} on {fog_node.get('label')} (ID: {id_fog}, ISP: {node_isp})"
                            )

                    # Pass 2: Fill remaining replicas with any available Fog node (ignoring ISP)
                    if len(deployed_nodes) < target_replicas:
                        for id_fog in id_fog_list:
                            if len(deployed_nodes) >= target_replicas:
                                break

                            if id_fog in deployed_nodes:
                                continue

                            fog_node = sim.topology.get_node(id_fog)
                            available_ram = fog_node.get("RAM", 0)

                            if available_ram >= required_ram:
                                sim.deploy_module(
                                    app_name, module, services[module], [id_fog]
                                )
                                fog_node["RAM"] -= required_ram
                                deployed_nodes.append(id_fog)
                                logging.info(
                                    f"[CUSTOM] Deployed {module} on {fog_node.get('label')} (ID: {id_fog}) - ISP constraint relaxed"
                                )

                    # Pass 3: Cloud fallback
                    if len(deployed_nodes) < target_replicas and cloud_node:
                        # Only allow 1 replica on Cloud to avoid redundancy on the same node
                        if id_cloud not in deployed_nodes:
                            available_ram = cloud_node.get("RAM", 0)
                            if available_ram >= required_ram:
                                sim.deploy_module(
                                    app_name, module, services[module], [id_cloud]
                                )
                                cloud_node["RAM"] -= required_ram
                                deployed_nodes.append(id_cloud)
                                logging.info(
                                    f"[CUSTOM] Deployed {module} on Cloud (ID: {id_cloud})"
                                )

                    if len(deployed_nodes) == 0:
                        msg = f"[CUSTOM] Failed to deploy {module}. Required RAM: {required_ram}. No suitable node found."
                        logging.error(msg)
                        # Register error in a CSV file
                        error_log_path = "resultados/deployment_errors.csv"
                        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

                        file_exists = os.path.isfile(error_log_path)
                        with open(error_log_path, "a", newline="") as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(
                                    [
                                        "App",
                                        "Module",
                                        "NodeID",
                                        "RequiredRAM",
                                        "AvailableRAM",
                                        "Message",
                                    ]
                                )
                            writer.writerow(
                                [app_name, module, "None", required_ram, "N/A", msg]
                            )
                else:
                    for rep in range(0, self.scaleServices[module]):
                        required_ram = module_specs[module].get("RAM", 0)
                        deployed = False

                        # 1. Try Fog Nodes
                        for id_fog in id_fog_list:
                            fog_node = sim.topology.get_node(id_fog)
                            available_ram = fog_node.get("RAM", 0)

                            if available_ram >= required_ram:
                                sim.deploy_module(
                                    app_name, module, services[module], [id_fog]
                                )
                                fog_node["RAM"] -= required_ram
                                logging.info(
                                    f"Deployed {module} on {fog_node.get('label')} (ID: {id_fog}). Remaining RAM: {fog_node['RAM']}"
                                )
                                deployed = True
                                break

                        if deployed:
                            continue

                        # 2. Try Cloud Node
                        if cloud_node:
                            available_ram = cloud_node.get("RAM", 0)
                            if available_ram >= required_ram:
                                sim.deploy_module(
                                    app_name, module, services[module], [id_cloud]
                                )
                                cloud_node["RAM"] -= required_ram
                                logging.info(
                                    f"Deployed {module} on Cloud (ID: {id_cloud}). Remaining RAM: {cloud_node['RAM']}"
                                )
                                deployed = True

                        if not deployed:
                            msg = f"Not enough RAM on Fog nodes or Cloud for {module}. Required: {required_ram}"
                            logging.error(msg)

                            # Register error in a CSV file
                            error_log_path = "resultados/deployment_errors.csv"
                            os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

                            file_exists = os.path.isfile(error_log_path)
                            with open(error_log_path, "a", newline="") as f:
                                writer = csv.writer(f)
                                if not file_exists:
                                    writer.writerow(
                                        [
                                            "App",
                                            "Module",
                                            "NodeID",
                                            "RequiredRAM",
                                            "AvailableRAM",
                                            "Message",
                                        ]
                                    )
                                writer.writerow(
                                    [app_name, module, "None", required_ram, "N/A", msg]
                                )

    def run(self, sim):
        """
        This method is invoked periodically by the simulator to reallocate services.
        It checks if there are better nodes available for the services based on the current strategy.
        """
        current_time = sim.env.now
        logging.info(
            f"Running Reallocation Strategy for {self.name} at time {current_time}"
        )

        # Parse app_name from policy name
        try:
            app_id = self.name.split("-")[1]
            app_name = f"Application-{app_id}"
        except IndexError:
            logging.error(
                f"Could not parse app ID from placement policy name: {self.name}"
            )
            return

        if app_name not in sim.apps:
            return

        app = sim.apps[app_name]
        services = app.services

        # Get Fog Nodes
        value_fog = {"mytag": "fog"}
        id_fog_list = sim.topology.find_IDs(value_fog)

        # Sort Fog Nodes based on Strategy (Best first)
        sorted_fog_nodes = self._sort_fog_nodes(sim, app_name, id_fog_list)

        # Iterate over services
        for module in services:
            # Skip Sensor modules (Fixed placement)
            if module.endswith("-Sensor"):
                continue

            # Get current deployments
            # sim.alloc_module[app_name][module] -> list of DES IDs
            # We iterate over a copy because we might modify the list during migration
            des_ids = list(sim.alloc_module[app_name].get(module, []))

            # Get required RAM
            required_ram = 0
            for item in app.data:
                if module in item:
                    required_ram = item[module].get("RAM", 0)
                    break

            # For each current deployment, check if we can improve it
            for des_id in des_ids:
                current_node_id = sim.alloc_DES[des_id]
                current_node = sim.topology.get_node(current_node_id)

                best_node_id = None

                # Special handling for Custom Strategy (ISP constraint)
                if self.strategy == "custom_proposed_by_felipe":
                    # Gather all current locations of this module to check ISP diversity
                    # Note: We use the current state of deployments.
                    # If we just moved a replica, it will be reflected in sim.alloc_module if we query it again,
                    # but here we are using the snapshot 'des_ids'.
                    # However, for ISP check, we should look at *other* replicas.

                    current_allocations = sim.alloc_module[app_name].get(module, [])
                    other_locs = [
                        sim.alloc_DES[d] for d in current_allocations if d != des_id
                    ]
                    used_isps = {
                        sim.topology.get_node(l).get("ISP") for l in other_locs
                    }

                    current_rank = -1
                    if current_node_id in sorted_fog_nodes:
                        current_rank = sorted_fog_nodes.index(current_node_id)
                    else:
                        current_rank = float(
                            "inf"
                        )  # Current node is not in fog list (e.g. Cloud)

                    # Search for a better node
                    for i, candidate_id in enumerate(sorted_fog_nodes):
                        # If candidate is the current node, we are already at best possible position
                        if candidate_id == current_node_id:
                            break

                        # If we found a candidate that is better ranked than current
                        if i < current_rank:
                            candidate_node = sim.topology.get_node(candidate_id)
                            available_ram = candidate_node.get("RAM", 0)

                            if available_ram >= required_ram:
                                # Check ISP constraint
                                if candidate_node.get("ISP") not in used_isps:
                                    best_node_id = candidate_id
                                    break

                else:
                    # Standard strategies
                    current_rank = (
                        sorted_fog_nodes.index(current_node_id)
                        if current_node_id in sorted_fog_nodes
                        else float("inf")
                    )

                    for i, candidate_id in enumerate(sorted_fog_nodes):
                        if candidate_id == current_node_id:
                            break

                        if i < current_rank:
                            candidate_node = sim.topology.get_node(candidate_id)
                            if candidate_node.get("RAM", 0) >= required_ram:
                                best_node_id = candidate_id
                                break

                # Perform Migration if a better node was found
                if best_node_id:
                    target_node = sim.topology.get_node(best_node_id)
                    logging.info(
                        f"Migrating {module} from {current_node.get('label')} (ID: {current_node_id}) to {target_node.get('label')} (ID: {best_node_id})"
                    )

                    # 1. Undeploy from current node
                    sim.undeploy_module(app_name, module, des_id)
                    if "RAM" in current_node:
                        current_node["RAM"] += required_ram
                    else:
                        # If it was cloud or some node without RAM tracking (unlikely given the code)
                        pass

                    # 2. Deploy to new node
                    sim.deploy_module(
                        app_name, module, services[module], [best_node_id]
                    )
                    target_node["RAM"] -= required_ram
