"""Fail-closed release gate; receipts must come from the owner's trusted QA job."""
import json
from pathlib import Path
import re

from .errors import KhcomError
from .io import read_file
from .package import digest, relative

DIGEST = re.compile(r"[0-9a-f]{64}\Z")
GATES = ("coverage", "sora-campaign", "riku-campaign", "graphics-movies-credits",
         "windows-clean-install", "macos-arm64-native", "macos-intel-native",
         "performance", "package-provenance", "update-rollback-uninstall", "reproducibility",
         "apple-signature-notarization", "owner-review")
DELIVERABLES = ("windows-portable", "windows-installer", "macos-universal")


def verify(root: Path, manifest: dict, commit: str) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise KhcomError("release_identity", "Commit precisa ser SHA completo.")
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise KhcomError("release_schema", "Versão de manifesto inválida.")
    if manifest.get("commit") != commit or manifest.get("status") != "complete":
        raise KhcomError("release_incomplete", "Candidato incompleto ou de outro commit.")
    for field in ("source_sha256", "target_sha256", "patch_sha256", "inventory_sha256"):
        if not isinstance(manifest.get(field), str) or not DIGEST.fullmatch(manifest[field]):
            raise KhcomError("release_identity", "Identidade ausente.", field=field)
    artifacts = manifest.get("artifacts")
    gates = manifest.get("gates")
    if not isinstance(artifacts, dict) or set(artifacts) != set(DELIVERABLES):
        raise KhcomError("release_artifacts", "Faltam os três pacotes finais.")
    if not isinstance(gates, dict) or set(gates) != set(GATES):
        raise KhcomError("release_gates", "Faltam gates obrigatórios.")
    root = root.resolve()

    def verified_file(row, maximum):
        if not isinstance(row, dict) or not isinstance(row.get("sha256"), str) or not DIGEST.fullmatch(row["sha256"]):
            raise KhcomError("release_file", "Descritor de arquivo inválido.")
        path = root / relative(row.get("path"))
        if path.is_symlink() or not path.resolve().is_relative_to(root):
            raise KhcomError("release_path", "Arquivo fora do candidato.")
        data = read_file(path, maximum)
        if digest(data) != row["sha256"]:
            raise KhcomError("release_digest", "Digest do candidato diverge.", path=row["path"])
        return data

    artifact_hashes = {}
    for name, descriptor in artifacts.items():
        verified_file(descriptor, 256 * 1024 * 1024)
        artifact_hashes[name] = descriptor["sha256"]
    for name, descriptor in gates.items():
        receipt = json.loads(verified_file(descriptor, 1024 * 1024))
        if (not isinstance(receipt, dict) or receipt.get("schema_version") != 1
                or receipt.get("gate") != name or receipt.get("commit") != commit
                or receipt.get("result") != "pass" or receipt.get("artifact_sha256") != artifact_hashes
                or any(receipt.get(field) != manifest[field] for field in
                       ("source_sha256", "target_sha256", "patch_sha256", "inventory_sha256"))
                or not isinstance(receipt.get("evidence_sha256"), list) or not receipt["evidence_sha256"]
                or any(not isinstance(d, str) or not DIGEST.fullmatch(d) for d in receipt["evidence_sha256"])
                or not isinstance(receipt.get("reviewer"), str) or not receipt["reviewer"].strip()):
            raise KhcomError("release_receipt", "Gate ausente, falhou ou não corresponde aos artefatos.", gate=name)
        if name == "coverage" and (receipt.get("unknowns") != 0 or receipt.get("unreviewed") != 0
                                    or receipt.get("untranslated") != 0 or receipt.get("items_total", 0) < 18083):
            raise KhcomError("release_coverage", "Cobertura não está encerrada.")
        if name == "apple-signature-notarization" and (
                receipt.get("developer_id_verified") is not True
                or receipt.get("notarization_status") != "Accepted"
                or receipt.get("staple_verified") is not True or receipt.get("gatekeeper_clean_download") is not True):
            raise KhcomError("release_signature", "Faltam assinatura Apple, ticket ou Gatekeeper.")
        if name == "owner-review" and receipt.get("human_approval") is not True:
            raise KhcomError("release_owner", "A revisão humana não foi registrada.")
        if name in ("macos-arm64-native", "macos-intel-native") and receipt.get("execution") != "native-physical":
            raise KhcomError("release_native", "Rosetta/cruzamento não substitui a plataforma física.")
    return {"schema_version": 1, "release_gate_passed": True, "commit": commit,
            "artifacts": artifact_hashes, "gates": list(GATES),
            "trust_boundary": "Receipts supplied by the protected owner-controlled QA workflow; integrity alone is not independent review."}
