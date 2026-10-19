#include "platform/storage_lock.hpp"
#ifdef _WIN32
#define NOMINMAX
#include <windows.h>
#else
#include <fcntl.h>
#include <sys/file.h>
#include <unistd.h>
#endif
namespace khcom {
Result<std::unique_ptr<StorageLock>>
StorageLock::acquire(const std::filesystem::path &directory) {
  std::error_code ec;
  std::filesystem::create_directories(directory, ec);
  if (ec)
    return Error{"storage_directory", ec.message()};
  auto p = directory / "desktop.lock";
  if (std::filesystem::is_symlink(p))
    return Error{"storage_link", "Arquivo de bloqueio simbólico recusado."};
  auto lock = std::unique_ptr<StorageLock>(new StorageLock);
#ifdef _WIN32
  lock->handle_ =
      CreateFileW(p.c_str(), GENERIC_READ | GENERIC_WRITE, 0, nullptr,
                  OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (lock->handle_ == INVALID_HANDLE_VALUE) {
    lock->handle_ = nullptr;
    return Error{"storage_busy", "Outra instância já usa esta pasta de dados, "
                                 "ou a pasta não permite gravação."};
  }
#else
  lock->handle_ = ::open(p.c_str(), O_RDWR | O_CREAT | O_NOFOLLOW, 0600);
  if (lock->handle_ < 0 || ::flock(lock->handle_, LOCK_EX | LOCK_NB) != 0)
    return Error{"storage_busy", "Outra instância já usa esta pasta de dados, "
                                 "ou a pasta não permite gravação."};
#endif
  return lock;
}
StorageLock::~StorageLock() {
#ifdef _WIN32
  if (handle_)
    CloseHandle(handle_);
#else
  if (handle_ >= 0) {
    ::flock(handle_, LOCK_UN);
    ::close(handle_);
  }
#endif
}
} // namespace khcom
