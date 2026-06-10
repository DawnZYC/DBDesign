## What & why

<!-- One paragraph: what does this PR change and why is the change needed? -->

## How

<!-- Brief description of the implementation approach. Call out any non-obvious
trade-offs (e.g., chose SQLite for unit tests because postgres adds 30s to CI). -->

## Test plan

- [ ] `pytest` passes locally
- [ ] `npm run test` passes locally
- [ ] `npm run lint` and `npm run format:check` pass
- [ ] Manual smoke test against `docker compose up`
- [ ] (If schema changed) `psql -f sql/*.sql` runs cleanly on a fresh DB

## Screenshots / API samples

<!-- Optional: paste UI screenshots or `curl` examples for new endpoints. -->

## Risk & rollback

<!-- What's the blast radius if this breaks? How would we revert? -->
