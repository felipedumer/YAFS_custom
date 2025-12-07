import time
import networkx
import random

from pathlib import Path

from yafs.core import Sim
from yafs.topology import Topology
from yafs.application import Application, Message, fractional_selectivity
from yafs.population import Statical
from yafs.distribution import deterministic_distribution

from simplePlacement import CloudPlacement
from simpleSelection import MinimunPath

actuatorNodeName = "actuator-device"
sensorNodeName = "sensor-device"

def createTopology():
    """
    Creates a simple fixed topology for testing purposes.

    Returns:
        dict: A dictionary representing the topology with 'entity' and 'link' lists.
    """

    ## REQUIRED FIELDS
    topology_object = {}
    topology_object["entity"] = []
    topology_object["link"] = []

    cloud_dev = {
        "id": 0,
        "model": "cloud",
        "mytag": "cloud",
        "IPT": 5000 * 10**6,
        "RAM": 40000,
        "COST": 3,
        "WATT": 20.0,
    }
    fog_device = {
        "id": 1,
        "model": "fog-device",
        "mytag": "fog",
        "IPT": 1000 * 10**6,
        "RAM": 8000,
        "COST": 2,
        "WATT": 10.0,
    }
    router_device = {
        "id": 2,
        "model": "router",
        "mytag": "router",
        "IPT": 0,
        "RAM": 0,
    }
    sensor_dev = {
        "id": 3,
        "model": sensorNodeName,
    }
    actuator_dev = {
        "id": 4,
        "model": actuatorNodeName,
    }

    link_0_to_1 = {"s": 0, "d": 1, "BW": 10, "PR": 10}
    link_1_to_2 = {"s": 1, "d": 2, "BW": 5, "PR": 5}
    link_2_to_3 = {"s": 2, "d": 3, "BW": 1, "PR": 10}
    link_2_to_4 = {"s": 2, "d": 4, "BW": 1, "PR": 1}

    topology_object["entity"].append(cloud_dev)
    topology_object["entity"].append(sensor_dev)
    topology_object["entity"].append(actuator_dev)
    topology_object["entity"].append(router_device)
    topology_object["entity"].append(fog_device)

    topology_object["link"].append(link_0_to_1)
    topology_object["link"].append(link_1_to_2)
    topology_object["link"].append(link_2_to_3)
    topology_object["link"].append(link_2_to_4)
    return topology_object

def createRandomTopology(
    num_fog_nodes=2,
    random_seed=None,
    cloud_ipt=50000 * 10**6,
    cloud_ram=400000,
    cloud_cost=10,
    cloud_watt=100.0,
    fog_ipt=1000 * 10**6,
    fog_ram=8000,
    fog_cost=2,
    fog_watt=10.0,
    link_bw_cloud=100,
    link_pr_cloud=20,
    link_bw_fog=15,
    link_pr_fog=8,
    link_bw_middle=8,
    link_pr_middle=5,
    link_bw_router=2,
    link_pr_router=1,
    city_width=100,
    layer_gap=40,
):
    """
    Create a strict 4-layer topology (Cloud -> Fog -> Middle -> End).
    The number of nodes in lower layers is automatically generated.

    Layer 0 (Cloud): Single cloud node (high capacity).
    Layer 1 (Fog): Computational nodes connected to the cloud.
    Layer 2 (Middle): Communication-only nodes (routers/switches) connected to Fog nodes.
    Layer 3 (End): Home routers connected to Middle nodes, with sensors/actuators attached.

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
        link_bw_fog (float): Bandwidth for links from Fog to Middle.
        link_pr_fog (float): Propagation delay for links from Fog to Middle.
        link_bw_middle (float): Bandwidth for links from Middle to End routers.
        link_pr_middle (float): Propagation delay for links from Middle to End routers.
        link_bw_router (float): Bandwidth for links from End routers to devices.
        link_pr_router (float): Propagation delay for links from End routers to devices.
        city_width (float): Width of the simulation area (for x-coordinates).
        layer_gap (float): Vertical distance between layers (for y-coordinates).

    Returns:
        dict: A dictionary representing the topology with 'entity' and 'link' lists.
    """
    if random_seed is not None:
        random.seed(random_seed)

    # Automatically determine topology structure
    middle_per_fog = random.randint(2, 3)
    routers_per_middle = random.randint(2, 3)
    sensors_per_router = random.randint(1, 2)
    actuators_per_router = 1

    topology_object = {"entity": [], "link": []}
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
    middle_y = layer_gap
    router_y = 0
    device_y = -layer_gap

    # 1. Cloud Layer (Single Node)
    cloud_id = next_id()
    topology_object["entity"].append(
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
        topology_object["entity"].append(
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
        topology_object["link"].append(
            {"s": cloud_id, "d": fog_id, "BW": link_bw_cloud, "PR": link_pr_cloud}
        )
        fog_ids.append(fog_id)

    # 3. Middle Layer (Communication Only)
    middle_ids = []
    for fog_idx, fog_id in enumerate(fog_ids):
        for mid_idx in range(middle_per_fog):
            mid_id = next_id()
            topology_object["entity"].append(
                {
                    "id": mid_id,
                    "model": f"middle",
                    "mytag": "router", # Tagged as router since it's comm-only
                    "label": f"Middle-{fog_idx}-{mid_idx}",
                    "IPT": 0, # No computational power
                    "RAM": 0,
                    "x": random_x(),
                    "y": middle_y,
                }
            )
            # Connect Middle to Fog (Primary Link)
            topology_object["link"].append(
                {"s": fog_id, "d": mid_id, "BW": link_bw_fog, "PR": link_pr_fog}
            )
            
            connected_fogs = {fog_id}

            # Redundancy: Connect to other Fog nodes (Mesh-like)
            # Simulating a real-life scenario where intermediary nodes have backup connections
            if num_fog_nodes > 1:
                # Connect to 1 extra random fog node for redundancy
                other_fogs = [f for f in fog_ids if f not in connected_fogs]
                if other_fogs:
                    extra_fog = random.choice(other_fogs)
                    topology_object["link"].append(
                        {"s": extra_fog, "d": mid_id, "BW": link_bw_fog, "PR": link_pr_fog}
                    )
                    connected_fogs.add(extra_fog)

            middle_ids.append((fog_id, mid_id))

    # Redundancy: Horizontal connections between Middle nodes
    # Connect each middle node to at least one other middle node (Ring-like + Random)
    all_middle_nodes = [mid_id for _, mid_id in middle_ids]
    existing_horizontal_links = set()
    
    if len(all_middle_nodes) > 1:
        # 1. Create a ring to ensure all are connected horizontally
        for i in range(len(all_middle_nodes)):
            u = all_middle_nodes[i]
            v = all_middle_nodes[(i + 1) % len(all_middle_nodes)] # Next node (circular)
            
            link_pair = tuple(sorted((u, v)))
            if link_pair not in existing_horizontal_links:
                topology_object["link"].append(
                    {"s": u, "d": v, "BW": link_bw_middle, "PR": link_pr_middle}
                )
                existing_horizontal_links.add(link_pair)

        # 2. Add random cross-links for extra redundancy
        for mid_id in all_middle_nodes:
            if random.random() < 0.3: # 30% chance for an extra link
                neighbor = random.choice(all_middle_nodes)
                if neighbor != mid_id:
                    link_pair = tuple(sorted((mid_id, neighbor)))
                    if link_pair not in existing_horizontal_links:
                        topology_object["link"].append(
                            {"s": mid_id, "d": neighbor, "BW": link_bw_middle, "PR": link_pr_middle}
                        )
                        existing_horizontal_links.add(link_pair)

    # 4. End Layer (Home Routers + Devices)
    for _, mid_id in middle_ids:
        for router_idx in range(routers_per_middle):
            router_id = next_id()
            router_x = random_x()
            topology_object["entity"].append(
                {
                    "id": router_id,
                    "model": f"home-router",
                    "mytag": "router",
                    "label": f"Router-{mid_id}-{router_idx}",
                    "IPT": 0,
                    "RAM": 0,
                    "x": router_x,
                    "y": router_y,
                }
            )
            # Connect Home Router to Middle Node
            topology_object["link"].append(
                {"s": mid_id, "d": router_id, "BW": link_bw_middle, "PR": link_pr_middle}
            )

            # Sensors
            for sensor_idx in range(sensors_per_router):
                sensor_id = next_id()
                topology_object["entity"].append(
                    {
                        "id": sensor_id,
                        "model": sensorNodeName,
                        "label": f"Sensor-{sensor_id}",
                        "x": router_x + random.uniform(-2, 2),
                        "y": device_y,
                    }
                )
                topology_object["link"].append(
                    {"s": router_id, "d": sensor_id, "BW": link_bw_router, "PR": link_pr_router}
                )

            # Actuators
            for actuator_idx in range(actuators_per_router):
                actuator_id = next_id()
                topology_object["entity"].append(
                    {
                        "id": actuator_id,
                        "model": actuatorNodeName,
                        "label": f"Actuator-{actuator_id}",
                        "x": router_x + random.uniform(-2, 2),
                        "y": device_y,
                    }
                )
                topology_object["link"].append(
                    {"s": router_id, "d": actuator_id, "BW": link_bw_router, "PR": link_pr_router}
                )

    return topology_object

def createApplication():
    """
    Creates the application definition with modules and messages.

    Returns:
        Application: The application object containing modules, messages, and services.
    """
    applicationObject = Application(name="FelipeCase")

    sensor1Name = "SensorCollectingRawData"
    service1Name = "ServiceProcessingTheRequest"
    sink1Name = "SinkMessageConsumer"

    # Creating modules
    applicationObject.set_modules(
        [
            {sensor1Name: {"Type": Application.TYPE_SOURCE}},
            {service1Name: {"RAM": 10, "Type": Application.TYPE_MODULE}},
            {sink1Name: {"Type": Application.TYPE_SINK}},
        ]
    )

    # Creating messages
    messageFromSensorToService = Message("Hey This is Sensor Calling Service!", sensor1Name, service1Name, instructions=20 * 10**6, bytes=1000)
    messageFromServiceToConsumer = Message("This is Service sending message to the Consumer!", service1Name, sink1Name, instructions=20 * 10**6, bytes=1000)
    anotherMessageFromSensorToSink = Message("Sensor sending message directly to sink !", sensor1Name, sink1Name, instructions=30 * 10**6, bytes=500)

    # Source messages are controlled by popution algorithm
    applicationObject.add_source_messages(messageFromSensorToService)
    applicationObject.add_source_messages(anotherMessageFromSensorToSink)

    # Modules redirect the messages ??? but it can also be a sink
    applicationObject.add_service_module(service1Name, messageFromSensorToService, messageFromServiceToConsumer, fractional_selectivity, threshold=1.0)

    return applicationObject

if __name__ == "__main__":
    import logging.config
    import os

    path = os.getcwd()

    logging.config.fileConfig(os.getcwd() + "/logging.ini")

    start_time = time.time()

    results_path = Path("resultados/")
    results_path.mkdir(parents=True, exist_ok=True)
    results_path = str(results_path) + "/"

    # The topology is being created using the function createTopology()
    topology = Topology()
    
    # Capture the topology data to access labels
    topo_data = createRandomTopology(
            num_fog_nodes=4,
            random_seed=42,
        )
    topology.load(topo_data)

    # Explicitly add all attributes to the NetworkX graph so they are saved in the GEXF
    for entity in topo_data["entity"]:
        for key, value in entity.items():
            if key != "id":
                topology.G.nodes[entity["id"]][key] = value

    # Explicitly add all attributes to the edges as well
    for link in topo_data["link"]:
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
        topology.G, results_path + "graph_felipe_tutorial1.gexf"
    )

    # The application is being created using the function createApplication()
    application = createApplication()

    # Initial placement if "mytag": "cloud"
    placementAlgorithm = CloudPlacement("tagEqualsToCloud")
    placementAlgorithm.scaleService({"ServiceProcessingTheRequest": 1})

    # Population Algorithm
    populationAlgorithm = Statical("Statical")
    # For each type of sink modules we set a deployment on some type of devices
    # A control sink consists on:
    #  args:
    #     model (str): identifies the device or devices where the sink is linked
    #     number (int): quantity of sinks linked in each device
    #     module (str): identifies the module from the app who receives the messages
    populationAlgorithm.set_sink_control(
        {"model": actuatorNodeName, "number": 1, "module": application.get_sink_modules()}
    )

    # In addition, a source includes a distribution function, This basically says send message every 50 simulation times
    distributionObject = deterministic_distribution(name="Deterministic", time=50)

    populationAlgorithm.set_src_control(
        {
            "model": sensorNodeName,
            "number": 1,
            "message": application.get_message("Hey This is Sensor Calling Service!"),
            "distribution": distributionObject,
        }
    )

    # Their "selector" is actually the shortest way, there is not type of orchestration algorithm.
    # This implementation is already created in selector.class,called: First_ShortestPath
    selectorPathAlgorithm = MinimunPath()

    stop_time = 1000

    simulationObject = Sim(topology, default_results_path=results_path + "sim_trace")
    simulationObject.deploy_app2(application, placementAlgorithm, populationAlgorithm, selectorPathAlgorithm)

    simulationObject.run(stop_time)

    print("\n--- %s seconds ---" % (time.time() - start_time))
