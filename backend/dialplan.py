#!/usr/bin/env python3
"""
QoS (Quality of Service) Configuration Module

Enables QoS tracking by configuring Asterisk dialplan files.
"""

import logging
import os
import subprocess
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
log = logging.getLogger(__name__)

# Asterisk configuration paths
EXTENSIONS_CUSTOM_CONF = "/etc/asterisk/extensions_custom.conf"
EXTENSIONS_OPDESK_CONF = "/etc/asterisk/extensions_opdesk.conf"
EXTENSIONS_MOBILE_WAKE_CONF = "/etc/asterisk/extensions_mobile_wake.conf"


def write_qos_conf():
    """
    Write the QoS dialplan sections to a dedicated extensions_opdesk.conf
    and ensure it is included from extensions_custom.conf.

    The hangup handler is pushed on every call that enters the configured
    internal context (`AMI_CONTEXT`, default `from-internal`) — the same context
    every incoming / internal dial lands in, regardless of how the PBX is set up.
    """
    log.info(f"Writing QoS dialplan to {EXTENSIONS_OPDESK_CONF}")

    internal_ctx = os.getenv("AMI_CONTEXT", "from-internal").strip() or "from-internal"

    custom_content = f"""; OpDesk QoS dialplan — auto-generated. Do not edit manually.
; Pushed via the hangup handler when any call enters the configured internal context
; (AMI_CONTEXT = {internal_ctx}). The handler samples RTPAUDIOQOS and stores it on
; the CDR userfield so analytics can read it after the call.

[{internal_ctx}]
exten => _.,1,Set(CHANNEL(hangup_handler_push)=qos-handler,s,1)

[qos-handler]
exten => s,1,NoOp(-- QoS Handler Start --)
 same => n,Set(QOS_SRC=${{IF($["${{RTPAUDIOQOSBRIDGED}}"!=""]?${{RTPAUDIOQOSBRIDGED}}:${{RTPAUDIOQOS}})}})
 same => n,GotoIf($["${{QOS_SRC}}" != ""]?save)
 same => n,Set(QOS_SRC=${{DB(qos/${{CHANNEL(linkedid)}}/data)}})

 same => n(save),GotoIf($["${{QOS_SRC}}" = ""]?end)
 same => n,Set(QOS_CALLER=${{IF($["${{DB(qos/${{CHANNEL(linkedid)}}/caller)}}"!=""]?${{DB(qos/${{CHANNEL(linkedid)}}/caller)}}:${{CALLERID(num)}})}})
 same => n,Set(CDR(userfield)=QoS:${{QOS_SRC}},Caller:${{QOS_CALLER}})
 same => n,NoOp(Saved QoS to CDR: ${{CDR(userfield)}})
 same => n,DBdeltree(qos/${{CHANNEL(linkedid)}})
 same => n(end),NoOp(QoS Handler Finished)
 same => n,Return()
"""
    try:
        import tempfile

        # 1) Write or overwrite the dedicated OpDesk QoS file
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp_file:
            tmp_file.write(custom_content)
            opdesk_tmp_path = tmp_file.name

        result_opdesk = subprocess.run(
            ['sudo', 'cp', opdesk_tmp_path, EXTENSIONS_OPDESK_CONF],
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ['sudo', 'chmod', '644', EXTENSIONS_OPDESK_CONF],
            capture_output=True,
            text=True,
        )

        os.unlink(opdesk_tmp_path)

        if result_opdesk.returncode != 0:
            log.error(f"Failed to write to {EXTENSIONS_OPDESK_CONF}: {result_opdesk.stderr}")
            return False

        log.info(f"Successfully wrote QoS custom dialplan to {EXTENSIONS_OPDESK_CONF}")

        # 2) Ensure extensions_custom.conf includes the OpDesk file
        include_lines = {
            f"#include {os.path.basename(EXTENSIONS_OPDESK_CONF)}",
            f"#include {EXTENSIONS_OPDESK_CONF}",
        }

        existing_content = ""
        if os.path.exists(EXTENSIONS_CUSTOM_CONF):
            with open(EXTENSIONS_CUSTOM_CONF, 'r') as f:
                existing_content = f.read()

        # If any acceptable include line already exists, we are done with this part
        if any(line in existing_content for line in include_lines):
            log.info(f"{EXTENSIONS_CUSTOM_CONF} already includes {EXTENSIONS_OPDESK_CONF}")
            return True

        # Append a simple relative include by default
        if existing_content and not existing_content.endswith('\n'):
            existing_content += '\n'
        existing_content += f"#include {os.path.basename(EXTENSIONS_OPDESK_CONF)}\n"

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp_file:
            tmp_file.write(existing_content)
            custom_tmp_path = tmp_file.name

        result_custom = subprocess.run(
            ['sudo', 'cp', custom_tmp_path, EXTENSIONS_CUSTOM_CONF],
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ['sudo', 'chmod', '644', EXTENSIONS_CUSTOM_CONF],
            capture_output=True,
            text=True,
        )

        os.unlink(custom_tmp_path)

        if result_custom.returncode == 0:
            log.info(
                f"Ensured {EXTENSIONS_CUSTOM_CONF} includes {os.path.basename(EXTENSIONS_OPDESK_CONF)}"
            )
            return True

        log.error(f"Failed to update {EXTENSIONS_CUSTOM_CONF}: {result_custom.stderr}")
        return False

    except Exception as e:
        log.error(f"Error writing QoS configuration files: {e}")
        return False


def reload_asterisk_dialplan():
    """Reload Asterisk dialplan using 'asterisk -rx dialplan reload'."""
    log.info("Reloading Asterisk dialplan...")
    
    try:
        result = subprocess.run(
            ['sudo', 'asterisk', '-rx', 'dialplan reload'],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            log.info("Successfully reloaded Asterisk dialplan")
            return True
        else:
            log.error(f"Failed to reload dialplan: {result.stderr}")
            return False
            
    except subprocess.TimeoutExpired:
        log.error("Timeout while reloading Asterisk dialplan")
        return False
    except Exception as e:
        log.error(f"Error reloading dialplan: {e}")
        return False


def reload_asterisk_sip():
    """
    No-op for pure-Asterisk deployments.

    Endpoints are managed statically in `pjsip.conf`, so there is no
    fwconsole/retrieve_conf to run. Kept as a stable entry point for callers
    that still want to reload after a config write; returns True.
    """
    log.info("PBX=Asterisk (pure) — skipping SIP/config reload (manage pjsip.conf directly)")
    return True


def write_mobile_wake_conf(backend_port: int = None, wait_seconds: int = None) -> bool:
    """
    Install an automatic "wake before dial" hook as a standalone context
    `[opdesk-mobile-wake]`.

    The hook is designed to be called via `Gosub(opdesk-mobile-wake,s,1)` from
    the operator's internal context (`AMI_CONTEXT`), e.g.:

        ; in AMI_CONTEXT (the operator's dialplan)
        exten => _XXX,1,Gosub(opdesk-mobile-wake,s,1)
         same =>  n,Dial(PJSIP/${EXTEN},60)

    Pure-Asterisk mode (no FreePBX context graph):
      * We do NOT shadow the existing `Dial()` for the pattern — the operator
        keeps full control over their dialplan.
      * We do NOT use `DB(AMPUSER/${EXTEN}/device)` — that AstDB key only exists
        on FreePBX/Issabel deployments. We rely entirely on `PJSIP_DIAL_CONTACTS()`
        to detect an already-registered mobile SIP contact; if present, the hook
        falls through immediately (no wake, zero added latency).
      * Otherwise CURLs the backend wake endpoint. The endpoint returns "1"
        only when the extension has a registered mobile push token; only then
        do we `Wait()` for the app to come up.
      * `Return()` hands control back to the caller's same priority+1 so the
        operator's `Dial()` (and the AMI `DialBegin` event) still fire.
    """
    if backend_port is None:
        backend_port = int(os.getenv("PORT", "8765"))
    if wait_seconds is None:
        wait_seconds = int(os.getenv("MOBILE_WAKE_WAIT", "3"))

    log.info(f"Writing mobile wake dialplan to {EXTENSIONS_MOBILE_WAKE_CONF}")

    content = f"""; OpDesk mobile wake dialplan — auto-generated. Do not edit manually.
;
; Pure-Asterisk mode: this is a standalone context callable via
;   Gosub(opdesk-mobile-wake,s,1) from the operator's AMI_CONTEXT.
; See backend/dialplan.write_mobile_wake_conf docstring for usage.
;
; Wakes a killed/backgrounded mobile softphone BEFORE the operator's
; Dial() resolves its SIP contact, so the app has time to re-register
; and actually ring. Tunable: MOBILE_WAKE_WAIT (seconds to wait after
; the push) in the backend .env.

[opdesk-mobile-wake]
exten => s,1,NoOp(OpDesk mobile wake for ${{EXTEN}})
 same => n,GotoIf($["${{PJSIP_DIAL_CONTACTS(${{EXTEN}})}}"!=""]?return)
 same => n,Set(CURLOPT(conntimeout)=2)
 same => n,Set(CURLOPT(httptimeout)=3)
 same => n,Set(OPDESKWAKE=${{CURL(http://127.0.0.1:{backend_port}/api/internal/mobile-wake/${{EXTEN}}?caller=${{URIENCODE(${{CALLERID(num)}})}})}})
 same => n,ExecIf($["${{OPDESKWAKE}}"="1"]?Wait({wait_seconds}))
 same => n(return),Return()
"""
    try:
        import tempfile

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        result = subprocess.run(
            ['sudo', 'cp', tmp_path, EXTENSIONS_MOBILE_WAKE_CONF],
            capture_output=True, text=True,
        )
        subprocess.run(['sudo', 'chmod', '644', EXTENSIONS_MOBILE_WAKE_CONF], capture_output=True)
        os.unlink(tmp_path)

        if result.returncode != 0:
            log.error(f"Failed to write {EXTENSIONS_MOBILE_WAKE_CONF}: {result.stderr}")
            return False

        # Ensure extensions_custom.conf includes the new file (so the operator's
        # AMI_CONTEXT — which typically includes extensions_custom.conf — can
        # Gosub into it).
        include_line = f"#include {os.path.basename(EXTENSIONS_MOBILE_WAKE_CONF)}"
        existing = ""
        if os.path.exists(EXTENSIONS_CUSTOM_CONF):
            with open(EXTENSIONS_CUSTOM_CONF, 'r') as f:
                existing = f.read()

        if include_line not in existing:
            if existing and not existing.endswith('\n'):
                existing += '\n'
            existing += include_line + '\n'
            with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp:
                tmp.write(existing)
                tmp_path = tmp.name
            subprocess.run(['sudo', 'cp', tmp_path, EXTENSIONS_CUSTOM_CONF], capture_output=True)
            subprocess.run(['sudo', 'chmod', '644', EXTENSIONS_CUSTOM_CONF], capture_output=True)
            os.unlink(tmp_path)

        log.info(f"Mobile wake dialplan written to {EXTENSIONS_MOBILE_WAKE_CONF}")
        return True

    except Exception as e:
        log.error(f"Error writing mobile wake conf: {e}")
        return False


def remove_mobile_wake_conf() -> bool:
    """Clear the mobile wake dialplan context (disables the feature)."""
    log.info(f"Clearing mobile wake dialplan from {EXTENSIONS_MOBILE_WAKE_CONF}")
    try:
        import tempfile
        if not os.path.exists(EXTENSIONS_MOBILE_WAKE_CONF):
            return True
        minimal = "; OpDesk mobile wake disabled\n"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp:
            tmp.write(minimal)
            tmp_path = tmp.name
        result = subprocess.run(['sudo', 'cp', tmp_path, EXTENSIONS_MOBILE_WAKE_CONF], capture_output=True, text=True)
        subprocess.run(['sudo', 'chmod', '644', EXTENSIONS_MOBILE_WAKE_CONF], capture_output=True)
        os.unlink(tmp_path)
        if result.returncode != 0:
            log.error(f"Failed to clear {EXTENSIONS_MOBILE_WAKE_CONF}: {result.stderr}")
            return False
        log.info("Mobile wake dialplan cleared")
        return True
    except Exception as e:
        log.error(f"Error clearing mobile wake conf: {e}")
        return False


def enable_mobile_wake(wait_seconds: int = None) -> bool:
    """Enable the mobile pre-dial wake dialplan and reload Asterisk."""
    if not write_mobile_wake_conf(wait_seconds=wait_seconds):
        return False
    return reload_asterisk_dialplan()


def disable_mobile_wake() -> bool:
    """Disable the mobile pre-dial wake dialplan and reload Asterisk."""
    if not remove_mobile_wake_conf():
        return False
    return reload_asterisk_dialplan()


def remove_qos_conf():
    """
    Remove the QoS dialplan contents from extensions_opdesk.conf,
    but keep the file itself and the #include in extensions_custom.conf.
    """
    log.info(f"Clearing QoS custom dialplan from {EXTENSIONS_OPDESK_CONF}")

    try:
        import tempfile

        # If the OpDesk file does not exist, nothing to clean
        if not os.path.exists(EXTENSIONS_OPDESK_CONF):
            log.info(f"{EXTENSIONS_OPDESK_CONF} does not exist. Nothing to clear.")
            return True

        # Write an empty (or minimal) file so QoS contexts are removed
        minimal_content = "; QoS disabled – OpDesk dialplan cleared by OpDesk backend\n"

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.conf') as tmp_file:
            tmp_file.write(minimal_content)
            tmp_path = tmp_file.name

        result = subprocess.run(
            ['sudo', 'cp', tmp_path, EXTENSIONS_OPDESK_CONF],
            capture_output=True,
            text=True,
        )

        subprocess.run(
            ['sudo', 'chmod', '644', EXTENSIONS_OPDESK_CONF],
            capture_output=True,
            text=True,
        )

        os.unlink(tmp_path)

        if result.returncode == 0:
            log.info(f"Successfully cleared QoS dialplan from {EXTENSIONS_OPDESK_CONF}")
            return True

        log.error(f"Failed to clear {EXTENSIONS_OPDESK_CONF}: {result.stderr}")
        return False

    except Exception as e:
        log.error(f"Error clearing QoS configuration file: {e}")
        return False


def enable_qos():
    """Main function to enable QoS configuration."""
    log.info("Enabling QoS configuration...")
    
    # Write QoS configuration
    if not write_qos_conf():
        log.error("Failed to write QoS configuration. Aborting.")
        return False
    
    # Reload dialplan
    if not reload_asterisk_dialplan():
        log.error("Failed to reload dialplan. Configuration may not be active.")
        return False
    
    log.info("QoS configuration enabled successfully!")
    return True


def disable_qos():
    """Main function to disable QoS configuration."""
    log.info("Disabling QoS configuration...")
    
    # Clear QoS configuration from the OpDesk dialplan file
    if not remove_qos_conf():
        log.error("Failed to clear QoS configuration. Continuing...")
    
    # Reload dialplan
    if not reload_asterisk_dialplan():
        log.error("Failed to reload dialplan. Configuration may still be active.")
        return False
    
    log.info("QoS configuration disabled successfully!")
    return True


# Markers written around OpDesk's TLS block so we can find and remove it cleanly
_TLS_MARKER_START = "; --- OpDesk SIP TLS BEGIN ---"
_TLS_MARKER_END   = "; --- OpDesk SIP TLS END ---"


def _detect_tls_mode():
    """
    Pick the PJSIP custom config file for the TLS transport block.

    Pure-Asterisk mode: write the `[opdesk-sip-tls]` transport into the first
    existing of `pjsip_custom_post.conf` / `pjsip_custom.conf`, falling back to
    `/etc/asterisk/pjsip_custom_post.conf`. Returns (mode, config_file) where
    `mode` is always `"asterisk"`.
    """
    for candidate in ("/etc/asterisk/pjsip_custom_post.conf",
                      "/etc/asterisk/pjsip_custom.conf"):
        if os.path.isfile(candidate):
            return "asterisk", candidate

    return "asterisk", "/etc/asterisk/pjsip_custom_post.conf"


def _write_to_file(path: str, content: str) -> bool:
    """Overwrite a file via sudo tee."""
    try:
        result = subprocess.run(
            ["sudo", "tee", path],
            input=content.encode(),
            capture_output=True,
        )
        if result.returncode != 0:
            log.error(f"tee {path} failed: {result.stderr.decode()}")
            return False
        return True
    except Exception as e:
        log.error(f"Failed to write {path}: {e}")
        return False


def _remove_opdesk_block(path: str) -> bool:
    """Remove the OpDesk TLS marker block from a file, leave the rest intact."""
    if not os.path.isfile(path):
        return True
    try:
        result = subprocess.run(["sudo", "cat", path], capture_output=True)
        if result.returncode != 0:
            return False
        lines = result.stdout.decode(errors="replace").splitlines(keepends=True)
        out, inside = [], False
        for line in lines:
            if _TLS_MARKER_START in line:
                inside = True
            if not inside:
                out.append(line)
            if _TLS_MARKER_END in line:
                inside = False
        return _write_to_file(path, "".join(out))
    except Exception as e:
        log.error(f"Failed to remove OpDesk TLS block from {path}: {e}")
        return False


def _reload_asterisk(mode: str) -> bool:
    """Restart Asterisk immediately to pick up transport changes.

    TLS transports have allow_reload=false, so a module reload is not enough.
    'core restart now' is used instead of 'graceful' because graceful waits
    for all active calls to end — on a busy PBX this can mean it never fires.
    """
    result = subprocess.run(
        ["sudo", "asterisk", "-rx", "core restart now"],
        capture_output=True,
    )
    if result.returncode != 0:
        log.error(f"Asterisk restart failed: {result.stderr.decode()}")
        return False
    log.info("Asterisk restarted — TLS transport changes applied")
    return True


def enable_sip_tls(domain: str) -> bool:
    """Enable SIP TLS on port 5061 using the Let's Encrypt cert for the given domain."""
    le_cert = f"/etc/letsencrypt/live/{domain}/fullchain.pem"
    le_key  = f"/etc/letsencrypt/live/{domain}/privkey.pem"

    if not os.path.isfile(le_cert) or not os.path.isfile(le_key):
        log.error(f"Let's Encrypt cert not found for domain '{domain}'. Expected: {le_cert}")
        return False

    # /etc/letsencrypt/live and /archive are root-only — asterisk can't read them.
    # Copy into /etc/asterisk/keys/ where asterisk has access.
    cert = "/etc/asterisk/keys/opdesk_le_fullchain.pem"
    key  = "/etc/asterisk/keys/opdesk_le_privkey.pem"
    for src, dst, perms in ((le_cert, cert, "644"), (le_key, key, "600")):
        r = subprocess.run(["sudo", "cp", "-L", src, dst], capture_output=True)
        if r.returncode != 0:
            log.error(f"Failed to copy {src} → {dst}: {r.stderr.decode()}")
            return False
        subprocess.run(["sudo", "chown", "asterisk:asterisk", dst], capture_output=True)
        subprocess.run(["sudo", "chmod", perms, dst], capture_output=True)

    mode, config_file = _detect_tls_mode()
    log.info(f"SIP TLS mode detected: {mode} → {config_file}")

    # Pure-Asterisk: append a dedicated [opdesk-sip-tls] transport to the shared
    # pjsip custom file. method=tlsv1_2 is required on OpenSSL 3.x (the
    # default "sslv23" throws "no protocols available" because SSLv3 / TLS 1.0
    # / 1.1 are disabled).
    content_prefix = ""
    if os.path.isfile(config_file):
        r = subprocess.run(["sudo", "cat", config_file], capture_output=True)
        content_prefix = r.stdout.decode(errors="replace").rstrip("\n") + "\n"
    new_block = (
        f"\n{_TLS_MARKER_START}\n"
        f"[opdesk-sip-tls]\n"
        f"type=transport\n"
        f"protocol=tls\n"
        f"bind=0.0.0.0:5061\n"
        f"cert_file={cert}\n"
        f"priv_key_file={key}\n"
        f"method=tlsv1_2\n"
        f"verify_client=no\n"
        f"verify_server=no\n"
        f"{_TLS_MARKER_END}\n"
    )
    content = content_prefix + new_block

    if not _write_to_file(config_file, content):
        return False

    subprocess.run(["sudo", "ufw", "allow", "5061/tcp"], capture_output=True)
    subprocess.run(["sudo", "ufw", "allow", "5061/udp"], capture_output=True)
    subprocess.run(["sudo", "ufw", "reload"], capture_output=True)

    if not _reload_asterisk(mode):
        return False

    log.info(f"SIP TLS enabled on port 5061 ({mode}) with cert for {domain}")
    return True


def disable_sip_tls() -> bool:
    """Disable SIP TLS on port 5061."""
    mode, config_file = _detect_tls_mode()
    log.info(f"SIP TLS disable: mode={mode}, file={config_file}")

    _remove_opdesk_block(config_file)

    subprocess.run(["sudo", "ufw", "delete", "allow", "5061/tcp"], capture_output=True)
    subprocess.run(["sudo", "ufw", "delete", "allow", "5061/udp"], capture_output=True)
    subprocess.run(["sudo", "ufw", "reload"], capture_output=True)

    if not _reload_asterisk(mode):
        return False

    log.info("SIP TLS disabled on port 5061")
    return True


