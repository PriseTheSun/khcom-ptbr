#include "app/desktop_model.hpp"
#include "core/sha256.hpp"
#include "platform/atomic_file.hpp"
#include "platform/crt_shader.hpp"
#include "platform/storage_lock.hpp"
#include "ui_font.hpp"
#include <SDL3/SDL.h>
#include <SDL3/SDL_main.h>
#include <algorithm>
#include <chrono>
#include <future>
#include <imgui.h>
#include <imgui_impl_sdl3.h>
#include <imgui_impl_sdlrenderer3.h>
#include <iostream>
#include <map>
#include <mgba/core/log.h>
#include <optional>
#include <set>
#include <thread>
using namespace khcom;
using namespace khcom::desktop;
namespace {
template <class T> T take(Result<T> r) {
  if (auto *e = std::get_if<Error>(&r))
    throw std::runtime_error(e->code + ": " + e->message);
  return std::move(std::get<T>(r));
}
std::string utf8(const fs::path &p) {
  auto s = p.u8string();
  return {s.begin(), s.end()};
}
Bytes text_bytes(const std::string &s) { return {s.begin(), s.end()}; }
struct SDLResources {
  SDL_Window *window = nullptr;
  SDL_Renderer *renderer = nullptr;
  SDL_Texture *texture = nullptr;
  SDL_AudioStream *audio = nullptr;
  bool imgui = false;
  std::unique_ptr<CrtShader> crt;
  std::map<SDL_JoystickID, SDL_Gamepad *> pads;
  ~SDLResources() {
    for (auto &[_, pad] : pads)
      SDL_CloseGamepad(pad);
    if (imgui) {
      ImGui_ImplSDLRenderer3_Shutdown();
      ImGui_ImplSDL3_Shutdown();
      ImGui::DestroyContext();
    }
    crt.reset();
    SDL_DestroyAudioStream(audio);
    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
  }
};
struct Browser {
  struct Entry {
    fs::path path;
    bool directory;
  };
  struct Listing {
    std::vector<Entry> entries;
    std::string error;
    bool truncated = false;
  };
  bool visible = false, loading = false;
  int purpose = 0;
  fs::path directory;
  Listing current;
  std::future<Listing> pending;
  void refresh() {
    if (loading)
      return;
    loading = true;
    current = {};
    pending = std::async(std::launch::async, [where = directory] {
      Listing result;
      try {
        for (auto &e : fs::directory_iterator(where)) {
          if (result.entries.size() == 1024) {
            result.truncated = true;
            break;
          }
          if (e.is_symlink())
            continue;
          bool dir = e.is_directory();
          if (dir || e.is_regular_file())
            result.entries.push_back({e.path(), dir});
        }
        std::sort(result.entries.begin(), result.entries.end(),
                  [](const Entry &a, const Entry &b) {
                    if (a.directory != b.directory)
                      return a.directory > b.directory;
                    return a.path.filename() < b.path.filename();
                  });
      } catch (const std::exception &e) {
        result.error = e.what();
      }
      return result;
    });
  }
  void open(int type) {
    purpose = type;
    visible = true;
    if (directory.empty()) {
      const char *p = SDL_GetUserFolder(SDL_FOLDER_DOWNLOADS);
      directory = p ? from_utf8(p) : fs::current_path();
    }
    refresh();
  }
  std::optional<fs::path> draw() {
    if (loading && pending.wait_for(std::chrono::seconds(0)) ==
                       std::future_status::ready) {
      current = pending.get();
      loading = false;
    }
    if (!visible)
      return {};
    std::optional<fs::path> result;
    ImGui::OpenPopup("Selecionar arquivo");
    auto screen = ImGui::GetIO().DisplaySize;
    ImGui::SetNextWindowSize(
        ImVec2(std::min(650.f, screen.x - 16), std::min(450.f, screen.y - 16)),
        ImGuiCond_Appearing);
    if (ImGui::BeginPopupModal("Selecionar arquivo", nullptr,
                               ImGuiWindowFlags_NoSavedSettings)) {
      ImGui::TextWrapped("%s", utf8(directory).c_str());
      ImGui::BeginDisabled(loading);
      if (ImGui::Button("Pasta anterior") && directory.has_parent_path()) {
        directory = directory.parent_path();
        refresh();
      }
      ImGui::SameLine();
      if (ImGui::Button("Downloads")) {
        auto *p = SDL_GetUserFolder(SDL_FOLDER_DOWNLOADS);
        if (p) {
          directory = from_utf8(p);
          refresh();
        }
      }
      ImGui::EndDisabled();
      ImGui::SameLine();
      if (ImGui::Button("Cancelar")) {
        visible = false;
        ImGui::CloseCurrentPopup();
      }
      ImGui::TextWrapped(
          "%s", purpose == 0 ? "Escolha sua ROM .gba ou um arquivo .zip."
                : purpose == 1
                    ? "Escolha o manifest.json do pacote de tradução local."
                    : "Escolha um save .khcs exportado pelo aplicativo.");
      if (loading)
        ImGui::TextWrapped("Lendo pasta… Se o sistema pedir permissão, "
                           "responda ao diálogo para concluir a leitura.");
      if (!current.error.empty())
        ImGui::TextWrapped("%s", current.error.c_str());
      if (current.truncated)
        ImGui::TextWrapped("Pasta com mais de 1.024 entradas; use uma subpasta "
                           "para localizar o arquivo.");
      ImGui::BeginChild("arquivos", ImVec2(0, 0), ImGuiChildFlags_Borders);
      for (const auto &e : current.entries) {
        auto ext = e.path.extension().string();
        std::transform(ext.begin(), ext.end(), ext.begin(),
                       [](unsigned char c) { return std::tolower(c); });
        bool allowed =
            e.directory || (purpose == 0   ? (ext == ".gba" || ext == ".zip")
                            : purpose == 1 ? ext == ".json"
                                           : ext == ".khcs");
        if (!allowed)
          continue;
        auto label = (e.directory ? "[Pasta] " : "") + utf8(e.path.filename());
        if (ImGui::Selectable(label.c_str())) {
          if (e.directory) {
            directory = e.path;
            refresh();
            break;
          }
          result = e.path;
          visible = false;
          ImGui::CloseCurrentPopup();
          break;
        }
      }
      ImGui::EndChild();
      ImGui::EndPopup();
    }
    return result;
  }
};
struct CancelTaskOnExit {
  std::atomic<bool> &cancel;
  ~CancelTaskOnExit() { cancel = true; }
};
const char *gba_names[] = {"A",        "B",    "Select", "Start", "Direita",
                           "Esquerda", "Cima", "Baixo",  "R",     "L"};
const char *pad_names[] = {"Sul (A / Cruz)",
                           "Leste (B / Círculo)",
                           "Oeste (X / Quadrado)",
                           "Norte (Y / Triângulo)",
                           "Voltar",
                           "Guia (menu)",
                           "Iniciar",
                           "Analógico esquerdo",
                           "Analógico direito",
                           "Ombro esquerdo",
                           "Ombro direito",
                           "Direcional cima",
                           "Direcional baixo",
                           "Direcional esquerda",
                           "Direcional direita",
                           "Extra 1",
                           "Pá direita1",
                           "Pá esquerda1",
                           "Pá direita2",
                           "Pá esquerda2",
                           "Touchpad",
                           "Extra2",
                           "Extra3",
                           "Extra4",
                           "Extra5",
                           "Extra6"};
struct Options {
  fs::path data, rom, package, report, capture, screenshot;
  unsigned frames = 0, ui_frames = 0;
  bool headless = false, hidden = false, mute = false;
  int filter = -1;
};
Options parse(int argc, char **argv) {
  Options o;
  for (int i = 1; i < argc; ++i) {
    std::string a = argv[i];
    if (a == "--help") {
      std::cout
          << "KHCoM PT-BR desktop (tradução experimental/parcial)\n--data-dir "
             "DIR --rom ORIGINAL.gba|zip --package "
             "manifest.json\n--headless|--hidden --frames N --report FILE "
             "--capture FILE.ppm --screenshot OUTPUT.ppm --ui-frames N "
             "--filter 0|1|2 --mute\nEscape/F1 ou Guia do controle: menu. Sem "
             "savestates na interface.\n";
      std::exit(0);
    }
    if (a == "--headless") {
      o.headless = true;
      continue;
    }
    if (a == "--hidden") {
      o.hidden = true;
      continue;
    }
    if (a == "--mute") {
      o.mute = true;
      continue;
    }
    if (i + 1 >= argc)
      throw std::runtime_error("Opção sem valor: " + a);
    auto v = argv[++i];
    if (a == "--data-dir")
      o.data = from_utf8(v);
    else if (a == "--rom")
      o.rom = from_utf8(v);
    else if (a == "--package")
      o.package = from_utf8(v);
    else if (a == "--report")
      o.report = from_utf8(v);
    else if (a == "--capture")
      o.capture = from_utf8(v);
    else if (a == "--screenshot")
      o.screenshot = from_utf8(v);
    else if (a == "--ui-frames")
      o.ui_frames = std::stoul(v);
    else if (a == "--frames")
      o.frames = std::stoul(v);
    else if (a == "--filter") {
      o.filter = std::stoi(v);
      if (o.filter < 0 || o.filter > 2)
        throw std::runtime_error("Filtro deve ser 0, 1 ou 2.");
    } else
      throw std::runtime_error("Opção desconhecida: " + a);
  }
  if ((o.headless || o.hidden) && !o.frames && !o.ui_frames)
    throw std::runtime_error(
        "Modo sem janela exige --frames para limitar a execução.");
  return o;
}
} // namespace
int main(int argc, char **argv) try {
  auto options = parse(argc, argv);
  if (options.headless) {
    SDL_SetHint(SDL_HINT_VIDEO_DRIVER, "dummy");
    SDL_SetHint(SDL_HINT_AUDIO_DRIVER, "dummy");
  }
  mLogFilter logFilter;
  mLogFilterInit(&logFilter);
  logFilter.defaultLevels = mLOG_ERROR | mLOG_FATAL;
  mLogger logger{};
  logger.filter = &logFilter;
  logger.log = [](mLogger *, int, mLogLevel, const char *, va_list) {};
  mLogSetDefaultLogger(&logger);
  SDLResources s;
  if (!SDL_Init(SDL_INIT_VIDEO | SDL_INIT_AUDIO | SDL_INIT_GAMEPAD))
    throw std::runtime_error(SDL_GetError());
  if (options.data.empty()) {
    auto *p = SDL_GetPrefPath("KHCoM-PTBR", "desktop");
    if (!p)
      throw std::runtime_error(SDL_GetError());
    options.data = from_utf8(p);
    SDL_free(p);
  }
  auto lock = take(StorageLock::acquire(options.data));
  auto loaded = take(load_config(options.data / "config.json"));
  Config config = loaded.config;
  if (options.filter >= 0)
    config.filter = options.filter;
  if (options.mute)
    config.mute = true;
  std::string message = loaded.warning;
  auto recovery = take(recover_owned_temporaries(options.data));
  if (!recovery.retained.empty())
    message = "Há temporários preservados; consulte Dados > Tentar limpeza "
              "novamente.";
  s.window = SDL_CreateWindow(
      "Kingdom Hearts: Corrente de Memórias · PT-BR experimental", 960, 640,
      SDL_WINDOW_RESIZABLE | SDL_WINDOW_HIGH_PIXEL_DENSITY |
          ((options.headless || options.hidden) ? SDL_WINDOW_HIDDEN : 0));
  if (!s.window)
    throw std::runtime_error(SDL_GetError());
  SDL_SetWindowMinimumSize(s.window, 420, 280);
  if (!options.headless)
    s.renderer = SDL_CreateRenderer(s.window, SDL_GPU_RENDERER);
  if (!s.renderer)
    s.renderer = SDL_CreateRenderer(s.window, nullptr);
  if (!s.renderer)
    throw std::runtime_error(SDL_GetError());
  s.texture = SDL_CreateTexture(s.renderer, SDL_PIXELFORMAT_ABGR8888,
                                SDL_TEXTUREACCESS_STREAMING, 240, 160);
  if (!s.texture)
    throw std::runtime_error(SDL_GetError());
  SDL_SetTextureBlendMode(s.texture, SDL_BLENDMODE_NONE);
  IMGUI_CHECKVERSION();
  ImGui::CreateContext();
  auto &io = ImGui::GetIO();
  io.ConfigFlags |=
      ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
  io.IniFilename = nullptr;
  io.LogFilename = nullptr;
  static const ImWchar ui_glyph_ranges[] = {0x20,   0xFF,   0x2013, 0x2014,
                                            0x2026, 0x2026, 0};
  ImFontConfig fc;
  fc.FontDataOwnedByAtlas = false;
  auto *font = io.Fonts->AddFontFromMemoryTTF(
      khcom_ui_font, sizeof(khcom_ui_font), 18, &fc, ui_glyph_ranges);
  io.Fonts->Build();
  for (char32_t cp : U"áéíóúâêôãõçàÁÉÍÓÚÂÊÔÃÕÇÀ…–—")
    if (cp && !font->FindGlyphNoFallback(cp))
      throw std::runtime_error("Fonte da interface não cobre PT-BR.");
  ImGui::StyleColorsDark();
  auto &style = ImGui::GetStyle();
  style.WindowRounding = 10;
  style.FrameRounding = 5;
  style.FramePadding = ImVec2(10, 6);
  style.ItemSpacing = ImVec2(12, 9);
  style.Colors[ImGuiCol_WindowBg] = ImVec4(.045f, .06f, .085f, .97f);
  style.Colors[ImGuiCol_Button] = ImVec4(.12f, .26f, .4f, 1);
  if (!ImGui_ImplSDL3_InitForSDLRenderer(s.window, s.renderer) ||
      !ImGui_ImplSDLRenderer3_Init(s.renderer))
    throw std::runtime_error("Falha na interface SDL.");
  s.imgui = true;
  bool audio_ok = false;
  std::uint64_t audio_bytes = 0, audio_drops = 0;
  int max_audio_queue = 0;
  auto open_audio = [&]() {
    SDL_DestroyAudioStream(s.audio);
    s.audio = nullptr;
    SDL_AudioSpec spec{SDL_AUDIO_S16, 2, 48000};
    s.audio = SDL_OpenAudioDeviceStream(SDL_AUDIO_DEVICE_DEFAULT_PLAYBACK,
                                        &spec, nullptr, nullptr);
    audio_ok = s.audio && SDL_ResumeAudioStreamDevice(s.audio);
    if (!audio_ok)
      message = "Áudio indisponível: " + std::string(SDL_GetError()) +
                ". Use Áudio > Reconectar.";
  };
  open_audio();
  std::string shader_diagnostic, video_warning;
  s.crt = CrtShader::create(s.renderer, shader_diagnostic);
  auto apply_video = [&]() {
    video_warning.clear();
    if (config.filter == 2 && !s.crt) {
      config.filter = 0;
      video_warning = shader_diagnostic + " Fallback: pixels nítidos.";
    }
    if (!SDL_SetRenderVSync(s.renderer, config.vsync ? 1 : 0)) {
      config.vsync = false;
      video_warning +=
          " Vsync indisponível neste backend; a velocidade do jogo "
          "continua controlada pelo relógio GBA.";
    }
    SDL_SetTextureScaleMode(s.texture, config.filter == 1
                                           ? SDL_SCALEMODE_LINEAR
                                           : SDL_SCALEMODE_NEAREST);
    if (!SDL_SetWindowFullscreen(s.window, config.fullscreen)) {
      config.fullscreen = false;
      video_warning += SDL_GetError();
    }
  };
  apply_video();
  auto save_options = [&]() {
    auto r = save_config(options.data / "config.json", config);
    if (auto *e = std::get_if<Error>(&r))
      message = e->message;
  };
  auto refresh_pads = [&]() {
    int count = 0;
    auto *ids = SDL_GetGamepads(&count);
    std::set<SDL_JoystickID> current;
    for (int i = 0; i < count; ++i) {
      current.insert(ids[i]);
      if (!s.pads.contains(ids[i]))
        if (auto *p = SDL_OpenGamepad(ids[i]))
          s.pads[ids[i]] = p;
    }
    SDL_free(ids);
    for (auto it = s.pads.begin(); it != s.pads.end();)
      if (!current.contains(it->first)) {
        SDL_CloseGamepad(it->second);
        it = s.pads.erase(it);
      } else
        ++it;
  };
  refresh_pads();
  Bytes original;
  fs::path original_path = options.rom, package_path = options.package;
  if (package_path.empty()) {
    const char *base = SDL_GetBasePath();
    if (base) {
      auto bundled = from_utf8(base) / "localization" / "manifest.json";
      if (fs::exists(bundled))
        package_path = bundled;
    }
  }
  std::vector<ZipChoice> zip_choices;
  std::unique_ptr<Session> session;
  Json manifest;
  FrameClock clock;
  bool menu = true, running = true, focused = true, save_failed = false;
  Browser browser;
  int remap = -1;
  bool remap_pad = false;
  int session_profile = config.profile;
  std::atomic<bool> cancel = false;
  std::atomic<InstallPhase> install_phase = InstallPhase::validation;
  // Futures join before their cancellation/progress owners are destroyed.
  std::future<Result<Installed>> job;
  std::future<Result<RomImport>> import_job;
  CancelTaskOnExit cancel_on_exit{cancel};
  bool importing = false;
  bool busy = false, quit_after_job = false;
  double saved_at = 0, active_elapsed = 0;
  unsigned presented = 0;
  std::uint64_t core_frames = 0;
  int max_due = 0;
  auto flush_save = [&]() {
    if (!session)
      return true;
    auto raw = session->save();
    if (auto *e = std::get_if<Error>(&raw)) {
      message = e->message;
      return false;
    }
    auto r = store_save(options.data, manifest, session_profile,
                        std::get<Bytes>(raw));
    if (auto *e = std::get_if<Error>(&r)) {
      message = e->message;
      save_failed = true;
      return false;
    }
    save_failed = false;
    return true;
  };
  auto activate = [&](Installed installed, bool flush_current = true,
                      int next_profile = -1) {
    if (flush_current && session && !flush_save())
      return;
    const int selected_profile =
        next_profile < 0 ? config.profile : next_profile;
    auto save =
        take(load_save(options.data, installed.manifest, selected_profile));
    auto next = take(Session::create(std::move(installed.bytes), save));
    session = std::move(next);
    manifest = std::move(installed.manifest);
    config.profile = selected_profile;
    session_profile = selected_profile;
    clock = FrameClock(session->seconds_per_frame());
    if (s.audio)
      SDL_ClearAudioStream(s.audio);
    menu = !video_warning.empty() && !options.hidden && !options.headless;
    message = "Pacote carregado. Tradução experimental/parcial; a maior parte "
              "do jogo ainda está em inglês.";
  };
  auto start_install = [&]() {
    if (original.empty() || package_path.empty() || busy)
      return;
    cancel = false;
    busy = true;
    menu = true;
    job = std::async(
        std::launch::async, [&, rom = original, package = package_path]() {
          return install(options.data, rom, package, &cancel,
                         [&](InstallPhase p) { install_phase = p; });
        });
    message = "Validando origem, patch e destino. A instalação anterior "
              "permanece disponível.";
  };
  auto select_rom = [&](const fs::path &p, int member = -1) {
    if (busy)
      return;
    original_path = p;
    cancel = false;
    busy = true;
    importing = true;
    menu = true;
    import_job = std::async(std::launch::async,
                            [p, member] { return import_rom(p, member); });
    message = "Lendo a ROM local. Se o sistema pedir acesso à pasta, responda "
              "ao diálogo para concluir ou cancelar.";
  };
  if (!original_path.empty())
    select_rom(original_path);
  else if (fs::exists(options.data / "active.json")) {
    auto current = load_active(options.data);
    if (auto *e = std::get_if<Error>(&current))
      message = e->message;
    else
      try {
        activate(std::move(std::get<Installed>(current)));
      } catch (const std::exception &e) {
        message = e.what();
        menu = true;
      }
  }
  auto last = std::chrono::steady_clock::now();
  auto begin = last;
  while (running) {
    auto now = std::chrono::steady_clock::now();
    double elapsed = std::chrono::duration<double>(now - last).count();
    last = now;
    double wall = std::chrono::duration<double>(now - begin).count();
    SDL_Event event;
    while (SDL_PollEvent(&event)) {
      ImGui_ImplSDL3_ProcessEvent(&event);
      if (event.type == SDL_EVENT_QUIT) {
        if (busy) {
          cancel = true;
          quit_after_job = true;
          message = "Cancelando trabalho antes de encerrar…";
        } else if (flush_save())
          running = false;
        else
          menu = true;
      }
      if (event.type == SDL_EVENT_WINDOW_FOCUS_LOST && !options.hidden) {
        focused = false;
        clock.reset();
        if (s.audio)
          SDL_ClearAudioStream(s.audio);
        flush_save();
      }
      if (event.type == SDL_EVENT_WINDOW_FOCUS_GAINED) {
        focused = true;
        clock.reset();
      }
      if (event.type == SDL_EVENT_GAMEPAD_ADDED ||
          event.type == SDL_EVENT_GAMEPAD_REMOVED)
        refresh_pads();
      if (event.type == SDL_EVENT_AUDIO_DEVICE_REMOVED ||
          event.type == SDL_EVENT_AUDIO_DEVICE_ADDED) {
        open_audio();
        if (!audio_ok)
          menu = true;
      }
      if (event.type == SDL_EVENT_KEY_DOWN && !event.key.repeat) {
        int key = event.key.scancode;
        if (remap >= 0 && !remap_pad) {
          if (key == SDL_SCANCODE_ESCAPE)
            remap = -1;
          else if (key == SDL_SCANCODE_F1)
            message = "F1 é reservado ao menu.";
          else {
            auto it =
                std::find(config.keyboard.begin(), config.keyboard.end(), key);
            if (it != config.keyboard.end())
              *it = config.keyboard[remap];
            config.keyboard[remap] = key;
            remap = -1;
            save_options();
          }
        } else if (key == SDL_SCANCODE_ESCAPE || key == SDL_SCANCODE_F1) {
          menu = !menu;
          clock.reset();
          if (s.audio)
            SDL_ClearAudioStream(s.audio);
          if (menu)
            flush_save();
        }
      }
      if (event.type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {
        int button = event.gbutton.button;
        if (button == SDL_GAMEPAD_BUTTON_GUIDE) {
          menu = !menu;
          clock.reset();
          if (s.audio)
            SDL_ClearAudioStream(s.audio);
          if (menu)
            flush_save();
        } else if (remap >= 0 && remap_pad) {
          auto it =
              std::find(config.gamepad.begin(), config.gamepad.end(), button);
          if (it != config.gamepad.end())
            *it = config.gamepad[remap];
          config.gamepad[remap] = button;
          remap = -1;
          save_options();
        }
      }
    }
    if (busy && importing &&
        import_job.wait_for(std::chrono::seconds(0)) ==
            std::future_status::ready) {
      auto result = import_job.get();
      busy = false;
      importing = false;
      if (cancel) {
        message = "Importação cancelada após o término da leitura do sistema.";
      } else if (auto *e = std::get_if<Error>(&result)) {
        message = e->message;
      } else {
        auto imported = std::move(std::get<RomImport>(result));
        zip_choices = std::move(imported.choices);
        if (!imported.bytes.empty()) {
          original = std::move(imported.bytes);
          message = "ROM USA original reconhecida.";
          if (!package_path.empty() && !quit_after_job)
            start_install();
        }
      }
    }
    if (busy && !importing &&
        job.wait_for(std::chrono::seconds(0)) == std::future_status::ready) {
      auto result = job.get();
      busy = false;
      if (auto *e = std::get_if<Error>(&result))
        message = e->message;
      else
        try {
          activate(std::move(std::get<Installed>(result)));
        } catch (const std::exception &e) {
          message = e.what();
          menu = true;
        }
    }
    if (quit_after_job && !busy) {
      if (flush_save())
        running = false;
      else {
        menu = true;
        quit_after_job = false;
      }
    }
    if (options.ui_frames)
      menu = true;
    bool paused = menu || !focused || busy || !session;
    if (!paused && elapsed <= .25)
      active_elapsed += elapsed;
    auto due = clock.due(elapsed, paused);
    auto *keys = SDL_GetKeyboardState(nullptr);
    std::uint16_t mask = 0;
    if (!paused) {
      for (int i = 0; i < 10; ++i) {
        if (keys[config.keyboard[i]])
          mask |= 1 << i;
        for (auto &[_, pad] : s.pads)
          if (SDL_GetGamepadButton(pad, SDL_GamepadButton(config.gamepad[i])))
            mask |= 1 << i;
      }
      for (auto &[_, pad] : s.pads) {
        auto x = SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTX),
             y = SDL_GetGamepadAxis(pad, SDL_GAMEPAD_AXIS_LEFTY);
        if (x > config.deadzone)
          mask |= 16;
        if (x < -config.deadzone)
          mask |= 32;
        if (y < -config.deadzone)
          mask |= 64;
        if (y > config.deadzone)
          mask |= 128;
      }
    }
    if (options.frames)
      due = std::min<std::uint64_t>(due, options.frames - core_frames);
    unsigned advanced = 0;
    for (unsigned n = 0; n < due; ++n) {
      auto r = session->advance(mask);
      if (auto *e = std::get_if<Error>(&r)) {
        message = e->message;
        menu = true;
        break;
      }
      ++core_frames;
      ++advanced;
      if (s.audio && audio_ok) {
        auto samples = session->audio_frame();
        int queued = SDL_GetAudioStreamQueued(s.audio);
        max_audio_queue = std::max(max_audio_queue, queued);
        if (queued > 48000) {
          SDL_ClearAudioStream(s.audio);
          ++audio_drops;
        }
        SDL_SetAudioStreamGain(s.audio,
                               config.mute ? 0 : config.volume / 100.f);
        if (!SDL_PutAudioStreamData(s.audio, samples.data(),
                                    samples.size_bytes())) {
          audio_ok = false;
          message = "Falha no áudio: " + std::string(SDL_GetError());
        }
        audio_bytes += samples.size_bytes();
      }
    }
    max_due = std::max(max_due, int(advanced));
    if (paused && s.audio)
      SDL_ClearAudioStream(s.audio);
    if (session && wall - saved_at >= 5) {
      if (!flush_save())
        menu = true;
      saved_at = wall;
    }
    int pw = 0, ph = 0;
    SDL_GetRenderOutputSize(s.renderer, &pw, &ph);
    auto vp = viewport(pw, ph, config);
    SDL_SetRenderDrawColor(s.renderer, 5, 7, 10, 255);
    SDL_RenderClear(s.renderer);
    if (session && vp.fits) {
      SDL_UpdateTexture(s.texture, nullptr, session->pixels().data(), 960);
      SDL_FRect rect{float(vp.x), float(vp.y), float(vp.width),
                     float(vp.height)};
      if (config.filter == 2 && s.crt && !s.crt->enable()) {
        video_warning = "Falha no shader: " + std::string(SDL_GetError());
        config.filter = 0;
      }
      SDL_RenderTexture(s.renderer, s.texture, nullptr, &rect);
      if (s.crt)
        s.crt->disable();
    } else if (session && !vp.fits)
      menu = true;
    ImGui_ImplSDLRenderer3_NewFrame();
    ImGui_ImplSDL3_NewFrame();
    ImGui::NewFrame();
    if (menu || !session || busy) {
      auto display = io.DisplaySize;
      ImGui::SetNextWindowPos(ImVec2(display.x * .5f, display.y * .5f),
                              ImGuiCond_Always, ImVec2(.5f, .5f));
      ImGui::SetNextWindowSize(ImVec2(std::min(790.f, display.x - 16),
                                      std::min(580.f, display.y - 16)),
                               ImGuiCond_Always);
      ImGui::Begin("Kingdom Hearts: Corrente de Memórias · PT-BR", nullptr,
                   ImGuiWindowFlags_NoCollapse |
                       ImGuiWindowFlags_NoSavedSettings);
      ImGui::TextColored(ImVec4(.45f, .8f, 1, 1),
                         "Tradução experimental e parcial");
      ImGui::TextWrapped("O jogo completo ainda não está traduzido. Escape/F1 "
                         "ou botão Guia abre este menu.");
      if (!message.empty())
        ImGui::TextWrapped("%s", message.c_str());
      if (!video_warning.empty()) {
        ImGui::PushTextWrapPos(0);
        ImGui::TextColored(ImVec4(1, .75f, .35f, 1), "%s",
                           video_warning.c_str());
        ImGui::PopTextWrapPos();
      }
      if (!vp.fits)
        ImGui::TextColored(ImVec4(1, .7f, .3f, 1),
                           "A escala não cabe na área física. Selecione "
                           "Ajustar ou aumente a janela.");
      if (busy) {
        const char *phases[] = {
            "Validando ROM original…", "Verificando pacote BPS…",
            "Preparando cache local…", "Ativando pacote…", "Concluído"};
        ImGui::TextUnformatted(importing ? "Lendo arquivo local…"
                                         : phases[int(install_phase.load())]);
        if (ImGui::Button("Cancelar operação"))
          cancel = true;
      }
      ImGui::BeginDisabled(busy);
      if (ImGui::BeginTabBar("opcoes")) {
        if (ImGui::BeginTabItem("Jogo")) {
          if (session && ImGui::Button("Continuar jogo", ImVec2(240, 0))) {
            menu = false;
            clock.reset();
          }
          if (ImGui::Button("Importar minha ROM…"))
            browser.open(0);
          ImGui::SameLine();
          ImGui::TextUnformatted(original.empty() ? "Não selecionada"
                                                  : "Original validada");
          if (ImGui::Button("Selecionar pacote PT-BR…"))
            browser.open(1);
          if (!package_path.empty())
            ImGui::TextWrapped("Pacote: %s",
                               utf8(package_path.filename()).c_str());
          if (!original.empty() && !package_path.empty() &&
              ImGui::Button("Aplicar pacote e jogar"))
            start_install();
          if (!zip_choices.empty()) {
            ImGui::TextUnformatted(
                "Este ZIP contém várias ROMs. Escolha explicitamente:");
            for (auto &choice : zip_choices)
              if (ImGui::Button(choice.name.c_str())) {
                try {
                  select_rom(original_path, choice.index);
                } catch (const std::exception &e) {
                  message = e.what();
                }
                break;
              }
          }
          if (session && ImGui::Button("Reiniciar jogo")) {
            if (flush_save())
              try {
                activate(take(load_active(options.data)));
              } catch (const std::exception &e) {
                message = e.what();
              }
          }
          if (ImGui::Button("Sair")) {
            if (flush_save())
              running = false;
          }
          ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Vídeo")) {
          bool changed = false;
          changed |= ImGui::Checkbox("Ajustar com escala inteira", &config.fit);
          changed |= ImGui::Checkbox(
              "Esticar para preencher (altera proporção)", &config.stretch);
          ImGui::BeginDisabled(config.fit || config.stretch);
          changed |=
              ImGui::SliderInt("Escala física", &config.scale, 1, 6, "%dx");
          ImGui::EndDisabled();
          changed |= ImGui::Checkbox("Tela cheia", &config.fullscreen);
          changed |= ImGui::Checkbox("Vsync", &config.vsync);
          const char *filters[] = {"Pixels nítidos", "Suave (linear)",
                                   "CRT (shader)"};
          changed |= ImGui::Combo("Filtro", &config.filter, filters, 3);
          ImGui::Text("Saída: %d × %d pixels físicos | jogo: %d × %d", pw, ph,
                      vp.width, vp.height);
          ImGui::TextWrapped("Original: 240 × 160, proporção 3:2. As escalas "
                             "1x–6x usam pixels físicos inclusive em telas "
                             "Retina. Nenhuma escala é cortada para caber.");
          if (changed) {
            apply_video();
            save_options();
          }
          ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Áudio")) {
          bool changed =
              ImGui::SliderInt("Volume", &config.volume, 0, 100, "%d%%");
          changed |= ImGui::Checkbox("Silenciar", &config.mute);
          if (changed)
            save_options();
          ImGui::Text("Saída estéreo 48 kHz: %s",
                      audio_ok ? "conectada" : "indisponível");
          if (ImGui::Button("Reconectar áudio"))
            open_audio();
          ImGui::TextWrapped("O áudio pausa junto do jogo e é limpo ao perder "
                             "foco ou retornar de uma suspensão.");
          ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Controles")) {
          ImGui::Text("Controles conectados: %d", int(s.pads.size()));
          ImGui::TextWrapped(
              "Escolha um botão para remapear. Conflitos trocam as duas "
              "funções. Escape/F1 e Guia ficam reservados ao menu. Setas/Tab "
              "navegam; Enter confirma.");
          if (remap >= 0) {
            ImGui::Text("Aguardando %s para %s…",
                        remap_pad ? "botão do controle" : "tecla",
                        gba_names[remap]);
            if (ImGui::Button("Cancelar remapeamento"))
              remap = -1;
          }
          if (ImGui::BeginTable("mapa", 3,
                                ImGuiTableFlags_Borders |
                                    ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("GBA");
            ImGui::TableSetupColumn("Teclado");
            ImGui::TableSetupColumn("Controle");
            ImGui::TableHeadersRow();
            for (int i = 0; i < 10; ++i) {
              ImGui::PushID(i);
              ImGui::TableNextRow();
              ImGui::TableNextColumn();
              ImGui::TextUnformatted(gba_names[i]);
              ImGui::TableNextColumn();
              if (ImGui::Button(
                      SDL_GetScancodeName(SDL_Scancode(config.keyboard[i])))) {
                remap = i;
                remap_pad = false;
              }
              ImGui::TableNextColumn();
              if (ImGui::Button(pad_names[config.gamepad[i]])) {
                remap = i;
                remap_pad = true;
              }
              ImGui::PopID();
            }
            ImGui::EndTable();
          }
          if (ImGui::SliderInt("Zona morta analógica", &config.deadzone, 2000,
                               24000))
            save_options();
          ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Dados")) {
          ImGui::TextWrapped(
              "Saves de cartucho são gravados a cada 5 segundos e ao "
              "pausar/sair, com backup da versão anterior. Use também o save "
              "do próprio jogo. Savestates não são oferecidos nesta versão.");
          int profile = config.profile;
          const char *profiles[] = {"Perfil 1", "Perfil 2", "Perfil 3"};
          if (ImGui::Combo("Perfil", &profile, profiles, 3)) {
            try {
              if (session) {
                activate(take(load_active(options.data)), true, profile);
                menu = true;
              } else
                config.profile = profile;
              save_options();
            } catch (const std::exception &e) {
              message = e.what();
            }
          }
          if (session) {
            if (ImGui::Button("Exportar save")) {
              try {
                auto dir = options.data / "exports";
                fs::create_directories(dir);
                auto dest =
                    dir / ("perfil-" + std::to_string(config.profile + 1) +
                           "-" + std::to_string(SDL_GetTicks()) + ".khcs");
                take(export_save(dest, manifest, take(session->save())));
                message = "Save exportado: " + utf8(dest);
              } catch (const std::exception &e) {
                message = e.what();
              }
            }
            ImGui::SameLine();
            if (ImGui::Button("Importar save…"))
              browser.open(2);
          }
          if (fs::exists(options.data / "active.json") &&
              ImGui::Button("Restaurar backup do save")) {
            try {
              auto installed = take(load_active(options.data));
              take(restore_save_backup(options.data, installed.manifest,
                                       config.profile));
              session.reset(); // Recovery replaces the persisted generation
                               // before restart.
              activate(std::move(installed), false);
              menu = true;
              save_failed = false;
              message = "Backup restaurado. O save substituído foi preservado "
                        "separadamente.";
            } catch (const std::exception &e) {
              message = e.what();
            }
          }
          if (fs::exists(options.data / "active.json") &&
              ImGui::Button("Voltar ao pacote anterior")) {
            try {
              if (flush_save()) {
                take(rollback(options.data));
                activate(take(load_active(options.data)));
                menu = true;
              }
            } catch (const std::exception &e) {
              message = e.what();
            }
          }
          if (ImGui::Button("Tentar limpeza novamente")) {
            auto result = recover_owned_temporaries(options.data);
            if (auto *e = std::get_if<Error>(&result))
              message = e->message;
            else {
              recovery = std::get<TemporaryRecovery>(std::move(result));
              message = "Temporários removidos: " +
                        std::to_string(recovery.recovered) +
                        "; registros pendentes: " +
                        std::to_string(recovery.retained.size());
            }
          }
          for (auto &entry : recovery.retained)
            ImGui::TextWrapped("%s", entry.c_str());
          if (ImGui::Button("Restaurar configurações padrão")) {
            int profile = config.profile;
            config = Config{};
            config.profile = profile;
            apply_video();
            save_options();
            message = "Padrões restaurados. Saves e perfis mantidos.";
          }
          ImGui::TextWrapped("Pasta de dados: %s", utf8(options.data).c_str());
          if (save_failed)
            ImGui::TextWrapped("O save ainda está em memória. Resolva o erro e "
                               "tente salvar/sair novamente.");
          ImGui::EndTabItem();
        }
        if (ImGui::BeginTabItem("Sobre")) {
          ImGui::TextUnformatted("KHCoM PT-BR · aplicativo em desenvolvimento");
          ImGui::TextWrapped(
              "A ROM é fornecida por você e permanece intacta. A tradução é "
              "aplicada localmente por BPS. Não há download de ROM, BIOS ou "
              "dados do jogo. Multiplayer ainda não está disponível.");
          ImGui::Text("Core mGBA %s | %s", Session::core_version(),
                      SDL_GetRevision());
          ImGui::TextWrapped(
              "Interface: Dear ImGui(MIT), JSON(MIT), miniz(MIT), Droid "
              "Sans(Apache2.0). Avisos completos acompanham a distribuição.");
          if (session && manifest.contains("description"))
            ImGui::TextWrapped(
                "%s", manifest["description"].get<std::string>().c_str());
          ImGui::EndTabItem();
        }
        ImGui::EndTabBar();
      }
      ImGui::EndDisabled();
      ImGui::End();
    }
    if (auto selected = browser.draw())
      try {
        if (browser.purpose == 0)
          select_rom(*selected);
        else if (browser.purpose == 1) {
          package_path = *selected;
          if (!original.empty())
            start_install();
        } else if (session) {
          auto imported = take(import_save(*selected, manifest));
          if (flush_save()) {
            take(store_save(options.data, manifest, session_profile, imported));
            activate(take(load_active(options.data)), false);
            menu = true;
            message = "Save importado com backup do anterior.";
          }
        }
      } catch (const std::exception &e) {
        message = e.what();
      }
    ImGui::Render();
    ImGui_ImplSDLRenderer3_RenderDrawData(ImGui::GetDrawData(), s.renderer);
    bool final_frame =
        (options.frames && core_frames >= options.frames) ||
        (options.ui_frames && presented + 1 >= options.ui_frames);
    if (final_frame && !options.screenshot.empty()) {
      auto *surface = SDL_RenderReadPixels(s.renderer, nullptr);
      if (!surface)
        throw std::runtime_error(SDL_GetError());
      auto *rgb = SDL_ConvertSurface(surface, SDL_PIXELFORMAT_RGB24);
      SDL_DestroySurface(surface);
      if (!rgb)
        throw std::runtime_error(SDL_GetError());
      auto output = text_bytes("P6\n" + std::to_string(rgb->w) + " " +
                               std::to_string(rgb->h) + "\n255\n");
      for (int y = 0; y < rgb->h; ++y) {
        auto *row = static_cast<unsigned char *>(rgb->pixels) + y * rgb->pitch;
        output.insert(output.end(), row, row + rgb->w * 3);
      }
      SDL_DestroySurface(rgb);
      take(atomic_write(options.screenshot, output, false));
    }
    SDL_RenderPresent(s.renderer);
    ++presented;
    if (final_frame)
      running = false;
    if (options.frames && core_frames >= options.frames)
      running = false;
    if (options.headless && !options.ui_frames && !busy && !session)
      throw std::runtime_error(
          message.empty() ? "Nenhuma instalação disponível." : message);
    if ((options.headless || options.hidden) &&
        wall > (options.frames + options.ui_frames) / 50.0 + 30)
      throw std::runtime_error("Execução de teste excedeu tempo limite.");
    SDL_Delay(config.vsync ? 1 : 2);
  }
  cancel = true;
  if (busy) {
    if (importing)
      import_job.wait();
    else
      job.wait();
  }
  flush_save();
  save_options();
  if (!options.capture.empty() && session) {
    auto head = text_bytes("P6\n240 160\n255\n");
    for (auto p : session->pixels())
      for (int shift : {0, 8, 16})
        head.push_back(p >> shift);
    take(atomic_write(options.capture, head, false));
  }
  if (!options.report.empty()) {
    int pw, ph;
    SDL_GetRenderOutputSize(s.renderer, &pw, &ph);
    auto vp = viewport(pw, ph, config);
    Json report = {
        {"schema_version", 1},
        {"core_version", Session::core_version()},
        {"sdl_revision", SDL_GetRevision()},
        {"simulated_frames", core_frames},
        {"presented_frames", presented},
        {"elapsed_seconds",
         std::chrono::duration<double>(std::chrono::steady_clock::now() - begin)
             .count()},
        {"frame_period", clock.period()},
        {"max_frames_per_present", max_due},
        {"suspended_gaps", clock.suspended_gaps()},
        {"audio_submitted_bytes", audio_bytes},
        {"audio_queue_peak_bytes", max_audio_queue},
        {"audio_queue_resets", audio_drops},
        {"audio_device_opened", audio_ok},
        {"headless_dummy_devices", options.headless},
        {"hidden_hardware_window", options.hidden},
        {"renderer", SDL_GetRendererName(s.renderer)},
        {"shader_available", bool(s.crt)},
        {"selected_filter", config.filter},
        {"video_warning", video_warning},
        {"active_wall_seconds", active_elapsed},
        {"simulated_seconds", core_frames * clock.period()},
        {"audio_nonzero_samples", session ? session->audio().nonzero : 0},
        {"ui_ptbr_glyphs_present", true},
        {"physical_output", {pw, ph}},
        {"game_viewport", {vp.x, vp.y, vp.width, vp.height}},
        {"save_error", save_failed},
        {"translation_complete", false}};
    if (session)
      report["target_sha256"] = sha256(session->rom());
    take(atomic_write(options.report, text_bytes(report.dump(2)), false));
  }
  mLogSetDefaultLogger(nullptr);
  mLogFilterDeinit(&logFilter);
  return save_failed ? 1 : 0;
} catch (const std::exception &e) {
  std::cerr << "KHCoM: " << e.what() << '\n';
  return 1;
}
