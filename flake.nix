{
  description = "A simple token based voting system";

  inputs = {
    nixpkgs.url = "github:mayflower/nixpkgs/mf-stable";
  };

  outputs = { self, nixpkgs }: let
    forEachSystem = nixpkgs.lib.genAttrs [ "x86_64-linux" ];
    pkgs = forEachSystem (system: nixpkgs.legacyPackages.${system});
  in {
    devShells = forEachSystem (system: with pkgs.${system}; {
      default = mkShell {
        name = "demockrazy-env";
        buildInputs = [
          python3
          python3Packages.django
          python3Packages.psycopg2
        ];
      };
    });
  };
}
