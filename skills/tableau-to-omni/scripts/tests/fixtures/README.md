# Test fixtures

These fixtures are generated programmatically by `tests/test_apply_rules.py`
into a tmp directory at test time, so the directory only contains this README
and the fallback YAML.

## Fallback mapping-rules.yaml

`mapping-rules-fallback.yaml` is loaded by the tests when the real sidecar at
`skills/tableau-to-omni/context/mapping-rules.yaml`
does not yet exist (the sibling agent is producing it in parallel).

It is a minimal subset of the full 129-rule sidecar covering only the rules the
tests assert on. Once the real sidecar lands, the tests will prefer it and the
fallback stays as a compact reference of the expected schema.
