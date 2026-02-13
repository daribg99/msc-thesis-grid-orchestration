# TESTING SETUP

## RUNNING Topology change tests
To run topology change tests, run:
```bash
python test_functions/batch_runner.py
```
This script will run N main run, with T changes for each run, with placement algorithm specified inthe script. 

## RUNNING icresing nodes tests:
```bash
python test_functions/batch_runner.py
```
and select 2nd option. This will run 4 main runs, without anychange but increasing the number of nodes in the cluster. 
#### NOTE: This following setup is for testing purposes. It give the possibility to see all PMU phasors arrive at the last PDC. This is developed because PDC Manager utility has some problems when PDC are setted up with CLI commands. 

## PDC-test setup
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