import csv
import matplotlib.pyplot as plt

def plot_topology_metrics(csv_path):
    T, churn_y, jd_y = [], [], []

    with open(csv_path, "r") as f:
        reader = csv.DictReader(f)
        for r in reader:
            T.append(int(r["T"]))
            churn_y.append(float(r["churn"]))
            jd_y.append(float(r["jaccard_distance"]))

    if not T:
        print("⚠️ No metrics to plot.")
        return

    plt.figure()
    plt.plot(T, churn_y, marker="o")
    plt.xlabel("T (topology change index)")
    plt.ylabel("Topo churn")
    plt.grid(True)

    plt.figure()
    plt.plot(T, jd_y, marker="o")
    plt.xlabel("T (topology change index)")
    plt.ylabel("1 - Jaccard similarity")
    plt.grid(True)

    plt.show()
