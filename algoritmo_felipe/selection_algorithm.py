
from yafs.selection import Selection
import networkx as nx
import logging

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


class DijkstraBasedAllocation(Selection):
    """
    Implementação do algoritmo de alocação baseado em Dijkstra com replicação geográfica.
    Considera recursos (CPU/RAM), latência, confiabilidade e diversidade de ISP.
    """
    
    # Constantes
    REQUER_ISP_DIFERENTE = True
    PESO_RECURSOS = 0.4
    PESO_LATENCIA = 0.3
    PESO_CONFIABILIDADE = 0.3
    NUM_REPLICAS = 2
    
    def __init__(self):
        self.mapeamento_alocacao = {}  # serviço_id -> (nó_primário, nó_secundário)
        
    def get_path(self, sim, app_name, message, topology_src, alloc_DES, alloc_module, traffic, from_des):
        """
        Encontra o melhor par de nós para alocar o serviço usando algoritmo baseado em Dijkstra.
        """
        node_src = topology_src
        DES_dst = alloc_module[app_name][message.dst]
        
        print("\n=== DIJKSTRA-BASED ALLOCATION ===")
        print(f"Nó origem (topology): {node_src}")
        print(f"Serviço requisitado: {message.dst}")
        print(f"Processos DES disponíveis: {DES_dst}")
        
        # Encontra o melhor par de nós
        par_otimo = self._encontrar_melhor_par_de_nos(sim, message, DES_dst, alloc_DES)
        
        if par_otimo is None:
            print("ERRO: Não foi possível encontrar par de nós adequado")
            # Fallback: usa o primeiro nó disponível
            if len(DES_dst) > 0:
                des = DES_dst[0]
                dst_node = alloc_DES[des]
                path = list(nx.shortest_path(sim.topology.G, source=node_src, target=dst_node))
                return [path], [des]
            return [], []
        
        # Retorna o caminho para o nó primário
        des_primario = par_otimo['des_primario']
        des_secundario = par_otimo['des_secundario']
        node_primario = par_otimo['no_primario']
        node_secundario = par_otimo['no_secundario']
        
        path_primario = list(nx.shortest_path(sim.topology.G, source=node_src, target=node_primario))
        path_secundario = list(nx.shortest_path(sim.topology.G, source=node_src, target=node_secundario))
        
        print(f"\n✓ Par ótimo encontrado:")
        print(f"  Primário: Nó {node_primario} (DES: {des_primario})")
        print(f"  Secundário: Nó {node_secundario} (DES: {des_secundario})")
        print(f"  Custo total: {par_otimo['custo_total']:.4f}")
        print(f"  ISPs diferentes: {par_otimo['isps_diferentes']}")
        print(f"  Caminho primário: {path_primario}")
        print(f"  Caminho secundário: {path_secundario}")
        
        # Armazena o mapeamento
        self.mapeamento_alocacao[message.name] = par_otimo
        
        # Retorna caminho primário (o secundário fica como backup)
        return [path_primario], [des_primario]
    
    def _encontrar_melhor_par_de_nos(self, sim, message, DES_dst, alloc_DES):
        """
        Algoritmo de Dijkstra modificado para encontrar o melhor par de nós.
        """
        candidatos_pares = []
        
        # Filtra nós viáveis (com recursos suficientes)
        nos_viaveis = self._filtrar_nos_viaveis(sim, message, DES_dst, alloc_DES)
        
        if len(nos_viaveis) < self.NUM_REPLICAS:
            print(f"AVISO: Apenas {len(nos_viaveis)} nós viáveis encontrados (necessário {self.NUM_REPLICAS})")
            return None
        
        print(f"\nNós viáveis encontrados: {len(nos_viaveis)}")
        
        # Para cada nó viável, encontra o melhor par
        for info_primario in nos_viaveis:
            melhor_secundario = None
            melhor_custo_par = float('inf')
            
            for info_secundario in nos_viaveis:
                # Ignora o mesmo nó
                if info_primario['no_id'] == info_secundario['no_id']:
                    continue
                
                # Verifica se são ISPs diferentes (requisito de segurança)
                isp_primario = self._obter_isp_do_no(sim, info_primario['no_id'])
                isp_secundario = self._obter_isp_do_no(sim, info_secundario['no_id'])
                
                if self.REQUER_ISP_DIFERENTE and isp_primario == isp_secundario:
                    continue
                
                # Calcula custo combinado do par (inspirado em Dijkstra)
                custo_primario = self._calcular_custo_no(sim, info_primario, message, e_primario=True)
                custo_secundario = self._calcular_custo_no(sim, info_secundario, message, e_primario=False)
                
                custo_total = custo_primario + custo_secundario
                
                # Mantém o melhor par para este nó primário
                if custo_total < melhor_custo_par:
                    melhor_custo_par = custo_total
                    melhor_secundario = info_secundario
            
            # Adiciona o melhor par encontrado para este nó primário
            if melhor_secundario is not None:
                isp_prim = self._obter_isp_do_no(sim, info_primario['no_id'])
                isp_sec = self._obter_isp_do_no(sim, melhor_secundario['no_id'])
                
                par = {
                    'no_primario': info_primario['no_id'],
                    'no_secundario': melhor_secundario['no_id'],
                    'des_primario': info_primario['des'],
                    'des_secundario': melhor_secundario['des'],
                    'custo_total': melhor_custo_par,
                    'isps_diferentes': (isp_prim != isp_sec),
                    'isp_primario': isp_prim,
                    'isp_secundario': isp_sec
                }
                candidatos_pares.append(par)
        
        # Retorna o par com menor custo total (similar ao caminho mais curto de Dijkstra)
        if len(candidatos_pares) == 0:
            return None
        
        par_otimo = min(candidatos_pares, key=lambda p: p['custo_total'])
        return par_otimo
    
    def _filtrar_nos_viaveis(self, sim, message, DES_dst, alloc_DES):
        """
        Filtra nós que possuem recursos suficientes (critério impeditivo).
        """
        nos_viaveis = []
        
        for des in DES_dst:
            no_id = alloc_DES[des]
            no_attrs = sim.topology.G.nodes[no_id]
            
            # Verifica se o nó está ativo
            if not self._no_esta_ativo(sim, no_id):
                print(f"  Nó {no_id} descartado: inativo")
                continue
            
            # CRITÉRIO IMPEDITIVO: Verifica recursos (se disponíveis nos atributos)
            cpu_disponivel = no_attrs.get('IPT', 0)
            ram_disponivel = no_attrs.get('RAM', 0)
            
            # Recursos necessários (simplificado - pode ser ajustado)
            cpu_necessaria = 10 * 10**6  # 10 MIPS
            ram_necessaria = 10  # 10 MB
            
            if cpu_disponivel < cpu_necessaria:
                print(f"  Nó {no_id} descartado: CPU insuficiente ({cpu_disponivel} < {cpu_necessaria})")
                continue
            
            if ram_disponivel < ram_necessaria:
                print(f"  Nó {no_id} descartado: RAM insuficiente ({ram_disponivel} < {ram_necessaria})")
                continue
            
            nos_viaveis.append({
                'no_id': no_id,
                'des': des,
                'cpu_disponivel': cpu_disponivel,
                'ram_disponivel': ram_disponivel
            })
        
        return nos_viaveis
    
    def _calcular_custo_no(self, sim, info_no, message, e_primario):
        """
        Calcula o custo de alocar o serviço em um nó específico.
        Similar ao peso de arestas no Dijkstra.
        """
        no_id = info_no['no_id']
        no_attrs = sim.topology.G.nodes[no_id]
        
        # 1. Custo de recursos (quanto menos disponível, maior o custo)
        cpu_total = no_attrs.get('IPT', 100 * 10**6)
        ram_total = no_attrs.get('RAM', 100)
        
        utilizacao_cpu = 1.0 - (info_no['cpu_disponivel'] / cpu_total) if cpu_total > 0 else 0.5
        utilizacao_ram = 1.0 - (info_no['ram_disponivel'] / ram_total) if ram_total > 0 else 0.5
        custo_recursos = (utilizacao_cpu + utilizacao_ram) / 2.0
        
        # 2. Custo de latência (baseado em propagação de links)
        custo_latencia = self._calcular_latencia_media(sim, no_id)
        
        # 3. Custo de confiabilidade (simulado - pode usar taxa de falhas real)
        custo_confiabilidade = no_attrs.get('taxa_falhas', 0.05)
        
        # Custo total ponderado
        custo = (custo_recursos * self.PESO_RECURSOS +
                custo_latencia * self.PESO_LATENCIA +
                custo_confiabilidade * self.PESO_CONFIABILIDADE)
        
        # Nó primário tem peso ligeiramente menor (preferência)
        if e_primario:
            custo *= 0.9
        
        return custo
    
    def _calcular_latencia_media(self, sim, no_id):
        """
        Calcula a latência média dos links conectados ao nó.
        """
        latencias = []
        for vizinho in sim.topology.G.neighbors(no_id):
            edge_attrs = sim.topology.G.edges[no_id, vizinho]
            pr = edge_attrs.get('PR', 10)  # Propagation delay
            latencias.append(pr)
        
        if len(latencias) == 0:
            return 0.01  # Valor padrão normalizado
        
        latencia_media = sum(latencias) / len(latencias)
        return latencia_media / 1000.0  # Normaliza para 0-1
    
    def _obter_isp_do_no(self, sim, no_id):
        """
        Obtém o ISP (provedor) do nó.
        """
        no_attrs = sim.topology.G.nodes[no_id]
        # Usa o modelo ou uma propriedade específica como ISP
        # Para simulação, considera modelos diferentes como ISPs diferentes
        return no_attrs.get('model', 'ISP_Desconhecido')
    
    def _no_esta_ativo(self, sim, no_id):
        """
        Verifica se o nó está ativo.
        """
        no_attrs = sim.topology.G.nodes[no_id]
        return no_attrs.get('status', 'ATIVO') == 'ATIVO'
