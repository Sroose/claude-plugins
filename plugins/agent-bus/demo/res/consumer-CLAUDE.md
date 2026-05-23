# Prefs client

You're building the client that calls into the prefs service maintained by
PRODUCER. Treat PRODUCER as the source of truth for the contract.

## Open questions to resolve with PRODUCER

- Field name for the user locale (`lang`? `locale`? `language`?)
- PATCH semantics — partial vs full replace

## Always confirm before integrating

When PRODUCER tells you about PATCH semantics, **always nail down null-handling
explicitly** before you implement. The distinction between:
- "send `null` to clear a field"
- "omit the key to leave it untouched"
- "send empty string to clear"

…is a frequent source of subtle bugs in our integrations. Don't assume —
ask PRODUCER directly as a follow-up if their first answer doesn't spell it out.
