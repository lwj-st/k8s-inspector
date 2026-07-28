# k8s-inspector Helm Chart

## 安装

必须使用与应用镜像相同版本的 Chart 完整安装或升级，不能只替换 Deployment
中的镜像。Chart 同时管理 ServiceAccount、ClusterRole 和 ClusterRoleBinding。

```bash
helm lint ./deploy/helm/k8s-inspector \
  -f ./deploy/helm/k8s-inspector/values-dev.yaml

helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace \
  -f ./deploy/helm/k8s-inspector/values-dev.yaml \
  --atomic \
  --timeout 15m
```

## 安装后权限验收

默认部署完成后，在一个实际巡检的名称空间执行：

```bash
AUTH_AS=system:serviceaccount:k8s-inspector:k8s-inspector-k8s-inspector
TARGET_NAMESPACE=platform

kubectl auth can-i list pods \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list deployments.apps \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list ingresses.networking.k8s.io \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list endpointslices.discovery.k8s.io \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i list persistentvolumeclaims \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
kubectl auth can-i get pods \
  --subresource=log \
  --as="${AUTH_AS}" -n "${TARGET_NAMESPACE}"
```

所有命令都必须返回 `yes`。返回 `no` 时不要继续做巡检验收，应先确认：

```bash
helm get manifest k8s-inspector -n k8s-inspector
kubectl get clusterrole k8s-inspector-k8s-inspector -o yaml
kubectl get clusterrolebinding k8s-inspector-k8s-inspector -o yaml
```

Metrics API 为可选能力；未安装 Metrics Server 时资源指标检查会显示未检查，
不应影响基础资源巡检。

## 关键参数

- `image.repository`：镜像地址，默认 `ghcr.io/lwj-st/k8s-inspector`
- `image.tag`：镜像标签，默认 `latest`
- `basePath`：应用子路径，默认空，表示域名根路径访问
- `ingress.className`：默认 `nginx`，其他环境可改成 `kong`、`traefik`，或显式置空
- `ingress.hosts[0].host`：访问域名
- `ingress.tls`：TLS 证书配置，示例默认使用 `sensecore-tls`
- `ingress.annotations`：可填 Kong 注解，后续配合 `strip-path`
- `persistence.enabled`：是否为 SQLite 启用持久化，默认 `true`
- `persistence.size`：PVC 容量，默认 `512Mi`
- `persistence.storageClass`：存储类；留空时使用集群默认 StorageClass
- `persistence.existingClaim`：复用已有 PVC；留空时由 Chart 创建

默认数据库文件位于 `/data/k8s_inspector.db`，通过 `ReadWriteOnce` PVC 持久化。SQLite 部署应保持 `replicaCount: 1`，不支持多个 Pod 同时写入同一数据库文件。

## 开发环境 values

仓库自带 [values-dev.yaml](values-dev.yaml)，仅用于 test/dev，默认配置：

- 域名 `dev-inspector.sensecore.com`
- 根路径 `/`
- TLS Secret `sensecore-tls`
- IngressClass `nginx`
- 本地管理员账号 `admin`
- 固定的开发环境 Session Secret 和配置加密密钥

此文件中的账号和密钥已经公开，严禁用于生产环境。生产环境必须新建受访问控制的
私有 values 文件并重新生成全部密钥。CI 不使用此文件，CI 仍然只使用
`ci-values.yaml` 和 `e2e-values.yaml`。

## Kong strip-path 示例

```yaml
basePath: /inspector
ingress:
  enabled: true
  annotations:
    konghq.com/strip-path: "true"
  hosts:
    - host: your-domain.example.com
      paths:
        - path: /inspector
          pathType: Prefix
```
