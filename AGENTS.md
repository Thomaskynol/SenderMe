# AGENTS.md — SenderMe

## Project and current baseline (2026-11-02, code+manifest 1.23 signed; docs 1.23)

SenderMe is a Python 3 peer-to-peer LAN chat with a local browser interface.
Runtime uses only the Python standard library; Bootstrap is bundled for
offline use. The target includes Linux Mint and a removable FAT32/NTFS/exFAT
volume mounted `noexec`.

Current layout:

- `senderme.py`: thin entry (~110 lines) plus `sm.*` compatibility re-exports;
  mutable state is delegated to `senderme_app.estado` (never import a mutable
  by value). `senderme_app/`: 18 modules by real responsibility (estado, meta,
  persist, presenca, eventos, arquivos, transporte, tcp, udp, manut, update,
  update_store, update_proto, diario, comandos, http, app, preboot), each under 700 lines of owned code
  (no exceptions: `update.py` is 608 lines after the 1.12 Desenho A split, which moved
  the fd-pinned helpers unchanged into the stdlib-only leaf `update_store.py`
  (227 lines, imports nothing from `senderme_app`; `update.py` re-exports them
  for compat); `preboot.py` at 629 lines is under the target and therefore NOT
  an exception — it stays autonomous by design, running as a direct script with
  no package context (boot may run on a partial install; a kill between files
  would destroy mid-recovery; see docs/02). `meta.py` is the
  single source for `VERSAO`, owner public key, and `ARQUIVOS_UPDATE`
  (28 files since v1.12: the 1.11 set plus `update_store.py`; 29 files since v1.18: plus `diario.py`; 25 files since the redesign+dist lane: runtime only, `README.md` and `docs/01-03` out of the signed set and the dist); `dono/assinar_update.py` reads version/list from it.
  `preboot.py` (629 lines) deliberately duplicates the minimal recovery
  instead of importing `senderme_app` (boot may run on a partial install).
  `diario.py` (1.19: `_ArquivoSeguro` failure capture, `CAMPOS_PERMITIDOS`
  allowlist + per-value validation, run-local `peer-N` labels, safe
  `threading.excepthook` with documented limits; 1.20: per-call return under
  lock + cru-free version category) is covered by 35 tests in
  `tests/test_diario.py`. `pagina.py` validates `mid` as `^[0-9a-f]{64}$`
  before interpolating into file href/src (1.21; 2 tests in
  `tests/test_ui_redesign.py` `MidSeguro`).
- `config.py`, `crypto.py`, `pagina.py`: leaf settings, cryptography, and
  embedded HTML/JS (`pagina.py` deliberately not split; see docs/02).
- `start.sh`: copies the full RUNTIME set into `/tmp`, runs Python, loops on
  exit code 42, propagates any other child exit code, cleans `$RUN_DIR` via
  trap. It forces `SENDERME_HOME` to its own application directory.
- `build_dist.sh`: generates `dist/SenderMe` from an explicit allowlist that
  must match `ARQUIVOS_UPDATE` + manifest (tested file-by-file).
- `dono/assinar_update.py` and `update-manifest.json`: owner signing workflow
  (code+manifest in tree v1.23 signed, 26 files; docs at v1.23, see docs/03; real 1.11→1.12
  P2P verified, see docs/04; 1.21→1.22 and 1.22→1.23 P2P verified in the 1.22/1.23 lanes).
- `tests/`: standard-library `unittest` suite (412 tests, incl. real-process
  launcher/dist/boot/migration/2-peer tests). Run:

  ```bash
  python3 -m unittest discover -s tests -v
  ```

Contract notes (v1.23 docs, contract unchanged since v1.12, compatible with v1.11/v1.10): `/api/enviar` returns `estado` ∈
{`entregue`,`guardada`,`somente_memoria`,`erro`} + `transmitida` (UI clears input only on
`entregue`/`guardada`; `transmitida=true`+`somente_memoria` warns without claiming
receipt, keeps text, blocks identical resend until edited; legacy fallback without `estado` preserved)
+ `nivel` ∈ {`local`,`socket`} + `confirmado=false` (never any receipt/read
acknowledgment today) + `peers` (connected peer count; new fields optional,
old values intact); HEAD
responses carry status+headers with zero body bytes; concurrent-swap update
failure returns False with journal preserved and an honest message (never
claims full "rollback" of external effects); tmp files of marker/manifest open
fd-relative O_NOFOLLOW with post-check (Opção B); update offer marks
(peer, version) only after confirmed send, re-offers on dead delivery
connection or next `ver` after failure under a 10 s per-peer cooldown;
if the cooldown suppresses an offer for a still-connected old peer — or the
send fails with the peer still connected — ONE deferred attempt is scheduled
for the end of the window (daemon Timer; revalidates peer/socket/version,
cancelled on disconnect or superseding `ver`; still 1 offer per live
(peer, version));
`SENDERME_NO_BROADCAST=1` suppresses UDP broadcast in tests (unicast kept).
Persistent stdlib diary since v1.18 (`senderme_app/diario.py`): JSON lines in
`<install>/logs/senderme.log` (rotating: main + 5 backups, ~6 MiB) plus autonomous
`logs/preboot.log`; allowlist + per-value validation (no message text, nicks, full IPs/IDs,
keys, paths, arbitrary network data, or `str(exc)`; peers as run-local `peer-N`);
`SENDERME_SEM_LOG=1` disables file logging (including preboot);
`logs/` is git-ignored and outside the signed set and clean dist.
School kit: `dist/SenderMe/` only (app files, no roteiro); `ROTEIRO-ESCOLA.md`
lives at the repo root for the test responsible, outside dist/pendrives/manifest.

Defaults: TCP P2P `13337`, UDP discovery `13338`, HTTP
`127.0.0.1:13336`. Check current code before relying on baseline details.
`docs/01-produto.md`, `docs/02-arquitetura.md`, `docs/03-progresso.md`, and
`docs/04-migracao.md` record product, architecture, progress, and migration.
Round reports (`RELATORIO_*.md`) and `arquivos_e_entregas/` are archived
outside the tree in `SenderMe-historico/relatorios/`, never in git.
Dated history inside docs stays dated; the newest entry is current. Resolve
relevant inconsistencies when changing the app.

Update this overview, commands, and verification instructions when a task
changes the architecture. Do not describe a proposed structure as implemented.

## Working rules and maintainability

- Read relevant code, tests, documentation, and working-tree status first.
- User instructions take precedence over this file. An explicit request for
  broad refactoring authorizes evaluating and reorganizing the project; do not
  reject it merely because this file recommends limited scope by default.
- Otherwise, keep changes proportional to the task and avoid unrelated work.
- Prefer clear names, explicit dependencies, focused responsibilities, and
  straightforward control flow. Extract duplication or abstractions when doing
  so makes the project easier to understand and maintain.
- Organize by real responsibilities and use cases. Avoid circular imports,
  misleading module names, speculative layers, giant catch-all classes, and
  moving a monolith into multiple files while keeping hidden coupling intact.
- Aim for at most 700 lines per file of project-owned source code. Treat this
  as a target, not a correctness test: document a concrete reason for an
  exception instead of splitting solely to reach a number. Generated and
  third-party assets are exempt. Existing debt is not a reason to block an
  unrelated task, but explicit refactoring work may address it.
- Preserve external behavior, on-disk data, protocol formats, and startup
  commands unless a requested change or an identified bug requires otherwise.
  Describe and test intended behavior changes separately.
- Do not add third-party runtime dependencies without explicit authorization.
  Do not modify cryptographic schemes or P2P wire formats casually.
- Keep docs current where affected. Commands, versions, and claims must be
  verified against the actual tree; do not invent behavior or test results.

## State, concurrency, and persistence

Shared mutable state lives in `senderme_app/estado.py` (single owner), used by
networking, HTTP, maintenance, and storage via `S.*` with locks `L` (state)
and `_disco` (persistence). When moving responsibilities, keep the owner
explicit: object lifetime, lock ownership and acquisition
order, and which operations require synchronization. Avoid importing a mutable
or reassignable global by value across modules. Keep refactors incremental;
verify concurrency-sensitive behavior before and after moving it.

Treat absence, corruption, and I/O failures as different states:

- Never silently replace an existing unreadable or invalid identity with a new
  one. Preserve the original and report an actionable error.
- Never report successful persistence when an identity, history, or other
  important write failed. Handle and surface relevant errors safely.
- Do not test against real `dados/`; use isolated temporary directories and
  synthetic identities, peers, and messages.

## Security and privacy

- `dono/privada.json` is the owner's update-signing secret. `dados/` may hold
  a private identity, messages, and attachments. Do not print, upload, commit,
  distribute, or use them as test fixtures. Do not copy them into public
  backups or review packages.
- Check `.gitignore` and the actual distribution; an ignore rule alone does not
  prove a file was never committed or included in an archive.
- Use temporary synthetic signing keys for automated and migration tests.
  Never rotate, overwrite, delete, or re-sign with the real owner key as part
  of a test. Coordinate real release signing and key migration deliberately.
- Treat network data, peer-supplied filenames, uploads, manifests, and local
  HTTP requests as untrusted. Validate relevant inputs, bounds, paths, and
  origins at the boundary; do not leak secrets in errors or logs.
- Bind the browser server to `127.0.0.1` unless explicitly authorized to
  change it. Localhost alone is not a complete defense against a web page
  sending requests to local services; test protections on mutating routes.
- Do not claim confidentiality or end-to-end encryption for the existing DMs:
  the current product describes direct DMs without additional encryption.
- Preserve existing crypto and wire behavior during structural refactoring;
  separate any protocol or security design change and demonstrate compatibility.

## Update, launcher, and distribution

These components form one release contract: runtime files, `start.sh`,
`build_dist.sh`, version, manifest, owner signer, public verification key,
P2P update transfer, and the receiving launcher's restart behavior.

- Same-version updates are rejected. Do not reuse a
  version number for a changed release and claim existing peers will update.
- Signed set = `ARQUIVOS_UPDATE` (26 files since the 1.22 lane: 1.21 set plus `TERCEIROS.md`; runtime
  only: `README.md`, `docs/01-03`, `ROTEIRO-ESCOLA.md`, `AGENTS.md`, and `.gitignore` are unsigned): editing any of them requires a version bump plus the
  official re-sign (`python3 dono/assinar_update.py`).
  This round (1.23 final integration) absorbed the pousado layout fix
  (`pagina.py` CSS/structure only + textarea rows 3→2, JS byte-identical,
  11 `test_ui_layout` Chromium tests), bumped "atual" to 1.23
  in README and docs/01-03 (+ 1.22→1.23 row in docs/04), and re-signed as 1.23;
  `dist/` and P2P release as the signed 1.23 envelope.
  (Previous round (1.22 final integration) absorbed the pousado draft-preservation fix
  (`pagina.py` snapshot txt/para/arquivo + button held disabled while `enviando`,
  16 `test_ui_preserva_rascunho` tests) and the pousado `TERCEIROS.md` MIT notice
  (root, `meta` 26 files, build allowlist, 6 `Terceiros` tests),
  bumped "atual" to 1.22
  in README and docs/01-03 (+ 1.21→1.22 row in docs/04), and re-signed as 1.22;
  `dist/` and P2P release as the signed 1.22 envelope.
  (Previous round (1.21 final integration) fixed the `pagina.py` review finding
  (`mid` validated as `^[0-9a-f]{64}$` before href/src, +2 `MidSeguro` tests),
  moved `SenderMe-checkpoints/` out of the tree, bumped "atual" to 1.21
  in README and docs/01-03 (+ 1.20→1.21 row in docs/04), and re-signed as 1.21;
  `dist/` and P2P release as the signed 1.21 envelope.
  (Previous round (1.20 final integration) absorbed the pousado diary race fix
  (per-call return under lock, cru-free version category, 35 diary tests)
  and the root-level school roteiro, bumped "atual" to 1.20
  in README and docs/01-03, and re-signed as 1.20;
  `dist/` and P2P release as the signed 1.20 envelope.
  (Previous round fixed the diary (failure capture, SEM_LOG preboot, `peer-N`
  labels, value allowlist, thread hook), bumped "atual" to 1.19
  in README and docs/01-03, and re-signed as 1.19.)
  `docs/04-migracao.md`, `docs/05-roteiro-escola.md` (pointer), `ROTEIRO-ESCOLA.md`, `AGENTS.md`, and `.gitignore` are unsigned.
- The old `start.sh` from `24176fa` copies only `senderme.py` and CSS. An
  already-running old launcher continues its old restart loop even if the
  file on disk is replaced, and exits 0 even when Python fails. P2P update
  from ≤1.2 applies the files but cannot auto-restart (demonstrated in
  `tests/test_migracao_legada.py`); the documented path is the manual
  migration in `docs/04-migracao.md` (re-run the new `start.sh`, same `dados/`).
- The updater persists the signed `{manifest, sig}` envelope on apply (needed
  for A→B→C propagation), stages to `.upd-staging/`, backs up to
  `.upd-backup/` with a `.upd-pendente.json` marker, rolls back on any write
  failure, and recovers at boot. Treat propagation,
  interruption, rollback/recovery, and version coherence as release-critical.
- Confirm that every new runtime module and asset is copied, distributed,
  signed, verified, and served where applicable. Do not include `dados/`,
  `dono/`, keys, `.git/`, caches, or tests' private fixtures in a user build.
- Use a synthetic signed release in temporary directories for E2E tests.
  Check tampering, equal/older versions, real restart and multi-peer
  propagation. Validate actual output files and exit statuses, not just text
  patterns in scripts.
- Preserve exit code 42 as the restart contract unless a documented, tested
  change replaces it. Propagate other child process failures appropriately.
- If a real signature, a legacy migration, or a supported device cannot be
  verified, report the specific limitation; do not claim release readiness.

## Run and test safely

Production: `bash start.sh`. Do not launch it against a real installation for
tests: it forces `SENDERME_HOME=$APP_DIR` and may read or modify real data.
A copied, fully isolated test installation with its own synthetic `dados/` is
appropriate for launcher and update E2E tests.

For direct isolated runs, set a new `SENDERME_HOME` and distinct available
`SENDERME_PORTA`, `SENDERME_UDP_PORTA`, and `SENDERME_HTTP` values. Use
`SENDERME_FIXOS=127.0.0.1:<peer-tcp-port>` for local peer connections.
`SENDERME_VERSAO` exists for tests; confirm both code and manifest versions
when testing updates. Select available ports by binding or an appropriate OS
tool; failed `curl` alone does not establish that a port is free.

Add and run tests proportional to risk. For meaningful runtime or structural
changes, retain relevant unit tests and exercise the affected behavior end to
end when feasible. Use real process, file, and protocol interactions where
necessary; mocks alone cannot establish launcher or distribution behavior.

When JavaScript or serving changes, check the actual JS delivered by the
server using `node --check` when available and test the interaction in a
browser if feasible. Until the embedded page is moved, remember the double
escaping in the non-raw Python string. Never replace runtime JS validation
with syntax checks on the Python source alone.

Use bounded processes and clean up only resources created by the test. Keep
true exit codes; do not mask failures with pipes or unconditional `exit 0`.
Describe environmental limitations and distinguish test evidence from claims.

## Git and completion

Inspect `git status` and preserve tracked **and untracked** user changes.
The `24176fa` commit does not contain the modular files and tests in the
reviewed working tree. Do not use `git reset --hard`, `git clean`, destructive
restores, push, PR, publication, or distribution unless explicitly requested.
Use isolated copies or a safe local checkpoint that includes the intended
untracked source files and excludes sensitive data.

Report the actual changes, verification commands and outcomes, compatibility
and signing status, remaining risks, and anything not tested. A passing suite
is evidence for the cases it covers, not proof that the entire product works.
