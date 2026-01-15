import time
import logging
import logging.config
import os

from pathlib import Path

from yafs.core import Sim

from modules.selections import MinimunPath
from modules.messages import MessageProfile
from modules.applications import dynamic_app_manager
from modules.metrics import save_node_counts, save_unprocessed_messages
from modules.monitors import schedule_random_fog_removals, start_node_count_monitor
from modules.topology import load_topology

MESSAGE_PROFILE = MessageProfile()

## Configuration Parameters

TOPOLOGY_FILE = "cloud1-gateway12-fog12-end48"
# Define the placement strategy here
# Options: 'latency', 'hops', 'cost', 'ipt', 'custom_proposed_by_felipe', 'roundRobin'
PLACEMENT_STRATEGY = "custom"
SOURCE_PERIOD = 100 # simulation time units
REALLOCATION_PERIOD = 1000 # simulation time units
APP_CREATION_INTERVAL = 200 # simulation time units
APP_LIFETIME = 2000 # simulation time units
FOG_REMOVAL_INTERVAL = 300 # simulation time units
MAX_FOG_REMOVALS = 10
NODE_COUNT_INTERVAL = 50 # simulation time units
STOP_TIME = 100000 # simulation time units
RESULTS_FOLDER = "resultados" 

def main():
    root_path = os.path.dirname(os.path.abspath(__file__))
    log_file_path = os.path.join(root_path, "execution.log")

    results_path = Path(RESULTS_FOLDER)
    results_path.mkdir(parents=True, exist_ok=True)
    results_path = str(results_path) + "/"

    logging.config.fileConfig(
        os.path.join(root_path, "logging.ini"),
        defaults={"logfilename": log_file_path},
        disable_existing_loggers=False,  # keep pre-imported module loggers enabled
    )
    logging.getLogger().setLevel(logging.DEBUG)
    logging.debug("Verbose logging enabled")

    start_time = time.time()

    stop_time = STOP_TIME

    topology, topology_json, num_fog_nodes, topology_path = load_topology(
        root_path, TOPOLOGY_FILE
    )
    logging.info(
        "Loaded topology %s with %d fog nodes", topology_path, num_fog_nodes
    )

    sim_trace_path = results_path + f"{TOPOLOGY_FILE}-{PLACEMENT_STRATEGY}-sim_trace" # {nodes}-{PLACEMENT_STRATEGY}

    simulator = Sim(topology, default_results_path=sim_trace_path)

    # Identify all applications from the topology entities
    app_ids = set()
    for entity in topology_json["entity"]:
        if "model" in entity and entity["model"].startswith("EndDevice-"):
            # Format: model: EndDevice-{id}
            parts = entity["model"].split("-")
            if len(parts) >= 2 and parts[1].isdigit():
                app_ids.add(int(parts[1]))


    sorted_app_ids = sorted(list(app_ids))
    logging.info(f"Deploying {len(sorted_app_ids)} applications...")

    selection_policy = MinimunPath()

    simulator.env.process(
        dynamic_app_manager(
            sorted_app_ids=sorted_app_ids,
            simulator=simulator,
            selection_policy=selection_policy,
            source_period=SOURCE_PERIOD,
            placement_strategy=PLACEMENT_STRATEGY,
            reallocation_period=REALLOCATION_PERIOD,
            app_creation_interval=APP_CREATION_INTERVAL,
            app_lifetime=APP_LIFETIME,
        )
    )

    # Optional: Schedule random fog node removals
    schedule_random_fog_removals(simulator, FOG_REMOVAL_INTERVAL, MAX_FOG_REMOVALS)

    node_count_records = start_node_count_monitor(simulator, NODE_COUNT_INTERVAL)

    simulator.run(stop_time)

    node_counts_file = sim_trace_path + "_node_counts.csv"
    save_node_counts(node_count_records, node_counts_file)

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

    save_unprocessed_messages(simulator, unprocessed_file)

    logging.info("\n--- %s seconds ---" % (time.time() - start_time))

if __name__ == "__main__":
    main()