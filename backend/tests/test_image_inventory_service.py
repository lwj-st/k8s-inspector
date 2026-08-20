from app.services import image_inventory_service


class FakeProvider:
    def list_namespace_pod_images(self, namespace: str) -> dict:
        return {
            "namespace": namespace,
            "executed_at": "2026-08-19T00:00:00+00:00",
            "provider_mode": "fake",
            "simulated": False,
            "pods": [
                {
                    "name": "api-new",
                    "phase": "Running",
                    "created_at": "2026-08-19T02:00:00+00:00",
                    "images": [
                        {
                            "container_name": "api",
                            "container_type": "container",
                            "source": "spec",
                            "image": " registry.local/api:v1 ",
                        },
                        {
                            "container_name": "api",
                            "container_type": "container",
                            "source": "status",
                            "image": "registry.local/api:v1",
                            "image_id": "docker-pullable://registry.local/api@sha256:abc",
                        },
                        {
                            "container_name": "api",
                            "container_type": "container",
                            "source": "imageID",
                            "image": "docker-pullable://registry.local/api@sha256:abc",
                            "image_id": "docker-pullable://registry.local/api@sha256:abc",
                        },
                    ],
                },
                {
                    "name": "api-old",
                    "phase": "Succeeded",
                    "created_at": "2026-08-18T02:00:00+00:00",
                    "images": [
                        {
                            "container_name": "api",
                            "container_type": "container",
                            "source": "spec",
                            "image": "registry.local/api:v1",
                        }
                    ],
                },
            ],
        }


def test_build_inventory_deduplicates_image_and_container_counts() -> None:
    result = image_inventory_service.build_inventory(
        FakeProvider(),
        namespaces=["demo", "demo", " prod "],
    )

    assert result["namespaces"] == ["demo", "prod"]
    item = next(item for item in result["items"] if item["image"] == "registry.local/api:v1")
    assert item["namespace_count"] == 2
    assert item["pod_count"] == 4
    assert item["container_count"] == 4
    assert item["latest_pod_created_at"] == "2026-08-19T02:00:00+00:00"
    assert item["latest_pod_phase"] == "Running"
    assert all("@sha256:" not in item["image"] for item in result["items"])
    assert any(ref["image_id"] == "docker-pullable://registry.local/api@sha256:abc" for ref in item["references"])


def test_build_inventory_requires_namespace() -> None:
    try:
        image_inventory_service.build_inventory(FakeProvider(), namespaces=[" ", ""])
    except image_inventory_service.ImageInventoryScopeError as exc:
        assert "请选择名称空间" in str(exc)
    else:
        raise AssertionError("expected ImageInventoryScopeError")
