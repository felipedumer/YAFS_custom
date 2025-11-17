import time
import networkx

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
    topology.load(createTopology())
    
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
