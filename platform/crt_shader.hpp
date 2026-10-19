#pragma once
#include <SDL3/SDL.h>
#include <memory>
#include <string>
namespace khcom {
class CrtShader {
public:
  static std::unique_ptr<CrtShader> create(SDL_Renderer *,
                                           std::string &diagnostic);
  ~CrtShader();
  bool enable();
  void disable();

private:
  SDL_Renderer *renderer_ = nullptr;
  SDL_GPUDevice *device_ = nullptr;
  SDL_GPUShader *shader_ = nullptr;
  SDL_GPURenderState *state_ = nullptr;
};
} // namespace khcom
