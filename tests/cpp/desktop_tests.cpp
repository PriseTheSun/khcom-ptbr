#include "app/desktop_model.hpp"
#include "platform/atomic_file.hpp"
#include "platform/storage_lock.hpp"
#include <chrono>
#include <iostream>
#include <miniz.h>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <signal.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>
#endif
using namespace khcom;
using namespace khcom::desktop;
namespace {
void require(bool v, const char *m) {
  if (!v)
    throw std::runtime_error(m);
}
template <class T> T take(Result<T> r) {
  if (auto *e = std::get_if<Error>(&r))
    throw std::runtime_error(e->code + ":" + e->message);
  return std::move(std::get<T>(r));
}
template <class T> void error(Result<T> r, const char *code) {
  auto *e = std::get_if<Error>(&r);
  require(e && e->code == code, code);
}
Bytes b(std::string s) { return {s.begin(), s.end()}; }
void word(Bytes &v, std::uint32_t n) {
  for (int i = 0; i < 4; ++i)
    v.push_back(n >> (i * 8));
}
Bytes footer(Bytes body, const Bytes &s, const Bytes &t) {
  word(body, mz_crc32(0, s.data(), s.size()));
  word(body, mz_crc32(0, t.data(), t.size()));
  word(body, mz_crc32(0, body.data(), body.size()));
  return body;
}
void put(const fs::path &p, Bytes v) { take(atomic_write(p, v, false)); }
Bytes zip(const std::vector<std::pair<std::string, Bytes>> &entries) {
  mz_zip_archive z{};
  require(mz_zip_writer_init_heap(&z, 0, 0), "ZIP writer");
  for (auto &[name, data] : entries)
    require(mz_zip_writer_add_mem(&z, name.c_str(), data.data(), data.size(),
                                  MZ_BEST_SPEED),
            "ZIP add");
  void *mem = nullptr;
  size_t size = 0;
  require(mz_zip_writer_finalize_heap_archive(&z, &mem, &size), "ZIP finalize");
  Bytes result(static_cast<std::uint8_t *>(mem),
               static_cast<std::uint8_t *>(mem) + size);
  mz_free(mem);
  mz_zip_writer_end(&z);
  return result;
}
void interrupted_fixture(const fs::path &directory) {
  fs::create_directories(directory);
  auto temp = directory / ".khcom-write-fixture",
       anchor = directory / ".khcom-anchor-fixture";
  put(temp, b("incomplete payload"));
  fs::create_hard_link(temp, anchor);
  std::uint64_t device = 0, index = 0;
#ifdef _WIN32
  auto h = CreateFileW(temp.c_str(), 0,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  require(h != INVALID_HANDLE_VALUE, "fixture file handle");
  BY_HANDLE_FILE_INFORMATION info{};
  require(GetFileInformationByHandle(h, &info), "fixture identity");
  CloseHandle(h);
  device = info.dwVolumeSerialNumber;
  index = (std::uint64_t(info.nFileIndexHigh) << 32) | info.nFileIndexLow;
#else
  struct stat st{};
  require(::stat(temp.c_str(), &st) == 0, "fixture identity");
  device = st.st_dev;
  index = st.st_ino;
#endif
  Json j = {{"schema", "khcom-owned-write-v1"},
            {"temporary", ".khcom-write-fixture"},
            {"anchor", ".khcom-anchor-fixture"},
            {"device", device},
            {"index", index}};
  put(directory / ".khcom-owned-fixture.json", b(j.dump()));
}
} // namespace
int main() {
  fs::path root =
      fs::temp_directory_path() /
      ("khcom-desktop-test-" +
       std::to_string(
           std::chrono::steady_clock::now().time_since_epoch().count()));
  try {
    fs::create_directories(root);
    auto lock = take(StorageLock::acquire(root));
    error(StorageLock::acquire(root), "storage_busy");
    auto source = b("ABCDEabcde"), target = b("ABxyabcabcabcAB");
    auto body = b("BPS1");
    for (auto v : {0x8a, 0x8f, 0x80, 0x84, 0x85, 'x' + 0, 'y' + 0, 0x8a, 0x8a,
                   0x97, 0x88, 0x86, 0x91})
      body.push_back(v);
    auto patch = footer(body, source, target);
    require(take(apply_bps(source, patch)) == target,
            "independent BPS all four actions and signed offsets");
    patch.back() ^= 1;
    error(apply_bps(source, patch), "bps_crc");
    error(apply_bps({}, {}), "bps_header");
    auto invalid = b("BPS1");
    for (int v : {0x81, 0x81, 0x80, 0x82, 0x83})
      invalid.push_back(v);
    error(apply_bps(b("a"), footer(invalid, b("a"), b("x"))), "bps_relative");
    auto badrom = root / "renomeado.gba";
    put(badrom, b("not a ROM"));
    error(import_rom(badrom), "rom_identity");
    auto z = root / from_utf8("coleção.zip");
    put(z, zip({{"a.gba", Bytes(128)}, {"b.gba", Bytes(128)}}));
    auto choices = take(import_rom(z));
    require(choices.bytes.empty() && choices.choices.size() == 2,
            "ZIP requires explicit member choice");
    error(import_rom(z, 0), "rom_size");
    error(import_rom(z, 99), "zip_selection");
    put(z, zip({{"../a.gba", Bytes(128)}}));
    error(import_rom(z), "zip_path");
    put(z, zip({{"C:evil.gba", Bytes(128)}}));
    error(import_rom(z), "zip_path");
    put(z, b("PKtruncated"));
    error(import_rom(z), "zip_invalid");
    Config c;
    c.scale = 6;
    c.filter = 1;
    c.volume = 23;
    c.fit = false;
    c.keyboard[0] = 6;
    take(save_config(root / "config.json", c));
    auto lc = take(load_config(root / "config.json"));
    require(lc.config.scale == 6 && lc.config.volume == 23 &&
                lc.config.keyboard[0] == 6,
            "config persistence");
    auto previous = take(read_file(root / "config.json", 65536));
    put(root / "config.json", b("{broken"));
    lc = take(load_config(root / "config.json"));
    require(!lc.warning.empty() && lc.config.scale == 3,
            "malformed config preserved with defaults");
    bool found = false;
    for (auto &e : fs::directory_iterator(root))
      if (e.path().filename().string().find(".invalid-") != std::string::npos)
        found = true;
    require(found, "invalid config backup exists");
    auto j = Json::parse(previous);
    j["unknown_option"] = true;
    put(root / "config.json", b(j.dump()));
    require(!take(load_config(root / "config.json")).warning.empty(),
            "unknown configuration rejected");
    Json manifest = {{"save_compatibility", "B8CE-sram-v1"},
                     {"target_sha256", std::string(64, 'a')}};
    Bytes save(32768, 0x5a);
    take(store_save(root, manifest, 0, save));
    require(take(load_save(root, manifest, 0)) == save,
            "cartridge envelope reload");
    require(take(load_save(root, manifest, 1)).empty(), "profile separation");
    save[45] = 0xab;
    take(store_save(root, manifest, 0, save));
    auto saved = root / "saves" / "B8CE" / "B8CE-sram-v1" / "perfil-1.khcs";
    require(fs::exists(saved.string() + ".bak"), "save backup preserved");
    auto exported = root / from_utf8("ação.khcs");
    take(export_save(exported, manifest, save));
    require(take(import_save(exported, manifest)) == save,
            "UTF8 save path and roundtrip");
    auto incompatible = manifest;
    incompatible["save_compatibility"] = "different-v2";
    error(import_save(exported, incompatible), "save_identity");
    auto raw = take(read_file(exported, 65536));
    auto envelope = Json::from_cbor(raw);
    envelope["sha256"] = std::string(64, '0');
    put(exported, Json::to_cbor(envelope));
    error(import_save(exported, manifest), "save_integrity");
    auto corrupt = b("corrupt preserved save");
    put(saved, corrupt);
    take(restore_save_backup(root, manifest, 0));
    auto restored = take(load_save(root, manifest, 0));
    require(restored[45] == 0x5a,
            "backup recovery uses validated previous generation");
    bool preserved_corrupt = false;
    for (auto &e : fs::directory_iterator(saved.parent_path()))
      if (e.path().filename().string().find(".before-restore-") !=
          std::string::npos)
        preserved_corrupt = take(read_file(e.path(), 65536)) == corrupt;
    require(preserved_corrupt,
            "corrupt current save preserved during recovery");
    Json cache_manifest = {{"source_sha256", std::string(64, 'a')},
                           {"patch_sha256", std::string(64, 'b')},
                           {"target_sha256", std::string(64, 'c')}};
    auto first_key = cache_key(cache_manifest);
    cache_manifest["patch_sha256"] = std::string(64, 'd');
    require(cache_key(cache_manifest) != first_key,
            "cache binds patch identity even for identical target");
    auto protected_path = root / "destination";
    fs::create_directory(protected_path);
    auto result = atomic_write(protected_path, b("new"));
    require(std::holds_alternative<Error>(result) &&
                fs::is_directory(protected_path),
            "failed activation preserves destination");
    auto recovery = take(recover_owned_temporaries(root));
    require(recovery.retained.empty(),
            "failed rename cleaned only its owned temporary");
    auto unknown = root / ".khcom-owned-unknown.json";
    put(unknown, b("{broken"));
    recovery = take(recover_owned_temporaries(root));
    require(recovery.retained.size() == 1 && fs::exists(unknown),
            "unknown ownership must remain preserved");
    fs::remove(unknown);
    auto interrupted = root / "interrupted";
    interrupted_fixture(interrupted);
    recovery = take(recover_owned_temporaries(interrupted));
    require(recovery.recovered == 1 && recovery.retained.empty() &&
                fs::is_empty(interrupted),
            "partial owned bytes recover without requiring valid content");
    interrupted_fixture(interrupted);
    fs::remove(interrupted / ".khcom-write-fixture");
    put(interrupted / ".khcom-write-fixture", b("foreign replacement"));
    recovery = take(recover_owned_temporaries(interrupted));
    require(recovery.retained.size() == 1 &&
                take(read_file(interrupted / ".khcom-write-fixture", 65536)) ==
                    b("foreign replacement"),
            "name reuse does not establish ownership");
    fs::remove(interrupted / ".khcom-write-fixture");
    fs::create_hard_link(interrupted / ".khcom-anchor-fixture",
                         interrupted / ".khcom-write-fixture");
    require(take(recover_owned_temporaries(interrupted)).recovered == 1,
            "retained ownership permits cleanup retry");
    interrupted_fixture(interrupted);
    fs::rename(interrupted / ".khcom-write-fixture", interrupted / "committed");
    require(take(recover_owned_temporaries(interrupted)).recovered == 1 &&
                take(read_file(interrupted / "committed", 65536)) ==
                    b("incomplete payload"),
            "post-rename cleanup never removes committed file");
#ifndef _WIN32
    if (geteuid() != 0) {
      interrupted_fixture(interrupted);
      fs::permissions(interrupted,
                      fs::perms::owner_read | fs::perms::owner_exec);
      recovery = take(recover_owned_temporaries(interrupted));
      fs::permissions(interrupted, fs::perms::owner_all);
      require(recovery.retained.size() == 1,
              "permission failure retains ownership");
      require(take(recover_owned_temporaries(interrupted)).recovered == 1,
              "permission recovery retries cleanup");
    }
    auto capacity = root / "capacity";
    put(capacity, b("old"));
    auto child = fork();
    require(child >= 0, "capacity test fork");
    if (child == 0) {
      signal(SIGXFSZ, SIG_IGN);
      rlimit limit{512, 512};
      if (setrlimit(RLIMIT_FSIZE, &limit) != 0)
        _exit(2);
      auto result = atomic_write(capacity, Bytes(2048, 0x42));
      _exit(std::holds_alternative<Error>(result) ? 0 : 3);
    }
    int status = 0;
    require(waitpid(child, &status, 0) == child && WIFEXITED(status) &&
                WEXITSTATUS(status) == 0,
            "kernel write capacity failure observed");
    require(
        take(read_file(capacity, 65536)) == b("old") &&
            take(recover_owned_temporaries(root)).retained.empty(),
        "capacity failure preserves active bytes and cleans owned temporary");
#endif

    c = Config{};
    c.fit = false;
    c.scale = 6;
    auto v = viewport(1440, 960, c);
    require(v.fits && v.width == 1440 && v.height == 960, "physical6x exact");
    require(!viewport(1280, 720, c).fits, "oversize explicit refusal");
    c.fit = true;
    v = viewport(1920, 1080, c);
    require(v.width == 1440 && v.height == 960, "integer fit");
    c.stretch = true;
    v = viewport(1920, 1080, c);
    require(v.width == 1920 && v.height == 1080, "stretch explicit");
    for (int hz : {60, 120, 144, 500}) {
      FrameClock clock;
      unsigned frames = 0;
      for (int i = 0; i < hz * 120; ++i)
        frames += clock.due(1.0 / hz, false);
      require(frames == unsigned(120 / clock.period()),
              "simulation duration independent of display cadence");
      require(clock.due(15, false) == 0 && clock.suspended_gaps() == 1,
              "suspend does not fast-forward");
      require(clock.due(.02, true) == 0, "paused clock");
    }
    lock.reset();
    fs::remove_all(root);
    std::cout << "BPS/ZIP identity, config recovery, atomic save "
                 "envelope/backups/profiles, physical viewport "
                 "and60/120/144/500Hz scheduler contracts passed.\n";
    return 0;
  } catch (const std::exception &e) {
    std::cerr << e.what() << " (evidence left in " << root << ")\n";
    return 1;
  }
}
