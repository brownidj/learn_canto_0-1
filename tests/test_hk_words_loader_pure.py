import csv


def _write_csv(path, rows):
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.writer(fh)
        for row in rows:
            writer.writerow(row)


def test_load_words_hk_reads_freq_and_colloquial(tmp_path, monkeypatch):
    from services.hk_words import load_words_hk

    p = tmp_path / "words_hk.csv"
    _write_csv(
        p,
        [
            ["word", "freq", "register"],
            ["飲野", "120", "colloquial"],
            ["工作", "80", "literary"],
        ],
    )

    freq_map, colloq, attested = load_words_hk(str(p))
    assert freq_map.get("飲野") == 120.0
    assert freq_map.get("工作") == 80.0
    assert "飲野" in colloq
    assert "飲野" in attested
    assert "工作" in attested


def test_load_words_hk_uses_rank_if_no_freq(tmp_path):
    from services.hk_words import load_words_hk

    p = tmp_path / "words_hk.csv"
    _write_csv(
        p,
        [
            ["hanzi", "rank"],
            ["講", "1"],
            ["去", "2"],
        ],
    )

    freq_map, colloq, attested = load_words_hk(str(p))
    assert freq_map.get("講") > freq_map.get("去")
    assert "講" in attested
    assert "去" in attested
