"""Pascal-derived navigation baseline for the M2 Python TUI model."""

from __future__ import annotations

from .models import ActionKind, MenuNode, item


FIRST_SCAN_DISABLED_REASON = "deploy SSC and ScanCentral SAST before running the first-scan demo"


MAIN_MENU = MenuNode(
    id="main",
    title="FortifyLab",
    return_aliases=("r",),
    back_aliases=("b", "escape", ""),
    items=(
        item("0", "Initial setup and readiness", ActionKind.WORKFLOW, "setup_readiness", placeholder=False),
        item("1", "Deploy: guided, express, resume", ActionKind.MENU, "deploy", placeholder=False),
        item("2", "Lab lifecycle controls", ActionKind.MENU, "lifecycle", placeholder=False),
        item("3", "Configuration editor", ActionKind.VIEW, "configuration_editor"),
        item("4", "Logs", ActionKind.VIEW, "logs"),
        item(
            "5",
            "First-scan one-click demo",
            ActionKind.WORKFLOW,
            "first_scan_demo",
            disabled_reason=FIRST_SCAN_DISABLED_REASON,
        ),
        item("?", "Help Center / Fortify Knowledge Center", ActionKind.VIEW, "help_center"),
        item("m", "More tools", ActionKind.MENU, "more_tools", placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


DEPLOY_MENU = MenuNode(
    id="deploy",
    title="Deploy",
    return_aliases=("r", ""),
    items=(
        item("1", "Guided deployment", ActionKind.WORKFLOW, "guided_deployment", placeholder=False),
        item("2", "Express deployment", ActionKind.WORKFLOW, "express_deployment"),
        item("3", "Resume or repair deployment", ActionKind.WORKFLOW, "resume_or_repair"),
        item("b", "Back", ActionKind.RETURN, "main", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


MORE_TOOLS_MENU = MenuNode(
    id="more_tools",
    title="More tools",
    return_aliases=("r", ""),
    items=(
        item("0", "Setup and readiness", ActionKind.WORKFLOW, "setup_readiness", placeholder=False),
        item("1", "Guided deployment", ActionKind.WORKFLOW, "guided_deployment", placeholder=False),
        item("2", "Express deployment", ActionKind.WORKFLOW, "express_deployment"),
        item("3", "Resume or repair", ActionKind.WORKFLOW, "resume_or_repair"),
        item("4", "Flight Plans", ActionKind.VIEW, "flight_plans"),
        item("5", "App management", ActionKind.MENU, "app_lifecycle", placeholder=False),
        item("6", "Sample apps", ActionKind.MENU, "sample_apps", placeholder=False),
        item("7", "Dashboard access", ActionKind.VIEW, "dashboard_access"),
        item("8", "Diagnostics", ActionKind.VIEW, "diagnostics"),
        item("9", "Advanced setup", ActionKind.WORKFLOW, "advanced_setup"),
        item("10", "Lifecycle controls", ActionKind.MENU, "lifecycle", placeholder=False),
        item("11", "Logs", ActionKind.VIEW, "logs"),
        item("12", "Cluster snapshot", ActionKind.VIEW, "cluster_snapshot"),
        item("13", "URLs and credentials", ActionKind.VIEW, "urls_credentials"),
        item("14", "FCLI readiness", ActionKind.VIEW, "fcli_readiness"),
        item("15", "Runbook Library", ActionKind.VIEW, "runbook_library"),
        item("16", "Configuration editor", ActionKind.VIEW, "configuration_editor"),
        item("17", "Help Center", ActionKind.VIEW, "help_center"),
        item("18", "Operational guidance", ActionKind.VIEW, "operational_guidance"),
        item("19", "Wizard log", ActionKind.VIEW, "wizard_log"),
        item(
            "20",
            "First-scan one-click demo",
            ActionKind.WORKFLOW,
            "first_scan_demo",
            disabled_reason=FIRST_SCAN_DISABLED_REASON,
        ),
        item("b", "Back", ActionKind.RETURN, "main", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


GUIDED_DEPLOYMENT_WORKFLOW = MenuNode(
    id="guided_deployment",
    title="Guided deployment",
    workflow_boundary=True,
    return_aliases=("r", ""),
    notes=(
        "State machine boundary for profile selection, deployment mode selection, per-step controls, and completion handoff.",
        "M2 models the boundary only; M3 and later milestones wire real operation adapters.",
    ),
    items=(
        item("1", "Profile selection", ActionKind.PLACEHOLDER, "guided_deployment.profile_selection"),
        item("2", "Deployment mode selection", ActionKind.PLACEHOLDER, "guided_deployment.deployment_mode"),
        item("3", "Per-step controls", ActionKind.PLACEHOLDER, "guided_deployment.step_controls"),
        item("4", "Completion handoff", ActionKind.PLACEHOLDER, "guided_deployment.completion_handoff"),
        item("b", "Back", ActionKind.RETURN, "deploy", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


SETUP_READINESS_WORKFLOW = MenuNode(
    id="setup_readiness",
    title="Initial setup and readiness",
    workflow_boundary=True,
    return_aliases=("r", ""),
    notes=(
        "State machine boundary for guided setup steps and complete lab reset tiers.",
    ),
    items=(
        item("1", "Guided setup steps", ActionKind.PLACEHOLDER, "setup_readiness.guided_steps"),
        item("2", "Complete lab reset tiers", ActionKind.PLACEHOLDER, "setup_readiness.reset_tiers"),
        item("b", "Back", ActionKind.RETURN, "main", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


LIFECYCLE_MENU = MenuNode(
    id="lifecycle",
    title="Lab lifecycle controls",
    return_aliases=("r", ""),
    notes=("M2 names the lifecycle boundary only; M3 will wire operation adapters.",),
    items=(
        item("1", "Start lab", ActionKind.PLACEHOLDER, "lifecycle.start_lab"),
        item("2", "Stop lab", ActionKind.PLACEHOLDER, "lifecycle.stop_lab"),
        item("3", "Restart lab", ActionKind.PLACEHOLDER, "lifecycle.restart_lab"),
        item("4", "Reset lab", ActionKind.PLACEHOLDER, "lifecycle.reset_lab"),
        item("b", "Back", ActionKind.RETURN, "main", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


APP_LIFECYCLE_MENU = MenuNode(
    id="app_lifecycle",
    title="App lifecycle",
    return_aliases=("r", ""),
    items=(
        item("1", "MySQL", ActionKind.PLACEHOLDER, "app_lifecycle.mysql"),
        item("2", "PostgreSQL", ActionKind.PLACEHOLDER, "app_lifecycle.postgresql"),
        item("3", "SSC", ActionKind.PLACEHOLDER, "app_lifecycle.ssc"),
        item("4", "LIM", ActionKind.PLACEHOLDER, "app_lifecycle.lim"),
        item("5", "ScanCentral SAST", ActionKind.PLACEHOLDER, "app_lifecycle.scancentral_sast"),
        item("6", "ScanCentral DAST", ActionKind.PLACEHOLDER, "app_lifecycle.scancentral_dast"),
        item("7", "Juice Shop", ActionKind.PLACEHOLDER, "app_lifecycle.juice_shop"),
        item("8", "WebGoat", ActionKind.PLACEHOLDER, "app_lifecycle.webgoat"),
        item("9", "DVWA", ActionKind.PLACEHOLDER, "app_lifecycle.dvwa"),
        item("b", "Back", ActionKind.RETURN, "more_tools", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


SAMPLE_APPS_MENU = MenuNode(
    id="sample_apps",
    title="Sample apps",
    return_aliases=("r", ""),
    items=(
        item("1", "Juice Shop", ActionKind.PLACEHOLDER, "sample_apps.juice_shop"),
        item("2", "WebGoat", ActionKind.PLACEHOLDER, "sample_apps.webgoat"),
        item("3", "DVWA", ActionKind.PLACEHOLDER, "sample_apps.dvwa"),
        item("b", "Back", ActionKind.RETURN, "more_tools", aliases=("r", "escape", ""), placeholder=False),
        item("q", "Quit", ActionKind.QUIT, "process", placeholder=False),
    ),
)


WORKFLOW_PLACEHOLDERS = (
    GUIDED_DEPLOYMENT_WORKFLOW,
    SETUP_READINESS_WORKFLOW,
)


MENU_TREE = (
    MAIN_MENU,
    DEPLOY_MENU,
    MORE_TOOLS_MENU,
    GUIDED_DEPLOYMENT_WORKFLOW,
    SETUP_READINESS_WORKFLOW,
    LIFECYCLE_MENU,
    APP_LIFECYCLE_MENU,
    SAMPLE_APPS_MENU,
)
