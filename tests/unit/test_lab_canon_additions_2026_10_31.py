"""Расширение словаря канона 2026-10-31: аналиты из экспорта личной базы (labs_export.md),
которых у канона не было — непрямой билирубин, UIBC, общие T3/T4, тиреоглобулин, витамины
K1/B2/B3/B5, антиоксидантные ферменты, ENA-панель, серологии, стул-маркеры, КЖК.

Сторожа: новые имена — неподвижные точки normalize; старые имена не перехвачены
(PCT остаётся тромбокритом, «тг» — триглицеридами, ELI-ДНК не уехала в Anti_dsDNA).
"""
from __future__ import annotations

import pytest

import lab_canon as LC

pytestmark = pytest.mark.unit

ADDED = ["Bilirubin_indirect", "UIBC", "T3_total", "T4_total", "Thyroglobulin", "Vitamin_K1",
         "Vitamin_B2", "Lactate", "Procalcitonin", "SOD", "Glutathione_peroxidase", "TAS", "MDA",
         "AMH", "sTfR", "Kappa_free", "Lambda_free", "Kappa_Lambda_ratio", "eGFR", "Non_HDL",
         "Beta_globulin", "Anti_dsDNA", "Anti_Sm", "Anti_SSA_Ro52", "HBsAg", "Anti_HCV", "CMV_IgG",
         "Toxoplasma_IgG", "Giardia_Ab", "SCFA_butyrate", "Anaerobic_index", "De_Ritis_ratio",
         "Reactive_lymphocytes_pct", "T_helpers_naive_pct", "Lupus_anticoagulant_ratio", "EPA_DHA_total"]


@pytest.mark.parametrize("canon", ADDED)
def test_added_canonicals_are_fixed_points(canon):
    assert canon in LC.CANONICALS
    assert LC.normalize(canon) == canon


@pytest.mark.parametrize("raw,canon", [
    ("Indirect Bilirubin (unconjugated)", "Bilirubin_indirect"),
    ("Непрямой билирубин", "Bilirubin_indirect"),
    ("Unsaturated Iron Binding Capacity (UIBC)", "UIBC"),
    ("НЖСС", "UIBC"),
    ("Total T3", "T3_total"), ("Т4 общий", "T4_total"),
    ("Thyroglobulin (Tg)", "Thyroglobulin"),
    ("Vitamin K1 (Phylloquinone)", "Vitamin_K1"),
    ("Витамин В2", "Vitamin_B2"),                       # кириллическая В — гомоглиф
    ("Lactate (Lactic Acid)", "Lactate"),
    ("Procalcitonin", "Procalcitonin"),
    ("Superoxide Dismutase (SOD) erythrocytes", "SOD"),
    ("Anti-Müllerian Hormone (AMH)", "AMH"), ("АМГ", "AMH"),
    ("Free Kappa/Lambda Ratio", "Kappa_Lambda_ratio"),
    ("Estimated Glomerular Filtration Rate (eGFR)", "eGFR"), ("СКФ", "eGFR"),
    ("Non-HDL Cholesterol", "Non_HDL"),
    ("Total Bilirubin", "Bilirubin_total"), ("Total Cholesterol", "Cholesterol_Total"),  # англ. «Total X» не читался
    ("Total EPA + DHA (Omega-3 fatty acids)", "EPA_DHA_total"),
    ("Lupus Anticoagulant screening", "Lupus_anticoagulant_screen"),
    ("Lupus Anticoagulant confirmatory", "Lupus_anticoagulant_confirm"),
    ("Beta-Globulins (g/L)", "Beta_globulin"),
    ("Anti-SS-A/Ro 52 kDa Antibodies IgG", "Anti_SSA_Ro52"),
    ("Hepatitis B Surface Antigen (HBsAg)", "HBsAg"),
    ("Toxoplasma gondii IgG", "Toxoplasma_IgG"),
    ("C4 Butyric Acid (mg/g)", "SCFA_butyrate"),
    ("De Ritis Ratio (AST/ALT)", "De_Ritis_ratio"),
    ("Reactive Lymphocytes (RE-LYMP) %", "Reactive_lymphocytes_pct"),
    ("CD4+CD45RA+ Naive Th-Cells %", "T_helpers_naive_pct"),
])
def test_export_spellings_resolve(raw, canon):
    assert LC.normalize(raw) == canon


def test_old_homes_not_hijacked():
    """Негативный контроль: соседние по написанию старые имена остались у своих статей."""
    assert LC.normalize("PCT") == "PCT"                       # тромбокрит, не прокальцитонин
    assert LC.normalize("ТГ") == "Triglycerides"               # не тиреоглобулин
    assert LC.normalize("Антитела к тиреоглобулину") == "Anti_Thyroglobulin"
    assert LC.normalize("Bilirubin direct") == "Bilirubin_direct"
    assert LC.normalize("FT3") == "T3_free" and LC.normalize("FT4") == "T4_free"
    assert LC.normalize("Глутатион") == "Glutathione_reduced"
    assert LC.normalize("Alpha 1") == "Alpha1_globulin"
    assert LC.identity_name("Тироглобулин", "%") == "ELI_Thyroglobulin"
    assert LC.normalize("Зюзюблик обыкновенный") not in LC.CANONICALS


def test_beta_globulin_dimension_and_ratios_dimensionless():
    assert LC.dimension_key("Beta_globulin", "%") == "Beta_globulin_pct"
    assert LC.dimension_key("Beta_globulin", "g/L") == "Beta_globulin_conc"
    assert {"Beta_globulin_pct", "Beta_globulin_conc"} <= LC.CANONICALS
    for n in ("De_Ritis_ratio", "Kappa_Lambda_ratio", "ApoB_ApoA1_ratio", "Anaerobic_index", "SII"):
        assert LC.is_dimensionless(n), n


def test_no_unreachable_synonym_among_added():
    dead = [(c, v) for c in ADDED for v in LC.synonyms_for(c) if LC.normalize(v) != c]
    assert not dead, dead


def test_estradiol_lands_in_one_scale():
    """Серия эстрадиола из двух методов: pmol/L (hs) и ng/L (ИФА) — одна шкала после to_conventional."""
    v, u = LC.to_conventional("Estradiol", 240.0, "pmol/L")
    assert u == "pg/mL" and abs(v - 65.38) < 0.01
    assert LC.to_conventional("Estradiol", 12.42, "ng/L") == (12.42, "pg/mL")
    assert LC.to_conventional("Estradiol", 20.0, "pg/mL") == (20.0, "pg/mL")
    lo, hi = LC.to_conventional_range("Estradiol", 29.0, 147.0, "pmol/L")
    assert abs(lo - 7.9) < 0.01 and abs(hi - 40.04) < 0.01
