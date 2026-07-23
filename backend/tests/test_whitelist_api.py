import pytest

from app.services.keyword_service import match_explicit_log_keywords, match_log_text


def test_create_and_list_whitelist(client) -> None:
    payload = {
        "namespace": "demo",
        "label_selector": "app=demo",
        "keyword": "connection refused",
        "enabled": True,
        "note": "known harmless in warmup",
    }

    create_response = client.post("/api/v1/whitelists", json=payload)
    list_response = client.get("/api/v1/whitelists")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    assert list_response.json()[0]["keyword"] == "connection refused"


def test_create_and_list_keywords(client) -> None:
    payload = {
        "keyword": "timeout",
        "category": "network",
        "severity": "warning",
        "description": "downstream request timeout",
        "enabled": True,
    }

    create_response = client.post("/api/v1/keywords", json=payload)
    list_response = client.get("/api/v1/keywords")

    assert create_response.status_code == 201
    assert list_response.status_code == 200
    created = create_response.json()
    assert created["keyword"] == "timeout"
    assert any(item["keyword"] == "timeout" for item in list_response.json())


def test_list_keywords_includes_common_builtin_error_keywords(client) -> None:
    response = client.get("/api/v1/keywords")

    assert response.status_code == 200
    keywords = {item["keyword"]: item for item in response.json()}

    for keyword in [
        "Traceback (most recent call last)",
        "ERROR",
        "ModuleNotFoundError",
        "SyntaxError",
        "UnhandledPromiseRejection",
        "ChunkLoadError",
        "Failed to fetch",
        "Cannot read properties of undefined",
    ]:
        assert keyword in keywords
        assert keywords[keyword]["builtin"] is True
        assert keywords[keyword]["enabled"] is True


def test_create_keyword_rejects_invalid_severity(client) -> None:
    response = client.post(
        "/api/v1/keywords",
        json={
            "keyword": "oom",
            "category": "runtime",
            "severity": "fatal",
            "description": "invalid severity",
            "enabled": True,
        },
    )

    assert response.status_code == 422


def test_keyword_enable_disable(client) -> None:
    create_response = client.post(
        "/api/v1/keywords",
        json={
            "keyword": "timeout",
            "category": "network",
            "severity": "warning",
            "description": "downstream request timeout",
            "enabled": True,
        },
    )
    keyword_id = create_response.json()["id"]

    disable_response = client.post(f"/api/v1/keywords/{keyword_id}/disable")
    enable_response = client.post(f"/api/v1/keywords/{keyword_id}/enable")

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True


def test_ignore_log_hit_creates_whitelist_rule(client) -> None:
    response = client.post(
        "/api/v1/whitelists/ignore",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api",
            "container_name": "demo-api",
            "note": "ignored from inspection result",
        },
    )

    payload = response.json()
    list_response = client.get("/api/v1/whitelists")

    assert response.status_code == 201
    assert payload["keyword"] == "connection refused"
    assert payload["namespace"] == "demo"
    assert payload["label_selector"] == "app=demo"
    assert payload["pod_name_pattern"] is None
    assert payload["container_name"] == "demo-api"
    assert payload["enabled"] is True
    assert payload["note"] == "ignored from inspection result"
    assert list_response.json()[0]["keyword"] == "connection refused"


def test_whitelist_enable_disable(client) -> None:
    create_response = client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )
    whitelist_id = create_response.json()["id"]

    disable_response = client.post(f"/api/v1/whitelists/{whitelist_id}/disable")
    enable_response = client.post(f"/api/v1/whitelists/{whitelist_id}/enable")

    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert enable_response.status_code == 200
    assert enable_response.json()["enabled"] is True


def test_namespace_inspection_returns_keyword_hits(client) -> None:
    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()
    pod = payload["pods"][0]
    hit = pod["log_hits"][0]

    assert response.status_code == 200
    assert hit["keyword"] == "connection refused"
    assert hit["category"] == "database"
    assert hit["severity"] == "error"
    assert hit["whitelisted"] is False


def test_namespace_inspection_hides_whitelisted_keyword_hits(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    payload = response.json()
    pod = payload["pods"][0]

    assert response.status_code == 200
    assert pod["log_hits"] == []


def test_namespace_inspection_whitelist_ignores_pod_name_pattern(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "does-not-match-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "label scoped rule ignores pod name",
        },
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    assert response.status_code == 200
    assert response.json()["pods"][0]["log_hits"] == []


def test_whitelist_phrase_suppresses_only_matching_log_line(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=worker",
            "keyword": "Error -2 connecting to dragonfly-0.dragonfly",
            "container_name": "worker",
            "enabled": True,
            "note": "known redis warmup retry",
        },
    )

    with client.app.state.session_factory() as session:
        whitelisted_only = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=worker",
            pod_name="worker-abc",
            container_name="worker",
            log_text="[ERROR] consumer: Error -2 connecting to dragonfly-0.dragonfly.svc.cluster.local",
        )
        has_other_error = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=worker",
            pod_name="worker-def",
            container_name="worker",
            log_text=(
                "[ERROR] consumer: Error -2 connecting to dragonfly-0.dragonfly.svc.cluster.local\n"
                "[ERROR] payment callback failed"
            ),
        )

    error_hit = next(hit for hit in whitelisted_only if hit.keyword == "ERROR")
    other_error_hit = next(hit for hit in has_other_error if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert "dragonfly-0.dragonfly" in error_hit.matched_text
    assert other_error_hit.whitelisted is False
    assert other_error_hit.matched_text == "[ERROR] payment callback failed"


def test_whitelist_json_fragment_suppresses_error_key_hit(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=oidc",
            "keyword": '"error":"invalid_client"',
            "container_name": "api",
            "enabled": True,
            "note": "known upstream auth failure",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=oidc",
            pod_name="oidc-api-1",
            container_name="api",
            log_text=(
                "Token refresh failed detail: {'error': 'Token refresh failed', "
                "'upstream_body': '{\"error\":\"invalid_client\",\"error_description\":\"Client authentication failed\"}'}"
            ),
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert '"error":"invalid_client"' in error_hit.matched_text


def test_whitelist_json_fragment_matches_escaped_log_text(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=oidc",
            "keyword": '"error":"invalid_client"',
            "container_name": "api",
            "enabled": True,
            "note": "known upstream auth failure",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=oidc",
            pod_name="oidc-api-1",
            container_name="api",
            log_text=(
                "Token refresh failed detail: {'error': 'Token refresh failed', "
                "'upstream_body': '{\\\"error\\\":\\\"invalid_client\\\",\\\"error_description\\\":\\\"Client authentication failed\\\"}'}"
            ),
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True


def test_whitelisted_error_line_is_kept_in_other_hit_context(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=worker",
            "keyword": "level=error msg=",
            "container_name": "worker",
            "enabled": True,
            "note": "known noisy structured log prefix",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=worker",
            pod_name="worker-1",
            container_name="worker",
            log_text=(
                "level=error msg=known startup retry\n"
                "still starting\n"
                "[ERROR] payment callback failed"
            ),
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is False
    assert error_hit.matched_text == "[ERROR] payment callback failed"
    assert error_hit.context_before == ["level=error msg=known startup retry", "still starting"]
    assert error_hit.context_text == (
        "level=error msg=known startup retry\n"
        "still starting\n"
        "[ERROR] payment callback failed"
    )


def test_whitelist_level_error_msg_fragment_suppresses_error_hit(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=worker",
            "keyword": "level=error msg",
            "container_name": "worker",
            "enabled": True,
            "note": "known structured log prefix",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=worker",
            pod_name="worker-1",
            container_name="worker",
            log_text="level=error msg=known startup retry",
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert error_hit.matched_text == "level=error msg=known startup retry"


def test_whitelist_error_connect_fragment_suppresses_error_hit(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=frontend",
            "keyword": "Error: connect ECONNREFUSED",
            "container_name": "web",
            "enabled": True,
            "note": "known local dependency startup race",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector="app=frontend",
            pod_name="web-1",
            container_name="web",
            log_text="Error: connect ECONNREFUSED 127.0.0.1:8080",
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert error_hit.matched_text == "Error: connect ECONNREFUSED 127.0.0.1:8080"


def test_namespace_inspection_does_not_match_whitelist_when_container_name_differs(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "sidecar",
            "enabled": True,
            "note": "only ignore sidecar",
        },
    )

    response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )

    hit = response.json()["pods"][0]["log_hits"][0]

    assert response.status_code == 200
    assert hit["keyword"] == "connection refused"
    assert hit["whitelisted"] is False
    assert hit["whitelist_rule_id"] is None


def test_namespace_inspection_disabled_whitelist_restores_non_whitelisted_hit(client) -> None:
    create_response = client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "demo-api-*",
            "container_name": "demo-api",
            "enabled": True,
            "note": "known harmless in warmup",
        },
    )
    whitelist_id = create_response.json()["id"]

    first_response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )
    disable_response = client.post(f"/api/v1/whitelists/{whitelist_id}/disable")

    second_response = client.post(
        "/api/v1/inspections/namespace/run",
        json={"namespace": "demo", "label_selector": "app=demo"},
    )
    second_hit = second_response.json()["pods"][0]["log_hits"][0]

    assert first_response.status_code == 200
    assert first_response.json()["pods"][0]["log_hits"] == []
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False
    assert second_response.status_code == 200
    assert second_hit["whitelisted"] is False
    assert second_hit["whitelist_rule_id"] is None


def test_pod_inspection_whitelist_matches_pod_labels_without_request_selector(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "demo",
            "label_selector": "app=demo",
            "keyword": "connection refused",
            "pod_name_pattern": "ignored-pod-name",
            "container_name": "demo-api",
            "enabled": True,
            "note": "single pod inspection should resolve whitelist by pod labels",
        },
    )

    response = client.post(
        "/api/v1/inspections/pod/run",
        json={"namespace": "demo", "pod_name": "demo-api-7c8f6f7c6b-fh2ns"},
    )

    assert response.status_code == 200
    assert response.json()["pod"]["log_hits"] == []


def test_whitelist_label_selector_matches_supplied_pod_labels(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=frontend",
            "keyword": "Error: connect ECONNREFUSED",
            "container_name": "web",
            "enabled": True,
            "note": "known local dependency startup race",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector=None,
            pod_name="web-1",
            container_name="web",
            log_text="Error: connect ECONNREFUSED 127.0.0.1:5432",
            pod_labels={"app": "frontend"},
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert error_hit.matched_text == "Error: connect ECONNREFUSED 127.0.0.1:5432"


def test_whitelist_fragment_suppresses_error_log_level_in_same_context(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=frontend",
            "keyword": "Error: connect ECONNREFUSED",
            "container_name": "web",
            "enabled": True,
            "note": "known local dependency startup race",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector=None,
            pod_name="web-1",
            container_name="web",
            log_text=(
                "[2026-07-23T10:57:08.905] [ERROR] nodeJS - checkFileExpire error:\n"
                "Error: connect ECONNREFUSED 127.0.0.1:5432\n"
                "    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1148:16)"
            ),
            pod_labels={"app": "frontend"},
        )

    error_hit = next(hit for hit in hits if hit.keyword == "ERROR")

    assert error_hit.whitelisted is True
    assert error_hit.matched_text == "[2026-07-23T10:57:08.905] [ERROR] nodeJS - checkFileExpire error:"


def test_whitelist_fragment_keeps_warn_line_error_word_visible(client) -> None:
    client.post(
        "/api/v1/whitelists",
        json={
            "namespace": "platform",
            "label_selector": "app=frontend",
            "keyword": "Error: connect ECONNREFUSED",
            "container_name": "web",
            "enabled": True,
            "note": "known local dependency startup race",
        },
    )

    with client.app.state.session_factory() as session:
        hits = match_log_text(
            session=session,
            namespace="platform",
            label_selector=None,
            pod_name="web-1",
            container_name="web",
            log_text=(
                "==> /var/log/onlyoffice/documentserver/docservice/out.log <==\n"
                "[2026-07-23T10:57:08.905] [WARN] nodeJS - sqlQuery error sqlCommand: SELECT * FROM task_result WHERE last_open_date <= :\n"
                "Error: connect ECONNREFUSED 127.0.0.1:5432\n"
                "    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1148:16)\n"
                "[2026-07-23T10:57:08.905] [ERROR] nodeJS - checkFileExpire error:\n"
                "Error: connect ECONNREFUSED 127.0.0.1:5432\n"
                "    at TCPConnectWrap.afterConnect [as oncomplete] (net.js:1148:16)"
            ),
            pod_labels={"app": "frontend"},
        )

    visible_error_hits = [hit for hit in hits if hit.keyword == "ERROR" and not hit.whitelisted]
    whitelisted_error_hits = [hit for hit in hits if hit.keyword == "ERROR" and hit.whitelisted]

    assert [hit.matched_text for hit in visible_error_hits] == [
        "[2026-07-23T10:57:08.905] [WARN] nodeJS - sqlQuery error sqlCommand: SELECT * FROM task_result WHERE last_open_date <= :"
    ]
    assert whitelisted_error_hits == []


@pytest.mark.parametrize("match_index", [0, 6, 12])
def test_keyword_hit_contains_up_to_five_lines_of_log_context(client, match_index: int) -> None:
    session = client.app.state.session_factory()
    try:
        lines = [f"line-{index}" for index in range(13)]
        lines[match_index] = "database connection refused"
        hits = match_log_text(session, "demo", None, "demo-api", "demo-api", "\n".join(lines))
    finally:
        session.close()

    assert hits[0].matched_text == "database connection refused"
    assert hits[0].context_before == [f"line-{index}" for index in range(max(0, match_index - 5), match_index)]
    assert hits[0].context_after == [f"line-{index}" for index in range(match_index + 1, min(13, match_index + 6))]
    assert hits[0].context_text == "\n".join([*hits[0].context_before, hits[0].matched_text, *hits[0].context_after])


def test_short_keyword_does_not_match_inside_config_field_name(client) -> None:
    session = client.app.state.session_factory()
    try:
        hits = match_log_text(
            session,
            "demo",
            None,
            "demo-api",
            "envoy",
            "envoy.tcp_proxy.per_connection_idle_timeout_ms: 300000",
        )
    finally:
        session.close()

    assert [hit.keyword for hit in hits if hit.keyword == "timeout"] == []


@pytest.mark.parametrize(
    ("log_text", "keyword"),
    [
        ("x-envoy-is-timeout-retry: false", "timeout"),
        ("grpc-timeout: 1S", "timeout"),
        ("timeout-grpc: 1S", "timeout"),
        ("grpctimeout: 1S", "timeout"),
        ("grpc-error: unavailable", "ERROR"),
        ("error-grpc: unavailable", "ERROR"),
        ("grpcerror: unavailable", "ERROR"),
    ],
)
def test_short_keyword_does_not_match_inside_compound_field_name(client, log_text: str, keyword: str) -> None:
    session = client.app.state.session_factory()
    try:
        hits = match_log_text(
            session,
            "demo",
            None,
            "demo-api",
            "envoy",
            log_text,
        )
    finally:
        session.close()

    assert [hit.keyword for hit in hits if hit.keyword == keyword] == []


def test_short_keyword_matches_standalone_log_word(client) -> None:
    session = client.app.state.session_factory()
    try:
        hits = match_log_text(
            session,
            "demo",
            None,
            "demo-api",
            "api",
            "upstream request timeout after 30s",
        )
    finally:
        session.close()

    assert any(hit.keyword == "timeout" and hit.matched_text == "upstream request timeout after 30s" for hit in hits)


@pytest.mark.parametrize("log_text", ["[error] upstream reset", "[ERROR] upstream reset"])
def test_error_keyword_matches_bracketed_log_level(client, log_text: str) -> None:
    session = client.app.state.session_factory()
    try:
        hits = match_log_text(session, "demo", None, "demo-api", "api", log_text)
    finally:
        session.close()

    assert any(hit.keyword == "ERROR" and hit.matched_text == log_text for hit in hits)


def test_error_keyword_does_not_match_inside_config_field_name(client) -> None:
    session = client.app.state.session_factory()
    try:
        hits = match_log_text(session, "demo", None, "demo-api", "api", "error_code: 0")
    finally:
        session.close()

    assert [hit.keyword for hit in hits if hit.keyword == "ERROR"] == []


def test_explicit_log_keyword_uses_same_token_boundary(client) -> None:
    session = client.app.state.session_factory()
    try:
        config_hits = match_explicit_log_keywords(
            session,
            "demo",
            None,
            "demo-api",
            "envoy",
            "envoy.tcp_proxy.per_connection_idle_timeout_ms: 300000",
            ["timeout"],
        )
        log_hits = match_explicit_log_keywords(
            session,
            "demo",
            None,
            "demo-api",
            "envoy",
            "request timeout: upstream reset",
            ["timeout"],
        )
    finally:
        session.close()

    assert config_hits == []
    assert len(log_hits) == 1
    assert log_hits[0].matched_text == "request timeout: upstream reset"
