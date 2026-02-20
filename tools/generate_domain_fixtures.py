"""Generate JSON fixtures for domain-only parity tests.

Writes fixtures to flutter_app/test/fixtures/domain_fixtures.json.
"""

from __future__ import annotations

import json
import os
from typing import Any

from domain.jyutping_validation import normalize_jyutping, validate_jyut_syllables
from domain.category_rules import (
    is_category_placeholder,
    save_enabled_gate,
    should_show_custom_hanzi_button,
    prefer_meanings,
    detect_ambiguity,
)
from domain.duplicate_rules import is_duplicate_jy, is_exact_duplicate_entry
from domain.meaning_sources_cleaning import clean_glosses_for_display
from domain.hanzi_candidate_utils import (
    _norm_space,
    _split_syllables,
    _coerce_candidates,
    _dedupe_keep_first,
    _simple_rank,
)
from domain.hanzi_candidate_ranker import rerank_candidates_with_meanings
from domain.hanzi_candidate_pipeline_core import (
    HanziCandidatePipeline,
    HanziPipelineDeps,
    build_pipeline_from_category_manager,
)
from domain.meaning_sources_models import MeaningResolver, MeaningFacade
from domain.entry_validation import EntryValidator
from domain.vocabulary_service import VocabularyService


def _fixture_path() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, "flutter_app", "test", "fixtures", "domain_fixtures.json")


def _case(function: str, input_data: Any, output_data: Any) -> dict:
    return {"function": function, "input": input_data, "output": output_data}


def _detect_ambiguity_call(input_data: dict) -> bool:
    meanings = input_data.get("meanings_for_hanzi")
    fn = None
    if isinstance(meanings, list):
        fn = lambda _hz: meanings
    return detect_ambiguity(
        candidates=input_data.get("candidates"),
        n_syllables=input_data.get("n_syllables"),
        meanings_for_hanzi=fn,
    )


def generate() -> list[dict]:
    fixtures: list[dict] = []

    # 1) normalize_jyutping
    for inp in ["  Nei5   Hou2 ", "zi6-ji2", "", None]:
        fixtures.append(_case("normalize_jyutping", inp, normalize_jyutping(inp)))

    # 2) validate_jyut_syllables
    for inp in ["nei5 hou2", "nei5hou2", "nei5 hou", "nei5, hou2", ""]:
        fixtures.append(_case("validate_jyut_syllables", inp, list(validate_jyut_syllables(inp))))

    # 3) is_category_placeholder
    for inp in [None, "", "— choose category —", "- choose category -", "greetings"]:
        fixtures.append(_case("is_category_placeholder", inp, is_category_placeholder(inp)))

    # 4) save_enabled_gate
    save_cases = [
        {"jyut": "nei5 hou2", "hanzi": "你好", "meanings": ["hello"], "category": "greetings"},
        {"jyut": "", "hanzi": "你好", "meanings": ["hello"], "category": "greetings"},
        {"jyut": "nei5 hou2", "hanzi": "", "meanings": ["hello"], "category": "greetings"},
        {"jyut": "nei5 hou2", "hanzi": "你好", "meanings": [], "category": "greetings"},
        {"jyut": "nei5 hou2", "hanzi": "你好", "meanings": ["hello"], "category": "— choose category —"},
    ]
    for inp in save_cases:
        fixtures.append(_case("save_enabled_gate", inp, save_enabled_gate(**inp)))

    # 5) should_show_custom_hanzi_button
    for inp in [None, [], [""], ["飲", " "], [" ", "\t"]]:
        fixtures.append(_case("should_show_custom_hanzi_button", inp, should_show_custom_hanzi_button(inp)))

    # 6) prefer_meanings
    prefer_cases = [
        {"primary": ["", " hello "], "fallback": ["bye"]},
        {"primary": [""], "fallback": ["bye"]},
        {"primary": None, "fallback": ["bye", ""]},
        {"primary": ["foo", "bar"], "fallback": ["baz"]},
    ]
    for inp in prefer_cases:
        fixtures.append(_case("prefer_meanings", inp, prefer_meanings(inp["primary"], inp["fallback"])))

    # 7) detect_ambiguity
    ambiguity_cases = [
        {"candidates": ["飲", "喝"], "n_syllables": 1, "meanings_for_hanzi": None},
        {"candidates": [], "n_syllables": 2, "meanings_for_hanzi": None},
        {"candidates": ["飲"], "n_syllables": 1, "meanings_for_hanzi": ["drink", "beverage"]},
        {"candidates": ["飲"], "n_syllables": 1, "meanings_for_hanzi": ["drink"]},
    ]
    for inp in ambiguity_cases:
        fixtures.append(_case("detect_ambiguity", inp, _detect_ambiguity_call(inp)))

    # 8) is_duplicate_jy
    vocab_entries = {
        "entries": {
            "nei5 hou2": {
                "jyutping": "nei5 hou2",
                "senses": [{"hanzi": "你好", "gloss": "hello", "categories": ["greetings"]}],
            }
        }
    }
    legacy_vocab = {"你好": [["hello"], "nei5 hou2"]}
    dup_cases = [
        {"jy": "nei5 hou2", "vocab": vocab_entries},
        {"jy": " Nei5   Hou2 ", "vocab": vocab_entries},
        {"jy": "nei5 hou3", "vocab": vocab_entries},
        {"jy": "nei5 hou2", "vocab": legacy_vocab},
    ]
    for inp in dup_cases:
        fixtures.append(_case("is_duplicate_jy", inp, is_duplicate_jy(inp["jy"], vocab=inp["vocab"])))

    # 9) is_exact_duplicate_entry
    exact_vocab = {
        "entries": {
            "nei5 hou2": {
                "headword": "你好",
                "jyutping": "nei5 hou2",
                "senses": [{"hanzi": "你好", "gloss": "hello", "categories": ["greetings"]}],
            }
        }
    }
    exact_cases = [
        {"jy": "nei5 hou2", "hz": "你好", "vocab": exact_vocab},
        {"jy": "nei5 hou2", "hz": "哈囉", "vocab": exact_vocab},
        {"jy": " Nei5   Hou2 ", "hz": "你好", "vocab": exact_vocab},
    ]
    for inp in exact_cases:
        fixtures.append(_case("is_exact_duplicate_entry", inp, is_exact_duplicate_entry(inp["vocab"], inp["jy"], inp["hz"])))

    # 10) clean_glosses_for_display
    for inp in [[" hello ", "", "bye"], "notlist", []]:
        fixtures.append(_case("clean_glosses_for_display", inp, clean_glosses_for_display(inp)))

    # 11) _norm_space
    for inp in ["  nei5   hou2 ", "a  b   c", ""]:
        fixtures.append(_case("norm_space", inp, _norm_space(inp)))

    # 12) _split_syllables
    for inp in ["nei5 hou2", "zi6-ji2", ""]:
        fixtures.append(_case("split_syllables", inp, _split_syllables(inp)))

    # 13) _coerce_candidates
    coerce_cases = [
        {"raw": ["飲", ("喝", "tier1", 2), ("飲", 3)], "default_source": "tier2"},
        {"raw": [("  ", "tier1", 1)], "default_source": "tier2"},
        {"raw": None, "default_source": "tier2"},
    ]
    for inp in coerce_cases:
        out = _coerce_candidates(inp["raw"], inp["default_source"])
        fixtures.append(
            _case(
                "coerce_candidates",
                inp,
                [(c.hanzi, c.source, c.freq) for c in out],
            )
        )

    # 14) _dedupe_keep_first
    dedupe_in = _coerce_candidates(["飲", ("飲", "tier1", 2), ("喝", "tier2", 1)], "tier2")
    dedupe_out = _dedupe_keep_first(dedupe_in)
    fixtures.append(_case("dedupe_keep_first", None, [(c.hanzi, c.source, c.freq) for c in dedupe_out]))

    # 15) _simple_rank
    rank_in = _coerce_candidates([("喝", "tier2", 1), ("飲", "tier1", 3), ("啦", "tier1", 3)], "tier2")
    rank_out = _simple_rank(rank_in)
    fixtures.append(_case("simple_rank", None, [(c.hanzi, c.source, c.freq) for c in rank_out]))

    # 16) rerank_candidates_with_meanings
    meaning_map = {
        "飲": ["drink", "beverage"],
        "喝": ["drink"],
        "阿飲": ["[yue] to drink"],
    }
    profiles = {"food": {"drink": 2.0, "beverage": 1.0}}
    hk_freq = {"阿飲": 50, "飲": 10}
    hk_colloq = {"阿飲"}
    hk_attested = {"阿飲", "飲", "喝"}
    cands = [("喝", "tier1", 1.0), ("飲", "tier2", 1.0), ("阿飲", "tier2", 1.0)]

    def _meanings_for(hz: str):
        return meaning_map.get(hz, [])

    reranked = rerank_candidates_with_meanings(
        cands,
        meanings_for_hanzi=_meanings_for,
        active_category="food",
        category_profiles=profiles,
        hk_freq_map=hk_freq,
        hk_colloquial=hk_colloq,
        hk_attested=hk_attested,
    )
    fixtures.append(_case("rerank_candidates_with_meanings", {
        "cands": cands,
        "meaning_map": meaning_map,
        "active_category": "food",
        "category_profiles": profiles,
        "hk_freq_map": hk_freq,
        "hk_colloquial": list(hk_colloq),
        "hk_attested": list(hk_attested),
    }, reranked))

    # 17) rerank_candidates_with_meanings (no HK data, no category profile)
    meaning_map2 = {
        "文": ["[lit] written language"],
        "話": ["speech"],
        "口語": ["(colloquial) spoken language"],
    }
    cands2 = [("話", "tier2", 1.0), ("文", "tier1", 2.0), ("口語", "tier1", 1.0)]
    reranked2 = rerank_candidates_with_meanings(
        cands2,
        meanings_for_hanzi=lambda hz: meaning_map2.get(hz, []),
        active_category="",
        category_profiles={},
        hk_freq_map=None,
        hk_colloquial=None,
        hk_attested=None,
    )
    fixtures.append(_case("rerank_candidates_with_meanings_nohk", {
        "cands": cands2,
        "meaning_map": meaning_map2,
        "active_category": "",
        "category_profiles": {},
        "hk_freq_map": {},
        "hk_colloquial": [],
        "hk_attested": [],
    }, reranked2))

    # 18) rerank_candidates_with_meanings (tagged vs clean glosses)
    meaning_map3 = {
        "甲": ["[char] jia3", "alpha"],
        "乙": ["[char] yi3"],
        "丙": ["beta"],
    }
    cands3 = [("乙", "tier1", 1.0), ("甲", "tier1", 1.0), ("丙", "tier1", 1.0)]
    reranked3 = rerank_candidates_with_meanings(
        cands3,
        meanings_for_hanzi=lambda hz: meaning_map3.get(hz, []),
        active_category="",
        category_profiles={},
    )
    fixtures.append(_case("rerank_candidates_with_meanings_tagged", {
        "cands": cands3,
        "meaning_map": meaning_map3,
        "active_category": "",
        "category_profiles": {},
        "hk_freq_map": {},
        "hk_colloquial": [],
        "hk_attested": [],
    }, reranked3))

    # 19) _coerce_candidates (freq in slot 2 and 3)
    coerce_cases2 = [
        {"raw": [("飲", 5), ("喝", "tier1", 7.5)], "default_source": "tier2"},
    ]
    for inp in coerce_cases2:
        out = _coerce_candidates(inp["raw"], inp["default_source"])
        fixtures.append(
            _case(
                "coerce_candidates_freq",
                inp,
                [(c.hanzi, c.source, c.freq) for c in out],
            )
        )

    # 20) HanziCandidatePipeline (tier1 path)
    t1_map = {
        "jam2": [("飲", "tier1", 1.0), ("喝", "tier1", 1.0)],
    }
    meaning_map_t1 = {"飲": ["drink", "beverage"], "喝": ["drink"]}
    profiles_t1 = {"food": {"drink": 2.0, "beverage": 1.0}}

    deps_t1 = HanziPipelineDeps(
        normalize_jyutping=normalize_jyutping,
        tier1_reverse_candidates=lambda jy: t1_map.get(jy, []),
        cc_glosses_for=lambda hz: meaning_map_t1.get(hz, []),
        gloss_cleaner=clean_glosses_for_display,
        active_category_provider=lambda: "food",
        category_profiles=profiles_t1,
        max_candidates=5,
    )
    pipe_t1 = HanziCandidatePipeline(deps_t1)
    out_t1 = pipe_t1.run("jam2")
    fixtures.append(_case("pipeline_tier1", {"jyut": "jam2"}, out_t1))

    # 21) HanziCandidatePipeline (tier2 path)
    def _compose_stub(jy_norm: str, _char_map: dict):
        return [("飲", "tier2-char", 1.0), ("喝", "tier2-char", 2.0)]

    def _shortlist_stub(items: object):
        try:
            return list(items)[:1]
        except Exception:
            return items

    deps_t2 = HanziPipelineDeps(
        normalize_jyutping=normalize_jyutping,
        tier1_reverse_candidates=lambda _jy: [],
        tier2_compose=_compose_stub,
        tier2_shortlist=_shortlist_stub,
        char_map={"飲": "jam2"},
        max_candidates=5,
    )
    pipe_t2 = HanziCandidatePipeline(deps_t2)
    out_t2 = pipe_t2.run("jam2")
    fixtures.append(_case("pipeline_tier2", {"jyut": "jam2"}, out_t2))

    # 22) HanziCandidatePipeline (manual mode)
    out_manual = pipe_t1.run("jam2", manual_hanzi_mode=True)
    fixtures.append(_case("pipeline_manual", {"jyut": "jam2"}, out_manual))

    # 23) build_pipeline_from_category_manager
    class _Prov:
        def __init__(self, mapping):
            self._m = mapping

        def get_candidates(self, jy):
            return self._m.get(jy, [])

    class _Dialog:
        pass

    dlg = _Dialog()
    dlg._normalize_jy = normalize_jyutping
    dlg._candidate_provider = _Prov({"jam2": [("飲", "tier1", 1.0)]})
    dlg._reverse_index = {}
    dlg._char_map = {"飲": "jam2"}
    dlg._cc_glosses_for = lambda hz: meaning_map_t1.get(hz, [])
    dlg._cedict_meanings_for = lambda hz: []
    dlg._candidate_curator = None
    dlg._selected_categories = ["food"]
    dlg._last_committed_category = ""
    dlg._add_cat = None
    dlg._hk_word_freq_map = {"飲": 10}
    dlg._hk_word_colloq = set()
    dlg._hk_word_attested = {"飲"}
    dlg.MAX_HANZI_CANDIDATES = 5

    pipe_from = build_pipeline_from_category_manager(dlg)
    out_from = pipe_from.run("jam2")
    fixtures.append(_case("build_pipeline_from_category_manager", {"jyut": "jam2"}, out_from))

    # 24) MeaningResolver + MeaningFacade
    cc_map = {"飲": ["drink", "beverage", ""], "喝": ["drink"]}
    ce_map = {"飲": ["to drink"], "話": ["speech"]}
    resolver = MeaningResolver(cc_glosses_for=lambda hz: cc_map.get(hz, []),
                               cedict_meanings_for=lambda hz: ce_map.get(hz, []))
    fixtures.append(_case("meaning_resolver_glosses_for", {"hanzi": "飲", "limit": 2},
                          resolver.glosses_for("飲", limit=2)))
    fixtures.append(_case("meaning_resolver_glosses_fallback", {"hanzi": "話", "limit": 2},
                          resolver.glosses_for("話", limit=2)))

    facade = MeaningFacade(resolver=resolver, cleaner=clean_glosses_for_display)
    fixtures.append(_case("meaning_facade_meanings_for_display", {"hanzi": "飲"},
                          facade.meanings_for_display("飲")))
    fixtures.append(_case("meaning_facade_preview", {"hanzi": "飲", "max_items": 1},
                          facade.preview_for_display("飲", max_items=1)))
    fixtures.append(_case("meaning_facade_candidate_label", {"hanzi": "飲", "source": "cccanto", "preferred": True},
                          facade.candidate_label("飲", "cccanto", preferred=True, max_items=2)))
    sel = facade.select_candidate("飲", "cccanto", preferred=True, max_items=2)
    fixtures.append(_case("meaning_facade_select_candidate", {"hanzi": "飲", "source": "cccanto"},
                          {"hanzi": sel.hanzi, "source": sel.source, "meanings": sel.meanings, "label": sel.label}))

    # 25) EntryValidator
    ev = EntryValidator()
    res_all = ev.validate_all(jyutping="nei5 hou2", hanzi="你好", meanings="hello, hi", category="greetings")
    fixtures.append(_case("entry_validator_validate_all", {}, {k: vars(v) for k, v in res_all.items()}))
    fixtures.append(_case("entry_validator_is_valid_entry", {}, ev.is_valid_entry(
        jyutping="nei5 hou2", hanzi="你好", meanings="hello", category="greetings"
    )))

    # 26) VocabularyService add/update
    vocab = {}
    cats = {"unassigned": []}
    svc = VocabularyService(vocab=vocab, categories=cats)
    import copy
    entry = svc.add_entry("nei5 hou2", "你好", ["hello"], ["greetings"])
    fixtures.append(_case("vocab_service_add_entry", {}, {
        "entry": entry.to_dict(),
        "vocab": copy.deepcopy(vocab),
        "categories": copy.deepcopy(cats),
    }))
    updated = svc.update_entry("你好", "nei5 hou2", "你好呀", ["hello there"], ["greetings"])
    fixtures.append(_case("vocab_service_update_entry", {}, {
        "entry": updated.to_dict(),
        "vocab": copy.deepcopy(vocab),
        "categories": copy.deepcopy(cats),
    }))

    return fixtures


def main() -> None:
    out_path = _fixture_path()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    fixtures = generate()
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(fixtures, fh, ensure_ascii=False, indent=2)
    print(f"Wrote {len(fixtures)} fixtures -> {out_path}")


if __name__ == "__main__":
    main()
