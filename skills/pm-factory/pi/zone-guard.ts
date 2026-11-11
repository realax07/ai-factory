/**
 * zone-guard — зоны записи и запреты роли для исполнителя Pi (extension).
 *
 * Эталон один: skills/pm-factory/pi/zone-guard.ts (J64.10). Пакетный раннер
 * (scripts/package_runner.py) подключает его прямо из репо фабрики
 * (`pi -e <фабрика>/skills/pm-factory/pi/zone-guard.ts`): нет файла — STOP
 * стадии, sha256 guard'а пишется в отчет стадии. Копия в
 * ~/.pi/agent/extensions/zone-guard.ts нужна только для ручных запусков по
 * README паков; ставит ее factory_bootstrap (расхождение с репо — WARN).
 *
 * Настройка — env процесса pi (раннер ставит все три):
 *   PI_ZONE_WRITE      зоны записи через ':' — префикс-форма относительно
 *                      cwd (корня worktree): `src`, `tests/unit`,
 *                      `code-reviews/x/review-*.md` (glob-хвост раннер
 *                      срезает, J61). Не задан или пуст — запись запрещена
 *                      целиком (fail-closed).
 *   PI_ZONE_ROLE       роль политики (agents/roles.json: dev, devops,
 *                      regress_runner, …) — выбирает bash-правила.
 *   PI_ZONE_GUARD_LOG  файл лога отказов — ВНЕ worktree (раннер: state
 *                      фабрики). Не задан — ~/.pi/agent/zone-guard.log.
 *
 * Что охраняет (fail-closed):
 *   1. write/edit — только внутри зон PI_ZONE_WRITE; путь без path, вне
 *      worktree или вне зон — отказ.
 *   2. bash — `git push` запрещен всем ролям (пушит ПМ после приемки).
 *   3. bash — docker-мутации (run/exec/rm/build/compose up|down/…) запрещены
 *      всем ролям, кроме devops (решение Заказчика 2026-11-11, J64.10);
 *      чтение (ps/inspect/logs/images/version/info/stats/top/events) — всем.
 *
 * Отказ: { block: true, reason } модели + строка в лог + ui.notify, если UI
 * есть. Ошибка обработчика тоже блокирует tool call (fail-safe самого pi).
 *
 * Ограничение (честно): bash-канал — эвристика по строке команды
 * (редиректы/tee/mv мимо зон НЕ парсятся). Механическая граница записи —
 * сверка git diff с зоной на finish стадии у раннера (J63); guard — ранняя
 * подсказка агенту, его обход стоит итераций, а не дыры в зоне.
 *
 * Формат — доки pi (pi.dev/docs/latest/extensions): фабрика, получающая
 * ExtensionAPI; jiti грузит TS без компиляции; перехват — событие
 * "tool_call", блок = { block: true, reason }.
 */

import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { promises as fs } from "node:fs";
import * as os from "node:os";
import * as path from "node:path";

/** Роли, которым разрешены docker-мутации (J64.10). */
const DOCKER_MUTATION_ROLES = new Set(["devops"]);

export default function (pi: ExtensionAPI) {
	const writeZones = (process.env.PI_ZONE_WRITE ?? "")
		.split(":")
		.map((z) => z.trim().replace(/^\.\//, "").replace(/\/+$/, ""))
		.filter(Boolean);
	const role = (process.env.PI_ZONE_ROLE ?? "").trim() || "unknown";
	const logFile = (process.env.PI_ZONE_GUARD_LOG ?? "").trim() ||
		path.join(os.homedir(), ".pi", "agent", "zone-guard.log");

	async function log(line: string): Promise<void> {
		const stamp = new Date().toISOString();
		try {
			await fs.mkdir(path.dirname(logFile), { recursive: true });
			await fs.appendFile(logFile, `[${stamp}] role=${role} ${line}\n`, "utf8");
		} catch {
			// лог best-effort: отказ все равно уже вынесен
		}
	}

	/** Сегмент зоны с glob ('*', '?') — сопоставление внутри одного сегмента. */
	function segMatch(zoneSeg: string, seg: string): boolean {
		if (!/[*?]/.test(zoneSeg)) return zoneSeg === seg;
		const re = new RegExp(
			"^" + zoneSeg.replace(/[.+^${}()|[\]\\]/g, "\\$&")
				.replace(/\*/g, "[^/]*").replace(/\?/g, "[^/]") + "$",
		);
		return re.test(seg);
	}

	/** Путь в зоне: сегменты зоны — префикс сегментов пути. */
	function inZone(norm: string, zone: string): boolean {
		const zs = zone.split("/");
		const ps = norm.split("/");
		if (ps.length < zs.length) return false;
		return zs.every((z, i) => segMatch(z, ps[i]));
	}

	function inWriteZone(target: string, cwd: string): boolean {
		const rel = path.relative(cwd, path.resolve(cwd, target));
		if (rel === "" || rel.startsWith("..") || path.isAbsolute(rel)) return false;
		const norm = rel.split(path.sep).join("/");
		return writeZones.some((z) => inZone(norm, z));
	}

	const GIT_PUSH = /(^|[\s;&|(])git(\s+\S+)*\s+push\b/;
	const DOCKER_MUTATING = /\bdocker(?:\s+compose)?\s+(run|exec|rm|rmi|stop|kill|restart|pause|unpause|build|pull|push|cp|save|load|tag|import|export|commit|attach|system|volume|network|secret|config|up|down|create|update|scale|start|swarm|node|stack|prune|login|logout)\b/;
	// Чтение (ps/inspect/logs/images/version/info/stats/top/events) мутацией не
	// считается. Совпадение чтения мутацию НЕ снимает: `docker ps && docker rm x`
	// — отказ (прежний guard пропускал такую команду).

	async function block(kind: string, detail: string, reason: string, ctx: any) {
		await log(`BLOCK ${kind} ${detail}`);
		if (ctx?.hasUI) ctx.ui.notify(`zone-guard: отказ — ${kind}`, "warning");
		return { block: true, reason };
	}

	pi.on("tool_call", async (event: any, ctx: any) => {
		const cwd = ctx?.cwd ?? process.cwd();

		if (event.toolName === "write" || event.toolName === "edit") {
			const target = (event.input?.path as string | undefined) ?? "";
			const zones = writeZones.join(", ") || "— (PI_ZONE_WRITE не задан: запись запрещена)";
			if (!target) {
				return block(event.toolName, ":: нет path",
					`${event.toolName}: не указан path — блокирую fail-closed (зона роли ${role}: ${zones})`, ctx);
			}
			if (!inWriteZone(target, cwd)) {
				return block(event.toolName, `${target} :: вне зоны`,
					`zone-guard: запись «${target}» вне зоны роли ${role}. ` +
					`Разрешены только (относительно ${cwd}): ${zones}. ` +
					`Остальное — через ПМ; коммитит/пушит ПМ.`, ctx);
			}
			return undefined;
		}

		if (event.toolName === "bash") {
			const cmd = (event.input?.command as string | undefined) ?? "";
			if (!cmd) return undefined;
			if (GIT_PUSH.test(cmd)) {
				return block("bash git-push", `:: ${cmd.slice(0, 200)}`,
					`zone-guard: \`git push\` запрещен роли ${role} — пушит ПМ после приемки.`, ctx);
			}
			if (!DOCKER_MUTATION_ROLES.has(role) && DOCKER_MUTATING.test(cmd)) {
				return block("bash docker-mutation", `:: ${cmd.slice(0, 200)}`,
					`zone-guard: docker-мутации запрещены роли ${role} (разрешены только devops). ` +
					`Чтение: docker ps/inspect/logs/images/version/info/stats/top.`, ctx);
			}
			return undefined;
		}

		return undefined;
	});
}
