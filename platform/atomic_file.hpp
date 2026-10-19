#pragma once
#include "core/session.hpp"
#include <filesystem>
namespace khcom {
struct TemporaryRecovery {
  unsigned recovered = 0;
  std::vector<std::string> retained;
};
// A durable ownership record and a hard-link anchor keep incomplete writes
// attributable even after restart. Recovery never uses a PID or name alone.
Result<Success> write_atomic_owned(const std::filesystem::path &path,
                                   std::span<const std::uint8_t> bytes);
Result<TemporaryRecovery>
recover_owned_temporaries(const std::filesystem::path &root);
} // namespace khcom
