# Proposal: Progression Engine

## Intent

DARTH-GAIN syncs workouts but can't tell you when to increase weight. Add deterministic double progression — checks if all sets in a workout hit the top of the rep range, then recommends increasing weight. First step toward automated progression management for hypertrophy training.

## Scope

### In Scope
- `progression_config` and `progression_history` DB tables
- Core double progression algorithm (deterministic, no RPE)
- `darth-gain progression check <exercise_template_id>` CLI subcommand
- Per-exercise rep range and weight increment config (defaults via DB, no UI)
- Auto-filter: `weight_reps` exercises only; skip `reps_only`/`duration`

### Out of Scope
- Multi-exercise overview (`progression status` — Phase 2)
- Progression application tracking (`progression apply` — Phase 2)
- Routine-based default rep range discovery (Phase 2)
- Deload detection (Phase 2)
- RPE-aware adjustments (Phase 2)
- Auto-apply or CLI write-back to Hevy

## Capabilities

### New Capabilities
- `progression-engine`: Double progression check algorithm, DB schema for config + history, per-exercise config management, deterministic status reporting

### Modified Capabilities
None — progression is entirely new, no existing specs change.

## Approach

New `src/darth_gain/progression/` module with `engine.py` (algorithm), `models.py` (dataclasses), `repo.py` (DB CRUD), `__init__.py` (public API). Algorithm: query all normal sets for an exercise chronological by workout → group by workout → for each workout, check if ALL sets hit or exceed rep_max → if the most recent workout meets criteria, recommend increasing weight by increment.

## Key Design Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Default rep range | 8-12 | Standard hypertrophy zone, configurable per exercise via `progression_config` |
| Weight increment | 2.5kg global default | Smallest barbell increment (1.25kg plates), overrideable per exercise |
| Exercise qualification | Auto-`enabled` for `weight_reps`, disabled for `reps_only`/`duration` | Double progression requires weight + reps; user overrides via `progression_config.enabled` |
| Consecutive workouts | 1 full workout at top of range | Simplest deterministic check; N-consecutive deferred to Phase 2 |

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/darth_gain/progression/` | New | Module: engine, models, repo |
| `src/darth_gain/db/engine.py` | Modified | Add `progression_config` + `progression_history` to DDL |
| `src/darth_gain/cli.py` | Modified | Add `progression` group with `check` subcommand |
| `tests/test_progression_engine.py` | New | Unit tests for algorithm |
| `tests/test_progression_repo.py` | New | Tests for DB queries |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| Inconsistent weight across sets within same exercise | Medium | Working weight = most common weight across normal sets; document behavior |
| NULL weight_kg/reps in set data for weight_reps exercises | Low | Skip NULL sets gracefully; algorithm works with partial data |
| User has never configured rep ranges — no config exists | Medium | Report "not configured" with instructions to insert default; no crash |
| Beta Hevy API may change exercise template model | Low | Adapter pattern in `client.py` protects; exercise_templates type field is stable |

## Rollback Plan

1. Revert the commit — zero blast radius on existing `ingest` functionality
2. If DB schema was deployed: `DROP TABLE IF EXISTS progression_config, progression_history`
3. No active cron/scheduling depends on this feature yet

## Dependencies

- Existing `workouts`, `exercises`, `sets`, `exercise_templates` tables (already populated by ingest)
- Existing index on `workouts.start_time` and set type filtering

## Success Criteria

- [ ] `darth-gain progression check <id>` returns status for a configured exercise
- [ ] Algorithm correctly identifies when all sets hit rep_max → recommends increase
- [ ] Algorithm correctly reports "stay at current weight" when sets are below rep_max
- [ ] `reps_only` and `duration` exercises return "not tracked" without error
- [ ] Exercise with no config returns clear "not configured" message
- [ ] History query returns empty result for never-progressed exercise
- [ ] All tests pass with `pytest` (>99% coverage maintained)
