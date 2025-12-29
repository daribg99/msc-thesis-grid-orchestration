from graph_model import create_graph
from visualizer import draw_graph
from placement_pdc import place_pdcs_greedy
from placement_pdc import place_pdcs_random
from placement_pdc import place_pdcs_bruteforce
from placement_pdc import q_learning_placement
#from placement_pdc import place_pdcs_centrality
#from placement_pdc import place_pdcs_betweenness
from graph_model import modify_latency
from graph_model import modify_edge_status
from graph_model import modify_bandwidth
from gnn import train_with_policy_gradient
# Algoritmi di posizionamento: 
# place_pdcs_greedy(G, max_latency)
# place_pdcs_random(G, num_pdcs, seed=None)
# place_pdcs_centrality(G, num_pdcs)

def choose_algorithm(G):
    print("Choose a placement algorithm:")
    print("1. Greedy (with maximum latency)")
    print("2. Random (with specified number of PDCs)")
    print("3. Q-Learning")
    print("4. GNN + Policy Gradient")
    print("5. Bruteforce")
    print("6. Exit")

    choice = input("Enter your choice (1-6): ")
    if choice == "6":
        print("Exiting...")
        exit(0)
    elif choice not in ["1", "2", "3", "4", "5"]:
        print("Invalid choice. Please try again.")
        return choose_algorithm(G)
    flag_splitting = input("Enable cluster splitting? (y/n): ").lower() == 'y'
    if choice == "1":
        max_latency = int(input("Enter maximum latency (in ms): "))
        return place_pdcs_greedy(G, max_latency, flag_splitting)
    elif choice == "2":
        max_latency = int(input("Enter maximum latency (in ms): "))
        seed = int(input("Enter seed (leave empty for no seed): ") or 42)
        return place_pdcs_random(G, max_latency, seed, flag_splitting)
    elif choice == "3":
        max_latency = int(input("Enter maximum latency (in ms): "))
        return q_learning_placement(G, max_latency)
    elif choice == "4":
        max_latency = int(input("Enter maximum latency (in ms): "))
        return train_with_policy_gradient(G, max_latency)
    elif choice == "5":
        max_latency = int(input("Enter maximum latency (in ms): "))
        return place_pdcs_bruteforce(G, max_latency,flag_splitting)

def main():
    G = create_graph(seed=42)
    while True:
        modify_latency(G)
        modify_edge_status(G)
        modify_bandwidth(G)
        (pdcs,path, max_latency) = choose_algorithm(G)
        print("PDCs assigned in clusters:", pdcs)
        draw_graph(G, pdcs=pdcs, paths=path, max_latency=max_latency)

if __name__ == "__main__":
    main()
