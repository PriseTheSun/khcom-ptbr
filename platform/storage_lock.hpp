#pragma once
#include "core/session.hpp"
#include <filesystem>
namespace khcom {
class StorageLock {
public:
  static Result<std::unique_ptr<StorageLock>>
  acquire(const std::filesystem::path &directory);
  ~StorageLock();

private:
  StorageLock() = default;
#ifdef _WIN32
  void *handle_ = nullptr;
#else
  int handle_ = -1;
#endif
};
} // namespace khcom
