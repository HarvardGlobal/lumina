{
  description = "Pinned developer tooling for the LUMINA core workspace";

  # This immutable revision is mirrored into flake.lock on the first Nix run.
  # Run `nix flake update` deliberately when reviewing toolchain updates.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/ac62194c3917d5f474c1a844b6fd6da2db95077d";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let pkgs = import nixpkgs { inherit system; };
        in {
          default = pkgs.mkShellNoCC {
            packages = with pkgs; [
              git
              gnumake
              curl
              python3
            ];
            shellHook = ''
              echo "LUMINA Nix shell: pinned tooling is active. Docker Desktop/Engine remains a host prerequisite."
            '';
          };
        });
      formatter = forAllSystems (system: (import nixpkgs { inherit system; }).nixfmt-rfc-style);
    };
}
