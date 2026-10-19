#include "core/session.hpp"
#include "core/sha256.hpp"
#include <iostream>
#include <stdexcept>

namespace {
void require(bool condition,const char* message) {if(!condition) throw std::runtime_error(message);}
template<class T> T take(khcom::Result<T> result) {
  if(auto* e=std::get_if<khcom::Error>(&result)) throw std::runtime_error(e->code+": "+e->message);
  return std::move(std::get<T>(result));
}
std::vector<std::uint8_t> fixture() {
  // Authored ARM instructions only. No Nintendo logo, BIOS or game assets.
  std::vector<std::uint8_t> rom(512);
  auto word=[&](unsigned offset,std::uint32_t value) {for(unsigned n=0;n<4;++n) rom[offset+n]=value>>(8*n);};
  word(0,0xea00002e); // branch to cartridge entry at 0xc0
  const std::uint32_t code[]={
    0xe3a00301,0xe3a01b01,0xe3811003,0xe1c010b0, // display mode 3 + BG2
    0xe3a00406,0xe3a0101f,0xe1c010b0, // red pixel at 0,0
    0xe3a0040e,0xe3a0105a,0xe5c01000, // write 0x5a to cartridge SRAM
    0xe3a00301,0xe2800e13,0xe1d010b0, // read KEYINPUT (active low)
    0xe3a0040e,0xe5c01002,0xe1a01421,0xe5c01003, // store both input bytes
    0xeafffff7 // poll keys again
  };
  unsigned offset=0xc0;for(auto instruction:code) {word(offset,instruction);offset+=4;}
  return rom;
}
}
int main() {
  try {
    require(std::string(khcom::Session::core_version())==KHCOM_PINNED_CORE_VERSION,
            "Core build identity must match the pinned dependency, never the enclosing Git repository");
    require(khcom::sha256({})=="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855","SHA256 empty vector");
    const std::vector<std::uint8_t> abc={'a','b','c'};
    require(khcom::sha256(abc)=="ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad","SHA256 abc vector");
    const std::vector<std::uint8_t> million(1000000,'a');
    require(khcom::sha256(million)=="cdc76e5c9914fb9281a1c7e284d73e67f1809a48a497200e046d39ccc7112cd0","SHA256 million a vector");
    require(std::holds_alternative<khcom::Error>(khcom::Session::create({})),"Empty ROM rejection");
    auto rom=fixture();auto digest=khcom::sha256(rom);auto session=take(khcom::Session::create(rom));
    for(unsigned n=0;n<3;++n) take(session->advance(0));
    require(session->frames()==3,"Frame count");
    if((session->pixels()[0]&0xffffff)!=0xff)
      throw std::runtime_error("Authored fixture framebuffer; pixel="+std::to_string(session->pixels()[0]));
    require(session->save_info().backend=="sram_32k","SRAM backend detection");
    auto save=take(session->save());require(save.size()==32768&&save[0]==0x5a,"SRAM write/clone");
    save[1]=0xa5;auto reload=take(khcom::Session::create(rom,save));
    for(unsigned n=0;n<3;++n) take(reload->advance(0));
    require(take(reload->save())==save,"Fresh core save reload");
    take(reload->advance(1|256));
    auto pressed=take(reload->save());
    require(pressed[2]==0xfe&&pressed[3]==0x02,"A/R input reaches emulated KEYINPUT");
    auto checkpoint=take(reload->checkpoint());
    auto resumed=take(khcom::Session::create(rom,pressed));
    take(resumed->restore_checkpoint(checkpoint));
    require(resumed->frames()==reload->frames(),"Checkpoint retains emulated frame count");
    take(reload->advance(2));take(resumed->advance(2));
    require(take(reload->save())==take(resumed->save()),"Checkpoint and cartridge pairing resumes authored fixture");
    auto corrupted=checkpoint;corrupted.back()^=1;
    require(std::holds_alternative<khcom::Error>(resumed->restore_checkpoint(corrupted)),"Corrupt checkpoint rejected");
    auto foreign=rom;foreign.back()^=1;auto other=take(khcom::Session::create(foreign));
    require(std::holds_alternative<khcom::Error>(other->restore_checkpoint(checkpoint)),"Foreign ROM checkpoint rejected");
    auto mismatched=take(khcom::Session::create(rom,save));
    require(std::holds_alternative<khcom::Error>(mismatched->restore_checkpoint(checkpoint)),"Mismatched cartridge save rejected");
    require(std::holds_alternative<khcom::Error>(resumed->restore_checkpoint({})),"Truncated checkpoint rejected");
    require(khcom::sha256(session->rom())==digest,"Immutable ROM buffer");
    require(std::holds_alternative<khcom::Error>(session->advance(0x400)),"Reject unsupported key bits");
    std::cout<<"SHA256, authored ARM framebuffer, input guard, SRAM reload and diagnostic checkpoint contracts passed.\n"
      "These synthetic checks do not establish KHCoM gameplay or in-game save compatibility.\n";
    return 0;
  } catch(const std::exception& e) {std::cerr<<e.what()<<'\n';return 1;}
}
