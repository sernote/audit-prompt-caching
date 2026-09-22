# Спецификация: version-aware и geometry-aware аудит vLLM prefix cache

Дата: 2026-08-23

Окно исследуемых публикаций: 2026-08-17—2026-08-22

Статус: готово к реализации

Целевая база: `origin/main@99f3ea9`

Приоритет исходной идеи: P1

## Task 1: Реализовать version-aware и geometry-aware аудит

## Решение

Изменение нужно. Центральный gap подтверждён: текущий скилл направляет vLLM-сценарии в Deployment Audit, но не требует сначала установить точную версию/commit, наличие функции, topology KV-групп и совместимость block hash между процессами.

Исходная формулировка подтверждена после ключевых поправок:

1. На момент повторной проверки последний стабильный релиз — `v0.27.1` от 11 августа. Изменения от 17–18 августа находятся после него; нельзя придумывать version floor до их появления в релизе.
2. Retention-функция не «появилась 17 августа»: в `v0.27.1` уже есть env-only настройка с default `None`. Commit `017e9f4` переносит её в CLI/config и меняет default на `0`.
3. Для eligible SWA/Mamba-групп `prefix_cache_retention_interval=0` сохраняет semantic checkpoints, включая latest replay boundary и shared-prefix junctions. Это не «ровно один последний блок»; для pure-dense geometry поведение `0` зависит от версии.
4. Геометрия определяется конкретным классом KV spec, а не словом «local attention»: validator принимает `SlidingWindowSpec` (включая `SlidingWindowMLASpec`) и `MambaSpec`, но не `RSWASpec`, `ChunkedLocalAttentionSpec` или full-attention subclasses.
5. Совпадение effective seed недостаточно: для общего KV tier должны совпасть hash algorithm, effective seed, serialization/runtime и остальные cache-key inputs. `cache_salt` остаётся отдельным механизмом isolation.
6. Hash defaults в stable и post-18-Aug `main` различаются. Любая рекомендация должна использовать матрицу «версия × алгоритм», а не одну общую таблицу.

## Первоисточники

- vLLM `v0.27.1`, опубликован 2026-08-11: https://github.com/vllm-project/vllm/releases/tag/v0.27.1
- retention/config change от 2026-08-17: https://github.com/vllm-project/vllm/commit/017e9f4448b700e85ee16023287b025693c72b9e
- deterministic cross-process hash change от 2026-08-18: https://github.com/vllm-project/vllm/commit/ef47a897e2ad9a404cce9c9e7df15934deb8ffbe
- stable `v0.27.1` hash implementation: https://github.com/vllm-project/vllm/blob/v0.27.1/vllm/v1/core/kv_cache_utils.py
- stable `v0.27.1` retention env and coordinator: https://github.com/vllm-project/vllm/blob/v0.27.1/vllm/envs.py and https://github.com/vllm-project/vllm/blob/v0.27.1/vllm/v1/core/kv_cache_coordinator.py
- current KV spec class hierarchy and validator: https://github.com/vllm-project/vllm/blob/main/vllm/v1/kv_cache_interface.py and https://github.com/vllm-project/vllm/blob/main/vllm/v1/core/kv_cache_coordinator.py
- cache isolation через `cache_salt`: https://docs.vllm.ai/en/stable/design/v1/prefix_caching.html

Оба commit-level изменения следует описывать как поведение upstream `main`, пока официальный релиз или проверяемый deployment SHA не докажет обратное.

## Нормативная модель поведения

### Feature gate

Перед точным советом скилл должен собрать доказательства в таком порядке:

1. image digest и `vllm --version`; для source/nightly build — commit SHA;
2. наличие параметра в `--help`, resolved config или source SHA;
3. effective value и его источник: CLI, config, env или default с учётом release line;
4. concrete KV spec class каждой группы, а затем human-readable geometry;
5. `scheduler_block_size`, отдельно от physical group block size и `prefix_match_unit`/`hash_block_size`;
6. topology общего tier: local APC, FS, OBJ, P2P/PD или другой connector.

Если feature presence не доказано, ответ должен быть `Change needed: unknown until feature/version evidence`, а не рекомендация конкретного значения.

### Version × retention behavior

| Runtime evidence | Feature surface | Default/meaning |
| --- | --- | --- |
| `v0.27.1` source/release | env `VLLM_PREFIX_CACHE_RETENTION_INTERVAL`; coordinator consumes it | default `None`; feature уже присутствует, но CLI/config из `017e9f4` ещё нет |
| source/nightly с `017e9f4` | CLI/config `prefix_cache_retention_interval`; env остаётся deprecated fallback | default `0`; resolved source обязан быть виден |
| другая stable/legacy line | неизвестно без source/help/resolved config | не переносить semantics ни `v0.27.1`, ни post-commit `main` |

Аудит должен показывать resolved source. Наличие env в manifest не доказывает, что runtime его применяет; отсутствие CLI-флага не доказывает отсутствие env-only функции.

### Version × retention matrix

| Runtime | Effective value | Только dense/non-eligible specs | SWA/Mamba/hybrid |
| --- | --- | --- | --- |
| stable `v0.27.1` env-only | `None` | interval не применяется | dense checkpoints на sparse-группах |
| stable `v0.27.1` env-only | `0` | startup/config error: любой non-`None` env value требует SWA/Mamba | semantic checkpoints: latest replay boundary и shared-prefix junctions |
| stable `v0.27.1` env-only | положительное число | startup/config error, если sparse-групп нет | дополнительные periodic checkpoints; значение кратно effective `scheduler_block_size` |
| post-`017e9f4` source/main | `None` | interval не применяется | dense checkpoints на sparse-группах |
| post-`017e9f4` source/main | `0` | допустимый no-op | semantic checkpoints: latest replay boundary и shared-prefix junctions |
| post-`017e9f4` source/main | положительное число | startup/config error, если sparse-групп нет | дополнительные periodic checkpoints; значение кратно effective `scheduler_block_size`; full-attention groups игнорируют interval |

В post-commit runtime `ChunkedLocalAttentionSpec` относится к dense/non-eligible колонке: `0` — no-op, а positive interval в pure-dense конфигурации — error. Для неизвестной release line матрицу не применять без source/runtime evidence.

Нельзя подменять `scheduler_block_size` физическим block size одной группы. В проверенном commit это scheduling granularity, кратная `hash_block_size` и block size каждой KV group.

### Geometry eligibility

Таблица должна строиться по runtime/spec-class evidence:

| KV spec class | Retention-interval eligibility |
| --- | --- |
| `SlidingWindowSpec`, включая `SlidingWindowMLASpec` | да |
| `MambaSpec` | да |
| `FullAttentionSpec` и subclasses, включая `RSWASpec` и `SinkFullAttentionSpec` | нет |
| `ChunkedLocalAttentionSpec` | нет в проверенном validator |
| неизвестный/new spec | `unknown`, пока source/runtime probe не подтвердит eligibility |

Нельзя классифицировать eligibility только по словам `sliding`, `local`, `sink` или по архитектуре модели.

### Version × hash compatibility

| Runtime evidence | Algorithm | Default seed без `PYTHONHASHSEED` | Cross-process reuse |
| --- | --- | --- | --- |
| stable `v0.27.1` | все поддерживаемые algorithms | random `os.urandom(32)` per process | без общего effective seed несовместимо по умолчанию |
| stable `v0.27.1` | любой algorithm с явно общим `PYTHONHASHSEED` | deterministic from supplied value | возможно только при одинаковом algorithm и остальных inputs |
| post-`ef47a897` source/main | `sha256`, `sha256_cbor` | фиксированный deterministic default | возможно при одинаковом algorithm и остальных inputs |
| post-`ef47a897` source/main | `xxhash`, `xxhash_cbor` | random per process | требуется одинаковый security-sensitive `PYTHONHASHSEED` и одинаковый algorithm |

P2P handshake проверяет advertised effective seed и отклоняет mismatch. Это operational validation, но не основание считать разные algorithms совместимыми.

Совпадение algorithm и effective seed необходимо, но недостаточно для cross-version compatibility. Должны совпадать все cache-key inputs и совместимый способ serialization: `sha256` использует Pickle, поэтому совместимость Python/vLLM runtime нельзя предполагать; `sha256_cbor` делает serialization воспроизводимее, но не отменяет model/config/token inputs.

Разделять три понятия:

- hash algorithm — способ вычисления block key;
- effective seed — совместимость цепочки block hashes между процессами;
- `cache_salt` — intentional trust-boundary isolation для запросов.

Не помещать raw seed в audit report, telemetry или рекомендованные metric labels и не предлагать `PYTHONHASHSEED` как tenant-isolation mechanism. Для post-commit cryptographic algorithms fixed default публичен и не является секретом. Effective seed для `xxhash`/`xxhash_cbor` должен оставаться secret и unpredictable; общее значение передаётся только через защищённую конфигурацию, а наружу выходят `matched`/`mismatched`, boolean presence или keyed fingerprint. Сам vLLM/runtime или handshake может раскрывать значение в собственных логах: это отдельный redaction risk, который аудит должен проверить, а не обещать отсутствие утечки.

## Обязательные изменения по файлам

### `audit-prompt-caching/references/vllm.md`

Добавить:

- блок `Version and capability gate`;
- предупреждение `upstream main versus stable release`;
- retention matrix и разбор full/SWA/Mamba/hybrid geometry;
- version × behavior tables для stable `v0.27.1` и post-commit `main`;
- exact KV spec-class eligibility с защитой от имени архитектуры;
- различие `scheduler_block_size`, physical block size и `prefix_match_unit`;
- hash compatibility matrix;
- FS/OBJ/P2P validation и P2P seed handshake;
- отдельный подраздел `Compatibility is not isolation` про `cache_salt`;
- operational evidence contract без raw seed.

Обновить `Last reviewed` только в реализации, после повторного открытия официальных источников.

### `audit-prompt-caching/SKILL.md`

Не переносить туда всю механику. Добавить короткие требования:

- в Deployment Audit сначала фиксировать version/SHA/image, feature presence, effective retention, KV-group topology, scheduler block size, hash algorithm, seed compatibility status и tier type;
- в vLLM playbook различать retention/geometry mismatch и cross-process hash mismatch;
- при source/nightly build применять feature detection, а не guessed version floor.
- расширить trigger surface/frontmatter: `prefix_cache_retention_interval`, `prefix_caching_hash_algo`, Mamba/SWA/hybrid и cross-process block hash должны реально активировать скилл; одних новых eval queries недостаточно.
- после добавления AP-13/AP-14 обновить все тексты `AP-1 through AP-12` на `AP-1 through AP-14` и определить границу: AP-9b — isolation/trust boundary, AP-14 — technical compatibility внутри разрешённой sharing group.

### `audit-prompt-caching/references/predeploy-checklist.md`

Добавить blockers:

- retention flag/env используется без доказательства поддержки в runtime;
- positive interval выбран без sparse topology и effective scheduler-block evidence;
- FS/OBJ/P2P sharing group использует разные algorithms или effective seeds;
- `PYTHONHASHSEED` используется как isolation mechanism;
- rolling upgrade общего cache tier/prefix-reuse path смешивает разные hash/retention semantics без canary evidence; для pure full-attention без shared reuse этот blocker не применяется автоматически.

В Minimum Release Evidence добавить image digest/version/SHA, resolved cache config и redacted compatibility status.

### `audit-prompt-caching/references/rules.json`

Добавить два правила, не перегружая общий AP-9:

| ID | Category | Summary | Fix | Validation |
| --- | --- | --- | --- | --- |
| `AP-13` | `engine-config-compatibility` | vLLM retention advice ignores runtime capability or KV-group geometry | установить version/SHA, feature presence, topology и effective interval | startup принят; resolved config и group behavior совпадают; hit/TTFT сверены по deployment version |
| `AP-14` | `cache-identity-compatibility` | cross-process hash compatibility conflated with cache isolation | согласовать algorithm, effective seed, serialization/runtime и cache-key inputs внутри sharing group; сохранить отдельный `cache_salt` boundary | для P2P — handshake/reject, config fingerprint/block length и read; для FS/OBJ — independently verified config и реальный cross-process read без раскрытия seed |

Для обоих `default_severity` — `medium`; повышать severity только после Project Context Gate.

`AP-14.avoid` должен запрещать raw seed logging, хранение/передачу общего xxhash seed вне защищённой secret-конфигурации, предсказуемый non-crypto seed и замену `cache_salt` на `PYTHONHASHSEED`.

### `audit-prompt-caching/references/observability.md`

Добавить self-hosted dimensions:

```text
engine_version
engine_commit
image_digest
retention_feature_present
retention_effective_value
attention_geometry
scheduler_block_size
hash_algorithm
seed_compatibility_status
pythonhashseed_present
pythonhashseed_match_status
kv_tier_type
cache_salt_boundary_fingerprint
```

`seed_compatibility_status` и `pythonhashseed_match_status` принимают безопасные значения вроде `matched`, `mismatched`, `unknown`; `pythonhashseed_present` — boolean. Raw seed запрещён. `cache_salt_boundary_fingerprint` должен быть keyed, non-reversible fingerprint без raw salt и tenant identity; использовать его прежде всего в trace/log. В metrics он допустим только при доказанной bounded cardinality, но не как tenant-level label.

### `audit-prompt-caching/references/report-template.md`

Добавить `Deployment Audit` в Output Contract Selector и следующие поля в Header/Evidence Needed Next:

```text
Engine version/commit/image:
Capability evidence:
Attention/KV geometry:
Effective retention and source:
Scheduler block size:
Hash algorithm:
Seed compatibility status:
KV tier:
Isolation/cache_salt boundary:
```

### `audit-prompt-caching/scripts/extract_llm_calls.py`

Расширить только vLLM patterns:

```text
--prefix-cache-retention-interval
prefix_cache_retention_interval
VLLM_PREFIX_CACHE_RETENTION_INTERVAL
--prefix-caching-hash-algo
prefix_caching_hash_algo
```

Текущий extractor прекращает проверку после первого provider pattern в строке, поэтому реализация должна собирать additive unique signals для найденного vLLM finding, не раздувая provider/file count. Реалистичная строка `command: vllm ... --prefix-cache-retention-interval ...` обязана сохранить и generic vLLM detection, и конкретный flag signal.

Добавить scanning для `.sh`, `.service` и `Makefile`, потому что именно там часто лежат CLI-флаги. `.env` по умолчанию не сканировать: это отдельный secret-exposure risk. Поддержать его можно только явным opt-in/targeted path с прозрачным сообщением о прочитанных файлах.

Не добавлять общий pattern `PYTHONHASHSEED`: вне vLLM-контекста он даст ложные срабатывания. Скрипт лишь обнаруживает конфигурацию; он не должен выполнять runtime probe или извлекать значения.

### `tests/test_prompt_cache_scripts.py`

Сначала добавить failing tests:

1. extractor находит CLI, config key и deprecated env retention в YAML/Python, `.sh`, `.service` и `Makefile`;
2. extractor находит CLI/config hash algorithm;
3. realistic multi-token line с `vllm` и retention/hash flag возвращает specific additive signal, а не только generic match;
4. generic `PYTHONHASHSEED` без vLLM-контекста не классифицируется как vLLM; это regression guard, а не ожидаемый RED;
5. contract assertions фиксируют version-aware `None`/`0`/positive semantics, stable pure-full `env=0` error, post-commit `0` no-op, spec-class eligibility и stable-versus-main matrices;
6. SKILL/frontmatter, checklist, report, observability и AP-13/AP-14 содержат обязательные anchors и актуальный диапазон правил;
7. нигде не требуется логировать raw seed в audit-owned artifacts;
8. negative assertions запрещают: positive interval как full-attention no-op, `0` как «no retention», `PYTHONHASHSEED` как isolation и algorithm+seed как достаточную cross-version гарантию;
9. `cache_salt_boundary_fingerprint` не допускает raw salt, tenant ID или unbounded metric cardinality.

Изменения в существующий dirty test file нужно накладывать поверх пользовательской версии, не заменяя её содержимое.

### `audit-prompt-caching/evals/evals.json`

Добавить четыре behavioral cases:

1. неизвестная legacy line: CLI feature отсутствует, env может присутствовать, default неизвестен — не переносить semantics по одному имени env;
2. stable `v0.27.1` versus post-`017e9f4`/`ef47a897` SHA: env-only `None`, pure-full `env=0` error и random-all-algorithms default не смешивать с main CLI/config `0` no-op и split crypto/xxhash behavior;
3. hybrid full+SWA/Mamba с `None`, `0` и positive interval: корректно применить matrix и проверить `scheduler_block_size`;
4. FS/OBJ/P2P shared cache с `sha256`/`xxhash`: разделить algorithm, effective seed, serialization/runtime, P2P handshake и `cache_salt` isolation.

Ожидаемый ответ не должен автоматически советовать включить общий seed или менять retention до Applicability Gate.

### `audit-prompt-caching/evals/trigger_eval.json`

Добавить positive queries для `prefix_cache_retention_interval`, hybrid Mamba/SWA geometry и cross-process vLLM hash mismatch. Негативные non-LLM/Kubernetes cases оставить без изменений.

## Порядок реализации

1. Добавить tests/evals и получить RED на missing patterns/anchors.
2. Минимально расширить `extract_llm_calls.py`, получить GREEN для extractor tests.
3. Обновить references, rules, SKILL и report contract.
4. Прогнать behavioral/trigger package checks.
5. Повторно сверить upstream release status: если commit уже попал в релиз, заменить `main-only` на доказанный version floor; иначе оставить feature detection.
6. Сохранить upgrade-delta evidence: один и тот же fixture должен показывать ожидаемое различие stable и post-commit behavior.

## Non-goals

- Не реализовывать remote/runtime vLLM inspector.
- Не задавать будущий version floor по догадке.
- Не менять deployment, retention, algorithm, seed или `cache_salt` автоматически.
- Не добавлять raw seed или raw prompt в telemetry.
- Не утверждать production ROI по config evidence без representative workload.
- Не менять `validate_skill_package.py`, `run_trigger_eval.py`, pricing или usage-accounting scripts.

## Acceptance criteria

- Любой точный совет начинается с version/SHA и feature evidence.
- `None`, `0`, positive и pure-full-attention error описаны в version-aware matrix; stable `v0.27.1 env=0` не объявляется post-commit no-op.
- Hybrid semantics применяются per KV group; full-attention groups не объявляются sparse.
- Positive interval проверяется против effective `scheduler_block_size`.
- Algorithm, effective seed, handshake и `cache_salt` представлены как разные оси.
- Stable `v0.27.1` и post-18-Aug `main` не используют одну hash-default table.
- Retention в `v0.27.1` признаётся env-only feature с default `None`; `017e9f4` описывается как promotion/default change, а не появление функции.
- Eligibility выводится из concrete KV spec class; `RSWASpec` и `ChunkedLocalAttentionSpec` не считаются eligible по имени.
- Для shared KV tier требуется совпадение algorithm и effective seed.
- Algorithm и seed не объявляются достаточной cross-version гарантией без serialization/runtime/model/config evidence.
- Effective seed для xxhash/xxhash_cbor нормативно secret/unpredictable и передаётся только через защищённую конфигурацию; публичный crypto default отделён от него.
- P2P handshake не переносится на FS/OBJ; там требуются config evidence и cross-process read.
- Legacy env-only deployment не получает main semantics без feature detection.
- Новые evals ловят version guessing, geometry errors и compatibility/isolation conflation.
- Все существующие positive/negative trigger cases и tests остаются зелёными.

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
git diff --check -- audit-prompt-caching/SKILL.md audit-prompt-caching/references audit-prompt-caching/scripts/extract_llm_calls.py audit-prompt-caching/evals tests/test_prompt_cache_scripts.py
find . \( -name __pycache__ -o -name '*.pyc' \) -print
```

Реализацию вести в isolated worktree от `origin/main@99f3ea9`: текущий checkout содержит пользовательский overlay, а его test baseline отличается от целевой ветки. Не использовать dirty checkout как fallback. Если пользовательскую test-правку нужно сохранить, переносить её отдельным проверяемым patch после реализации. Последняя команда должна только показать generated bytecode. Удалять чужие untracked artifacts нельзя.
