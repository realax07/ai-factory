# Tasks: remove-qa-checklist

- [ ] 1.1 Фабрика: flow_transition — Stage qa_checklist удален, check_qa_cases — вход от спеки без чеклиста
- [ ] 1.2 Фабрика: flow_check — валидация чеклистов удалена, трассировка кейсов к Requirement/Scenario
- [ ] 1.3 Фабрика: pr_validate — чеклист удален из обязательного набора change-PR
- [ ] 1.4 Фабрика: role_zone_policy — роль/зона qa_checklist удалена
- [ ] 1.5 Фабрика: contracts (artifact_contract, flow_control_contract) — граф без qa_checklist
- [ ] 1.6 Фабрика: agents — qa_case_author (вход = спека), qa_case_reviewer (оси: покрытие/негатив/дефекты спеки), README-реестр без qa_checklist, промпт в archive/
- [ ] 1.7 Фабрика: openspec-дельта (этот пакет) + validate --strict
- [ ] 1.8 Фабрика: тесты — qa_cases без чеклиста ALLOW; трассировка к Req ALLOW; без трассировки — дефект; STAGE_TABLE без qa_checklist
- [ ] 2.1 Проект: flow_check.py + промпты скопированы с sha-шапками, чеклисты → test-model/checklists/archive/
- [ ] 2.2 Проект: flow_check OK, openspec validate --strict зеленый
