#pragma once
#include "core/session.hpp"
#include <memory>

namespace khcom {
class Preview {
public:
  static Result<std::unique_ptr<Preview>> create(unsigned scale);
  ~Preview();
  Result<bool> present(std::span<const std::uint32_t> pixels);
private:
  Preview() = default;
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
}
