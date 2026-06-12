# Project Rules

## File Organization Rules
- All source code goes in `src/`
- All scripts go in `scripts/`
- Development documentation organized by date under `docs/development/YY-MM-DD/`
- AI summaries organized by date under `.ai/summaries/YY-MM-DD/`
- Temporary debugging files ONLY in `debug/` directory

## Documentation Rules
- TODO.md contains ONLY unfinished tasks (remove completed items)
- Development notes go in date-based folders
- Always check existing docs and summaries before starting new work

## Development Workflow
- Use `.devcontainer/` Docker Compose configs for local environment
- Reference `docs/AI-external-context/` for external system context
