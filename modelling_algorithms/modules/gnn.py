import networkx as nx


def compute_path_latency(G, path):
    latency = 0
    for i in range(len(path) - 1):
        edge = G[path[i]][path[i + 1]]
        if edge.get("status") != "up":
            return float("inf")
        latency += edge.get("latency", 0)

    for node in path:
        if G.nodes[node].get("role") == "candidate":
            if G.nodes[node].get("status") != "online":
                return float("inf")
            latency += G.nodes[node].get("processing", 0)

    return latency


def is_valid_chain(G, chain, pmu, cc):
    if not chain:
        return False
    if chain[0] not in G.neighbors(pmu):
        return False
    if chain[-1] not in G.neighbors(cc):
        return False

    for i in range(len(chain) - 1):
        if not G.has_edge(chain[i], chain[i + 1]):
            return False
        if G[chain[i]][chain[i + 1]].get("status") != "up":
            return False

    return True


def find_best_paths(G, pmus, cc, pdcs, max_latency):
    valid_paths = {}

    for pmu in pmus:
        best_path = None
        best_delay = float("inf")

        # se non ho PDC, non posso trovare path "a catena"
        if not pdcs:
            continue

        try:
            # subgraph con PMU, CC e PDC selezionati
            subgraph = G.subgraph(pdcs.union({pmu, cc}))
            path = nx.shortest_path(subgraph, source=pmu, target=cc, weight="latency")

            # chain = nodi intermedi (esclusi pmu e cc)
            chain = path[1:-1]
            if not is_valid_chain(G, chain, pmu, cc):
                continue

            delay = compute_path_latency(G, path)

            if delay <= max_latency:
                best_path = path
                best_delay = delay

        except Exception:
            continue

        if best_path is not None:
            valid_paths[pmu] = (best_path, best_delay)

    return valid_paths


def train_with_policy_gradient(G, max_latency, episodes=5000, max_pdcs=15, temperature=0.5):
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    import torch.optim as optim
    from torch_geometric.utils import from_networkx
    from torch_geometric.nn import GCNConv

    class GraphPolicyNetwork(nn.Module):
        def __init__(self, in_channels, hidden_channels):
            super().__init__()
            self.conv1 = GCNConv(in_channels, hidden_channels)
            self.conv2 = GCNConv(hidden_channels, hidden_channels)
            self.out = nn.Linear(hidden_channels, 1)

        def forward(self, x, edge_index):
            x = F.relu(self.conv1(x, edge_index))
            x = F.relu(self.conv2(x, edge_index))
            logits = self.out(x).squeeze(-1)
            probs = F.softmax(logits / temperature, dim=0)
            return probs

    # --- node features ---
    role_encoding = {"PMU": [1, 0, 0], "CC": [0, 1, 0], "candidate": [0, 0, 1]}
    for n, d in G.nodes(data=True):
        role = d.get("role", "candidate")
        d["x"] = role_encoding.get(role, [0, 0, 1])

    # --- torch_geometric data ---
    data = from_networkx(G)
    data.x = torch.tensor([G.nodes[n]["x"] for n in G.nodes()], dtype=torch.float)

    pmus = [n for n, d in G.nodes(data=True) if d.get("role") == "PMU"]
    cc_nodes = [n for n, d in G.nodes(data=True) if d.get("role") == "CC"]
    if not cc_nodes:
        raise ValueError("No CC node found in graph (role == 'CC').")
    cc = cc_nodes[0]

    model = GraphPolicyNetwork(in_channels=3, hidden_channels=16)
    optimizer = optim.Adam(model.parameters(), lr=0.01)

    best_pdcs = set()
    best_latency = float("inf")

    nodes_list = list(G.nodes())

    for episode in range(episodes):
        pdcs = set()
        log_probs = []
        valid_episode = True

        for _ in range(max_pdcs):
            probs = model(data.x, data.edge_index)
            mask = torch.ones_like(probs)

            for i, n in enumerate(nodes_list):
                node = G.nodes[n]

                if node.get("role") in {"PMU", "CC"} or n in pdcs:
                    mask[i] = 0

                elif pdcs:
                    if not any(
                        (neigh in pdcs) or (neigh in pmus) or (neigh == cc)
                        for neigh in G.neighbors(n)
                    ):
                        mask[i] = 0

                if node.get("status") != "online":
                    mask[i] = 0

            masked_probs = probs * mask
            total = masked_probs.sum()

            if total.item() <= 0.0 or torch.isnan(total):
                valid_episode = False
                break

            masked_probs = masked_probs / total
            m = torch.distributions.Categorical(masked_probs)
            action_idx = m.sample()
            action_node = nodes_list[action_idx.item()]

            pdcs.add(action_node)
            log_probs.append(m.log_prob(action_idx))

        if not valid_episode:
            continue

        best_paths = find_best_paths(G, pmus, cc, pdcs, max_latency)

        # reward
        if len(best_paths) < len(pmus):
            reward = -100.0
        else:
            total_delay = sum(delay for _, delay in best_paths.values())
            reward = -float(total_delay) - len(pdcs) * 3.0

            if total_delay < best_latency:
                best_latency = total_delay
                best_pdcs = pdcs.copy()

        # update policy
        if episode >= 10 and log_probs:
            loss = -torch.stack(log_probs).sum() * torch.tensor(reward)
            optimizer.zero_grad()
            loss.backward()
            optimizer.step()

        if (episode + 1) % 1000 == 0:
            print(f"[Ep {episode+1}] Reward: {reward:.2f}  BestLatency: {best_latency:.2f}  BestPDCs: {len(best_pdcs)}")

    print("\n✅ Migliori PDC selezionati:", best_pdcs)
    final_paths = find_best_paths(G, pmus, cc, best_pdcs, max_latency)
    for pmu, (path, delay) in final_paths.items():
        print(f"  {pmu} → CC: {path} | Delay = {delay:.2f} ms")

    return best_pdcs
