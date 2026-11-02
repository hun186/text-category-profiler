# Creating the standalone GitHub repository

This directory is the reusable Jaal topology viewer's **complete repository
root**, not a subdirectory that requires another project's Python imports.

## Verified source

The canonical source is `packages/jaal-topology/` in
[hun186/text-category-profiler](https://github.com/hun186/text-category-profiler).
Changes should be submitted there until an independent repository has been
created and a source-of-truth/mirror policy has been agreed upon. Avoid
maintaining unrelated copies of the visualizer's JS in several repos.

The source project's **Jaal Standalone GitHub Repository Export** GitHub
Actions workflow publishes `jaal-topology-viewer.zip`, its `.sha256`,
and `source-commit.txt` together as a downloadable artifact. It creates the
archive via `git archive HEAD:packages/jaal-topology`, checks its exact tracked
file list, installs the extracted package in a clean folder, executes its own
Python and Node tests, checks the real Jaal Dash HTTP routes and prefixed WSGI
mount, and verifies the built wheel contains JS and CSS assets.

Do not use an artifact from a failing job or an unreviewed branch as a
release. The main-branch workflow artifact (if available) is preferred.

## Publish using GitHub Desktop (requires your own GitHub access)

1. From the source repository's **Actions → Jaal Standalone GitHub
   Repository Export**, select a successful **main** run. Download the
   `jaal-topology-viewer-repository-...` artifact and unzip it.
2. Verify the SHA-256 of the nested `jaal-topology-viewer.zip` against the
   accompanying `.sha256`; unpack the nested ZIP. Its
   `jaal-topology-viewer/` folder is the actual new project root.
3. In GitHub Desktop choose **File → Add local repository**, select that
   folder and accept the prompt to initialize a Git repository if shown.
   Alternatively create the initial local Git commit using the shell commands
   below.
4. In GitHub Desktop use **Publish repository** to create a repository named
   `jaal-topology-viewer` in your selected account. Review the **Keep this
   code private** choice deliberately; do not expose it publicly by mistake.
5. Confirm that README, LICENSE, Python package, original Jaal JavaScript and
   `.github/workflows/ci.yml` are all in the new repository root. Check the
   new repository's own **Portable Jaal Viewer CI** result.

Or, after creating an **empty** GitHub repository without starter files:

```sh
cd jaal-topology-viewer
git init -b main
git add .
git commit -m "Import standalone Jaal topology viewer"
git remote add origin https://github.com/hun186/jaal-topology-viewer.git
git push -u origin main
```

Both routes require a human account operation to create the repository;
the source project's CI does **not** create a GitHub repository or use a
cross-repository personal access token.

## Verify a standalone checkout

```sh
python -m pip install -e .
python -m unittest discover -s tests -p "test_*.py" -v
node --test tests/*.test.cjs
jaal-topology --edges examples/relationships.csv \
  --metadata examples/metadata.csv --root Root
```

Windows visual acceptance, Dash/visdcc dependency variants, and a strategy
for keeping the main source project and the separate GitHub repository in sync
remain independent release checks. No PyPI publication, public web service,
or unsupported global secret was created by this export pipeline.
