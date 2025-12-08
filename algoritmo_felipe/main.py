import time
import networkx
import random
import json
import csv

from pathlib import Path

from yafs.core import Sim
from yafs.topology import Topology
from yafs.application import Application, Message, fractional_selectivity
from yafs.population import Statical
from yafs.distribution import deterministic_distribution

from placement_algorithm import CloudPlacement
from selection_algorithm import MinimunPath

class RandomMessage(Message):
    def __init__(self, name, src, dst, instructions=0, bytes=0, broadcasting=False):
        super(RandomMessage, self).__init__(name, src, dst, instructions, bytes, broadcasting)
        self.inst_range = instructions if isinstance(instructions, (list, tuple)) else (instructions, instructions)
        self.bytes_range = bytes if isinstance(bytes, (list, tuple)) else (bytes, bytes)

    def __copy__(self):
        new_msg = RandomMessage(self.name, self.src, self.dst, self.inst_range, self.bytes_range, self.broadcasting)
        new_msg.inst = random.randint(self.inst_range[0], self.inst_range[1])
        new_msg.bytes = random.randint(self.bytes_range[0], self.bytes_range[1])
        return new_msg

def create_application_structure(name: str) -> Application:
    # APLICATION
    app = Application(name)

    # (Sensor) --> (Service) --> (Sensor)
    # Sensor is both Source (generator) and Module (consumer of response)
    app.set_modules([
        {f"{name}-Sensor": {"Type": Application.TYPE_MODULE}},
        {f"{name}-Service": {"RAM": random.randint(50, 100), "Type": Application.TYPE_MODULE}}
    ])

    """
    Messages among MODULES
    """
    # M_Req: Sensor -> Service. High instructions (Service workload), Medium size.
    msg_req = RandomMessage("M_Req", f"{name}-Sensor", f"{name}-Service", instructions=(200*10**6, 500*10**6), bytes=(1000, 2000))
    
    # M_Resp: Service -> Sensor. Low instructions (Sensor logging), Medium size.
    msg_resp = RandomMessage("M_Resp", f"{name}-Service", f"{name}-Sensor", instructions=(1*10**6, 2*10**6), bytes=(1000, 2000))

    """
    Defining which messages will be dynamically generated
    """
    app.add_source_messages(msg_req)

    """
    MODULES/SERVICES
    """
    # Sensor -> Service (Request) -> Service -> Sensor (Response)
    app.add_service_module(f"{name}-Service", msg_req, msg_resp, fractional_selectivity, threshold=1.0)
    
    # Sensor receives Response (Sink behavior)
    app.add_service_module(f"{name}-Sensor", msg_resp)

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

    distribution = deterministic_distribution(name="Deterministic", time=100)

    # SELECTION POLICY
    # The Selection Policy determines how messages are routed between service modules.
    # When a module (e.g., Sensor) sends a message to another module (e.g., Service),
    # this policy decides which specific instance of the destination module receives it.
    # 'MinimunPath' routes the message to the nearest instance (shortest network path).
    selection_policy = MinimunPath()

    stop_time = 1000

    # Load topology from file

    file_to_load = "fog3-middle37-end942"
    topology_path = os.path.join(script_dir, f"topologia/{file_to_load}.json")
    logging.info(f"Loading topology from {topology_path}...")
    with open(topology_path, "r") as f:
        topology_json = json.load(f)
    
    topology = Topology()
    topology.load_all_node_attr(topology_json)

    # Calculate num_fog_nodes from topology
    num_fog_nodes = sum(1 for entity in topology_json["entity"] if entity["model"] == "fog")

    # Identify all applications from the topology entities
    app_ids = set()
    for entity in topology_json["entity"]:
        if "model" in entity and entity["model"].startswith("Application-"):
            # Format: Application-{id}-DeviceType
            parts = entity["model"].split("-")
            if len(parts) >= 2 and parts[1].isdigit():
                app_ids.add(int(parts[1]))
    
    sorted_app_ids = sorted(list(app_ids))
    logging.info(f"Deploying {len(sorted_app_ids)} applications...")

    # Define the placement strategy here
    # Options: 'latency', 'hops', 'cost', 'ipt', 'custom_proposed_by_felipe', 'roundRobin'
    PLACEMENT_STRATEGY = 'custom_proposed_by_felipe'

    # Pattern: {numberOfFogNodes}-{placementStrategy}
    sim_trace_path = results_path + f"{file_to_load}-{PLACEMENT_STRATEGY}-sim_trace"
    simulator = Sim(topology, default_results_path=sim_trace_path)

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
        placement_policy.scaleService({f"{app_name}-Service": 1, f"{app_name}-Sensor": 1})
        
        # Population
        population = Statical(f"Statical-{app_id}")
        population.set_src_control({
            "model": f"{app_name}-Sensor", 
            "number": 1, 
            "message": app.get_message("M_Req"), 
            "distribution": distribution,
            "param": {"time_shift": 100}
        })
        
        simulator.deploy_app2(app, placement_policy, population, selection_policy)

    simulator.run(stop_time)

    # Logic to save unprocessed messages (Queue Buildup)
    unprocessed_file = results_path + "unprocessed_messages.csv"
    logging.info(f"Saving unprocessed messages to {unprocessed_file}...")
    
    # DEBUG: Print queue sizes
    logging.info(f"Network Queue Size: {len(simulator.network_ctrl_pipe.items)}")
    total_consumer_items = sum(len(p.items) for p in simulator.consumer_pipes.values())
    logging.info(f"Total Consumer Queues Size: {total_consumer_items}")
    logging.info(f"In-Transit/Processing Messages: {len(simulator.processing_messages)}")

    with open(unprocessed_file, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(["QueueType", "App", "Message", "Src", "Dst", "Timestamp", "Path", "CurrentNode", "Until"])
        
        # 1. Network Queue (Messages in transit)
        # simulator.network_ctrl_pipe is a simpy.Store
        if hasattr(simulator.network_ctrl_pipe, 'items'):
            for msg in simulator.network_ctrl_pipe.items:
                writer.writerow(["Network_Queue", msg.app_name, msg.name, msg.src, msg.dst, msg.timestamp, msg.path, msg.dst_int, "N/A"])
        
        # 2. Consumer Queues (Messages waiting for processing at nodes)
        # simulator.consumer_pipes is a dict of simpy.Store
        for pipe_id, pipe in simulator.consumer_pipes.items():
            if hasattr(pipe, 'items'):
                for msg in pipe.items:
                    writer.writerow(["Processing_Queue", msg.app_name, msg.name, msg.src, msg.dst, msg.timestamp, msg.path, msg.dst_int, "N/A"])

        # 3. Active Processing/Transit (Messages in yield)
        for entry in simulator.processing_messages:
            msg = entry["msg"]
            writer.writerow([entry["type"], msg.app_name, msg.name, msg.src, msg.dst, msg.timestamp, msg.path, msg.dst_int, entry.get("until", "N/A")])


    logging.info("\n--- %s seconds ---" % (time.time() - start_time))
