# Create and configure k3d

Create a dedicated Docker network for k3d clusters:
```bash
docker network create mc-net
```
Create a k3d cluster without Traefik on the created network:
```bash
k3d cluster create cluster-1 --servers 1 --agents 0 --k3s-arg "--disable=traefik@server:*" --network mc-net
```
or, with port mappings:
```bash
k3d cluster create cluster-1 \
  -p "8500:30085@server:0" \
  -p "6165:30065@server:0" \
  -p "4712:30099@server:0" \
  --agents 1 \
  --network mc-net
```
and for db:
```bash
k3d cluster create cluster-db \
  -p "3306:30950@server:0" \
  --agents 1 \
  --network mc-net
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
sed 's/name: cluster-db-secrets/name: clusterdb-secrets/' | \
kubectl --context k3d-cluster-1 -n lower apply -f -
```


