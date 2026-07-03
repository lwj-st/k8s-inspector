from app.engine.matcher import match_template


def test_match_template_hits_crashloop_keyword_rule() -> None:
    template = {
        "match_conditions": [
            {"type": "pod_status", "operator": "in", "value": ["CrashLoopBackOff"]},
            {"type": "log_keyword", "operator": "contains", "value": "connection refused"},
        ],
        "reason": "Startup dependency failure",
    }
    context = {
        "pods": [
            {"name": "demo-api", "status": "CrashLoopBackOff", "log_summary": "database connection refused"}
        ]
    }

    result = match_template(template, context)

    assert result["matched"] is True
    assert len(result["evidence"]) == 2
