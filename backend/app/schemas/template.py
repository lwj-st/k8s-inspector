from typing import Any

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, model_serializer, model_validator

from app.schemas.common import TemplateCondition, TemplateTarget, TimestampedModel


class FaultTemplateBase(BaseModel):
    name: str = Field(min_length=1)
    scenario: str
    targets: list[TemplateTarget] = Field(
        default_factory=list,
        validation_alias=AliasChoices("targets", "target_groups"),
    )
    match_conditions: list[TemplateCondition]
    joint_rule: dict | None = None
    reason: str
    suggestion: str
    command: str | None = None
    risk_note: str | None = None
    enabled: bool = True
    object_scope: str | None = None
    namespace_scope: str | None = None
    label_selector: str | None = None

    @model_validator(mode="before")
    @classmethod
    def apply_legacy_defaults(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        targets = payload.get("targets") or payload.get("target_groups")
        if not targets and payload.get("namespace_scope"):
            payload["targets"] = [
                {
                    "target_ref": "default",
                    "namespace": payload["namespace_scope"],
                    "label_selector": payload.get("label_selector"),
                    "resource_scope": [payload["object_scope"]] if payload.get("object_scope") else [],
                }
            ]
        elif targets:
            normalized_targets = []
            for item in targets:
                normalized_targets.append(
                    {
                        "target_ref": item.get("target_ref") or item.get("ref", "default"),
                        "namespace": item["namespace"],
                        "label_selector": item.get("label_selector"),
                        "pod_name_pattern": item.get("pod_name_pattern") or item.get("name"),
                        "resource_scope": item.get("resource_scope")
                        or ([item["object_scope"]] if item.get("object_scope") else []),
                    }
                )
            payload["targets"] = normalized_targets

        normalized_conditions = []
        first_target_ref = payload.get("targets", [{}])[0].get("target_ref", "default")
        joint_operator = payload.get("joint_rule", {}).get("operator")
        for condition in payload.get("match_conditions", []):
            updated = dict(condition)
            updated.setdefault("target_ref", first_target_ref)
            updated.setdefault("join_operator", joint_operator)
            normalized_conditions.append(updated)
        payload["match_conditions"] = normalized_conditions
        return payload

    @model_validator(mode="after")
    def validate_target_refs(self) -> "FaultTemplateBase":
        refs = {group.target_ref for group in self.targets}
        for condition in self.match_conditions:
            if condition.target_ref not in refs:
                raise ValueError(f"unknown target_ref: {condition.target_ref}")
        return self


class FaultTemplateCreate(FaultTemplateBase):
    pass


class FaultTemplateUpdate(FaultTemplateBase):
    pass


class FaultTemplateRead(TimestampedModel, FaultTemplateBase):
    model_config = ConfigDict(from_attributes=True)

    @model_serializer(mode="wrap")
    def serialize(self, handler):
        data = handler(self)
        normalized_targets = [
            {
                "target_ref": item.target_ref,
                "namespace": item.namespace,
                "label_selector": item.label_selector,
                "pod_name_pattern": item.pod_name_pattern,
                "resource_scope": item.resource_scope,
            }
            for item in self.targets
        ]
        legacy_targets = [
            {
                "ref": item.target_ref,
                "name": item.pod_name_pattern,
                "namespace": item.namespace,
                "label_selector": item.label_selector,
                "object_scope": item.object_scope,
            }
            for item in self.targets
        ]
        conditions = []
        for condition in self.match_conditions:
            payload = {
                "target_ref": condition.target_ref,
                "condition_type": condition.condition_type,
                "type": condition.condition_type,
                "operator": condition.operator,
                "expected_value": condition.expected_value,
                "value": condition.expected_value,
                "join_operator": condition.join_operator,
                "enabled": condition.enabled,
            }
            conditions.append(payload)

        data["targets"] = normalized_targets
        data["target_groups"] = legacy_targets
        data["match_conditions"] = conditions
        return data
