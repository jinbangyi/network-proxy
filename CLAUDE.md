# CLAUDE.md

## Project Overview

TODO: Add a brief project description here.

## Repository Structure

### Overview

```bash
.
├── .ai/summaries/                              # AI-generated summaries (date-based: YY-MM-DD/)
│   └── 26-01-09/                               # summaries for Jan 9, 2026
├── .claude/                                    # Claude Code configuration (agents, commands, skills)
├── .devcontainer/                              # Development container runtime configuration
│   ├── .env.example                            # Example environment variables file
│   └── docker-compose.yaml                     # Docker Compose file for devcontainer
├── debug/                                      # Temporary debugging files ONLY
├── data/                                       # persistent data storage for the workspace
├── code-repos/                                 # external repo references for AI agents to use as context
│   ├── github/                                 # Public GitHub repositories
│   │   ├── Public Github Repo1/                # Github repository, AI can create a deepresearch based on the source code
│   │   └── Public Github Repo2/                # Github repository
│   ├── gitlab/                                 # Public GitLab repositories
│   │   ├── self-host GitLab Repo1/             # GitLab repository, AI can create a deepresearch based on the source code
│   │   └── self-host GitLab Repo2/             # GitLab repository
│   ├── Your Github Account/                    # code repo of your personal github account
│   │   ├── Your Personal Repo1/                # Description of your repo
│   │   └── Your Personal Repo2/                # Description of your repo
│   └── Your Github Org/                        # Your GitHub organization repositories
│       ├── Your Org Repo1/                     # Description of your org repo
│       └── Your Org Repo2/                     # Description of your org repo
├── docs/                                       # Project documentation
│   ├── AI-external-context/                    # External system context for AI agents
│   │   ├── personal-info/                      # user personal information for AI agents to use as context
│   │   │   ├── github.md                       # github info
│   │   │   ├── npm.md                          # npm info
│   │   │   └── pypi.md                         # pypi info
│   │   ├── local.md                            # Local running environment info, local env which can upload to git
│   │   └── dev.md                              # Development environment info(vercel,loki,database,hosting,ci/cd etc)
│   ├── blogs/                                  # Blog posts and articles (best practices, tutorials, solutions)
│   ├── development/                            # Date-based development plans (YY-MM-DD/)
│   │   ├── templates/                          # Template for development notes
│   │   │   └── user.md                         # Template for user requirements/tasks
│   │   │── 26-01-09/                           # development notes for Jan 9, 2026
│   │   │   └── user.md                         # user requirements/tasks for the day
│   │   └── TODO.md                             # TODO list for recent development tasks (short-term, tactical)
│   ├── project/                                # all project-related documentation
│   │   └── requirements/                       # Project requirements and specifications
│   │       └── feature-xx/                     # Feature-specific requirements
│   ├── rules/                                  # Repository rules and guidelines
│   │   └── project.md                          # Project-specific rules and guidelines
│   ├── user-guide/                             # User guides and manuals
│   └── TODO.md                                 # project level TODO list for long-term, big-picture
├── scripts/                                    # Repository scripts (to be implemented)
├── src/                                        # All source code (to be implemented)
├── .dockerignore                               # Docker ignore file
├── .env.example                                # Example environment variables file
├── .env.local                                  # Local environment variables file (to be created by user)
├── .gitignore                                  # Git ignore file
├── CLAUDE.md                                   # Project overview and guidelines for AI agents
├── Dockerfile                                  # Dockerfile for containerizing the application
├── main.py                                     # Main application entry point (to be implemented)
├── pyproject.toml                              # Python project configuration (to be implemented)
├── README.md                                   # Project README file (to be implemented)
└── uv.lock                                     # Python dependency lock file (to be implemented)
```

### Detail Description of each directory or file

- `src/`: include all source code.
- `scripts/`: include all scripts.

- `docs/AI-external-context/`: include external system context for AI agents, such as personal information, local environment info, development environment info, etc.
- `docs/development/YY-MM-DD/`: include development documentation organized by date.
- `docs/project/`: include project-related documentation, such as architecture, design decisions, features, and meeting notes.

- `.ai/summaries/YY-MM-DD/`: include AI summaries organized by date.
- `debug/`: include temporary debugging files ONLY.
- `TODO.md`: include ONLY unfinished tasks (remove completed items).
- `.devcontainer/`: include Docker Compose configuration for local development environment.

## Rules and Guidelines

only add rules each session should flow
