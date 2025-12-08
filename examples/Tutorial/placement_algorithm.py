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
    - 'custom_proposed_by_felipe': Weighted score of Latency, IPT, COST, and WATT.
    """
    def __init__(self, name, activation_dist=None, logger=None, strategy='latency'):
        super(CloudPlacement, self).__init__(name, activation_dist, logger)
        self.strategy = strategy

    def _sort_fog_nodes(self, sim, app_name, id_fog_list):
        """
        Sorts the list of Fog nodes based on the selected strategy.
        """
        if not id_fog_list:
            return []

        # Strategies that require a source sensor
        if self.strategy in ['latency', 'hops']:
            sensor_model = f"{app_name}-Sensor"
            sensor_nodes = sim.topology.find_IDs({"model": sensor_model})
            
            if not sensor_nodes:
                logging.warning(f"Sensor for {app_name} not found. Fallback to simple sort.")
                return sorted(id_fog_list)
            
            sensor_id = sensor_nodes[0]
            weight = 'PR' if self.strategy == 'latency' else None
            
            fog_distances = []
            for fog_id in id_fog_list:
                try:
                    distance = nx.shortest_path_length(sim.topology.G, source=sensor_id, target=fog_id, weight=weight)
                    fog_distances.append((fog_id, distance))
                except nx.NetworkXNoPath:
                    fog_distances.append((fog_id, float('inf')))
            
            # Sort by distance (ascending)
            fog_distances.sort(key=lambda x: x[1])
            
            # Logging for debugging
            sensor_label = sim.topology.get_node(sensor_id).get('label', sensor_id)
            formatted_distances = [f"{sim.topology.get_node(fid).get('label', fid)}: {dist}" for fid, dist in fog_distances]
            logging.info(f"[{self.strategy.upper()}] App {app_name}: Distances from {sensor_label} to Fog: {', '.join(formatted_distances)}")
            
            return [x[0] for x in fog_distances]

        # Strategies based on Node Attributes
        elif self.strategy == 'cost':
            # Sort by COST (ascending)
            return sorted(id_fog_list, key=lambda x: sim.topology.get_node(x).get('COST', float('inf')))
            
        elif self.strategy == 'ipt':
            # Sort by IPT (descending - higher is better)
            return sorted(id_fog_list, key=lambda x: sim.topology.get_node(x).get('IPT', 0), reverse=True)

        elif self.strategy == 'custom_proposed_by_felipe':
            # 1. Identify Sensor for Latency Calculation
            sensor_model = f"{app_name}-Sensor"
            sensor_nodes = sim.topology.find_IDs({"model": sensor_model})
            sensor_id = sensor_nodes[0] if sensor_nodes else None

            # 2. Collect Metrics for all Fog Nodes
            node_metrics = []
            for fog_id in id_fog_list:
                node = sim.topology.get_node(fog_id)
                
                # Attributes
                ipt = node.get('IPT', 0)
                cost = node.get('COST', float('inf'))
                watt = node.get('WATT', float('inf'))
                
                # Latency (Dijkstra)
                latency = float('inf')
                if sensor_id is not None:
                    try:
                        latency = nx.shortest_path_length(sim.topology.G, source=sensor_id, target=fog_id, weight='PR')
                    except nx.NetworkXNoPath:
                        pass
                
                node_metrics.append({
                    'id': fog_id,
                    'ipt': ipt,
                    'cost': cost,
                    'watt': watt,
                    'latency': latency
                })

            # 3. Normalize and Score
            # Filter valid nodes for min/max calculation
            valid_metrics = [m for m in node_metrics if m['latency'] != float('inf')]
            
            if not valid_metrics:
                return sorted(id_fog_list) # Fallback

            # Helper to safely get min/max
            def get_min_max(key):
                vals = [m[key] for m in valid_metrics]
                return min(vals), max(vals)

            min_ipt, max_ipt = get_min_max('ipt')
            min_cost, max_cost = get_min_max('cost')
            min_watt, max_watt = get_min_max('watt')
            min_lat, max_lat = get_min_max('latency')

            # Weights (Adjustable)
            W_LATENCY = 0.1
            W_IPT = 0.5
            W_COST = 0.2
            W_WATT = 0.2

            scored_nodes = []
            for m in node_metrics:
                if m['latency'] == float('inf'):
                    score = -1.0 # Penalize unreachable nodes
                else:
                    # Normalize (0 to 1)
                    # Higher is better for IPT
                    norm_ipt = (m['ipt'] - min_ipt) / (max_ipt - min_ipt) if max_ipt > min_ipt else 0.0
                    
                    # Lower is better for Cost, Watt, Latency (Invert: 1 - norm)
                    norm_cost = (m['cost'] - min_cost) / (max_cost - min_cost) if max_cost > min_cost else 0.0
                    norm_watt = (m['watt'] - min_watt) / (max_watt - min_watt) if max_watt > min_watt else 0.0
                    norm_lat = (m['latency'] - min_lat) / (max_lat - min_lat) if max_lat > min_lat else 0.0
                    
                    # Score Calculation (Higher score is better)
                    score = (W_IPT * norm_ipt) + \
                            (W_COST * (1 - norm_cost)) + \
                            (W_WATT * (1 - norm_watt)) + \
                            (W_LATENCY * (1 - norm_lat))
                
                scored_nodes.append((m['id'], score))

            # Sort by Score (Descending)
            scored_nodes.sort(key=lambda x: x[1], reverse=True)
            
            # Log the ranking
            ranking_str = ", ".join([f"{sim.topology.get_node(nid).get('label', nid)}: {score:.2f}" for nid, score in scored_nodes])
            logging.info(f"[CUSTOM] App {app_name} Ranking: {ranking_str}")

            return [x[0] for x in scored_nodes]
            
        else:
            logging.warning(f"Unknown strategy '{self.strategy}'. Defaulting to simple sort.")
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
                     logging.info(f"Deployed {module} on Sensor Node (ID: {sensor_nodes[0]})")
                     continue

            if module in self.scaleServices:
                for rep in range(0, self.scaleServices[module]):
                    required_ram = module_specs[module].get("RAM", 0)
                    deployed = False

                    # 1. Try Fog Nodes
                    for id_fog in id_fog_list:
                        fog_node = sim.topology.get_node(id_fog)
                        available_ram = fog_node.get("RAM", 0)
                        
                        if available_ram >= required_ram:
                            sim.deploy_module(app_name, module, services[module], [id_fog])
                            fog_node["RAM"] -= required_ram
                            logging.info(f"Deployed {module} on {fog_node.get('label')} (ID: {id_fog}). Remaining RAM: {fog_node['RAM']}")
                            deployed = True
                            break
                    
                    if deployed:
                        continue

                    # 2. Try Cloud Node
                    if cloud_node:
                        available_ram = cloud_node.get("RAM", 0)
                        if available_ram >= required_ram:
                            sim.deploy_module(app_name, module, services[module], [id_cloud])
                            cloud_node["RAM"] -= required_ram
                            logging.info(f"Deployed {module} on Cloud (ID: {id_cloud}). Remaining RAM: {cloud_node['RAM']}")
                            deployed = True
                    
                    if not deployed:
                        msg = f"Not enough RAM on Fog nodes or Cloud for {module}. Required: {required_ram}"
                        logging.error(msg)
                        
                        # Register error in a CSV file
                        error_log_path = "resultados/deployment_errors.csv"
                        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

                        file_exists = os.path.isfile(error_log_path)
                        with open(error_log_path, 'a', newline='') as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(["App", "Module", "NodeID", "RequiredRAM", "AvailableRAM", "Message"])
                            writer.writerow([app_name, module, "None", required_ram, "N/A", msg])
    
    def run(self, sim):
        """
        This method is invoked periodically by the simulator to reallocate services.
        Strategy:
        - Time < 2000: Migrate Fog -> Cloud.
        - Time >= 2000: Migrate Cloud -> Fog.
        """
        current_time = sim.env.now
        logging.info(f"Running Reallocation Strategy for {self.name} at time {current_time}")
        
        # We need to iterate over the applications managed by this placement policy
        # Since we create one policy per app, we can extract the app name from the policy name
        # Policy name format: "CloudPlacement-{app_id}" -> App name: "Application-{app_id}"
        try:
            app_id = self.name.split("-")[1]
            app_name = f"Application-{app_id}"
        except IndexError:
            logging.error(f"Could not parse app ID from placement policy name: {self.name}")
            return

        if app_name not in sim.apps:
            return

        app = sim.apps[app_name]
        services = app.services
        
        # Get Cloud Node ID
        value_cloud = {"mytag": "cloud"}
        id_cloud_list = sim.topology.find_IDs(value_cloud)
        if not id_cloud_list:
            return
        id_cloud = id_cloud_list[0]

        # Get Fog Nodes
        value_fog = {"mytag": "fog"}
        id_fog_list = sim.topology.find_IDs(value_fog)

        # Iterate over services
        for module in services:
            # Skip Sensor modules (Fixed placement)
            if module.endswith("-Sensor"):
                continue

            # Check where the module is currently deployed
            # sim.alloc_module[app_name][module] returns a list of DES IDs (not Node IDs)
            des_ids = sim.alloc_module[app_name].get(module, [])
            
            for des_id in des_ids:
                # Get the actual Node ID from the DES ID
                current_node_id = sim.alloc_DES[des_id]
                
                # Get required RAM
                required_ram = 0
                for item in app.data:
                    if module in item:
                        required_ram = item[module].get("RAM", 0)
                        break

                # Strategy 1: Fog -> Cloud (Time < 2000)
                if current_time < 2000:
                    if current_node_id != id_cloud:
                        logging.info(f"Time < 2000: Service {module} is on Fog (ID: {current_node_id}). Migrating to Cloud...")
                        
                        cloud_node = sim.topology.get_node(id_cloud)
                        available_ram = cloud_node.get("RAM", 0)
                        
                        if available_ram >= required_ram:
                            # Perform Migration
                            logging.info(f"Migrating {module} from Fog (ID: {current_node_id}) to Cloud (ID: {id_cloud})")
                            
                            # 1. Undeploy from Fog
                            sim.undeploy_module(app_name, module, des_id)
                            fog_node = sim.topology.get_node(current_node_id)
                            
                            if "RAM" in fog_node:
                                fog_node["RAM"] += required_ram
                            else:
                                logging.warning(f"Node {current_node_id} ({fog_node.get('label')}) has no 'RAM' attribute. Cannot restore RAM.")

                            # 2. Deploy to Cloud
                            sim.deploy_module(app_name, module, services[module], [id_cloud])
                            cloud_node["RAM"] -= required_ram
                            
                        else:
                            logging.info(f"Could not migrate {module} to Cloud. Cloud has not enough RAM.")

                # Strategy 2: Cloud -> Fog (Time >= 2000)
                else:
                    if current_node_id == id_cloud:
                        logging.info(f"Time >= 2000: Service {module} is on Cloud. Migrating to Fog...")
                        
                        # Sort Fog Nodes based on Strategy
                        target_fog_list = self._sort_fog_nodes(sim, app_name, id_fog_list)
                        
                        migrated = False
                        for id_fog in target_fog_list:
                            fog_node = sim.topology.get_node(id_fog)
                            available_ram = fog_node.get("RAM", 0)
                            
                            if available_ram >= required_ram:
                                logging.info(f"Migrating {module} from Cloud to {fog_node.get('label')} (ID: {id_fog})")
                                
                                # 1. Undeploy from Cloud
                                sim.undeploy_module(app_name, module, des_id)
                                cloud_node = sim.topology.get_node(id_cloud)
                                cloud_node["RAM"] += required_ram
                                
                                # 2. Deploy to Fog
                                sim.deploy_module(app_name, module, services[module], [id_fog])
                                fog_node["RAM"] -= required_ram
                                
                                migrated = True
                                break
                        
                        if not migrated:
                            logging.info(f"Could not migrate {module} from Cloud. No Fog node has enough RAM.")
