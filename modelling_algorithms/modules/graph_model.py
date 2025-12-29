import networkx as nx
import random

import networkx as nx
import random

def create_graph(
    num_candidates=4,
    num_pmus=3,
    seed=42
):
    if seed is not None:
        random.seed(seed)

    G = nx.Graph()

    # Nodo centrale
    G.add_node(
        "CC",
        role="CC",
        processing=10,
        status="online"
    )

    # Nodi candidati N1..Nn
    for i in range(1, num_candidates + 1):
        G.add_node(
            f"N{i}",
            role="candidate",
            processing=10,
            status="online"
        )

    # PMU1..PMUm
    for i in range(1, num_pmus + 1):
        G.add_node(
            f"PMU{i}",
            role="PMU",
            data_rate=100,
            status="online"
        )

    # ---- Archi ----

    # CC collegato a tutti i candidati
    for i in range(1, num_candidates + 1):
        G.add_edge("CC", f"N{i}",
                   latency=round(random.uniform(2, 9), 2),
                   bandwidth=200,
                   status="up")

    # Catena / mesh tra candidati
    for i in range(1, num_candidates):
        G.add_edge(f"N{i}", f"N{i+1}",
                   latency=round(random.uniform(2, 9),2),
                   bandwidth=200,
                   status="up")

    # Ogni PMU collegata a un candidato casuale
    for i in range(1, num_pmus + 1):
        n = random.randint(1, num_candidates)
        G.add_edge(f"PMU{i}", f"N{n}",
                   latency=round(random.uniform(2, 9), 2),
                   bandwidth=200,
                   status="up")

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