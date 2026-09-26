# Phone Access — Scoping Doc

**Prepared by:** Silas Reeve / DDL-3004 / reborn-cowork
**For:** Dave Kitchens (Operator)
**Date:** 2026-07-24 (drafted overnight, for review)
**Status:** SCOPE ONLY — nothing built. This is the "fun project for tomorrow." Read it, poke holes, then we brainstorm → approve → build.

---

## The ask, restated

> "Scope out turning this into an app that I can use from phone."

"This" = the Dex Jr. workspace (`dex-chat`, port 8791) primarily, with the campaign cockpit (port 8801) as a sibling that rides the same rails. You want to open Dex — chat, search, dispatch a worker, check health — from your phone, from anywhere, and have it feel like an *app*, not a bookmark.

---

## The one constraint that decides everything

**The intelligence can't move to the phone.** Dex is his corpus (965k chunks in ChromaDB), his models (Ollama), and the GPUs. That lives on **reborn** (brain + voice) and **gaminglaptop** (image). A phone has none of it and never will.

So the goal is **not** "port the app to a phone." It's **"reach the reborn-hosted app *from* the phone."** That reframing makes this small instead of huge — and we already own the hard part.

---

## Recommended architecture: **Tailscale + Responsive + PWA**

Three layers, each cheap, no new servers, no public exposure:

### 1. Reach — Tailscale (we already run it)
Reborn and gaminglaptop are already on the tailnet (that's how image offload works: `http://gaminglaptop:8793` via MagicDNS). **Your phone joins the same tailnet** (install the Tailscale app, sign in) and it can hit `http://reborn:8791` from anywhere — home, cell, coffee shop — as if it were on the LAN.

- **No public internet exposure.** The apps stay invisible to the world; only your own devices on your private mesh can see them. This is the DDL-correct posture: private by default, no attack surface, no auth infra to get wrong.
- **One code change:** the servers currently bind `127.0.0.1` (localhost only). They need to bind the tailnet interface so the phone can connect. This is a one-line change per app *plus* a Windows firewall rule scoped to the tailnet CIDR (exactly like the one already scoping gaminglaptop's image server). **Not** `0.0.0.0` wide open — tailnet-scoped.

### 2. Fit — Responsive pass
The tabbed shell is desktop-dense right now (grouped left nav, wide cards, hover affordances). On a phone it needs:
- Left nav → collapsible drawer / bottom tab bar
- Cards → single-column stacking
- Tap targets ≥ 44px, no hover-only actions
- The chat composer + mic button thumb-reachable
- Tables (analytics, health) → horizontal-scroll containers, never break the page width

This is CSS + a little layout JS, no rearchitecting. The palette/fonts stay.

### 3. Feel — PWA install
Add a web-app manifest + icon + a minimal service worker so Dex **installs to your home screen** with its own icon and opens full-screen (no browser chrome). That's the difference between "a website I visit" and "an app I have." Offline caching stays minimal on purpose — Dex is useless without reborn anyway, so the SW just shells the UI and shows an honest "can't reach reborn" state when you're off-tailnet (a green-light-is-a-claim touch: the app tells the truth about whether the brain is reachable, never fakes it).

---

## Alternatives considered (and why not)

| Option | Verdict | Why |
|---|---|---|
| **Cloudflare Tunnel / public reverse proxy + auth** | ❌ Rejected | Exposes Dex to the public internet, needs real auth (a thing to get wrong), more moving parts. Tailscale gives the same "from anywhere" with zero public surface. |
| **Native iOS/Android app** | ❌ Overkill | Weeks of work, app-store friction, for a UI that's already a perfectly good web app. PWA gets 95% of the feel for ~2% of the cost. |
| **Cloud-host the whole stack** | ❌ Non-starter | Moving the corpus + models to a cloud GPU = money, privacy loss, and it defeats the entire "local, private, mine" thesis of Dex. |
| **Just bookmark the LAN URL** | ⚠️ Partial | Works only at home, no app feel, breaks the moment you leave the house. Tailscale is the "from anywhere" upgrade over this. |

---

## Work breakdown (for tomorrow's build, once approved)

**Phase 1 — Reach (get it on the phone at all)** · smallest, highest payoff
1. Bind `dex-chat` server to the tailnet interface (+ tailnet-scoped firewall rule).
2. Confirm phone joins tailnet, hits `http://reborn:8791`, chat round-trips.
3. Repeat for campaign cockpit (8801) if you want it too.
> Endpoint of Phase 1: **you can use Dex from your phone tonight.** Ugly, but real.

**Phase 2 — Fit (make it usable with a thumb)**
4. Responsive nav (drawer/bottom-bar), single-column stacking, tap targets, scroll-safe tables.
5. Phone-optimized **Dispatch** view — you specifically wanted "send Dex a task from my phone." Make that the fast path: big compose box, pick a worker, fire to the queue. This is the killer feature for mobile.

**Phase 3 — Feel (make it an app)**
6. PWA manifest + icon + minimal service worker → installs to home screen, full-screen, honest offline/unreachable state.

Each phase is independently shippable. Phase 1 alone delivers the ask; 2 and 3 make it *nice*.

---

## Open questions for you (answer whenever)

1. **Which apps on your phone?** Dex-chat only, or the campaign cockpit too? (Cockpit is nearly free to add once the pattern exists.)
2. **Phone OS** — iPhone or Android? (Changes only the PWA-install instructions and a couple of Safari vs. Chrome quirks; architecture is identical.)
3. **Is Dispatch-from-phone the priority feature** the way I'm guessing it is? If yes, I'll make Phase 2's dispatch view the centerpiece rather than an afterthought.
4. **Voice on phone?** The mic/STT + clone playback *can* work through the phone browser over tailnet — worth a Phase-2.5 if you want to talk to Dex from your pocket. (Flagging it because you've treated voice as an importance signal — capturing it from the phone would be a rich vein.)

---

## Effort read (honest)

- **Phase 1:** small — an evening. The tailnet is already up; this is bind + firewall + verify.
- **Phase 2:** medium — a focused day. Responsive CSS is fiddly but not deep, and the dispatch view is net-new but small.
- **Phase 3:** small — a few hours. PWA boilerplate is well-trodden.

**No new infrastructure, no public exposure, no new services to babysit.** We're bolting a phone door onto a house that's already built and already on your private mesh. That's why this is a *fun* project and not a slog.

---

*Silas Reeve / DDL-3004 · runtime-truth caveat: the effort reads above are estimates, not measurements. The only number I'll stand behind is Phase 1, because I can see the tailnet's already carrying image traffic today — the rest I'll know once I'm in it.*
