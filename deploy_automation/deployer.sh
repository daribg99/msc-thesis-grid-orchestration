#!/usr/bin/env bash
set -euo pipefail

SCRIPT_NAME="$(basename "$0")"

print_help() {
  cat <<EOF
$SCRIPT_NAME - Create k3d clusters from JSON and deploy base architecture with PDCs connected to DB cluster.

Usage:
  $SCRIPT_NAME <paths.json> [OUT_DIR]

Examples:
  $SCRIPT_NAME paths.json
  $SCRIPT_NAME paths.json output-kubeconfigs

FLAG:
  -h, --help   Show this message and exit.
EOF
}

# --- args / help ---
if [[ "${1:-}" == "-h" || "${1:-}" == "--help" ]]; then
  print_help
  exit 0
fi

if [ $# -lt 1 ]; then
  echo "Usage: $SCRIPT_NAME <paths.json> [OUT_DIR]" >&2
  echo "Usage '$SCRIPT_NAME -h' for more information." >&2
  exit 1
fi

JSON="$1"
OUT_DIR="${2:-kubeconfigs}"
MERGED="${OUT_DIR}/merged.yaml"
mkdir -p "$OUT_DIR"

if [ ! -f "$JSON" ]; then
  echo "❌ JSON file not found: $JSON" >&2
  exit 1
fi

echo "📄 JSON file: $JSON"
echo "📂 Output directory: $OUT_DIR"
echo

# --- deps ---
for bin in k3d kubectl jq awk sed; do
  command -v "$bin" >/dev/null 2>&1 || { echo "❌ '$bin' not found in PATH" >&2; exit 1; }
done
if ! command -v yq >/dev/null 2>&1; then
  echo "ℹ️  'yq' not found: skipping 0.0.0.0 → 127.0.0.1 fix"
  YQ_AVAILABLE=0
else
  YQ_AVAILABLE=1
fi

# --- helper functions ---

# From "cluster1" / "cluster-1" / " cluster1 " -> "cluster-1"
normalize_cluster_name() {
  local raw="$1"
  raw="${raw//$'\r'/}"                                # remove CR
  raw="$(echo -n "$raw" | sed -E 's/[[:space:]]//g')" # remove spaces/tabs
  local norm
  norm="$(echo "$raw" | sed -E 's/^cluster-?([0-9]+)$/cluster-\1/i')"
  # If it doesn't match the expected pattern, return the cleaned string anyway
  if [[ -z "$norm" ]]; then
    echo "$raw"
  else
    echo "$norm"
  fi
}

# port offset based on cluster name
# cluster-1 -> offset 0, cluster-2 -> 100, cluster-3 -> 200, ...
cluster_port_offset() {
  local name="$1"
  if [[ "$name" =~ ([0-9]+)$ ]]; then
    local n="${BASH_REMATCH[1]}"
    if (( n > 0 )); then
      echo $(( (n - 1) * 100 ))
      return
    fi
  fi
  # fallback se non c'è numero alla fine
  echo 0
}

# From "cluster-1" → "k3d-cluster-1"
normalize_to_ctx() {
  local raw="$1"
  local cname
  cname="$(normalize_cluster_name "$raw")"
  echo "k3d-${cname}"
}

wait_for_percona_ready() {
  local ctx="$1"   # es: k3d-cluster-db
  local ns="db"
  local timeout_sec=7200    # 2 hours
  local interval_sec=30   # 30 seconds

  echo "⏱️  Waiting for Percona XtraDB Cluster in context '$ctx' (ns=$ns) to become READY. The operation may take several minutes..."

  # Wait that at least one PerconaXtraDBCluster resource appears
  local elapsed=0
  local pxc_name=""
  while (( elapsed < timeout_sec )); do
    pxc_name="$(kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$ns" get perconaxtradbcluster \
      -o jsonpath='{.items[0].metadata.name}' 2>/dev/null || true)"
    if [[ -n "$pxc_name" ]]; then
      echo " Found PerconaXtraDBCluster resource: $pxc_name"
      break
    fi
    echo "   … no PerconaXtraDBCluster resource yet, retrying in ${interval_sec}s"
    sleep "$interval_sec"
    elapsed=$((elapsed + interval_sec))
  done

  if [[ -z "$pxc_name" ]]; then
    echo "   ⚠️  No PerconaXtraDBCluster found within ${timeout_sec}s. Continuing anyway, but the DB might not be ready." >&2
    return 1
  fi

  # Now wait for the status to become "ready"
  elapsed=0
  while (( elapsed < timeout_sec )); do
    local status
    status="$(kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$ns" get perconaxtradbcluster "$pxc_name" \
      -o jsonpath='{.status.state}' 2>/dev/null || true)"

    if [[ "$status" == "ready" ]]; then
      echo "   ✅ PerconaXtraDBCluster '$pxc_name' is READY (status=$status)."
      return 0
    fi

    echo "   … PerconaXtraDBCluster '$pxc_name' not ready yet (status='${status:-<none>}'), retrying in ${interval_sec}s"
    sleep "$interval_sec"
    elapsed=$((elapsed + interval_sec))
  done

  echo "   ⚠️  Timeout: PerconaXtraDBCluster '$pxc_name' did not become READY within ${timeout_sec}s. Continuing anyway." >&2
  return 1
}

wait_for_all_workloads_ready() {
  local timeout_sec=7200     # 2 hours
  local interval_sec=30
  local elapsed=0

  local total="${#WORKLOAD_NAME[@]}"

  echo "⏱️  Waiting for ALL PMU + PDC workloads to become READY..."

  local -a READY_FLAGS
  for ((i=0; i<total; i++)); do READY_FLAGS[i]=0; done

  while (( elapsed < timeout_sec )); do
    local ready_count=0

    for ((i=0; i<total; i++)); do
      if (( READY_FLAGS[i] == 1 )); then
        ((ready_count++))
        continue
      fi

      local ctx="${WORKLOAD_CTX[i]}"
      local ns="${WORKLOAD_NS[i]}"
      local app="${WORKLOAD_NAME[i]}"   # es: "openpdc" o "pmu-1"

      deploy_name="$app"

      if [[ -z "$deploy_name" ]]; then
        echo "   … no deployment with app=$app in $ctx yet"
        continue
      fi

      # CHECK READY/EXPECTED
      ready="$(kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$ns" \
        get deploy "$deploy_name" -o jsonpath='{.status.readyReplicas}' 2>/dev/null || echo 0)"

      desired="$(kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$ns" \
        get deploy "$deploy_name" -o jsonpath='{.spec.replicas}' 2>/dev/null || echo 1)"

      if [[ -z "$ready" ]]; then ready=0; fi

      if (( ready == desired )); then
        echo "   ✅ $app @ $ctx READY ($ready/$desired)"
        READY_FLAGS[i]=1
        ((ready_count++))
      else
        echo "   … $app @ $ctx NOT ready ($ready/$desired)"
      fi
    done

    echo

    if (( ready_count == total )); then
      echo "🎉 All workloads READY!"
      return 0
    fi

    echo "⏳ Retrying in ${interval_sec}s..."
    sleep "$interval_sec"
    elapsed=$((elapsed + interval_sec))
  done

  echo "⚠️  Timeout: not all workloads became ready in ${timeout_sec}s" >&2
  return 1
}



# --- Extraction of clusters (PDC) from JSON ---
echo "🔎 Extracting PDC (clusters) from JSON..."
readarray -t ORDERED_CLUSTERS < <(
  jq -r '.paths[] | .[1:][]' "$JSON" | awk '!seen[$0]++'
)

if [ "${#ORDERED_CLUSTERS[@]}" -eq 0 ]; then
  echo "⚠️  No clusters found in JSON under 'paths' (after skipping PMU)." >&2
  echo "👉 Example: {\"paths\":[[\"PMU-1\",\"cluster1\",...],[\"PMU-2\",\"cluster4\",...]]}"
  echo "🔎 Debug dump of .paths:"
  jq '.paths' "$JSON" || true
  exit 1
fi

echo "🗺️  Computed PDC/cluster list (from JSON, no duplicates): ${ORDERED_CLUSTERS[*]}"
echo

# --- Creation of k3d clusters for each PDC (if they don't exist) ---

echo "🏗️  Ensuring k3d clusters exist for each PDC..."

# List of already existing clusters
existing_json="$(k3d cluster list -o json || echo '[]')"
mapfile -t EXISTING_CLUSTERS < <(echo "$existing_json" | jq -r '.[].name')

for raw in "${ORDERED_CLUSTERS[@]}"; do
  cname="$(normalize_cluster_name "$raw")"  # e.g., "cluster-1"
  # Check if it already exists
  if printf '%s\n' "${EXISTING_CLUSTERS[@]}" | grep -qx "$cname"; then
    echo "   ✅ Cluster '$cname' already exists, skipping creation"
    continue
  fi

  # Calculate external ports based on the cluster number
  offset="$(cluster_port_offset "$cname")"
  p1=$((30085 + offset))
  p2=$((30065 + offset))
  p3=$((30099 + offset))

  echo "   ➕ Creating k3d cluster '$cname' (ports: $p1:30085, $p2:30065, $p3:30099)..."
  k3d cluster create "$cname" \
    --image rancher/k3s:v1.29.4-k3s1 \
    -p "${p1}:30085@server:0" \
    -p "${p2}:30065@server:0" \
    -p "${p3}:30099@server:0" \
    --agents 1 \
    --k3s-arg "--flannel-iface=eth0"@server:0 \
    --network mc-net

  # Update the list of existing clusters in memory
  EXISTING_CLUSTERS+=("$cname")
done
echo

# --- Creation (only once) of the cluster-db ---
DB_CLUSTER="cluster-db"
echo "🏗️  Ensuring k3d cluster '$DB_CLUSTER' exists (DB cluster)..."
CLUSTER_DB_EXISTS=0
if printf '%s\n' "${EXISTING_CLUSTERS[@]}" | grep -qx "$DB_CLUSTER"; then
  CLUSTER_DB_EXISTS=1
  echo "   ✅ Cluster '$DB_CLUSTER' already exists, skipping creation"
else
  echo "   ➕ Creating k3d cluster '$DB_CLUSTER'..."
  k3d cluster create "$DB_CLUSTER" \
    --image rancher/k3s:v1.24.17-k3s1 \
    --agents 1 \
    --network mc-net \
    --k3s-arg "--disable=traefik@server:0" \
    -p "30950:30950@server:0" \
    -p "15021:15021@server:0" \
    -p "15443:15443@server:0" \
    -p "15012:15012@server:0" \
    -p "15017:15017@server:0"

  EXISTING_CLUSTERS+=("$DB_CLUSTER")
fi

echo

# merge kubeconfig + deploy manifest ---

echo "🔎 Reading list of k3d clusters..."
clusters_json="$(k3d cluster list -o json)"
mapfile -t CLUSTERS < <(echo "$clusters_json" | jq -r '.[].name')

if [ "${#CLUSTERS[@]}" -eq 0 ]; then
  echo "No k3d clusters found." >&2
  exit 1
fi

echo "📦 Exporting and merging kubeconfigs..."
KUBEFILES=()
for c in "${CLUSTERS[@]}"; do
  f="$OUT_DIR/${c}.yaml"
  k3d kubeconfig get "$c" > "$f"
  if [ "$YQ_AVAILABLE" -eq 1 ]; then
    yq -i '(.clusters[].cluster.server |= sub("0.0.0.0","127.0.0.1"))' "$f" || true
  fi
  KUBEFILES+=("$f")
done

export KUBECONFIG="$(IFS=: ; echo "${KUBEFILES[*]}")"
kubectl config view --merge --flatten > "$MERGED"
echo "✅ Merged kubeconfig created successfully into $MERGED"
echo


# --- Deploy Percona XtraDB on cluster-db ---

echo
echo "🏗️  Setup Percona XtraDB sul cluster DB ('$DB_CLUSTER')..."

PERCONA_DIR="../../percona-xtradb-cluster-operator/deploy"

if [ ! -d "$PERCONA_DIR" ]; then
  echo "❌ Percona directory not found: $PERCONA_DIR" >&2
  exit 1
fi

# Check that the files exist
for f in crd.yaml rbac.yaml operator.yaml secrets.yaml cr.yaml; do
  if [ ! -f "$PERCONA_DIR/$f" ]; then
    echo "❌ Missing file: $PERCONA_DIR/$f" >&2
    exit 1
  fi
done

DB_CTX="k3d-${DB_CLUSTER}"

if ! kubectl --kubeconfig "$MERGED" config get-contexts -o name | grep -qx "$DB_CTX"; then
  echo "❌ Context '$DB_CTX' not found in the merged kubeconfig ($MERGED)" >&2
  exit 1
fi

# Namespace db (if it doesn't exist, create it)
if ! kubectl --kubeconfig "$MERGED" --context "$DB_CTX" get ns db >/dev/null 2>&1; then
  echo "   📦 Creating namespace 'db' in the cluster-db..."
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" create ns db
fi

if [ "$CLUSTER_DB_EXISTS" -eq 0 ]; then
  echo "   📥 Applying Percona manifest in the cluster-db..."
  # CRD (cluster-scoped, without -n)
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" apply -f "$PERCONA_DIR/crd.yaml"

  # Everything else inside ns db
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db apply -f "$PERCONA_DIR/rbac.yaml"
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db apply -f "$PERCONA_DIR/operator.yaml"
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db apply -f "$PERCONA_DIR/secrets.yaml"
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db apply -f "$PERCONA_DIR/cr.yaml"
  kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db apply -f "$PERCONA_DIR/np-svc.yaml"

  echo "   ✅ Percona XtraDB manifest applied (operator + cluster + secrets)."
  echo

  # Wait for PerconaXtraDBCluster to become READY
  wait_for_percona_ready "$DB_CTX" || echo "   ⚠️  Continuing anyway with the deploy of PDC."
  echo
else 
  echo "   ✅ Percona XtraDB already set up in cluster-db, skipping manifest application."
fi 

# --- Preparing DB data: IP and secret ---
echo "🔗 Retrieving DB IP (container k3d-cluster-db-server-0 on mc-net)..."
DB_IP="$(docker inspect -f '{{ (index .NetworkSettings.Networks "mc-net").IPAddress }}' k3d-cluster-db-server-0 2>/dev/null || true)"
if [[ -z "$DB_IP" ]]; then
  echo "❌ Unable to determine DB IP on mc-net. Verify that the container 'k3d-cluster-db-server-0' exists and is on the 'mc-net' network." >&2
  exit 1
fi
echo "   ✅ DB_IP: $DB_IP"


# Global array for wait_for_all_workloads_ready function
WORKLOAD_CTX=()
WORKLOAD_NS=()
WORKLOAD_NAME=()

# --- Deploy openPDC on each cluster (except DB) ---
NAMESPACE="lower"
RAW_PDC_URL="https://raw.githubusercontent.com/daribg99/TESI/refs/heads/main/deploy/openpdc.yaml"
if ! curl -fsI "$RAW_PDC_URL" >/dev/null; then
  echo "❌ Manifest unreachable (404?): $RAW_PDC_URL" >&2
  echo "👉 Open the link in your browser and use the 'Raw' button to copy the correct URL." >&2
  exit 1
fi
# Download the RAW manifest only once into a temporary file
echo "⬇️  Downloading RAW openPDC manifest only once..."
TMP_RAW="$(mktemp)"
curl -fsSL "$RAW_PDC_URL" -o "$TMP_RAW"

echo
echo "🚀 Deploy PDC on each cluster (except '$DB_CLUSTER')..."
echo "-----------------------------------------------------------"

for c in "${ORDERED_CLUSTERS[@]}"; do
  cname="$(normalize_cluster_name "$c")"          # es: cluster-1
  if [[ "$cname" == "$DB_CLUSTER" ]]; then
    echo "➡️  Skipping DB cluster '$cname'"
    continue
  fi

  ctx="$(normalize_to_ctx "$cname")"              # es: k3d-cluster-1
  echo "➡️  Cluster JSON: '$c'  → context: '$ctx'"

  if ! kubectl --kubeconfig "$MERGED" config get-contexts -o name | grep -qx "$ctx"; then
    echo "   ⚠️  Context '$ctx' NOT present in the merged kubeconfig. Skip."
    echo
    continue
  fi

  # Namespace on the target PDC cluster
  if ! kubectl --kubeconfig "$MERGED" --context "$ctx" get ns "$NAMESPACE" >/dev/null 2>&1; then
    echo "   📦 Creating namespace '$NAMESPACE'..."
    kubectl --kubeconfig "$MERGED" --context "$ctx" create ns "$NAMESPACE"
  fi

  # 1) Copy secret from DB cluster → target cluster (lower namespace)
echo "   🔐 Sync secret 'cluster-db-secrets' from DB → $ctx/$NAMESPACE ..."

kubectl --kubeconfig "$MERGED" --context "$DB_CTX" -n db get secret cluster-db-secrets -o yaml \
  | sed '
      /resourceVersion:/d
      /uid:/d
      /creationTimestamp:/d
      /selfLink:/d
      /managedFields:/,/^[^ ]/d
      /^  namespace:/d
    ' \
  | sed "s/^metadata:\n  name: .*/metadata:\n  name: cluster-db-secrets/" \
  | sed "s/^metadata:$/metadata:\n  namespace: $NAMESPACE/" \
  | kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$NAMESPACE" apply -f - >/dev/null


  # 2) Preparing patched YAML file for this cluster
#    - DB_NAME: cluster1/cluster2/...  (removing the '-')
#    - DB_URL:  IP of the DB (from docker inspect)
#    - Service name: openpdc-low-<cluster> (per distinguerlo negli script)

db_name_no_dash="$(echo "$cname" | sed 's/-//')"
svc_name="openpdc-$db_name_no_dash"

TMP_PER_CLUSTER="$(mktemp)"

echo "   🛠️  Patch con awk (DB_NAME=$db_name_no_dash, DB_URL=$DB_IP, SVC_NAME=$svc_name)..."
awk -v db="$db_name_no_dash" -v ip="$DB_IP" -v svc="$svc_name" '
  BEGIN {
    isService = 0
  }
  /^kind:[[:space:]]*Service/ {
    isService = 1
    print
    next
  }
  /^kind:/ {
    isService = 0
    print
    next
  }
  isService && $1 == "name:" && $2 == "openpdc" {
    sub(/openpdc$/, svc)
    print
    next
  }
  /name:[[:space:]]*DB_NAME/ {
    print
    if (getline line) {
      sub(/value:.*/, "value: " db, line)
      print line
    }
    next
  }
  /name:[[:space:]]*DB_URL/ {
    print
    if (getline line) {
      sub(/value:.*/, "value: \"" ip "\"", line)
      print line
    }
    next
  }

  { print }
' "$TMP_RAW" > "$TMP_PER_CLUSTER"

  # 3) Apply patched manifest to the target cluster
  echo "   📥 kubectl apply -n $NAMESPACE -f <patched>"
  if kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$NAMESPACE" apply -f "$TMP_PER_CLUSTER"; then
    echo "   ✅ Apply OK on '$ctx'"
    echo "   🔎 Pods:"
    kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$NAMESPACE" get pods
    WORKLOAD_CTX+=("$ctx")
    WORKLOAD_NS+=("$NAMESPACE")
    WORKLOAD_NAME+=("openpdc")  

  else
    echo "   ❌ Apply FAILED on '$ctx' — continuing with the next one" >&2
  fi

  echo
done


# --- Deploy PMU ---
echo
echo "🚀 PMU Deployment..."

PMU_DIR="../deploy"

if [ ! -d "$PMU_DIR" ]; then
  echo "❌ Directory for PMU not found: $PMU_DIR" >&2
  exit 1
fi

# Extract pairs (PMU-X → clusterY)
readarray -t PMU_MAP < <(
  jq -r '.paths[] | "\(.[0]) \(.[1])"' "$JSON"
)
for entry in "${PMU_MAP[@]}"; do
  pmu_name="$(echo "$entry" | awk '{print $1}')"     # es: PMU-1
  raw_cluster="$(echo "$entry" | awk '{print $2}')"  # es: cluster1

  cname="$(normalize_cluster_name "$raw_cluster")"    # es: cluster-1
  ctx="$(normalize_to_ctx "$cname")"                 # es: k3d-cluster-1

  yaml_file="$PMU_DIR/$(echo "$pmu_name" | tr '[:upper:]' '[:lower:]').yaml"
  # => pmu-1.yaml

  echo "➡️  Deploy PMU '$pmu_name' in cluster '$cname'"

  # Check context
  if ! kubectl --kubeconfig "$MERGED" config get-contexts -o name | grep -qx "$ctx"; then
    echo "   ⚠️  Context '$ctx' NOT found in merged kubeconfig, skip."
    echo
    continue
  fi

  # Check PMU YAML file
  if [ ! -f "$yaml_file" ]; then
    echo "   ❌ PMU file missing: $yaml_file"
    echo
    continue
  fi

  echo "   📥 Apply $yaml_file in cluster '$ctx'..."
  if kubectl --kubeconfig "$MERGED" --context "$ctx" -n "$NAMESPACE" apply -f "$yaml_file"; then
    echo "   ✅ PMU '$pmu_name' deployed successfully."
    # Register PMU workload for final wait
    pmu_deploy_name="$(echo "$pmu_name" | tr '[:upper:]' '[:lower:]')"  # pmu-1
    WORKLOAD_CTX+=("$ctx")
    WORKLOAD_NS+=("lower")
    WORKLOAD_NAME+=("$pmu_deploy_name")

  else
    echo "   ❌ Failed to deploy '$pmu_name' in '$ctx'"
  fi

  echo
done

echo
wait_for_all_workloads_ready || echo "⚠️  Some workloads did not become ready in time."
echo "🎯 Done. You can see pod and svc by running:"
echo "kubectl --kubeconfig \"$MERGED\" --context <context> -n <namespace> get pods,svc"