// Optional local verification only: never discovers or downloads a ROM.
#include "app/desktop_model.hpp"
#include "core/sha256.hpp"
#include "platform/atomic_file.hpp"
#include "platform/storage_lock.hpp"
#include <iostream>
using namespace khcom;
using namespace khcom::desktop;
namespace {
template <class T> T take(Result<T> r) {
  if (auto *e = std::get_if<Error>(&r))
    throw std::runtime_error(e->code + ": " + e->message);
  return std::move(std::get<T>(r));
}
void require(bool b, const char *m) {
  if (!b)
    throw std::runtime_error(m);
}
template <class T> void fails(Result<T> r, const char *code) {
  auto *e = std::get_if<Error>(&r);
  require(e && e->code == code, code);
}
} // namespace
int main(int argc, char **argv) try {
  if (argc != 5) {
    std::cerr
        << "Uso local: khcom-storage-integration ORIGINAL.gba|zip "
           "pacote-v1/manifest.json pacote-v2/manifest.json DIRETORIO-NOVO\n";
    return 2;
  }
  auto source = from_utf8(argv[1]), first = from_utf8(argv[2]),
       second = from_utf8(argv[3]), root = from_utf8(argv[4]);
  require(!fs::exists(root),
          "Use um diretório novo para preservar evidências anteriores.");
  auto lock = take(StorageLock::acquire(root));
  auto source_hash = sha256(take(read_file(source, 128 * 1024 * 1024)));
  auto rom = take(import_rom(source));
  require(!rom.bytes.empty(), "ZIP ambíguo não é adequado a este ensaio.");
  auto initial = take(install(root, rom.bytes, first));
  auto first_sha = sha256(initial.bytes);
  auto cache = root / "cache" / cache_key(initial.manifest) / "game.gba";
  auto mtime = fs::last_write_time(cache);
  auto active = take(read_file(root / "active.json", 65536));
  take(install(root, rom.bytes, first));
  require(fs::last_write_time(cache) == mtime,
          "cache validado foi regravado sem necessidade");
  require(take(read_file(root / "active.json", 65536)) == active,
          "repetição alterou histórico");
  std::atomic<bool> cancel = true;
  fails(install(root, rom.bytes, second, &cancel), "cancelled");
  require(take(read_file(root / "active.json", 65536)) == active,
          "cancelamento antes do trabalho alterou ativação");
  for (auto stage :
       {InstallPhase::patch, InstallPhase::cache, InstallPhase::activation}) {
    cancel = false;
    fails(install(root, rom.bytes, second, &cancel,
                  [&](InstallPhase p) {
                    if (p == stage)
                      cancel = true;
                  }),
          "cancelled");
    require(take(read_file(root / "active.json", 65536)) == active,
            "cancelamento de etapa alterou identidade corrente/anterior");
  }
  cancel = false;
  auto updated =
      take(install(root, rom.bytes, second, &cancel, [&](InstallPhase p) {
        if (p == InstallPhase::complete)
          cancel = true;
      }));
  auto second_sha = sha256(updated.bytes);
  require(second_sha != first_sha, "dois pacotes distintos são necessários");
  require(sha256(take(load_active(root, true)).bytes) == first_sha,
          "histórico não retém V1");
  auto second_active = take(read_file(root / "active.json", 65536));
  take(install(root, rom.bytes, second));
  require(take(read_file(root / "active.json", 65536)) == second_active,
          "repetição perdeu rollback");
  take(rollback(root));
  require(sha256(take(load_active(root)).bytes) == first_sha,
          "rollback não ativou V1");
  require(sha256(take(load_active(root, true)).bytes) == second_sha,
          "rollback perdeu V2");
  take(rollback(root));
  auto second_cache = root / "cache" / cache_key(updated.manifest) / "game.gba";
  auto damaged = updated.bytes;
  damaged[12345] ^= 1;
  take(atomic_write(second_cache, damaged, false));
  fails(load_active(root), "cache_corrupt");
  auto repaired = take(install(root, rom.bytes, second));
  require(sha256(repaired.bytes) == second_sha, "cache não foi reconstruído");
  require(sha256(take(load_active(root, true)).bytes) == first_sha,
          "reparo alterou rollback");
  auto recovery = take(recover_owned_temporaries(root));
  require(recovery.retained.empty(), "temporários pendentes inesperados");
  require(source_hash == sha256(take(read_file(source, 128 * 1024 * 1024))),
          "origem foi alterada");
  Json report = {
      {"schema_version", 1},
      {"source_archive_sha256", source_hash},
      {"original_rom_sha256", sha256(rom.bytes)},
      {"first_target_sha256", first_sha},
      {"second_target_sha256", second_sha},
      {"checks",
       {"validated_cache_reuse", "cancellation_before_work",
        "cancellation_at_patch_cache_activation",
        "late_cancellation_after_commit_reports_success",
        "update_atomic_history", "repeat_preserves_history",
        "rollback_both_directions", "tampered_cache_rejected", "cache_rebuilt",
        "source_preserved", "owned_temporaries_clean"}},
      {"gameplay_asserted", false}};
  auto text = report.dump(2);
  take(atomic_write(
      root / "integration-report.json",
      {reinterpret_cast<const std::uint8_t *>(text.data()), text.size()},
      false));
  std::cout
      << "Integração local de instalação/cache/rollback/cancelamento passou.\n";
  return 0;
} catch (const std::exception &e) {
  std::cerr << e.what() << '\n';
  return 1;
}
