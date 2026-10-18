#include "platform/sdl_preview.hpp"
#include <SDL3/SDL.h>

namespace khcom {
struct Preview::Impl {
  SDL_Window* window=nullptr;
  SDL_Renderer* renderer=nullptr;
  SDL_Texture* texture=nullptr;
  ~Impl() {
    SDL_DestroyTexture(texture);
    SDL_DestroyRenderer(renderer);
    SDL_DestroyWindow(window);
    SDL_Quit();
  }
};
Result<std::unique_ptr<Preview>> Preview::create(unsigned scale) {
  if(scale<1 || scale>6) return Error{"invalid_scale","Escala deve estar entre 1 e 6."};
  auto self=std::unique_ptr<Preview>(new Preview);
  self->impl_=std::make_unique<Impl>();
  if(!SDL_Init(SDL_INIT_VIDEO)) return Error{"sdl_initialization",SDL_GetError()};
  auto& i=*self->impl_;
  i.window=SDL_CreateWindow("KHCoM — diagnóstico original (sem tradução)",240*scale,160*scale,0);
  if(!i.window) return Error{"sdl_window",SDL_GetError()};
  i.renderer=SDL_CreateRenderer(i.window,nullptr);
  if(!i.renderer) return Error{"sdl_renderer",SDL_GetError()};
  i.texture=SDL_CreateTexture(i.renderer,SDL_PIXELFORMAT_ABGR8888,SDL_TEXTUREACCESS_STREAMING,240,160);
  if(!i.texture || !SDL_SetTextureScaleMode(i.texture,SDL_SCALEMODE_NEAREST) ||
     !SDL_SetTextureBlendMode(i.texture,SDL_BLENDMODE_NONE))
    return Error{"sdl_texture",SDL_GetError()};
  return self;
}
Preview::~Preview()=default;
Result<bool> Preview::present(std::span<const std::uint32_t> pixels) {
  SDL_Event event;
  while(SDL_PollEvent(&event)) if(event.type==SDL_EVENT_QUIT) return false;
  if(pixels.size()!=240*160) return Error{"framebuffer_size","Framebuffer inválido."};
  auto& i=*impl_;
  if(!SDL_UpdateTexture(i.texture,nullptr,pixels.data(),240*4) ||
     !SDL_RenderClear(i.renderer) || !SDL_RenderTexture(i.renderer,i.texture,nullptr,nullptr) ||
     !SDL_RenderPresent(i.renderer)) return Error{"sdl_present",SDL_GetError()};
  return true;
}
}
