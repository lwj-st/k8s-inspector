# k8s-inspector Helm Chart

## 安装

```bash
helm upgrade --install k8s-inspector ./deploy/helm/k8s-inspector \
  --namespace k8s-inspector \
  --create-namespace
```

## 关键参数

- `image.repository`：镜像地址，默认 `ghcr.io/lwj-st/k8s-inspector`
- `image.tag`：镜像标签，默认 `latest`
- `basePath`：应用子路径，默认空，表示域名根路径访问
- `ingress.hosts[0].host`：访问域名
- `ingress.annotations`：可填 Kong 注解，后续配合 `strip-path`

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
