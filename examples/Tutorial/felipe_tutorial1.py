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
    TOPOLOGY CREATION

    Some attributes of fog entities (nodes) are approximate
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

def createRandomTopology(num_fog_nodes=3, num_routers=5, num_sensors_per_router=2, 
                        num_actuators_per_router=1, fog_ipt=1000*10**6, fog_ram=8000,
                        fog_cost=2, fog_watt=10.0, link_bw_fog=10, link_pr_fog=10,
                        link_bw_router=5, link_pr_router=5, link_bw_device=1, 
                        link_pr_device=1, random_seed=None, city_width=100, city_height=100):
    """
    Create a city-like network topology simulating urban infrastructure.
    
    Topology simulates:
    - Fog nodes: Data centers/edge computing facilities distributed across the city
    - Routers: Neighborhood network hubs (one per residential area/block)
    - Sensors/Actuators: Smart home IoT devices (multiple per neighborhood)
    
    Network structure:
    - Fog nodes form a backbone mesh (connected to nearest neighbors)
    - Routers connect to nearest fog node (geographic proximity)
    - Nearby routers interconnect for redundancy (street-level mesh)
    - Homes (sensors/actuators) connect to their neighborhood router
    
    Parameters:
    - num_fog_nodes: Number of fog data centers in the city
    - num_routers: Number of neighborhood routers (residential areas)
    - num_sensors_per_router: Number of smart home sensors per neighborhood
    - num_actuators_per_router: Number of smart home actuators per neighborhood
    - fog_ipt: Instructions per time for fog nodes
    - fog_ram: RAM for fog nodes
    - fog_cost: Cost for fog nodes
    - fog_watt: Wattage for fog nodes
    - link_bw_fog: Bandwidth for backbone links between fog nodes
    - link_pr_fog: Propagation delay for backbone links
    - link_bw_router: Bandwidth for links between routers and fog/other routers
    - link_pr_router: Propagation delay for router links
    - link_bw_device: Bandwidth for home device connections
    - link_pr_device: Propagation delay for home device connections
    - random_seed: Seed for random number generator (for reproducibility)
    - city_width: Width of the city grid (coordinate space)
    - city_height: Height of the city grid (coordinate space)
    
    Returns:
    - topology_object: Dictionary containing the topology structure
    """
    
    if random_seed is not None:
        random.seed(random_seed)
    
    topology_object = {}
    topology_object["entity"] = []
    topology_object["link"] = []
    
    node_id = 0
    
    # Create fog nodes distributed across the city (like data centers at strategic locations)
    fog_ids = []
    fog_positions = []  # Store (x, y) coordinates for distance calculations
    
    for i in range(num_fog_nodes):
        # Distribute fog nodes across the city grid
        pos_x = random.uniform(0, city_width)
        pos_y = random.uniform(0, city_height)
        fog_positions.append((pos_x, pos_y))
        
        fog_dev = {
            "id": node_id,
            "model": f"fog-device-{i}",
            "mytag": "fog",
            "IPT": fog_ipt,
            "RAM": fog_ram,
            "COST": fog_cost,
            "WATT": fog_watt,
            "x": pos_x,
            "y": pos_y,
        }
        topology_object["entity"].append(fog_dev)
        fog_ids.append(node_id)
        node_id += 1
    
    # Create city backbone network: connect each fog node to its 2-3 nearest neighbors
    for i, fog_id in enumerate(fog_ids):
        distances = []
        for j, other_fog_id in enumerate(fog_ids):
            if i != j:
                # Calculate Euclidean distance
                dist = ((fog_positions[i][0] - fog_positions[j][0])**2 + 
                       (fog_positions[i][1] - fog_positions[j][1])**2)**0.5
                distances.append((dist, other_fog_id))
        
        # Connect to 2-3 nearest fog nodes for redundant backbone
        distances.sort()
        num_connections = min(random.randint(2, 3), len(distances))
        for k in range(num_connections):
            if fog_id < distances[k][1]:  # Avoid duplicate bidirectional links
                link = {"s": fog_id, "d": distances[k][1], "BW": link_bw_fog, "PR": link_pr_fog}
                topology_object["link"].append(link)
    
    # Create neighborhood routers and home devices (sensors/actuators)
    router_ids = []
    router_positions = []
    
    for i in range(num_routers):
        # Distribute routers across the city (representing neighborhoods)
        pos_x = random.uniform(0, city_width)
        pos_y = random.uniform(0, city_height)
        router_positions.append((pos_x, pos_y))
        
        router_dev = {
            "id": node_id,
            "model": f"router-{i}",
            "mytag": "router",
            "IPT": 0,
            "RAM": 0,
            "x": pos_x,
            "y": pos_y,
        }
        topology_object["entity"].append(router_dev)
        router_id = node_id
        router_ids.append(router_id)
        node_id += 1
        
        # Connect router to the geographically nearest fog node
        min_dist = float('inf')
        nearest_fog = fog_ids[0]
        for j, fog_id in enumerate(fog_ids):
            dist = ((pos_x - fog_positions[j][0])**2 + 
                   (pos_y - fog_positions[j][1])**2)**0.5
            if dist < min_dist:
                min_dist = dist
                nearest_fog = fog_id
        
        link = {"s": nearest_fog, "d": router_id, "BW": link_bw_router, "PR": link_pr_router}
        topology_object["link"].append(link)
        
        # Create smart home sensors in this neighborhood
        for j in range(num_sensors_per_router):
            sensor_dev = {
                "id": node_id,
                "model": sensorNodeName,
            }
            topology_object["entity"].append(sensor_dev)
            
            # Connect sensor to neighborhood router
            link = {"s": router_id, "d": node_id, "BW": link_bw_device, "PR": link_pr_device}
            topology_object["link"].append(link)
            
            node_id += 1
        
        # Create smart home actuators in this neighborhood
        for j in range(num_actuators_per_router):
            actuator_dev = {
                "id": node_id,
                "model": actuatorNodeName,
            }
            topology_object["entity"].append(actuator_dev)
            
            # Connect actuator to neighborhood router
            link = {"s": router_id, "d": node_id, "BW": link_bw_device, "PR": link_pr_device}
            topology_object["link"].append(link)
            
            node_id += 1
    
    # Create street-level mesh: connect nearby routers for redundancy
    # Routers within ~30% of city width connect to 1-2 nearest neighbors
    distance_threshold = city_width * 0.3
    
    for i, router_id in enumerate(router_ids):
        distances = []
        for j, other_router_id in enumerate(router_ids):
            if i != j:
                dist = ((router_positions[i][0] - router_positions[j][0])**2 + 
                       (router_positions[i][1] - router_positions[j][1])**2)**0.5
                if dist <= distance_threshold:
                    distances.append((dist, other_router_id))
        
        # Connect to 1-2 nearest routers within threshold
        distances.sort()
        num_connections = min(random.randint(1, 2), len(distances))
        for k in range(num_connections):
            if router_id < distances[k][1]:  # Avoid duplicate links
                link = {"s": router_id, "d": distances[k][1], "BW": link_bw_router, "PR": link_pr_router}
                topology_object["link"].append(link)
    
    return topology_object

def createApplication():
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
    applicationObject.add_service_module(service1Name, messageFromSensorToService, messageFromServiceToConsumer, fractional_selectivity(threshold=1.0))

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
    # topology.load(createTopology())
    topology.load(createRandomTopology(num_fog_nodes=30, num_routers=500, num_sensors_per_router=2, 
                        num_actuators_per_router=1, fog_ipt=1000*10**6, fog_ram=8000,
                        fog_cost=2, fog_watt=10.0, link_bw_fog=10, link_pr_fog=10,
                        link_bw_router=5, link_pr_router=5, link_bw_device=1, 
                        link_pr_device=1, random_seed=42))
    
    networkx.write_gexf(
        topology.G, results_path + "graph_felipe_tutorial1.gexf"
    )

    # The application is being created using the function createApplication()
    application = createApplication()

    # Initial placement if "mytag": "cloud"
    placementAlgorithm = CloudPlacement("tagEqualsToCloud")
    placementAlgorithm.scaleService({"ServiceA": 1})

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

    print("\n--- %s seconds ---" % (time.time() - start_time))
