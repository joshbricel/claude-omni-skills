# Omni Branch Creator

Create Omni model branches with standardized naming via the Omni API.

## Trigger

Activate when the user asks to "create a branch", "create an omni branch", or "start a new model branch".

## Prerequisites

- `OMNI_API_KEY` environment variable (starts with `omni_osk_` or `omni_pat_`)
- `OMNI_BASE_URL` environment variable (e.g., `https://yourcompany.omniapp.co`)
- Python 3.9+ with `omni-python-sdk` installed

## Workflow

### Step 1: Gather Information

Ask the user for:
1. **First name** and **last name** (for branch naming)
2. **Purpose** (optional — appended to branch name, e.g., `semantic-layer-demo`)

If not provided, prompt before proceeding.

### Step 2: Find the Shared Model

```bash
curl -s -L "$OMNI_BASE_URL/api/v1/models" \
  -H "Authorization: Bearer $OMNI_API_KEY" | python3 -c "
import json, sys
models = json.load(sys.stdin)
for m in models.get('records', []):
    if m.get('modelKind') == 'SHARED':
        print(f'Name: {m[\"name\"]}')
        print(f'ID: {m[\"id\"]}')
        print(f'Connection: {m[\"connectionId\"]}')
        print()
"
```

If multiple SHARED models exist, ask the user which one to branch from.

### Step 3: Create the Branch

Branch naming convention: `{firstname}-{lastname}-{YYYY-MM-DD}-{purpose}`

```python
from omni_python_sdk import OmniAPI
from datetime import date
import os

api = OmniAPI(
    api_key=os.environ['OMNI_API_KEY'],
    base_url=os.environ['OMNI_BASE_URL']
)

branch_name = f"{first_name.lower()}-{last_name.lower()}-{date.today().isoformat()}-{purpose}"

result = api.create_model(
    connection_id=CONNECTION_ID,   # from Step 2
    modelName=branch_name,
    modelKind='BRANCH',
    baseModelId=MODEL_ID           # from Step 2
)

branch_id = result['model']['id']
print(f"Branch: {result['model']['name']}")
print(f"ID: {branch_id}")
```

### Step 4: Report Results

Provide the user with:
- Branch name
- Branch ID
- Direct URL: `{OMNI_BASE_URL}/models/{MODEL_ID}/branch/{branch_name}`

Remind the user of the deployment workflow:
1. Deploy changes to this branch with `build_semantic_layer.py`
2. Validate with `validate_omni_model.py`
3. Review the branch in Omni UI
4. Merge to production with `validate_omni_model.py --merge`

**Never merge directly to production without validating and reviewing the branch first.**

## Error Handling

| Error | Fix |
|-------|-----|
| `omni_python_sdk` not found | Run `pip3 install omni-python-sdk` |
| No SHARED model found | Check API key permissions or ask user for model ID |
| Auth error | Verify `OMNI_API_KEY` is valid and not expired |
| Branch name conflict | Append a counter: `-v2`, `-v3`, etc. |
