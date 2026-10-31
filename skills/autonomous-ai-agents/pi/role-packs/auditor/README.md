# Ролевой пак Pi: auditor (ручной вызов)

Аудитор с большим контекстом (Kimi K3.1) для разовых аудит-задач ПМ.
**Вне конвейера**: во флоу/ворота не встроен, вызывается только ПМ вручную.

## Сборка
1. Провайдер в `~/.pi/agent/models.json` — блок `"moonshot"` (endpoint Moonshot
   OpenAI-совместимый, модель `kimi-k3.1`, ключ — от Заказчика, chmod 600).
2. `cp settings.example.json ~/.pi/agent/settings.json.auditor` (НЕ поверх
   regress-runner: у ролей разные settings; вызов с флагами ниже).
3. `cp extensions/auditor-readonly.ts ~/.pi/agent/extensions/` — грузится всегда;
   guard блокирует write/edit и bash-мутации (git push/commit, docker-мутации,
   rm/tee/редиректы, пакетные менеджеры, systemctl/crontab).

## Вызов (не меняя settings regress-runner)
```bash
cd <репо-клон>
pi --provider moonshot --model kimi-k3.1 --no-session \
   --agent-dir ~/.pi/agent-auditor -p "<область аудита и критерии вердикта>"
```
Либо одноразово: скопировать role-agents.md в корень клона как AGENTS.md —
Pi подхватит как контекст. Результат — вердикт в stdout (факты → атрибуция →
severity → рекомендации); агент ничего не пишет на диск.
