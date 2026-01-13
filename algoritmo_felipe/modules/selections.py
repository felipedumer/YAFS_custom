
from yafs.selection import Selection
import networkx as nx
import logging

logger = logging.getLogger(__name__)


class MinimunPath(Selection):

    def get_path(self, sim, app_name, message, topology_src, alloc_DES, alloc_module, traffic,from_des):

        """
        Computes the minimun path among the source elemento of the topology and the localizations of the module

        Return the path and the identifier of the module deployed in the last element of that path
        """
        node_src = topology_src

        # Skip if src node was removed
        if not sim.topology.G.has_node(node_src):
            logging.warning("FAILURE: source node %s not in topology for %s", node_src, app_name)
            try:
                src_label = sim.topology.get_node(node_src).get('label', node_src) if sim.topology.G.has_node(node_src) else ""
                sim.metrics.insert_failure({
                    "id": getattr(message, "id", None),
                    "app": app_name,
                    "message": message.name,
                    "reason": "missing_source",
                    "TOPO.src": node_src,
                    "TOPO.dst": message.dst,
                    "TOPO.srcLabel": src_label,
                    "TOPO.dstLabel": message.dst,
                    "ctime": sim.env.now,
                })
                sim.metrics.flush()
            except Exception:
                logging.exception("Failed to record failure metric")
            return [], []

        # Filter destinations whose node still exists
        DES_dst = [des for des in alloc_module[app_name][message.dst] if sim.topology.G.has_node(alloc_DES[des])]
        if not DES_dst:
            logging.warning("FAILURE: no reachable destination nodes for %s (module %s)", app_name, message.dst)
            try:
                src_label = sim.topology.get_node(node_src).get('label', node_src) if sim.topology.G.has_node(node_src) else ""
                sim.metrics.insert_failure({
                    "id": getattr(message, "id", None),
                    "app": app_name,
                    "message": message.name,
                    "reason": "missing_destination",
                    "TOPO.src": node_src,
                    "TOPO.dst": message.dst,
                    "TOPO.srcLabel": src_label,
                    "TOPO.dstLabel": message.dst,
                    "ctime": sim.env.now,
                })
                sim.metrics.flush()
            except Exception:
                logging.exception("Failed to record failure metric")
            return [], []

        print(("GET PATH"))
        print(("\tNode _ src (id_topology): %i" %node_src))
        print(("\tRequest service: %s " %message.dst))
        print(("\tProcess serving that service: %s " %DES_dst))

        bestPath = []
        bestDES = []

        for des in DES_dst: ## In this case, there are only one deployment
            dst_node = alloc_DES[des]
            print(("\t\t Looking the path to id_node: %i" %dst_node))

            try:
                path = list(nx.shortest_path(sim.topology.G, source=node_src, target=dst_node))
            except nx.NodeNotFound:
                logging.warning("FAILURE: path not found because node missing (src=%s dst=%s)", node_src, dst_node)
                try:
                    src_label = sim.topology.get_node(node_src).get('label', node_src) if sim.topology.G.has_node(node_src) else ""
                    dst_label = sim.topology.get_node(dst_node).get('label', dst_node) if sim.topology.G.has_node(dst_node) else ""
                    sim.metrics.insert_failure({
                        "id": getattr(message, "id", None),
                        "app": app_name,
                        "message": message.name,
                        "reason": "node_not_found",
                        "TOPO.src": node_src,
                        "TOPO.dst": dst_node,
                        "TOPO.srcLabel": src_label,
                        "TOPO.dstLabel": dst_label,
                        "ctime": sim.env.now,
                    })
                    sim.metrics.flush()
                except Exception:
                    logging.exception("Failed to record failure metric")
                continue
            except nx.NetworkXNoPath:
                logging.warning("FAILURE: no path between %s and %s", node_src, dst_node)
                try:
                    src_label = sim.topology.get_node(node_src).get('label', node_src) if sim.topology.G.has_node(node_src) else ""
                    dst_label = sim.topology.get_node(dst_node).get('label', dst_node) if sim.topology.G.has_node(dst_node) else ""
                    sim.metrics.insert_failure({
                        "id": getattr(message, "id", None),
                        "app": app_name,
                        "message": message.name,
                        "reason": "no_path",
                        "TOPO.src": node_src,
                        "TOPO.dst": dst_node,
                        "TOPO.srcLabel": src_label,
                        "TOPO.dstLabel": dst_label,
                        "ctime": sim.env.now,
                    })
                    sim.metrics.flush()
                except Exception:
                    logging.exception("Failed to record failure metric")
                continue

            # custom
            # if bestPath is empty array
            if not bestPath:
                bestPath = path
                bestDES = [des]

            if bestPath > path:
                bestPath = path
                bestDES = [des]
            print("Path: ", path)
            print("Best DES? ", des)

            # original 
            # bestPath = [path]
            # bestDES = [des]

        if not bestPath:
            logging.warning("FAILURE: no valid path found for %s to %s", node_src, message.dst)
            try:
                src_label = sim.topology.get_node(node_src).get('label', node_src) if sim.topology.G.has_node(node_src) else ""
                sim.metrics.insert_failure({
                    "id": getattr(message, "id", None),
                    "app": app_name,
                    "message": message.name,
                    "reason": "no_path",
                    "TOPO.src": node_src,
                    "TOPO.dst": message.dst,
                    "TOPO.srcLabel": src_label,
                    "TOPO.dstLabel": message.dst,
                    "ctime": sim.env.now,
                })
                sim.metrics.flush()
            except Exception:
                logging.exception("Failed to record failure metric")
            return [], []

        return [bestPath], bestDES


class MinPath_RoundRobin(Selection):

    def __init__(self):
        self.rr = {} #for a each type of service, we have a mod-counter

    def get_path(self, sim, app_name, message, topology_src, alloc_DES, alloc_module, traffic,from_des):
        """
        Computes the minimun path among the source elemento of the topology and the localizations of the module

        Return the path and the identifier of the module deployed in the last element of that path
        """
        node_src = topology_src
        DES_dst = alloc_module[app_name][message.dst] #returns an array with all DES process serving


        if message.dst not in self.rr.keys():
            self.rr[message.dst] = 0


        print(("GET PATH"))
        print(("\tNode _ src (id_topology): %i" %node_src))
        print(("\tMessage SRC: %s " %(message.src)))
        print(("\tRequest service: %s " %(message.dst)))
        print(("\tProcesses (DES) serving that service: %s (pos ID: %i)" %(DES_dst,self.rr[message.dst])))

        bestPath = []
        bestDES = []

        for ix,des in enumerate(DES_dst):
            if message.name == "M.A":
                if self.rr[message.dst]==ix:
                    dst_node = alloc_DES[des]

                    path = list(nx.shortest_path(sim.topology.G, source=node_src, target=dst_node))

                    bestPath = [path]
                    bestDES = [des]

                    self.rr[message.dst] = (self.rr[message.dst]+ 1) % len(DES_dst)
                    break
            else: #message.name == "M.B"

                dst_node = alloc_DES[des]

                path = list(nx.shortest_path(sim.topology.G, source=node_src, target=dst_node))
                if message.broadcasting:
                    bestPath.append(path)
                    bestDES.append(des)
                else:
                    bestPath = [path]
                    bestDES = [des]

        return bestPath, bestDES
