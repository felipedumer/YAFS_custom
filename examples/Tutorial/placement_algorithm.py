from yafs.placement import Placement
import logging

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
                        logging.error(f"Not enough RAM on Cloud (ID: {id_cloud}) for {module}. "
                              f"Required: {required_ram}, Available: {available_ram}")
                        raise Exception(f"Deployment failed for {module}: Insufficient RAM.")
