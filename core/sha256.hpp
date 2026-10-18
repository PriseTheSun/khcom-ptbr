#pragma once
#include <cstdint>
#include <span>
#include <string>

namespace khcom {
std::string sha256(std::span<const std::uint8_t> data);
}
