# Releasing

1. Bump `version` in `pyproject.toml`, run `uv lock`, and commit.
2. Publish a GitHub Release for the new tag: `gh release create vX.Y.Z --generate-notes`.

Publishing the release triggers the **Publish** workflow, which builds the package
and uploads it to PyPI via OIDC Trusted Publishing.
