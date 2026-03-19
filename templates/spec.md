# Spec: [FILL: FEATURE_NAME]

## Summary
[FILL: What this feature does, in one paragraph.]

## User-Facing Behavior
[FILL: What the user/consumer sees or experiences. Not implementation details.]

## Technical Requirements
- [FILL: Requirement with acceptance criterion]
- [FILL: Requirement with acceptance criterion]

## Interface Definitions
<!-- GUIDANCE: Exact type definitions, function signatures, API contracts. -->
<!-- These must be copy-pasteable — not prose descriptions. -->
<!-- Use Python dataclasses or TypeScript interfaces as appropriate for the layer. -->

```python
# Example — replace with actual definitions
@dataclass
class CueEvent:
    timestamp: float
    cue_type: str
    intensity: float
    metadata: dict[str, Any]
```

## Layer Boundaries
- **[FILL: Layer X]** is responsible for: [FILL: scope]
- **[FILL: Layer Y]** is responsible for: [FILL: scope]
- Interface between X and Y: [FILL: reference to interface definition above]

<!-- GUIDANCE: Every spec must define which layers are involved and where -->
<!-- the boundaries are. This prevents scope creep during implementation. -->

## Constraints
- [FILL: Non-negotiable rules]

## Out of Scope
- [FILL: What this feature explicitly does NOT include]

## Open Questions
- `[DECISION NEEDED]`: [FILL: Question requiring human decision before implementation]

<!-- GUIDANCE: Every ambiguity that could lead to divergent implementations -->
<!-- must be marked [DECISION NEEDED]. Do NOT infer a default. -->

## Edge Cases
- [FILL: Edge case]: [FILL: Expected behavior]
