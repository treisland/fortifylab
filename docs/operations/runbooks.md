# Runbook Library

The Runbook Library lets Solutions Engineers and instructors add reusable Bash
scripts to Fortify Lab and run them from the wizard. A runbook can be a demo
helper, diagnostic check, customer-environment adapter, class exercise, or file
generator.

Runbooks are local-first. Fortify Lab discovers scripts only when they opt in with
metadata comments. The wizard lets you inspect metadata, preview the script, edit
parameters, show the resolved command, validate the script, and run it.

## Folders

```text
runbooks/
  templates/   starter templates
  official/    maintained Fortify Lab runbooks
  training/    classroom, workshop, and demo runbooks
  local/       private local runbooks ignored by git
```

Use `runbooks/local/` for customer-specific scripts or experiments. Promote a
script to `runbooks/training/` or `runbooks/official/` only after removing
customer data, credentials, tokens, and private source paths.

## Add a runbook

Copy the shell template:

```bash
cp runbooks/templates/shell-runbook.sh runbooks/local/my-runbook.sh
```

Edit the file in VS Code, Notepad++, or your preferred editor. Required
metadata:

```bash
  # fortifylab-runbook: true
  # name: My runbook
  # description: Explain what this script does and when to use it.
  # risk: low
```

Supported risk values are `low`, `medium`, `high`, and `destructive`. High and
destructive runbooks require confirmation before running.

Optional metadata:

```bash
  # category: CI/CD Examples
  # order: 20
  # requires: bash,fcli
  # type: script
```

`order` is optional. Missing order values sort as `1000`; duplicate order values
are sorted by name and file path.

## Parameters

Parameters are optional. Parameter names become uppercase environment variables
when the script runs. For example, `target_repo` becomes `TARGET_REPO`.

```bash
  # params:
  #   - name: target_repo
  #     description: Local repository path where output should be written.
  #     required: true
  #   - name: app_version
  #     description: SSC application version.
  #     default: JuiceShop:training
  #   - name: ssc_url
  #     description: SSC URL from .env when available.
  #     defaultFromEnv: SSC_URL
```

The wizard passes parameters as environment variables rather than building a
command string from user input.

## Use the wizard

Open the wizard and choose:

```text
Runbook Library
```

From there you can:

- validate all discovered runbooks
- inspect a runbook's purpose, source, path, risk, and required tools
- edit parameter values
- preview the script
- show the resolved command
- run the script and record output in the wizard log

## Example: GitHub Actions SAST

A training runbook can generate a GitHub Actions workflow for FCLI and
ScanCentral SAST. During a class, an instructor can select the runbook, provide
a target repository path, generate `.github/workflows/fortify-sast.yml`, and
walk students through the generated file.

This keeps the class synchronized without pasting long commands from slides or
searching old notes during a live demo.

## Safety

Do not hard-code secrets or customer data. Use parameters, `.env` defaults, or
existing Fortify Lab/Kubernetes secrets. Runbooks marked `high` or `destructive`
should clearly explain what they change and why.
