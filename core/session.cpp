#include "core/session.hpp"
#include "core/sha256.hpp"
#include <algorithm>
#include <array>
#include <cstdlib>
#include <mgba/core/blip_buf.h>
#include <mgba/core/core.h>
#include <mgba/core/version.h>
#include <mgba/internal/gba/gba.h>
#include <mgba-util/vfs.h>

namespace khcom {
Result<std::unique_ptr<Session>> Session::create(std::vector<std::uint8_t> rom,
                                                std::span<const std::uint8_t> save) {
  if(rom.size()<0xc0 || rom.size()>32*1024*1024)
    return Error{"invalid_rom_size", "ROM fora do intervalo de cartucho GBA admitido."};
  if(save.size()>128*1024)
    return Error{"invalid_save_size", "Save maior que a capacidade de cartucho suportada."};
  auto self=std::unique_ptr<Session>(new Session);
  self->rom_=std::move(rom);
  self->initial_save_digest_=sha256(save);
  self->pixels_.resize(width*height);
  static_assert(sizeof(color_t)==sizeof(std::uint32_t));
  self->core_=mCoreCreate(mPLATFORM_GBA);
  if(!self->core_) return Error{"core_allocation", "Não foi possível criar o core GBA."};
  if(!self->core_->init(self->core_))
    return Error{"core_initialization", "Não foi possível inicializar o core GBA."};
  self->initialized_=true;
  mCoreInitConfig(self->core_, nullptr);
  self->config_initialized_=true;
  mCoreConfigSetDefaultIntValue(&self->core_->config, "useBios", 0);
  mCoreConfigSetDefaultIntValue(&self->core_->config, "skipBios", 1);
  mCoreConfigSetDefaultIntValue(&self->core_->config, "volume", 0x100);
  mCoreConfigSetDefaultIntValue(&self->core_->config, "audioBuffers", 2048);
  mCoreLoadConfig(self->core_);
  self->core_->opts.useBios=false;
  self->core_->opts.skipBios=true;
  self->core_->setVideoBuffer(self->core_, self->pixels_.data(), width);
  auto* rom_file=VFileFromConstMemory(self->rom_.data(), self->rom_.size());
  if(!rom_file) return Error{"rom_allocation", "Não foi possível mapear a ROM em memória."};
  if(!self->core_->loadROM(self->core_,rom_file)) {
    rom_file->close(rom_file);
    return Error{"rom_load", "O core rejeitou o carregamento da ROM."};
  }
  auto* save_file=VFileMemChunk(save.data(),save.size());
  if(!save_file) return Error{"save_allocation", "Não foi possível criar save em memória."};
  if(!self->core_->loadSave(self->core_,save_file)) {
    save_file->close(save_file);
    return Error{"save_load", "O core rejeitou o save em memória."};
  }
  self->core_->setAudioBufferSize(self->core_,2048);
  mCoreCallbacks callbacks{};
  callbacks.context=self.get();
  callbacks.coreCrashed=[](void* context) {static_cast<Session*>(context)->crashed_=true;};
  self->core_->addCoreCallbacks(self->core_,&callbacks);
  self->core_->reset(self->core_);
  for(int channel=0;channel<2;++channel)
    blip_set_rates(self->core_->getAudioChannel(self->core_,channel),
                   self->core_->frequency(self->core_),48000);
  return self;
}

Session::~Session() {
  if(config_initialized_) mCoreConfigDeinit(&core_->config);
  if(initialized_) core_->deinit(core_);
  else std::free(core_);
}

Result<Success> Session::advance(std::uint16_t keys) {
  if(keys>0x3ff) return Error{"invalid_input", "Máscara de entrada excede os dez botões GBA."};
  core_->setKeys(core_,keys);
  core_->runFrame(core_);
  if(crashed_)
    return Error{"core_crash", "O core sinalizou falha da execução emulada."};
  std::array<short,2048> samples{};
  for(int channel=0;channel<2;++channel) {
    auto* buffer=core_->getAudioChannel(core_,channel);
    while(int count=blip_read_samples(buffer,samples.data(),samples.size(),0)) {
      audio_.samples+=count;
      for(int i=0;i<count;++i) {
        audio_.nonzero+=samples[i]!=0;
        audio_.peak=std::max(audio_.peak,std::abs(static_cast<int>(samples[i])));
      }
    }
  }
  return Success{};
}

Result<std::vector<std::uint8_t>> Session::save() const {
  const auto info=save_info();
  if(info.size==0) return std::vector<std::uint8_t>{};
  void* bytes=nullptr;
  const auto size=core_->savedataClone(core_,&bytes);
  if(size!=info.size || !bytes) {
    std::free(bytes);
    return Error{"save_clone", "O core não retornou o save completo."};
  }
  const auto* begin=static_cast<const std::uint8_t*>(bytes);
  std::vector<std::uint8_t> result(begin,begin+size);
  std::free(bytes);
  return result;
}

Result<std::vector<std::uint8_t>> Session::checkpoint() const {
  constexpr std::size_t header_size=232;
  auto cartridge=save();if(auto* e=std::get_if<Error>(&cartridge)) return *e;
  std::vector<std::uint8_t> result(header_size+core_->stateSize(core_));
  if(!core_->saveState(core_,result.data()+header_size))
    return Error{"checkpoint_save", "O core rejeitou a captura do estado de diagnóstico."};
  const std::string version=core_version();
  if(version.size()>31) return Error{"checkpoint_version", "Versão do core excede o cabeçalho de diagnóstico."};
  const auto rom_hash=sha256(rom_);
  const auto state_hash=sha256(std::span(result).subspan(header_size));
  const std::string magic="KHCP0001";
  std::copy(magic.begin(),magic.end(),result.begin());
  std::copy(rom_hash.begin(),rom_hash.end(),result.begin()+8);
  std::copy(state_hash.begin(),state_hash.end(),result.begin()+72);
  std::copy(version.begin(),version.end(),result.begin()+136);
  const auto save_hash=sha256(std::get<std::vector<std::uint8_t>>(cartridge));
  std::copy(save_hash.begin(),save_hash.end(),result.begin()+168);
  return result;
}

Result<Success> Session::restore_checkpoint(std::span<const std::uint8_t> bytes) {
  constexpr std::size_t header_size=232;
  if(bytes.size()!=header_size+core_->stateSize(core_))
    return Error{"checkpoint_size", "Tamanho incompatível com o core de diagnóstico."};
  auto field=[&](std::size_t start,std::size_t size) {return std::string(bytes.begin()+start,bytes.begin()+start+size);};
  std::string expected_version=core_version();expected_version.resize(32,'\0');
  if(field(0,8)!="KHCP0001"||field(8,64)!=sha256(rom_)||field(136,32)!=expected_version)
    return Error{"checkpoint_identity", "Checkpoint pertence a outra ROM, formato ou versão do core."};
  if(field(72,64)!=sha256(bytes.subspan(header_size)))
    return Error{"checkpoint_integrity", "Digest do checkpoint não confere."};
  if(frames()!=0||field(168,64)!=initial_save_digest_)
    return Error{"checkpoint_cartridge", "Retome o checkpoint em um core novo com o save de cartucho correspondente."};
  if(!core_->loadState(core_,bytes.data()+header_size))
    return Error{"checkpoint_load", "O core rejeitou o checkpoint de diagnóstico."};
  crashed_=false;
  return Success{};
}

SaveInfo Session::save_info() const {
  const auto& data=static_cast<GBA*>(core_->board)->memory.savedata;
  const char* backend="unknown";
  switch(data.type) {
    case SAVEDATA_AUTODETECT: backend="not_detected";break;
    case SAVEDATA_FORCE_NONE: backend="none";break;
    case SAVEDATA_SRAM: backend="sram_32k";break;
    case SAVEDATA_SRAM512: backend="sram_64k";break;
    case SAVEDATA_FLASH512: backend="flash_64k";break;
    case SAVEDATA_FLASH1M: backend="flash_128k";break;
    case SAVEDATA_EEPROM: backend="eeprom_8k";break;
    case SAVEDATA_EEPROM512: backend="eeprom_512";break;
  }
  return {backend,GBASavedataSize(&data)};
}
std::uint32_t Session::frames() const { return core_->frameCounter(core_); }
const char* Session::core_version() { return projectVersion; }
}
