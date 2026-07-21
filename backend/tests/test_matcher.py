from app.engine.matcher import describe_condition, match_template


def test_match_template_hits_target_group_conditions() -> None:
    template = {
        "target_groups": [
            {
                "ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "object_scope": "deployment",
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"},
            {"target_ref": "api", "type": "event_keyword", "operator": "contains", "value": "Back-off restarting"},
        ],
        "joint_rule": {"operator": "AND"},
        "reason": "Startup dependency failure",
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [
                    {
                        "name": "demo-api",
                        "status": "CrashLoopBackOff",
                        "log_summary": "database connection refused",
                        "log_hits": [
                            {
                                "keyword": "connection refused",
                                "category": "database",
                                "severity": "error",
                                "source": "log_summary",
                                "matched_text": "database connection refused",
                                "container_name": "demo-api",
                                "whitelisted": False,
                                "whitelist_rule_id": None,
                            }
                        ],
                        "events": ["Back-off restarting failed container"],
                        "restarts": 5,
                    }
                ],
                "related_objects": {"services": [], "ingresses": [], "daemonsets": [], "tls_secrets": []},
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["matched_conditions"]) == 3
    assert result["unmatched_conditions"] == []
    assert result["evidence"]


def test_match_template_reports_unmatched_related_object_condition() -> None:
    template = {
        "target_groups": [
            {
                "ref": "api",
                "namespace": "demo",
                "label_selector": "app=demo-api",
            }
        ],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {
                "target_ref": "api",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "statuses": ["degraded"]},
            },
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [{"name": "demo-api", "status": "CrashLoopBackOff", "log_summary": "", "events": []}],
                "related_objects": {
                    "services": [{"name": "demo-api", "status": "healthy"}],
                    "ingresses": [],
                    "daemonsets": [],
                    "tls_secrets": [],
                },
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is False
    assert len(result["matched_conditions"]) == 1
    assert len(result["unmatched_conditions"]) == 1
    assert result["unmatched_conditions"][0]["type"] == "related_object_status"


def test_match_template_ignores_whitelisted_log_hits() -> None:
    template = {
        "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo-api"}],
        "match_conditions": [
            {"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"}
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [
                    {
                        "name": "demo-api",
                        "status": "CrashLoopBackOff",
                        "log_hits": [
                            {
                                "keyword": "connection refused",
                                "category": "database",
                                "severity": "error",
                                "source": "log_summary",
                                "matched_text": "database connection refused",
                                "container_name": "demo-api",
                                "whitelisted": True,
                                "whitelist_rule_id": 1,
                            }
                        ],
                        "events": [],
                    }
                ],
                "related_objects": {"services": [], "ingresses": [], "daemonsets": [], "tls_secrets": []},
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is False
    assert result["matched_conditions"] == []
    assert len(result["unmatched_conditions"]) == 1


def test_match_template_supports_equals_and_lte_operators() -> None:
    template = {
        "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo-api"}],
        "match_conditions": [
            {"target_ref": "api", "type": "pod_status", "operator": "equals", "value": "Running"},
            {"target_ref": "api", "type": "restart_count", "operator": "lte", "value": 1},
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [
                    {
                        "name": "demo-api",
                        "status": "Running",
                        "restarts": 1,
                        "log_hits": [],
                        "events": [],
                    }
                ],
                "related_objects": {"services": [], "ingresses": [], "daemonsets": [], "tls_secrets": []},
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["matched_conditions"]) == 2


def test_match_template_supports_gte_and_related_object_equals() -> None:
    template = {
        "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo-api"}],
        "match_conditions": [
            {"target_ref": "api", "type": "restart_count", "operator": "gte", "value": 3},
            {
                "target_ref": "api",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "statuses": ["degraded"]},
            },
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [
                    {
                        "name": "demo-api",
                        "status": "Running",
                        "restarts": 5,
                        "log_hits": [],
                        "events": [],
                    }
                ],
                "related_objects": {
                    "services": [{"name": "demo-api", "status": "degraded"}],
                    "ingresses": [],
                    "daemonsets": [],
                    "tls_secrets": [],
                },
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["matched_conditions"]) == 2


def test_match_template_filters_related_object_by_name() -> None:
    template = {
        "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo-api"}],
        "match_conditions": [
            {
                "target_ref": "api",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "object_name": "api-svc", "match_any": False, "statuses": ["degraded"]},
            },
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [],
                "related_objects": {
                    "services": [
                        {"name": "other-svc", "status": "degraded"},
                        {"name": "api-svc", "status": "healthy"},
                    ],
                    "ingresses": [],
                    "daemonsets": [],
                    "tls_secrets": [],
                },
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is False
    assert result["unmatched_conditions"][0]["value"]["object_name"] == "api-svc"


def test_match_template_supports_related_object_name_pattern() -> None:
    template = {
        "target_groups": [{"ref": "api", "namespace": "demo", "label_selector": "app=demo-api"}],
        "match_conditions": [
            {
                "target_ref": "api",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "object_name_pattern": "api-*", "match_any": False, "statuses": ["degraded"]},
            },
        ],
        "joint_rule": {"operator": "AND"},
    }
    context = {
        "targets": {
            "api": {
                "namespace": "demo",
                "label_selector": "app=demo-api",
                "pods": [],
                "related_objects": {
                    "services": [{"name": "api-svc", "status": "degraded"}],
                    "ingresses": [],
                    "daemonsets": [],
                    "tls_secrets": [],
                },
            }
        }
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert result["evidence"][0]["objects"] == ["api-svc"]


def test_describe_condition_covers_existing_condition_types() -> None:
    assert (
        describe_condition({"target_ref": "api", "type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]}, True)
        == "api Pod 状态匹配 CrashLoopBackOff"
    )
    assert (
        describe_condition({"target_ref": "api", "type": "log_keyword", "operator": "contains", "value": "connection refused"}, False)
        == "缺少 api 日志关键字 connection refused"
    )
    assert (
        describe_condition({"target_ref": "api", "type": "event_keyword", "operator": "contains", "value": "Back-off restarting"}, False)
        == "缺少 api 事件关键字 Back-off restarting"
    )
    assert (
        describe_condition({"target_ref": "worker", "type": "restart_count", "operator": "gte", "value": 3}, False)
        == "worker 重启次数未达到 >= 3"
    )
    assert (
        describe_condition(
            {
                "target_ref": "gateway",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "statuses": ["degraded"]},
            },
            True,
        )
        == "gateway services 任意对象 状态匹配 = degraded"
    )
    assert (
        describe_condition(
            {
                "target_ref": "gateway",
                "type": "related_object_status",
                "operator": "equals",
                "value": {"resource": "services", "object_name": "gateway-svc", "match_any": False, "statuses": ["degraded"]},
            },
            False,
        )
        == "gateway services gateway-svc 状态未匹配 = degraded"
    )
