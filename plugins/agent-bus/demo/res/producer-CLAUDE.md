# Prefs service

You maintain the user-preferences service. Source of truth for any contract
question from other repos.

## /prefs endpoint contract

**Schema**
- `locale` (string, IETF BCP-47 tag — e.g. `"en-US"`, `"fr-FR"`)
- `theme` (enum: `"light"` | `"dark"` | `"auto"`)
- `notifications` (object: `{ email: bool, push: bool }`)

**Methods**
- `GET /prefs` → full prefs object
- `PUT /prefs` → full replacement
- `PATCH /prefs` → RFC 7396 merge-patch
  - send only the keys you want to change
  - `null` value = clear that field (revert to default)
  - omitted key = leave that field untouched

**Errors**
- `404` if the user hasn't set prefs yet — clients should fall back to their defaults

When another agent asks about the contract, answer concretely from this doc.
Don't equivocate. If they ask about edge cases not covered here, say so.
