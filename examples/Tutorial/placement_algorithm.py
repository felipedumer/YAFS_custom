from yafs.placement import Placement
import logging
import csv
import os
import networkx as nx

class CloudPlacement(Placement):
    """
    This implementation locates the services of the application in the nearest Fog node with available RAM.
    If there is no space (RAM), it tries the Cloud.
    """
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
        
        # Find the sensor node for this application to determine proximity
        sensor_model = f"{app_name}-Sensor"
        sensor_nodes = sim.topology.find_IDs({"model": sensor_model})
        
        if sensor_nodes:
            sensor_id = sensor_nodes[0]
            # Calculate shortest path (latency) from sensor to each fog node
            # We use 'PR' (Propagation Delay) as the weight
            fog_distances = []
            for fog_id in id_fog_list:
                try:
                    # Calculate distance based on Propagation Delay (PR)
                    distance = nx.shortest_path_length(sim.topology.G, source=sensor_id, target=fog_id, weight='PR')
                    fog_distances.append((fog_id, distance))
                except nx.NetworkXNoPath:
                    fog_distances.append((fog_id, float('inf')))
            
            # Sort fog nodes by distance (nearest first)
            fog_distances.sort(key=lambda x: x[1])
            id_fog_list = [x[0] for x in fog_distances]

            sensor_label = sim.topology.get_node(sensor_id).get('label', sensor_id)
            formatted_distances = [f"{sim.topology.get_node(fid).get('label', fid)}: {dist}" for fid, dist in fog_distances]
            logging.info(f"App {app_name}: Distances from {sensor_label} (ID: {sensor_id}) to Fog nodes: {', '.join(formatted_distances)}")
        else:
            # Fallback to simple sort if sensor not found
            id_fog_list.sort()
        
        app = sim.apps[app_name]
        services = app.services

        # Create a dictionary for easier access to module specifications (RAM, etc.)
        module_specs = {}
        for item in app.data:
            module_specs.update(item)

        for module in services:
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
