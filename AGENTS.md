# AGENTS.md — SenderMe

## Project overview

SenderMe is a peer-to-peer LAN chat implemented with Python 3 and the
standard library only. It has no third-party runtime dependencies.

The application currently lives in a single file: `senderme.py`.

- TCP P2P communication: default port `13337`
- UDP peer discovery: default port `13338`
- Local web interface: `127.0.0.1:13336`

There is no CI or established test or lint suite. Do not claim otherwise
without verifying the current project state. The repo uses Git locally
(`main`); `dist/` is a generated artifact and stays out of version control.

The main project documents are:

- `docs/01-produto.md`
- `docs/02-arquitetura.md`
- `docs/03-progresso.md`

Keep these documents consistent with the implementation. Update the
documents affected by a change when necessary; do not modify unrelated
documents merely to update all three.

## Working principles

Before changing code:

1. Read the relevant documentation and existing implementation.
2. Identify the behavior being changed and any related constraints.
3. Follow existing project conventions when they are reasonable.
4. Check how the affected behavior can be verified.

Make changes that solve the requested problem without expanding scope
unnecessarily. Prefer small, understandable changes over broad rewrites.

Do not refactor unrelated code just because it could be cleaner. When a
larger structural problem blocks the requested change, explain the
trade-off and keep the refactor limited to what is necessary.

Do not introduce third-party runtime dependencies unless explicitly
requested or approved. Prefer the Python standard library.

## Code quality

Write code that is easy to read, maintain, and debug:

- Use clear names and keep behavior consistent with surrounding code.
- Give functions and components focused responsibilities where practical.
- Avoid unnecessary duplication, deep nesting, and excessive complexity.
- Add abstractions when they solve a real problem, not merely in
  anticipation of hypothetical future needs.
- Avoid magic numbers and strings when a named constant improves clarity.
- Comment non-obvious decisions and constraints; do not restate the code.
- Keep public behavior and existing data formats compatible unless the
  requested change explicitly requires otherwise.
- Avoid unrelated formatting changes that make review harder.

The application is currently a single file. Do not split it into modules
solely to satisfy a generic best practice. A structural change should have
a concrete benefit, a manageable scope, and appropriate verification.

## Errors, security, and concurrency

- Handle expected failures explicitly, especially around network I/O,
  files, JSON, and subprocesses.
- Do not silently suppress exceptions or report success when an operation
  failed. Provide actionable errors without exposing sensitive data.
- Validate external input at the relevant trust boundary, including data
  received from peers, HTTP requests, uploaded files, and update metadata.
- Treat LAN peers and received content as potentially untrusted.
- Avoid unsafe file paths, unintended overwrites, and unrestricted access
  to sensitive files.
- Do not expose the local HTTP interface beyond `127.0.0.1` unless
  explicitly requested and the security implications are addressed.
- Consider concurrent access and shared state when changing networking,
  message handling, file operations, or background work.
- Avoid logging private keys, credentials, or message contents
  unnecessarily.

Apply security measures appropriate to the actual feature and risk. Do
not claim that the application is secure based only on these rules.

## Verification

Choose verification appropriate to the change and its risks.

- Run the relevant existing checks, if any.
- Add or update automated tests when useful for preventing regressions,
  especially for protocol behavior, parsing, validation, persistence, and
  update logic. Standard-library `unittest` is a suitable default.
- Do not add tests that merely duplicate implementation details or create
  unnecessary maintenance burden.
- For behavior involving multiple peers, verify the relevant interaction
  between isolated instances where feasible.
- For UI changes, inspect the affected behavior in a browser when
  possible, in addition to checking JavaScript syntax.
- Preserve real exit codes in verification commands. Do not hide failures
  behind pipes, unconditional success exits, or truncated output.
- Report what was actually tested, the results, and any checks that could
  not be performed. Never present an unrun or failing test as passing.

The absence of an existing test suite is not a reason to skip verification.

## Run

Production:

```bash
bash start.sh
```

`start.sh` copies the application to `/tmp`, forces
`SENDERME_HOME=$APP_DIR`, opens the browser, and restarts the application
when it exits with code `42`. The terminal remains attached to the server;
use Ctrl+C to leave.

For isolated testing, run `senderme.py` directly. Do not use `start.sh`:
it overrides `SENDERME_HOME`.

```bash
SENDERME_HOME=/tmp/senderme-test-example \
SENDERME_PORTA=<tcp-port> \
SENDERME_UDP_PORTA=<udp-port> \
SENDERME_HTTP=<http-port> \
SENDERME_FIXOS=127.0.0.1:<peer-tcp-port> \
python3 senderme.py
```

Replace the placeholders with actual values. Use a fresh directory and
available ports appropriate to each test instance.

Environment variables:

- `SENDERME_HOME`
- `SENDERME_PORTA`
- `SENDERME_UDP_PORTA`
- `SENDERME_HTTP`
- `SENDERME_FIXOS`
- `SENDERME_VERSAO` — can override the version for update tests

Local API endpoints include:

```text
GET /api/eu
GET /api/mensagens
GET /api/rede
```

Inspect the implementation for current request formats and behavior
before relying on an endpoint.

## Test environment quirks

In the environment where these notes were recorded, `pkill` was blocked.
Check the current environment rather than assuming process termination
is always unavailable.

When process cleanup is restricted:

- Start test servers with a bounded lifetime, for example using
  `timeout N`.
- Use fresh directories and distinct available ports for each batch.
- Ensure test processes have exited before reusing resources.

Check port availability using an appropriate operating-system tool or a
bind attempt. A failed `curl` request alone does not prove that a port is
free. After starting a server, query `/api/eu` and verify the response
belongs to the expected instance.

For a two-instance test, configure `SENDERME_FIXOS` to point each instance
at the other's TCP port. Typical interactions include:

- `POST /api/login` with a JSON nickname.
- `POST /api/enviar`.
- `POST /api/upload`.
- `GET /api/mensagens?depois=...`.

Confirm exact payloads and expected behavior in the current code.

## Embedded JavaScript

The JavaScript lives inside `PAGINA`, a non-raw triple-quoted Python
string. Escaping must account for both Python and JavaScript.

For example, the Python source may need `\\n` to produce `\n` in the
served JavaScript.

After changing JavaScript:

1. Extract the script from the actual served page.
2. Run `node --check` on the extracted JavaScript when Node.js is
   available.
3. Verify the affected interaction in a browser when possible.

If a check cannot be run, state the limitation rather than assuming it
passed.

## Updates and distribution

`update-manifest.json` signs seven files using the owner-only script
`dono/assinar_update.py`.

When changing a signed file, the manifest and distribution must remain
consistent:

1. Identify whether the changed file is covered by the manifest.
2. Re-sign using the authorized owner process and key when available.
3. Run `bash build_dist.sh`.
4. Verify the relevant files under `dist/SenderMe` are byte-identical to
   their intended source files, for example with `cmp`.
5. Verify the update behavior when the change affects that flow.

Do not fabricate a signature or claim that the update package is valid
if signing or verification could not be completed. Report the blocker
and the remaining steps.

`dono/privada.json` is a secret, and `dados/` contains identity data.
Neither may be included in `dist/`. Preserve the exclusions in
`build_dist.sh` and verify them when changing the build process.

Exit code `42` means an update was applied. `start.sh` must then recopy
and restart the application. Preserve this behavior unless explicitly
changing the update design.

## Git

- Local repo only (`main`, `core.fileMode=false` for FAT32). Check
  `git status`/`git diff` before committing; commit only when asked or to
  checkpoint a verified change.
- Never commit `dados/`, `dono/privada.json`, or `dist/` (all in
  `.gitignore`). Only `dono/assinar_update.py` and `dono/publica.txt` from
  `dono/` are versioned.
- `build_dist.sh` copies an allowlist, so `.git` never leaks into `dist/`.

## Final report

After completing a task, briefly report:

- what changed and why;
- which checks were run and their results;
- any remaining risks, limitations, or incomplete verification;
- whether signing or rebuilding the distribution is still required.

Be precise: distinguish verified behavior from assumptions or untested
expectations.

