import matplotlib
import matplotlib.pyplot as plt
import networkx as nx
from matplotlib.patches import Patch
from pathlib import Path


def draw_graph(G, pdcs=None, paths=None, max_latency=None, output_path: Path | None = None):
   
    if pdcs is None:
        pdcs = set()

    if output_path is None:
        output_path = Path("runtime_results") / "graph.png"
    else:
        output_path = Path(output_path)

    output_path.parent.mkdir(parents=True, exist_ok=True)

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

    nx.draw_networkx_nodes(
        G,
        pos,
        node_color=node_colors,
        edgecolors=node_edgecolors,
        node_size=1100,
        linewidths=1.8,
    )

    nx.draw_networkx_edges(G, pos, width=1.2, edge_color="lightgray")
    nx.draw_networkx_labels(G, pos, labels=node_labels, font_size=8)
    nx.draw_networkx_edge_labels(G, pos, edge_labels=edge_labels, font_size=7, label_pos=0.5)

    # Highlight each PMU -> CC path with a different color
    if paths:
        colors = [
            "crimson", "darkgreen", "royalblue", "goldenrod",
            "purple", "darkorange", "deeppink", "teal", "brown"
        ]

        for i, (pmu, data) in enumerate(paths.items()):
            path = data["path"]
            color = colors[i % len(colors)]
            edges = list(zip(path, path[1:]))

            nx.draw_networkx_edges(
                G,
                pos,
                edgelist=edges,
                width=2.8,
                edge_color=color,
            )

        # Text box with PMU -> CC delays
        all_pmus = [n for n in G.nodes if G.nodes[n].get("role") == "PMU"]
        text = "Latency PMU → CC:\n"
        if max_latency is not None:
            text += f"Max required latency: {float(max_latency):.2f} ms\n"
        else:
            text += "Max required latency: N/A\n"

        for pmu in all_pmus:
            if pmu in paths:
                delay = paths[pmu].get("delay", None)
                if delay is not None:
                    text += f"{pmu} → CC: {float(delay):.2f} ms ✔️\n"
                else:
                    text += f"{pmu} → CC: delay N/A\n"
            else:
                text += f"{pmu} → CC: no path available ✗\n"

        plt.gcf().text(
            0.05, 0.85, text,
            fontsize=9,
            verticalalignment="top",
            bbox=dict(facecolor="white", edgecolor="black", boxstyle="round,pad=0.5"),
        )

    # Legend
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

    plt.savefig(output_path, dpi=300, bbox_inches="tight")

    backend = matplotlib.get_backend().lower()
    if backend not in {"agg", "pdf", "ps", "svg"}:
        plt.show(block=False)
    else:
        print(
            f"ℹ️  Matplotlib backend '{backend}' is non-interactive.\n"
            f"   Graph saved to \"{output_path}\"."
        )

    plt.close()





