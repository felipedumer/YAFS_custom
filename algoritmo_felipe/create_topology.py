import networkx
import random
from yafs.topology import Topology
from pathlib import Path
import os
import json

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
    link_bw_cloud=10000,
    link_pr_cloud=2000,
    link_bw_fog=1500,
    link_pr_fog=100,
    link_bw_aggregation=1000,
    link_pr_aggregation=100,
    link_bw_edge=200,
    link_pr_edge=100,
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
    aggregation_nodes_per_fog = random.randint(10, 15)
    edge_nodes_per_aggregation = random.randint(20, 30)
    sensors_per_edge_node = 1

    topology_json = {"entity": [], "link": []}
    node_id = 0

    def next_id():
        nonlocal node_id
        current = node_id
        node_id += 1
        return current

    def random_x():
        return random.uniform(0, city_width)

    def get_random_bw(base):
        return max(1, random.randint(int(base * 0.5), int(base * 1.5)))

    def get_random_pr(base):
        return max(0.1, random.uniform(base * 0.5, base * 1.5))

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
            "COST": float(cloud_cost),
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
                "IPT": random.randint(10000, 20000) * 10**6,
                "RAM": random.randint(1500, 3000),
                "COST": random.uniform(1.0, 3.0),
                "WATT": random.uniform(8.0, 12.0),
                "ISP": random.choice(["ISP-A", "ISP-B", "ISP-C", "ISP-D"]),
                "x": random_x(),
                "y": fog_y,
            }
        )
        # Connect Fog to Cloud
        topology_json["link"].append(
            {"s": cloud_id, "d": fog_id, "BW": get_random_bw(link_bw_cloud), "PR": get_random_pr(link_pr_cloud)}
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
                {"s": fog_id, "d": agg_id, "BW": get_random_bw(link_bw_fog), "PR": get_random_pr(link_pr_fog)}
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
                        {"s": extra_fog, "d": agg_id, "BW": get_random_bw(link_bw_fog), "PR": get_random_pr(link_pr_fog)}
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
                    {"s": u, "d": v, "BW": get_random_bw(link_bw_aggregation), "PR": get_random_pr(link_pr_aggregation)}
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
                            {"s": agg_id, "d": neighbor, "BW": get_random_bw(link_bw_aggregation), "PR": get_random_pr(link_pr_aggregation)}
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
                {"s": agg_id, "d": edge_node_id, "BW": get_random_bw(link_bw_aggregation), "PR": get_random_pr(link_pr_aggregation)}
            )

            # Sensors
            for sensor_idx in range(sensors_per_edge_node):
                sensor_id = next_id()
                topology_json["entity"].append(
                    {
                        "id": sensor_id,
                        "model": f"Application-{app_id}-Sensor",
                        "label": f"Application-{app_id}-Sensor",
                        "IPT": random.randint(80, 120) * 10**6,
                        "RAM": random.randint(5, 15),
                        "COST": 1,
                        "WATT": 0.1,
                        "x": edge_node_x + random.uniform(-2, 2),
                        "y": device_y,
                    }
                )
                topology_json["link"].append(
                    {"s": edge_node_id, "d": sensor_id, "BW": get_random_bw(link_bw_edge), "PR": get_random_pr(link_pr_edge)}
                )

    return topology_json

def main():
    # Define path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(script_dir, "topologia/")
    os.makedirs(results_path, exist_ok=True)
    
    topology_file = os.path.join(results_path, "random_topology.json")

    # Create topology
    num_fog_nodes = 5
    print(f"Generating topology with {num_fog_nodes} fog nodes...")
    topology_json = create_random_topology(
        num_fog_nodes=num_fog_nodes,
        random_seed=42,
    )

    # Save to JSON
    print(f"Saving topology to {topology_file}...")
    with open(topology_file, "w") as f:
        json.dump(topology_json, f, indent=4)

    # Load into YAFS Topology to save GEXF (visualization)
    topology = Topology()
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
    
    gexf_path = os.path.join(results_path, f"graph_{num_fog_nodes}_fog.gexf")
    print(f"Saving GEXF to {gexf_path}...")
    networkx.write_gexf(topology.G, gexf_path)

if __name__ == "__main__":
    main()
