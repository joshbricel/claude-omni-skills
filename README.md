# Claude Skills

A collection of Claude Code skills for data engineering, analytics, and BI workflows.

## Skills

| Skill | Description |
|-------|-------------|
| [omni-branch-creator](skills/omni-branch-creator/) | Create Omni model branches with standardized naming via the Omni API |
| [omni-semantic-layer-setup](skills/omni-semantic-layer-setup/) | Configure an Omni model with descriptions, relationships, AI context, and sample queries. Includes build, validate, and merge scripts. |
| [tableau-to-omni](skills/tableau-to-omni/) | Migrate a Tableau workbook (.twbx) to Omni: parse the XML, map every calc / parameter / dashboard zone / action / style, then rebuild as an Omni dashboard via the official `omni` CLI. Includes a five-stage pipeline (parse → map → build → deploy → verify), 129 mapping rules + 22 guardrails, and a worked Acme demo spec. |

## Setup

### Prerequisites
- [Claude Code](https://claude.com/claude-code) installed
- Python 3.9+
- `omni-python-sdk` (`pip install omni-python-sdk`)

### Environment Variables
```bash
export OMNI_API_KEY="<your-omni-api-key>"           # Organization API key (or PAT for read paths)
export OMNI_BASE_URL="https://yourcompany.omniapp.co"
```

The `tableau-to-omni` skill also uses the `omni` CLI:

```bash
brew tap exploreomni/tap && brew install omni
omni config init   # paste an API token when prompted
```

### Install Skills
Clone this repo and reference skills in your project's `CLAUDE.md`:

```markdown
## Available Skills
- @/path/to/claude-omni-skills/skills/omni-branch-creator/SKILL.md
- @/path/to/claude-omni-skills/skills/omni-semantic-layer-setup/SKILL.md
- @/path/to/claude-omni-skills/skills/tableau-to-omni/SKILL.md
```

## Adding New Skills

Each skill is a folder under `skills/` containing:
- `SKILL.md` — Instructions, triggers, workflow steps, and examples
- Optional supporting scripts or templates

Follow the [Anthropic Skills standard](https://github.com/anthropics/skills) for structure and conventions.

## License

Apache 2.0
