# 🚀 WORK IN PROGRESS — Thesis under development

This repository contains drafts, experiments and notes for the thesis. The work is actively in progress and will be updated regularly.

Status
- 🔧 In development
- 📅 Last updated: 22 January 2026

Folders content:
- `deploy/`: deployment for PDCs and PMUs
- `deploy_automation/`: script to automate deployment, including applier for topology-based configuration and cli for automatic configuration
- `modeling_algorithms/`: placement and visualization algorithms for PDCs
- `reinforcement-learning/`: testing RL algorithms for PDC placement 

# Important Notes: 
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
You don't have to apply any files, the scripts that you launch will do everything for you.
Finally, go to the deployer.sh script, and change the line:
```bash
PERCONA_DIR="/your/path/with/percona-xtradb-cluster-operator"
```
based on your path where you cloned the Percona repository.

This was necessary because the folder "Percona" cannot be added to the repository because it contains third-party dependencies and configuration files that may include secrets, which are not allowed in the repository.
Now you are ready to try the deployment.

# If you want to try the deployment...
- Go into deploy_automation folder
- make sure kubeconfigs folders is empty ( only for the first time )
- run 
```bash
./autopdc_configurator.py json_file
```

# If you want to try entire setup ( algorithms + deployment )...
- make sure kubeconfigs folders is empty ( only for the first time )
- Run, in the root folder
```bash
python3 -m venv .venv

source .venv/bin/activate

python -m pip install -r requirements.txt
```
- Finally, in the root folder run
```bash
python -m deploy_automation.autopdc_configurator
```

Note: you need k3d installed. As said before, this is a work in progress, so some parts of the code may not work as expected.