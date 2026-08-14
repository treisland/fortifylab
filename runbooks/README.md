# Runbook Library

Runbooks are Bash scripts that opt in to the FortifyLab wizard with metadata
comments. They are intended for Solutions Engineers, instructors, and operators
who want repeatable demo, diagnostic, training, or customer-workflow scripts.

## Folders

- `official/` contains maintained FortifyLab runbooks.
- `training/` contains classroom, workshop, and demo runbooks.
- `local/` is for private customer-specific scripts and is ignored by git.
- `templates/` contains starter files to copy.

## Authoring Flow

1. Copy `runbooks/templates/shell-runbook.sh` into `runbooks/local/` or
   `runbooks/training/`.
2. Edit the metadata and script body in VS Code, Notepad++, or your editor.
3. Open `Runbook Library` in the wizard.
4. Choose `Validate runbooks`.
5. Inspect, preview, edit parameters, and run the script.

Do not hard-code customer data, passwords, tokens, license values, or private
source code. Use parameters, `.env` defaults, or existing Kubernetes secrets.
