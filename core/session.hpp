#pragma once
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <variant>
#include <vector>

struct mCore;
namespace khcom {
struct Error { std::string code; std::string message; };
template<class T> using Result = std::variant<T, Error>;
using Success = std::monostate;
struct AudioStats { std::uint64_t samples = 0; std::uint64_t nonzero = 0; int peak = 0; };
struct SaveInfo { std::string backend; std::size_t size; };

// Owns its core, immutable ROM buffer and memory-backed save. It never reads a
// global emulator configuration, discovers a BIOS, or writes files implicitly.
class Session {
public:
  static Result<std::unique_ptr<Session>> create(std::vector<std::uint8_t> rom,
                                                std::span<const std::uint8_t> save = {});
  ~Session();
  Session(const Session&) = delete;
  Session& operator=(const Session&) = delete;
  Result<Success> advance(std::uint16_t keys);
  Result<std::vector<std::uint8_t>> save() const;
  // Diagnostic CPU/RAM checkpoint only; cartridge data remains a separate save.
  Result<std::vector<std::uint8_t>> checkpoint() const;
  Result<Success> restore_checkpoint(std::span<const std::uint8_t> bytes);
  SaveInfo save_info() const;
  std::span<const std::uint32_t> pixels() const { return pixels_; }
  std::span<const std::uint8_t> rom() const { return rom_; }
  const AudioStats& audio() const { return audio_; }
  std::uint32_t frames() const;
  static constexpr unsigned width = 240;
  static constexpr unsigned height = 160;
  static const char* core_version();
private:
  Session() = default;
  mCore* core_ = nullptr;
  bool initialized_ = false;
  bool config_initialized_ = false;
  bool crashed_ = false;
  std::vector<std::uint8_t> rom_;
  std::string initial_save_digest_;
  std::vector<std::uint32_t> pixels_;
  AudioStats audio_;
};
}
