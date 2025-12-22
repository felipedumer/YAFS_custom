import networkx
import random
from yafs.topology import Topology
from pathlib import Path
import os
import json


def create_random_topology(
    random_seed=None,
    cloud_ipt=120000,  # instructions per time unit
    cloud_ram=64000,   # MB
    cloud_cost=10,     # arbitrary cost units
    cloud_watt=100.0,  # watts
    proxy_ipt=60000,   # instructions per time unit
    proxy_ram=8000,    # MB
    proxy_cost=4,      # arbitrary cost units
    proxy_watt=40.0,   # watts
    gateway_ipt=0,      # gateways are forwarding-only; set IPT to 0
    gateway_ram=0,      # gateways are forwarding-only; set RAM to 0
    gateway_cost=0,     # minimal cost for gateways
    gateway_watt=0.0,   # minimal wattage for gateways
    edge_nodes=12,
    devices_per_edge=4,
    edge_small_ipt=6750,     # instructions per time unit
    edge_small_ram=1000,     # MB
    edge_big_ipt=13500,      # instructions per time unit
    edge_big_ram=2000,       # MB
    # 10000 Mbps ≈ 1_250_000_000 bytes per second
    link_bw_cloud_proxy=1250000000,  # bytes per second
    link_pr_cloud_proxy=100,         # milliseconds
    # 10000 Mbps ≈ 1_250_000_000 bytes per second
    link_bw_proxy_edge=1250000000,   # bytes per second
    link_pr_proxy_edge=2,            # milliseconds
    # 0.65 Mbps ≈ 81_250 bytes per second
    link_bw_edge_device=81250,       # bytes per second
    link_pr_edge_device=100,         # milliseconds
):
    """
    Create a fixed 3-layer topology:
      - Cloud (1)
      - Proxy server (1)
            - Gateway nodes (1 per fog)
                - Fog nodes (12)
                - End devices (48 total, devices_per_edge each)

        The structure is Cloud -> Proxy -> Gateway -> Fog -> End devices.
        Each fog has a dedicated gateway; end devices attach to the gateway,
        so if a fog is removed the gateway can still forward upstream.
    """
    if random_seed is not None:
        random.seed(random_seed)

    total_devices = edge_nodes * devices_per_edge

    topology_json = {"entity": [], "link": []}
    node_id = 0

    def next_id():
        nonlocal node_id
        current = node_id
        node_id += 1
        return current

    # 1) Cloud
    cloud_id = next_id()
    topology_json["entity"].append(
        {
            "id": cloud_id,
            "model": "cloud",
            "mytag": "cloud",
            "label": "Cloud",
            "IPT": cloud_ipt,      # instructions/time unit
            "RAM": cloud_ram,       # MB
            "COST": float(cloud_cost),
            "WATT": cloud_watt,     # watts
        }
    )

    # 2) Proxy server
    proxy_id = next_id()
    topology_json["entity"].append(
        {
            "id": proxy_id,
            "model": "proxy",
            "mytag": "proxy",
            "label": "Proxy",
            "IPT": proxy_ipt,       # instructions/time unit
            "RAM": proxy_ram,       # MB
            "COST": float(proxy_cost),
            "WATT": proxy_watt,     # watts
        }
    )
    topology_json["link"].append(
        {
            "s": cloud_id,
            "d": proxy_id,
            "BW": link_bw_cloud_proxy,
            "PR": link_pr_cloud_proxy,
        }
    )

    # Gateway-fog link intentionally matches proxy-edge characteristics
    link_bw_gateway_fog = link_bw_proxy_edge
    link_pr_gateway_fog = link_pr_proxy_edge

    # 3) Gateway + Fog nodes (half small, half big)
    gateway_ids = []
    edge_ids = []
    small_count = edge_nodes // 2
    for i in range(edge_nodes):
        # 3a) Gateway (unique per fog)
        gateway_id = next_id()
        topology_json["entity"].append(
            {
                "id": gateway_id,
                "model": "gateway",
                "mytag": "gateway",
                "label": f"Gateway-{i+1}",
                "IPT": gateway_ipt,
                "RAM": gateway_ram,
                "COST": float(gateway_cost),
                "WATT": gateway_watt,
            }
        )
        topology_json["link"].append(
            {
                "s": proxy_id,
                "d": gateway_id,
                "BW": link_bw_proxy_edge,
                "PR": link_pr_proxy_edge,
            }
        )
        gateway_ids.append(gateway_id)

        # 3b) Fog behind this gateway
        edge_id = next_id()
        is_small = i < small_count
        ipt_val = edge_small_ipt if is_small else edge_big_ipt
        ram_val = edge_small_ram if is_small else edge_big_ram
        topology_json["entity"].append(
            {
                "id": edge_id,
                "model": "fog",
                "mytag": "fog",
                "label": f"Fog-{i+1}",
                "IPT": ipt_val,      # instructions/time unit
                "RAM": ram_val,      # MB
                "COST": proxy_cost * random.uniform(0.5, 1.5),
                "WATT": proxy_watt * random.uniform(0.5, 1.5),
            }
        )
        topology_json["link"].append(
            {
                "s": gateway_id,
                "d": edge_id,
                "BW": link_bw_gateway_fog,
                "PR": link_pr_gateway_fog,
            }
        )
        edge_ids.append(edge_id)

    # 4) End devices (attach to corresponding gateway, not fog)
    device_count = 0
    for gw_id in gateway_ids:
        for _ in range(devices_per_edge):
            device_count += 1
            dev_id = next_id()
            label = f"EndDevice-{device_count}"
            topology_json["entity"].append(
                {
                    "id": dev_id,
                    "model": label,
                    "label": label,
                    "IPT": random.randint(50, 120) * 10**6,  # instructions/time unit
                    "RAM": random.randint(4, 16),            # MB
                    "COST": 1,
                    "WATT": 0.5,                             # watts
                }
            )
            topology_json["link"].append(
                {
                    "s": gw_id,
                    "d": dev_id,
                    "BW": link_bw_edge_device,
                    "PR": link_pr_edge_device,
                }
            )

    return topology_json, 1, edge_nodes, total_devices


def main():
    # Define path
    script_dir = os.path.dirname(os.path.abspath(__file__))
    results_path = os.path.join(script_dir, "topologia/")
    os.makedirs(results_path, exist_ok=True)

    # Create topology (fixed: 1 cloud, 1 proxy, 12 fog nodes, 48 end devices)
    print("Generating topology: cloud + proxy + 12 fog nodes + 48 end devices ...")
    topology_json, n_cloud, n_edge, n_devices = create_random_topology(
        random_seed=42,
    )

    filename = f"cloud{n_cloud}-gateway{n_edge}-fog{n_edge}-end{n_devices}"
    topology_file = os.path.join(results_path, f"{filename}.json")

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

    gexf_path = os.path.join(results_path, f"{filename}.gexf")
    print(f"Saving GEXF to {gexf_path}...")
    networkx.write_gexf(topology.G, gexf_path)


if __name__ == "__main__":
    main()
