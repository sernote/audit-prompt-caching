# Спецификация: dynamic tools и границы provider-dashboard evidence

Дата: 2026-08-23

Окно исследуемых публикаций: 2026-08-17—2026-08-22

Статус: готово к реализации

Целевая база: `origin/main@99f3ea9`

Приоритет исходной идеи: P1

## Task 1: Реализовать dynamic tools и aggregate provider evidence

## Решение

Изменение нужно, но объём меньше, чем предполагала исходная формулировка:

- Vercel/OpenAI Responses — подтверждённый wrapper-specific gap. Общий совет про allowed tools в скилле уже есть, но без wire mapping, version scope и failure behavior он недостаточен для безопасной рекомендации.
- OpenAI Prompt Caching dashboard — подтверждённое, но инкрементальное улучшение evidence contract. Dashboard UI и документированный Usage API — разные источники: у первого публично не раскрыты формулы, второй даёт явную token decomposition.

Measurement change: yes.

Prompt behavior change: no — меняется руководство скилла.

Provider/routing change: no.

Confidence: high для Vercel, medium-high для dashboard evidence.

## Поправка к хронологии

`allowedTools` не появился на неделе 17–22 августа:

- базовая поддержка OpenAI Responses добавлена 2026-05-05: https://github.com/vercel/ai/commit/29e6ac6f1ffe0eaed2aa937c8a1657e90d3d8411
- недельное изменение — исправление mapping для built-in/provider-defined/custom/MCP tools от 2026-08-18: https://github.com/vercel/ai/commit/a062795bbe22ecc96a38d114bf8b8ea4af070914
- исправленное поведение опубликовано в `@ai-sdk/openai 4.0.43` 2026-08-18;
- v6 backport https://github.com/vercel/ai/pull/19051 опубликован в `3.0.98`; базовая функция в этой line появилась в `3.0.62`;
- в AI SDK v5 / `@ai-sdk/openai 2.x` проверенный Responses options schema не содержит `allowedTools`. Нельзя обещать, что переданный unknown provider option дошёл до wire: фактическое parsing/stripping проверяется fixture-тестом.

Version/capability matrix:

| `@ai-sdk/openai` line | Availability | Corrected provider-tool mapping |
| --- | --- | --- |
| `2.x` / AI SDK v5 | `allowedTools` отсутствует в проверенном schema | неприменимо; не убирать `activeTools` restriction без другого доказанного механизма |
| `3.x` / AI SDK v6 | доступно с `3.0.62` | `>=3.0.98` |
| `4.x` | доступно в проверенной line | `>=4.0.43` |
| другая/неизвестная line | установить по lockfile, changelog и wire | не переносить floors между majors |

OpenAI выпустил Prompt Caching dashboard 2026-08-20: https://developers.openai.com/api/docs/changelog

Usage API completions описывает time-bucketed aggregate usage и поля cached/write/uncached tokens: https://developers.openai.com/api/reference/resources/admin/subresources/organization/subresources/usage/methods/completions

Официальный OpenAI function-calling guide прямо рекомендует сохранять полный `tools` array и менять `allowed_tools` ради prompt-cache reuse: https://developers.openai.com/api/docs/guides/function-calling

## Нормативная модель Vercel `allowedTools`

Применимость должна быть доказана пятью фактами:

1. используется `openai.responses(...)`, а не Chat Completions;
2. зафиксированы версии `ai` и `@ai-sdk/openai`;
3. release line вообще содержит option — это отдельный availability gate;
4. конкретные model и tool class поддерживают выбранные `allowed_tools` semantics, включая `mode: auto|required`;
5. для provider-defined tools проверена release line с corrected mapping или actual wire behavior.

Правильный cache-preserving pattern:

```text
full stable tools catalog
+ providerOptions.openai.allowedTools changes per step
= stable prompt prefix and narrower callable set
```

`providerOptions.openai.allowedTools` формирует `tool_choice: {type: "allowed_tools", mode, tools}` и переопределяет request-level `toolChoice`.

Wire mapping:

| Tool class | Entry in `allowed_tools.tools` |
| --- | --- |
| function | `{type: "function", name}` |
| custom | `{type: "custom", name}` |
| MCP | `{type: "mcp", server_label}` |
| supported built-in/provider-defined | `{type}` |

Ограничения corrected implementation:

- `tool_search`, `deferLoading` и namespaced tools нельзя выразить в `allowed_tools`; SDK удаляет их из effective allow-list, сохраняет полный `tools` catalog и выдаёт warning;
- если после удаления allow-list пуст, request завершается error, а не становится unrestricted;
- unknown и ambiguous names должны быть видимы в warnings;
- declared tool name имеет приоритет над совпавшим provider-tool name и даёт warning; общий provider name у нескольких tools удаляется из allow-list с warning; unknown name сохраняет прежнее поведение, но теперь даёт warning и может закончиться provider-side error;
- MCP entry разрешает сервер целиком; per-tool restriction внутри MCP требует собственного `allowedTools` механизма MCP tool;
- support нельзя переносить на Chat Completions или произвольный OpenAI-compatible wrapper без wire evidence.

Официальная рекомендация сохранять полный `tools` array максимизирует шанс prompt-cache reuse, но не гарантирует hit: одинаковый wire prefix и `cached_tokens` всё равно нужно измерить. Это также не blanket-запрет `activeTools`: при cold/low-reuse workload меньший передаваемый catalog может быть дешевле, чем стабильный большой catalog с cached billing. Выбор проходит Applicability Gate и AP-4 economics.

## Нормативная модель aggregate provider evidence

OpenAI changelog документирует доступность и следующие metrics:

- cache hit rate over time;
- cache reads per write;
- breakdown cache-read/cache-write/uncached tokens;
- filters by model and service tier.

Публичный changelog не определяет denominators и weighting этих dashboard ratios. Поэтому Dashboard UI — `provider_dashboard_aggregate`, а не request-level ground truth и не доказательство root cause.

Отдельно Organization Usage API документирует `provider_usage_api_aggregate`:

- `input_tokens` включает cached и cache-write tokens;
- `input_cached_tokens` агрегирует cache reads;
- `input_cache_write_tokens` агрегирует cache writes;
- `input_uncached_tokens` исключает cache-write tokens;
- запрос задаёт time buckets и может группироваться по `model`, `project_id`, `api_key_id`, `user_id`, `batch`, `service_tier`.

Для Usage API decomposition/accounting известны, но optional/missing fields, filters, grouping и bucket boundaries всё равно фиксируются. Dashboard UI ratio не выводится автоматически из Usage API без доказательства одинаковой формулы, scope и filters.

Минимальный provenance contract:

```text
evidence_source: provider_dashboard_aggregate | provider_usage_api_aggregate | request_level_provider_usage | gateway_or_replica_telemetry | rendered_prefix_evidence
provider:
time_window:
granularity:
filters:
displayed_metric:
displayed_value:
definition_status: provider_documented | unknown
denominator_status: provider_documented | unknown
accounting_semantics: inclusive | additive | provider_defined | unknown
request_correlation: present | absent
route_correlation: present | absent
```

Для Dashboard UI `definition_status`, `denominator_status` и `accounting_semantics` остаются `unknown`, если конкретная публичная документация не говорит обратного. Для Usage API token fields они `provider_documented` с inclusive/decomposition semantics выше. Нельзя вычислять или нормализовать dashboard ratio, если denominator/accounting semantics не опубликованы. Нельзя смешивать dashboard, Usage API и request-level ratio в одной серии без явной маркировки.

Dashboard подтверждает тренд. Для causal finding всё ещё нужны request-level usage, prompt/tool/schema hashes, SDK/deploy version и actual route/replica evidence.

## Обязательные изменения по файлам

### `audit-prompt-caching/references/vercel-ai-sdk.md`

Обновить review date после повторной проверки источников и добавить раздел `OpenAI Responses allowedTools`:

- stable full `tools` versus changing `activeTools`;
- exact `providerOptions.openai.allowedTools` example;
- Responses-only scope и override `toolChoice`;
- wire mapping table;
- unsupported tool classes, warnings, empty-list error и ambiguity behavior;
- MCP server-level semantics;
- version matrix: 2.x unavailable, 3.x available `>=3.0.62` и corrected `>=3.0.98`, 4.x corrected `>=4.0.43`;
- availability gate отдельно от corrected-mapping gate;
- диагностика: package versions, selected factory, final request body, `tool_choice`, SDK warnings, HTTP status и raw provider usage.

### `audit-prompt-caching/references/agent-tools.md`

Заменить общий совет на wrapper-aware decision rule:

- stable catalog + provider allow-list, если конкретный endpoint/SDK это поддерживает и reuse economics это оправдывает;
- direct OpenAI Responses `allowed_tools` и Vercel `providerOptions.openai.allowedTools` — разные API surfaces;
- Chat Completions и OpenAI-compatible wrappers не наследуют поддержку автоматически;
- cache improvement подтверждается stable tools/prefix hashes и provider usage, а не только уменьшением callable set.

### `audit-prompt-caching/references/openai.md`

Ссылки на prompt caching и function calling в `origin/main` уже есть; не дублировать их. Добавить только Aug 20 dashboard и Usage API, затем зафиксировать:

- известные metrics и filters;
- отдельные evidence types `provider_dashboard_aggregate` и `provider_usage_api_aggregate`;
- unknown formula/denominator только для Dashboard UI, пока OpenAI не документировал их явно;
- документированную Usage API decomposition: inclusive `input_tokens`, cached, write и uncached-excluding-write;
- request-level `cached_tokens`/`cache_write_tokens` и hashes остаются обязательными для causal finding;
- dashboard и per-request ratios нельзя сравнивать как одну метрику без определения accounting semantics.

### `audit-prompt-caching/references/observability.md`

Добавить раздел `Provider aggregate evidence boundary` с provenance contract выше и двумя подтипами evidence.

Сохранить существующее правило inclusive/additive accounting и расширить его: источник, scope, granularity, filters и definition status обязательны перед вычислением ratio.

Нормативная wire mapping table должна жить только в `vercel-ai-sdk.md`. `agent-tools.md`, `SKILL.md` и AP-4 должны ссылаться на wrapper/endpoint decision, не копировать mapping и unsupported-class list.

### `audit-prompt-caching/SKILL.md`

Сделать две короткие правки, не дублируя references:

- в `Dynamic tools in long agent loops` различить direct OpenAI Responses, Vercel provider option и unsupported wrapper/endpoint;
- в evidence types добавить `provider-dashboard aggregate` и `provider-usage-api aggregate`, а также запрет causal claim без request/route correlation.

### `audit-prompt-caching/references/rules.json`

Не добавлять новый ID. Уточнить AP-4:

- `fix`: после Applicability/economics Gate — stable full catalog + endpoint/version-verified allow-list; иначе stable bundle/tool search/deferred loading или меньший stable catalog;
- `avoid`: changing `activeTools`, assuming Responses support on Chat Completions/wrappers, ignoring SDK warnings;
- `validation`: tools/prefix hashes, final wire `tool_choice`, warnings, raw cache usage.

Dashboard evidence не оформлять отдельным anti-pattern: это cross-cutting evidence contract, который принадлежит `observability.md`, report template и evals.

AP-4 не должен безусловно запрещать `activeTools`: он запрещает mutation без измерения prefix/economics. Acceptance зависит от reuse rate, cached/uncached billing, catalog size и latency.

### `audit-prompt-caching/references/report-template.md`

В `Evidence Needed Next` добавить:

```text
Evidence source:
Scope/granularity:
Time window:
Filters:
Metric definition status:
Denominator status:
Accounting semantics:
Request correlation:
Route/replica correlation:
```

Dashboard aggregate и Usage API aggregate должны записываться отдельно друг от друга, от request-level provider usage и от route-level telemetry.

### `audit-prompt-caching/evals/evals.json`

Добавить пять behavioral cases:

1. Vercel OpenAI Responses agent меняет `activeTools`: рекомендовать stable full tools + verified `allowedTools`, проверить wire и warnings;
2. Version matrix: 2.x option unavailable; 3.0.62–3.0.97 base mapping; 3.x corrected from 3.0.98; 4.x corrected from 4.0.43. Не советовать blindly и не снимать active restriction без wire proof;
3. OpenAI dashboard показывает высокий hit rate: классифицировать как Dashboard aggregate corroboration и запросить request-level usage/hashes/routes до causal conclusion;
4. Usage API даёт cached/write/uncached fields: применить documented decomposition, сохранить filters/buckets и не приписывать Dashboard UI ту же формулу;
5. Contrast case: direct OpenAI Responses, Vercel Responses, Azure Responses с api-version gate, Chat Completions и arbitrary OpenAI-compatible wrapper — не переносить `allowedTools` между surfaces без wire evidence.

Vercel evals должны проверять `mode: auto|required` и concrete wire fixtures для function, custom, MCP `server_label` и `web_search`, плюс negative cases для `tool_search`, `deferLoading` и namespaced tools.

### `audit-prompt-caching/evals/trigger_eval.json`

Добавить positive cases для Vercel `activeTools`/`allowedTools` и OpenAI Prompt Caching dashboard. Существующие negative prompt-writing и non-LLM cases не менять.

### `tests/test_prompt_cache_scripts.py`

Сначала добавить failing semantic contract tests:

- wrapper reference содержит Responses-only scope, mapping, warnings и version guard;
- exact version anchors `2.x`, `3.0.62`, `3.0.98`, `4.0.43` и package/lockfile gate присутствуют;
- model/tool capability и `mode: auto|required` входят в applicability gate;
- AP-4 запрещает blind use of `activeTools`;
- observability/report template различают dashboard aggregate, Usage API aggregate, request-level usage и route telemetry;
- provenance contract содержит `denominator_status` и `accounting_semantics`;
- evals покрывают version/wire warning и aggregate-evidence cases;
- contrast eval не переносит Responses behavior на Chat Completions/wrappers;
- contract tests фиксируют `input_tokens` inclusive и `input_uncached_tokens` excluding cache-write только для Usage API;
- negative assertion запрещает дублировать нормативную mapping table за пределами `vercel-ai-sdk.md` и проверяет anchor `toolNames`, чтобы тест не прошёл на unrelated text;
- trigger eval сохраняет positive/negative coverage.

Script behavior не меняется. Не добавлять dashboard scraper, parser или Vercel runtime adapter.

Изменения в существующий dirty test file нужно накладывать поверх пользовательской версии, не заменяя её содержимое.

## Порядок реализации

1. Добавить semantic contract tests/evals и получить RED на missing anchors, mapping fixtures и contrast cases.
2. Обновить Vercel/agent/OpenAI/observability references.
3. Минимально уточнить SKILL, AP-4 и report template.
4. Проверить package/version claims по lockfile и официальным changelog на дату реализации.
5. Получить GREEN на полном наборе tests/package/trigger checks; RED и GREEN сохранить в implementation evidence.

## Non-goals

- Не менять application code или package versions автоматически.
- Не добавлять `allowedTools` в `layout_linter.py`.
- Не утверждать support для Chat Completions, arbitrary wrappers или всех majors.
- Не утверждать, что unknown provider option в 2.x обязательно дошёл до wire или обязательно был silently stripped без fixture evidence.
- Не скрейпить dashboard и не выдумывать его formulas.
- Не преобразовывать dashboard aggregates в request-level events.
- Не считать dashboard trend доказательством prompt drift, routing miss или конкретного SDK regression.
- Не менять provider/routing behavior репозитория скилла.

## Acceptance criteria

- История May introduction и Aug 18 corrected mapping разделена.
- Для corrected 4.x behavior указан `@ai-sdk/openai >=4.0.43`; другие lines требуют отдельной проверки.
- Для 3.x разделены availability `>=3.0.62` и corrected mapping `>=3.0.98`; для 2.x option считается unavailable по проверенному schema.
- Рекомендация звучит как `stable full tools + dynamic allowedTools`, а не mutation `activeTools`.
- Direct OpenAI, Vercel, Chat Completions и wrapper scopes не смешаны.
- Все четыре wire shapes и unsupported classes описаны.
- Model/tool capability и `mode` проверяются до рекомендации.
- Empty effective allow-list не может незаметно расширить tool access.
- Dashboard evidence помечено aggregate; его `definition_status`, `denominator_status` и `accounting_semantics` остаются unknown без документации.
- Usage API aggregate — отдельный source с документированной token decomposition; его не смешивают с формулой Dashboard UI.
- Causal finding требует request-level и route-level correlation.
- Direct OpenAI, Vercel, Chat Completions и arbitrary wrapper различаются отдельным contrast eval.
- Нормативная wire mapping table существует в одном месте — `vercel-ai-sdk.md`; остальные файлы содержат только routing/decision pointers.
- Новые evals ловят prefix mutation, blind version assumption и aggregate-as-proof.
- Existing tests, package validation и trigger coverage остаются зелёными.
- AP-4 сохраняет economics gate: active catalog mutation не объявлена вредной без reuse/cost evidence.

## Проверка после реализации

```bash
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest tests/test_prompt_cache_scripts.py
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/validate_skill_package.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 audit-prompt-caching/scripts/run_trigger_eval.py audit-prompt-caching
PYTHONDONTWRITEBYTECODE=1 python3 - <<'PY'
from pathlib import Path
for path in [*Path('audit-prompt-caching/scripts').glob('*.py'),
             *Path('tests').glob('*.py')]:
    compile(path.read_text(), str(path), 'exec')
    print(f'ok {path}')
PY
git diff --check -- audit-prompt-caching/SKILL.md audit-prompt-caching/references audit-prompt-caching/evals tests/test_prompt_cache_scripts.py
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Реализацию вести в isolated worktree от `origin/main@99f3ea9`: текущий checkout содержит пользовательский overlay, а его test baseline отличается от целевой ветки. Не использовать dirty checkout как fallback. Если пользовательскую test-правку нужно сохранить, переносить её отдельным проверяемым patch после реализации. Последняя команда только перечисляет artifacts. Удалять чужие untracked files нельзя.
