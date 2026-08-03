{
  description = "A simple token based voting system";

  inputs = {
    nixpkgs.url = "github:mayflower/nixpkgs/mf-next";
  };

  outputs = { self, nixpkgs }: let
    forEachSystem = nixpkgs.lib.genAttrs [ "x86_64-linux" ];
    pkgs = forEachSystem (system: nixpkgs.legacyPackages.${system});
  in {
    devShells = forEachSystem (system: with pkgs.${system}; {
      default = mkShell {
        name = "demockrazy-env";
        packages = [
          (python3.withPackages (ps: with ps; [
            django
            pytest
            pytest-django
          ]))
          ruff
        ];
      };
    });
  };
}
