import pytest

from document_engine.checklist import build_checklist, specs_for
from document_engine.document_acquisition import build_document_packages
from document_engine.typology import TYPOLOGIES
from schemas import TipoDocumento


def keys(typology, contract="vendita"):
    record = {"id": 1, "typology": typology, "contract": contract, "property_type": TYPOLOGIES[typology].asset, "is_condominio": False}
    return {i["key"] for i in build_checklist(property_record=record, documents=[], findings=[])["items"] if i["applicable"]}


def test_each_typology_gets_its_own_documents():
    assert {"collaudo_statico", "certificato_destinazione_urbanistica", "libretto_impianto"} <= keys("villa")
    assert not {"collaudo_statico", "libretto_impianto"} & keys("appartamento")
    assert {"autorizzazione_ambientale", "valutazione_amianto", "verifica_messa_a_terra", "collaudo_statico"} <= keys("capannone")
    assert {"autorizzazione_grande_struttura", "convenzione_urbanistica", "regolamento_centro_commerciale", "elenco_locazioni"} <= keys("centro_commerciale")
    assert "valutazione_amianto" in keys("magazzino") and "autorizzazione_ambientale" not in keys("magazzino")
    # an office or a plain warehouse does not normally hold a commercial licence; a shop does
    assert "scia_licenza_commerciale" not in keys("ufficio") | keys("magazzino")
    assert "scia_licenza_commerciale" in keys("negozio")


def test_commercial_typologies_are_no_longer_interchangeable():
    lists = {t: frozenset(keys(t)) for t in ("negozio", "ufficio", "capannone", "laboratorio", "magazzino", "centro_commerciale")}
    assert len(set(lists.values())) >= 5          # only capannone and laboratorio may share the same list
    assert keys("villa") != keys("appartamento")


@pytest.mark.parametrize("typology", list(TYPOLOGIES))
@pytest.mark.parametrize("contract", ["vendita", "affitto"])
def test_every_checklist_key_is_a_document_type_the_classifier_can_return(typology, contract):
    known = {t.value for t in TipoDocumento}
    record = {"id": 1, "typology": typology, "contract": contract, "property_type": TYPOLOGIES[typology].asset}
    for spec in specs_for(record):
        assert spec.key in known, f"{spec.key} cannot be produced by the classifier"


def test_acquisition_plan_asks_for_the_same_specific_documents():
    def plan(typology):
        record = {"id": 1, "typology": typology, "contract": "vendita", "is_condominio": False, "is_rented": True}
        result = build_document_packages(record, [], [])
        return {i["document_type"] for g in result["packages"] for i in g["items"]}

    assert {"collaudo_statico", "certificato_destinazione_urbanistica"} <= plan("villa")
    assert {"autorizzazione_ambientale", "valutazione_amianto", "verifica_messa_a_terra"} <= plan("capannone")
    assert {"autorizzazione_grande_struttura", "convenzione_urbanistica", "regolamento_centro_commerciale"} <= plan("centro_commerciale")
    assert not {"autorizzazione_ambientale", "autorizzazione_grande_struttura"} & plan("appartamento")


# --- lease -------------------------------------------------------------------------------------------------

def lease(typology):
    return keys(typology, "affitto")


def test_box_lease_has_its_own_short_list():
    box = lease("box") - {"certificato_prevenzione_incendi"}      # the fire-safety question applies to every property
    assert box == {"visura_catastale", "planimetria", "visura_ipotecaria"}      # no deed, no assembly minutes
    assert "atto_di_provenienza" not in box and "verbale_assemblea_condominio" not in box


def test_home_lease_asks_for_the_heating_system_book_and_not_for_sale_documents():
    home = lease("appartamento")
    assert "libretto_impianto" in home and "atto_di_provenienza" not in home
    assert not {"collaudo_statico", "certificato_destinazione_urbanistica"} & lease("villa")    # sale-only documents


def test_commercial_leases_differ_by_typology():
    assert {"collaudo_statico", "autorizzazione_ambientale", "valutazione_amianto", "verifica_messa_a_terra"} <= lease("capannone")
    assert {"regolamento_centro_commerciale", "autorizzazione_grande_struttura"} <= lease("centro_commerciale")
    assert "valutazione_amianto" in lease("magazzino") and "autorizzazione_ambientale" not in lease("magazzino")
    assert "scia_licenza_commerciale" not in lease("ufficio") and "scia_licenza_commerciale" in lease("negozio")
    lists = {t: frozenset(lease(t)) for t in ("negozio", "ufficio", "capannone", "laboratorio", "magazzino", "centro_commerciale")}
    assert len(set(lists.values())) >= 5


SPECIFIC = {"collaudo_statico", "autorizzazione_ambientale", "valutazione_amianto", "verifica_messa_a_terra",
            "autorizzazione_grande_struttura", "convenzione_urbanistica", "regolamento_centro_commerciale",
            "certificato_destinazione_urbanistica"}


@pytest.mark.parametrize("typology", list(TYPOLOGIES))
@pytest.mark.parametrize("contract", ["vendita", "affitto"])
def test_what_is_requested_is_also_on_the_checklist(typology, contract):
    record = {"id": 1, "typology": typology, "contract": contract, "is_condominio": False, "is_rented": True}
    requested = {i["document_type"] for g in build_document_packages(record, [], [])["packages"] for i in g["items"]}
    assert (requested & SPECIFIC) <= keys(typology, contract), "requested documents the checklist does not know"
