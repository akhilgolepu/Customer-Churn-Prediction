# MLOps Docs Index

Date: 2026-04-12
Project: Customer Churn Predictor

## Recommended Reading Order

1. Start here: project execution order and operating rules

- [MLOps Execution Playbook](mlops_execution_playbook.md)

2. Understand target maturity and finish line

- [MLOps 100% Milestone Goals](mlops_100_percent_milestone_goals.md)

3. Check live implementation status and next gaps

- [MLOps Implementation Tracker](mlops_implementation_tracker.md)

4. Understand testing and CI/security validation policy

- [Formal Testing Program](testing_program.md)

5. Reference concept map and capability catalog

- [MLOps Concepts](mlops_concepts.md)

## Quick Use by Role

1. Product/Owner

- Read: Playbook, Milestone Goals, Implementation Tracker.
- Purpose: roadmap, risk, release confidence.

2. ML Engineer

- Read: Playbook, Testing Program, Implementation Tracker.
- Purpose: validation order, artifact discipline, promotion readiness.

3. Backend/Platform Engineer

- Read: Playbook, Testing Program, Implementation Tracker.
- Purpose: CI/CD/security gates, runtime safety, operations.

4. Reviewer/Auditor

- Read: Milestone Goals, Implementation Tracker, Testing Program.
- Purpose: evidence of controls and remaining compliance gaps.

## Operational Rule

Use the execution order in the playbook as the source of truth when deciding what to implement next. If any tracker/goals item conflicts with runtime safety, follow the playbook order first.
