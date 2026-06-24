# Plan: Remove all FreePBX/Issabel code → pure-Asterisk only

## Goal
Remove every FreePBX- and Issabel-specific code path so the project is pure-Asterisk only. Keep the CDR feature fully working (CDR table moves into the OpDesk database).

## Locked decisions
- Remove Issabel mode too (project becomes pure-Asterisk only).
- CDR table lives inside the **OpDesk** database (`DB_CDR=OpDesk`), matching `compose.yml`.
- Remove the `PBX` env var and the QoS-status `pbx` field entirely.
- Remove the FreePBX SIP-secret/username/name table writers and their call sites.
- Mobile-wake hook targets the configured internal context (from `AMI_CONTEXT`, default `from-internal`), replacing the FreePBX `[from-internal-custom]` / `from-internal-additional` / `DB(AMPUSER/...)` mechanism.

## File-by-file changes

### `backend/db_manager.py`
- Delete `_is_pure_asterisk()`.
- Collapse every `if _is_pure_asterisk(): return <pure body>` to the pure body (unconditional):
  - `get_extensions_from_db` → only `inventory.get_extensions()`.
  - `get_extension_names_from_db` → only `inventory.get_extension_names()`.
  - `get_queue_names_from_db` → only `inventory.get_queue_names()`.
  - `get_extension_secret_from_db` → only `_get_pure_asterisk_secret()`.
- Delete the FreePBX/Issabel MySQL reads: `users`, `ps_endpoints`, `queues_config`, `sip` queries and their fallback blocks.
- Delete `_upsert_sip_keyword`, `set_extension_secret_in_pbx`, `set_extension_username_in_pbx`, `set_extension_name_in_pbx`.
- Rewrite `set_extension_webrtc(extension, enabled)`:
  - Drop the `PBX` parameter, the `is_issabel` branch, the FreePBX `sip`/`certman_mapping` writes, and the `reload_asterisk_sip(PBX)` call.
  - Keep only the pure-mode body: update `OpDesk.users.webrtc` and return.
- Drop `DB_NAME`/`asterisk` references from `get_db_config` calls; CDR functions keep using `DB_CDR`.
- Remove the `from dialplan import reload_asterisk_sip` import block (no longer needed here).
- Update module docstring (remove "FreePBX").

### `backend/dialplan.py`
- `reload_asterisk_sip()`: reduce to a pure-Asterisk no-op that logs and returns `True` (endpoints are managed in `pjsip.conf`). Drop the `PBX` param, Issabel `retrieve_conf` branch, and `fwconsole reload` branch.
- `_detect_tls_mode()`: remove the `"freepbx"` branch and the `/etc/asterisk/pjsip.transports.conf` check. Return a single target: first existing of `pjsip_custom_post.conf` / `pjsip_custom.conf`, defaulting to `/etc/asterisk/pjsip_custom_post.conf`. Drop the mode token (or always `"asterisk"`).
- `enable_sip_tls()` / `disable_sip_tls()`: keep only the `[opdesk-sip-tls]` transport write into the custom pjsip file (the former Issabel branch becomes the only path). Remove the `"freepbx"` `[0.0.0.0-tls]` override block. Keep `_reload_asterisk()` (`core restart now`) and ufw rules.
- `write_qos_conf()`: replace `[from-internal-custom]` / `[from-pstn-custom]` overrides with hook injection into the configured internal context (`AMI_CONTEXT`, default `from-internal`) + the hangup-handler push. Remove FreePBX context names from comments.
- `write_mobile_wake_conf()`:
  - Inject the wake step into the configured internal context (`AMI_CONTEXT`) instead of `[from-internal-custom]`.
  - Remove `DB(AMPUSER/${EXTEN}/device)` check (FreePBX AstDB key) — keep the `PJSIP_DIAL_CONTACTS` registered-contact check and the CURL wake + `Wait()`.
  - Replace `Goto(from-internal-additional,${EXTEN},1)` with continuing the normal dial in the same configured context (wake-then-proceed so `DialBegin` still fires for AMI push).
  - Rewrite the docstring/comments to the pure-Asterisk flow.
- `remove_mobile_wake_conf()`, `enable/disable_mobile_wake()`: unchanged logic; update comments.
- Update `reload_asterisk_dialplan()` comments (it already uses `asterisk -rx dialplan reload`).

### `backend/server.py`
- Remove imports: `set_extension_secret_in_pbx`, `set_extension_username_in_pbx`, `set_extension_name_in_pbx`, and `reload_asterisk_sip` (line ~40, ~43) — keep `set_extension_webrtc` (now param-free) and the QoS/TLS/mobile-wake imports.
- In create-user and update-user endpoints: remove the `set_extension_*_in_pbx(...)` calls and the `reload_asterisk_sip()` calls; keep `db_create_user`/`db_update_user` (OpDesk users table still records name/extension).
- In the WebRTC endpoint: call `set_extension_webrtc(extension=ext, enabled=enabled)` (drop `PBX=os.getenv('PBX')`).
- `GET /api/qos/status` (~line 1990): remove the `"pbx": get_setting('PBX', os.getenv('PBX','FreePBX'))` field.
- Update the admin-seed comment (~634) and inventory-load comment (~714) to drop "FreePBX".

### `backend/ami.py`
- Comment/docstring cleanup only: lines ~772, ~788-789, ~1295-1300, ~2670-2676 — remove "FreePBX" mentions; trunk-naming logic (`PJSIP/asterisk-*`, `SIP/asterisk-*`) can stay as legacy detection but reword comments. Keep `load_inventory()`.

### `backend/inventory.py`
- Update module docstring (lines 2-6) to drop the FreePBX/Issabel contrast; describe it as the live AMI inventory source.

### `backend/call_log.py`
- Update the `get_answer_time` docstring (~line 188) from "FreePBX CDR row" to "Asterisk CDR row". Logic unchanged.

### `backend/schema.sql`
- Update comment (~line 187) to drop "populated lazily from FreePBX".

### `backend/02-cdr-schema.sql`
- Keep the file (CDR still used). Update the comment (~line 8) from "mirrors the standard FreePBX asteriskcdrdb.cdr layout" to "standard Asterisk CDR layout, loaded into the OpDesk database".

### `.env`
- Remove `PBX=Asterisk`, `DB_NAME=asterisk` (unused). Set `DB_CDR=OpDesk`. Keep `DB_OpDesk=OpDesk`, `AMI_CONTEXT`.
- Rewrite the header/comments to drop FreePBX mentions (lines 1, 5, 16-17, 70-71).

### `.env.example`
- Remove `PBX=FreePBX` (line 2). Remove `DB_NAME=asterisk`; set `DB_CDR=OpDesk`. Update the `pjsip` channel-driver comment (~line 25) to drop the FreePBX reference. Keep `AMI_CONTEXT=from-internal` (pure-Asterisk default; was `ext-local`).

### `install.sh`
- Step 6 PBX detection (~lines 316-457): collapse to a single pure-Asterisk path. Delete the Issabel branch (`/etc/issabel.conf`, `/usr/share/issabel`, `_root_pass` from issabel) and the FreePBX branch (`/etc/freepbx.conf`). Keep the "Generic" path as the only path; set `DB_USER="OpDesk"` and create the user.
- DB grants: replace `GRANT ... ON asterisk.* / asteriskcdrdb.*` with `GRANT ALL PRIVILEGES ON OpDesk.*` only (all three sudo/root fallback blocks + the manual-instructions echo).
- `.env` write block (~lines 1016-1025): remove `PBX=$PBX`, `DB_NAME=$DB_NAME`; write `DB_CDR=OpDesk`. Update the `AMI_CONTEXT` default-note comment (~line 1003) to drop "FreePBX/Issabel".
- Remove the `DB_NAME="asterisk"` default (~line 312) and `PBX="Generic"` tracking (~line 316, 479) where it's now vestigial.
- httpd/CentOS comments (~lines 669, 674): drop "FreePBX"/"issabel.conf" references.

### `compose.yml`
- Keep the `02-cdr-schema.sql` mount. Update the comment (lines 23-25) to remove "FreePBX asteriskcdrdb" wording: "CDR table + seed data. Loaded into the OpDesk database; reads use DB_CDR=OpDesk."

### `README.md`
- Rewrite compatibility/requirements/architecture sections to pure-Asterisk only. Remove FreePBX/Issabel mentions (lines 3, 13, 43, 49, 51, 78, 82, 85, 304, 319, 387). Drop the FreePBX port-80/443 warning block. Keep AMI/WSS/MySQL(OpDesk) requirements.

## Out of scope
- No changes to `frontend/**` (no FreePBX references; `pbx` field already unused by UI).
- No changes to `Dockerfile`, `start.sh`, `nginx/opdesk.conf` (no FreePBX references).
- CDR query logic in `db_manager.py`/`analytics.py`/`call_log.py` is unchanged (still reads via `DB_CDR`).

## Risks & key validation
- **Mobile-wake hook rewrite (highest risk):** FreePBX's context graph (`from-internal-custom` → `from-internal-additional`) no longer exists. Must confirm the operator's internal context name (`AMI_CONTEXT`) and that wake-then-continue still produces a `DialBegin` AMI event so push fires. Test with a backgrounded softphone.
- **TLS enable:** verify `pjsip_custom_post.conf` is actually `#include`d by the pure-Asterisk `pjsip.conf` and that `core restart now` applies the `[opdesk-sip-tls]` transport on 5061.
- **WebRTC toggle:** now only flips `OpDesk.users.webrtc`; confirm the WebRTC tab still lists/toggles and that pjsip.conf WebRTC endpoints (static) keep working.
- **User create/update:** confirm it still succeeds without the PBX writers (OpDesk users row updated; no SIP-side write — documented as expected).
- **CDR:** confirm call log + analytics populate from the OpDesk DB after a test call.

## Validation steps
1. Backend boots with the cleaned `.env` (no `PBX`, `DB_CDR=OpDesk`).
2. `GET /api/extensions` and queue/extension-name lists load from AMI inventory.
3. `GET /api/qos/status` returns JSON without a `pbx` field.
4. Create/update a user → succeeds; no SIP write attempted.
5. Toggle WebRTC on an extension → `users.webrtc` updated; no error.
6. Enable SIP TLS → `[opdesk-sip-tls]` written to `pjsip_custom_post.conf`; Asterisk restarts; 5061 listening.
7. Enable mobile wake → wake step injected into the configured internal context; test call to a backgrounded mobile app rings after wake.
8. Place a call → CDR row appears in OpDesk DB; call log + analytics populate.
9. `grep -ri freepbx .` and `grep -ri issabel .` return only acceptable vestiges (if any) — target: zero in source/config, none functional.

## Open question for implementation
- Exact mobile-wake dialplan form in the configured context (Gosub include vs. context-pattern override) depends on the operator's dialplan structure; implementer should prefer a `Gosub`-style include that does not shadow the existing context's `Dial()`, and document the required `AMI_CONTEXT`.
