# EPIC-08 --- Security, RBAC & Audit

## Цель

AI-агент не должен автоматически наследовать полный доступ
пользователя/backend.

## RBAC

Минимум: Viewer, Developer, Operator, Admin.

Разделить права на просмотр, draft editing, promotion, run, sensitive
payload/PII, tools и permissions.

## Agent Permissions

Каждая AgentVersion имеет явный allowlist capabilities/tools.

## Requirements

SSO, secret management, encryption, PII masking, retention, audit,
quotas/rate limits, payload limits, отдельные permissions для mutating
tools.

## Audit

Кто создал/изменил draft, promoted version, изменил tool permissions,
вручную запустил Run, выполнил admin change.

## Acceptance Criteria

-   Unauthorized tool call невозможен.
-   Secret не появляется в trace/log/UI.
-   Promotion отражается в audit.
-   Sensitive payload имеет отдельный access check.
-   Retention удаляет payload без потери необходимой audit metadata.
