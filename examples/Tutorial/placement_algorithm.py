from yafs.placement import Placement
import logging
import csv
import os

class CloudPlacement(Placement):
    """
    This implementation locates the services of the application in the Fog nodes first.
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
        # Sort for deterministic behavior
        id_fog_list.sort()
        
        # Implement Round Robin based on App ID
        # Since a new Placement object is created for each App, we can't store state.
        # We use the App ID to determine the starting node.
        try:
            # Assuming app_name format "Application-X"
            app_id_num = int(app_name.split("-")[1])
            start_index = app_id_num % len(id_fog_list)
            # Rotate the list so we start checking from a different node each time
            id_fog_list = id_fog_list[start_index:] + id_fog_list[:start_index]
        except (IndexError, ValueError):
            pass # Fallback to default order if name format is unexpected
        
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
