from ckan_cloud_operator import logs
from ckan_cloud_operator import kubectl


DEPLOYMENT_YAML = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {instance_id}
  labels:
    app: {instance_id}
  namespace: {namespace}
spec:
  replicas: 1
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: {instance_id}
  template:
    metadata:
      labels:
        app: {instance_id}
    spec:
      serviceAccountName: {instance_id}
      containers:
        - name: {instance_id}
          image: quay.io/external_storage/nfs-client-provisioner:latest
          volumeMounts:
            - name: nfs-client-root
              mountPath: /persistentvolumes
          env:
            - name: PROVISIONER_NAME
              value: fuseim.pri/{instance_id}
            - name: NFS_SERVER
              value: {server_ip}
            - name: NFS_PATH
              value: {server_path}
      volumes:
        - name: nfs-client-root
          nfs:
            server: {server_ip}
            path: {server_path}
"""


RBAC_YAML = """
apiVersion: v1
kind: ServiceAccount
metadata:
  name: {instance_id}
  namespace: {namespace}
---
kind: ClusterRole
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: {instance_id}-runner
rules:
  - apiGroups: [""]
    resources: ["persistentvolumes"]
    verbs: ["get", "list", "watch", "create", "delete"]
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "list", "watch", "update"]
  - apiGroups: ["storage.k8s.io"]
    resources: ["storageclasses"]
    verbs: ["get", "list", "watch"]
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["create", "update", "patch"]
---
kind: ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: run-{instance_id}
subjects:
  - kind: ServiceAccount
    name: {instance_id}
    namespace: {namespace}
roleRef:
  kind: ClusterRole
  name: {instance_id}-runner
  apiGroup: rbac.authorization.k8s.io
---
kind: Role
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: leader-locking-{instance_id}
  namespace: {namespace}
rules:
  - apiGroups: [""]
    resources: ["endpoints"]
    verbs: ["get", "list", "watch", "create", "update", "patch"]
---
kind: RoleBinding
apiVersion: rbac.authorization.k8s.io/v1
metadata:
  name: leader-locking-{instance_id}
  namespace: {namespace}
subjects:
  - kind: ServiceAccount
    name: {instance_id}
    namespace: {namespace}
roleRef:
  kind: Role
  name: leader-locking-{instance_id}
  apiGroup: rbac.authorization.k8s.io
"""


CLASS_YAML = """
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: {storage_class}
provisioner: fuseim.pri/{instance_id}
parameters:
  archiveOnDelete: "{archive_on_delete}"
"""

def pre_update_hook(instance_id, instance, res):
    pass


def deploy(instance_id, instance):
    namespace = instance["spec"]["namespace"]
    storage_class = instance["spec"]["storageclass"]
    server_ip = instance["spec"]["nfs-server-ip"]
    server_path = instance["spec"]["nfs-server-path"]
    archive_on_delete = instance["spec"]["archive-on-delete"]
    vals = {"instance_id": instance_id, "namespace": namespace, "storage_class": storage_class, "server_ip": server_ip, "server_path": server_path, "archive_on_delete": archive_on_delete}
    kubectl.apply(DEPLOYMENT_YAML.format(**vals), is_yaml=True)
    for obj_yaml in RBAC_YAML.split("---"):
        kubectl.apply(obj_yaml.format(**vals), is_yaml=True)
    kubectl.apply(CLASS_YAML.format(**vals), is_yaml=True)


def delete(instance_id, instance):
    namespace = instance["spec"]["namespace"]
    storage_class = instance["spec"]["storageclass"]
    kubectl.check_call("delete deployment %s" % instance_id, namespace=namespace)
    kubectl.check_call("delete RoleBinding leader-locking-%s" % instance_id, namespace=namespace)
    kubectl.check_call("delete Role leader-locking-%s" % instance_id, namespace=namespace)
    kubectl.check_call("delete ClusterRoleBinding run-%s" % instance_id, namespace=namespace)
    kubectl.check_call("delete ClusterRole %s-runner" % instance_id, namespace=namespace)
    kubectl.check_call("delete ServiceAccount %s" % instance_id, namespace=namespace)
    kubectl.check_call("delete StorageClass %s" % storage_class, namespace=namespace)


def get(instance_id, instance, res):
    namespace = instance["spec"]["namespace"]
    storage_class = instance["spec"]["storageclass"]
    res['ready'] = True
    app_pod = None
    for pod in kubectl.get('pods', namespace=namespace, required=True)['items']:
        app = pod['metadata']['labels'].get('app')
        if app == instance_id:
            assert app_pod is None, "Too many nfs-client-provisioner pods in namespace %s" % namespace
            app_pod = pod
    assert app_pod is not None, "nfs-client-provisioner pod is missing from namespace %s" % namespace
    pod_status = kubectl.get_item_detailed_status(app_pod)
    app_deployment = kubectl.get("deployment", instance_id, namespace=namespace, required=True)
    deployment_status = kubectl.get_item_detailed_status(app_deployment)
    storage_class = kubectl.get("storageclass", storage_class, namespace=namespace, required=True)
    storage_class_status = {
        "name": storage_class["metadata"]["name"],
        "parameters": storage_class["parameters"],
        "reclaimPolicy": storage_class["reclaimPolicy"],
    }
    for status in (pod_status, deployment_status, storage_class_status):
        if status.get("errors") and len(status["errors"]) > 0:
            res["ready"] = False
    res['app'] = {
        'namespace': namespace,
        'pod': pod_status,
        'deployment': deployment_status,
        "storage_class": storage_class_status
    }
