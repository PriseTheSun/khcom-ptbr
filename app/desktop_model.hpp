#pragma once
#include "core/session.hpp"
#include <array>
#include <atomic>
#include <filesystem>
#include <functional>
#include <nlohmann/json.hpp>
#include <string_view>
namespace khcom::desktop {
namespace fs = std::filesystem;
inline fs::path from_utf8(std::string_view s) {
  return fs::path(std::u8string(s.begin(), s.end()));
}
using Bytes = std::vector<std::uint8_t>;
using Json = nlohmann::json;
inline constexpr const char *original_sha =
    "6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d";
inline constexpr std::size_t rom_size = 33554432;
struct Config {
  int version = 1, scale = 3, filter = 0, volume = 80, deadzone = 8000,
      profile = 0;
  bool fit = true, stretch = false, fullscreen = false, vsync = true,
       mute = false;
  std::array<int, 10> keyboard{27, 29, 42, 40, 79, 80, 82, 81, 22, 4};
  std::array<int, 10> gamepad{0, 1, 4, 6, 14, 13, 11, 12, 10, 9};
};
struct LoadedConfig {
  Config config;
  std::string warning;
};
struct ZipChoice {
  unsigned index;
  std::string name;
  std::uint64_t size;
};
struct RomImport {
  Bytes bytes;
  std::vector<ZipChoice> choices;
};
struct Installed {
  Bytes bytes;
  Json manifest;
};
Result<Bytes> read_file(const fs::path &, std::size_t limit);
Result<Success> atomic_write(const fs::path &, std::span<const std::uint8_t>,
                             bool backup = true);
Result<Bytes> apply_bps(std::span<const std::uint8_t> source,
                        std::span<const std::uint8_t> patch);
Result<RomImport> import_rom(const fs::path &, int member = -1);
Result<LoadedConfig> load_config(const fs::path &);
Result<Success> save_config(const fs::path &, const Config &);
enum class InstallPhase { validation, patch, cache, activation, complete };
using InstallObserver = std::function<void(InstallPhase)>;
Result<Installed> install(const fs::path &root, const Bytes &original,
                          const fs::path &package,
                          std::atomic<bool> *cancel = nullptr,
                          InstallObserver observer = {});
Result<Installed> load_active(const fs::path &root, bool previous = false);
Result<Success> rollback(const fs::path &root);
std::string cache_key(const Json &manifest);
Result<Success> restore_save_backup(const fs::path &root, const Json &manifest,
                                    int profile);
Result<Bytes> load_save(const fs::path &root, const Json &manifest,
                        int profile);
Result<Success> store_save(const fs::path &root, const Json &manifest,
                           int profile, std::span<const std::uint8_t>);
Result<Success> export_save(const fs::path &destination, const Json &manifest,
                            std::span<const std::uint8_t>);
Result<Bytes> import_save(const fs::path &source, const Json &manifest);
struct Viewport {
  int x, y, width, height;
  bool fits;
};
Viewport viewport(int physical_width, int physical_height, const Config &);
// Wall-clock accumulator; display cadence never selects simulated speed.
class FrameClock {
public:
  explicit FrameClock(double period = 280896.0 / 16777216.0)
      : period_(period) {}
  unsigned due(double elapsed, bool paused);
  void reset() { credit_ = 0; }
  double period() const { return period_; }
  std::uint64_t suspended_gaps() const { return gaps_; }

private:
  double period_, credit_ = 0;
  std::uint64_t gaps_ = 0;
};
} // namespace khcom::desktop
