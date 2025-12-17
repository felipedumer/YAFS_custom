import time
import networkx
import random
import json
import csv
import logging

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
        super(RandomMessage, self).__init__(
            name, src, dst, instructions, bytes, broadcasting
        )
        self.inst_range = (
            instructions
            if isinstance(instructions, (list, tuple))
            else (instructions, instructions)
        )
        self.bytes_range = bytes if isinstance(bytes, (list, tuple)) else (bytes, bytes)

    def __copy__(self):
        new_msg = RandomMessage(
            self.name,
            self.src,
            self.dst,
            self.inst_range,
            self.bytes_range,
            self.broadcasting,
        )
        new_msg.inst = random.randint(self.inst_range[0], self.inst_range[1])
        new_msg.bytes = random.randint(self.bytes_range[0], self.bytes_range[1])

        # Copy internal attributes from the parent Message class
        new_msg.timestamp = self.timestamp
        new_msg.id = self.id
        new_msg.original_DES_src = self.original_DES_src

        return new_msg


def create_application_structure(name: str) -> Application:
    # APLICATION
    app = Application(name)

    # (Sensor) --> (Service) --> (Sensor)
    # Sensor is both Source (generator) and Module (consumer of response)
    app.set_modules(
        [
            {f"{name}-Sensor": {"Type": Application.TYPE_MODULE}},
            {
                f"{name}-Service": {
                    "RAM": random.randint(50, 100),
                    "Type": Application.TYPE_MODULE,
                }
            },
        ]
    )

    """
    Messages among MODULES
    """
    # M_Req: Sensor -> Service. High instructions (Service workload), Medium size.
    msg_req = RandomMessage(
        "M_Req",
        f"{name}-Sensor",
        f"{name}-Service",
        instructions=(200 * 10**6, 500 * 10**6),
        bytes=(1000, 2000),
    )

    # M_Resp: Service -> Sensor. Low instructions (Sensor logging), Medium size.
    msg_resp = RandomMessage(
        "M_Resp",
        f"{name}-Service",
        f"{name}-Sensor",
        instructions=(1 * 10**6, 2 * 10**6),
        bytes=(1000, 2000),
    )

    """
    Defining which messages will be dynamically generated
    """
    app.add_source_messages(msg_req)

    """
    MODULES/SERVICES
    """
    # Sensor -> Service (Request) -> Service -> Sensor (Response)
    app.add_service_module(
        f"{name}-Service", msg_req, msg_resp, fractional_selectivity, threshold=1.0
    )

    # Sensor receives Response (Sink behavior)
    app.add_service_module(f"{name}-Sensor", msg_resp)

    return app


def register_application(
    simulator: Sim,
    app_id: int,
    selection_policy: MinimunPath,
    source_period: int,
    placement_strategy: str,
    reallocation_period: int,
    allocate_now: bool = False,
) -> dict:
    app_name = f"Application-{app_id}"
    app = create_application_structure(app_name)

    # Create per-app distributions so later deployments are not coupled through shared state
    reallocation_dist = deterministic_distribution(
        name=f"Reallocation-{app_id}", time=reallocation_period
    )
    src_distribution = deterministic_distribution(
        name=f"Deterministic-{app_id}", time=source_period
    )

    placement_policy = CloudPlacement(
        f"CloudPlacement-{app_id}",
        activation_dist=reallocation_dist,
        strategy=placement_strategy,
    )
    placement_policy.scaleService({f"{app_name}-Service": 1, f"{app_name}-Sensor": 1})

    population = Statical(f"Statical-{app_id}")
    population.set_src_control(
        {
            "model": f"{app_name}-Sensor",
            "number": 1,
            "message": app.get_message("M_Req"),
            "distribution": src_distribution,
            "param": {"time_shift": 100},
        }
    )

    simulator.deploy_app2(app, placement_policy, population, selection_policy)
    logging.debug(
        "Registered app %s with placement %s, population %s | src_period=%s realloc_period=%s",
        app_name,
        placement_policy.name,
        population.name,
        source_period,
        reallocation_period,
    )

    # When apps are injected mid-simulation, we need to do the initial allocation manually
    if allocate_now:
        logging.debug("Triggering immediate allocations for %s", app_name)
        population.initial_allocation(simulator, app_name)
        placement_policy.initial_allocation(simulator, app_name)

    return {
        "app_name": app_name,
        "placement_name": placement_policy.name,
        "population_name": population.name,
    }


def _stop_policy_process(simulator: Sim, policy_name: str, registry: dict):
    policy_entry = registry.get(policy_name)
    if policy_entry and not policy_entry["apps"]:
        process_id = simulator.des_control_process.get(policy_name)
        if process_id is not None:
            simulator.des_process_running[process_id] = False
            simulator.des_control_process.pop(policy_name, None)
        registry.pop(policy_name, None)


def destroy_application(simulator: Sim, app_ctx: dict):
    app_name = app_ctx["app_name"]
    placement_name = app_ctx["placement_name"]
    population_name = app_ctx["population_name"]

    # Stop and remove sources
    sources_to_remove = [
        des
        for des, meta in list(simulator.alloc_source.items())
        if meta.get("app") == app_name
    ]
    logging.debug("Destroy %s: removing %d sources", app_name, len(sources_to_remove))
    for des in sources_to_remove:
        node_id = simulator.alloc_DES.get(des)
        node_label = (
            simulator.topology.get_node(node_id).get("label", node_id)
            if node_id is not None and simulator.topology.G.has_node(node_id)
            else "?"
        )
        logging.info(
            "Destroy %s: stopping source DES=%s at node %s", app_name, des, node_label
        )
        simulator.undeploy_source(des)

    # Stop and remove deployed modules (service + sensor consumers)
    if app_name in simulator.alloc_module:
        for module, des_list in list(simulator.alloc_module[app_name].items()):
            logging.debug(
                "Destroy %s: removing %d deployments of module %s",
                app_name,
                len(des_list),
                module,
            )
            for des in list(des_list):
                node_id = simulator.alloc_DES.get(des)
                node_label = (
                    simulator.topology.get_node(node_id).get("label", node_id)
                    if node_id is not None and simulator.topology.G.has_node(node_id)
                    else "?"
                )
                logging.info(
                    "Destroy %s: undeploying module %s DES=%s at node %s",
                    app_name,
                    module,
                    des,
                    node_label,
                )
                simulator.undeploy_module(app_name, module, des)
        simulator.alloc_module.pop(app_name, None)

    # Drop pending consumer pipes for this app to avoid leaks
    for pipe_key in list(simulator.consumer_pipes.keys()):
        if pipe_key.startswith(app_name):
            simulator.consumer_pipes.pop(pipe_key, None)
    logging.debug("Destroy %s: cleaned consumer pipes", app_name)

    # Clean routing and app registry
    simulator.selector_path.pop(app_name, None)
    simulator.apps.pop(app_name, None)

    # Detach from policies
    for policy in simulator.population_policy.values():
        if app_name in policy["apps"]:
            policy["apps"].remove(app_name)
    for policy in simulator.placement_policy.values():
        if app_name in policy["apps"]:
            policy["apps"].remove(app_name)

    _stop_policy_process(simulator, placement_name, simulator.placement_policy)
    _stop_policy_process(simulator, population_name, simulator.population_policy)
    logging.info("Destroyed application %s", app_name)


def schedule_random_fog_removals(simulator: Sim, interval: int, max_removals: int):
    """Remove a random fog node every `interval` simulation time units.

    This uses the existing `Sim.remove_node` (no core changes). If no fog nodes
    remain, the process stops early.
    """

    def current_fog_nodes():
        fog_ids = []
        for node_id in simulator.topology.G.nodes():
            node = simulator.topology.get_node(node_id)
            model_tag = node.get("model") or node.get("mytag")
            if model_tag == "fog":
                fog_ids.append(node_id)
        return fog_ids

    def _loop():
        removals = 0
        while removals < max_removals:
            yield simulator.env.timeout(interval)
            candidates = current_fog_nodes()
            # Never remove the last remaining fog node to keep the topology alive
            if len(candidates) <= 1:
                logging.info(
                    "Stopping removals: only %d fog node left at t=%s",
                    len(candidates),
                    simulator.env.now,
                )
                return

            node_id = random.choice(candidates)
            node = simulator.topology.get_node(node_id)
            node_label = node.get("label", node_id)
            logging.info(
                "Removing fog node %s (id=%s) at t=%s",
                node_label,
                node_id,
                simulator.env.now,
            )
            simulator.remove_node(node_id)
            removals += 1

    simulator.env.process(_loop())


def start_node_count_monitor(simulator: Sim, interval: int):
    """Sample the number of active nodes over simulation time and return the log list."""

    records = []
    tracked_models = ["fog", "proxy", "cloud", "end"]

    def snapshot():
        model_counts = {model: 0 for model in tracked_models}
        other_nodes = 0

        for node_id in simulator.topology.G.nodes():
            node = simulator.topology.get_node(node_id)
            model = node.get("model") or node.get("mytag") or "unknown"
            if model in model_counts:
                model_counts[model] += 1
            else:
                other_nodes += 1

        records.append(
            {
                "time": simulator.env.now,
                "total_nodes": len(simulator.topology.G.nodes()),
                "cloud_nodes": model_counts["cloud"],
                "proxy_nodes": model_counts["proxy"],
                "fog_nodes": model_counts["fog"],
                "end_nodes": model_counts["end"],
                "other_nodes": other_nodes,
            }
        )

    def _loop():
        snapshot()
        while True:
            yield simulator.env.timeout(interval)
            snapshot()

    simulator.env.process(_loop())
    return records


if __name__ == "__main__":
    import logging.config
    import os

    # Get the directory of the current script
    script_dir = os.path.dirname(os.path.abspath(__file__))

    # Define the log file path
    log_file_path = os.path.join(script_dir, "execution.log")

    logging.config.fileConfig(
        os.path.join(script_dir, "logging.ini"), defaults={"logfilename": log_file_path}
    )
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Verbose logging enabled")

    start_time = time.time()

    results_path = Path("resultados/")
    results_path.mkdir(parents=True, exist_ok=True)
    results_path = str(results_path) + "/"

    # Dynamic lifecycle parameters
    source_period = 100
    reallocation_period = 1000
    app_creation_interval = 200
    app_lifetime = 600
    # Fog removal parameters
    fog_removal_interval = 300
    max_fog_removals = 2
    node_count_interval = 50

    # SELECTION POLICY
    # The Selection Policy determines how messages are routed between service modules.
    # When a module (e.g., Sensor) sends a message to another module (e.g., Service),
    # this policy decides which specific instance of the destination module receives it.
    # 'MinimunPath' routes the message to the nearest instance (shortest network path).
    selection_policy = MinimunPath()

    stop_time = 1000

    # Load topology from file

    file_to_load = "fog2-middle8-end31"
    topology_path = os.path.join(script_dir, f"topologia/{file_to_load}.json")
    logging.info(f"Loading topology from {topology_path}...")
    with open(topology_path, "r") as f:
        topology_json = json.load(f)

    topology = Topology()
    topology.load_all_node_attr(topology_json)

    # Calculate num_fog_nodes from topology
    num_fog_nodes = sum(
        1 for entity in topology_json["entity"] if entity["model"] == "fog"
    )

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
    PLACEMENT_STRATEGY = "custom_proposed_by_felipe"

    # Pattern: {numberOfFogNodes}-{placementStrategy}
    sim_trace_path = results_path + f"{file_to_load}-{PLACEMENT_STRATEGY}-sim_trace"
    simulator = Sim(topology, default_results_path=sim_trace_path)

    # Remove random fog nodes periodically (uses existing Sim.remove_node)
    schedule_random_fog_removals(simulator, fog_removal_interval, max_fog_removals)

    node_count_records = start_node_count_monitor(simulator, node_count_interval)

    def teardown_after(app_ctx: dict, lifetime: float):
        yield simulator.env.timeout(lifetime)
        destroy_application(simulator, app_ctx)
        logging.info(f"Destroyed {app_ctx['app_name']} at t={simulator.env.now}")

    def dynamic_app_manager():
        for idx, app_id in enumerate(sorted_app_ids):
            if idx > 0:
                yield simulator.env.timeout(app_creation_interval)
            app_ctx = register_application(
                simulator,
                app_id,
                selection_policy,
                source_period,
                PLACEMENT_STRATEGY,
                reallocation_period,
                allocate_now=True,
            )
            logging.info(f"Deployed {app_ctx['app_name']} at t={simulator.env.now}")
            if app_lifetime > 0:
                simulator.env.process(teardown_after(app_ctx, app_lifetime))

    simulator.env.process(dynamic_app_manager())

    simulator.run(stop_time)

    node_counts_file = sim_trace_path + "_node_counts.csv"
    with open(node_counts_file, "w", newline="") as f:
        fieldnames = [
            "time",
            "total_nodes",
            "cloud_nodes",
            "proxy_nodes",
            "fog_nodes",
            "end_nodes",
            "other_nodes",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(node_count_records)
    logging.info("Saved node count samples to %s", node_counts_file)

    # Logic to save unprocessed messages (Queue Buildup)
    unprocessed_file = results_path + "unprocessed_messages.csv"
    logging.info(f"Saving unprocessed messages to {unprocessed_file}...")

    # DEBUG: Print queue sizes
    logging.info(f"Network Queue Size: {len(simulator.network_ctrl_pipe.items)}")
    total_consumer_items = sum(len(p.items) for p in simulator.consumer_pipes.values())
    logging.info(f"Total Consumer Queues Size: {total_consumer_items}")
    logging.info(
        f"In-Transit/Processing Messages: {len(simulator.processing_messages)}"
    )

    with open(unprocessed_file, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            [
                "QueueType",
                "App",
                "Message",
                "Src",
                "Dst",
                "Timestamp",
                "Path",
                "CurrentNode",
                "Until",
            ]
        )

        # 1. Network Queue (Messages in transit)
        # simulator.network_ctrl_pipe is a simpy.Store
        if hasattr(simulator.network_ctrl_pipe, "items"):
            for msg in simulator.network_ctrl_pipe.items:
                writer.writerow(
                    [
                        "Network_Queue",
                        msg.app_name,
                        msg.name,
                        msg.src,
                        msg.dst,
                        msg.timestamp,
                        msg.path,
                        msg.dst_int,
                        "N/A",
                    ]
                )

        # 2. Consumer Queues (Messages waiting for processing at nodes)
        # simulator.consumer_pipes is a dict of simpy.Store
        for pipe_id, pipe in simulator.consumer_pipes.items():
            if hasattr(pipe, "items"):
                for msg in pipe.items:
                    writer.writerow(
                        [
                            "Processing_Queue",
                            msg.app_name,
                            msg.name,
                            msg.src,
                            msg.dst,
                            msg.timestamp,
                            msg.path,
                            msg.dst_int,
                            "N/A",
                        ]
                    )

        # 3. Active Processing/Transit (Messages in yield)
        for entry in simulator.processing_messages:
            msg = entry["msg"]
            writer.writerow(
                [
                    entry["type"],
                    msg.app_name,
                    msg.name,
                    msg.src,
                    msg.dst,
                    msg.timestamp,
                    msg.path,
                    msg.dst_int,
                    entry.get("until", "N/A"),
                ]
            )

    logging.info("\n--- %s seconds ---" % (time.time() - start_time))
