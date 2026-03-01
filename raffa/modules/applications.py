import random
import logging

from yafs.application import Application, fractional_selectivity
from yafs.core import Sim
from yafs.population import Statical
from yafs.distribution import deterministic_distribution

from modules.messages import MessageProfile, RandomMessage
from modules.selections import MinimunPath
from modules.allocations import CustomPlacement

MESSAGE_PROFILE = MessageProfile()

APP_MAX_RAM = 1000
APP_MIN_RAM = 500
APP_MAX_IPT = 5000
APP_MIN_IPT = 2500

logger = logging.getLogger(__name__)


def create_application_structure(name: str) -> Application:
    # APLICATION
    app = Application(name)

    # Names of modules/services
    endDeviceApplicationName = f"{name}-EndDevice"
    serviceApplicationName = f"{name}-Service"

    """
    Creating Modules/Services
    (EndDevice) --> (Service) --> (EndDevice)
    EndDevice is both Source (generator) and Module (consumer of response), because it needs to receive an answer from the server, and do something.
    """
    app.set_modules(
        [
            {endDeviceApplicationName: {"Type": Application.TYPE_MODULE}},
            {
                serviceApplicationName: {
                    "RAM": random.randint(APP_MIN_RAM, APP_MAX_RAM),
                    "IPT": random.randint(APP_MIN_IPT, APP_MAX_IPT),
                    "Type": Application.TYPE_MODULE,
                }
            },
        ]
    )

    """
    Creating Messages among MODULES
    """
    # MESSAGE_REQUEST: EndDevice -> Service. High instructions (Service workload), High size.
    msg_req = RandomMessage(
        MESSAGE_PROFILE.Request.name,
        endDeviceApplicationName,
        serviceApplicationName,
        instructions=MESSAGE_PROFILE.Request.instructions,
        bytes=MESSAGE_PROFILE.Request.bytes,
    )

    # MESSAGE_RESPONSE: Service -> EndDevice. Low instructions (EndDevice answer), Medium size.
    msg_resp = RandomMessage(
        MESSAGE_PROFILE.Response.name,
        serviceApplicationName,
        endDeviceApplicationName,
        instructions=MESSAGE_PROFILE.Response.instructions,
        bytes=MESSAGE_PROFILE.Response.bytes,
    )

    """
    Defining which messages will be dynamically generated
    """
    app.add_source_messages(msg_req)

    app.add_source_messages(msg_resp)

    """
    Adds MODULES/SERVICES
    """
    # EndDevice -> Service (Request) -> Service -> EndDevice (Response)
    app.add_service_module(
        serviceApplicationName, msg_req, msg_resp, fractional_selectivity, threshold=1.0
    )

    # Service (Response) -> EndDevice
    app.add_service_module(endDeviceApplicationName, msg_resp)

    return app, endDeviceApplicationName, serviceApplicationName

def register_application(
    simulator: Sim,
    app_id: int,
    selection_policy: MinimunPath,
    source_period: int,
    placement_strategy: str,
    reallocation_period: int,
    allocate_now: bool = False,
    app_lifetime: int = 2000,
) -> dict:
    app_name = f"Application-{app_id}"
    app, endDeviceApplicationName, serviceApplicationName = create_application_structure(app_name)

    # Create per-app distributions so later deployments are not coupled through shared state
    reallocation_dist = deterministic_distribution(
        name=f"Reallocation-{app_id}", time=reallocation_period
    )
    src_distribution = deterministic_distribution(
        name=f"Deterministic-{app_id}", time=source_period
    )

    placement_policy = CustomPlacement(
        f"CustomPlacement-{app_id}",
        activation_dist=reallocation_dist,
        strategy=placement_strategy,
        app_lifetime=app_lifetime,
    )
    placement_policy.scaleService({endDeviceApplicationName: 1, serviceApplicationName: 1})

    population = Statical(f"Statical-{app_id}")
    population.set_src_control(
        {
            "model": f"EndDevice-{app_id}",
            "number": 1,
            "message": app.get_message(MESSAGE_PROFILE.Request.name),
            "distribution": src_distribution,
            "param": {"time_shift": 100},
        }
    )

    simulator.deploy_app2(app, placement_policy, population, selection_policy)
    logger.info(
        "Registered app %s with placement %s, population %s | src_period=%s realloc_period=%s",
        app_name,
        placement_policy.name,
        population.name,
        source_period,
        reallocation_period,
    )

    # When apps are injected mid-simulation, we need to do the initial allocation manually
    if allocate_now:
        logger.info("Triggering immediate allocations for %s", app_name)
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
    logging.debug("Destroy %s: removing %d sources | T:%s", app_name, len(sources_to_remove), simulator.env.now)
    for des in sources_to_remove:
        node_id = simulator.alloc_DES.get(des)
        node_label = (
            simulator.topology.get_node(node_id).get("label", node_id)
            if node_id is not None and simulator.topology.G.has_node(node_id)
            else "?"
        )
        logging.info(
            "Destroy %s: stopping source DES=%s at node %s | T:%s",
            app_name,
            des,
            node_label,
            simulator.env.now,
        )
        simulator.undeploy_source(des)

    # Stop and remove deployed modules (service + sensor consumers)
    if app_name in simulator.alloc_module:
        for module, des_list in list(simulator.alloc_module[app_name].items()):
            logging.debug(
                "Destroy %s: removing %d deployments of module %s | T:%s",
                app_name,
                len(des_list),
                module,
                simulator.env.now,
            )
            for des in list(des_list):
                node_id = simulator.alloc_DES.get(des)
                node_label = (
                    simulator.topology.get_node(node_id).get("label", node_id)
                    if node_id is not None and simulator.topology.G.has_node(node_id)
                    else "?"
                )
                logging.info(
                    "Destroy %s: undeploying module %s DES=%s at node %s | T:%s",
                    app_name,
                    module,
                    des,
                    node_label,
                    simulator.env.now,
                )
                simulator.undeploy_module(app_name, module, des)
        simulator.alloc_module.pop(app_name, None)

    # Drop pending consumer pipes for this app to avoid leaks
    for pipe_key in list(simulator.consumer_pipes.keys()):
        if pipe_key.startswith(app_name):
            simulator.consumer_pipes.pop(pipe_key, None)
    logging.debug("Destroy %s: cleaned consumer pipes | T:%s", app_name, simulator.env.now)

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
    logging.info("Destroyed application %s | T:%s", app_name, simulator.env.now)

def teardown_after(
    simulator: Sim,
    app_ctx: dict,
    lifetime: float,
    app_contexts: dict,
    app_id: int,
    selection_policy: MinimunPath,
    source_period: int,
    placement_strategy: str,
    reallocation_period: int,
    app_lifetime: int,
):
    yield simulator.env.timeout(lifetime)
    # Only destroy if this context is still the active one (guard against stale teardowns)
    if app_contexts.get(app_id) is not app_ctx:
        logging.debug(f"Skipped stale teardown for {app_ctx['app_name']} at t={simulator.env.now} (already recycled)")
        return

    destroy_application(simulator, app_ctx)
    logging.info(f"Teardown destroyed {app_ctx['app_name']} at t={simulator.env.now}")

    # Immediately redeploy on fresh surviving nodes
    new_ctx = register_application(
        simulator,
        app_id,
        selection_policy,
        source_period,
        placement_strategy,
        reallocation_period,
        allocate_now=True,
        app_lifetime=app_lifetime,
    )
    app_contexts[app_id] = new_ctx
    logging.info(f"Teardown redeployed {new_ctx['app_name']} at t={simulator.env.now}")

    # Schedule the next teardown cycle
    if app_lifetime > 0:
        simulator.env.process(teardown_after(
            simulator, new_ctx, app_lifetime, app_contexts, app_id,
            selection_policy, source_period, placement_strategy,
            reallocation_period, app_lifetime,
        ))


def dynamic_app_manager(
    sorted_app_ids: list,
    simulator: Sim,
    selection_policy: MinimunPath,
    source_period: int,
    placement_strategy: str,
    reallocation_period: int,
    app_creation_interval: int,
    app_lifetime: int,
):
    # Keep as generator for env.process
    yield simulator.env.timeout(0)

    # Deploy all apps immediately
    app_contexts = {}
    for app_id in sorted_app_ids:
        ctx = register_application(
            simulator,
            app_id,
            selection_policy,
            source_period,
            placement_strategy,
            reallocation_period,
            allocate_now=True,
            app_lifetime=app_lifetime,
        )
        app_contexts[app_id] = ctx
        logging.info(f"Deployed {ctx['app_name']} at t={simulator.env.now}")
        if app_lifetime > 0:
            simulator.env.process(teardown_after(
                simulator, ctx, app_lifetime, app_contexts, app_id,
                selection_policy, source_period, placement_strategy,
                reallocation_period, app_lifetime,
            ))

    # If no interval, stop here
    if app_creation_interval <= 0:
        return

    # Simple rolling recycle: each interval, remove a small batch and recreate immediately
    total_apps = len(sorted_app_ids)
    batch_size = max(1, total_apps // 5)  # ~20% each round
    cursor = 0

    while True:
        yield simulator.env.timeout(app_creation_interval)

        batch_ids = random.sample(sorted_app_ids, k=min(batch_size, total_apps))

        for app_id in batch_ids:
            ctx = app_contexts.get(app_id)
            if ctx:
                destroy_application(simulator, ctx)

            new_ctx = register_application(
                simulator,
                app_id,
                selection_policy,
                source_period,
                placement_strategy,
                reallocation_period,
                allocate_now=True,
                app_lifetime=app_lifetime,
            )
            app_contexts[app_id] = new_ctx
            logging.info(f"Re-Deployed {new_ctx['app_name']} at t={simulator.env.now}")
            if app_lifetime > 0:
                simulator.env.process(teardown_after(
                    simulator, new_ctx, app_lifetime, app_contexts, app_id,
                    selection_policy, source_period, placement_strategy,
                    reallocation_period, app_lifetime,
                ))
