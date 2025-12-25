# Project Antigravity - GEMINI.md

## Pre-Flight Protocol

### Bootstrapping
**CRITICAL:** You are running in a manual, periodic session. Your FIRST action is always a **System Audit**. Scan the project root (`requirements.txt`, `.env`, `docker-compose.*.yml`, etc.) to identify the current tech stack, dependencies, and environment variables. Do not proceed with code generation until you have grounded your context in these actual files.

### Context Hierarchy
Prioritize the instructions in this `.md` file and the codebase state over your general training data. If a conflict arises between this file and the code, ask for clarification.

---

## Tech Stack Summary

- **Language:** Python 3.x (Flask-based web application)
- **Framework:** Flask 3.1.x with Flask-HTTPAuth
- **Dependencies:** paho-mqtt, pydantic, python-dotenv, requests, PyYAML, xxtea, astral, tzlocal
- **Containerization:** Docker with docker-compose
- **Environment:** `.env` file for versioning and SDK configuration

---

## Autonomous Git & GitHub Protocol

### Atomic Logic
Work in small, logical units. Do not attempt to refactor the entire codebase in one turn.

### Completion Trigger
Once a feature, bug fix, or logical unit of work is complete, you must commit all files with a `git commit` message following **Conventional Commits** specifications. Push to origin if origin exists. If the branch doesn't exist at origin, create it.

---

## Engineering Standards

### No Placeholders
Never use comments like `// rest of code here` or `....`. You must write the full implementation.

### Defensive Coding
Assume inputs are malicious. Implement strict type checks and comprehensive error handling.

### DRY Principle
Do not duplicate logic. Refactor repetition into shared utilities.

---

## Output Efficiency (The "No-Yapping" Protocol)

### Conciseness
Minimize conversational filler. Do not apologize for errors; simply fix them.

### Diff-Based Editing
Prefer showing the Diff or the specific code block changed rather than reprinting the entire file, unless a full reprint is safer for context.

---

## Session State Management

### The 'Hand-Off'
At the end of a significant task, provide a **Session Summary** listing:
- **Current Status:** Where the project stands
- **Active Bugs:** Known issues or regressions
- **Next Actions:** Recommended next steps
