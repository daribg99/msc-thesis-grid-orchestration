# 🚀 WORK IN PROGRESS — Thesis under development

This repository contains drafts, experiments and notes for the thesis. The work is actively in progress and will be updated regularly.

Status
- 🔧 In development
- 📅 Last updated: 24 February 2026

Folders content:
- `deploy/`: deployment for PDCs and PMUs
- `deploy_automation/`: script to automate deployment, including applier for topology-based configuration and cli for automatic configuration
- `modeling_algorithms/`: placement and visualization algorithms for PDCs
- `reinforcement-learning/`: testing RL algorithms for PDC placement 
- `runtime_results/`: storage for runtime results of experiments
- `test_functions/`: functions for testing and evaluating the algorithms, including delay applicator and plotting functions

# Configuration setup 
if you want to try one of the follwing sections, you need to follow the instructions below.
Follow this guide (paragraph advanced installation guide) in order to install the Operator [click here](https://docs.percona.com/legacy-documentation/percona-operator-for-mysql-pxc/percona-kubernetes-operator-for-pxc-1.11.0.pdf). NOTE: See the next instructions for the necessary adjustments.
Clone the repository, and follow the following steps:
On the file 'deploy/cr.yaml', you need to do the following changes:
  1) Change the name from cluster1 to cluster-db 
  2) Set allowUnsafeConfigurations: false, and
       - pxc size: 1,
       - haproxy size:1
  3) Uncomment the lines configuration |, [mysql] and add the following lines: pxc_strict_mode=permissive(to let the manager to modify the DB) and auto_increment_increment=1 (otherwise PDC can't create database)   
  6) In the haproxy sections, uncomment replicasServiceType: and put it as NodePort.

Then, you need to creare a file named 'np-svc.yaml' in the deploy/ folder with the following content:
```yaml
apiVersion: v1
kind: Service
metadata:
  name: cluster-db-haproxy-rw-nodeport
  namespace: db
spec:
  type: NodePort
  selector:
    app.kubernetes.io/component: haproxy
    app.kubernetes.io/instance: cluster-db
    app.kubernetes.io/name: percona-xtradb-cluster
  ports:
    - name: mysql-rw
      port: 3306
      targetPort: 3306
      nodePort: 30950   
```
You do not need to manually apply any Kubernetes manifests.
All required resources will be deployed automatically by the provided scripts.

Before running the deployer, copy the .env.example file and rename it to `.env`. Then edit the .env file and set the correct PERCONA_ROOT path on your machine.

This step is required because the percona-xtradb-cluster-operator directory is not included in the repository.
It contains third-party dependencies and configuration files that may include sensitive information, which cannot be committed to the repository.


Then, launch:
```bash
docker network create mc-net
```
to create the network that contains the k3d clusters. 

Now you are ready to try the deployment.

From the project root directory, it is recommended to create and activate a Python virtual environment to ensure dependency isolation and reproducibility:

```bash
python3 -m venv .venv

source .venv/bin/activate

python -m pip install -r requirements.txt
```
This guarantees that all required dependencies are installed locally without affecting your system-wide Python environment.

Finally:

```bash
python -m deploy_automation.autopdc_configurator
```
The script accept the following arguments:

- `--skip-deploy`  
  Skip the deployment phase.  
  **Default:** `true`

- `--no-skip-deploy`  
  Execute the deployment phase (sets `skip_deploy=false`).

- `--skip-delay`  
  Skip waiting/delay phases between operations.  
  **Default:** `true`

- `--no-skip-delay`  
  Enable delays between operations (sets `skip_delay=false`).

- `--num-candidates <int>`  
  Number of **candidate nodes** in the generated graph.  
  **Default:** `15`

- `--num-pmus <int>`  
  Number of **PMU nodes** in the graph.  
  **Default:** `3`

- `--seed <int>`  
  Random seed for reproducibility.  
  **Default:** `None` (random behavior)

- `--p-extra <float>`  
  Probability factor for adding extra edges beyond the minimum required structure.  
  **Default:** `0.25`

- `--cc-min-links <int>`  
  Minimum number of links connected to the **CC node**.  
  **Default:** `2`

- `--cc-max-links <int>`  
  Maximum number of links connected to the **CC node**.  
  **Default:** `None` (no explicit upper bound)

- `--pmu-links <int>`  
  Number of links per **PMU node**.  
  **Default:** `1`

---

Note: you need docker and k3d installed. As said before, this is a work in progress, so some parts of the code may not work as expected.
To run the tests, navigate to the `tests_functions` directory and follow the instructions provided in the corresponding file.