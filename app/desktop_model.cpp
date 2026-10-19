#include "app/desktop_model.hpp"
#include "core/sha256.hpp"
#include "platform/atomic_file.hpp"
#include <algorithm>
#include <chrono>
#include <fstream>
#include <limits>
#include <miniz.h>
#include <set>
#include <system_error>

namespace khcom::desktop {
namespace {
struct Failed : std::runtime_error {
  std::string code;
  Failed(std::string c, std::string m) : runtime_error(m), code(c) {}
};
[[noreturn]] void fail(const char *c, const std::string &m) {
  throw Failed(c, m);
}
template <class T, class F> Result<T> guard(F f) {
  try {
    return f();
  } catch (const Failed &e) {
    return Error{e.code, e.what()};
  } catch (const std::exception &e) {
    return Error{"desktop_io", e.what()};
  }
}
template <class T> T take(Result<T> r) {
  if (auto *e = std::get_if<Error>(&r))
    throw Failed(e->code, e->message);
  return std::move(std::get<T>(r));
}
Bytes bytes(const std::string &s) { return Bytes(s.begin(), s.end()); }
std::string token() {
  static std::atomic<unsigned> n = 0;
  return std::to_string(
             std::chrono::steady_clock::now().time_since_epoch().count()) +
         "-" + std::to_string(++n);
}
bool hash(const std::string &s) {
  return s.size() == 64 && s.find_first_not_of("0123456789abcdef") == s.npos;
}
bool safe_name(const std::string &s) {
  return !s.empty() && s.size() <= 80 && s != "." && s != ".." &&
         s.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVW"
                             "XYZ0123456789-_.") == s.npos;
}
Json read_json(const fs::path &p) {
  auto b = take(read_file(p, 65536));
  auto j = Json::parse(b);
  if (!j.is_object())
    fail("json_shape", "Documento deve ser um objeto JSON.");
  return j;
}
void write_json(const fs::path &p, const Json &j, bool backup = true) {
  take(atomic_write(p, bytes(j.dump(2)), backup));
}
void validate_manifest(const Json &j) {
  if (j.at("schema_version") != 1 || j.at("source_sha256") != original_sha ||
      j.at("source_size") != rom_size)
    fail("package_source",
         "O pacote não corresponde à ROM USA B8CE suportada.");
  for (auto k : {"patch_sha256", "target_sha256"})
    if (!hash(j.at(k).get<std::string>()))
      fail("package_digest", "Digest do pacote inválido.");
  if (!safe_name(j.at("id")) || !safe_name(j.at("patch_file")) ||
      !safe_name(j.at("save_compatibility")))
    fail("package_path", "Identificador/caminho do pacote inválido.");
  if (j.at("status") != "experimental" && j.at("status") != "complete")
    fail("package_status", "Estado do pacote desconhecido.");
  if (j.at("target_size") != rom_size ||
      !j.at("patch_size").is_number_unsigned() ||
      j.at("patch_size").get<std::uint64_t>() > 64 * 1024 * 1024 ||
      j.at("patch_size").get<std::uint64_t>() < 19)
    fail("package_size", "Tamanhos do pacote fora dos limites.");
}
fs::path save_path(const fs::path &r, const Json &m, int profile) {
  if (profile < 0 || profile > 2)
    fail("save_profile", "Perfil inválido.");
  auto compat = m.at("save_compatibility").get<std::string>();
  if (!safe_name(compat))
    fail("save_identity", "Compatibilidade do save inválida.");
  return r / "saves" / "B8CE" / compat /
         ("perfil-" + std::to_string(profile + 1) + ".khcs");
}
std::uint32_t u32(std::span<const std::uint8_t> b, std::size_t off) {
  if (off > b.size() || b.size() - off < 4)
    fail("truncated", "Dados truncados.");
  return b[off] | (std::uint32_t(b[off + 1]) << 8) |
         (std::uint32_t(b[off + 2]) << 16) | (std::uint32_t(b[off + 3]) << 24);
}
std::uint32_t crc(std::span<const std::uint8_t> b) {
  return mz_crc32(0, b.data(), b.size());
}
void check_cancel(std::atomic<bool> *c) {
  if (c && c->load())
    fail("cancelled",
         "Operação cancelada. A instalação anterior foi preservada.");
}
} // namespace
Result<Bytes> read_stream(std::istream &input, std::size_t limit,
                          std::optional<std::size_t> expected_size) {
  return guard<Bytes>([&] {
    if (limit > import_limit || (expected_size && *expected_size > limit))
      fail("file_limit", "Limite de leitura fora do intervalo permitido.");
    const auto cap = expected_size.value_or(limit);
    std::array<char, 65536> chunk;
    Bytes result;
    result.reserve(std::min(cap, chunk.size()));
    while (true) {
      // Read one sentinel byte beyond the cap, without allocating beyond it.
      const auto amount = std::min(chunk.size(), cap - result.size() + 1);
      bool threw = false;
      try {
        input.read(chunk.data(), static_cast<std::streamsize>(amount));
      } catch (const std::exception &) {
        threw = true;
      }
      const auto count = input.gcount();
      if (count < 0 || static_cast<std::size_t>(count) > amount ||
          input.bad() || (threw && !input.eof()) ||
          (input.fail() && !input.eof()))
        fail("file_read", "Falha na leitura do fluxo de dados.");
      const auto received = static_cast<std::size_t>(count);
      if (received > cap - result.size())
        fail(expected_size ? "file_changed" : "file_limit",
             "Fonte excedeu o tamanho permitido durante a leitura.");
      const auto needed = result.size() + received;
      if (needed > result.capacity())
        result.reserve(std::min(cap, std::max(needed, result.capacity() * 2)));
      result.insert(result.end(), chunk.begin(), chunk.begin() + received);
      if (input.eof()) {
        if (expected_size && result.size() != *expected_size)
          fail("file_changed", "Fonte foi truncada durante a leitura.");
        return result;
      }
      if (received != amount)
        fail("file_read", "Fluxo terminou sem confirmar fim de arquivo.");
    }
  });
}
Result<Bytes> read_file(const fs::path &p, std::size_t limit) {
  return guard<Bytes>([&] {
    if (limit > import_limit)
      fail("file_limit", "Limite de leitura fora do intervalo permitido.");
    if (!fs::is_regular_file(p))
      fail("file_type", "Selecione um arquivo regular.");
    const auto n = fs::file_size(p);
    if (n > limit)
      fail("file_limit", "Arquivo excede o limite permitido.");
    std::ifstream input(p, std::ios::binary);
    if (!input)
      fail("file_open", "Não foi possível abrir o arquivo.");
    return take(read_stream(input, limit, static_cast<std::size_t>(n)));
  });
}
Result<Success> atomic_write(const fs::path &p, std::span<const std::uint8_t> b,
                             bool backup) {
  return guard<Success>([&] {
    if (fs::is_symlink(p))
      fail("write_symlink", "Destino simbólico recusado.");
    if (backup && fs::exists(p)) {
      auto old = take(read_file(p, 64 * 1024 * 1024));
      auto bak = p;
      bak += ".bak";
      take(write_atomic_owned(bak, old));
    }
    return take(write_atomic_owned(p, b));
  });
}
Result<Bytes> apply_bps(std::span<const std::uint8_t> s,
                        std::span<const std::uint8_t> p) {
  return guard<Bytes>([&] {
    if (s.size() > rom_size || p.size() < 19 || p.size() > 64 * 1024 * 1024 ||
        std::string(p.begin(), p.begin() + 4) != "BPS1")
      fail("bps_header", "Patch BPS inválido ou grande demais.");
    auto end = p.size() - 12;
    if (crc(p.first(p.size() - 4)) != u32(p, p.size() - 4) ||
        crc(s) != u32(p, end))
      fail("bps_crc", "CRC do patch ou da origem inválido.");
    std::size_t pos = 4;
    auto number = [&]() {
      std::uint64_t v = 0, shift = 1;
      for (int i = 0; i < 10; ++i) {
        if (pos >= end)
          fail("bps_truncated", "Inteiro BPS truncado.");
        auto b = p[pos++];
        auto low = b & 127;
        if (low > (UINT64_MAX - v) / shift)
          fail("bps_integer", "Inteiro BPS excede 64 bits.");
        v += low * shift;
        if (b & 128)
          return v;
        if (shift > UINT64_MAX / 128)
          fail("bps_integer", "Inteiro BPS excede 64 bits.");
        shift *= 128;
        if (v > UINT64_MAX - shift)
          fail("bps_integer", "Inteiro BPS excede 64 bits.");
        v += shift;
      }
      fail("bps_integer", "Inteiro BPS inválido.");
    };
    if (number() != s.size())
      fail("bps_source", "Tamanho da origem BPS incorreto.");
    auto target = number(), meta = number();
    if (target > rom_size || meta > 65536 || meta > end - pos)
      fail("bps_limit", "Destino/metadados BPS excedem o limite.");
    pos += meta;
    Bytes out;
    out.reserve(target);
    std::int64_t sr = 0, tr = 0;
    unsigned actions = 0;
    while (pos < end) {
      if (++actions > 262144)
        fail("bps_actions", "Patch excede limite de comandos.");
      auto command = number(), n = (command >> 2) + 1;
      auto op = command & 3;
      if (n > target - out.size())
        fail("bps_overflow", "Comando ultrapassa o destino.");
      if (op == 0) {
        if (out.size() + n > s.size())
          fail("bps_read", "Leitura fora da origem.");
        out.insert(out.end(), s.begin() + out.size(),
                   s.begin() + out.size() + n);
      } else if (op == 1) {
        if (n > end - pos)
          fail("bps_literal", "Literal truncado.");
        out.insert(out.end(), p.begin() + pos, p.begin() + pos + n);
        pos += n;
      } else {
        auto delta = number();
        if ((delta >> 1) > INT64_MAX - rom_size)
          fail("bps_relative", "Deslocamento relativo inválido.");
        auto &relative = op == 2 ? sr : tr;
        relative +=
            (delta & 1) ? -std::int64_t(delta >> 1) : std::int64_t(delta >> 1);
        if (relative < 0)
          fail("bps_relative", "Referência negativa.");
        for (std::uint64_t i = 0; i < n; ++i) {
          if (op == 2) {
            if (std::uint64_t(relative) >= s.size())
              fail("bps_copy", "Cópia fora da origem.");
            out.push_back(s[relative++]);
          } else {
            if (std::uint64_t(relative) >= out.size())
              fail("bps_copy", "Cópia futura inválida.");
            out.push_back(out[relative++]);
          }
        }
      }
    }
    if (out.size() != target || crc(out) != u32(p, end + 4))
      fail("bps_target", "Destino BPS incompleto ou CRC inválido.");
    return out;
  });
}
Result<RomImport> import_rom(const fs::path &p, int member) {
  return guard<RomImport>([&] {
    return take(import_rom_bytes(take(read_file(p, import_limit)), member));
  });
}
Result<RomImport> import_rom_stream(std::istream &input, int member) {
  return guard<RomImport>([&] {
    return take(
        import_rom_bytes(take(read_stream(input, import_limit)), member));
  });
}
Result<RomImport> import_rom_bytes(Bytes b, int member) {
  return guard<RomImport>([&] {
    if (b.size() > import_limit)
      fail("file_limit", "Fonte excede o limite de importação.");
    RomImport out;
    if (b.size() >= 4 && b[0] == 'P' && b[1] == 'K') {
      mz_zip_archive z{};
      if (!mz_zip_reader_init_mem(&z, b.data(), b.size(), 0))
        fail("zip_invalid", "ZIP inválido ou truncado.");
      struct End {
        mz_zip_archive *z;
        ~End() { mz_zip_reader_end(z); }
      } end{&z};
      auto count = mz_zip_reader_get_num_files(&z);
      if (count > 1024)
        fail("zip_count", "ZIP com mais de 1024 entradas não suportado.");
      std::uint64_t total = 0;
      for (unsigned i = 0; i < count; ++i) {
        mz_zip_archive_file_stat st{};
        if (!mz_zip_reader_file_stat(&z, i, &st))
          fail("zip_stat", "Índice ZIP inválido.");
        std::string name = st.m_filename;
        fs::path entry = from_utf8(name);
        if (name.empty() || name.size() > 512 || name[0] == '/' ||
            name.find('\\') != name.npos || name.find(':') != name.npos ||
            ((st.m_external_attr >> 16) & 0170000) == 0120000)
          fail("zip_path", "ZIP contém caminho ou link não permitido.");
        for (const auto &part : entry)
          if (part == "..")
            fail("zip_path", "ZIP contém caminho que sai do destino.");
        if (st.m_is_encrypted)
          fail("zip_encrypted", "ZIP criptografado não suportado.");
        total += st.m_uncomp_size;
        if (st.m_uncomp_size > rom_size || total > 128 * 1024 * 1024)
          fail("zip_expansion", "ZIP excede limite de expansão.");
        auto ext = entry.extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        if (!st.m_is_directory && ext == ".gba")
          out.choices.push_back({i, name, st.m_uncomp_size});
      }
      if (out.choices.empty())
        fail("zip_empty", "ZIP sem arquivo .gba.");
      if (member < 0 && out.choices.size() > 1)
        return out;
      unsigned selected = member < 0 ? out.choices[0].index : unsigned(member);
      auto choice = std::find_if(out.choices.begin(), out.choices.end(),
                                 [&](auto &c) { return c.index == selected; });
      if (choice == out.choices.end())
        fail("zip_selection", "Seleção ZIP inválida.");
      if (choice->size != rom_size)
        fail("rom_size", "A ROM selecionada não tem 32 MiB.");
      out.bytes.resize(choice->size);
      if (!mz_zip_reader_extract_to_mem(&z, selected, out.bytes.data(),
                                        out.bytes.size(), 0))
        fail("zip_crc",
             "Extração ZIP falhou (CRC, compressão ou truncamento).");
      out.choices.clear();
    } else
      out.bytes = std::move(b);
    if (out.bytes.size() != rom_size || sha256(out.bytes) != original_sha)
      fail(
          "rom_identity",
          "ROM incompatível. É necessária a edição USA B8CE revisão 0 original "
          "de 32 MiB. Uma ROM já modificada não é aceita como origem.");
    return out;
  });
}
Result<LoadedConfig> load_config(const fs::path &p) {
  return guard<LoadedConfig>([&] {
    LoadedConfig out;
    if (!fs::exists(p))
      return out;
    try {
      auto j = read_json(p);
      if (j.at("schema_version") != 1)
        fail("config_version", "Versão de configuração desconhecida.");
      const std::set<std::string> allowed = {
          "schema_version", "scale",    "filter",  "volume",     "deadzone",
          "profile",        "fit",      "stretch", "fullscreen", "vsync",
          "mute",           "keyboard", "gamepad"};
      for (auto it = j.begin(); it != j.end(); ++it)
        if (!allowed.contains(it.key()))
          fail("config_unknown", "Opção de configuração desconhecida.");
      Config c;
      c.scale = j.at("scale");
      c.filter = j.at("filter");
      c.volume = j.at("volume");
      c.deadzone = j.at("deadzone");
      c.profile = j.at("profile");
      c.fit = j.at("fit");
      c.stretch = j.at("stretch");
      c.fullscreen = j.at("fullscreen");
      c.vsync = j.at("vsync");
      c.mute = j.at("mute");
      c.keyboard = j.at("keyboard").get<std::array<int, 10>>();
      c.gamepad = j.at("gamepad").get<std::array<int, 10>>();
      if (c.scale < 1 || c.scale > 6 || c.filter < 0 || c.filter > 2 ||
          c.volume < 0 || c.volume > 100 || c.deadzone < 2000 ||
          c.deadzone > 24000 || c.profile < 0 || c.profile > 2)
        fail("config_range", "Configuração fora do intervalo.");
      std::set<int> keys, pads;
      for (auto k : c.keyboard)
        if (k <= 0 || k >= 512 || k == 41 || k == 58 || !keys.insert(k).second)
          fail("config_keys", "Mapeamento de teclado inválido.");
      for (auto k : c.gamepad)
        if (k < 0 || k >= 26 || k == 5 || !pads.insert(k).second)
          fail("config_pad", "Mapeamento de controle inválido.");
      out.config = c;
    } catch (const std::exception &) {
      auto backup = p;
      backup += ".invalid-" + token();
      auto original = take(read_file(p, 1024 * 1024));
      take(atomic_write(backup, original, false));
      out.warning = "Configuração inválida preservada em " + backup.string() +
                    ". Padrões aplicados; saves mantidos.";
    }
    return out;
  });
}
Result<Success> save_config(const fs::path &p, const Config &c) {
  return guard<Success>([&] {
    Json j = {{"schema_version", 1},
              {"scale", c.scale},
              {"filter", c.filter},
              {"volume", c.volume},
              {"deadzone", c.deadzone},
              {"profile", c.profile},
              {"fit", c.fit},
              {"stretch", c.stretch},
              {"fullscreen", c.fullscreen},
              {"vsync", c.vsync},
              {"mute", c.mute},
              {"keyboard", c.keyboard},
              {"gamepad", c.gamepad}};
    write_json(p, j);
    return Success{};
  });
}
std::string cache_key(const Json &manifest) {
  // Bind every result-affecting input and applicator contract, not just output.
  return sha256(bytes(std::string("khcom-bps-v1\n") +
                      manifest.at("source_sha256").get<std::string>() + "\n" +
                      manifest.at("patch_sha256").get<std::string>() + "\n" +
                      manifest.at("target_sha256").get<std::string>()));
}
Result<Installed> install(const fs::path &r, const Bytes &original,
                          const fs::path &package, std::atomic<bool> *cancel,
                          InstallObserver observer) {
  return guard<Installed>([&] {
    auto phase = [&](InstallPhase p) {
      if (observer)
        try {
          observer(p);
        } catch (...) {
        };
    };
    phase(InstallPhase::validation);
    if (original.size() != rom_size || sha256(original) != original_sha)
      fail("rom_identity", "Origem precisa ser a ROM original validada.");
    check_cancel(cancel);
    auto j = read_json(package);
    validate_manifest(j);
    phase(InstallPhase::patch);
    auto patch =
        take(read_file(package.parent_path() /
                           from_utf8(j.at("patch_file").get<std::string>()),
                       64 * 1024 * 1024));
    if (patch.size() != j.at("patch_size") ||
        sha256(patch) != j.at("patch_sha256").get<std::string>())
      fail("patch_identity", "Patch difere do manifesto.");
    check_cancel(cancel);
    j.erase("previous_installation"); // Package metadata cannot supply local
                                      // history.
    j["applicator"] = "khcom-bps-v1";
    j["cache_key"] = cache_key(j);
    auto dir = r / "cache" / cache_key(j);
    phase(InstallPhase::cache);
    Bytes target;
    if (fs::exists(dir / "game.gba")) {
      auto cached = read_file(dir / "game.gba", rom_size);
      if (auto *b = std::get_if<Bytes>(&cached);
          b && b->size() == rom_size &&
          sha256(*b) == j.at("target_sha256").get<std::string>())
        target = std::move(*b);
    }
    if (target.empty()) {
      target = take(apply_bps(original, patch));
      if (target.size() != j.at("target_size") ||
          sha256(target) != j.at("target_sha256").get<std::string>())
        fail("target_identity", "Destino difere do manifesto.");
      check_cancel(cancel);
      take(atomic_write(dir / "game.gba", target, false));
      write_json(dir / "manifest.json", j, false);
    }
    check_cancel(cancel);
    bool unchanged = false;
    if (fs::exists(r / "active.json")) {
      auto old = read_json(r / "active.json");
      validate_manifest(old);
      if (old.value("cache_key", "") == cache_key(j)) {
        if (old.contains("previous_installation"))
          j["previous_installation"] = old["previous_installation"];
        unchanged = old == j;
      } else {
        old.erase("previous_installation");
        j["previous_installation"] = old;
      }
    }
    check_cancel(cancel);
    phase(InstallPhase::activation);
    check_cancel(cancel);
    // Current and rollback identities become visible at the same atomic rename.
    if (!unchanged)
      write_json(r / "active.json", j);
    phase(InstallPhase::complete);
    return Installed{std::move(target), j};
  });
}
Result<Installed> load_active(const fs::path &r, bool previous) {
  return guard<Installed>([&] {
    auto j = read_json(r / "active.json");
    if (previous) {
      if (!j.contains("previous_installation"))
        fail("no_previous", "Não há pacote anterior registrado.");
      j = j.at("previous_installation").get<Json>();
    }
    validate_manifest(j);
    if (j.value("applicator", "") != "khcom-bps-v1" ||
        j.value("cache_key", "") != cache_key(j))
      fail("cache_version", "Cache de outra versão do aplicador. Reimporte a "
                            "ROM e o pacote; saves preservados.");
    auto target =
        take(read_file(r / "cache" / cache_key(j) / "game.gba", rom_size));
    if (target.size() != j.at("target_size") ||
        sha256(target) != j.at("target_sha256").get<std::string>())
      fail("cache_corrupt", "Cache adulterado ou incompleto. Reimporte a ROM e "
                            "o pacote; o save foi preservado.");
    return Installed{std::move(target), j};
  });
}
Result<Success> rollback(const fs::path &r) {
  return guard<Success>([&] {
    auto previous = take(load_active(r, true));
    auto current = read_json(r / "active.json");
    current.erase("previous_installation");
    previous.manifest["previous_installation"] = current;
    write_json(r / "active.json", previous.manifest);
    return Success{};
  });
}
Result<Bytes> load_save(const fs::path &r, const Json &m, int profile) {
  return guard<Bytes>([&] {
    auto p = save_path(r, m, profile);
    if (!fs::exists(p))
      return Bytes{};
    return take(import_save(p, m));
  });
}
Result<Success> restore_save_backup(const fs::path &r, const Json &m,
                                    int profile) {
  return guard<Success>([&] {
    auto path = save_path(r, m, profile);
    auto backup = path;
    backup += ".bak";
    auto data = take(
        import_save(backup, m)); // Validate before touching the active file.
    if (fs::exists(path)) {
      auto preserved = path;
      preserved += ".before-restore-" + token();
      take(atomic_write(preserved, take(read_file(path, 65536)), false));
    }
    auto packed = take(read_file(backup, 65536));
    take(atomic_write(path, packed, false));
    return Success{};
  });
}
Result<Success> store_save(const fs::path &r, const Json &m, int profile,
                           std::span<const std::uint8_t> b) {
  return guard<Success>([&] {
    if (b.empty())
      return Success{};
    if (b.size() != 32768)
      fail("save_size",
           "Backend de save inesperado; dados preservados em memória.");
    auto p = save_path(r, m, profile);
    if (fs::exists(p)) {
      auto old = take(import_save(p, m));
      if (old.size() == b.size() &&
          std::equal(old.begin(), old.end(), b.begin()))
        return Success{};
    }
    return take(export_save(p, m, b));
  });
}
Result<Bytes> encode_save(const Json &m, std::span<const std::uint8_t> b) {
  return guard<Bytes>([&] {
    if (b.size() != 32768)
      fail("save_size", "Nenhum save SRAM válido para exportar.");
    if (!safe_name(m.at("save_compatibility").get<std::string>()))
      fail("save_identity", "Compatibilidade do save inválida.");
    Json j = {{"schema_version", 1},
              {"game", "B8CE"},
              {"save_compatibility", m.at("save_compatibility")},
              {"sha256", sha256(b)},
              {"data", Json::binary(Bytes(b.begin(), b.end()))}};
    return Json::to_cbor(j);
  });
}
Result<Bytes> decode_save(std::span<const std::uint8_t> b, const Json &m) {
  return guard<Bytes>([&] {
    if (b.size() > 65536)
      fail("file_limit", "Envelope de save excede o limite permitido.");
    auto j = Json::from_cbor(b.begin(), b.end());
    if (j.at("schema_version") != 1 || j.at("game") != "B8CE" ||
        j.at("save_compatibility") != m.at("save_compatibility") ||
        !safe_name(m.at("save_compatibility").get<std::string>()) ||
        !j.at("data").is_binary())
      fail("save_identity",
           "Save pertence a outro jogo/formato/versão de compatibilidade.");
    Bytes data = j.at("data").get_binary();
    if (data.size() != 32768 ||
        sha256(data) != j.at("sha256").get<std::string>())
      fail("save_integrity", "Save exportado inválido ou corrompido.");
    return data;
  });
}
Result<Success> export_save(const fs::path &p, const Json &m,
                            std::span<const std::uint8_t> b) {
  return guard<Success>(
      [&] { return take(atomic_write(p, take(encode_save(m, b)))); });
}
Result<Bytes> import_save(const fs::path &p, const Json &m) {
  return guard<Bytes>(
      [&] { return take(decode_save(take(read_file(p, 65536)), m)); });
}
Viewport viewport(int w, int h, const Config &c) {
  if (w <= 0 || h <= 0)
    return {0, 0, 0, 0, false};
  if (c.stretch)
    return {0, 0, w, h, true};
  int dw = 240 * c.scale, dh = 160 * c.scale;
  if (c.fit) {
    int scale = std::min(w / 240, h / 160);
    if (scale < 1)
      return {0, 0, 0, 0, false};
    dw = 240 * scale;
    dh = 160 * scale;
  }
  if (dw > w || dh > h)
    return {0, 0, 0, 0, false};
  return {(w - dw) / 2, (h - dh) / 2, dw, dh, true};
}
unsigned FrameClock::due(double elapsed, bool paused) {
  if (paused) {
    reset();
    return 0;
  }
  if (elapsed < 0 || elapsed > 0.25) {
    reset();
    ++gaps_;
    return 0;
  }
  credit_ += elapsed;
  auto frames = unsigned((credit_ + 1e-12) / period_);
  credit_ -= frames * period_;
  return frames;
}
} // namespace khcom::desktop
