#include "core/session.hpp"
#include "core/sha256.hpp"
#include "platform/sdl_preview.hpp"
#include <charconv>
#include <chrono>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <map>
#include <sstream>
#include <thread>
#include <mgba/core/log.h>
#include <SDL3/SDL_main.h>

namespace fs = std::filesystem;
using khcom::Error;
template<class T> using Result = khcom::Result<T>;
namespace {
constexpr const char* original_sha256="6f6e7b61bb7b6ef7e2bea6e9dd01e70570a715835cc3713abe86186fd2c4e28d";
struct LogStats {
  std::uint64_t total=0, emitted=0, warning_or_error=0, game_error=0;
  std::vector<std::string> game_error_examples;
} logs;
struct Options {
  fs::path rom, output, trace, save, checkpoint;
  std::string expected=original_sha256;
  unsigned frames=600, capture=0, scale=3;
  bool preview=false, realtime=false, checkpoint_out=false;
};
std::string path_text(const fs::path& path) {
  const auto utf8=path.u8string();return {utf8.begin(),utf8.end()};
}
std::string quote(std::string_view input) {
  std::ostringstream out;out<<'"';
  for(unsigned char c:input) {
    if(c=='"'||c=='\\') out<<'\\'<<c;
    else if(c<32) out<<"\\u"<<std::hex<<std::setw(4)<<std::setfill('0')<<static_cast<unsigned>(c);
    else out<<c;
  }
  out<<'"';return out.str();
}
int fail(const Error& e) {
  std::cerr<<"{\"ok\":false,\"error\":{\"code\":"<<quote(e.code)<<",\"message\":"<<quote(e.message)<<"}}\n";
  return 1;
}
Result<unsigned> number(std::string_view value) {
  unsigned result=0;auto [p,ec]=std::from_chars(value.data(),value.data()+value.size(),result);
  if(ec!=std::errc{}||p!=value.data()+value.size()) return Error{"invalid_number","Número decimal inválido: "+std::string(value)};
  return result;
}
Result<Options> parse(int argc,char** argv) {
  Options o;
  for(int i=1;i<argc;++i) {
    std::string name=argv[i];
    if(name=="--preview") {o.preview=true;continue;}
    if(name=="--realtime") {o.realtime=true;continue;}
    if(name=="--checkpoint-out") {o.checkpoint_out=true;continue;}
    if(i+1==argc) return Error{"missing_argument","Valor ausente: "+name};
    std::string value=argv[++i];
    if(name=="--rom") o.rom=fs::u8path(value);
    else if(name=="--output-dir") o.output=fs::u8path(value);
    else if(name=="--input-trace") o.trace=fs::u8path(value);
    else if(name=="--save-in") o.save=fs::u8path(value);
    else if(name=="--checkpoint-in") o.checkpoint=fs::u8path(value);
    else if(name=="--expect-sha256") o.expected=value;
    else if(name=="--frames"||name=="--capture-every"||name=="--scale") {
      auto n=number(value);if(auto* e=std::get_if<Error>(&n)) return *e;
      if(name=="--frames") o.frames=std::get<unsigned>(n);
      else if(name=="--capture-every") o.capture=std::get<unsigned>(n);
      else o.scale=std::get<unsigned>(n);
    } else return Error{"unknown_argument","Opção desconhecida: "+name};
  }
  if(o.rom.empty()||o.output.empty()) return Error{"missing_argument","Informe --rom e --output-dir."};
  if(!o.checkpoint.empty()&&o.save.empty()) return Error{"checkpoint_save_required","Checkpoint exige --save-in do mesmo ponto; não substitui o save de cartucho."};
  if(o.frames==0||o.frames>10'000'000) return Error{"invalid_frames","Informe entre 1 e 10000000 frames por execução."};
  constexpr std::uint64_t capture_bytes=240*160*3+15;
  if(o.capture&&std::uint64_t((o.frames-1)/o.capture+1)*capture_bytes>1024ULL*1024*1024)
    return Error{"capture_capacity","Capturas excedem o orçamento de 1 GiB por execução; aumente --capture-every ou reduza --frames."};
  if(o.scale<1||o.scale>6) return Error{"invalid_scale","Escala deve estar entre 1 e 6."};
  if(o.expected.size()!=64||o.expected.find_first_not_of("0123456789abcdef")!=std::string::npos)
    return Error{"invalid_digest","SHA-256 deve conter 64 dígitos hexadecimais minúsculos."};
  return o;
}
Result<std::vector<std::uint8_t>> read(const fs::path& path,std::size_t maximum) {
  std::error_code ec;auto size=fs::file_size(path,ec);
  if(ec) return Error{"input_stat",path_text(path)+": "+ec.message()};
  if(size>maximum) return Error{"input_capacity","Arquivo excede capacidade admitida: "+path_text(path)};
  std::ifstream in(path,std::ios::binary);
  if(!in) return Error{"input_open","Não foi possível abrir "+path_text(path)};
  std::vector<std::uint8_t> bytes(size);
  if(size&&!in.read(reinterpret_cast<char*>(bytes.data()),static_cast<std::streamsize>(size)))
    return Error{"input_read","Leitura incompleta de "+path_text(path)};
  if(in.peek()!=std::char_traits<char>::eof()) return Error{"input_changed","Arquivo mudou durante a leitura."};
  return bytes;
}
using Trace=std::map<unsigned,std::uint16_t>;
Result<Trace> trace(const fs::path& path,unsigned frames) {
  Trace result;if(path.empty()) return result;
  auto data=read(path,1024*1024);if(auto* e=std::get_if<Error>(&data)) return *e;
  const auto& b=std::get<std::vector<std::uint8_t>>(data);
  std::istringstream in(std::string(b.begin(),b.end()));std::string line;unsigned row=0;
  while(std::getline(in,line)) {
    ++row;if(!line.empty()&&line.back()=='\r') line.pop_back();
    if(line.empty()||line[0]=='#'||(row==1&&line=="frame,keys")) continue;
    auto comma=line.find(',');
    if(comma==std::string::npos) return Error{"trace_format","Trace deve conter frame,keys na linha "+std::to_string(row)};
    auto f=number(std::string_view(line).substr(0,comma));auto k=number(std::string_view(line).substr(comma+1));
    if(auto* e=std::get_if<Error>(&f)) return *e;if(auto* e=std::get_if<Error>(&k)) return *e;
    auto frame=std::get<unsigned>(f),keys=std::get<unsigned>(k);
    if(frame>=frames||keys>1023||!result.emplace(frame,keys).second)
      return Error{"trace_range","Frame duplicado/fora da execução ou máscara inválida na linha "+std::to_string(row)};
  }
  return result;
}
Result<khcom::Success> write(const fs::path& path,std::span<const std::uint8_t> bytes) {
  std::ofstream out(path,std::ios::binary);
  if(!out) return Error{"output_open","Não foi possível criar "+path_text(path)};
  out.write(reinterpret_cast<const char*>(bytes.data()),static_cast<std::streamsize>(bytes.size()));out.close();
  if(!out) return Error{"output_write","Gravação incompleta de "+path_text(path)};
  return khcom::Success{};
}
Result<khcom::Success> text_file(const fs::path& path,const std::string& s) {
  return write(path,{reinterpret_cast<const std::uint8_t*>(s.data()),s.size()});
}
std::string framebuffer_hash(const khcom::Session& s) {
  // Canonical RGB bytes, independent of host endianness and unused alpha bits.
  std::vector<std::uint8_t> bytes;bytes.reserve(240*160*3);
  for(auto p:s.pixels()) for(int shift:{0,8,16}) bytes.push_back(static_cast<std::uint8_t>(p>>shift));
  return khcom::sha256(bytes);
}
Result<khcom::Success> capture(const fs::path& dir,unsigned frame,const khcom::Session& s) {
  const std::string header="P6\n240 160\n255\n";
  std::vector<std::uint8_t> bytes(header.begin(),header.end());bytes.reserve(header.size()+240*160*3);
  for(auto p:s.pixels()) for(int shift:{0,8,16}) bytes.push_back(static_cast<std::uint8_t>(p>>shift));
  return write(dir/("frame-"+std::to_string(frame)+".ppm"),bytes);
}
const char* platform() {
#if defined(__APPLE__)
  return "macOS";
#elif defined(_WIN32)
  return "Windows";
#else
  return "other";
#endif
}
const char* arch() {
#if defined(__aarch64__) || defined(_M_ARM64)
  return "arm64";
#elif defined(__x86_64__) || defined(_M_X64)
  return "x86_64";
#else
  return "other";
#endif
}
int run(int argc,char** argv) {
  static mLogger logger{[](mLogger*,int category,mLogLevel level,const char* format,va_list args) {
    ++logs.total;
    if(level==mLOG_GAME_ERROR) {
      ++logs.game_error;
      if(logs.game_error_examples.size()<8) {
        char message[512];std::vsnprintf(message,sizeof(message),format,args);
        logs.game_error_examples.push_back(std::string(mLogCategoryName(category))+": "+message);
      }
      return;
    }
    if(!(level&(mLOG_WARN|mLOG_ERROR|mLOG_FATAL))) return;
    ++logs.warning_or_error;
    if(logs.emitted>=200) return;
    ++logs.emitted;
    std::fprintf(stderr,"mGBA[%s]: ",mLogCategoryName(category));std::vfprintf(stderr,format,args);std::fputc('\n',stderr);
  },nullptr};
  mLogSetDefaultLogger(&logger);
  if(argc==2&&std::string_view(argv[1])=="--help") {
    std::cout<<"KHCoM M1 diagnostic; inspect supplied ROM translation separately; no release packaging.\n"
      "--rom FILE --output-dir NEW_DIRECTORY [--frames 600] [--input-trace CSV]\n"
      "[--save-in FILE] [--capture-every N] [--preview] [--scale 1..6] [--realtime]\n"
      "[--checkpoint-out] [--checkpoint-in FILE (requires matching --save-in)]\n"
      "[--expect-sha256 DIGEST] (default: original USA B8CE revision 0)\n"
      "Trace: frame,keys decimal, zero-based frame before execution. Masks:\n"
      "A=1 B=2 Select=4 Start=8 Right=16 Left=32 Up=64 Down=128 R=256 L=512.\n";
    return 0;
  }
  auto options=parse(argc,argv);if(auto* e=std::get_if<Error>(&options)) return fail(*e);
  const auto o=std::get<Options>(options);
  auto bytes=read(o.rom,32*1024*1024);if(auto* e=std::get_if<Error>(&bytes)) return fail(*e);
  auto rom=std::move(std::get<std::vector<std::uint8_t>>(bytes));const auto source_hash=khcom::sha256(rom);
  if(source_hash!=o.expected) return fail({"rom_identity","SHA-256 da ROM difere da identidade selecionada."});
  auto inputs=trace(o.trace,o.frames);if(auto* e=std::get_if<Error>(&inputs)) return fail(*e);
  std::vector<std::uint8_t> save;
  if(!o.save.empty()) {auto r=read(o.save,128*1024);if(auto* e=std::get_if<Error>(&r)) return fail(*e);save=std::move(std::get<std::vector<std::uint8_t>>(r));}
  auto created=khcom::Session::create(std::move(rom),save);if(auto* e=std::get_if<Error>(&created)) return fail(*e);
  auto session=std::move(std::get<std::unique_ptr<khcom::Session>>(created));
  if(!o.checkpoint.empty()) {
    auto c=read(o.checkpoint,2*1024*1024);if(auto* e=std::get_if<Error>(&c)) return fail(*e);
    auto r=session->restore_checkpoint(std::get<std::vector<std::uint8_t>>(c));if(auto* e=std::get_if<Error>(&r)) return fail(*e);
  }
  const auto initial_core_frame_count=session->frames();
  std::error_code ec;
  if(!fs::create_directory(o.output,ec)) return fail({"output_directory","Destino deve ser uma pasta nova com pai existente: "+path_text(o.output)+" ("+ec.message()+")"});
  std::unique_ptr<khcom::Preview> preview;
  if(o.preview) {auto p=khcom::Preview::create(o.scale);if(auto* e=std::get_if<Error>(&p)) return fail(*e);preview=std::move(std::get<std::unique_ptr<khcom::Preview>>(p));}
  const auto& keys_by_frame=std::get<Trace>(inputs);std::ostringstream normalized;normalized<<"frame,keys\n";
  for(const auto& [frame,keys]:keys_by_frame) normalized<<frame<<','<<keys<<'\n';
  auto w=text_file(o.output/"input.csv",normalized.str());if(auto* e=std::get_if<Error>(&w)) return fail(*e);
  std::ofstream samples(o.output/"samples.csv");
  if(!samples) return fail({"output_open","Não foi possível criar samples.csv."});
  samples<<"frame,keys,framebuffer_sha256,save_backend,save_bytes,audio_samples,audio_nonzero\n";
  const auto start=std::chrono::steady_clock::now();unsigned completed=0;std::uint16_t keys=0;bool closed=false;
  for(unsigned frame=0;frame<o.frames;++frame) {
    if(auto it=keys_by_frame.find(frame);it!=keys_by_frame.end()) keys=it->second;
    auto step=session->advance(keys);if(auto* e=std::get_if<Error>(&step)) return fail(*e);++completed;
    if(completed%60==0||completed==o.frames) {
      auto info=session->save_info();samples<<completed<<','<<keys<<','<<framebuffer_hash(*session)<<','<<info.backend<<','<<info.size<<','<<session->audio().samples<<','<<session->audio().nonzero<<'\n';
    }
    if(o.capture&&(completed%o.capture==0||completed==o.frames)) {auto c=capture(o.output,completed,*session);if(auto* e=std::get_if<Error>(&c)) return fail(*e);}
    if(preview) {auto p=preview->present(session->pixels());if(auto* e=std::get_if<Error>(&p)) return fail(*e);if(!std::get<bool>(p)) {closed=true;break;}}
    if(o.realtime) std::this_thread::sleep_until(start+std::chrono::duration<double>(completed*280896.0/16777216.0));
  }
  const auto seconds=std::chrono::duration<double>(std::chrono::steady_clock::now()-start).count();samples.close();
  if(!samples) return fail({"output_write","Gravação incompleta de samples.csv."});
  auto snapshot=session->save();if(auto* e=std::get_if<Error>(&snapshot)) return fail(*e);
  const auto& saved=std::get<std::vector<std::uint8_t>>(snapshot);
  if(!saved.empty()) {auto r=write(o.output/"cartridge.sav",saved);if(auto* e=std::get_if<Error>(&r)) return fail(*e);}
  if(o.checkpoint_out) {
    auto c=session->checkpoint();if(auto* e=std::get_if<Error>(&c)) return fail(*e);
    auto r=write(o.output/"checkpoint.bin",std::get<std::vector<std::uint8_t>>(c));if(auto* e=std::get_if<Error>(&r)) return fail(*e);
  }
  const auto info=session->save_info();const auto& a=session->audio();std::ostringstream report;
  report<<std::boolalpha<<"{\n  \"schema_version\": 1,\n  \"ok\": true,\n  \"kind\": \"runtime_diagnostic\",\n"
    "  \"harness_version\": "<<quote(KHCOM_DIAGNOSTIC_VERSION)<<",\n  \"core_version\": "<<quote(session->core_version())
    <<",\n  \"platform\": "<<quote(platform())<<",\n  \"arch\": "<<quote(arch())
    <<",\n  \"bios\": \"mGBA built-in substitute; startup skipped; no external BIOS\",\n  \"source_sha256\": "<<quote(source_hash)
    <<",\n  \"inputs\": {\"rom_path\": "<<quote(path_text(o.rom))<<", \"trace_path\": "<<quote(path_text(o.trace))<<", \"save_path\": "<<quote(path_text(o.save))<<", \"output_directory\": "<<quote(path_text(o.output))<<"}"
    <<",\n  \"rom_memory_unchanged\": "<<(khcom::sha256(session->rom())==source_hash)
    <<",\n  \"diagnostic_checkpoint\": {\"loaded\": "<<!o.checkpoint.empty()<<", \"input_path\": "<<quote(path_text(o.checkpoint))<<", \"written\": "<<o.checkpoint_out<<", \"initial_core_frame_count\": "<<initial_core_frame_count<<", \"in_game_save_evidence\": false}"
    <<",\n  \"frames_requested\": "<<o.frames<<",\n  \"frames_executed\": "<<completed<<",\n  \"core_frame_count\": "<<session->frames()
    <<",\n  \"user_closed_window\": "<<closed<<",\n  \"wall_seconds\": "<<seconds<<",\n  \"wall_seconds_scope\": \"emulation loop including capture and pacing; excludes startup and final report\",\n  \"realtime_requested\": "<<o.realtime
    <<",\n  \"framebuffer_sha256\": "<<quote(framebuffer_hash(*session))
    <<",\n  \"save\": {\"backend\": "<<quote(info.backend)<<", \"size\": "<<saved.size()<<", \"sha256\": "<<quote(khcom::sha256(saved))<<", \"loaded_input\": "<<!o.save.empty()<<"},\n"
    "  \"audio\": {\"samples\": "<<a.samples<<", \"nonzero\": "<<a.nonzero<<", \"peak\": "<<a.peak<<", \"played_to_device\": false},\n"
    "  \"logs\": {\"total\": "<<logs.total<<", \"warning_or_error\": "<<logs.warning_or_error<<", \"emitted\": "<<logs.emitted<<", \"suppressed\": "<<logs.total-logs.emitted<<", \"game_error\": "<<logs.game_error<<", \"game_error_examples\": [";
  for(std::size_t index=0;index<logs.game_error_examples.size();++index) {
    if(index) report<<", ";report<<quote(logs.game_error_examples[index]);
  }
  report<<"]},\n  \"verification\": {\"boot_visual\": \"requires screenshot review\", \"gameplay\": \"not asserted\", \"in_game_save_reload\": \"not asserted\", \"translation\": \"not asserted; inspect supplied ROM separately\"}\n}\n";
  auto r=text_file(o.output/"report.json",report.str());if(auto* e=std::get_if<Error>(&r)) return fail(*e);
  std::cout<<report.str();return 0;
}
}
int main(int argc,char** argv) {
  try {return run(argc,argv);} catch(const std::exception& e) {return fail({"unexpected_failure",e.what()});}
}
