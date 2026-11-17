# Spec Miner (Arena Rules & Mechanics) Dispatch

Task: Mine authoritative specifications, rules, card mechanics, penalties, and CLI constraints for i151 Arena.
Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md
- Any arena documentation, CLI help (`arena --help`), or library rules
Output: spec_report.md in this directory, handoff.md summarizing findings.

## 2026-09-09T13:58:40Z
You are Spec Miner. Your working directory is /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2.

Read:
- /home/ibrahim-tomota/mon-bot/.agents/ORIGINAL_REQUEST.md
- /home/ibrahim-tomota/mon-bot/.agents/skills/i151-master-bot/SKILL.md

Investigate the authoritative arena specifications:
1. Run arena CLI commands (e.g. `arena --help`, `arena test --help`, `arena match --help`, `arena pack --help`) and inspect python packages or arena rules modules to verify exact rules of i151: legal moves, suit changing with 8, penalties for cards left in hand (8 is 32 pts, As is 11 pts, 10 is 10 pts, etc.), 2-player Queen combo rules (playing Queen gives another turn, but cannot be played as the single last card without penalty), Ace blocking/canceling, bank draw rules when void.
2. Identify all constraints, limits (e.g. 1000ms max timeout, <50ms target avg latency, packaging zip contents and dependencies).

Write your report to /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/spec_report.md and handoff to /home/ibrahim-tomota/mon-bot/.agents/survey_explorer_r2_2/handoff.md.
Send a message back when done.

