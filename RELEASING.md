# Releasing

1. Commit to `main`.
2. Tag and push: `git tag vX.Y.Z && git push --tags` (semver — your call on the bump).

The [Homebrew tap](https://github.com/akirayamamoto/homebrew-tap) auto-bumps its formula within a week. To publish immediately, run the **bump** workflow: Actions → bump → Run workflow.
