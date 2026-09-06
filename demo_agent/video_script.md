# Agentic Trading Guardrail — Demo Video Captions / Voice-Over Script

Each numbered line is one caption = one voice-over clip. Generate each with
macOS's `say` command (swap "Ava" for whatever voice you downloaded):

    say -v Ava -o audio/01_cold_open.aiff "Binance's own Agent OS guardrail stops an agent from withdrawing funds. It does not stop it from losing money through bad trades."

Check each clip's length before editing:

    afinfo audio/01_cold_open.aiff | grep duration

That tells you exactly how much timeline space to give each line before the
next SFX stinger or caption comes in — no guessing, no overlap.

---

## 1. Cold open
"Binance's own Agent OS guardrail stops an agent from withdrawing funds. It does not stop it from losing money through bad trades."

## 2. The gap
"No position limits. No kill switch. That's the gap this project fills."

## 3. What it is
"This is a guardrail layer that sits in front of any trading agent. Every order gets checked before it ever reaches Binance."

## 4. Scenario 1 — normal order
"A normal order. It passes every check and gets forwarded."

## 5. Scenario 2 — duplicate
"The same order fires again, simulating a dropped connection retry. The dedup check catches it and blocks the repeat."

## 6. Scenario 3 — oversized
"An oversized order — thirty thousand in notional value against a ten thousand balance. The position cap blocks it outright."

## 7. Scenario 4 — rapid-fire loop
"Now, a buggy agent stuck in a decision loop, firing fifteen orders in two seconds. Watch it get cut off — first per symbol, then globally."

## 8. Scenario 5 — circuit breaker
"Three losing trades in a row trips the circuit breaker. The next order is blocked outright, until a human manually resets it."

## 9. Scenario 6 — kill switch
"And a manual kill switch — independent of the breaker — halts everything the instant an operator engages it."

## 10. Close
"This is infrastructure, not a strategy. It works underneath any agent."

---

## SFX placement notes (to avoid overlapping the voice)

Treat SFX as **stingers between lines, never under them**:
- A short "click" or "whoosh" transition sound as each new scenario's terminal
  output appears on screen — placed in the ~0.5s gap *before* that scenario's
  voice-over line starts, not during it.
- A distinct "block"/alert sound (a short buzz or stop-chime) the instant a
  BLOCKED result appears on screen — place it right as the voice-over line
  finishes speaking, so it lands as a punctuation mark, not a collision.
- For scenario 4 (the loop), consider a single alert sound on the first
  BLOCKED line only, not one per rejected order — repeating it 10 times will
  fight with the voice-over and get noisy fast.
- In iMovie: put voice-over on one audio track and SFX on a separate track
  below it, so you can see both waveforms and visually confirm gaps between
  them before exporting.
