"""Фаза R: «позиции нет в VCF полного генома = гомозигота по референсу» в рамках (28.09).

Решение владельца: вывод только для полного генома с вызывальщиком в заголовке (и GRCh37);
CYP2D6 и HLA-B — никогда; панель и экзом — без вывода; разошлось с чипом — откат всего
вывода. Референс по построению не несёт вариантного звёздного аллеля — даже если буква
референса совпала с зашитым аллелем эффекта (класс ложного «плохого метаболизатора» DPYD*13).
Все данные синтетические.
"""
import sqlite3

import pytest

import pharmaco_pipeline as pp
import vcf_import_pipeline as v

pytestmark = pytest.mark.unit

PANEL = {
    "rs4244285": {"gene": "CYP2C19", "chrom": "10", "pos": 96541616, "ref": "G"},
    "rs4986893": {"gene": "CYP2C19", "chrom": "10", "pos": 96540410, "ref": "G"},
    "rs12248560": {"gene": "CYP2C19", "chrom": "10", "pos": 96521657, "ref": "C"},
    "rs55886062": {"gene": "DPYD", "chrom": "1", "pos": 97981343, "ref": "A"},
}
HEAD_WGS = ["##fileformat=VCFv4.2", "##DeepVariant_version=1.5.0",
            "##contig=<ID=chr1,length=249250621>"]
COLS = "#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\tFORMAT\tSAMPLE"


def _vcf(tmp_path, header, rows, filler=0):
    lines = header + [COLS] + rows
    lines += [f"chr3\t{1000 + i}\t.\tA\tG\t30\tPASS\t.\tGT:GQ:DP\t0/1:40:30" for i in range(filler)]
    p = tmp_path / "s.vcf"
    p.write_text("\n".join(lines) + "\n")
    return p


def _db(chip=None):
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE raw_snps (rsid TEXT PRIMARY KEY, chromosome TEXT, position INTEGER, "
                "genotype TEXT, source TEXT)")
    for rsid, gt in (chip or {}).items():
        con.execute("INSERT INTO raw_snps VALUES (?,?,?,?, '23andme')", (rsid, "1", 1, gt))
    v.ensure_tables(con)
    return con


@pytest.fixture(autouse=True)
def _small_wgs(monkeypatch):
    monkeypatch.setattr(v, "WGS_MIN_RECORDS", 50)


def _src(con):
    return {r["rsid"]: (r["genotype"], r["source"]) for r in con.execute("SELECT * FROM raw_snps")}


def test_полный_геном_с_вызывальщиком_выводит_референс(tmp_path):
    con = _db()
    out = v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS, [], filler=60), panel=PANEL)
    assert out["may_infer"]
    assert _src(con)["rs4244285"] == ("GG", v.SRC_INFERRED)
    assert len(_src(con)) == len(PANEL)


@pytest.mark.parametrize("header,filler,why", [
    (HEAD_WGS, 10, "экзом/панель: мало записей"),
    (["##fileformat=VCFv4.2", "##contig=<ID=chr1,length=249250621>"], 60, "нет вызывальщика"),
    (["##fileformat=VCFv4.2", "##DeepVariant_version=1.5.0", "##contig=<ID=chr1,length=248956422>"], 60, "GRCh38"),
])
def test_вне_рамок_вывода_нет(tmp_path, header, filler, why):
    con = _db()
    out = v.phase_r_reference_fill(con, _vcf(tmp_path, header, [], filler=filler), panel=PANEL)
    assert not out["may_infer"], why
    assert _src(con) == {}


def test_refcall_это_свидетельство_даже_в_экзоме(tmp_path):
    rows = ["chr10\t96541616\t.\tG\tA\t30\tRefCall\t.\tGT:GQ:DP\t0/0:50:30"]
    con = _db()
    v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS, rows, filler=5), panel=PANEL)
    assert _src(con) == {"rs4244285": ("GG", v.SRC_REFCALL)}


def test_расхождение_с_чипом_откатывает_весь_вывод(tmp_path):
    con = _db(chip={"rs4244285": "GA"})                       # чип: гетерозигота *2
    out = v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS, [], filler=60), panel=PANEL)
    assert out["rolled_back"] == ["rs4244285"]
    assert _src(con) == {"rs4244285": ("GA", "23andme")}       # чип цел, выведенного нет


def test_cyp2d6_и_hla_b_вне_панели_вывода():
    panel = v.load_panel()
    assert not {p["gene"] for p in panel.values()} & {"CYP2D6", "HLA-B"}
    assert "rs2395029" not in panel and "rs1065852" not in panel


def _pharmaco_db():
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.executescript("""
        CREATE TABLE raw_snps (rsid TEXT PRIMARY KEY, chromosome TEXT, position INTEGER,
                               genotype TEXT, source TEXT);
        CREATE TABLE genome_imports (id INTEGER PRIMARY KEY, vcf_source TEXT, phase_e_pharmaco_at TEXT);
        CREATE TABLE pharmaco_phenotypes (id INTEGER PRIMARY KEY AUTOINCREMENT, gene TEXT NOT NULL,
            star_allele_1 TEXT, star_allele_2 TEXT, phenotype TEXT NOT NULL,
            confidence TEXT NOT NULL DEFAULT 'indeterminate', coverage_snp_count INTEGER DEFAULT 0,
            genome_import_id INTEGER, computed_at TEXT NOT NULL DEFAULT (datetime('now')));
        CREATE UNIQUE INDEX uq ON pharmaco_phenotypes(gene);
        INSERT INTO genome_imports (id) VALUES (1);
    """)
    return con


def test_выведенный_референс_норма_с_пониженной_уверенностью():
    con = _pharmaco_db()
    panel = v.load_panel()
    for rsid, p in panel.items():
        con.execute("INSERT INTO raw_snps VALUES (?,?,?,?,?)",
                    (rsid, p["chrom"], p["pos"], p["ref"] * 2, pp.INFERRED_SOURCE))
    res = pp.run(con, 1)["results"]
    assert res["CYP2C19"]["star_allele_1"] == "*1" and res["CYP2C19"]["star_allele_2"] == "*1"
    assert res["CYP2C19"]["confidence"] == "medium"             # вывод — не наблюдение
    assert "Poor" not in res["DPYD"]["phenotype"]              # «A» референса ≠ аллель эффекта *13
    assert res["DPYD"]["star_allele_1"] == res["DPYD"]["star_allele_2"]
    assert res["CYP2D6"]["confidence"] == "indeterminate"       # CYP2D6 не выводится никогда
    assert res["HLA-B"]["confidence"] == "indeterminate"


# ── GRCh38 (2026-10-31): файл DRAGEN/Nucleus hg38 читается по панели своей сборки ─────────────
HEAD_WGS38 = ["##fileformat=VCFv4.2", "##DRAGENCommandLine=<ID=dragen,Version=\"SW: 05.121\">",
              "##contig=<ID=chr1,length=248956422>"]


def test_панель_grch38_тот_же_набор_что_grch37():
    p37, p38 = v.load_panel(v.PANEL_FILES["GRCh37"]), v.load_panel(v.PANEL_FILES["GRCh38"])
    assert p37.keys() == p38.keys()
    for rsid in p37:
        assert (p37[rsid]["gene"], p37[rsid]["chrom"], p37[rsid]["ref"]) == \
               (p38[rsid]["gene"], p38[rsid]["chrom"], p38[rsid]["ref"]), rsid
        assert p37[rsid]["pos"] != p38[rsid]["pos"], rsid


def test_сборка_читается_из_заголовка():
    assert v.vcf_kind(HEAD_WGS, 0)["build"] == "GRCh37"
    assert v.vcf_kind(HEAD_WGS38, 0)["build"] == "GRCh38"
    assert v.vcf_kind(["##fileformat=VCFv4.2"], 0)["build"] is None


def test_полный_геном_grch38_выводит_референс_по_панели_grch38(tmp_path):
    """Без panel= фаза сама берёт панель по сборке файла; в raw_snps — координаты GRCh37 (чип)."""
    con = _db()
    out = v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS38, [], filler=60))
    assert out["may_infer"] and out["kind"]["build"] == "GRCh38"
    rows = {r["rsid"]: r for r in con.execute("SELECT * FROM raw_snps")}
    assert rows["rs4244285"]["genotype"] == "GG" and rows["rs4244285"]["source"] == v.SRC_INFERRED
    assert rows["rs4244285"]["position"] == 96541616            # GRCh37, не 94781859


def test_вариант_grch38_читается_по_координате_своей_сборки(tmp_path):
    rows = ["chr10\t94781859\t.\tG\tA\t50\tPASS\t.\tGT:GQ:DP\t0/1:45:30"]   # rs4244285 в GRCh38
    con = _db()
    v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS38, rows, filler=5))
    assert _src(con) == {"rs4244285": ("GA", v.SRC_PANEL)}


def test_панель_grch37_на_файле_grch38_не_выводит_и_не_совпадает(tmp_path):
    """Явно переданная GRCh37-панель на hg38-файле: координата rs4244285 (GRCh38) ей неизвестна."""
    rows = ["chr10\t94781859\t.\tG\tA\t50\tPASS\t.\tGT:GQ:DP\t0/1:45:30"]
    con = _db()
    out = v.phase_r_reference_fill(con, _vcf(tmp_path, HEAD_WGS38, rows, filler=60), panel=PANEL)
    assert not out["may_infer"] and _src(con) == {}


def test_фазы_A_и_B_отказывают_на_grch38(tmp_path, monkeypatch):
    """Чужая сборка — отказ с записью в журнал, ни одного запроса наружу."""
    def _no_network(*a, **k):
        raise AssertionError("myvariant.info вызван на GRCh38")
    monkeypatch.setattr(v.requests, "post", _no_network)
    con = _db(chip={"rs4244285": "GG"})
    vcf = _vcf(tmp_path, HEAD_WGS38, ["chr1\t1\t.\tA\tG\t50\tPASS\t.\tGT:GQ:DP\t0/1:45:30"], filler=60)
    assert v.phase_a_update_known(con, vcf) == {}
    v.phase_b_discover_new(con, vcf)
    log_rows = con.execute("SELECT phase, step, status FROM vcf_import_log ORDER BY phase").fetchall()
    assert [tuple(r) for r in log_rows] == [("A", "refused", "error"), ("B", "refused", "error")]
    assert _src(con) == {"rs4244285": ("GG", "23andme")}


def test_genome_imports_хранит_фактический_vcf(monkeypatch):
    """Провенанс: в genome_imports пишется файл прогона (--vcf), а не путь по умолчанию
    (до 2026-10-31 записывался несуществующий data/genome.vcf при фактическом genome.vcf.gz)."""
    con = _db()
    monkeypatch.setattr(v, "VCF_SOURCE", v.Path("/t/genome.vcf.gz"))
    v.phase_e_pharmaco(con)
    assert [r[0] for r in con.execute("SELECT vcf_source FROM genome_imports")] == ["/t/genome.vcf.gz"]
