# BRIEFING — 2026-09-09T13:58:40Z

## Mission
Mine authoritative specifications, exact game rules, card mechanics, penalties, Queen combo dynamics, and CLI constraints for i151 Arena.

## 🔒 My Identity
- Archetype: Specification Miner
- Roles: Teamwork specialist, Spec Miner
- Working directory: /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2
- Original parent: 353af73f-00a5-4c89-a94e-e8dfe324a469
- Milestone: Arena Rules & Mechanics Specification Mining

## 🔒 Key Constraints
- Discover and document features by probing authoritative specifications (CLI, SDK source code, documentation).
- Do NOT implement anything (read-only regarding implementation).
- Report in structured tables (Features Discovered, Edge Cases).
- Include exact verification methods, observations, logic chains, caveats, conclusions.

## Current Parent
- Conversation ID: 353af73f-00a5-4c89-a94e-e8dfe324a469
- Updated: not yet

## Loaded Skills
- **Source**: `/home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md`
- **Local copy**: `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/skills/i151-master-bot/SKILL.md`
- **Core methodology**: ELO 1900+ bot design, PIMC Minimax, 2P Queen invariant, penalty dumping, streak bonuses, CLI workflow.

## Task Summary
- **What to build**: Comprehensive authoritative specification report (`spec_report.md`) and handoff (`handoff.md`).
- **Success criteria**: Exhaustive probing of CLI (`arena`), `arena_sdk` source code, models, rules, engine, cards, scoring, timeout/latency budgets, packaging.
- **Interface contracts**: CLI parameters, Bot API (`setup`, `decide`, `observe`, `teardown`), PlayerView / Action representations.
- **Code layout**: `/home/ibrahim-tomota/mon-bot/`

## Key Decisions Made
- Inspected installed `arena_sdk` and `i151_engine` packages located at `/home/ibrahim-tomota/.platformio/penv/lib/python3.14/site-packages/` for ground-truth rules and engine implementation.
- Probed and verified 20 authoritative features and 15 distinct edge cases through Python execution and CLI probes.
- Discovered critical move equality requirement: `chosen_suit` embedded in `Action.play_card` causes immediate match forfeit; suit choice must occur via follow-up `Action.choose_suit`.
- Discovered exact 2P solitary Queen trap behavior: forced 1-card draw from bank and pass turn; does not end round.
- Probed Ace attacks (draw 2, turn terminates) vs Ace counters (deflection) and 8 counters (Ace effect canceled).
- Completed `spec_report.md` and `handoff.md`.

## Artifact Index
- `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md` — Authoritative rules & constraints report
- `/home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/handoff.md` — 5-component handoff report

