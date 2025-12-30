import networkx as nx
import random
import numpy as np
from itertools import islice
from itertools import combinations

def place_pdcs_greedy(G, max_latency, flag_splitting=False):
    if flag_splitting:
        pdcs = set()
        pmu_paths = {}
        bandwidth_usage = {}  # (u, v) -> banda usata corrente (kbps)
        edge_flow = {}        # (u, v) -> elenco di PMU che usano l’arco

        # --- Funzioni di supporto ---
        def path_valid(path, extra_rate):
            for u, v in zip(path, path[1:]):
                edge = (u, v) if (u, v) in G.edges else (v, u)
                capacity = G.edges[edge].get("bandwidth", float("inf"))
                usage = bandwidth_usage.get(edge, 0)
                if usage + extra_rate > capacity:
                    return False
            return True

        def update_bandwidth(path, rate, pmu):
            for u, v in zip(path, path[1:]):
                edge = (u, v) if (u, v) in G.edges else (v, u)
                bandwidth_usage[edge] = bandwidth_usage.get(edge, 0) + rate
                edge_flow.setdefault(edge, []).append(pmu)

        # --- Identifica tutte le PMU ---
        pmu_nodes = [n for n in G.nodes if G.nodes[n].get("role") == "PMU"]

        # --- Algoritmo Greedy ---
        for pmu in pmu_nodes:
            found = False
            rate = G.nodes[pmu].get("data_rate", 0)

            print(f"\n🔍 Analyzing {pmu} (rate={rate} kbps):")

            try:
                all_paths = nx.shortest_simple_paths(G, source=pmu, target="CC", weight="latency")
            except nx.NetworkXNoPath:
                print(f"❌ No path available from {pmu} to CC.")
                continue

            for path in all_paths:
                # controllo stato nodi/archi
                if not all(G.nodes[n].get("status", "online") == "online" for n in path):
                    continue
                if not all(G[u][v].get("status", "up") == "up" for u, v in zip(path, path[1:])):
                    continue

                # controllo banda
                if path_valid(path, extra_rate=rate):
                    update_bandwidth(path, rate, pmu)
                    found = True

                    # Calcola latenze: archi + processing solo per PDC
                    total_latency = 0.0
                    total_latency += sum(G[u][v]["latency"] for u, v in zip(path, path[1:]))
                    for node in path[1:-1]:  # escludi PMU e CC
                        if G.nodes[node].get("role") not in {"PMU", "CC"}:
                            total_latency += G.nodes[node].get("processing", 0)
                            pdcs.add(node)

                    pmu_paths[pmu] = {"path": path, "delay": total_latency}

                    print(f"✅ Path found for {pmu}: {path} (delay={total_latency:.2f} ms)")
                    break
                else:
                    print(f"⚠️ Insufficient bandwidth on {path}, trying next...")

            if not found:
                print(f"❌ No valid path found for {pmu}.")

        # --- Output finale ---
        print("\n📡 Final paths PMU → CC:")
        for pmu, data in pmu_paths.items():
            print(f"  {pmu} → CC: {data['path']} | Total delay: {data['delay']:.2f} ms")

        if pmu_paths:
            max_pmu, max_data = max(pmu_paths.items(), key=lambda x: x[1]["delay"])
            if max_data["delay"] > max_latency:
                print(f"\n⚠️ Maximum delay {max_data['delay']:.2f} ms exceeds threshold {max_latency} ms (PMU: {max_pmu})")
            else:
                print(f"\n✅ All paths under threshold {max_latency} ms.")
        else:
            print("\n⚠️ No valid path found.")

        return pdcs, pmu_paths, max_latency
    else:
        pmu_paths = {}        # {pmu: {"path": [...], "delay": ...}}
        pdcs = set()          
        bandwidth_usage = {}  
        pdc_to_pmus = {}      

        def path_valid(path, extra_rate=0):
            for u, v in zip(path, path[1:]):
                edge = (u, v) if (u, v) in G.edges else (v, u)
                cap = G.edges[edge].get("bandwidth", float("inf"))
                use = bandwidth_usage.get(edge, 0)
                if use + extra_rate > cap:
                    return False
            return True

        def update_bandwidth(path, rate):
            for u, v in zip(path, path[1:]):
                edge = (u, v) if (u, v) in G.edges else (v, u)
                bandwidth_usage[edge] = bandwidth_usage.get(edge, 0) + rate

        def compute_delay(path):
            delay = sum(G[u][v]["latency"] for u, v in zip(path, path[1:]))
            for node in path[1:-1]:
                if G.nodes[node].get("role") not in {"PMU", "CC"}:
                    delay += G.nodes[node].get("processing", 0)
            return delay

        def find_common_pdc(path):
            for pmu, data in pmu_paths.items():
                for node in path[1:-1]:
                    if node in data["path"][1:-1] and G.nodes[node].get("role") not in {"PMU", "CC"}:
                        return node, pmu
            return None, None

        pmu_nodes = [n for n in G.nodes if G.nodes[n].get("role") == "PMU"]

        for pmu in pmu_nodes:
            rate = G.nodes[pmu].get("data_rate", 0)
            found = False
            print(f"\n🔍 Analyzing {pmu} (rate={rate} kbps):")

            try:
                all_paths = nx.shortest_simple_paths(G, source=pmu, target="CC", weight="latency")
            except nx.NetworkXNoPath:
                print(f"❌ No path available for {pmu}")
                continue

            for path in all_paths:
                # verifica stato nodi e archi
                if not all(G.nodes[n].get("status", "online") == "online" for n in path):
                    continue
                if not all(G[u][v].get("status", "up") == "up" for u, v in zip(path, path[1:])):
                    continue

                #  cerca intersezione con PDC già usati
                common_pdc, ref_pmu = find_common_pdc(path)

                if common_pdc:
                    print(f"⚠️ {pmu} converges on {common_pdc}, shared with {ref_pmu}")

                    affected_existing = {p for p, d in pmu_paths.items() if common_pdc in d["path"]}
                    affected_all = affected_existing | {pmu}
                    total_rate = sum(G.nodes[p].get("data_rate", 0) for p in affected_all)

                    try:
                        for new_tail in nx.shortest_simple_paths(G, source=common_pdc, target="CC", weight="latency"):
                            if path_valid(new_tail, total_rate):
                                print(f"✅ New valid common segment from {common_pdc}: {new_tail}")

                                #  aggiorna path delle PMU già presenti
                                for p in affected_existing:
                                    old_path = pmu_paths[p]["path"]
                                    idx = old_path.index(common_pdc)
                                    new_path = old_path[:idx] + new_tail
                                    pmu_paths[p]["path"] = new_path
                                    pmu_paths[p]["delay"] = compute_delay(new_path)

                                #  aggiungi la nuova PMU
                                try:
                                    prefix = nx.shortest_path(G, source=pmu, target=common_pdc, weight="latency")
                                    full_path = prefix + new_tail[1:]
                                    pmu_paths[pmu] = {
                                        "path": full_path,
                                        "delay": compute_delay(full_path)
                                    }
                                    print(f"✅ New PMU {pmu} added with path: {full_path}")
                                except nx.NetworkXNoPath:
                                    print(f"❌ {pmu} cannot reach {common_pdc}")
                                    continue

                                # aggiorna la banda totale
                                for p in affected_all:
                                    update_bandwidth(pmu_paths[p]["path"], G.nodes[p].get("data_rate", 0))
                                found = True
                                break

                        if not found:
                            print(f"❌ No common segment available for {common_pdc}")

                    except nx.NetworkXNoPath:
                        print(f"❌ No path from PDC {common_pdc} to CC")

                    break  # intersezione gestita, passa alla prossima PMU

                # Nessuna intersezione → controllo di banda standard
                if path_valid(path, rate):
                    update_bandwidth(path, rate)
                    total_latency = compute_delay(path)

                    # aggiungi eventuali PDC
                    for node in path[1:-1]:
                        if G.nodes[node].get("role") not in {"PMU", "CC"}:
                            pdcs.add(node)
                            pdc_to_pmus.setdefault(node, set()).add(pmu)

                    pmu_paths[pmu] = {"path": path, "delay": total_latency}
                    print(f"✅ Path valid for {pmu}: {path} (delay={total_latency:.2f} ms)")
                    found = True
                    break

            if not found:
                print(f"❌ No valid path found for {pmu}")

        # --- Output finale ---
        print("\n📡 Final PMU → CC paths:")
        for pmu, data in pmu_paths.items():
            print(f"  {pmu} → {data['path']} | Total latency = {data['delay']:.2f} ms")

        if pmu_paths:
            max_pmu, max_data = max(pmu_paths.items(), key=lambda x: x[1]["delay"])
            if max_data["delay"] > max_latency:
                print(f"\n⚠️ Maximum latency {max_data['delay']:.2f} ms exceeds threshold {max_latency} ms (PMU: {max_pmu})")
            else:
                print(f"\n✅ All paths under threshold {max_latency} ms.")
        else:
            print("\n⚠️ No valid path found.")

        pdcs = set()
        pdc_to_pmus = {}

        for pmu, data in pmu_paths.items():
            path = data["path"]
            for node in path[1:-1]:
                if G.nodes[node].get("role") not in {"PMU", "CC"}:
                    pdcs.add(node)
                    pdc_to_pmus.setdefault(node, set()).add(pmu)

        return pdcs, pmu_paths, max_latency



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





