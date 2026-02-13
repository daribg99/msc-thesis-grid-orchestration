# GENERAL NOTES ABOUT K3D CLUSTER CONFIGURATION, DOCKER NETWORK and PERCONA DEPLOYMENT

Create a dedicated Docker network for k3d clusters:
```bash
docker network create mc-net
```
Create a k3d cluster without Traefik on the created network with port mappings:
```bash
k3d cluster create cluster-1 --image rancher/k3s:v1.24.17-k3s1 -p "30085:30085@server:0" -p "30065:30065@server:0" -p "30099:30099@server:0" --agents 1 --network mc-net
```
and for db:
```bash
k3d cluster create cluster-db   --image rancher/k3s:v1.29.4-k3s1   --agents 1   --network mc-net   --k3s-arg "--disable=traefik@server:0"   -p "30950:30950@server:0"   -p "15021:15021@server:0"   -p "15443:15443@server:0"   -p "15012:15012@server:0"   -p "15017:15017@server:0"
```
Retrieve the IP address of the server node:
```bash
docker inspect -f '{{ (index .NetworkSettings.Networks "mc-net").IPAddress }}' k3d-cluster-5-server-0
```
Run a temporary container to inspect network settings:
```bash
docker run --rm --net container:k3d-cluster-5-server-0 nicolaka/netshoot ip -o -4 addr show
```

Set network latency on the server node (replace `500ms` with desired latency):
```bash
docker run --rm --privileged --net container:k3d-cluster-5-server-0 \
  nicolaka/netshoot tc qdisc replace dev eth0 root netem delay 500ms
```
Try pinging another container in the same network to verify latency 
```bash
docker run --rm --net container:k3d-cluster-5-server-0 nicolaka/netshoot ping -c 5 172.18.0.14
```
Remove the latency configuration when done:
```bash
docker run --rm --privileged --net container:k3d-cluster-5-server-0 \
  nicolaka/netshoot tc qdisc del dev eth0 root
```


# PDC configuration

To merge multiple kubeconfig files into one, create a directory to hold them:
```bash
kubectl config view --merge --flatten > "$MERGED"
```

To launch kubectl commands on a specific namespace with specific context, use:
```bash
kubectl --kubeconfig kubeconfigs/merged.yaml --context k3d-cluster-1 -n lower
```

Port forward the database service from db-cluster:
```bash
kubectl --context k3d-cluster-db -n db port-forward --address 0.0.0.0 svc/cluster-db-haproxy 3306:3306
```

Copy secret from db-cluster to cluster-1:
```bash
kubectl --context k3d-cluster-db -n db get secret cluster-db-secrets -o yaml | \
sed 's/namespace: db/namespace: lower/' | \
sed 's/name: cluster-db-secrets/name: cluster-db-secrets/' | \
kubectl --context k3d-cluster-1 -n lower apply -f -
```


# DEPLOY HA MySQL with PERCONA and OPENPDC

This guide explains how to deploy a **High Availability MySQL cluster** using **Percona XtraDB Cluster Operator**, and then deploy **OpenPDC** on top of it.

---

## 1. Clone the Percona repository
```
git clone https://github.com/percona/percona-xtradb-cluster-operator.git
cd percona-xtradb-cluster-operator
```

## 2. Apply Custom Resource Definitions (CRDs)
CRDs define the custom resources used by the operator.
```
kubectl apply -f deploy/crd.yaml
```

## 3. Create a dedicated namespace
Choose a namespace (e.g., higher or lower):
```
kubectl create ns <namespace>
```

## 4. Apply RBAC configuration
Grant the required permissions to the operator in the chosen namespace:
```
kubectl apply -n <namespace> -f deploy/rbac.yaml
```

## 5. Deploy the operator
The operator manages the lifecycle of the Percona XtraDB Cluster.
```
kubectl apply -n <namespace> -f deploy/operator.yaml
```

## 6. Create Secrets
Secrets define the database credentials.
```
kubectl apply -n <namespace> -f deploy/secrets.yaml
```

## 7. Deploy the Percona Cluster (CR)
The cr.yaml resource describes the Percona XtraDB Cluster instance.
```
kubectl apply -n <namespace> -f deploy/cr.yaml
```

## 8. Deploy the OpenPDC
Once the Percona cluster is ready, deploy OpenPDC in the same namespace:
```
kubectl apply -n <namespace> -f openpdc.yaml
```

## 🔎 Notes:
1) Replace <namespace> with the namespace you created (e.g., higher or lower).
2) Make sure the nodePort values in your OpenPDC services are unique if deploying multiple instances.


# To retrive queries from PerconaDB:
1) Take db password from secret:
```
kubectl get secrets cluster1-secrets -n <namespace-name> -o yaml -o jsonpath='{.data.root}' | base64 --decode | tr '\n' ' ' && echo " "
```
2) Enter the specific pod:
```
kubectl exec -it cluster1-pxc-0 -c pxc -n <namespace> -- bash
```
3) On general_log to save queries
```
mysql -uroot -p"$PW" -e "SET GLOBAL log_output='TABLE'; SET GLOBAL general_log=ON; TRUNCATE TABLE mysql.general_log;"
```
4) Your operation...
5) Stamp your query ( converting UTC, fiter HAProxy and Percona Operator )
```
mysql -uroot -p"$PW" -e "
  SELECT
    CONVERT_TZ(event_time,'+00:00','Europe/Rome') AS event_time_rome,
    user_host,
    CONVERT(argument USING utf8) AS query
  FROM mysql.general_log
  WHERE command_type='Query'
    AND user_host NOT LIKE 'monitor%'
AND user_host NOT LIKE 'operator%'
  ORDER BY event_time;"
  ```

Or, if you are looking at SET, INSERT and DELETE:
 ```
mysql -uroot -p"$PW" -e "
  SELECT
    CONVERT_TZ(event_time,'+00:00','Europe/Rome') AS event_time_rome,
    user_host,
    CONVERT(argument USING utf8) AS query
  FROM mysql.general_log
  WHERE command_type='Query'
    AND user_host NOT LIKE 'monitor%'
    AND user_host NOT LIKE 'operator%'
    AND argument REGEXP '^(SET|INSERT|DELETE)[[:space:]]'
  ORDER BY event_time;"
 ```
6) Clear table
```
mysql -uroot -p"$PW" -e "TRUNCATE TABLE mysql.general_log;"
```

7) Turn off general_log
```
mysql -uroot -p"$PW" -e "SET GLOBAL general_log=OFF;"
```

# Port forwarding
Enable port forwarding ssh-ing to the remote k8s node using this command (based on the deployment).
Connect to lower-pdc:
```
ssh -L 3306:localhost:30006 -L 8500:localhost:30085 -L 6165:localhost:30065 user@kubernetes-node
```

   Connect to higher-pdc:
```
ssh -L 3306:localhost:30006 -L 8500:localhost:30185 -L 6165:localhost:30165 user@kubernetes-node
```