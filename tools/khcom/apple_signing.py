"""Developer ID/notarization on a new copy; input provenance is never rewritten."""
from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import copy
import json
import os
from pathlib import Path
import plistlib
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid

from .errors import KhcomError
from .io import read_file, write_json_new, write_new
from .package import MAX_FILE, MAX_FILES, MAX_TOTAL, architecture, audit, digest, relative

MANIFEST_LIMIT = 4 * 1024 * 1024
OLD_NOTICE = "A assinatura é somente ad-hoc;\nnão há Developer ID nem notarização."
BUNDLE_SUFFIXES = {".app", ".xpc", ".appex", ".bundle", ".framework"}
MACHO_MAGIC = {b"\xcf\xfa\xed\xfe", b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"}


@dataclass(frozen=True)
class Settings:
    identity: str = ""
    profile: str = ""
    keychain: str = ""

    def validate(self) -> None:
        if self.identity and not re.fullmatch(r"[0-9A-Fa-f]{40}", self.identity):
            raise KhcomError("apple_identity", "Informe o SHA-1 exato da identidade Developer ID Application.")
        if any("\x00" in value or "\n" in value for value in (self.profile, self.keychain)):
            raise KhcomError("apple_auth_reference", "Referência de Keychain inválida.")

    def auth(self) -> list[str]:
        return ["--keychain-profile", self.profile] + (["--keychain", self.keychain] if self.keychain else [])


@dataclass(frozen=True)
class ToolResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


def run_tool(argv: list[str], stage: str, timeout: int = 60) -> ToolResult:
    """Bounded output; no shell, passwords, environment snapshot or unowned PID."""
    with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
        process = subprocess.Popen(argv, stdin=subprocess.DEVNULL, stdout=stdout, stderr=stderr,
                                   start_new_session=True)
        try:
            process.wait(timeout=timeout)
        except BaseException:
            # A live child keeps its process group identity; do not rediscover it by PID/name.
            try:
                if process.poll() is None:
                    os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass  # The owned child/group exited between poll and signal.
            finally:
                process.wait()
            raise
        outputs = []
        for stream in (stdout, stderr):
            stream.seek(0)
            data = stream.read(1024 * 1024 + 1)
            if len(data) > 1024 * 1024:
                raise KhcomError("apple_output_limit", "Ferramenta excedeu o limite de diagnóstico.", stage=stage)
            outputs.append(data.decode("utf-8", "replace"))
        return ToolResult(process.returncode, *outputs)


def checked(runner, argv: list[str], stage: str) -> ToolResult:
    result = runner(argv, stage)
    if result.returncode:
        # Tool output may contain authentication diagnostics. Retain only digests/status;
        # never echo credentials or an unfiltered CalledProcessError command line.
        raise KhcomError("apple_tool_failed", "Ferramenta Apple recusou a etapa.", stage=stage,
                         exit_code=result.returncode, stdout_sha256=digest(result.stdout.encode()),
                         stderr_sha256=digest(result.stderr.encode()))
    return result


@contextmanager
def operation_lock(out: Path):
    """OS lifetime lock: process exit releases it without guessing PID ownership."""
    if out.is_symlink() or not out.is_dir():
        raise KhcomError("apple_output", "Diretório de operação inexistente/inválido.")
    lock = out / ".operation.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            raise KhcomError("apple_output", "Lock não é arquivo regular.")
        try:
            if os.name == "nt":
                import msvcrt
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"0")
                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise KhcomError("apple_busy", "Outra execução possui este diretório; não iniciar em paralelo.") from exc
        yield
    finally:
        os.close(fd)


def load_json(path: Path) -> dict:
    try:
        value = json.loads(read_file(path, MANIFEST_LIMIT))
    except (ValueError, UnicodeError) as exc:
        raise KhcomError("apple_json", "JSON de assinatura inválido.", path=str(path)) from exc
    if not isinstance(value, dict):
        raise KhcomError("apple_json", "Documento deve ser um objeto.", path=str(path))
    return value


def canonical(value: dict) -> str:
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":")).encode())


def plan(payload: Path) -> dict:
    payload = payload.absolute()
    if payload.is_symlink() or not payload.is_dir():
        raise KhcomError("apple_payload", "Escolha um diretório de payload regular.")
    raw = read_file(payload / "package-manifest.json", MANIFEST_LIMIT)
    manifest = load_json(payload / "package-manifest.json")
    audit(payload, manifest)
    if manifest.get("platform") != "macos" or manifest.get("status") != "experimental":
        raise KhcomError("apple_package", "Este fluxo aceita somente pacote macOS experimental auditado.")
    for field in ("sources_sha256", "binary_input_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", manifest.get(field, "")):
            raise KhcomError("apple_provenance", "Digest de proveniência ausente/inválido.", field=field)
    rows = {row["path"]: row for row in manifest["files"]}
    sources = [row for row in rows.values() if row["role"] == "sources"]
    if len(sources) != 1 or sources[0]["sha256"] != manifest["sources_sha256"]:
        raise KhcomError("apple_provenance", "Hash de fontes não corresponde ao arquivo auditado.")
    apps = {Path(name).parts[0] for name, row in rows.items() if row["role"] == "executable"}
    if len(apps) != 1 or not next(iter(apps)).endswith(".app"):
        raise KhcomError("apple_bundle", "O pacote deve conter um único .app externo.")
    app = next(iter(apps))
    bundles, code = {app}, []
    for name, row in rows.items():
        data = read_file(payload / name, MAX_FILE)
        if data[:4] in MACHO_MAGIC:
            if not name.startswith(app + "/") or row["role"] != "executable":
                raise KhcomError("apple_code_inventory", "Mach-O fora do inventário executável do app.", path=name)
            architecture(data)
            code.append(name)
            for parent in Path(name).parents:
                if parent.suffix in BUNDLE_SUFFIXES:
                    if parent.suffix == ".framework":
                        raise KhcomError("apple_bundle", "Frameworks versionados requerem contrato específico; não usar --deep para repará-los.")
                    bundles.add(parent.as_posix())
    if not code:
        raise KhcomError("apple_bundle", "Nenhum Mach-O inventariado.")
    for bundle in bundles:
        info = f"{bundle}/Contents/Info.plist"
        if info not in rows:
            raise KhcomError("apple_bundle", "Bundle sem Info.plist inventariado.", path=bundle)
        try:
            plist = plistlib.loads(read_file(payload / info, 65536))
        except Exception as exc:
            raise KhcomError("apple_bundle", "Info.plist inválido.", path=info) from exc
        executable = plist.get("CFBundleExecutable")
        if not isinstance(executable, str) or "/" in executable or not executable or f"{bundle}/Contents/MacOS/{executable}" not in code:
            raise KhcomError("apple_bundle", "Executável do bundle não consta do inventário.", path=bundle)
    instructions = rows.get("LEIA-ME.txt", {})
    if instructions.get("role") != "instructions" or read_file(payload / "LEIA-ME.txt", MAX_FILE).decode("utf-8").count(OLD_NOTICE) != 1:
        raise KhcomError("apple_instructions", "Aviso ad-hoc esperado ausente/ambíguo; atualizar contrato do empacotador antes de assinar.")
    targets = sorted(set(code) | bundles, key=lambda name: (-len(Path(name).parts), name))
    return {"schema_version": 1, "kind": "apple-signing-plan-v1", "input_payload": str(payload), "app": app,
            "input_manifest_sha256": digest(raw), "input_manifest_canonical_sha256": canonical(manifest),
            "sources_sha256": manifest["sources_sha256"], "binary_input_sha256": manifest["binary_input_sha256"],
            "sign_targets": targets, "code_files": sorted(code), "bundles": sorted(bundles),
            "input_files": copy.deepcopy(manifest["files"]), "release_approved": False,
            "sign_options": ["--force", "--options", "runtime", "--timestamp", "empty-entitlements"],
            "verification": ["codesign --verify --deep --strict", "Developer ID/Team/runtime/timestamp per slice",
                             "notarytool Accepted", "stapler validate", "spctl local", "re-extract and verify"],
            "submission_policy": "one submit; persist UUID; explicit resume; never retry unknown upload"}


def readiness(settings: Settings, runner=run_tool, host: str | None = None) -> dict:
    settings.validate()
    report = {"host_macos": (host or sys.platform) == "darwin", "tools": {}, "developer_id_available": False,
              "identity_sha1": settings.identity.upper() or None, "profile_configured": bool(settings.profile),
              "profile_credentials_verified": False, "keychain_configured": bool(settings.keychain),
              "ready_to_attempt": False, "reasons": []}
    if not report["host_macos"]:
        report["reasons"].append("Ferramentas Apple exigem macOS.")
        return report
    for name in ("codesign", "security", "ditto", "spctl", "notarytool", "stapler"):
        found = runner(["/usr/bin/xcrun", "--find", name], "find-" + name)
        candidate = found.stdout.strip()
        report["tools"][name] = candidate if found.returncode == 0 and candidate.startswith("/") and "\n" not in candidate else None
    identities = runner(["/usr/bin/security", "find-identity", "-v", "-p", "codesigning"] +
                        ([settings.keychain] if settings.keychain else []), "find-identity")
    available = re.findall(r'\b([0-9A-Fa-f]{40})\s+"(Developer ID Application:[^"\r\n]+)"', identities.stdout) if identities.returncode == 0 else []
    matched = [(sha, name) for sha, name in available if sha.upper() == settings.identity.upper()]
    report["developer_id_available"] = len(matched) == 1
    if matched:
        team = re.search(r"\(([A-Z0-9]{10})\)$", matched[0][1])
        report["team_id"] = team.group(1) if team else None
    if not all(report["tools"].values()):
        report["reasons"].append("Uma ou mais ferramentas Apple estão indisponíveis.")
    if not report["developer_id_available"] or not report.get("team_id"):
        report["reasons"].append("Identidade Developer ID Application exata não está disponível.")
    if not settings.profile:
        report["reasons"].append("Informe um profile notarytool já provisionado no Keychain.")
    report["ready_to_attempt"] = not report["reasons"]
    return report


def signature_paths(p: dict) -> set[str]:
    return {f"{bundle}/Contents/_CodeSignature/CodeResources" for bundle in p["bundles"]} | {p["app"] + "/Contents/CodeResources"}


def inventory_after(payload: Path, p: dict, *, signed: list[dict] | None = None,
                    instructions: bytes | None = None) -> tuple[list[dict], list[dict]]:
    """Only code signatures/ticket and the explicit notice rewrite may differ."""
    before = {row["path"]: row for row in (signed if signed is not None else p["input_files"])}
    current, changes, total = {}, [], 0
    for item in sorted(payload.rglob("*")):
        if item.is_symlink():
            raise KhcomError("apple_mutation", "Link inesperado após assinatura.", path=str(item))
        if not item.is_file() or item == payload / "package-manifest.json":
            continue
        name = item.relative_to(payload).as_posix()
        relative(name)
        data = read_file(item, min(MAX_FILE, MAX_TOTAL - total))
        total += len(data)
        if len(current) >= MAX_FILES:
            raise KhcomError("apple_mutation", "Inventário excedeu limite.")
        old = before.get(name)
        if old is None and name not in signature_paths(p):
            raise KhcomError("apple_mutation", "Arquivo novo fora das regiões de assinatura.", path=name)
        row = {"path": name, "role": old["role"] if old else "signature", "size": len(data), "sha256": digest(data)}
        if old != row:
            allowed = name in signature_paths(p) or (signed is None and name in p["code_files"])
            if name == "LEIA-ME.txt" and instructions is not None and data == instructions:
                allowed = True
            if not allowed:
                raise KhcomError("apple_mutation", "Assinatura alterou arquivo fora do contrato.", path=name)
            changes.append({"path": name, "before": old, "after": row})
        current[name] = row
    if set(before) - set(current):
        raise KhcomError("apple_mutation", "Arquivo de entrada desapareceu.", missing=sorted(set(before) - set(current)))
    return [current[key] for key in sorted(current)], changes


def signature_check(payload: Path, p: dict, tools: dict, team_id: str, runner) -> None:
    checked(runner, [tools["codesign"], "--verify", "--deep", "--strict", "--verbose=2", str(payload / p["app"])], "verify-signature")
    for name in p["code_files"]:
        for arch in architecture(read_file(payload / name, MAX_FILE)):
            result = checked(runner, [tools["codesign"], "--display", "--verbose=4", "--arch", arch, str(payload / name)], "display-signature")
            text = result.stdout + result.stderr
            flags = re.search(r"^CodeDirectory[^\r\n]*\bflags=(0x[0-9a-fA-F]+)", text, re.M)
            timestamp = re.search(r"^Timestamp=([^\r\n]+)$", text, re.M)
            if (not re.search(r"^Authority=Developer ID Application:[^\r\n]+$", text, re.M)
                    or not re.search(r"^TeamIdentifier=" + re.escape(team_id) + r"$", text, re.M)
                    or not flags or not (int(flags.group(1), 16) & 0x10000)
                    or not timestamp or timestamp.group(1).strip().lower() in {"none", "not set", ""}):
                raise KhcomError("apple_signature", "Assinatura não comprova Developer ID, Team, runtime e timestamp em toda slice.", path=name, architecture=arch)
            entitlements = checked(runner, [tools["codesign"], "--display", "--entitlements", ":-", "--arch", arch, str(payload / name)], "display-entitlements")
            if entitlements.stdout.strip():
                try:
                    value = plistlib.loads(entitlements.stdout.encode())
                except Exception as exc:
                    raise KhcomError("apple_entitlements", "Entitlements não puderam ser verificados.", path=name) from exc
                if value:
                    raise KhcomError("apple_entitlements", "Este core interpretado não solicita exceções ao hardened runtime.", path=name)


def receipt(result: ToolResult, *, require_status: bool = False) -> dict:
    try:
        value = json.loads(result.stdout)
        if not isinstance(value, dict) or not isinstance(value.get("id"), str):
            raise ValueError("receipt shape")
        identifier = str(uuid.UUID(value["id"]))
    except (ValueError, KeyError, TypeError) as exc:
        raise KhcomError("apple_submission_unknown", "Não há receipt válido; não reenviar automaticamente. Consulte o histórico Apple manualmente.") from exc
    status = value.get("status", None if require_status else "In Progress")
    if not isinstance(status, str) or status not in {"In Progress", "Accepted", "Invalid", "Rejected"}:
        raise KhcomError("apple_status", "Estado de notarização não reconhecido.", submission_id=identifier)
    return {"id": identifier, "status": status}


def execute(payload: Path, out: Path, settings: Settings, runner=run_tool) -> dict:
    p = plan(payload)
    ready = readiness(settings, runner)
    if not ready["ready_to_attempt"]:
        raise KhcomError("apple_not_ready", "Assinatura não está pronta para tentativa.", readiness=ready)
    out = out.absolute()
    source = payload.absolute()
    if out.exists() or out.is_symlink() or source == out or source in out.parents or out in source.parents:
        raise KhcomError("output_exists", "Use pasta nova fora da entrada.", path=str(out))
    out.mkdir(parents=True)
    with operation_lock(out):
        return _execute_copy(source, out, settings, p, ready, runner)


def _execute_copy(source: Path, out: Path, settings: Settings, p: dict, ready: dict, runner) -> dict:
    write_json_new(out / "provenance/plan.json", p)
    raw = read_file(source / "package-manifest.json", MANIFEST_LIMIT)
    if digest(raw) != p["input_manifest_sha256"]:
        raise KhcomError("apple_input_changed", "Manifesto de entrada mudou após planejamento.")
    write_new(out / "provenance/input-package-manifest.json", raw)
    destination = out / "payload"
    for row in p["input_files"]:
        data = read_file(source / row["path"], MAX_FILE)
        if len(data) != row["size"] or digest(data) != row["sha256"]:
            raise KhcomError("apple_input_changed", "Entrada mudou durante cópia.", path=row["path"])
        target = destination / row["path"]
        write_new(target, data)
        target.chmod(0o755 if row["role"] == "executable" else 0o644)
    tools = ready["tools"]
    # Strip ad-hoc entitlements rather than preserving unknown existing grants.
    empty = out / "provenance/empty-entitlements.plist"
    write_new(empty, plistlib.dumps({}))
    for target in p["sign_targets"]:
        argv = [tools["codesign"], "--force", "--sign", settings.identity, "--options", "runtime", "--timestamp",
                "--entitlements", str(empty)] + (["--keychain", settings.keychain] if settings.keychain else [])
        checked(runner, argv + [str(destination / target)], "sign-inside-out")
    signature_check(destination, p, tools, ready["team_id"], runner)
    signed, changes = inventory_after(destination, p)
    write_json_new(out / "provenance/signed-inventory.json", {"files": signed, "changes": changes,
                   "identity_sha1": settings.identity.upper(), "team_id": ready["team_id"]})
    upload = out / "submission.zip"
    checked(runner, [tools["ditto"], "-c", "-k", "--keepParent", str(destination / p["app"]), str(upload)], "notary-archive")
    write_json_new(out / "provenance/submit-attempt.json", {"archive_sha256": digest(read_file(upload, MAX_FILE)),
                   "signed_inventory_sha256": digest(read_file(out / "provenance/signed-inventory.json", MANIFEST_LIMIT)),
                   "plan_sha256": digest(read_file(out / "provenance/plan.json", MANIFEST_LIMIT)),
                   "identity_sha1": settings.identity.upper(), "submission_id": None,
                   "unknown_outcome_requires_manual_reconciliation": True})
    submitted = runner([tools["notarytool"], "submit", str(upload), *settings.auth(), "--output-format", "json", "--no-wait"], "notary-submit")
    accepted_receipt = receipt(submitted)
    write_json_new(out / "provenance/submission.json", accepted_receipt)
    if submitted.returncode:
        raise KhcomError("apple_submission_failed", "Apple devolveu receipt mas recusou a chamada; preserve o ID e consulte --resume.", **accepted_receipt)
    # Do not poll or resubmit. A later explicit --resume checks the same ID.
    return {"ok": True, "state": "submitted", "submission": accepted_receipt, "out": str(out),
            "release_approved": False, "next": "Execute --resume neste diretório para consultar e finalizar."}


def resume(out: Path, settings: Settings, runner=run_tool) -> dict:
    out = out.absolute()
    with operation_lock(out):
        return _resume_locked(out, settings, runner)


def _resume_locked(out: Path, settings: Settings, runner) -> dict:
    if (out / "result.json").exists():
        raise KhcomError("apple_finalized", "Resultado já finalizado; não será alterado.")
    p = load_json(out / "provenance/plan.json")
    attempt = load_json(out / "provenance/submit-attempt.json")
    for path, key in (("provenance/plan.json", "plan_sha256"),
                      ("provenance/signed-inventory.json", "signed_inventory_sha256"),
                      ("submission.zip", "archive_sha256")):
        if digest(read_file(out / path, MAX_FILE if path.endswith(".zip") else MANIFEST_LIMIT)) != attempt.get(key):
            raise KhcomError("apple_provenance", "Artefato da submissão mudou; não continuar.", path=path)
    original = load_json(out / "provenance/input-package-manifest.json")
    if p.get("kind") != "apple-signing-plan-v1" or canonical(original) != p["input_manifest_canonical_sha256"] or digest(read_file(out / "provenance/input-package-manifest.json", MANIFEST_LIMIT)) != p["input_manifest_sha256"]:
        raise KhcomError("apple_provenance", "Plano e manifesto de origem divergem.")
    if plan(Path(p["input_payload"])) != p:
        raise KhcomError("apple_input_changed", "Entrada original mudou; proveniência não será reescrita.")
    ready = readiness(settings, runner)
    if not ready["ready_to_attempt"]:
        raise KhcomError("apple_not_ready", "Prontidão insuficiente para retomar.", readiness=ready)
    signed = load_json(out / "provenance/signed-inventory.json")
    if signed["identity_sha1"] != settings.identity.upper() or signed["team_id"] != ready["team_id"]:
        raise KhcomError("apple_identity", "Retomada exige a mesma identidade de assinatura.")
    submission_path = out / "provenance/submission.json"
    if not submission_path.exists():
        raise KhcomError("apple_submission_unknown", "Tentativa sem ID persistido; não reenviar. Consulte o histórico Apple manualmente.")
    submission = receipt(ToolResult(0, json.dumps(load_json(submission_path))))
    tools, destination = ready["tools"], out / "payload"
    response = checked(runner, [tools["notarytool"], "info", submission["id"], *settings.auth(), "--output-format", "json"], "notary-info")
    status = receipt(response, require_status=True)
    if status["id"] != submission["id"]:
        raise KhcomError("apple_submission", "Resposta Apple pertence a outra submissão.")
    write_json_new(out / f"provenance/status-{uuid.uuid4()}.json", status)
    if status["status"] == "In Progress":
        return {"ok": True, "state": "pending", "submission": status, "release_approved": False}
    if status["status"] != "Accepted":
        raise KhcomError("apple_notarization_rejected", "Apple não aceitou o pacote; não haverá stapling/publicação.", **status)
    notice = read_file(Path(p["input_payload"]) / "LEIA-ME.txt", MAX_FILE).decode("utf-8").replace(
        OLD_NOTICE, "Este .app tem assinatura Developer ID e ticket de notarização anexado.\nA aprovação Apple não atesta tradução completa nem QA de plataforma.").encode()
    inventory_after(destination, p, signed=signed["files"], instructions=notice)
    signature_check(destination, p, tools, ready["team_id"], runner)
    app = destination / p["app"]
    checked(runner, [tools["stapler"], "staple", str(app)], "staple")
    checked(runner, [tools["stapler"], "validate", str(app)], "validate-ticket")
    signature_check(destination, p, tools, ready["team_id"], runner)
    checked(runner, [tools["spctl"], "--assess", "--type", "execute", "--verbose=2", str(app)], "gatekeeper-local")
    # Only this explicit outside-bundle notice is updated after all Apple checks.
    (destination / "LEIA-ME.txt").write_bytes(notice)
    files, changes = inventory_after(destination, p, instructions=notice)
    manifest = copy.deepcopy(original)
    manifest.update(files=files, signature="developer-id-notarized-stapled", release_approved=False,
                    apple_signing={"schema_version": 1, "input_manifest_sha256": p["input_manifest_sha256"],
                     "input_manifest_canonical_sha256": p["input_manifest_canonical_sha256"],
                     "identity_sha1": settings.identity.upper(), "team_id": ready["team_id"],
                     "submission_id": status["id"], "status": "Accepted", "stapled": True,
                     "local_signature_verified": True, "local_gatekeeper_assessed": True,
                     "clean_download_gatekeeper_verified": False, "changes": changes})
    if manifest["sources_sha256"] != p["sources_sha256"] or manifest["binary_input_sha256"] != p["binary_input_sha256"]:
        raise KhcomError("apple_provenance", "Proveniência de build alterada.")
    report = audit(destination, manifest)
    manifest_file = destination / "package-manifest.json"
    if manifest_file.exists():
        if load_json(manifest_file) != manifest:
            raise KhcomError("apple_finalization", "Manifesto parcial diverge; preservar para inspeção.")
    else:
        write_json_new(manifest_file, manifest)
    # A new attempt directory preserves any previous failed transport artifact.
    transport = out / ("transport-" + str(uuid.uuid4()))
    transport.mkdir()
    archive = transport / "KHCoM-PTBR-macos-signed-experimental.zip"
    checked(runner, [tools["ditto"], "-c", "-k", "--sequesterRsrc", "--keepParent", str(destination), str(archive)], "final-archive")
    extracted = transport / "verified"
    checked(runner, [tools["ditto"], "-x", "-k", str(archive), str(extracted)], "reextract-archive")
    unpacked = extracted / "payload"
    audit(unpacked, manifest)
    signature_check(unpacked, p, tools, ready["team_id"], runner)
    checked(runner, [tools["stapler"], "validate", str(unpacked / p["app"])], "validate-transport-ticket")
    if plan(Path(p["input_payload"])) != p:
        raise KhcomError("apple_input_changed", "Entrada original mudou durante a operação.")
    result = {"ok": True, "state": "notarized-and-stapled", "archive": str(archive),
              "archive_sha256": digest(read_file(archive, MAX_FILE)), "audit": report,
              "output_manifest_sha256": digest(read_file(manifest_file, MANIFEST_LIMIT)),
              "submission_id": status["id"], "release_approved": False,
              "clean_download_gatekeeper_verified": False}
    write_json_new(out / "result.json", result)
    return result
