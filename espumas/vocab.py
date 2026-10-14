"""Glossário de Valorant: ajuda o Whisper a acertar o jargão e corrige erros comuns."""

from __future__ import annotations

import re

from rapidfuzz import fuzz, process

AGENTES = [
    "Astra", "Breach", "Brimstone", "Chamber", "Clove", "Cypher", "Deadlock", "Fade",
    "Gekko", "Harbor", "Iso", "Jett", "KAY/O", "Killjoy", "Neon", "Omen", "Phoenix",
    "Raze", "Reyna", "Sage", "Skye", "Sova", "Tejo", "Veto", "Viper", "Vyse", "Waylay",
    "Yoru",
]
MAPAS = [
    "Abyss", "Ascent", "Bind", "Breeze", "Corrode", "Fracture", "Haven", "Icebox",
    "Lotus", "Pearl", "Split", "Sunset",
]
ARMAS = [
    "Vandal", "Phantom", "Operator", "Sheriff", "Ghost", "Classic", "Spectre", "Judge",
    "Marshal", "Outlaw", "Odin", "Ares", "Bulldog", "Guardian", "Stinger", "Bucky",
    "Frenzy", "Shorty",
]
TERMOS = [
    "heaven", "hell", "main", "site", "mid", "lobby", "link", "short", "long", "garage",
    "market", "tree", "hookah", "showers", "elbow", "CT", "spawn", "rafters", "default",
    "plant", "defuse", "spike", "rotate", "retake", "push", "lurk", "flash", "smoke",
    "molly", "util", "eco", "full buy", "force", "save", "one shot", "lit", "tapped",
    "trade", "peek", "wide swing", "off-angle", "ult", "orb", "drone", "dart", "clutch",
    "entry", "anchor", "IGL", "op",
]

# Erros de transcrição frequentes -> forma correta. Comparação sem maiúsculas,
# só em palavra inteira. Adicione os seus em `correcoes` no config.yaml.
CORRECOES_PADRAO = {
    "jet": "Jett",
    "sóva": "Sova",
    "sôva": "Sova",
    "vaiper": "Viper",
    "vaipa": "Viper",
    "kill joy": "Killjoy",
    "kiljoy": "Killjoy",
    "kayo": "KAY/O",
    "kay o": "KAY/O",
    "cai ou": "KAY/O",
    "brimston": "Brimstone",
    "saifer": "Cypher",
    "saipher": "Cypher",
    "omem": "Omen",
    "ômen": "Omen",
    "reina": "Reyna",
    "rayna": "Reyna",
    "geko": "Gekko",
    "vandau": "Vandal",
    "fantom": "Phantom",
    "espaique": "spike",
    "spaike": "spike",
    "espaike": "spike",
    "réven": "heaven",
    "héven": "heaven",
    "heven": "heaven",
    "rotei": "rotate",
    "uan shot": "one shot",
    "wan shot": "one shot",
}

# Nomes próprios que valem correção aproximada (palavras longas, pouco ambíguas).
_FUZZY_ALVOS = [w for w in AGENTES + MAPAS + ARMAS if len(w) >= 5 and "/" not in w]
# Palavras comuns em português que se parecem com algum alvo e nunca devem ser trocadas.
_NUNCA_TROCAR = {
    "classe", "clássico", "fantasma", "guarda", "ponto", "bindo", "fases", "fazer",
    "raiz", "rase", "sobre", "sabe", "saber", "nossa", "nosso", "verde", "vandalo",
    "ghost", "split", "judge", "ares",
}


def all_terms(extra: list[str] | None = None) -> list[str]:
    return AGENTES + MAPAS + ARMAS + TERMOS + list(extra or [])


def build_prompt(extra: list[str] | None = None) -> str:
    """Texto inicial que orienta o Whisper (limite prático ~200 tokens)."""
    termos_extra = ", ".join(extra or [])
    prompt = (
        "Call de Valorant em português, cinco jogadores. "
        f"Agentes: {', '.join(AGENTES)}. "
        f"Mapas: {', '.join(MAPAS)}. "
        "Callouts: heaven, hell, main, mid, lobby, link, short, long, spike, plant, "
        "defuse, rotate, retake, lurk, flash, smoke, molly, eco, full buy, one shot, "
        "lit, tapped, trade, peek, ult. Vandal, Phantom, Operator, Sheriff."
    )
    if termos_extra:
        prompt += f" {termos_extra}."
    return prompt


def build_hotwords(extra: list[str] | None = None) -> str:
    return " ".join(AGENTES + MAPAS + list(extra or []))


class Corrector:
    def __init__(self, extra_corrections: dict[str, str] | None = None, fuzzy: bool = True,
                 fuzzy_threshold: int = 85):
        corr = {**CORRECOES_PADRAO, **{k.lower(): v for k, v in (extra_corrections or {}).items()}}
        # Frases maiores primeiro, para "kill joy" ganhar de "kill".
        self._patterns = [
            (re.compile(rf"(?<!\w){re.escape(k)}(?!\w)", re.IGNORECASE), v)
            for k, v in sorted(corr.items(), key=lambda kv: -len(kv[0]))
        ]
        self.fuzzy = fuzzy
        self.threshold = fuzzy_threshold
        self._lower_targets = {t.lower(): t for t in _FUZZY_ALVOS}
        # Termos já corretos (inclui callouts como "heaven") nunca passam pelo fuzzy.
        self._protegidos = {t.lower() for t in all_terms()} | {v.lower() for v in corr.values()}

    def _fix_token(self, tok: str) -> str:
        core = tok.strip(".,!?;:\"'()")
        low = core.lower()
        if low in self._lower_targets:
            return tok.replace(core, self._lower_targets[low])
        if len(core) < 5 or low in _NUNCA_TROCAR or low in self._protegidos:
            return tok
        match = process.extractOne(low, list(self._lower_targets), scorer=fuzz.ratio)
        if match and match[1] >= self.threshold:
            return tok.replace(core, self._lower_targets[match[0]])
        return tok

    def __call__(self, text: str) -> str:
        for pat, repl in self._patterns:
            text = pat.sub(repl, text)
        if self.fuzzy:
            text = " ".join(self._fix_token(t) for t in text.split(" "))
        return text
