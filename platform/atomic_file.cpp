#include "platform/atomic_file.hpp"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <nlohmann/json.hpp>
#include <system_error>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#endif
namespace khcom {
namespace {
namespace fs = std::filesystem;
using Json = nlohmann::json;
std::string utf8(const fs::path &p) {
  auto s = p.u8string();
  return {s.begin(), s.end()};
}
fs::path path(const std::string &s) {
  return fs::path(std::u8string(s.begin(), s.end()));
}
std::string token() {
  static std::atomic<unsigned> n = 0;
  return std::to_string(
             std::chrono::steady_clock::now().time_since_epoch().count()) +
         "-" + std::to_string(++n);
}
struct Identity {
  std::uint64_t device, index;
  bool operator==(const Identity &) const = default;
};
Identity identity(const fs::path &p) {
  if (fs::is_symlink(p) || !fs::is_regular_file(p))
    throw std::runtime_error(
        "Identidade do temporário não é um arquivo regular.");
#ifdef _WIN32
  auto h = CreateFileW(p.c_str(), 0,
                       FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                       nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (h == INVALID_HANDLE_VALUE)
    throw std::runtime_error("Falha ao ler identidade do arquivo.");
  BY_HANDLE_FILE_INFORMATION info{};
  bool ok = GetFileInformationByHandle(h, &info);
  CloseHandle(h);
  if (!ok)
    throw std::runtime_error("Falha ao ler identidade do arquivo.");
  return {info.dwVolumeSerialNumber,
          (std::uint64_t(info.nFileIndexHigh) << 32) | info.nFileIndexLow};
#else
  struct stat st{};
  if (::lstat(p.c_str(), &st) != 0 || !S_ISREG(st.st_mode))
    throw std::runtime_error("Falha ao ler identidade do arquivo.");
  return {std::uint64_t(st.st_dev), std::uint64_t(st.st_ino)};
#endif
}
struct File {
#ifdef _WIN32
  HANDLE fd = INVALID_HANDLE_VALUE;
  explicit File(const fs::path &p) {
    fd = CreateFileW(p.c_str(), GENERIC_WRITE,
                     FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                     nullptr, CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (fd == INVALID_HANDLE_VALUE)
      throw std::runtime_error("Falha ao criar arquivo exclusivo.");
  }
  ~File() {
    if (fd != INVALID_HANDLE_VALUE)
      CloseHandle(fd);
  }
  void write(std::span<const std::uint8_t> b) {
    std::size_t done = 0;
    while (done < b.size()) {
      DWORD n = 0;
      DWORD amount = DWORD(std::min<std::size_t>(b.size() - done, 1 << 20));
      if (!WriteFile(fd, b.data() + done, amount, &n, nullptr) || !n)
        throw std::runtime_error("Gravação incompleta.");
      done += n;
    }
    if (!FlushFileBuffers(fd))
      throw std::runtime_error("Falha ao confirmar gravação.");
  }
#else
  int fd = -1;
  explicit File(const fs::path &p) {
    fd = ::open(p.c_str(), O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0600);
    if (fd < 0)
      throw std::runtime_error("Falha ao criar arquivo exclusivo.");
  }
  ~File() {
    if (fd >= 0)
      ::close(fd);
  }
  void write(std::span<const std::uint8_t> b) {
    std::size_t done = 0;
    while (done < b.size()) {
      auto n = ::write(fd, b.data() + done, b.size() - done);
      if (n < 0 && errno == EINTR)
        continue;
      if (n <= 0)
        throw std::runtime_error("Gravação incompleta.");
      done += n;
    }
    if (::fsync(fd) != 0)
      throw std::runtime_error("Falha ao confirmar gravação.");
  }
#endif
};
void sync_directory(const fs::path &p) {
#ifndef _WIN32
  int fd = ::open(p.c_str(), O_RDONLY);
  if (fd >= 0) {
    ::fsync(fd);
    ::close(fd);
  }
#endif
}
void unlink_owned(const fs::path &temp, const fs::path &anchor,
                  const fs::path &record, Identity expected) {
  if (!fs::exists(anchor) && !fs::exists(temp) && !fs::is_symlink(temp)) {
    fs::remove(record);
    return;
  }
  if (!fs::exists(anchor))
    throw std::runtime_error(
        "Âncora de ownership ausente; arquivos preservados.");
  if (identity(anchor) != expected)
    throw std::runtime_error(
        "Âncora mudou de identidade; arquivos preservados.");
  if (fs::exists(temp) || fs::is_symlink(temp)) {
    if (identity(temp) != expected)
      throw std::runtime_error(
          "Temporário mudou de identidade; arquivos preservados.");
    fs::remove(temp);
  }
  fs::remove(anchor);
  fs::remove(record);
  sync_directory(record.parent_path());
}
bool basename(const std::string &s) {
  return !s.empty() && s.size() < 250 && s.find_first_of("/\\:") == s.npos &&
         s != "." && s != "..";
}
} // namespace
Result<Success> write_atomic_owned(const fs::path &destination,
                                   std::span<const std::uint8_t> bytes) {
  fs::path temp, anchor, record;
  Identity owned{};
  bool created = false, anchored = false, recorded = false;
  try {
    auto parent = destination.has_parent_path() ? destination.parent_path()
                                                : fs::path(".");
    fs::create_directories(parent);
    if (fs::is_symlink(destination))
      return Error{"write_symlink", "Destino simbólico recusado."};
    auto id = token();
    temp = parent / (".khcom-write-" + id);
    anchor = parent / (".khcom-anchor-" + id);
    record = parent / (".khcom-owned-" + id + ".json");
    {
      File output(temp);
      created = true;
      owned = identity(temp);
      fs::create_hard_link(temp, anchor);
      anchored = true;
      Json j = {{"schema", "khcom-owned-write-v1"},
                {"temporary", utf8(temp.filename())},
                {"anchor", utf8(anchor.filename())},
                {"device", owned.device},
                {"index", owned.index}};
      auto serialized = j.dump();
      {
        File journal(record);
        recorded = true;
        journal.write(
            {reinterpret_cast<const std::uint8_t *>(serialized.data()),
             serialized.size()});
      }
      sync_directory(parent);
      output.write(bytes);
    }
#ifdef _WIN32
    if (!MoveFileExW(temp.c_str(), destination.c_str(),
                     MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH))
      throw std::runtime_error("Falha ao ativar arquivo.");
#else
    fs::rename(temp, destination);
#endif
    sync_directory(parent);
    // The destination is committed. Cleanup failure is retained by the journal;
    // it must not be reported as a failed activation or trigger a second
    // commit.
    try {
      unlink_owned(temp, anchor, record, owned);
    } catch (const std::exception &) {
    }
    return Success{};
  } catch (const std::exception &e) {
    std::string reason = e.what();
    try {
      if (recorded && anchored)
        unlink_owned(temp, anchor, record, owned);
      else {
        if (anchored && identity(anchor) == owned)
          fs::remove(anchor);
        if (created && identity(temp) == owned)
          fs::remove(temp);
        if (recorded)
          fs::remove(record);
      }
    } catch (const std::exception &cleanup) {
      reason += " Limpeza pendente: ";
      reason += cleanup.what();
      reason += " Registro: " + utf8(record);
    }
    return Error{"atomic_write", reason};
  }
}
Result<TemporaryRecovery> recover_owned_temporaries(const fs::path &root) {
  TemporaryRecovery result;
  try {
    if (!fs::exists(root))
      return result;
    unsigned examined = 0;
    for (auto it = fs::recursive_directory_iterator(root);
         it != fs::recursive_directory_iterator(); ++it) {
      if (it.depth() >= 8)
        it.disable_recursion_pending();
      if (++examined > 16384) {
        result.retained.push_back(
            "Limite de inspeção atingido; limpeza não declarada completa.");
        break;
      }
      auto name = utf8(it->path().filename());
      if (!name.starts_with(".khcom-owned-") || !name.ends_with(".json"))
        continue;
      auto record = it->path();
      try {
        if (fs::is_symlink(record) || !fs::is_regular_file(record) ||
            fs::file_size(record) > 4096)
          throw std::runtime_error(
              "Registro sem identidade/formato reconhecido.");
        std::ifstream input(record, std::ios::binary);
        Json j;
        input >> j;
        if (j.at("schema") != "khcom-owned-write-v1")
          throw std::runtime_error("Versão de ownership desconhecida.");
        auto temp = j.at("temporary").get<std::string>(),
             anchor = j.at("anchor").get<std::string>();
        if (!basename(temp) || !basename(anchor) ||
            !temp.starts_with(".khcom-write-") ||
            !anchor.starts_with(".khcom-anchor-"))
          throw std::runtime_error("Caminho de ownership inválido.");
        auto identifier = name.substr(13, name.size() - 13 - 5);
        if (temp != ".khcom-write-" + identifier ||
            anchor != ".khcom-anchor-" + identifier)
          throw std::runtime_error(
              "Registro e âncoras não pertencem à mesma operação.");
        unlink_owned(record.parent_path() / path(temp),
                     record.parent_path() / path(anchor), record,
                     {j.at("device").get<std::uint64_t>(),
                      j.at("index").get<std::uint64_t>()});
        ++result.recovered;
      } catch (const std::exception &e) {
        result.retained.push_back(utf8(record) + ": " + e.what());
      }
    }
    return result;
  } catch (const std::exception &e) {
    return Error{"temporary_recovery", e.what()};
  }
}
} // namespace khcom
