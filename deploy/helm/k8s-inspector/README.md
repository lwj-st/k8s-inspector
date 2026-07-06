# k8s-inspector Helm Chart

## 安装

```bash
helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace \
  -f ./deploy/helm/k8s-inspector/values-prod.yaml
```

## 关键参数

- `image.repository`：镜像地址，默认 `ghcr.io/lwj-st/k8s-inspector`
- `image.tag`：镜像标签，默认 `latest`
- `basePath`：应用子路径，默认空，表示域名根路径访问
- `ingress.className`：默认 `nginx`，其他环境可改成 `kong`、`traefik`，或显式置空
- `ingress.hosts[0].host`：访问域名
- `ingress.tls`：TLS 证书配置，示例默认使用 `sensecore-tls`
- `ingress.annotations`：可填 Kong 注解，后续配合 `strip-path`

## 生产 values 示例

仓库自带 [values-prod.yaml](/Users/liwenjian1.vendor/Documents/Codex/k8s-inspector/deploy/helm/k8s-inspector/values-prod.yaml:1)，默认配置：

- 域名 `dev-inspector.sensecore.com`
- 根路径 `/`
- TLS Secret `sensecore-tls`
- IngressClass `nginx`

CI 不使用这个文件，CI 仍然只使用 `ci-values.yaml` 和 `e2e-values.yaml`。

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
