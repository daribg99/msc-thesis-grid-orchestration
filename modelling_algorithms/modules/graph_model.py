import networkx as nx
import random

def create_graph(
    num_candidates=8,
    num_pmus=3,
    seed=None,
    p_extra=0.35,          # probabilità di aggiungere archi extra tra candidati
    cc_min_links=2,        # minimo collegamenti CC->candidati
    cc_max_links=None,     # massimo collegamenti CC->candidati (None = fino a num_candidates)
    pmu_links=1            # collegamenti per ogni PMU verso candidati
):
    if seed is not None:
        random.seed(seed)

    G = nx.Graph()

    # --- Nodi ---
    G.add_node("CC", role="CC", processing=10, status="online")

    candidates = [f"N{i}" for i in range(1, num_candidates + 1)]
    for n in candidates:
        G.add_node(n, role="candidate", processing=10, status="online")

    pmus = [f"PMU{i}" for i in range(1, num_pmus + 1)]
    for p in pmus:
        G.add_node(p, role="PMU", data_rate=100, status="online")

    # helper per aggiungere archi con attributi
    def add_edge(u, v):
        if u == v or G.has_edge(u, v):
            return
        G.add_edge(
            u, v,
            latency=round(random.uniform(2, 9), 2),
            bandwidth=200,
            status="up"
        )

    # --- 1) Sottografo candidati: connesso + casuale (non full mesh) ---
    # (a) Crea prima uno "spanning tree" casuale => garantisce connettività
    shuffled = candidates[:]
    random.shuffle(shuffled)
    for i in range(1, len(shuffled)):
        u = shuffled[i]
        v = random.choice(shuffled[:i])  # collega a un nodo precedente a caso
        add_edge(u, v)

    # (b) Aggiungi archi extra con probabilità p_extra
    for i in range(len(candidates)):
        for j in range(i + 1, len(candidates)):
            if random.random() < p_extra:
                add_edge(candidates[i], candidates[j])

    # --- 2) Collega CC a un sottoinsieme casuale di candidati ---
    if cc_max_links is None:
        cc_max_links = num_candidates
    cc_min_links = max(1, min(cc_min_links, num_candidates))
    cc_max_links = max(cc_min_links, min(cc_max_links, num_candidates))

    k = random.randint(cc_min_links, cc_max_links)
    for n in random.sample(candidates, k):
        add_edge("CC", n)

    # --- 3) Collega PMU ai candidati (1 o più link ciascuna) ---
    pmu_links = max(1, min(pmu_links, num_candidates))
    for p in pmus:
        for n in random.sample(candidates, pmu_links):
            add_edge(p, n)

    return G



def modify_latency(G):
    while True:
            print("\n🔗 Actually latency:")
            for u, v, data in G.edges(data=True):
                print(f"{u} – {v}: {data['latency']} ms")

            risposta = input("\nDo you want to modify a latency? (y/n): ").lower()
            if risposta != "y":
                break

            u = input("Node 1: ").strip()
            v = input("Node 2: ").strip()

            if G.has_edge(u, v):
                try:
                    nuova_latenza = float(input(f"Enter new latency for edge {u}–{v}: "))
                    G[u][v]["latency"] = nuova_latenza
                    print(f"✔️ Latency updated for {u}–{v} to {nuova_latenza} ms.")
                except ValueError:
                    print("❌ Invalid value.")
            else:
                print("❌ The specified edge does not exist.")

def modify_edge_status(G):
    while True:
        print("\n🔗 Current edge statuses:")
        for u, v, data in G.edges(data=True):
            print(f"{u} – {v}: {data['status']}")

        risposta = input("\nDo you want to modify the status of an edge? (y/n): ").lower()
        if risposta != "y":
            break

        u = input("Node 1: ").strip()
        v = input("Node 2: ").strip()

        if G.has_edge(u, v):
            nuovo_stato = input(f"Enter new status for edge {u}–{v} (up/down): ").strip().lower()
            if nuovo_stato in ["up", "down"]:
                G[u][v]["status"] = nuovo_stato
                print(f"✔️ Status updated for {u}–{v} to {nuovo_stato}.")
            else:
                print("❌ Invalid status. Use 'up' or 'down'.")
        else:
            print("❌ The specified edge does not exist.")

def modify_bandwidth(G):
    while True:
            print("\n🔗 Current bandwidths:")
            for u, v, data in G.edges(data=True):
                print(f"{u} – {v}: {data['bandwidth']} kbps")

            risposta = input("\nDo you want to modify a bandwidth? (y/n): ").lower()
            if risposta != "y":
                break

            u = input("Node 1: ").strip()
            v = input("Node 2: ").strip()

            if G.has_edge(u, v):
                try:
                    nuova_bandwidth = float(input(f"Enter new bandwidth for edge {u}–{v}: "))
                    G[u][v]["bandwidth"] = nuova_bandwidth
                    print(f"✔️ Bandwidth updated for {u}–{v} to {nuova_bandwidth} kbps.")
                except ValueError:
                    print("❌ Invalid value.")
            else:
                print("❌ The specified edge does not exist.")