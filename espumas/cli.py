"""Linha de comando: python -m espumas <comando> ..."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from .config import load_config


def _cmd_analisar(args) -> int:
    from .pipeline import analyze

    cfg = load_config(args.config)
    if args.modelo:
        cfg["transcricao"]["modelo"] = args.modelo
    if args.cpu:
        cfg["transcricao"]["dispositivo"] = "cpu"
        cfg["transcricao"]["compute_type"] = "int8"
    saida = Path(args.saida) if args.saida else Path("saida") / Path(args.fonte).stem
    match = None
    if args.partida:
        from .riot import HenrikClient, normalize_match

        r = cfg["riot"]
        if not r["api_key"] or not r["riot_id"]:
            print("Para usar --partida, preencha riot.api_key e riot.riot_id no config.yaml "
                  "(ou use a interface: python -m espumas web).", file=sys.stderr)
            return 2
        cli = HenrikClient(r["api_key"], r["regiao"], r["plataforma"])
        mid = args.partida
        if mid == "ultima":
            mid = cli.list_matches(r["riot_id"], size=1)[0]["id"]
        match = normalize_match(cli.get_match(mid), r["riot_id"], cfg["sinc"]["buy_fase_s"])
        print(f"Partida: {match['mapa']} {match['placar']}")
    html = analyze(args.fonte, saida, cfg, nome=args.nome, match=match)
    print(f"\nPronto! Abra o relatório: {html.resolve()}")
    return 0


def _cmd_relatorio(args) -> int:
    from .pipeline import rebuild

    cfg = load_config(args.config)
    html = rebuild(args.analise, cfg)
    print(f"Relatório refeito: {html.resolve()}")
    return 0


def _cmd_web(args) -> int:
    from .web.app import run

    run(port=args.porta, abrir=not args.sem_navegador)
    return 0


def _cmd_verificar(args) -> int:
    """Checa se a GPU está acessível para o faster-whisper."""
    from .transcribe import _windows_cuda_dlls

    _windows_cuda_dlls()
    try:
        import ctranslate2
    except ImportError:
        print("faster-whisper não está instalado. Rode: pip install -r requirements.txt")
        return 1
    print(f"CTranslate2 {ctranslate2.__version__}")
    n = ctranslate2.get_cuda_device_count()
    if n == 0:
        print("Nenhuma GPU CUDA encontrada. Veja a seção 'Problemas comuns' do README.")
        return 1
    print(f"GPUs CUDA: {n}")
    print("Tipos suportados:", ", ".join(sorted(ctranslate2.get_supported_compute_types("cuda"))))
    if args.modelo:
        from faster_whisper import WhisperModel

        print(f"Carregando {args.modelo} na GPU (baixa na primeira vez)...")
        WhisperModel(args.modelo, device="cuda", compute_type="float16")
        print("OK: modelo carregou na GPU.")
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="espumas", description="Analisa calls de Valorant gravadas pelo Craig.")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("analisar", help="Transcreve e gera o relatório de uma partida")
    a.add_argument("fonte", help="Pasta ou .zip baixado do Craig (multi-track)")
    a.add_argument("-c", "--config", default="config.yaml" if Path("config.yaml").exists() else None)
    a.add_argument("-o", "--saida", help="Pasta de saída (padrão: saida/<nome>)")
    a.add_argument("-n", "--nome", help="Nome da partida no relatório (ex.: 'Ascent 13-11')")
    a.add_argument("-m", "--modelo", help="Modelo Whisper (padrão: large-v3-turbo)")
    a.add_argument("--cpu", action="store_true", help="Roda sem GPU (bem mais lento)")
    a.add_argument("-p", "--partida", help="ID da partida ou 'ultima' (precisa da chave HenrikDev)")
    a.set_defaults(func=_cmd_analisar)

    r = sub.add_parser("relatorio", help="Refaz métricas/relatório sem transcrever de novo")
    r.add_argument("analise", help="Caminho do analise.json")
    r.add_argument("-c", "--config", default="config.yaml" if Path("config.yaml").exists() else None)
    r.set_defaults(func=_cmd_relatorio)

    w = sub.add_parser("web", help="Abre a interface no navegador")
    w.add_argument("--porta", type=int, default=8765)
    w.add_argument("--sem-navegador", action="store_true", help="Não abre o navegador sozinho")
    w.set_defaults(func=_cmd_web)

    v = sub.add_parser("verificar", help="Testa se a GPU funciona com o faster-whisper")
    v.add_argument("-m", "--modelo", help="Também carrega este modelo na GPU (ex.: large-v3-turbo)")
    v.set_defaults(func=_cmd_verificar)

    args = p.parse_args(argv)
    try:
        return args.func(args)
    except FileNotFoundError as e:
        print(f"Erro: {e}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
