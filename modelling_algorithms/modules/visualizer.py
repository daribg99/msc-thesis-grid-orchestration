import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import Patch

def draw_graph(G, pdcs=None, paths=None, max_latency=None):
    if pdcs is None:
        pdcs = set()

    plt.figure(figsize=(14, 10))

    try:
        pos = nx.nx_pydot.pydot_layout(G, prog="dot")
    except Exception:
        print("⚠️ Error with pydot layout, using spring layout instead.")
        pos = nx.spring_layout(G, seed=42)

    edge_labels = nx.get_edge_attributes(G, "latency")
    node_colors = []
    node_labels = {}
    node_edgecolors = []

    for n in G.nodes:
        role = G.nodes[n].get("role")
        label = n

        if n in pdcs:
            color = "orange"
            label += f"\n{G.nodes[n].get('processing', 0)}"
            edge_color = "black"
        elif role == "CC":
            color = "red"
            label += "\n(CC)"
            edge_color = "black"
        elif role == "PMU":
            color = "lightgreen"
            label += "\n(PMU)"
            edge_color = "black"
        else:
            color = "lightblue"
            edge_color = "gray"

        node_colors.append(color)
        node_labels[n] = label
        node_edgecolors.append(edge_color)

    nx.draw_networkx_nodes(G, pos,
                           node_color=node_colors,
                           edgecolors=node_edgecolors,
                           node_size=1100,
                           linewidths=1.8)

    # Disegna tutti gli archi base in grigio
    nx.draw_networkx_edges(G, pos, width=1.2, edge_color="lightgray")
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=8)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, label_pos=0.5)

    # Colori diversi per ogni path PMU → CC
    if paths:
        colors = [
            "crimson", "darkgreen", "royalblue", "goldenrod",
            "purple", "darkorange", "deeppink", "teal", "brown"
        ]
        color_map = {}

        for i, (pmu, data) in enumerate(paths.items()):
            path = data["path"]
            delay = data["delay"]
            color = colors[i % len(colors)]
            color_map[pmu] = color
            edges = list(zip(path, path[1:]))

            nx.draw_networkx_edges(G, pos,
                                   edgelist=edges,
                                   width=2.8,
                                   edge_color=color)

        # Testo con le latenze
        text = "Latency PMU → CC:\n"
        text += "Max latency: " + str(max_latency) + " ms\n"
        for pmu, data in paths.items():
            delay = data["delay"]            
            text += f"{pmu} → CC: {delay:.2f} ms"
            if max_latency is not None and delay > max_latency:
                text += f" ⚠️\n"
            else:
                text += " ✔️\n"

        plt.gcf().text(0.05, 0.85, text, fontsize=9, verticalalignment='top',
                       bbox=dict(facecolor='white', edgecolor='black', boxstyle='round,pad=0.5'))

    # Legenda
    legend_elements = [
        Patch(facecolor="red", edgecolor="black", label="CC"),
        Patch(facecolor="lightgreen", edgecolor="black", label="PMU"),
        Patch(facecolor="orange", edgecolor="black", label="PDC (assigned)"),
        Patch(facecolor="lightblue", edgecolor="gray", label="Other Nodes"),
    ]
    plt.legend(handles=legend_elements, loc="lower left", fontsize=9, frameon=True)

    plt.title("Graph with role and selected path", fontsize=12)
    plt.axis("off")
    plt.tight_layout()
    plt.savefig("graph.png", dpi=300, bbox_inches="tight")
    plt.show(block=False)
    plt.close()



