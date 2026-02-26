# TESTING SETUP
This file contains the instructions to run three types of tests:
- Topology Change Test: For each of the N main runs, T topology changes are applied.
Each change is evaluated using all three considered algorithms: Bruteforce, Greedy, and Random.
As output, the following metrics are analyzed:
    - accard distance (both single-run results and distribution)
    - Deployment time (both single-run results and distribution)

- Increasing Node Test:  A total of N × Latency main runs are performed. For each network topology size, all three algorithms are executed. The analysis includes:
    - Execution time for individual runs and its distribution
    - Number of selected PDCs vs. candidate nodes, for each topology size and for each algorithm   
- PDC Test Setup: This test consists of deploying a dedicated test PDC that collects measurements from the PMUs and verifies that the achieved latency matches the expected one, using the OpenPDC Manager GUI.

It is important to note that the runtime results of the first two tests are stored in the `runtime_results` folder, while the PDC test setup is executed on a dedicated cluster with a specific OpenPDC configuration.

Therefore, the `runtime_results` folder must be cleared before running new tests to avoid mixing results obtained with different configurations.

If the configuration remains unchanged, the new results will simply be appended to the existing ones. This can be useful to increase the sample size and improve the statistical significance of the results.

# 1) Topology Change Test
To run topology change tests, run:
```bash
python -m test_functions.batch_runner
```
and select option 1. 
This script will run N main run, with T changes for each run, with placement algorithm specified into the script. 

# 2) Increasing Node Test
```bash
python -m test_functions.batch_runner
```
and select 2nd option. This will run 4 main runs, without anychange but increasing the number of nodes in the cluster. 
 

# 3) PDC Test Setup
First, go on deploy/openpdc-test.yaml and change the DB ip address to the k3d-cluster-db server IP. We can found it on command printed by main script `python -m deploy_automation.autopdc_configurator` or by running:
```bash
docker inspect -f '{{ (index .NetworkSettings.Networks "mc-net").IPAddress }}' k3d-cluster-5-server-0
```

Then, go in the root folder and apply the configuration:
```bash
k context k3d-cluster-27 apply -n lower -f deploy/openpdc-test.yaml
```

## Port forwarding
```bash
ssh -L 3306:localhost:30950 -L 8500:localhost:32684 -L 6165:localhost:32664 user@remote-server
```
## OpenPDC manager
Run ConfigurationSetupUtility and use the following credential:
- Server: `localhost`
- database name: `clustertest`
- username: `openpdc`
- password: `password`

Before running the utility, go into Advanced and modify the Data Provider connection string with your version of MSQL connector. 
Finally, if you want to make quick setup, you can create historian directly with CLI by running:
```bash
./deploy_automation/openpdc_cli.sh createhistorian --db-context k3d-cluster-db --openpdc-context k3d-cluster-27 --db-ns db --pdc-ns lower --db clustertest --pod <openpdc-pod-name>
```
Now you can use OpenPDC Manager to connect to the downstreams. 