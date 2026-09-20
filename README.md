````markdown
# DecodeIt — Project Setup Guide

This guide will help you set up the project locally and contribute changes safely.

## 1. Clone the Repository

Open a terminal and run:

```bash
git clone https://github.com/Saurabhlodha29/DecodeIt.git
cd DecodeIt
````

Then open the project in VS Code:

```bash
code .
```

---

## 2. Create a Virtual Environment

Create a separate Python environment for this project:

### Windows

```bash
python -m venv .venv
```

Activate it:

```bash
.venv\Scripts\activate
```

You should now see something like:

```text
(.venv)
```

at the beginning of your terminal.

> **Important:** Each team member creates their own `.venv` locally. We do **not** push `.venv` to GitHub.

---

## 3. Select the Virtual Environment in VS Code

In VS Code:

```text
Ctrl + Shift + P
        ↓
Python: Select Interpreter
        ↓
Select .venv
```

After selecting it, open a **new terminal** in VS Code.

Check that the environment is active:

```bash
python --version
```

VS Code uses the selected interpreter for running, debugging, and Python language features.
[VS Code Python environments](https://code.visualstudio.com/docs/python/environments)

---

## 4. Install Project Requirements

Make sure your virtual environment is activated, then run:

```bash
pip install -r requirements.txt
```

Whenever a new dependency is added to the project, update `requirements.txt` so that other team members can install the same dependencies.

To update the file from your current environment:

```bash
pip freeze > requirements.txt
```

---

## 5. Maintain `.gitignore`

The `.gitignore` file tells Git which files should **not** be uploaded to GitHub.

For this Python project, make sure it contains at least:

```gitignore
# Virtual environment
.venv/
venv/

# Python
__pycache__/
*.py[cod]

# Environment variables / secrets
.env
.env.*

# VS Code
.vscode/

# Jupyter
.ipynb_checkpoints/

# OS files
.DS_Store
Thumbs.db
```

### Never commit:

* `.venv/`
* `.env`
* API keys
* passwords
* secret tokens
* personal configuration files

The `.gitignore` file itself **should be committed** so that everyone on the team follows the same rules.

---

# 6. Before Starting Your Work

Always get the latest version of the project:

```bash
git pull origin main
```

Then create your own branch:

```bash
git checkout -b feature/your-feature-name
```

Example:

```bash
git checkout -b feature/github-ingestion
```

Work on your feature in this branch.

---

# 7. Check Your Changes

Before committing:

```bash
git status
```

Review what changed.

You can also see the actual changes with:

```bash
git diff
```

Make sure you are **not accidentally adding**:

* `.venv/`
* `.env`
* API keys
* large unnecessary files
* generated/cache files

---

# 8. Add and Commit Your Changes

Add the files you want to commit:

```bash
git add .
```

Check what will be committed:

```bash
git status
```

Then commit:

```bash
git commit -m "Add GitHub repository ingestion"
```

Keep commit messages short and descriptive.

Examples:

```text
Add code parser
Fix repository ingestion
Add LangGraph workflow
Add Supabase database setup
Update project documentation
```

---

# 9. Push Your Branch

Push your branch to GitHub:

```bash
git push -u origin feature/your-feature-name
```

After this, your branch will appear on GitHub.

---

# 10. Create a Pull Request

On GitHub:

```text
Your Branch
     ↓
Create Pull Request
     ↓
Review
     ↓
Merge into main
```

**Do not directly push unfinished work to `main`.**

After your Pull Request is merged, update your local `main`:

```bash
git checkout main
git pull origin main
```

Then create a new branch for your next task:

```bash
git checkout -b feature/next-feature
```

---

# 🔄 Daily Git Workflow

For most tasks, follow this sequence:

```bash
# 1. Get latest main
git checkout main
git pull origin main

# 2. Create your feature branch
git checkout -b feature/your-feature

# 3. Activate environment
.venv\Scripts\activate

# 4. Work on your code
# ...

# 5. Check changes
git status
git diff

# 6. Commit
git add .
git commit -m "Describe your change"

# 7. Push
git push -u origin feature/your-feature

# 8. Create Pull Request on GitHub
```

---

## ⚠️ Important Team Rules

1. **Never commit API keys or passwords.**
2. **Never commit `.venv/`.**
3. **Don't directly push unfinished work to `main`.**
4. **Pull the latest `main` before starting new work.**
5. **Use a separate branch for each feature/fix.**
6. **Write meaningful commit messages.**
7. **Update `requirements.txt` when adding dependencies.**
8. **Keep your changes focused on your assigned task.**

### Basic Workflow

```text
Clone
  ↓
Create .venv
  ↓
Select .venv in VS Code
  ↓
Install requirements
  ↓
Pull latest main
  ↓
Create feature branch
  ↓
Write code
  ↓
git status / git diff
  ↓
git add
  ↓
git commit
  ↓
git push
  ↓
Pull Request
  ↓
Review & Merge
```

> **Tip:** If you are unsure whether a file should be committed, ask before pushing it.

```

The repository currently has `README.md` and `.gitignore` on the `main` branch, so this structure can be added directly to the README.

The `.gitignore` and virtual-environment practices above also follow GitHub and VS Code's current guidance.
```