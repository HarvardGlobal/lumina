{
  description = "Pinned developer tooling for the LUMINA core workspace";

  # This immutable revision and its content hash are committed in flake.lock.
  # Run `nix flake update` deliberately when reviewing toolchain updates.
  inputs.nixpkgs.url = "github:NixOS/nixpkgs/ac62194c3917d5f474c1a844b6fd6da2db95077d";

  outputs = { self, nixpkgs }:
    let
      systems = [ "aarch64-darwin" "x86_64-darwin" "aarch64-linux" "x86_64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python312.withPackages (ps: [
            # Archive and Core API runtime imports.
            ps.fastapi
            ps.starlette
            ps.pydantic
            ps.uvicorn
            ps.sqlalchemy
            ps.psycopg
            ps.alembic
            ps.httpx
            ps.pyarrow
            ps.boto3

            # Test and supply-chain/security checks used by `make test` and CI.
            ps.pytest
            ps."pytest-cov"
            ps."pip-audit"
            ps.bandit
          ]);
        in {
          default = pkgs.mkShellNoCC {
            packages = with pkgs; [
              bashInteractive
              coreutils
              git
              gnumake
              curl
              jq
              python
            ];
            shellHook = ''
              export LUMINA_NIX_SHELL=1
              echo "LUMINA Nix shell: pinned Python 3.12, Core imports, tests, audits, and build tooling are active. Docker Desktop/Engine remains a host prerequisite."
            '';
          };
        });
      formatter = forAllSystems (system: (import nixpkgs { inherit system; }).nixfmt-rfc-style);
    };
}
