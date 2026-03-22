# Claude Skills

A collection of Claude Code skills for data engineering, analytics, and BI workflows.

## Skills

| Skill | Description |
|-------|-------------|
| [omni-branch-creator](skills/omni-branch-creator/) | Create Omni model branches with standardized naming via the Omni API |
| [omni-semantic-layer-setup](skills/omni-semantic-layer-setup/) | Configure an Omni model with descriptions, relationships, AI context, and sample queries. Includes build, validate, and merge scripts. |

## Setup

### Prerequisites
- [Claude Code](https://claude.com/claude-code) installed
- Python 3.9+
- `omni-python-sdk` (`pip install omni-python-sdk`)

### Environment Variables
```bash
export OMNI_API_KEY="omni_osk_..."
export OMNI_BASE_URL="https://yourcompany.omniapp.co"
```

### Install Skills
Clone this repo and reference skills in your project's `CLAUDE.md`:

```markdown
## Available Skills
- @/path/to/claude-skills/skills/omni-branch-creator/SKILL.md
- @/path/to/claude-skills/skills/omni-semantic-layer-setup/SKILL.md
```

## Adding New Skills

Each skill is a folder under `skills/` containing:
- `SKILL.md` — Instructions, triggers, workflow steps, and examples
- Optional supporting scripts or templates

Follow the [Anthropic Skills standard](https://github.com/anthropics/skills) for structure and conventions.

## License

Apache 2.0
