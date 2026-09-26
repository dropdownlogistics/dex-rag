# Plugins — drop-in Programs

Drop a `.json` file in this folder and it becomes a **Program** in the app (Programs tab) — **no code edit.** Restart the server to pick up new or changed plugins.

Since a Program is just a *directive*, a plugin is pure data. This is the "plugins like superpowers" pattern, confined to this app.

## Format

```json
{
  "id": "unique_snake_case_id",
  "name": "Display Name",
  "icon": "◆",
  "blurb": "One line — what it does.",
  "category": "Reasoning",
  "grounded": true,
  "input_label": "topic to analyze",
  "directive": "What Dex should do with the input (and the corpus notes, if grounded)."
}
```

| field | required | notes |
|---|---|---|
| `directive` | **yes** | the system framing; without it the file is skipped |
| `id` | no | defaults to the filename; a built-in id is never overridden |
| `grounded` | no (default true) | `true` → runs Dex's corpus retrieval first, answer is cited; `false` → reasons from your input alone |
| `name`/`icon`/`blurb`/`category`/`input_label` | no | sensible defaults; `icon` is one glyph |

## Rules
- No `directive` → skipped. Same `id` as a built-in → skipped (built-ins win).
- Malformed JSON → skipped silently. **A bad plugin never breaks the app.**
- See `steelman.json` (ungrounded) and `red_team.json` (grounded) as templates.
