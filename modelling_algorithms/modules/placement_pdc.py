import networkx as nx
import random
import numpy as np
from itertools import islice
from itertools import combinations

def place_pdcs_greedy(G, max_latency, flag_splitting=False):

    def edge_key(u, v):
        return tuple(sorted((u, v)))

    def path_delay(H, path):
        return sum(
            float(H[a][b].get("latency", 0.0))
            for a, b in zip(path[:-1], path[1:])
        )

    def build_active_subgraph(G):
        H = nx.Graph()
        for n, data in G.nodes(data=True):
            if data.get("status", "online") == "online":
                H.add_node(n, **data)

        for u, v, data in G.edges(data=True):
            if u in H and v in H and data.get("status", "up") == "up":
                H.add_edge(u, v, **data)
        return H

    H = build_active_subgraph(G)

    cc = "CC"
    if cc not in H:
        raise ValueError("Nodo 'CC' non presente o non online (dopo filtering).")

    pmus = [n for n, d in H.nodes(data=True) if d.get("role") == "PMU"]

    used_bw = {}        # (u,v) -> used bandwidth
    next_hop_to_cc = {} # PDC(candidate) -> next hop toward CC (per no-splitting)

    pmu_paths = {}      # pmu -> {"path": [...], "delay": float}   (SOLO se valido)
    pdcs = set()
    accepted_delays = []

    for pmu in pmus:
        demand = float(H.nodes[pmu].get("data_rate", 0.0))

        try:
            paths_iter = nx.shortest_simple_paths(H, pmu, cc, weight="latency")
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            continue  # <-- niente None

        chosen_path = None
        chosen_delay = None

        for path in paths_iter:
            delay = path_delay(H, path)
            if delay > max_latency:
                continue

            if not flag_splitting:
                ok = True
                for i in range(1, len(path) - 1):
                    node = path[i]
                    if H.nodes[node].get("role") != "candidate":
                        continue
                    nxt = path[i + 1]
                    if node in next_hop_to_cc and next_hop_to_cc[node] != nxt:
                        ok = False
                        break
                if not ok:
                    continue

            ok = True
            for a, b in zip(path[:-1], path[1:]):
                cap = float(H[a][b].get("bandwidth", float("inf")))
                k = edge_key(a, b)
                if used_bw.get(k, 0.0) + demand > cap:
                    ok = False
                    break
            if not ok:
                continue

            chosen_path = path
            chosen_delay = float(delay)
            break

        if chosen_path is None:
            continue  # <-- niente None

        # commit bandwidth
        for a, b in zip(chosen_path[:-1], chosen_path[1:]):
            k = edge_key(a, b)
            used_bw[k] = used_bw.get(k, 0.0) + demand

        # commit no-splitting
        if not flag_splitting:
            for i in range(1, len(chosen_path) - 1):
                node = chosen_path[i]
                if H.nodes[node].get("role") == "candidate":
                    next_hop_to_cc.setdefault(node, chosen_path[i + 1])

        # store (compatibile con draw_graph)
        pmu_paths[pmu] = {"path": chosen_path, "delay": chosen_delay}
        accepted_delays.append(chosen_delay)

        for node in chosen_path:
            if H.nodes[node].get("role") == "candidate":
                pdcs.add(node)

    max_delay_out = max(accepted_delays) if accepted_delays else 0.0
    return pdcs, pmu_paths, max_delay_out







def place_pdcs_random(G, max_latency, seed=None):
        if seed is not None:
            random.seed(seed)

        pdcs = set()
        pmu_paths = {}
        bandwidth_usage = {}  # (u, v) → traffico cumulativo

        pmu_nodes = [n for n in G.nodes if G.nodes[n].get("role") == "PMU"]

        def dfs_random_path(current, target, visited, data_rate):
            if current == target:
                return [current]

            visited.add(current)
            neighbors = list(G.neighbors(current))
            random.shuffle(neighbors)

            for neighbor in neighbors:
                if neighbor in visited:
                    continue
                if G.nodes[neighbor].get("role") == "PMU":
                    continue
                if G.nodes[neighbor].get("status") != "online":
                    continue
                if G[current][neighbor].get("status") != "up":
                    continue

                edge = (current, neighbor) if (current, neighbor) in G.edges else (neighbor, current)
                capacity = G.edges[edge].get("bandwidth", float("inf"))
                usage = bandwidth_usage.get(edge, 0)
                if usage + data_rate > capacity:
                    print(f"⚠️ Arco {current}–{neighbor} saturato: {usage + data_rate} kbps > {capacity} kbps")
                    continue

                print(f"✅ Arco {current}–{neighbor} OK: {usage + data_rate} ≤ {capacity} kbps")
                path = dfs_random_path(neighbor, target, visited, data_rate)
                if path:
                    return [current] + path

            visited.remove(current)
            return None

        for pmu in pmu_nodes:
            data_rate = G.nodes[pmu].get("data_rate", 0)

            path = dfs_random_path(pmu, "CC", set(), data_rate)
            if path is None:
                print(f"⚠️ Nessun cammino valido per {pmu} → CC (nodi down o banda saturata).")
                continue

            # Calcola ritardo
            total_delay = 0.0
            for i in range(len(path) - 1):
                u, v = path[i], path[i + 1]
                total_delay += G[u][v]["latency"]
                if G.nodes[u].get("role") == "candidate":
                    total_delay += G.nodes[u].get("processing", 0)

                # Aggiorna uso della banda con data_rate della PMU sorgente
                edge = (u, v) if (u, v) in G.edges else (v, u)
                bandwidth_usage[edge] = bandwidth_usage.get(edge, 0) + data_rate
                print(f"📶 Arco {u}–{v} aggiornato: {bandwidth_usage[edge]} / {G.edges[edge]['bandwidth']} kbps")

            pmu_paths[pmu] = {"path": path, "delay": total_delay}
            for node in path[1:-1]:
                if G.nodes[node].get("role") not in {"PMU", "CC"}:
                    pdcs.add(node)

        # Trova ritardo massimo
        if pmu_paths:
            max_pmu = max(pmu_paths.items(), key=lambda x: x[1]["delay"])
            max_delay = max_pmu[1]["delay"]
            max_path = max_pmu[1]["path"]

            print("\n🎲 Cammini PMU → CC e ritardi:")
            for pmu, data in pmu_paths.items():
                print(f"  {pmu} → CC: {data['path']} | Ritardo = {data['delay']:.2f} ms")

            print()
            if max_delay > max_latency:
                print(f"⚠️ Ritardo massimo {max_delay:.2f} ms supera la soglia {max_latency} ms.")
                print(f"   Causato dal path: {max_pmu[0]} → CC = {max_path}")
            else:
                print(f"✅ Ritardo massimo {max_delay:.2f} ms sotto la soglia {max_latency} ms.")
        else:
            print("❌ Nessun path valido trovato da alcun PMU al CC.")

        return (pdcs, pmu_paths, max_latency)
    
    

from itertools import combinations, product

def place_pdcs_bruteforce(G, max_latency, flag_splitting=True, max_paths_per_pmu=None):
    def is_valid_chain(path, pdc_nodes, G):
        if not path:
            return False
        node_role = [G.nodes[n].get("role") for n in path]
        if node_role[0] != "PMU" or node_role[-1] != "CC":
            return False
        for i in range(1, len(path) - 1):
            if path[i] not in pdc_nodes:
                return False
            if not G.nodes[path[i]].get("online", True):
                return False
        for u, v in zip(path, path[1:]):
            if not G.has_edge(u, v) and not G.has_edge(v, u):
                return False
            # check status irrespective of direction
            e = (u, v) if (u, v) in G.edges else (v, u)
            if G[e[0]][e[1]].get("status", "up") != "up":
                return False
        return True

    def compute_path_latency(path, G, pdc_nodes):
        latency = 0
        for u, v in zip(path, path[1:]):
            e = (u, v) if (u, v) in G.edges else (v, u)
            latency += G[e[0]][e[1]].get("latency", 0)
        for n in path:
            if n in pdc_nodes:
                latency += G.nodes[n].get("processing", 0)
        return latency

    def check_splitting(pdc_nodes, pmu_paths):
        # return True if existe splitting (divergence) on some shared PDC
        pdc_to_pmus = {}
        for pmu, data in pmu_paths.items():
            path = data["path"]
            for n in path[1:-1]:
                if n in pdc_nodes:
                    pdc_to_pmus.setdefault(n, []).append(pmu)

        for pdc, pmus in pdc_to_pmus.items():
            if len(pmus) > 1:
                ref_path = None
                for pmu in pmus:
                    path = pmu_paths[pmu]["path"]
                    idx = path.index(pdc)
                    sub_path = path[idx:]  # path from pdc to cc
                    if ref_path is None:
                        ref_path = sub_path
                    elif ref_path != sub_path:
                        # splitting detected
                        # print(f"❌ Splitting detected at PDC {pdc} for PMUs {pmus}")
                        return True
        return False

    pmu_nodes = [n for n, d in G.nodes(data=True) if d.get("role") == "PMU"]
    candidate_nodes = [n for n, d in G.nodes(data=True) if d.get("role") == "candidate"]
    cc_nodes = [n for n, d in G.nodes(data=True) if d.get("role") == "CC"]
    if not cc_nodes:
        raise ValueError("No CC node found in G")
    cc_node = cc_nodes[0]

    best_config = None
    best_total_latency = float('inf')
    best_paths = {}
    best_bandwidth_usage = {}

    # iterate over all combinations of PDC
    for k in range(1, len(candidate_nodes) + 1):
        for pdc_nodes in combinations(candidate_nodes, k):
            pdc_nodes = set(pdc_nodes)
            # for each PMU calculate the set of possible paths in the subgraph limited to allowed nodes
            pmu_to_paths = {}
            valid_combination_of_pdc = True
            for pmu in pmu_nodes:
                allowed_nodes = set(pdc_nodes) | {pmu, cc_node}
                subgraph = nx.Graph()
                for u in allowed_nodes:
                    subgraph.add_node(u, **G.nodes[u])
                for u, v in G.edges():
                    if u in allowed_nodes and v in allowed_nodes:
                        if G[u][v].get("status", "up") == "up":
                            subgraph.add_edge(u, v, **G[u][v])
                # take all simple paths from pmu to cc_node
                try:
                    all_paths = list(nx.all_simple_paths(subgraph, source=pmu, target=cc_node, cutoff=5))
                    # optionally sort by latency and/or limit the number of paths
                    all_paths_sorted = sorted(all_paths, key=lambda p: compute_path_latency(p, G, pdc_nodes))
                    if max_paths_per_pmu is not None:
                        all_paths_sorted = all_paths_sorted[:max_paths_per_pmu]
                    # if no possible paths, the combination of PDC is not valid
                    if not all_paths_sorted:
                        valid_combination_of_pdc = False
                        break
                    pmu_to_paths[pmu] = all_paths_sorted
                except nx.NetworkXNoPath:
                    valid_combination_of_pdc = False
                    break

            if not valid_combination_of_pdc:
                continue

            # now generate all Cartesian combinations of paths (one choice per PMU)
            pmu_list = list(pmu_nodes)
            paths_product_iter = product(*(pmu_to_paths[pmu] for pmu in pmu_list))

            for paths_choice in paths_product_iter:
                # build current_path from the product
                current_path = {}
                for pmu, path in zip(pmu_list, paths_choice):
                    current_path[pmu] = {"path": path}

                # check that each path is a valid chain (PMU -> PDC* -> CC)
                valid_paths = True
                for pmu, data in current_path.items():
                    if not is_valid_chain(data["path"], pdc_nodes, G):
                        valid_paths = False
                        break
                if not valid_paths:
                    continue

                # check splitting if not allowed
                if not flag_splitting:
                    if check_splitting(pdc_nodes, current_path):
                        continue  # discard this combination of paths

                # check bandwidth: accumulate usage on edges
                bandwidth_usage = {}
                bandwidth_ok = True
                for pmu in pmu_list:
                    data_rate = G.nodes[pmu].get("data_rate", 0)
                    path = current_path[pmu]["path"]
                    for u, v in zip(path, path[1:]):
                        edge = (u, v) if (u, v) in G.edges else (v, u)
                        cap = G.edges[edge].get("bandwidth", float("inf"))
                        usage = bandwidth_usage.get(edge, 0)
                        if usage + data_rate > cap:
                            bandwidth_ok = False
                            break
                    if not bandwidth_ok:
                        break
                    # if ok, update usage (but only after verification for this pmu)
                    for u, v in zip(path, path[1:]):
                        edge = (u, v) if (u, v) in G.edges else (v, u)
                        bandwidth_usage[edge] = bandwidth_usage.get(edge, 0) + G.nodes[pmu].get("data_rate", 0)

                if not bandwidth_ok:
                    continue

                # calculate total latency for this combination of paths
                total_latency = 0
                for pmu in pmu_list:
                    path = current_path[pmu]["path"]
                    latency = compute_path_latency(path, G, pdc_nodes)
                    current_path[pmu]["delay"] = latency
                    total_latency += latency

                # possible constraint on max_latency: if you want to apply it per single PMU or total, adapt here.
                # here we keep the previous logic: optimize the sum of latencies
                if total_latency < best_total_latency:
                    best_config = list(pdc_nodes)
                    best_total_latency = total_latency
                    best_paths = current_path.copy()
                    best_bandwidth_usage = bandwidth_usage.copy()

    # output as before
    if best_config:
        print("\n📍 Best PMU → CC paths with optimal PDC configuration:")
        for pmu, data in best_paths.items():
            path = data["path"]
            delay = data["delay"]
            print(f"{pmu} → CC: {' → '.join(path)}, Delay = {delay:.2f} ms")
            print(f"Bandwidth used for each edge:")
            for u, v in zip(path, path[1:]):
                edge = (u, v) if (u, v) in G.edges else (v, u)
                usage = best_bandwidth_usage.get(edge) or best_bandwidth_usage.get((edge[1], edge[0]), 0)
                print(f"  {u}–{v}: {usage} kbps")
    else:
        print("❌ No valid configuration found.")

    return best_config if best_config else [], best_paths, max_latency




def q_learning_placement(G, max_latency, episodes=25000, alpha=0.1, gamma=0.9, epsilon=0.8, seed=None, verbose=False):
    
    if seed is not None:
        random.seed(seed)
        np.random.seed(seed)

    nodes_pdc = [n for n, data in G.nodes(data=True)
                 if data.get("role") == "candidate" and data.get("status") == "online"]
    pmu_nodes = [n for n, data in G.nodes(data=True) if data.get("role") == "PMU"]

    num_actions = len(nodes_pdc)
    Q = np.zeros((2 ** num_actions, num_actions)) # inizializzazione Q-table

    def compute_total_delay(path): # calcola il ritardo totale di un path
        delay = 0.0
        for u, v in zip(path, path[1:]):
            delay += G[u][v]["latency"]
        for node in path[1:-1]:
            delay += G.nodes[node].get("processing", 0)
        return delay
    
    # def valid_path(path, state):# controlla che ci siano solo PDC online e archi up
    #     for node in path[1:-1]:
    #         if node not in nodes_pdc:
    #             return False
    #         idx = nodes_pdc.index(node)
    #         if state[idx] != 1:  # se nodo è candidato ma non attivo ( da state[idx] )
    #             return False
    #     for u, v in zip(path, path[1:]): # se qualche arco nel path non è attivo
    #         if G[u][v].get("status") != "up":
    #             return False
    #     if any(G.nodes[n].get("status") != "online" for n in path):
    #         return False
    #     return True
    
    def valid_path(path, state, bandwidth_usage, data_rate):
        # Verifica nodi intermedi PDC attivi
        for node in path[1:-1]:
            if node not in nodes_pdc:
                return False
            idx = nodes_pdc.index(node)
            if state[idx] != 1:
                return False
        # Verifica stato archi e nodi + saturazione banda
        for u, v in zip(path, path[1:]):
            if G[u][v].get("status") != "up":
                return False
            edge = (u, v) if (u, v) in G.edges else (v, u)
            capacity = G.edges[edge].get("bandwidth", float("inf"))
            usage = bandwidth_usage.get(edge, 0)
            if usage + data_rate > capacity:
                return False
        if any(G.nodes[n].get("status") != "online" for n in path):
            return False
        return True


    
    def find_best_paths(state):
        pmu_to_best = {}
        bandwidth_usage = {}
        for pmu in pmu_nodes:
            data_rate = G.nodes[pmu].get("data_rate", 0)
            best_path = None
            best_delay = float("inf")
            try:
                paths = islice(nx.all_simple_paths(G, pmu, "CC", cutoff=15), 500)
                for path in paths:
                    if not valid_path(path, state, bandwidth_usage, data_rate):
                        continue
                    delay = compute_total_delay(path)
                    if delay < best_delay:
                        best_delay = delay
                        best_path = path
            except nx.NetworkXNoPath:
                continue
            if best_path:
                pmu_to_best[pmu] = {"path": best_path, "delay": best_delay}
                for u, v in zip(best_path, best_path[1:]):
                    edge = (u, v) if (u, v) in G.edges else (v, u)
                    bandwidth_usage[edge] = bandwidth_usage.get(edge, 0) + data_rate
        return pmu_to_best


    def state_to_index(state):
        return int("".join(str(b) for b in state), 2)

    best_state = None
    best_score = -float("inf")

    for ep in range(episodes):
        if ep % 1000 == 0: print(f"🔄 Episodio {ep}/{episodes}...")
        state = [0] * num_actions
        pmu_covered = set()

        for step in range(num_actions): # ad ogni step, si attiva un PDC
            s_idx = state_to_index(state) # converte lo stato in indice per Q-table
            available = [i for i in range(num_actions) if state[i] == 0] # seleziona i PDC ancora spenti
            if not available:
                break

            if random.random() < epsilon:
                action = random.choice(available)
            else:
                q_values = Q[s_idx]
                q_masked = [q if i in available else -np.inf for i, q in enumerate(q_values)]
                action = int(np.argmax(q_masked))

            state[action] = 1

            best_paths = find_best_paths(state)
            new_covered = set(best_paths.keys()) # nuove PMU coperte
            delta_covered = len(new_covered - pmu_covered)
            pmu_covered = new_covered

            total_delay = sum(data["delay"] for data in best_paths.values())

            pdc_count = sum(state)

            reward = (
                +20 * delta_covered
                - 1.0 * total_delay / 100
                - 3 * pdc_count
            )


            next_s_idx = state_to_index(state)
            Q[s_idx, action] += alpha * (reward + gamma * np.max(Q[next_s_idx]) - Q[s_idx, action])

            if verbose:
                print(f"[Ep{ep:4d}][St{step}] ΔPMU={delta_covered}, delay={total_delay:.1f}, PDCs={pdc_count}, R={reward:.2f}")

            # if len(pmu_covered) == len(pmu_nodes): # tutte le PMU sono coperte
            #     break

        # finito l'episodio, calcola il punteggio per quell'episodio ( il Q-value valuta l'action effettuato )
        final_paths = find_best_paths(state)
        total_delay = sum(data["delay"] for data in final_paths.values())
        pdc_count = sum(state)
        latency_avg = total_delay / len(final_paths) if final_paths else float('inf')
        # Conta i PDC attivi ma non usati nei path
        used_pdcs = set()
        for data in final_paths.values():
            path = data["path"]
            for node in path[1:-1]:
                used_pdcs.add(node)

        useless_pdc_count = sum(
            1 for i, b in enumerate(state)
            if b == 1 and nodes_pdc[i] not in used_pdcs
        )

        final_score = (
            1000 * len(final_paths) 
            - 5 * latency_avg 
            - 20 * pdc_count
            - 50 * useless_pdc_count  # penalità forte per sprechi
        )


        #final_score = 1000 * len(final_paths) - total_delay - 20 * pdc_count

        if final_score > best_score:
            best_score = final_score
            best_state = state.copy()

    # Esito finale
    # selected_pdc = {nodes_pdc[i] for i, b in enumerate(best_state) if b == 1}
    # print("\n Politica appresa:")
    # print(f" Stato binario: {''.join(str(b) for b in best_state)}")
    # print(f" Nodi PDC selezionati: {selected_pdc}")
    # 🔎 Ricava i PDC usati nei cammini finali
    used_pdcs = set()
    for data in final_paths.values():
        path = data["path"]
        for node in path[1:-1]:  # solo nodi intermedi tra PMU e CC
            used_pdcs.add(node)


    # 🧼 Pulisci best_state per mantenere solo i PDC usati
    clean_best_state = [0] * len(nodes_pdc)
    for i, n in enumerate(nodes_pdc):
        if best_state[i] == 1 and n in used_pdcs:
            clean_best_state[i] = 1
    best_state = clean_best_state
    
    selected_pdc = {nodes_pdc[i] for i, b in enumerate(best_state) if b == 1}


    print("\n📡 Cammini PMU → CC (validi con PDC selezionati):")
    final_paths = find_best_paths(best_state)
    for pmu in pmu_nodes:
        if pmu in final_paths:
            path = final_paths[pmu]["path"]
            delay = final_paths[pmu]["delay"]

            status = " OK" if delay <= max_latency else f" Ritardo {delay:.2f} ms > soglia"
            print(f"  {pmu} → CC: {path} | Ritardo = {delay:.2f} ms {status}")
        else:
            print(f"  {pmu} → CC:  Nessun path valido")

    return selected_pdc, final_paths, max_latency if selected_pdc else None





