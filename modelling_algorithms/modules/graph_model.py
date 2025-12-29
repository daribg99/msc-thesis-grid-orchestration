import networkx as nx
import random

def create_graph(seed=42):
    if seed is not None:
        random.seed(seed)
    G = nx.Graph()

    # Nodo centrale
    G.add_node("CC", group="core", level=0, processing=10, memory=32, storage=1000,
               status="online", energy=1.0, role="CC")

    # Nodi candidati (potranno diventare PDC o restare inutilizzati)
    for i in range(1, 13):
        G.add_node(f"N{i}",
                   group=random.choice(["A", "B"]),
                   level=random.choice([1, 2]),
                   #processing=random.randint(3, 6),
                   processing=10,
                   memory=random.choice([8, 16]),
                   storage=random.choice([250, 500]),
                   status="online",
                   energy=round(random.uniform(0.85, 0.95), 2),
                   role="candidate")

    # PMU (nodi foglia di livello 3)
    for i in range(1, 4):
        G.add_node(f"PMU{i}",
                   data_rate=100,
                   group="A",
                   level=3,
                   processing=1,
                   memory=2,
                   storage=64,
                   status="online",
                   energy=round(0.7 + i * 0.01, 2),
                   role="PMU")

    # Definizione archi
    edges = set([
        ("CC", "N1"), ("CC", "N2"), ("CC", "N3"),
        ("N1", "N2"), ("N2", "N3"), ("N3", "N4"),
        ("N4", "N5"), ("N5", "N6"), ("N6", "N1"),
        ("N1", "N7"), ("N2", "N8"), ("N3", "N9"),
        ("N4", "N10"), ("N5", "N11"), ("N6", "N12"),
        ("N7", "N8"), ("N8", "N9"), ("N9", "N10"),
        ("N10", "N11"), ("N11", "N12"), ("N12", "N7"),
        ("N7", "PMU1"), ("N8", "PMU2"), ("N9", "PMU3"),
        ("N5", "PMU1"), ("N4", "PMU2"), ("N3", "PMU3"),
        ("N2", "N11"), ("N6", "N9")
    ])

    for u, v in edges:
        latency = round(random.uniform(2, 9), 2)
        bandwidth = random.choice([200])  # in kbps
        status = "up"
        link_type = random.choices(["fiber", "ethernet", "wireless"], weights=[0.4, 0.4, 0.2])[0]

        G.add_edge(u, v,
                   latency=latency,
                   bandwidth=bandwidth,
                   status=status,
                   type=link_type)
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