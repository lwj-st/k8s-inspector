"""Service, Ingress and TLS configuration-chain evaluations."""

from app.schemas.v1_1 import (
    InspectionPolicySettings,
    IssueCandidate,
    IssueCode,
    IssueScope,
    IssueSeverity,
    ProviderObservation,
)
from app.services.resource_common import candidate, evidence


def service_candidates(items: list[ProviderObservation]) -> list[IssueCandidate]:
    check = "service.endpoints"
    issues: list[IssueCandidate] = []
    for item in items:
        facts = item.facts
        if str(facts.get("service_type") or "").casefold() == "externalname":
            continue
        if (
            not bool(facts.get("selector_present"))
            and int(facts.get("endpoint_slices") or 0) == 0
            and not bool(facts.get("ingress_referenced"))
        ):
            continue
        selected = int(facts.get("selected_pods") or 0)
        ready = int(facts.get("ready_endpoints") or 0)
        correlation = f"service:{item.resource.namespace or ''}/{item.resource.name}"
        if bool(facts.get("selector_present")) and selected == 0:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.SERVICE_SELECTOR_MISMATCH,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.service,
                    summary=f"Service {item.resource.name} 的 selector 未选中 Pod",
                    reason="Service 配置了 selector，但当前没有标签匹配的 Pod。",
                    suggestion="核对 Service selector 与 Pod labels。",
                    evidence_items=[
                        evidence(
                            item,
                            code="service_selector",
                            summary="selector 未选中 Pod",
                            facts={
                                "selector": list(facts.get("selector") or []),
                                "selected_pods": selected,
                            },
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        if ready == 0:
            severity = (
                IssueSeverity.critical
                if bool(facts.get("ingress_referenced"))
                else IssueSeverity.warning
            )
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.SERVICE_NO_READY_ENDPOINT,
                    severity=severity,
                    scope=IssueScope.service,
                    summary=f"Service {item.resource.name} 没有 Ready Endpoint",
                    reason="合并全部 EndpointSlice 后，Ready Endpoint 数量为 0。",
                    suggestion="检查 Service selector、Pod Ready 和 EndpointSlice。",
                    evidence_items=[
                        evidence(
                            item,
                            code="service_ready_endpoints",
                            summary="Ready Endpoint=0",
                            facts={
                                "endpoint_slices": int(
                                    facts.get("endpoint_slices") or 0
                                ),
                                "ready_endpoints": ready,
                            },
                        )
                    ],
                    correlation_key=correlation,
                )
            )
    return issues


def ingress_candidates(items: list[ProviderObservation]) -> list[IssueCandidate]:
    check = "ingress.config_chain"
    issues: list[IssueCandidate] = []
    for item in items:
        facts = item.facts
        ingress_correlation = (
            f"ingress:{item.resource.namespace or ''}/{item.resource.name}"
        )
        specs = (
            (
                "missing_backend_services",
                IssueCode.INGRESS_BACKEND_NOT_FOUND,
                IssueSeverity.critical,
                "配置链路中的 Service 不存在",
                "修正 Ingress backend 名称或创建对应 Service。",
                "ingress_backend_missing",
                "backend_service",
            ),
            (
                "invalid_backend_ports",
                IssueCode.INGRESS_BACKEND_PORT_INVALID,
                IssueSeverity.critical,
                "配置链路中的后端端口无效",
                "核对 Ingress backend port 与 Service ports。",
                "ingress_backend_port",
                "backend",
            ),
        )
        for fact_key, code, severity, summary, suggestion, evidence_code, evidence_key in specs:
            for value in [str(entry) for entry in facts.get(fact_key, [])]:
                service_name = value.split(":", 1)[0]
                issues.append(
                    candidate(
                        item,
                        check_code=check,
                        issue_code=code,
                        severity=severity,
                        scope=IssueScope.ingress,
                        summary=f"Ingress {item.resource.name} {summary}",
                        reason=f"后端对象 {value} 校验失败。",
                        suggestion=suggestion,
                        evidence_items=[
                            evidence(
                                item,
                                code=evidence_code,
                                summary=value,
                                facts={evidence_key: value},
                            )
                        ],
                        correlation_key=(
                            f"service:{item.resource.namespace or ''}/"
                            f"{service_name}"
                        ),
                    )
                )
        missing_class = str(facts.get("missing_ingress_class") or "")
        if missing_class:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.INGRESS_CLASS_NOT_FOUND,
                    severity=IssueSeverity.warning,
                    scope=IssueScope.ingress,
                    summary=f"Ingress {item.resource.name} 显式引用的 IngressClass 不存在",
                    reason=f"IngressClass {missing_class} 不存在。",
                    suggestion="修正 ingressClassName 或安装对应 Controller/Class。",
                    evidence_items=[
                        evidence(
                            item,
                            code="ingress_class_missing",
                            summary=f"缺失 IngressClass {missing_class}",
                            facts={"ingress_class": missing_class},
                        )
                    ],
                    correlation_key=ingress_correlation,
                )
            )
    return issues


def tls_candidates(
    items: list[ProviderObservation],
    policy: InspectionPolicySettings,
) -> list[IssueCandidate]:
    check = "tls.certificate"
    issues: list[IssueCandidate] = []
    thresholds = policy.thresholds
    for item in items:
        facts = item.facts
        related_ingress = next(
            (
                resource
                for resource in item.related_resources
                if resource.kind.casefold() == "ingress"
            ),
            None,
        )
        correlation = (
            f"ingress:{related_ingress.namespace or ''}/"
            f"{related_ingress.name}"
            if related_ingress
            else None
        )
        if facts.get("exists") is False:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.TLS_SECRET_NOT_FOUND,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.ingress,
                    summary=f"TLS Secret {item.resource.name} 不存在",
                    reason="Ingress 显式引用的 TLS Secret 无法找到。",
                    suggestion="创建 TLS Secret 或修正 Ingress 引用。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_secret_missing",
                            summary="TLS Secret 不存在",
                            facts={"exists": False},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
            continue
        if facts.get("parse_ok") is False:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.TLS_KEY_MISMATCH,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.ingress,
                    summary=f"TLS Secret {item.resource.name} 的证书或私钥无效",
                    reason="tls.crt/tls.key 缺失或无法安全解析。",
                    suggestion="重新生成并更新合法的 TLS 证书密钥对。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_material_invalid",
                            summary="TLS 密钥材料解析失败",
                            facts={"parse_ok": False},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
            continue
        if bool(facts.get("not_yet_valid")):
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.TLS_CERT_EXPIRED,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.ingress,
                    summary="TLS 证书尚未生效",
                    reason="当前时间早于证书有效期起始时间。",
                    suggestion="检查证书签发时间和集群时间，更新为当前有效的证书。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_not_yet_valid",
                            summary="证书尚未进入有效期",
                            facts={"not_yet_valid": True},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        days = float(facts.get("days_until_expiry") or 0)
        expiry: tuple[IssueCode, IssueSeverity, str] | None = None
        if days < 0:
            expiry = (
                IssueCode.TLS_CERT_EXPIRED,
                IssueSeverity.critical,
                "已经过期",
            )
        elif days <= thresholds.tls_critical_days:
            expiry = (
                IssueCode.TLS_CERT_EXPIRING,
                IssueSeverity.critical,
                f"将在 {days:.0f} 天内到期",
            )
        elif days <= thresholds.tls_warning_days:
            expiry = (
                IssueCode.TLS_CERT_EXPIRING,
                IssueSeverity.warning,
                f"将在 {days:.0f} 天内到期",
            )
        if expiry:
            code, severity, summary = expiry
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=code,
                    severity=severity,
                    scope=IssueScope.ingress,
                    summary=f"TLS 证书{summary}",
                    reason=f"证书剩余有效天数约为 {days:.0f}。",
                    suggestion="在到期前更新 Ingress 引用的 TLS Secret。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_expiry",
                            summary=summary,
                            facts={"days_until_expiry": days},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        if facts.get("host_match") is False:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.TLS_HOST_MISMATCH,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.ingress,
                    summary="TLS 证书与 Ingress 域名不匹配",
                    reason="证书 SAN 不覆盖 Ingress host。",
                    suggestion="签发覆盖目标域名的证书并更新 TLS Secret。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_host_mismatch",
                            summary="证书 SAN 不匹配",
                            facts={"hosts": list(facts.get("hosts") or [])[:50]},
                        )
                    ],
                    correlation_key=correlation,
                )
            )
        if facts.get("key_match") is False:
            issues.append(
                candidate(
                    item,
                    check_code=check,
                    issue_code=IssueCode.TLS_KEY_MISMATCH,
                    severity=IssueSeverity.critical,
                    scope=IssueScope.ingress,
                    summary=f"TLS Secret {item.resource.name} 的证书与私钥不匹配",
                    reason="证书公钥与私钥公钥不一致。",
                    suggestion="更新为同一密钥对生成的证书和私钥。",
                    evidence_items=[
                        evidence(
                            item,
                            code="tls_key_mismatch",
                            summary="证书与私钥不匹配",
                            facts={"key_match": False},
                        )
                    ],
                )
            )
    return issues
