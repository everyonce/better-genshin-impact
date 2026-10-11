Unexpected Power Tutorial Pilot

Scope: the English fresh-account Unexpected Power combat tutorial only.
It must run inside BetterGI r8+ in a Windows RDP/Desktop Clone session.
Game aspect ratio must be 16:9; capture/input coordinates are normalized to
1920x1080. The validated game was 2560x1440 in RDP session 5.

Leave Enable Input unchecked to save one observation without gameplay input.
Enable it to run the local controller. Configure the script group to allow
non-main-UI starts if the quest journal is open. The controller automatically
opens the journal only from a positively recognized world HUD and requires
Unexpected Power to be the selected journal quest before combat input.

Allowed combat actions are a 60ms E press, a 1200ms E hold, and a 60ms Q press,
each requiring its specific visible English tutorial prompt. The hold prompt
may wrap across two OCR lines; a matching E/Q key icon may be merged into the
prompt. A fresh capture checks the exact action again before any key-down.
This does not expand OpeningQuestPilot's general command allowlist.

The local runner verifies changed prompts, bounds unchanged-prompt retries
to three with at least three seconds between attempts, and limits its run
to two minutes between native calls. It stops on unknown screens, unavailable
world HUD, lost focus/session, stalled prompts, or a verified next quest.
Holds check focus/session at most 50ms apart and release keys in finally.
The controller never automatically refocuses after its initial startup.
Native capture/OCR calls cannot be preempted by the JavaScript time budget.

status.json is the latest run; runs/<session>.json preserves each run and
observations/<session> retains screenshots and their matching OCR records.
Input records are written before input; completion is recorded separately.
A started action alone is not proof of execution or quest completion.
manualInterventions describes in-run interventions only; code fixes/restarts
must be accounted for across runs, as in the live-run report below.

Live result, 2026-10-10: Unexpected Power completed in English through BetterGI
in RDP. The final journal selected Forest Rendezvous / Go to Mondstadt and
displayed the Let the Wind Lead achievement. No following-quest gameplay was
performed. There were three automatic combat actions and no manually issued
movement or combat inputs, but three code fixes/restarts were required.
Elapsed time including those fixes was 3m59s; controller runtime across the
four attempts totaled 26.442s. This was not one uninterrupted autonomous run.
The final version has not been replayed from the first prompt on another
fresh account. Six recorded OCR fixtures cover the initial journal, each
combat prompt, an unknown transition, and the selected following quest.

Evidence: Test/UnexpectedPowerPilot/live-run-report.json and live-captures.json.
Tests: node --test Test/UnexpectedPowerPilot/*.test.cjs
