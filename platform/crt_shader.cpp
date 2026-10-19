#include "platform/crt_shader.hpp"
// Unmodified compiled variants from the pinned SDL3 archive (test example).
// The HLSL source attributes pxlforge's CC0 Lightweight CRT Effect; SDL's
// integration is under the SDL license. See runtime-deps.json and notices.
#include "testgpurender_effects_CRT.frag.dxil.h"
#include "testgpurender_effects_CRT.frag.msl.h"
#include "testgpurender_effects_CRT.frag.spv.h"
namespace khcom {
std::unique_ptr<CrtShader> CrtShader::create(SDL_Renderer *r,
                                             std::string &diagnostic) {
  auto self = std::unique_ptr<CrtShader>(new CrtShader);
  self->renderer_ = r;
  self->device_ = SDL_GetGPURendererDevice(r);
  if (!self->device_) {
    diagnostic = "Shader CRT requer o backend SDL GPU. Pixels nítidos "
                 "disponíveis neste dispositivo.";
    return {};
  }
  auto formats = SDL_GetGPUShaderFormats(self->device_);
  SDL_GPUShaderCreateInfo info{};
  if (formats & SDL_GPU_SHADERFORMAT_SPIRV) {
    info.format = SDL_GPU_SHADERFORMAT_SPIRV;
    info.code = testgpurender_effects_CRT_frag_spv;
    info.code_size = sizeof(testgpurender_effects_CRT_frag_spv);
  } else if (formats & SDL_GPU_SHADERFORMAT_DXIL) {
    info.format = SDL_GPU_SHADERFORMAT_DXIL;
    info.code = testgpurender_effects_CRT_frag_dxil;
    info.code_size = sizeof(testgpurender_effects_CRT_frag_dxil);
  } else if (formats & SDL_GPU_SHADERFORMAT_MSL) {
    info.format = SDL_GPU_SHADERFORMAT_MSL;
    info.code = testgpurender_effects_CRT_frag_msl;
    info.code_size = sizeof(testgpurender_effects_CRT_frag_msl);
  } else {
    diagnostic =
        "Nenhuma variante de shader compatível; usando pixels nítidos.";
    return {};
  }
  info.num_samplers = 1;
  info.num_uniform_buffers = 1;
  info.stage = SDL_GPU_SHADERSTAGE_FRAGMENT;
  self->shader_ = SDL_CreateGPUShader(self->device_, &info);
  if (!self->shader_) {
    diagnostic = SDL_GetError();
    return {};
  }
  SDL_GPURenderStateCreateInfo state{};
  state.fragment_shader = self->shader_;
  self->state_ = SDL_CreateGPURenderState(r, &state);
  if (!self->state_) {
    diagnostic = SDL_GetError();
    return {};
  }
  const float resolution[2] = {240, 160};
  if (!SDL_SetGPURenderStateFragmentUniforms(self->state_, 0, resolution,
                                             sizeof(resolution))) {
    diagnostic = SDL_GetError();
    return {};
  }
  return self;
}
CrtShader::~CrtShader() {
  SDL_DestroyGPURenderState(state_);
  if (shader_)
    SDL_ReleaseGPUShader(device_, shader_);
}
bool CrtShader::enable() { return SDL_SetGPURenderState(renderer_, state_); }
void CrtShader::disable() { SDL_SetGPURenderState(renderer_, nullptr); }
} // namespace khcom
