"""Gera data/brasil_ufs.geojson (contorno simplificado das 27 UFs) a partir de um GeoJSON de estados.

Uso: python tools/gerar_mapa_brasil.py <geojson_de_origem>   (requer: pip install shapely)
Mantém só sigla, nome e um ponto central (lon/lat) para colocar rótulos e bolhas.

O GeoJSON de origem espera as propriedades `sigla` e `name`. O arquivo usado no projeto foi o
`brazil-states.geojson` do repositório codeforamerica/click_that_hood (ver README, seção "Fonte do mapa").
"""
import json
import sys
from pathlib import Path

from shapely.geometry import mapping, shape

TOLERANCIA = 0.03  # graus (~3 km): suficiente para um mapa do país inteiro
SAIDA = Path(__file__).resolve().parent.parent / "data" / "brasil_ufs.geojson"


def arredondar(coords, casas=3):
    if isinstance(coords[0], (int, float)):
        return [round(c, casas) for c in coords]
    return [arredondar(c, casas) for c in coords]


def main(origem: str) -> None:
    bruto = json.loads(Path(origem).read_text(encoding="utf-8"))
    features = []
    for f in bruto["features"]:
        geom = shape(f["geometry"]).simplify(TOLERANCIA, preserve_topology=True)
        ponto = geom.representative_point()  # sempre cai dentro do estado
        features.append(
            {
                "type": "Feature",
                "properties": {
                    "uf": f["properties"]["sigla"],
                    "nome": f["properties"]["name"],
                    "lon": round(ponto.x, 3),
                    "lat": round(ponto.y, 3),
                },
                "geometry": {"type": geom.geom_type, "coordinates": arredondar(mapping(geom)["coordinates"])},
            }
        )
    features.sort(key=lambda x: x["properties"]["uf"])
    SAIDA.write_text(json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":")), encoding="utf-8")
    print(f"{len(features)} UFs, {SAIDA.stat().st_size / 1024:.0f} KB -> {SAIDA}")


if __name__ == "__main__":
    main(sys.argv[1])
