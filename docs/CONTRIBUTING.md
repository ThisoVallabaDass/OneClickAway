# Development

Use Python 3.12 with `requirements-dev.txt` and `npm ci` for frontend tools.
Production needs no Node runtime or JavaScript build step.

Format with `python -m ruff format backend scripts tests` and `npm run format`.
Run the checks in the README before committing. CI checks formatting, Python
lint, service boundaries, and frontend helpers without private assets. Run the
full generation suite and browser checks locally with the original template.

Keep regression fixtures when changing layout behavior. Validate source-content
preservation and PowerPoint relationships as well as visual appearance. Durable
jobs contain JSON payloads, never pickled objects or Python callables.

Do not commit templates, user presentations, credentials, browser profiles,
databases or `.env`. Review staged files before every push.
