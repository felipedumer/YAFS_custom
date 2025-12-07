import time
import networkx
import random

from pathlib import Path

from yafs.core import Sim
from yafs.topology import Topology
from yafs.application import Application, Message, fractional_selectivity
from yafs.population import Statical
from yafs.distribution import deterministic_distribution

from placement_algorithm import CloudPlacement
from simpleSelection import MinimunPath

def create_random_topology(
    num_fog_nodes=2,
    random_seed=None,
    cloud_ipt=5 * 10**6,
    cloud_ram=10000,
    cloud_cost=10,
    cloud_watt=100.0,
    fog_ipt=1000 * 10**6,
    fog_ram=500,
    fog_cost=2,
    fog_watt=10.0,
    link_bw_cloud=100,
    link_pr_cloud=20,
    link_bw_fog=15,
    link_pr_fog=8,
    link_bw_aggregation=8,
    link_pr_aggregation=5,
    link_bw_edge=2,
    link_pr_edge=1,
    city_width=100,
    layer_gap=40,
):
    """
    Create a strict 4-layer topology (Cloud -> Fog -> Aggregation -> Edge).
    The number of nodes in lower layers is automatically generated.

    Layer 0 (Cloud): Single cloud node (high capacity).
    Layer 1 (Fog): Computational nodes connected to the cloud.
    Layer 2 (Aggregation): Communication-only nodes (routers/switches) connected to Fog nodes.
    Layer 3 (Edge): Home routers connected to Aggregation nodes, with sensors/actuators attached.

    Parameters:
        num_fog_nodes (int): Number of Fog nodes connected to the single Cloud node.
        random_seed (int, optional): Seed for random number generation. Defaults to None.
        cloud_ipt (float): Instructions per time unit for the Cloud node.
        cloud_ram (int): RAM available on the Cloud node.
        cloud_cost (float): Cost of using the Cloud node.
        cloud_watt (float): Power consumption of the Cloud node.
        fog_ipt (float): Instructions per time unit for Fog nodes.
        fog_ram (int): RAM available on Fog nodes.
        fog_cost (float): Cost of using Fog nodes.
        fog_watt (float): Power consumption of Fog nodes.
        link_bw_cloud (float): Bandwidth for link from Cloud to Fog.
        link_pr_cloud (float): Propagation delay for link from Cloud to Fog.
        link_bw_fog (float): Bandwidth for links from Fog to Aggregation.
        link_pr_fog (float): Propagation delay for links from Fog to Aggregation.
        link_bw_aggregation (float): Bandwidth for links from Aggregation to Edge routers.
        link_pr_aggregation (float): Propagation delay for links from Aggregation to Edge routers.
        link_bw_edge (float): Bandwidth for links from Edge routers to devices.
        link_pr_edge (float): Propagation delay for links from Edge routers to devices.
        city_width (float): Width of the simulation area (for x-coordinates).
        layer_gap (float): Vertical distance between layers (for y-coordinates).

    Returns:
        dict: A dictionary representing the topology with 'entity' and 'link' lists.
    """
    if random_seed is not None:
        random.seed(random_seed)

    # Automatically determine topology structure
    aggregation_nodes_per_fog = random.randint(2, 3)
    edge_nodes_per_aggregation = random.randint(2, 3)
    sensors_per_edge_node = 1
    actuators_per_edge_node = 1

    topology_json = {"entity": [], "link": []}
    node_id = 0

    def next_id():
        nonlocal node_id
        current = node_id
        node_id += 1
        return current

    def random_x():
        return random.uniform(0, city_width)

    # Predefined y positions so NetworkX layouts show clear layers
    cloud_y = layer_gap * 3
    fog_y = layer_gap * 2
    aggregation_y = layer_gap
    edge_y = 0
    device_y = -layer_gap

    # 1. Cloud Layer (Single Node)
    cloud_id = next_id()
    topology_json["entity"].append(
        {
            "id": cloud_id,
            "model": "cloud",
            "mytag": "cloud",
            "label": "Cloud",
            "IPT": cloud_ipt,
            "RAM": cloud_ram,
            "COST": cloud_cost,
            "WATT": cloud_watt,
            "x": city_width / 2,  # Center the cloud
            "y": cloud_y,
        }
    )

    # 2. Fog Layer (Computational Nodes)
    fog_ids = []
    for i in range(num_fog_nodes):
        fog_id = next_id()
        topology_json["entity"].append(
            {
                "id": fog_id,
                "model": f"fog",
                "mytag": "fog",
                "label": f"Fog-{i}",
                "IPT": fog_ipt,
                "RAM": fog_ram,
                "COST": fog_cost,
                "WATT": fog_watt,
                "x": random_x(),
                "y": fog_y,
            }
        )
        # Connect Fog to Cloud
        topology_json["link"].append(
            {"s": cloud_id, "d": fog_id, "BW": link_bw_cloud, "PR": link_pr_cloud}
        )
        fog_ids.append(fog_id)

    # 3. Aggregation Layer (Communication Only)
    aggregation_node_ids = []
    for fog_idx, fog_id in enumerate(fog_ids):
        for agg_idx in range(aggregation_nodes_per_fog):
            agg_id = next_id()
            topology_json["entity"].append(
                {
                    "id": agg_id,
                    "model": f"middle",
                    "mytag": "router", # Tagged as router since it's comm-only
                    "label": f"Middle-{fog_idx}-{agg_idx}",
                    "IPT": 0, # No computational power
                    "RAM": 0,
                    "x": random_x(),
                    "y": aggregation_y,
                }
            )
            # Connect Aggregation to Fog (Primary Link)
            topology_json["link"].append(
                {"s": fog_id, "d": agg_id, "BW": link_bw_fog, "PR": link_pr_fog}
            )
            
            connected_fogs = {fog_id}

            # Redundancy: Connect to other Fog nodes (Mesh-like)
            # Simulating a real-life scenario where intermediary nodes have backup connections
            if num_fog_nodes > 1:
                # Connect to 1 extra random fog node for redundancy
                other_fogs = [f for f in fog_ids if f not in connected_fogs]
                if other_fogs:
                    extra_fog = random.choice(other_fogs)
                    topology_json["link"].append(
                        {"s": extra_fog, "d": agg_id, "BW": link_bw_fog, "PR": link_pr_fog}
                    )
                    connected_fogs.add(extra_fog)

            aggregation_node_ids.append((fog_id, agg_id))

    # Redundancy: Horizontal connections between Aggregation nodes
    # Connect each aggregation node to at least one other aggregation node (Ring-like + Random)
    all_aggregation_nodes = [agg_id for _, agg_id in aggregation_node_ids]
    existing_horizontal_links = set()
    
    if len(all_aggregation_nodes) > 1:
        # 1. Create a ring to ensure all are connected horizontally
        for i in range(len(all_aggregation_nodes)):
            u = all_aggregation_nodes[i]
            v = all_aggregation_nodes[(i + 1) % len(all_aggregation_nodes)] # Next node (circular)
            
            link_pair = tuple(sorted((u, v)))
            if link_pair not in existing_horizontal_links:
                topology_json["link"].append(
                    {"s": u, "d": v, "BW": link_bw_aggregation, "PR": link_pr_aggregation}
                )
                existing_horizontal_links.add(link_pair)

        # 2. Add random cross-links for extra redundancy
        for agg_id in all_aggregation_nodes:
            if random.random() < 0.3: # 30% chance for an extra link
                neighbor = random.choice(all_aggregation_nodes)
                if neighbor != agg_id:
                    link_pair = tuple(sorted((agg_id, neighbor)))
                    if link_pair not in existing_horizontal_links:
                        topology_json["link"].append(
                            {"s": agg_id, "d": neighbor, "BW": link_bw_aggregation, "PR": link_pr_aggregation}
                        )
                        existing_horizontal_links.add(link_pair)

    # 4. Edge Layer (Home Routers + Devices)
    edge_node_global_idx = 0
    for _, agg_id in aggregation_node_ids:
        for edge_idx in range(edge_nodes_per_aggregation):
            edge_node_global_idx += 1
            app_id = edge_node_global_idx

            edge_node_id = next_id()
            edge_node_x = random_x()
            topology_json["entity"].append(
                {
                    "id": edge_node_id,
                    "model": f"Application-{app_id}-Router",
                    "mytag": "router",
                    "label": f"Application-{app_id}-Router",
                    "IPT": 0,
                    "RAM": 0,
                    "x": edge_node_x,
                    "y": edge_y,
                }
            )
            # Connect Home Router to Aggregation Node
            topology_json["link"].append(
                {"s": agg_id, "d": edge_node_id, "BW": link_bw_aggregation, "PR": link_pr_aggregation}
            )

            # Sensors
            for sensor_idx in range(sensors_per_edge_node):
                sensor_id = next_id()
                topology_json["entity"].append(
                    {
                        "id": sensor_id,
                        "model": f"Application-{app_id}-Sensor",
                        "label": f"Application-{app_id}-Sensor",
                        "x": edge_node_x + random.uniform(-2, 2),
                        "y": device_y,
                    }
                )
                topology_json["link"].append(
                    {"s": edge_node_id, "d": sensor_id, "BW": link_bw_edge, "PR": link_pr_edge}
                )

            # Actuators
            for actuator_idx in range(actuators_per_edge_node):
                actuator_id = next_id()
                topology_json["entity"].append(
                    {
                        "id": actuator_id,
                        "model": f"Application-{app_id}-Actuator",
                        "label": f"Application-{app_id}-Actuator",
                        "x": edge_node_x + random.uniform(-2, 2),
                        "y": device_y,
                    }
                )
                topology_json["link"].append(
                    {"s": edge_node_id, "d": actuator_id, "BW": link_bw_edge, "PR": link_pr_edge}
                )

    return topology_json

def create_application_structure(name: str) -> Application:
    # APLICATION
    app = Application(name)

    # (Sensor) --> (Service) --> (Actuator)
    app.set_modules([{f"{name}-Sensor":{"Type":Application.TYPE_SOURCE}},
                    {f"{name}-Service": {"RAM": 10, "Type": Application.TYPE_MODULE}},
                    {f"{name}-Actuator": {"Type": Application.TYPE_SINK}}
                    ])
    """
    Messages among MODULES (AppEdge in iFogSim)
    """
    msg_sensor_to_service = Message("Sensor calling Service", f"{name}-Sensor", f"{name}-Service", instructions=20*10**6, bytes=1000)
    msg_service_to_actuator = Message("Service calling Actuator", f"{name}-Service", f"{name}-Actuator", instructions=30*10**6, bytes=500)

    """
    Defining which messages will be dynamically generated # the generation is controlled by Population algorithm
    """
    app.add_source_messages(msg_sensor_to_service)

    """
    MODULES/SERVICES: Definition of Generators and Consumers (AppEdges and TupleMappings in iFogSim)
    """
    # MODULE SERVICES
    app.add_service_module(f"{name}-Service", msg_sensor_to_service, msg_service_to_actuator, fractional_selectivity, threshold=1.0)

    return app

if __name__ == "__main__":
    import logging.config
    import os

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))
    
    # Define the log file path
    log_file_path = os.path.join(script_dir, 'execution.log')

    logging.config.fileConfig(os.path.join(script_dir, "logging.ini"), defaults={'logfilename': log_file_path})

    start_time = time.time()

    results_path = Path("resultados/")
    results_path.mkdir(parents=True, exist_ok=True)
    results_path = str(results_path) + "/"

    # The topology is being created using the function create_fixed_topology()
    topology = Topology()
    
    # Capture the topology data to access labels
    num_fog_nodes = 4
    topology_json = create_random_topology(
            num_fog_nodes=num_fog_nodes,
            random_seed=42,
        )
    topology.load(topology_json)

    # Explicitly add all attributes to the NetworkX graph so they are saved in the GEXF
    for entity in topology_json["entity"]:
        for key, value in entity.items():
            if key != "id":
                topology.G.nodes[entity["id"]][key] = value

    # Explicitly add all attributes to the edges as well
    for link in topology_json["link"]:
        s = link["s"]
        d = link["d"]
        for key, value in link.items():
            if key not in ["s", "d"]:
                topology.G.edges[s, d][key] = value

    # Sanitize attributes for GEXF (convert tuples to strings)
    for node in topology.G.nodes:
        for key, value in list(topology.G.nodes[node].items()):
            if isinstance(value, tuple):
                topology.G.nodes[node][key] = str(value)

    for u, v in topology.G.edges:
        for key, value in list(topology.G.edges[u, v].items()):
            if isinstance(value, tuple):
                topology.G.edges[u, v][key] = str(value)
    networkx.write_gexf(
        topology.G, results_path + f"graph_{num_fog_nodes}_fog.gexf"
    )

    distribution = deterministic_distribution(name="Deterministic", time=100)

    # Their "selector" is actually the shortest way, there is not type of orchestration algorithm.
    # This implementation is already created in selector.class,called: First_ShortestPath
    selection_policy = MinimunPath()

    stop_time = 10000

    simulator = Sim(topology, default_results_path=results_path + "sim_trace")
    
    # Identify all applications from the topology entities
    app_ids = set()
    for entity in topology_json["entity"]:
        if "model" in entity and entity["model"].startswith("Application-"):
            # Format: Application-{id}-DeviceType
            parts = entity["model"].split("-")
            if len(parts) >= 2 and parts[1].isdigit():
                app_ids.add(int(parts[1]))
    
    sorted_app_ids = sorted(list(app_ids))
    print(f"Deploying {len(sorted_app_ids)} applications...")

    # Define the placement strategy here
    # Options: 'latency', 'hops', 'cost', 'ipt'
    PLACEMENT_STRATEGY = 'latency'

    for app_id in sorted_app_ids:
        app_name = f"Application-{app_id}"
        app = create_application_structure(app_name)
        
        # Placement
        # We use a unique placement policy name per application to ensure they are independent
        # Activation distribution for reallocation: every 1000 time units
        reallocation_dist = deterministic_distribution(name="Reallocation", time=1000)
        placement_policy = CloudPlacement(
            f"CloudPlacement-{app_id}", 
            activation_dist=reallocation_dist,
            strategy=PLACEMENT_STRATEGY
        )
        placement_policy.scaleService({f"{app_name}-Service": 1})
        
        # Population
        population = Statical(f"Statical-{app_id}")
        population.set_src_control({
            "model": f"{app_name}-Sensor", 
            "number": 1, 
            "message": app.get_message("Sensor calling Service"), 
            "distribution": distribution,
            "param": {"time_shift": 100}
        })
        population.set_sink_control({
            "model": f"{app_name}-Actuator", 
            "number": 1, 
            "module": app.get_sink_modules()
        })
        
        simulator.deploy_app2(app, placement_policy, population, selection_policy)

    simulator.run(stop_time)

    print("\n--- %s seconds ---" % (time.time() - start_time))
