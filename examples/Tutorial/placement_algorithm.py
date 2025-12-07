from yafs.placement import Placement
import logging
import csv
import os

class CloudPlacement(Placement):
    """
    This implementation locates the services of the application in the cheapest cloud,
    but checks if there is enough RAM available.
    """
    def initial_allocation(self, sim, app_name):
        # Find the ID-node/resource
        value = {"mytag": "cloud"} 
        id_cluster_list = sim.topology.find_IDs(value)
        
        if not id_cluster_list:
            logging.info("No cloud node found!")
            return

        # Assuming we want to use the first available cloud node
        id_cloud = id_cluster_list[0]
        cloud_node = sim.topology.get_node(id_cloud)
        
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
                    available_ram = cloud_node.get("RAM", 0)
                    
                    if available_ram >= required_ram:
                        # Deploy the module
                        sim.deploy_module(app_name, module, services[module], [id_cloud])
                        
                        # Update the node's RAM
                        cloud_node["RAM"] -= required_ram
                        logging.info(f"Deployed {module} on Cloud (ID: {id_cloud}). Remaining RAM: {cloud_node['RAM']}")
                    else:
                        msg = f"Not enough RAM on Cloud (ID: {id_cloud}) for {module}. Required: {required_ram}, Available: {available_ram}"
                        logging.error(msg)
                        
                        # Register error in a CSV file
                        error_log_path = "resultados/deployment_errors.csv"
                        os.makedirs(os.path.dirname(error_log_path), exist_ok=True)

                        file_exists = os.path.isfile(error_log_path)
                        with open(error_log_path, 'a', newline='') as f:
                            writer = csv.writer(f)
                            if not file_exists:
                                writer.writerow(["App", "Module", "NodeID", "RequiredRAM", "AvailableRAM", "Message"])
                            writer.writerow([app_name, module, id_cloud, required_ram, available_ram, msg])
                        
                        # We do not raise exception, just log the error and skip deployment
                        # raise Exception(f"Deployment failed for {module}: Insufficient RAM.")
