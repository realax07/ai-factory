# -*- coding: utf-8 -*-
"""J52 волна 2 «контракты в промпты ролей» (J52 п.4-6/8).

Корневой вывод разбора 2026-10-18 (подтвержден Заказчиком): ПМ не должен
быть носителем контрактов — стоячие контракты вшиваются в системные
промпты ролей. Тесты ниже — строковые assertion: контракты не должны
молча исчезнуть при синке промптов (правка/перезапись agents/*.md
ломает ворота, зависящие от этих форматов).

Трассировка:
  TC-J52-020  dev: контракт «баг-репорт BUG-NNN с разделом Статус —
              часть коммита багфикса, не воспоминание» в промпте
  TC-J52-021  dev: контракт «ветка/worktree — только из ALLOW prepare;
              коммиты в ТЕКУЩУЮ делегированную ветку» в промпте
  TC-J52-022  code_reviewer: машиночитаемый вердикт «## Вердикт:
              approve|return» заголовком в промпте
  TC-J52-023  code_reviewer: мета «Reviewer-Delegation: deleg_<id>»
              вплотную (deleg_) в промпте
  TC-J52-024  code_reviewer: review-mapping.json при нескольких задачах
              в промпте
  TC-J52-025  regress_runner: freeze tooling — после regress-final не
              коммитить scripts/**, .github/** до merge
  TC-J52-026  README-flow-control: секция про формат ревью-мет/маппинг
              (J10) синхронна с промптом code_reviewer
  TC-J52-027  формат в промптах согласован с реальными парсерами ворот
              (flow_check: VERDICT_LINE_RE, REVIEWER_META_RE) — примеры
              строк из промптов матчатся
"""
from __future__ import annotations

import re
from pathlib import Path

FACTORY = Path(__file__).resolve().parent.parent
AGENTS = FACTORY / "agents"
DOCS = FACTORY / "docs"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


# ------------------------------------------------------------ dev (п.6)

class TestDevContracts:
    def test_bug_report_part_of_bugfix_commit(self):
        """TC-J52-020: контракт баг-репорта (Флоу 2) — в промпте dev."""
        text = _read(AGENTS / "dev_agent.md")
        assert "test-model/bugs/BUG-NNN-*.md" in text
        assert "часть коммита багфикса" in text
        assert "не воспоминание" in text
        assert "«Статус»" in text

    def test_branch_worktree_from_allow_prepare(self):
        """TC-J52-021: контракт ветки/worktree — в промпте dev."""
        text = _read(AGENTS / "dev_agent.md")
        assert "только из ALLOW prepare" in text
        assert "ТЕКУЩУЮ делегированную ветку" in text


# ------------------------------------------------- code_reviewer (п.5)

class TestCodeReviewerContracts:
    def test_verdict_heading_format(self):
        """TC-J52-022: машиночитаемый вердикт-заголовок — в промпте."""
        text = _read(AGENTS / "code_reviewer_agent.md")
        assert "## Вердикт: approve" in text
        assert "## Вердикт: return" in text
        # Форма «approve|return» зафиксирована (канон формата).
        assert "approve|return" in text

    def test_reviewer_delegation_meta(self):
        """TC-J52-023: мета делегации вплотную deleg_<id> — в промпте."""
        text = _read(AGENTS / "code_reviewer_agent.md")
        assert "Reviewer-Delegation: deleg_<id>" in text
        # «вплотную» (deleg_ без пробела/дефиса) — требование проговорено.
        assert "вплотную" in text

    def test_review_mapping_for_multiple_tasks(self):
        """TC-J52-024: review-mapping.json при нескольких задачах."""
        text = _read(AGENTS / "code_reviewer_agent.md")
        assert "review-mapping.json" in text


# ----------------------------------------------- regress_runner (п.3/8)

class TestRegressRunnerContracts:
    def test_freeze_tooling_after_regress_final(self):
        """TC-J52-025: freeze tooling — после regress-final tooling-пути
        scripts/** и .github/** не коммитятся до merge."""
        text = _read(AGENTS / "regress_runner_agent.md")
        assert "regress-final" in text
        assert "scripts/**" in text
        assert ".github/**" in text
        assert "не коммитятся" in text
        assert "До merge" in text


# ------------------------------------------------------- README (п.4)

class TestFlowControlReadme:
    def test_review_meta_format_section(self):
        """TC-J52-026: README-flow-control несет секцию формата ревью-мет/
        маппинг (J10) — синхронно с промптом code_reviewer."""
        text = _read(DOCS / "README-flow-control.md")
        for line in (
            "## Вердикт: approve",
            "## Вердикт: return",
            "Reviewer-Delegation: deleg_<id>",
            "review-mapping.json",
        ):
            assert line in text, line


# -------------------------------- согласованность с парсерами ворот

class TestFormatsMatchGateParsers:
    def test_prompt_examples_match_flow_check_regexes(self):
        """TC-J52-027: канонические строки формата из промптов матчатся
        реальными regex'ами ворот flow_check — промпт и машина о TOM же."""
        sys_path_setup = str(FACTORY / "scripts")
        import sys
        if sys_path_setup not in sys.path:
            sys.path.insert(0, sys_path_setup)
        import flow_check

        sample_review = (
            "# Ревью\n\n"
            "Reviewer-Delegation: deleg_j52w2rev01\n"
            "\n"
            "## Вердикт: approve\n"
        )
        assert flow_check.parse_verdict(sample_review) == "approve"
        m = flow_check.REVIEWER_META_RE.search(sample_review)
        assert m and m.group(1) == "deleg_j52w2rev01"
        # return-вердикт тоже читается.
        assert flow_check.parse_verdict(
            "## Вердикт: return\n") == "return"
