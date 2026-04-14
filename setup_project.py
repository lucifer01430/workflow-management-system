from pathlib import Path

PROJECT_NAME = "Workflow Management System"

FOLDERS = [
    "apps",
    "templates/base",
    "templates/landing",
    "templates/accounts",
    "templates/dashboard",
    "templates/tasks",
    "templates/reports",
    "templates/includes",
    "static/css",
    "static/js",
    "static/images",
    "static/vendor",
    "media/profiles",
    "media/task_attachments",
    "media/reports",
    "requirements",
    "docs/planning",
    "docs/references",
]

FILES = {
    ".gitignore": """venv/
env/
__pycache__/
*.pyc
db.sqlite3
.env
media/
staticfiles/
.idea/
.vscode/
.DS_Store
""",

    ".env.example": """DEBUG=True
SECRET_KEY=your-secret-key-here
ALLOWED_HOSTS=127.0.0.1,localhost
EMAIL_HOST=smtp.example.com
EMAIL_PORT=587
EMAIL_HOST_USER=your-email@example.com
EMAIL_HOST_PASSWORD=your-email-password
EMAIL_USE_TLS=True
DEFAULT_FROM_EMAIL=your-email@example.com
""",

    "README.md": f"""# {PROJECT_NAME}

A role-based workflow and task management system for structured inter-department coordination, approvals, tracking, and reporting.

## Planned Stack
- Frontend: HTML, CSS, Bootstrap, JavaScript
- Backend: Python, Django
- Admin Panel: Jazzmin
- Dashboards: AdminLTE

## Roles
- Super Admin
- General Manager
- HOD
- Employee

## Initial Project Structure
- apps/
- templates/
- static/
- media/
- requirements/
- docs/

## Notes
This project is being built phase by phase with proper Git commits and modular architecture.
""",

    "docs/PROJECT_ROADMAP.md": """# Project Roadmap

## Phase 0
- Initial folder structure
- Git setup
- Django installation
- Settings structure

## Phase 1
- Custom user model
- Authentication
- Role system
- Department and employee profile setup

## Phase 2
- Task system
- Approval flow
- Task assignment
- Status and comments

## Phase 3
- Dashboards
- Notifications
- Reports
- Export to PDF/Excel

## Phase 4
- UI/UX refinement
- Reusability improvements
- Deployment preparation
""",

    "docs/MODULES.md": """# Planned Modules

## Core Modules
- Accounts
- Departments
- Employees
- Tasks
- Approvals
- Dashboard
- Notifications
- Reports
- Audit Logs
- Core Utilities
""",

    "docs/CHANGELOG.md": """# Changelog

## Initial
- Created base project structure
- Added docs
- Added README
- Added gitignore
"""
}


def create_folders(base_path: Path) -> None:
    for folder in FOLDERS:
        folder_path = base_path / folder
        folder_path.mkdir(parents=True, exist_ok=True)
        print(f"[OK] Folder created: {folder}")


def create_files(base_path: Path) -> None:
    for file_name, content in FILES.items():
        file_path = base_path / file_name
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(content, encoding="utf-8")
        print(f"[OK] File created: {file_name}")


def main() -> None:
    base_path = Path.cwd()
    print(f"Creating project structure in: {base_path}")
    print("-" * 50)

    create_folders(base_path)
    create_files(base_path)

    print("-" * 50)
    print("[DONE] Project structure created successfully.")


if __name__ == "__main__":
    main()