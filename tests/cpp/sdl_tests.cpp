#include <SDL3/SDL_version.h>
#include <iostream>
#include <string>
int main() {
  const std::string actual = SDL_GetRevision();
  if (actual != KHCOM_PINNED_SDL_REVISION || SDL_GetVersion() != SDL_VERSION) {
    std::cerr << "SDL runtime identity mismatch: " << actual << '\n';
    return 1;
  }
  std::cout << "Pinned SDL runtime identity: " << actual
            << " (parent Git excluded).\n";
  return 0;
}
